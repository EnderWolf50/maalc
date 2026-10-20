"""First-come-first-served queue for a resource one task may use at a time.

  python tools/live/queue.py run --resource <bench|emulator> --name <task> -- <command...>
  python tools/live/queue.py status [--resource <bench|emulator>]
  python tools/live/queue.py detach --log <file> -- <command...>
  python tools/live/queue.py status --log <file>
  python tools/live/queue.py resume --task <task>

`bench` is a timing or memory measurement, `emulator` is the user's game account on the
emulator (see the maalc-live-test skill). A run takes one ticket, waits until it is first,
runs the command and leaves the queue, so a chain of runs interleaves with other tasks' runs.
The tickets of dead processes are dropped. State: `<main checkout>/.local/queue/<resource>/`.

`detach` starts a command (a `run`, or the bot) in a process the caller does not own and returns at once,
so it outlives an agent harness that kills its background commands after a time limit; `status --log`
says whether it still runs (exit 0) or ended (exit 1, with the last line of its output).
`resume --task <task>` prints a live-test task's checklist from `.local/scratch/<task>/` (hold, bot, done, next step).
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
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


STRANDED = 600  # seconds a holder may sit after its bot ended before `status` calls it stranded


def hold_path(cmd: str, flag: str) -> Path | None:
    """The `--guard`/`--done` path of a `backup.py hold` command line (relative: to the main checkout)."""
    m = re.search(rf"--{flag}\s+(\S+)", cmd)  # ponytail: a path with spaces is cut at the space
    return m and main_checkout() / m.group(1)


def stranded(cmd: str, is_alive=alive, now: float | None = None) -> str:
    """Why a holder waits for an agent that is not there: its guard bot ended long ago and no `done` file exists."""
    guard, done = hold_path(cmd, "guard"), hold_path(cmd, "done")
    if not guard or not done or done.exists() or not guard.exists() or not detached_doc(guard) or detached_running(guard, is_alive):
        return ""
    secs = (now or time.time()) - guard.stat().st_mtime  # the bot's last write is when it ended
    return f" — bot ended {secs / 60:.0f} min ago, waiting for the agent" if secs > STRANDED else ""


def status(qdir: Path, is_alive=alive, now: float | None = None) -> list[str]:
    lines = []
    for i, p in enumerate(tickets(qdir, is_alive) if qdir.exists() else []):
        _, pid, name = p.stem.split("-", 2)
        cmd = read(p)[0]
        lines.append(("RUNNING " if i == 0 else f"#{i:<6} ") + f"{name} (pid {pid}){stranded(cmd, is_alive, now)}: {cmd[:120]}")
    return lines


def pid_file(log: Path) -> Path:
    return log.with_name(log.name + ".pid")


def detach(cmd: list[str], log: Path) -> int:
    """Start `cmd` in a process the caller does not own (own process group, out of the caller's job when the
    job allows it), output appended to `log`; its pid goes to `<log>.pid`. Returns the pid."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        kw = dict(stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # a hidden console its children share
            try:
                p = subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
            except PermissionError:  # the caller's job forbids breakaway; still outlives a tree kill of the caller
                out.write(b"[detach] the caller's job refused breakaway: closing that job still ends this process\n")
                out.flush()
                p = subprocess.Popen(cmd, creationflags=flags, **kw)
        else:
            p = subprocess.Popen(cmd, start_new_session=True, **kw)
    pid_file(log).write_text(json.dumps({"pid": p.pid, "start": started(p.pid), "cmd": " ".join(cmd)}), encoding="utf-8")
    return p.pid


def detached_doc(log: Path) -> dict | None:
    try:
        return json.loads(pid_file(log).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):  # not yet, or `detach` is still writing it
        return None


def detached_running(log: Path, is_alive=alive) -> bool:
    return (doc := detached_doc(log)) is not None and is_alive(doc["pid"], doc["start"])


def detached_status(log: Path, is_alive=alive) -> tuple[bool, str]:
    """(whether the process `detach` started with this log still runs, a line saying so)."""
    if (doc := detached_doc(log)) is None:
        return False, f"nothing was started with --log {log}"
    if is_alive(doc["pid"], doc["start"]):
        return True, f"running pid {doc['pid']}: {doc['cmd'][:120]}"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    return False, f"ended pid {doc['pid']}, last line: {lines[-1] if lines else '(no output)'}"


