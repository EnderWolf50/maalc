"""First-come-first-served queue for a resource one task may use at a time.

  python tools/live/queue.py run --resource <bench|emulator> --name <task> -- <command...>
  python tools/live/queue.py status [--resource <bench|emulator>]

`bench` is a timing or memory measurement, `emulator` is the user's game account on the
emulator (see the maalc-live-test skill). A run takes one ticket, waits until it is first,
runs the command and leaves the queue, so a chain of runs interleaves with other tasks' runs.
The tickets of dead processes are dropped. State: `<main checkout>/.local/queue/<resource>/`.
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parents[1])  # this file's name shadows the stdlib `queue`

from local_dir import local_dir, main_checkout

RESOURCES = ("bench", "emulator")


def alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        return True
    k = ctypes.windll.kernel32  # os.kill(pid, 0) would terminate the process on Windows
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def tickets(qdir: Path, is_alive=alive) -> list[Path]:
    """The live tickets in arrival order; tickets of dead processes are deleted."""
    out = []
    for p in sorted(qdir.glob("*.ticket")):
        if is_alive(int(p.stem.split("-", 2)[1])):
            out.append(p)
        else:
            p.unlink(missing_ok=True)
    return out


def run(qdir: Path, name: str, cmd: list[str], is_alive=alive, poll: float = 5.0) -> int:
    qdir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.]", "_", name)
    me = qdir / f"{time.time_ns()}-{os.getpid()}-{name}.ticket"
    me.write_text(" ".join(cmd), encoding="utf-8")
    try:
        said = False
        while (q := tickets(qdir, is_alive))[:1] != [me]:
            if not said:
                print(f"[queue] waiting, {q.index(me) if me in q else '?'} ahead", flush=True)
                said = True
            time.sleep(poll)
        print(f"[queue] start {name}", flush=True)
        return subprocess.call(cmd)
    finally:
        me.unlink(missing_ok=True)


def status(qdir: Path, is_alive=alive) -> list[str]:
    lines = []
    for i, p in enumerate(tickets(qdir, is_alive) if qdir.exists() else []):
        _, pid, name = p.stem.split("-", 2)
        lines.append(("RUNNING " if i == 0 else f"#{i:<6} ") + f"{name} (pid {pid}): {p.read_text(encoding='utf-8')[:120]}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--resource", choices=RESOURCES, required=True)
    r.add_argument("--name", required=True)
    r.add_argument("command", nargs=argparse.REMAINDER)
    s = sub.add_parser("status")
    s.add_argument("--resource", choices=RESOURCES)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        for res in [a.resource] if a.resource else RESOURCES:
            print(f"{res}:", *(status(main_checkout() / ".local" / "queue" / res) or ["free"]), sep="\n  ")
        return 0
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command after --")
    return run(local_dir("queue", a.resource), a.name, cmd)


if __name__ == "__main__":
    sys.exit(main())
