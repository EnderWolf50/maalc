"""First-come-first-served queue for a resource one task may use at a time, except a `run --first` ticket (#465).

  python tools/live/queue.py run --resource <bench|emulator> --name <task> [--log <file>] [--first] -- <command...>
  python tools/live/queue.py wait --resource <bench|emulator> --name <task> [--timeout-s N]
  python tools/live/queue.py pause --task <task> [--minutes N | --end]
  python tools/live/queue.py status [--resource <bench|emulator>]
  python tools/live/queue.py detach --log <file> -- <command...>
  python tools/live/queue.py status --log <file>
  python tools/live/queue.py resume --task <task>

`bench` is a timing or memory measurement, `emulator` is the user's game account on the
emulator (see the maalc-live-test skill). A run takes one ticket, waits until it is first,
runs the command and leaves the queue, so a chain of runs interleaves with other tasks' runs.
The tickets of dead processes are dropped. A `run` leaves `<name>.result` (exit code, `--log`) when its command ends.
A run whose ticket is removed while it waits (a cleared queue folder) does not start its command: it says so, leaves
exit 1 as its result, and has to be queued again.
`run --first` is for the daily task, which a 05:00 game reset ends (#465): its ticket goes right behind the one that
holds the resource, ahead of every waiting one, and `status` marks it FIRST. The holder's run is not cut short; a
live-test hold that spans several bot runs ends before its next one (the maalc-live-test skill). With no holder it
starts at once.
`wait` blocks in the foreground until that ticket's command ends, prints its exit code and log path and exits with that
code; at its own `--timeout-s` (default 540, inside a 10-minute tool limit) it prints "still running, run wait again" and
exits 75 (so can a command that exits 75: read the line). Exit 2: no such ticket or result. Exit 3: the run died without
a result. A delegated turn ends only after `wait` printed an exit code. State: `<main checkout>/.local/queue/<resource>/`.

`detach` starts a command (a `run`, or the bot) in a process the caller does not own and returns at once,
so it outlives an agent harness that kills its background commands after a time limit; `status --log`
says whether it still runs (exit 0) or ended (exit 1, with the last line of its output).
`pause --task <task>` marks the task's hold as paused for N minutes (default 120; `--end` lifts it): `backup.py hold` does
not time out meanwhile and `status` shows the holder as PAUSED, so a bot killed at a pause does not free the emulator.
`resume --task <task>` prints a live-test task's checklist from `.local/scratch/<task>/` (hold, bot, done, next step).
"""
import argparse
import ctypes
import glob
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
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


def read(p: Path) -> tuple[str, int | None, bool] | None:
    """(command, start time of the holder, queued with --first) of a ticket; a ticket without a start time is plain
    text. None: the ticket is gone, its run ended after the queue was listed (#577)."""
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        doc = json.loads(text)
        return doc["cmd"], doc.get("start"), doc.get("first") is True
    except (ValueError, KeyError, TypeError, AttributeError):
        return text, None, False


def tickets(qdir: Path, is_alive=alive) -> list[Path]:
    """The live tickets in arrival order; tickets of dead processes are deleted."""
    out = []
    for p in sorted(qdir.glob("*.ticket")):
        if (t := read(p)) is None:
            continue
        if is_alive(int(p.stem.split("-", 2)[1]), t[1]):
            out.append(p)
        else:
            p.unlink(missing_ok=True)
    return out


def ticket_name(name: str) -> str:
    return re.sub(r"[^\w.]", "_", name)


def result_path(qdir: Path, name: str) -> Path:
    return qdir / f"{ticket_name(name)}.result"


def place(qdir: Path, name: str, cmd: list[str], first: bool, is_alive=alive) -> Path:
    """Write this process's ticket and return it: in arrival order, or with first (#465) just behind the ticket that
    holds the resource and the --first ones already waiting behind it. A first ticket is written again when the holder
    left meanwhile: the run that took over may have started, and a ticket ahead of it would start a second command."""
    body = json.dumps({"cmd": " ".join(cmd), "start": started(os.getpid()), "first": first})
    while True:
        q = tickets(qdir, is_alive) if first else []
        # After every ticket already there, also when the wall clock stepped back since one was written (#636: on a
        # Windows CI runner a ticket placed milliseconds later sorted ahead).
        stamps = [int(s) for p in qdir.glob("*.ticket") if (s := p.name.split("-", 1)[0]).isdigit()]
        stamp = str(max([time.time_ns(), *(s + 1 for s in stamps)]))
        if q:
            behind = next((i for i, p in enumerate(q[1:], 1) if (t := read(p)) is not None and not t[2]), len(q)) - 1
            last = q[behind].name.split("-", 1)[0]
            stamp = str(int(last) + 1).zfill(len(last))  # same width: ticket names sort as text
        me = qdir / f"{stamp}-{os.getpid()}-{name}.ticket"
        me.write_text(body, encoding="utf-8")
        if not q or q[0].exists():  # the holder is still there: no ticket behind it has started
            return me
        me.unlink(missing_ok=True)


