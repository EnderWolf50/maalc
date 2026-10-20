"""Manual check for #149: run MirrorHub's dispatch over real captures offline and watch the process memory.

No emulator: a CustomController hands out tests/screens/*.png in turn, the repo's resource bundle (with the OCR
model from tools/fetch_ocr.py) runs MirrorHub's next list round after round, every listed node's action is
DoNothing and the agent is not started (its custom recognitions just miss). The Tasker runs in this process, so
this process's memory is the Tasker's.

    uv run --with opencv-python-headless python tools/ocr_memory_check.py --minutes 3 --csv mem.csv

Prints a line every 10 s and a summary. Exits 1 when the memory passes --cap-mb (it stops there), or when the median
of the last minute is more than --limit-mb over the median of the second (the first minute is warm-up; a single
batch OCR can spike a few hundred MB and give it back, so peaks alone do not fail).
"""

import argparse
import ctypes
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def memory_mb():
    """(private, working set) in MB."""
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        c = Counters(cb=ctypes.sizeof(Counters))
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        # private bytes decide: the working set also moves when Windows trims it
        return c.PagefileUsage / 2**20, c.WorkingSetSize / 2**20
    rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    return rss, rss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3)
    ap.add_argument("--screens", type=Path, default=ROOT / "tests" / "screens")
    ap.add_argument("--bundle", type=Path, default=ROOT / "assets" / "resource" / "base")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--limit-mb", type=float, default=300, help="allowed growth, last minute over the second")
    ap.add_argument("--cap-mb", type=float, default=6000, help="stop early past this much memory")
    ap.add_argument("--log-dir", type=Path, help="write MaaFramework's log here (default: no log)")
    args = ap.parse_args()

    if not (args.bundle / "model/ocr/rec.onnx").is_file():
        sys.exit("no OCR model: run tools/fetch_ocr.py first")

    import cv2
    from maa.controller import CustomController
    from maa.resource import Resource
    from maa.tasker import Tasker

    screens = [cv2.imread(str(p)) for p in sorted(args.screens.glob("*.png"))]
    screens = [s for s in screens if s is not None and s.shape[:2] == (720, 1280)]
    frames = [0]

    class Screens(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "ocr-memory-check"

        def screencap(self):
            frames[0] += 1
            return screens[frames[0] % len(screens)]

        def __getattr__(self, name):  # clicks, swipes, keys: nothing moves
            return lambda *a: True

    if args.log_dir:
        Tasker.set_log_dir(args.log_dir)
    Tasker.set_stdout_level(0)
    Tasker.set_save_draw(False)
    Tasker.set_save_on_error(False)

    resource = Resource()
    resource.post_bundle(args.bundle).wait()
    sys.path.insert(0, str(ROOT / "agent"))
    from hub_text import HubText

    resource.register_custom_recognition("HubText", HubText())  # the Agent's, in this process
    controller = Screens()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)

    # MirrorHub as it is, minus leaving it: no timeout, every listed node does nothing and comes back.
    hub = resource.get_node_data("MirrorHub")
    override = {"MirrorHub": {"timeout": 2**31 - 1, "on_error": []}}
    for entry in hub["next"]:
        name, jump_back = entry["name"], entry["jump_back"]
        override[name] = {"action": "DoNothing", "pre_delay": 0, "post_delay": 0, "on_error": [],
                          "next": [] if jump_back else ["MirrorHub"]}
    # BattleHUD's own list runs too (the battle screen's popups and turn); its nodes go back through the jump back.
    if hud := resource.get_node_data("BattleHUD"):  # (a bundle from before #157 has none)
        override["BattleHUD"] = {"pre_delay": 0, "post_delay": 0}
        for entry in hud["next"]:
            override[entry["name"]] = {"action": "DoNothing", "pre_delay": 0, "post_delay": 0, "on_error": [],
                                       "next": []}

    # HubText's list: the screens it picks, then the tail; they too do nothing and come back.
    if text := resource.get_node_data("HubText"):  # (a bundle from before #157 has none)
        override["HubText"] = {"pre_delay": 0, "post_delay": 0}
        param = text["recognition"]["param"]["custom_recognition_param"]
        param = json.loads(param) if isinstance(param, str) else param
        for name in param["entries"] + param["tail"]:
            override[name] = {"action": "DoNothing", "pre_delay": 0, "post_delay": 0, "on_error": [], "next": []}

    samples = []
    t0 = time.monotonic()
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            samples.append((time.monotonic() - t0, frames[0], *memory_mb()))
            if len(samples) % 10 == 1:
                t, f, m, ws = samples[-1]
                print(f"{t:6.0f} s  {f:6d} screens  {m:7.0f} MB  (working set {ws:.0f} MB)", flush=True)
            if samples[-1][2] > args.cap_mb:
                print(f"over {args.cap_mb:.0f} MB, stopping", flush=True)
                return
            stop.wait(1)

    sampler = threading.Thread(target=sample)
    sampler.start()
    job = tasker.post_task("MirrorHub", override)
    end = t0 + args.minutes * 60
    while time.monotonic() < end and not job.done and sampler.is_alive():
        time.sleep(0.5)
    tasker.post_stop().wait()
    stop.set()
    sampler.join()

    if args.csv:
        args.csv.write_text("seconds,screens,private_mb,working_set_mb\n"
                            + "".join(f"{t:.1f},{f},{m:.1f},{ws:.1f}\n" for t, f, m, ws in samples))
    last = samples[-1][0]
    second = statistics.median([m for t, _, m, _ in samples if 60 <= t < 120] or [samples[-1][2]])
    final = statistics.median([m for t, _, m, _ in samples if t >= last - 60])
    grew = final - second
    print(f"screens {frames[0]}, start {samples[0][2]:.0f} MB, peak {max(s[2] for s in samples):.0f} MB, "
          f"median of minute 2 {second:.0f} MB, of the last minute {final:.0f} MB, growth {grew:.0f} MB")
    sys.exit(1 if grew > args.limit_mb or samples[-1][2] > args.cap_mb else 0)


if __name__ == "__main__":
    main()
