"""Screenshots of the PC client's window, stage 1 of the PC client (#941, spec #922 D5, D6, D14, D15): no input at all.

    uv run python tools/live/queue.py run --resource emulator --name <task> -- uv run python tools/live/pc_shots.py <command>

  info --out DIR              the one game window as Windows says (step 1-1): title, class, client area, window rect,
                              DPI, styles, HDR of its monitor, the Steam build; DIR/info.json
  compare --out DIR [--count N]   N shots (5) with each background method, FramePool and PrintWindow (step 1-2): the
                              last of each saved, the ms of each, the mean difference of the two; DIR/compare.json
  watch --method M --out DIR [--every S] [--max-shots N] [--max-minutes M]
                              a shot every S s (2) with method M (framepool or printwindow), saved only when the screen
                              changed, until N saved (500), M minutes (20) or Ctrl-C (step 1-3); DIR/events.jsonl
  mask SRC DEST               copies of SRC's shots with the account's identity blacked out, for anyone else to see

The PC window is the emulator lane's (the same game account, D14): `info`, `compare` and `watch` act only under the
`queue.py run --resource emulator` ticket that holds the lane, and say why not otherwise. The user plays and turns the
pages; the tool reads the window and its screen and sends it nothing: its Win32 controller has mouse and keyboard Null
(runner/pc.py win32_controller, D6), so no input unit exists even by mistake.

Each shot goes through the PC window controller (runner/pc.py Controller), which looks at the window first (D5), and
reads, before and after it, the foreground window, the cursor, the window rect and the window's styles (read only:
GetForegroundWindow, GetCursorPos, GetWindowRect, GetWindowLongPtrW). Any of them different after the shot stops the
tool, and so do: the window gone, minimized or not 16:9, a black shot, a shot not 16:9 (#941 stop conditions 1 and 2).
Each shot and the stop go to DIR/events.jsonl, one JSON object a line. Exit 0 at a limit or Ctrl-C, 1 at a stop.

Shots carry the account's identity (UID, e-mail, player name): they stay in the evidence archive. `mask` writes the
copies to show or commit; it refuses until IDENTITY below is measured on PC shots (D15).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:  # run as a script, `live` is not importable until tools/ is on the path
    sys.path.insert(0, str(TOOLS))
REPO = TOOLS.parent
if str(REPO) not in sys.path:  # runner/ is the repo's
    sys.path.insert(0, str(REPO))

from live import queue  # noqa: E402
from runner import pc  # noqa: E402

METHODS = {"FramePool": pc.FRAME_POOL, "PrintWindow": pc.PRINT_WINDOW}
EVERY, MAX_SHOTS, MAX_MINUTES = 2.0, 500, 20  # #941 step 1-3
PIXEL, CHANGED = 24, 0.01  # a screen changed: over 1% of its pixels (a 1/4-scale grey copy) moved by more than 24 levels
BLACK = 8  # a shot no pixel of which is brighter is black
STEAM_APP = "1973530"  # Limbus Company on Steam

# The account's identity on a PC shot (D15, AGENTS.md "Public repo"): the UID plate, the account e-mail and the player
# name above the LV panel, each (x, y, width, height) in a 1920x1080 shot's pixels, scaled to a shot's own size. Not
# measured yet: stage 1 measures them on the first PC shots (#941); the Android ones (tests/test_screens_privacy.py) do
# not carry over. Until all three are, `mask` refuses, so no PC shot leaves the archive unmasked.
IDENTITY: dict[str, tuple | None] = {"uid": None, "email": None, "name": None}
IDENTITY_WIDTH = 1920


def wide(width: int, height: int) -> bool:
    return width > 0 and width * 9 == height * 16


class Stop(Exception):
    """A stop condition held: the tool ends at once and says why."""


@dataclass(frozen=True)
class State:
    """What a shot must leave as it was (#941 stop condition 1): the foreground window, the cursor, the game window's
    rect (x, y, width, height) and its styles (GWL_STYLE, GWL_EXSTYLE)."""
    foreground: int
    cursor: tuple
    rect: tuple
    style: int
    exstyle: int


def differs(before: State, after: State) -> list[str]:
    return [f.name for f in fields(State) if getattr(before, f.name) != getattr(after, f.name)]


def lane_trouble(env=os.environ, qdir: Path | None = None, is_alive=queue.alive) -> str | None:
    """None when this process runs under the ticket that holds the emulator lane; else why it may not touch the window."""
    ticket = env.get(queue.TICKET_ENV)
    if not ticket:
        return ("not run under `queue.py run --resource emulator`: the PC window is the emulator lane's (the same game "
                "account, spec #922 D14); queue this command on it")
    qdir, me = qdir or queue.queue_dir("emulator"), Path(ticket)
    if me.parent.resolve() != qdir.resolve():
        return f"the ticket {me.name} is not the emulator lane's: queue this command with --resource emulator"
    held = queue.tickets(qdir, is_alive) if qdir.exists() else []
    if not held or held[0].name != me.name:
        return f"the ticket {me.name} does not hold the emulator lane: {held[0].name if held else 'nobody'} does"
    return None


def one_window(windows) -> int:
    """The handle of the one game window (D3), not minimized."""
    found = pc.games(windows)
    if len(found) != 1:
        raise Stop(f"{len(found) or 'no'} game window{'s' if len(found) != 1 else ''} ({pc.CLASS}, {pc.TITLE}): "
                   f"open exactly one, windowed")
    if (p := pc.trouble(windows.look(found[0]), aspect=False)) is not None:
        raise Stop(explain(p))
    return found[0]


def explain(problem: pc.Problem) -> str:
    if problem.code == "PcMinimized":
        return (f"{problem.message}: stopped and took nothing. A background screencap of a minimized window changes it "
                f"(MaaFramework makes it transparent and shows it unactivated, spec #922 D5): restore the window, keep it "
                f"unminimized and start the tool again")
    return problem.message


def stamp() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


class Log:
    """DIR/events.jsonl, one event a line, flushed as it is written."""

    def __init__(self, out: Path):
        out.mkdir(parents=True, exist_ok=True)
        self.path = out / "events.jsonl"

    def __call__(self, action: str, **data) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": stamp(), "action": action, **data}) + "\n")


def controller(windows, hwnd, method: str, make=None) -> pc.Controller:
    """The PC window controller on a Win32 controller of `method` (a name of METHODS), mouse and keyboard Null,
    connected."""
    ctl = pc.Controller(hwnd, windows, inner=lambda h: pc.win32_controller(h, screencap=METHODS[method], make=make))
    if not ctl.connect():
        raise Stop(explain(ctl.problem) if ctl.problem else "the connect to the game's window failed")
    return ctl


class StateStop(Stop):
    """A stop condition a shot met, with the state before and after it and the fields that differ."""

    def __init__(self, reason: str, before: State | None, after: State | None, differ: list[str] | None = None):
        super().__init__(reason)
        self.before, self.after, self.differ = before, after, differ or []

    def event(self) -> dict:
        return {"reason": str(self), "before": self.before and asdict(self.before),
                "after": self.after and asdict(self.after), "differs": self.differ}


def shot(ctl: pc.Controller, windows, hwnd) -> tuple[np.ndarray, float, State, State]:
    """One screencap: (image BGR, ms, the state before it, after it). The controller's guard looks at the window first
    (Controller.usable, D5), then the inner controller screencaps, and its job says whether it succeeded:
    Controller.screencap drops that, and a failed job's get() is the controller's cached image (maa/controller.py
    _get_screencap), the last frame, which would read as a screen that did not change. Every stop condition the shot
    meets raises StateStop."""
    before = windows.state(hwnd)
    t = time.perf_counter()
    job = ctl.inner.post_screencap().wait() if ctl.usable() else None
    ms = (time.perf_counter() - t) * 1000
    after = windows.state(hwnd)
    if ctl.problem is not None:
        raise StateStop(explain(ctl.problem), before, after)
    if before is None or after is None:
        raise StateStop(explain(pc.trouble(None)), before, after)
    if d := differs(before, after):
        raise StateStop(f"the game's window changed during the screencap: {', '.join(d)}", before, after, d)
    image = job.get() if job.succeeded else None
    if not isinstance(image, np.ndarray) or image.ndim != 3:
        raise StateStop("the screencap failed: no image", before, after)
    h, w = image.shape[:2]
    if not wide(w, h):
        raise StateStop(f"the shot is {w}x{h}, not 16:9", before, after)
    if image.max() <= BLACK:
        raise StateStop("the shot is black", before, after)
    return image, ms, before, after


def changed(a: np.ndarray | None, b: np.ndarray) -> float:
    """The share of the screen that changed from a to b (1.0 from nothing or another size)."""
    if a is None or a.shape != b.shape:
        return 1.0
    grey = lambda img: img[::4, ::4].astype(np.int16).mean(axis=2)
    return float((np.abs(grey(a) - grey(b)) > PIXEL).mean())


def save(image: np.ndarray, path: Path) -> None:
    Image.fromarray(np.ascontiguousarray(image[..., ::-1])).save(path)  # BGR as MaaFramework hands it out


def client(windows, hwnd) -> list[int] | None:
    look = windows.look(hwnd)
    return None if look is None else [look.width, look.height]


def watch(windows, out: Path, method: str, make=None, every: float = EVERY, max_shots: int = MAX_SHOTS,
          max_seconds: float = MAX_MINUTES * 60, clock=time.monotonic, sleep=time.sleep, say=print) -> None:
    """Step 1-3: a shot every `every` s with `method` (a name of METHODS), saved as shot-NNNN.png when the screen
    changed, until a limit or Ctrl-C; a stop condition raises Stop. The start (the window's client area and DPI), every
    shot (its client area too: the user may resize the window, step 1-4), the stop and the end go to out/events.jsonl."""
    log, ctl, saved, reason = Log(out), None, 0, None
    try:
        hwnd = one_window(windows)
        log("start", method=method, client=client(windows, hwnd), dpi=windows.dpi(hwnd))
        ctl = controller(windows, hwnd, method, make)
        start, last = clock(), None
        while reason is None:
            image, ms, before, after = shot(ctl, windows, hwnd)
            share = changed(last, image)
            file = None
            if share > CHANGED:
                saved, last = saved + 1, image
                file = f"shot-{saved:04d}.png"
                save(image, out / file)
                say(f"saved {file} ({share:.0%} changed, {ms:.0f} ms)")
            log("screencap", method=method, ms=round(ms, 2), changed=round(share, 4), saved=file,
                client=client(windows, hwnd), before=asdict(before), after=asdict(after))
            if saved >= max_shots:
                reason = f"{max_shots} shots saved"
            elif clock() + every - start >= max_seconds:
                reason = f"{max_seconds:.0f} s passed"
            else:
                sleep(every)
    except StateStop as stop:
        log("stop", **stop.event())
        raise
    except Stop as stop:
        log("stop", reason=str(stop))
        raise
    except KeyboardInterrupt:
        reason = "stopped by the user"
    finally:
        if ctl is not None:
            ctl.inactive()
    log("end", reason=reason, saved=saved)
    say(f"ended: {reason}, {saved} shots saved in {out}")


def compare(windows, out: Path, make=None, count: int = 5, say=print) -> dict:
    """Step 1-2: `count` shots with each background method; the last of each saved, the ms of all, the mean grey
    difference of the two last ones. out/compare.json; each shot and a stop go to out/events.jsonl."""
    if count < 1:
        raise ValueError("compare takes at least one shot a method")
    log, doc, last = Log(out), {"methods": {}}, {}
    for name in METHODS:
        ctl = None
        try:
            hwnd = one_window(windows)
            ctl = controller(windows, hwnd, name, make)
            ms = []
            for _ in range(count):
                image, took, before, after = shot(ctl, windows, hwnd)
                ms.append(round(took, 2))
                log("screencap", method=name, ms=round(took, 2), client=client(windows, hwnd), before=asdict(before),
                    after=asdict(after))
        except StateStop as stop:
            log("stop", method=name, **stop.event())
            raise
        except Stop as stop:
            log("stop", method=name, reason=str(stop))
            raise
        finally:
            if ctl is not None:
                ctl.inactive()
        save(image, out / f"compare-{name}.png")
        last[name] = image
        doc["methods"][name] = {"ms": ms, "median_ms": statistics.median(ms), "shape": list(image.shape)}
        say(f"{name}: median {statistics.median(ms):.1f} ms over {count}, saved compare-{name}.png")
    a, b = last.values()
    doc["mean_difference"] = float(np.abs(a.astype(np.int16) - b).mean()) if a.shape == b.shape else None
    (out / "compare.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def info(windows, out: Path, steam=None) -> dict:
    """Step 1-1: the one game window as Windows says; out/info.json."""
    hwnd = one_window(windows)
    look, state = windows.look(hwnd), windows.state(hwnd)
    doc = {"title": pc.TITLE, "class": pc.CLASS, "client": [look.width, look.height],
           "rect": list(look.rect), "minimized": look.minimized, "maximized": look.maximized,
           "fullscreen": look.fullscreen, "dpi": windows.dpi(hwnd), "style": hex(state.style),
           "exstyle": hex(state.exstyle), "hdr": windows.hdr(hwnd), "steam": (steam or steam_build)()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "info.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def steam_build(root: Path | None = None) -> dict:
    """The game's build as Steam's app manifest says (buildid, LastUpdated, installdir), found through the Steam folder
    the registry names and its library folders; {} when Steam or the manifest is not found."""
    if root is None:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                root = Path(winreg.QueryValueEx(key, "SteamPath")[0])
        except (ImportError, OSError):
            return {}
    libraries = [root]
    try:
        vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libraries += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    for lib in libraries:
        try:
            acf = (lib / "steamapps" / f"appmanifest_{STEAM_APP}.acf").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        keys = dict(re.findall(r'"(\w+)"\s+"([^"]*)"', acf))
        return {k: keys[k] for k in ("buildid", "LastUpdated", "installdir") if k in keys}
    return {}


def masked(img: Image.Image, regions: dict[str, tuple]) -> Image.Image:
    """img with each region (in 1920x1080 pixels) blacked out at img's own size, rounded outward."""
    img, k = img.convert("RGB"), img.width / IDENTITY_WIDTH
    for x, y, w, h in regions.values():
        box = (math.floor(x * k), math.floor(y * k), math.ceil((x + w) * k), math.ceil((y + h) * k))
        img.paste((0, 0, 0), box)
    return img


def mask(src: Path, dest: Path, say=print) -> int:
    """SRC's shots masked into DEST; refused (1) while a region of IDENTITY is not measured or a shot is not 16:9."""
    if unmeasured := [k for k, box in IDENTITY.items() if box is None]:
        say(f"refused: the identity regions of a PC shot are not measured yet ({', '.join(unmeasured)}; IDENTITY in "
            f"tools/live/pc_shots.py, spec #922 D15): measure them on PC shots first; no PC shot is shown to anyone or "
            f"committed unmasked")
        return 1
    shots = sorted(src.glob("*.png"))
    bad = [p.name for p in shots if not wide(*Image.open(p).size)]
    if bad:
        say(f"refused: not 16:9, so the regions do not scale onto them: {', '.join(bad)}")
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    for p in shots:
        masked(Image.open(p), IDENTITY).save(dest / p.name)
    say(f"{len(shots)} masked shots in {dest}")
    return 0


class Win32Desk(pc.Win32Windows):
    """runner/pc.py's windows with what this tool reads besides, all read only: the state a shot must leave as it was,
    the window's DPI and its monitor's HDR (advanced colour)."""

    def state(self, hwnd) -> State | None:
        u, wt, ct = self.user32, self.wintypes, self.ctypes
        if u is None or not u.IsWindow(wt.HWND(hwnd)):
            return None
        with self.aware():
            window, cursor = self._rect(u.GetWindowRect, hwnd), wt.POINT()
            if window is None or not u.GetCursorPos(ct.byref(cursor)):
                return None
            u.GetForegroundWindow.restype = wt.HWND
            get = u.GetWindowLongPtrW
            get.restype, get.argtypes = ct.c_ssize_t, [wt.HWND, ct.c_int]
            return State(int(u.GetForegroundWindow() or 0), (cursor.x, cursor.y),
                         (window.left, window.top, window.right - window.left, window.bottom - window.top),
                         get(wt.HWND(hwnd), -16) & 0xFFFFFFFF, get(wt.HWND(hwnd), -20) & 0xFFFFFFFF)

    def dpi(self, hwnd) -> int | None:
        get = getattr(self.user32, "GetDpiForWindow", None)
        return int(get(self.wintypes.HWND(hwnd))) or None if get else None

    def hdr(self, hwnd) -> dict:
        """The window's monitor (its GDI name) and whether advanced colour (HDR) is on there: QueryDisplayConfig and
        DisplayConfigGetDeviceInfo (GET_SOURCE_NAME, GET_ADVANCED_COLOR_INFO). None where Windows does not say."""
        ct, wt, u = self.ctypes, self.wintypes, self.user32

        class MONITORINFOEXW(ct.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD),
                        ("szDevice", wt.WCHAR * 32)]

        u.MonitorFromWindow.restype = wt.HMONITOR
        mi = MONITORINFOEXW()
        mi.cbSize = ct.sizeof(MONITORINFOEXW)
        monitor = u.MonitorFromWindow(wt.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor or not u.GetMonitorInfoW(monitor, ct.byref(mi)):
            return {"monitor": None, "advanced_color": None}
        return {"monitor": mi.szDevice, "advanced_color": self._advanced_color(mi.szDevice)}

    def _advanced_color(self, device: str) -> bool | None:
        ct, u = self.ctypes, self.user32
        U32 = ct.c_uint32

        class LUID(ct.Structure):
            _fields_ = [("low", U32), ("high", ct.c_int32)]

        class PATH(ct.Structure):  # DISPLAYCONFIG_PATH_INFO
            _fields_ = [("src_adapter", LUID), ("src_id", U32), ("src_mode", U32), ("src_flags", U32),
                        ("tgt_adapter", LUID), ("tgt_id", U32), ("tgt_mode", U32), ("tech", U32), ("rotation", U32),
                        ("scaling", U32), ("refresh", U32 * 2), ("scanline", U32), ("available", ct.c_int32),
                        ("tgt_flags", U32), ("flags", U32)]

        class HEADER(ct.Structure):  # DISPLAYCONFIG_DEVICE_INFO_HEADER
            _fields_ = [("type", U32), ("size", U32), ("adapter", LUID), ("id", U32)]

        class SOURCE(ct.Structure):  # DISPLAYCONFIG_SOURCE_DEVICE_NAME
            _fields_ = [("header", HEADER), ("gdi", ct.c_wchar * 32)]

        class COLOR(ct.Structure):  # DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO
            _fields_ = [("header", HEADER), ("value", U32), ("encoding", U32), ("bits", U32)]

        paths, modes = U32(), U32()
        if u.GetDisplayConfigBufferSizes(2, ct.byref(paths), ct.byref(modes)):  # QDC_ONLY_ACTIVE_PATHS
            return None
        path_info, mode_info = (PATH * paths.value)(), (ct.c_byte * (64 * modes.value))()  # MODE_INFO is 64 bytes
        if u.QueryDisplayConfig(2, ct.byref(paths), path_info, ct.byref(modes), mode_info, None):
            return None
        for p in path_info[:paths.value]:
            src = SOURCE(HEADER(1, ct.sizeof(SOURCE), p.src_adapter, p.src_id))
            if u.DisplayConfigGetDeviceInfo(ct.byref(src)) or src.gdi != device:
                continue
            color = COLOR(HEADER(9, ct.sizeof(COLOR), p.tgt_adapter, p.tgt_id))
            return None if u.DisplayConfigGetDeviceInfo(ct.byref(color)) else bool(color.value & 0b10)  # enabled
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("info")
    i.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--count", type=int, choices=range(1, 101), metavar="1..100", default=5)
    w = sub.add_parser("watch")
    w.add_argument("--method", choices=[m.lower() for m in METHODS], required=True)
    w.add_argument("--out", type=Path, required=True)
    w.add_argument("--every", type=float, default=EVERY)
    w.add_argument("--max-shots", type=int, default=MAX_SHOTS)
    w.add_argument("--max-minutes", type=float, default=MAX_MINUTES)
    m = sub.add_parser("mask")
    m.add_argument("src", type=Path)
    m.add_argument("dest", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "mask":
        return mask(a.src, a.dest)
    if (why := lane_trouble()) is not None:
        print(f"refused: {why}")
        return 1
    windows = Win32Desk()
    try:
        if a.cmd == "info":
            print(json.dumps(info(windows, a.out), indent=1))
        elif a.cmd == "compare":
            compare(windows, a.out, count=a.count)
        else:
            method = next(n for n in METHODS if n.lower() == a.method)
            watch(windows, a.out, method, every=a.every, max_shots=a.max_shots, max_seconds=a.max_minutes * 60)
    except Stop as stop:
        print(f"stop: {stop}")
        return 1
    except KeyboardInterrupt:
        print("stopped by the user")
    return 0


if __name__ == "__main__":
    sys.exit(main())
