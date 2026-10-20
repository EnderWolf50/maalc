"""Manual check for #149: run MirrorHub's dispatch over real captures offline and watch the process memory.

No emulator: a CustomController hands out tests/screens/*.png in turn, the repo's resource bundle (with the OCR
model from tools/fetch_ocr.py) runs MirrorHub's next list round after round, every listed node's action does
nothing (a custom action that only clears the cache when asked) and the agent is not started (its custom recognitions just miss). The Tasker runs in this process, so
this process's memory is the Tasker's.

    uv run --with opencv-python-headless python tools/ocr_memory_check.py --minutes 3 --csv mem.csv

`--clear-nodes N` calls `tasker.clear_cache()` from the action of the node that hit once the task has N nodes, as
the Agent's hands_back does (#176): a clear between nodes leaves the task without a detail, and custom recognitions
miss until a node ends.
The summary adds the slope after minute 5 (least squares, MB/h) and the round time (one screencap to the next).

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
    ap.add_argument("--clear-nodes", type=int, help="call tasker.clear_cache() once the task has this many nodes")
    args = ap.parse_args()

    if not (args.bundle / "model/ocr/rec.onnx").is_file():
        sys.exit("no OCR model: run tools/fetch_ocr.py first")

    import cv2
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker

    screens = [cv2.imread(str(p)) for p in sorted(args.screens.glob("*.png"))]
    screens = [s for s in screens if s is not None and s.shape[:2] == (720, 1280)]
    frames = [0]
    rounds = []  # (seconds, round time in ms)

    class Screens(CustomController):
        last = None  # the previous screencap

        def connect(self):
            return True

        def request_uuid(self):
            return "ocr-memory-check"

        def screencap(self):
            now = time.monotonic()
            if self.last is not None:
                rounds.append((now - t0, (now - self.last) * 1000))
            self.last = now
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
    class Clear(CustomAction):
        def run(self, context, argv):
            if args.clear_nodes and len(argv.task_detail.node_id_list) >= args.clear_nodes:
                context.tasker.clear_cache()
            return True

    resource.register_custom_action("Clear", Clear())
    # both arms pay the same custom action
    nothing = {"action": "Custom", "custom_action": "Clear", "pre_delay": 0, "post_delay": 0, "on_error": []}
    controller = Screens()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)

    # MirrorHub as it is, minus leaving it: no timeout, every listed node does nothing and comes back.
    hub = resource.get_node_data("MirrorHub")
    override = {"MirrorHub": {"timeout": 2**31 - 1, "on_error": []}}
    for entry in hub["next"]:
        name, jump_back = entry["name"], entry["jump_back"]
        override[name] = {**nothing, "next": [] if jump_back else ["MirrorHub"]}
    # BattleHUD's own list runs too (the battle screen's popups and turn); its nodes go back through the jump back.
    if hud := resource.get_node_data("BattleHUD"):  # (a bundle from before #157 has none)
        override["BattleHUD"] = {"pre_delay": 0, "post_delay": 0}
        for entry in hud["next"]:
            override[entry["name"]] = {**nothing, "next": []}

    # HubText's list: the screens it picks, then the tail; they too do nothing and come back.
    if text := resource.get_node_data("HubText"):  # (a bundle from before #157 has none)
        override["HubText"] = {"pre_delay": 0, "post_delay": 0}
        param = text["recognition"]["param"]["custom_recognition_param"]
        param = json.loads(param) if isinstance(param, str) else param
        for name in param["entries"] + param["tail"]:
            override[name] = {**nothing, "next": []}

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
    tasker.post_task("MirrorHub", override)
    end = t0 + args.minutes * 60
    # tasker.running, not the job's status: a clear drops the task's id (running turns on with the first round)
    while time.monotonic() < end and (tasker.running or not frames[0]) and sampler.is_alive():
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
    after5 = [(t, m) for t, _, m, _ in samples if t >= 300]
    if len(after5) > 1:  # least squares
        mean_t, mean_mb = statistics.fmean(t for t, _ in after5), statistics.fmean(m for _, m in after5)
        slope = (sum((t - mean_t) * (m - mean_mb) for t, m in after5)
                 / sum((t - mean_t) ** 2 for t, _ in after5) * 3600)
        print(f"slope after minute 5: {slope:.0f} MB/h")
    for span, times in (("first 5 min", [ms for t, ms in rounds if t < 300]),
                        ("last 5 min", [ms for t, ms in rounds if t >= last - 300]),
                        ("all", [ms for _, ms in rounds])):
        if len(times) > 1:
            deciles = statistics.quantiles(times, n=10)
            print(f"round time {span}: n {len(times)}, p50 {statistics.median(times):.0f} ms, p90 {deciles[8]:.0f} ms")
    sys.exit(1 if grew > args.limit_mb or samples[-1][2] > args.cap_mb else 0)


if __name__ == "__main__":
    main()
