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
The tickets of dead processes are dropped. A `run` leaves `<name>.result` (exit code, `--log`) when its command ends,
and hands the command its ticket's path in MAALC_QUEUE_TICKET: a `backup.py hold` keeps its state beside it (hold.py).
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
What `status`, `pause` and `resume` know of a hold is hold.py's.
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:  # run as a script, local_dir is not importable until tools/ is on the path
    sys.path.insert(0, str(TOOLS))
# This file's name shadows the stdlib `queue` for a script in tools/live/, whose folder stays on its path: no module
# such a script imports may import the stdlib `queue` (none does; tests/test_live_queue.py runs the three as scripts).

from local_dir import local_dir, main_checkout  # noqa: E402

RESOURCES = ("bench", "emulator")
TICKET_ENV = "MAALC_QUEUE_TICKET"  # the ticket path a `run` hands its command (hold.py keeps its state beside it)


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


class Ticket(NamedTuple):
    """The parts of a ticket's file name, `<stamp>-<pid>-<name>.ticket`: the stamp (ns) sorts the queue, the pid is
    the process that holds the ticket, the name is the task's (ticket_name())."""
    stamp: str
    pid: str
    name: str

    @classmethod
    def of(cls, p: Path) -> "Ticket":
        return cls(*p.stem.split("-", 2))

    def path(self, qdir: Path) -> Path:
        return qdir / f"{self.stamp}-{self.pid}-{self.name}.ticket"


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
        if is_alive(int(Ticket.of(p).pid), t[1]):
            out.append(p)
        else:
            p.unlink(missing_ok=True)
    return out


def ticket_name(name: str) -> str:
    return re.sub(r"[^\w.]", "_", name)


def result_path(qdir: Path, name: str) -> Path:
    return qdir / f"{ticket_name(name)}.result"


FIRST_GAP = 1_000_000  # ns: room for the first tickets placed behind a ticket before the next plain one


def place(qdir: Path, name: str, cmd: list[str], first: bool, is_alive=alive) -> Path:
    """Write this process's ticket and return it: in arrival order, or with first (#465) just behind the ticket that
    holds the resource and the --first ones already waiting behind it. A first ticket is written again when the holder
    left meanwhile: the run that took over may have started, and a ticket ahead of it would start a second command."""
    body = json.dumps({"cmd": " ".join(cmd), "start": started(os.getpid()), "first": first})
    taken = 0  # first tickets: stamps behind the holder already taken by a ticket of this process and name
    while True:
        q = tickets(qdir, is_alive) if first else []
        # After every ticket already there: Python 3.12's wall clock on Windows ticks every 15.6 ms, and a ticket of the
        # same tick, pid and name would overwrite the one before it (#636); a clock stepped back would sort it ahead.
        # FIRST_GAP behind the last one, so the stamps a first ticket takes right behind a ticket stay free.
        stamps = [int(s) for p in qdir.glob("*.ticket") if (s := Ticket.of(p).stamp).isdigit()]
        stamp = str(max([time.time_ns(), *(s + FIRST_GAP for s in stamps)]))
        if q:
            behind = next((i for i, p in enumerate(q[1:], 1) if (t := read(p)) is not None and not t[2]), len(q)) - 1
            last = Ticket.of(q[behind]).stamp
            stamp = str(int(last) + 1 + taken).zfill(len(last))  # same width: ticket names sort as text
        me = Ticket(stamp, str(os.getpid()), name).path(qdir)
        try:
            with me.open("x", encoding="utf-8") as f:  # a thread of this process may have taken the stamp meanwhile
                f.write(body)
        except FileExistsError:
            taken += 1
            continue
        if not q or q[0].exists():  # the holder is still there: no ticket behind it has started
            return me
        me.unlink(missing_ok=True)


class TicketGone(SystemExit):
    """The ticket of a waiting turn() was removed (#582). Uncaught, it ends the process with exit 1 and its message."""