class TicketGone(SystemExit):
    """The ticket of a waiting turn() was removed (#582). Uncaught, it ends the process with exit 1 and its message."""


@contextmanager
def turn(qdir: Path, name: str, cmd: list[str], first: bool = False, is_alive=alive, poll: float = 5.0,
         sleep=time.sleep, on_wait=lambda ahead: None):
    """Hold this process's ticket in `qdir` from when it is first until the block ends. When it has to wait, `on_wait`
    is called once with (pid, command) of each ticket ahead of it that is still there; when none is, it waits a poll
    and looks again. When its own ticket is removed while it waits, it raises TicketGone and the block does not run."""
    qdir.mkdir(parents=True, exist_ok=True)
    me = place(qdir, ticket_name(name), cmd, first, is_alive)
    try:
        said = False
        while (q := tickets(qdir, is_alive))[:1] != [me]:
            if me not in q:
                raise TicketGone(f"[queue] the ticket {me.name} left the queue while {name} waited (removed, or dropped "
                                 f"as a dead process's); {name} did not start: queue it again")
            if not said:
                ahead = [(p.stem.split("-", 2)[1], t[0]) for p in q[:q.index(me)] if (t := read(p)) is not None]
                if ahead:
                    on_wait(ahead)
                    said = True
            sleep(poll)
        yield
    finally:
        me.unlink(missing_ok=True)


def run(qdir: Path, name: str, cmd: list[str], is_alive=alive, poll: float = 5.0, log: str | None = None,
        first: bool = False) -> int:
    name = ticket_name(name)
    result = result_path(qdir, name)
    result.unlink(missing_ok=True)  # a result of an earlier run under this name is not this one's

    def write_result(code: int, not_started: str | None = None) -> int:
        qdir.mkdir(parents=True, exist_ok=True)  # a hand-cleared queue may have taken the folder with the ticket
        doc = {"exit": code, "log": log, "ended": datetime.now().isoformat(timespec="seconds"), "not_started": not_started}
        result.write_text(json.dumps(doc), encoding="utf-8")
        return code

    try:
        with turn(qdir, name, cmd, first, is_alive, poll,
                  on_wait=lambda ahead: print(f"[queue] waiting, {len(ahead)} ahead", flush=True)):
            print(f"[queue] start {name}", flush=True)
            return write_result(subprocess.call(cmd))  # inside the turn: `wait` sees the result before the ticket goes
    except TicketGone as gone:
        print(gone, flush=True)
        return write_result(1, str(gone))


WAIT_TIMEOUT, WAIT_UNKNOWN, WAIT_DIED = 75, 2, 3


WAIT_GRACE = 10  # seconds a `run` started just before `wait` has to queue (uv starts first); until then the result is the last run's