OUTCOME = re.compile(r"forfeit|victory|claimed|goal not met|gave up|stop: \d+ of|Traceback|Error|failed", re.I)
BOT_ENDED = re.compile(r"\[hold\] bot ended (\S+)")


def resume(task: Path, is_alive=alive, now: float | None = None) -> list[str]:
    """Where a live-test task stands, from `<task>/` (hold.log, bot.log, done): the checklist an agent reads when its
    turn (re)starts, before it re-arms any wait."""
    now = now or time.time()
    hold_log, bot_log, done = task / "hold.log", task / "bot.log", task / "done"
    hold_up, (bot_up, bot_text) = detached_running(hold_log, is_alive), detached_status(bot_log, is_alive)
    out = [f"hold: {detached_status(hold_log, is_alive)[1]}", f"bot: {bot_text}"]
    if detached_doc(bot_log) and not bot_up:
        notes = BOT_ENDED.findall(hold_log.read_text(encoding="utf-8", errors="replace")) if hold_log.exists() else []
        ended = datetime.fromisoformat(notes[-1]).timestamp() if notes else bot_log.stat().st_mtime  # else its last write
        out.append(f"bot ended at {time.strftime('%H:%M:%S', time.localtime(ended))} ({(now - ended) / 60:.0f} min ago); outcome lines:")
        lines = [l for l in bot_log.read_text(encoding="utf-8", errors="replace").splitlines() if OUTCOME.search(l)]
        out += [f"  {l}" for l in lines[-5:]] or ["  (none matched)"]
    out.append(f"done file: {'present' if done.exists() else 'absent'}")
    if not detached_doc(hold_log):
        nxt = f"nothing was started for task '{task.name}': check the --task name, else begin at step 1"
    elif not hold_up:
        nxt = "hold ended: the emulator is released; read its result above, then check install/ and the game settings by hand"
    elif "[queue] start" not in hold_log.read_text(encoding="utf-8", errors="replace"):
        nxt = "step 1: still queued behind another task; keep waiting on hold.log, do not touch the emulator"
    elif not detached_doc(bot_log):
        nxt = "no bot started: finish steps 2-6 (pre-flight, record, start the bot)"
    elif bot_up:
        nxt = "step 6: the bot runs; wait with one Monitor on `status --log` of bot.log"
    elif not done.exists():
        nxt = "bot ended while you were away: step 7 (stop the run tree and the recording), 8 (evidence, verdicts), 9 (restore settings, create `done`); do not re-arm a wait"
    else:
        nxt = "done exists: step 9 is finished; step 10 (report) once hold.log shows `install matches the backup`"
    return out + [f"next: {nxt}"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--resource", choices=RESOURCES, required=True)
    r.add_argument("--name", required=True)
    r.add_argument("command", nargs=argparse.REMAINDER)
    d = sub.add_parser("detach")
    d.add_argument("--log", type=Path, required=True)
    d.add_argument("command", nargs=argparse.REMAINDER)
    s = sub.add_parser("status")
    which = s.add_mutually_exclusive_group()
    which.add_argument("--resource", choices=RESOURCES)
    which.add_argument("--log", type=Path, help="the --log of a detach: is its process still running")
    rs = sub.add_parser("resume", help="where a live-test task stands; run it first whenever your turn (re)starts")
    rs.add_argument("--task", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "resume":
        # not local_dir(): it would create the folder of a mistyped task
        print("\n".join(resume(main_checkout() / ".local" / "scratch" / a.task)))
        return 0
    if a.cmd == "status" and a.log:
        running, text = detached_status(a.log)
        print(text)
        return 0 if running else 1
    if a.cmd == "status":
        for res in [a.resource] if a.resource else RESOURCES:
            print(f"{res}:", *(status(main_checkout() / ".local" / "queue" / res) or ["free"]), sep="\n  ")
        return 0
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command after --")
    if a.cmd == "detach":
        print(f"pid {detach(cmd, a.log)}, output in {a.log}", flush=True)
        return 0
    return run(local_dir("queue", a.resource), a.name, cmd)


if __name__ == "__main__":
    sys.exit(main())
