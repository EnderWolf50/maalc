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
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parents[1])  # this file's name shadows the stdlib `queue`

from local_dir import local_dir, main_checkout

RESOURCES = ("bench", "emulator")


ACCESS_DENIED = 5


def kernel32():  # os.kill(pid, 0) would terminate the process on Windows, so ask the Win32 API
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.GetProcessTimes.argtypes = [ctypes.c_void_p] * 5
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


def win_alive(k, pid: int, start: int | None, last_error=lambda: ctypes.get_last_error()) -> bool:
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return last_error() == ACCESS_DENIED  # a process of another user exists; only a missing pid is dead
    code, times = ctypes.c_ulong(), [ctypes.c_ulonglong() for _ in range(4)]
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.GetProcessTimes(h, *map(ctypes.byref, times))
    k.CloseHandle(h)
    return code.value == 259 and start in (None, times[0].value)  # STILL_ACTIVE, and not a later process with a reused pid


def started(pid: int) -> int | None:
    """When the process started, in the platform's own unit (None when unknown): tells a pid's owner from a reuse of it."""
    if sys.platform == "win32":
        k = kernel32()
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return None
        times = [ctypes.c_ulonglong() for _ in range(4)]
        k.GetProcessTimes(h, *map(ctypes.byref, times))
        k.CloseHandle(h)
        return times[0].value
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[19])  # starttime, in clock ticks since boot
    except (OSError, ValueError, IndexError):
        return None


def alive(pid: int, start: int | None = None) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return start in (None, started(pid))
    return win_alive(kernel32(), pid, start)


def read(p: Path) -> tuple[str, int | None]:
    """(command, start time of the holder) of a ticket; a ticket without a start time is plain text."""
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc["cmd"], doc.get("start")
    except (ValueError, KeyError, TypeError):
        return p.read_text(encoding="utf-8"), None


def tickets(qdir: Path, is_alive=alive) -> list[Path]:
    """The live tickets in arrival order; tickets of dead processes are deleted."""
    out = []
    for p in sorted(qdir.glob("*.ticket")):
        if is_alive(int(p.stem.split("-", 2)[1]), read(p)[1]):
            out.append(p)
        else:
            p.unlink(missing_ok=True)
    return out


def run(qdir: Path, name: str, cmd: list[str], is_alive=alive, poll: float = 5.0) -> int:
    qdir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.]", "_", name)
    me = qdir / f"{time.time_ns()}-{os.getpid()}-{name}.ticket"
    me.write_text(json.dumps({"cmd": " ".join(cmd), "start": started(os.getpid())}), encoding="utf-8")
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
        lines.append(("RUNNING " if i == 0 else f"#{i:<6} ") + f"{name} (pid {pid}): {read(p)[0][:120]}")
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