def wait(qdir: Path, name: str, timeout_s: float, is_alive=alive, poll: float = 5.0, say=print,
         clock=time.monotonic, sleep=time.sleep, grace: float = WAIT_GRACE) -> int:
    """Block until the ticket `name` (queued or running) has ended; its exit code, or WAIT_TIMEOUT after timeout_s."""
    name, deadline, seen = ticket_name(name), clock() + timeout_s, False
    queued = lambda: [p for p in tickets(qdir, is_alive) if p.stem.split("-", 2)[2] == name] if qdir.exists() else []
    for _ in range(int(grace // poll) if poll else 0):
        if queued():
            break
        sleep(poll)
    while queued():
        if not seen:
            seen = True
            say(f"[queue] waiting for {name} (up to {timeout_s:.0f} s)")
        if clock() >= deadline:
            say(f"[queue] {name} still running, run wait again")
            return WAIT_TIMEOUT
        sleep(poll)
    result = result_path(qdir, name)
    for _ in range(int(grace // poll) if seen and poll else 0):  # a run whose ticket was removed writes it a poll later
        if result.exists():
            break
        sleep(poll)
    if not result.exists():
        say(f"[queue] {name}: " + ("the run ended without a result (its process died)" if seen else "no such ticket or result"))
        return WAIT_DIED if seen else WAIT_UNKNOWN
    doc = json.loads(result.read_text(encoding="utf-8"))
    if doc.get("not_started"):
        say(f"[queue] {name} did not start, exit code {doc['exit']}: {doc['not_started']}")
        return doc["exit"]
    say(f"[queue] {name} ended with exit code {doc['exit']} at {doc['ended']}; log: {doc['log'] or '(none: pass --log to run)'}")
    return doc["exit"]


STRANDED = 600  # seconds a holder may sit after its bot ended before `status` calls it stranded


def guard_logs(guard: Path) -> list[Path]:
    """The logs a `hold --guard` names: one path, or a glob of them (`bot*.log`: every bot run started during one hold,
    a second one under its own log included, live-1 T-live)."""
    s = str(guard)
    return [Path(p) for p in sorted(glob.glob(s))] if any(c in s for c in "*?[") else [guard]


def hold_path(cmd: str, flag: str) -> Path | None:
    """The `--guard`/`--done` path of a `backup.py hold` command line (relative: to the main checkout)."""
    m = re.search(rf"--{flag}\s+(\S+)", cmd)  # ponytail: a path with spaces is cut at the space
    return m and main_checkout() / m.group(1)


def stranded(cmd: str, is_alive=alive, now: float | None = None) -> str:
    """Why a holder waits for an agent that is not there: its guard bot ended long ago and no `done` file exists."""
    guard, done = hold_path(cmd, "guard"), hold_path(cmd, "done")
    logs = [p for p in guard_logs(guard) if p.exists() and detached_doc(p)] if guard else []
    if not logs or not done or done.exists() or any(detached_running(p, is_alive) for p in logs):
        return ""
    secs = (now or time.time()) - max(p.stat().st_mtime for p in logs)  # the last bot's last write is when it ended
    return f" — bot ended {secs / 60:.0f} min ago, waiting for the agent" if secs > STRANDED else ""


EXPIRY_WARN = 1800  # seconds before a hold's timeout from which `status` says it will expire


def pause_until(task: Path) -> float | None:
    """When the pause of the task folder `task` ends (epoch seconds), None when there is none."""
    try:
        return float((task / "pause").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pause(task: Path, minutes: float | None, now: float | None = None) -> str:
    """Pause the hold of a task for `minutes` (None lifts it): its timeout stops, `status` shows PAUSED."""
    if minutes is None:
        (task / "pause").unlink(missing_ok=True)
        return f"pause of {task.name} ended"
    task.mkdir(parents=True, exist_ok=True)
    until = (now or time.time()) + minutes * 60
    (task / "pause").write_text(str(until), encoding="utf-8")
    return f"{task.name} paused until {time.strftime('%H:%M', time.localtime(until))}; `pause --task {task.name} --end` lifts it"


def hold_note(cmd: str, now: float | None = None) -> str:
    """What a second agent must know about a hold: paused (do not touch), or about to time out."""
    done = hold_path(cmd, "done")
    if not done:
        return ""
    now = now or time.time()
    if (until := pause_until(done.parent)) and until > now:
        return f" — PAUSED until {time.strftime('%H:%M', time.localtime(until))}, its agent still owns the emulator"
    try:
        left = float((done.parent / "hold.deadline").read_text(encoding="utf-8")) - now
    except (OSError, ValueError):
        return ""
    return f" — hold expires in {max(left, 0) / 60:.0f} min unless its bot runs or it is paused" if left < EXPIRY_WARN else ""


FIRST_NOTE = " — FIRST: the daily task, due before the 05:00 reset; the holder ends its hold before its next bot run"


def status(qdir: Path, is_alive=alive, now: float | None = None) -> list[str]:
    lines = []
    listed = [(p, t) for p in (tickets(qdir, is_alive) if qdir.exists() else []) if (t := read(p)) is not None]
    for i, (p, (cmd, _, first)) in enumerate(listed):
        _, pid, name = p.stem.split("-", 2)
        note = hold_note(cmd, now) if i == 0 else FIRST_NOTE if first else ""
        lines.append(("RUNNING " if i == 0 else f"#{i:<6} ") + f"{name} (pid {pid}){stranded(cmd, is_alive, now)}{note}: {cmd[:120]}")
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


OUTCOME = re.compile(r"forfeit|victory|claimed|not passed|gave up|stop: \d+ of|Traceback|Error|failed", re.I)
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
    r.add_argument("--log", help="the file the command's output goes to, for `wait` to print")
    r.add_argument("--first", action="store_true",
                   help="queue right behind the run that holds the resource, ahead of the waiting ones (the daily task)")
    w = sub.add_parser("wait", help="block until a ticket's command ends; exit with its exit code")
    w.add_argument("--resource", choices=RESOURCES, required=True)
    w.add_argument("--name", required=True)
    w.add_argument("--timeout-s", type=float, default=540)
    pa = sub.add_parser("pause", help="keep a hold from timing out while its agent has paused the run")
    pa.add_argument("--task", required=True)
    pa.add_argument("--minutes", type=float, default=120)
    pa.add_argument("--end", action="store_true")
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
    if a.cmd == "pause":
        print(pause(main_checkout() / ".local" / "scratch" / a.task, None if a.end else a.minutes))
        return 0
    if a.cmd == "wait":
        return wait(main_checkout() / ".local" / "queue" / a.resource, a.name, a.timeout_s)
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
    return run(local_dir("queue", a.resource), a.name, cmd, log=a.log, first=a.first)


if __name__ == "__main__":
    sys.exit(main())
