"""The hold of a live test (`backup.py hold`): what it publishes about itself and what the other live tools read of it.

A hold queued with `queue.py run` gets that run's ticket in its environment (queue.TICKET_ENV) and keeps its state
beside it, in `<ticket stem>.hold.json`: the done file that ends the hold, the bot logs it guards (`--guard`, one path
or a glob) and the wall time it times out at (null until its wait starts and once the wait is over). The file goes when
the hold ends. `queue.py status` reads it for every ticket (holders()): a hold whose bot ended over STRANDED seconds ago
with no done file is stranded, which watchdog.py reports, and the holder's note says it is paused or near its timeout.

The task folder, the done file's, holds the rest: the `pause` file that `queue.py pause` writes and the hold reads, and
the hold.log, bot.log and done that `queue.py resume` reads, the hold's `[hold] bot ended <time>` line (bot_ended()) among
them.
"""
import glob
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from live.queue import TICKET_ENV, alive, detached_doc, detached_running, detached_status

STRANDED = 600  # seconds a holder may sit after its bot ended before `status` calls it stranded
EXPIRY_WARN = 1800  # seconds before a hold's timeout from which `status` says it will expire


@dataclass(frozen=True)
class State:
    """What a running hold publishes: the done file that ends it, the bot logs it guards, when it times out."""
    done: Path
    guard: Path | None = None
    deadline: int | None = None  # epoch seconds, whole: status shows minutes, and they carry no float noise (#578)


def state_path(ticket: Path) -> Path:
    """The state file of the hold that runs under this ticket."""
    return ticket.with_name(ticket.stem + ".hold.json")


def own_state_path() -> Path | None:
    """This process's state file: beside the ticket of the `queue.py run` that started it; None outside a queue."""
    ticket = os.environ.get(TICKET_ENV)
    return state_path(Path(ticket)) if ticket else None


def publish(path: Path | None, state: State) -> None:
    """Write the hold's state where readers look for it (nothing outside a queue), whole: a reader never sees half of
    it. The state is a courtesy to the readers, so a write that fails (a hand-cleared queue folder; on Windows, a reader
    that has the file open as it is replaced) is skipped, and the next one, 30 s on, tries again; the hold goes on."""
    if not path:
        return
    doc = {"done": str(state.done), "guard": state.guard and str(state.guard), "deadline": state.deadline}
    try:
        part(path).write_text(json.dumps(doc), encoding="utf-8")
        os.replace(part(path), path)
    except OSError:
        pass


def withdraw(path: Path | None) -> None:
    """Remove the state when the hold ends; one a reader holds open stays, read by nobody once the ticket is gone."""
    if not path:
        return
    for p in (path, part(path)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def part(path: Path) -> Path:
    """Where publish writes the state before it replaces the file with it."""
    return path.with_name(path.name + ".part")


def read_state(ticket: Path) -> State | None:
    """The state of the hold under this ticket; None when the ticket runs no hold."""
    try:
        doc = json.loads(state_path(ticket).read_text(encoding="utf-8"))
        return State(Path(doc["done"]), doc["guard"] and Path(doc["guard"]), doc["deadline"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def guard_logs(guard: Path) -> list[Path]:
    """The logs a `hold --guard` names: one path, or a glob of them (`bot*.log`: every bot run started during one hold,
    a second one under its own log included, live-1 T-live)."""
    s = str(guard)
    return [Path(p) for p in sorted(glob.glob(s))] if any(c in s for c in "*?[") else [guard]


def stranded(state: State | None, is_alive=alive, now: float | None = None) -> int | None:
    """Minutes since the guard bot of a hold that waits for an agent that is not there ended (no done file exists),
    when that is over STRANDED seconds; None otherwise."""
    logs = [p for p in guard_logs(state.guard) if p.exists() and detached_doc(p)] if state and state.guard else []
    if not logs or state.done.exists() or any(detached_running(p, is_alive) for p in logs):
        return None
    secs = (now or time.time()) - max(p.stat().st_mtime for p in logs)  # the last bot's last write is when it ended
    return round(secs / 60) if secs > STRANDED else None


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


def note(state: State | None, now: float | None = None) -> str:
    """What a second agent must know about a hold: paused (do not touch), or about to time out."""
    if not state:
        return ""
    now = now or time.time()
    if (until := pause_until(state.done.parent)) and until > now:
        return f" — PAUSED until {time.strftime('%H:%M', time.localtime(until))}, its agent still owns the emulator"
    if state.deadline is None:
        return ""
    left = state.deadline - now
    return f" — hold expires in {max(left, 0) / 60:.0f} min unless its bot runs or it is paused" if left < EXPIRY_WARN else ""


BOT_ENDED = re.compile(r"\[hold\] bot ended (\S+)")
OUTCOME = re.compile(r"forfeit|victory|claimed|not passed|gave up|stop: \d+ of|Traceback|Error|failed", re.I)


def bot_ended(when: datetime) -> str:
    """The hold.log line that says the guarded bot ended (resume reads it: nobody may have been watching)."""
    return f"[hold] bot ended {when.isoformat(timespec='seconds')}"


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
