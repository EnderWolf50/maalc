"""Launch the built settings GUI in a throwaway root and print its window, for the `maalc-gui-check` skill.

    uv run python tools/gui_probe.py --exe gui/src-tauri/target/release/maalc-gui.exe --root <dir> [--settings FILE] [--title maalc] [--timeout 30]
    uv run python tools/gui_probe.py --exe ... --root <dir> [--settings FILE] --prepare-only

The GUI reads and writes `<folder of its exe>/config/settings.json` (gui/src-tauri/src/lib.rs `root`), so the
probe copies the exe into `--root`, writes the demo settings there (the `valid` case of tests/settings_cases.json
unless `--settings` names a file) and links `assets/` beside it, which `load_theme_packs` looks for. The real
`install/` is never touched. The app stays running: stop it by the pid printed.

Prints one JSON line `{"pid", "hwnd", "title", "rect": [left, top, right, bottom], "width", "height", "root"}` when the
window shows. Exits 1 and kills the process when no window of the exe with that title shows within `--timeout`, and exits 1 before
starting anything when `--root` exists without the marker file the probe writes (the folder is not deleted).
`--prepare-only` lays out the root, prints `{"exe", "root"}` and starts nothing: `tools/gui_devtools.mjs open` starts the
copied exe itself, with a DevTools port.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import dir_link

REPO = Path(__file__).resolve().parents[1]
EXE_NAME = "maalc-gui.exe"
MARKER = ".gui-probe-root"  # written when the probe makes a root: only a folder that has it is replaced


class ForeignRoot(Exception):
    """`--root` exists and the probe did not make it."""


def demo_settings() -> str:
    cases = json.loads((REPO / "tests" / "settings_cases.json").read_text(encoding="utf-8"))
    return json.dumps(cases["valid"], ensure_ascii=False, indent=2)


def prepare_root(exe: Path, root: Path, settings_text: str, assets: Path = REPO / "assets") -> Path:
    """`root` holding a copy of `exe`, config/settings.json and a link to `assets`; a root the probe made earlier is replaced. Returns the copied exe.
    Raises `ForeignRoot`, deleting nothing, when `root` exists without the marker file."""
    if root.exists():
        if not (root / MARKER).is_file():
            raise ForeignRoot(f"{root} exists and has no {MARKER} marker: not made by this probe, so not deleted")
        dir_link.unlink(root / "assets")  # the link goes first: rmtree must never follow it into the repo
        shutil.rmtree(root)
    (root / "config").mkdir(parents=True)
    (root / MARKER).write_text("made by tools/gui_probe.py\n", encoding="utf-8")
    copied = root / EXE_NAME
    shutil.copy2(exe, copied)
    (root / "config" / "settings.json").write_text(settings_text, encoding="utf-8")
    dir_link.link(root / "assets", assets)
    return copied


def find_window(pid: int, title: str):
    """(hwnd, title, (left, top, right, bottom)) of the visible top-level window of process `pid` titled `title`, else None. Windows only."""
    import ctypes.wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == title:
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append((hwnd, buf.value, (rect.left, rect.top, rect.right, rect.bottom)))
            return False
        return True

    user32.EnumWindows(visit, 0)
    return found[0] if found else None


def wait_for_window(proc: subprocess.Popen, title: str, timeout: float, poll: float = 0.25):
    """The `find_window` result once it shows; None when the timeout passes or the process ends first."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and proc.poll() is None:
        hit = find_window(proc.pid, title)
        if hit:
            return hit
        time.sleep(poll)
    return None


def stop(proc: subprocess.Popen):
    """The process and its children (WebView2 helpers), by its own pid."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True, help="throwaway folder the exe is copied into (replaced only if the probe made it: it holds a marker file)")
    ap.add_argument("--settings", type=Path, help="settings.json to start with (default: the `valid` case of tests/settings_cases.json)")
    ap.add_argument("--title", default="maalc")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--prepare-only", action="store_true", help="lay out the root, print {exe, root} and start nothing")
    args = ap.parse_args(argv)

    text = args.settings.read_text(encoding="utf-8") if args.settings else demo_settings()
    try:
        exe = prepare_root(args.exe, args.root, text)
    except ForeignRoot as e:
        print(e, file=sys.stderr)
        return 1
    if args.prepare_only:
        print(json.dumps({"exe": str(exe), "root": str(args.root)}))
        return 0
    proc = subprocess.Popen([str(exe)], cwd=args.root)
    hit = wait_for_window(proc, args.title, args.timeout)
    if not hit:
        stop(proc)
        print(f"no window titled {args.title!r} from pid {proc.pid} within {args.timeout:g} s", file=sys.stderr)
        return 1
    hwnd, title, rect = hit
    print(json.dumps({"pid": proc.pid, "hwnd": hwnd, "title": title, "rect": list(rect),
                      "width": rect[2] - rect[0], "height": rect[3] - rect[1], "root": str(args.root)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
