"""Launch the built settings GUI in a throwaway root and print its window, for the `maalc-gui-check` skill.

    uv run python tools/gui_probe.py --exe gui/src-tauri/target/release/maalc-gui.exe --root <dir> [--settings FILE] [--title maalc] [--timeout 30]

The GUI reads and writes `<folder of its exe>/config/settings.json` (gui/src-tauri/src/lib.rs `root`), so the
probe copies the exe into `--root`, writes the demo settings there (the `valid` case of tests/settings_cases.json
unless `--settings` names a file) and links `assets/` beside it, which `load_theme_packs` looks for. The real
`install/` is never touched. The app stays running: stop it by the pid printed.

Prints one JSON line `{"pid", "hwnd", "title", "rect": [left, top, right, bottom], "width", "height", "root"}` when the
window shows. Exits 1 and kills the process when no window of the exe with that title shows within `--timeout`.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXE_NAME = "maalc-gui.exe"


def link_dir(link: Path, target: Path):
    """A directory link that needs no privilege: a junction on Windows, a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def unlink_dir(link: Path):
    """Remove a directory link made by `link_dir` without touching its target; nothing when it is absent."""
    try:
        os.rmdir(link)  # a junction, or a symlink to a directory on Windows
    except OSError:
        try:
            os.unlink(link)  # a symlink on POSIX
        except OSError:
            pass


def demo_settings() -> str:
    cases = json.loads((REPO / "tests" / "settings_cases.json").read_text(encoding="utf-8"))
    return json.dumps(cases["valid"], ensure_ascii=False, indent=2)


def prepare_root(exe: Path, root: Path, settings_text: str, assets: Path = REPO / "assets") -> Path:
    """`root` holding a copy of `exe`, config/settings.json and a link to `assets`; an existing root is replaced. Returns the copied exe."""
    unlink_dir(root / "assets")  # the link goes first: rmtree must never follow it into the repo
    if root.exists():
        shutil.rmtree(root)
    (root / "config").mkdir(parents=True)
    copied = root / EXE_NAME
    shutil.copy2(exe, copied)
    (root / "config" / "settings.json").write_text(settings_text, encoding="utf-8")
    link_dir(root / "assets", assets)
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
    ap.add_argument("--root", type=Path, required=True, help="throwaway folder the exe is copied into (replaced if it exists)")
    ap.add_argument("--settings", type=Path, help="settings.json to start with (default: the `valid` case of tests/settings_cases.json)")
    ap.add_argument("--title", default="maalc")
    ap.add_argument("--timeout", type=float, default=30)
    args = ap.parse_args(argv)

    text = args.settings.read_text(encoding="utf-8") if args.settings else demo_settings()
    exe = prepare_root(args.exe, args.root, text)
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