@contextmanager
def turn(qdir: Path, name: str, cmd: list[str], first: bool = False, is_alive=alive, poll: float = 5.0,
         sleep=time.sleep, on_wait=lambda ahead: None):
    """Hold this process's ticket in `qdir` from when it is first until the block ends; the block gets its path. When
    it has to wait, `on_wait` is called once with (pid, command) of each ticket ahead of it that is still there; when
    none is, it waits a poll and looks again. When its own ticket is removed while it waits, it raises TicketGone and
    the block does not run."""
    qdir.mkdir(parents=True, exist_ok=True)
    me = place(qdir, ticket_name(name), cmd, first, is_alive)
    try:
        said = False
        while (q := tickets(qdir, is_alive))[:1] != [me]:
            if me not in q:
                raise TicketGone(f"[queue] the ticket {me.name} left the queue while {name} waited (removed, or dropped "
                                 f"as a dead process's); {name} did not start: queue it again")
            if not said:
                ahead = [(Ticket.of(p).pid, t[0]) for p in q[:q.index(me)] if (t := read(p)) is not None]
                if ahead:
                    on_wait(ahead)
                    said = True
            sleep(poll)
        yield me
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
                  on_wait=lambda ahead: print(f"[queue] waiting, {len(ahead)} ahead", flush=True)) as me:
            print(f"[queue] start {name}", flush=True)
            # inside the turn: `wait` sees the result before the ticket goes
            return write_result(subprocess.call(cmd, env={**os.environ, TICKET_ENV: str(me)}))
    except TicketGone as gone:
        print(gone, flush=True)
        return write_result(1, str(gone))


WAIT_TIMEOUT, WAIT_UNKNOWN, WAIT_DIED = 75, 2, 3


WAIT_GRACE = 10  # seconds a `run` started just before `wait` has to queue (uv starts first); until then the result is the last run's


def wait(qdir: Path, name: str, timeout_s: float, is_alive=alive, poll: float = 5.0, say=print,
         clock=time.monotonic, sleep=time.sleep, grace: float = WAIT_GRACE) -> int:
    """Block until the ticket `name` (queued or running) has ended; its exit code, or WAIT_TIMEOUT after timeout_s."""
    name, deadline, seen = ticket_name(name), clock() + timeout_s, False
    queued = lambda: [p for p in tickets(qdir, is_alive) if Ticket.of(p).name == name] if qdir.exists() else []
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


FIRST_NOTE = " — FIRST: the daily task, due before the 05:00 reset; the holder ends its hold before its next bot run"


@dataclass(frozen=True)
class Holder:
    """A live ticket of a queue, as `status` lists it: the first one holds the resource, the others wait in order."""
    name: str
    pid: str
    cmd: str
    first: bool  # queued with --first
    stranded_min: int | None  # see hold.stranded()
    hold_note: str = ""  # see hold.note()


def holders(qdir: Path, is_alive=alive, now: float | None = None) -> list[Holder]:
    """The live tickets of `qdir` in turn order (none for a queue never used): what `status` prints, for the tools
    that act on it (watchdog.py, ship.py, after_land.py), so none of them parses its text. A ticket that runs a hold
    adds what the hold publishes (hold.py)."""
    from live import hold  # here, not at the top: hold imports this module

    out = []
    for p in tickets(qdir, is_alive) if qdir.exists() else []:
        if (t := read(p)) is not None:
            cmd, _, first = t
            ticket, state = Ticket.of(p), hold.read_state(p)
            out.append(Holder(ticket.name, ticket.pid, cmd, first, hold.stranded(state, is_alive, now), hold.note(state, now)))
    return out


def status(qdir: Path, is_alive=alive, now: float | None = None) -> list[str]:
    lines = []
    for i, h in enumerate(holders(qdir, is_alive, now)):
        note = h.hold_note if i == 0 else FIRST_NOTE if h.first else ""
        why = "" if h.stranded_min is None else f" — bot ended {h.stranded_min} min ago, waiting for the agent"
        lines.append(("RUNNING " if i == 0 else f"#{i:<6} ") + f"{h.name} (pid {h.pid}){why}{note}: {h.cmd[:120]}")
    return lines


def queue_dir(resource: str, root: Path | None = None) -> Path:
    """The folder of a resource's tickets in the main checkout (or `root`), created by the first `run`."""
    return (root or main_checkout()) / ".local" / "queue" / resource


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
    if a.cmd in ("resume", "pause"):
        from live import hold  # as in holders()

        # not local_dir(): it would create the folder of a mistyped task
        task = main_checkout() / ".local" / "scratch" / a.task
        if a.cmd == "resume":
            print("\n".join(hold.resume(task)))
        else:
            print(hold.pause(task, None if a.end else a.minutes))
        return 0
    if a.cmd == "wait":
        return wait(queue_dir(a.resource), a.name, a.timeout_s)
    if a.cmd == "status" and a.log:
        running, text = detached_status(a.log)
        print(text)
        return 0 if running else 1
    if a.cmd == "status":
        for res in [a.resource] if a.resource else RESOURCES:
            print(f"{res}:", *(status(queue_dir(res)) or ["free"]), sep="\n  ")
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
