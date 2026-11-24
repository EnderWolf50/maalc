"""A live run that holds the emulator gives way to the daily task, or takes a deliberate break, at a safe point (#853).

    uv run --group probe python tools/live/give_way.py watch --task T --install DIR (--next T2 [--recording PROFILE] [--timeout S] | --now)
        [--port 16384] [--out DIR] [--bot-log FILE] [--run-log FILE]
    uv run --group probe python tools/live/give_way.py look [--glance] [--json] IMAGE...

Start `watch` detached beside the bot (`queue.py detach --log <local>/scratch/T/give-way.log -- ...`; a name the hold's
`--guard` glob of bot logs does not match). Its files default to the task's folder: bot.log, run.log, done and, for the
screenshots, give-way/.

**watch** waits until a `--first` ticket (the daily task, queue.py) stands behind T's, then for a safe point, and leaves:

  1. Safe point: the map (MirrorMap) or a node's panel on it (MapNodePanel) shows, and the run log has no forfeit under way
     (only the bot's memory holds it: a new bot would play on). It suspends the bot's processes but an adb server, waits
     SETTLE s for a tap already sent, and reads the whole screen: a window over the map (the floor 5 prompt, a gift, ...)
     is not safe. When it is not, it resumes the bot and looks again.
  2. It pauses the hold of T (queue.py pause), ends the bot's processes, lifts a finger a cut swipe may have left down,
     closes a node panel with the Back key and goes to the main window with the pipeline's RecoverL2 (Dungeon Progress,
     To Window, Pause Exploration Confirm): the run stays in progress, and the daily's pre-flight reads `ok` there.
  3. It queues the next leg T2 with `--first`, so it stands right behind the daily and ahead of the tasks that wait: one of
     them would find the run in progress and stop at its pre-flight. Then it stops the recording PROFILE and creates T's
     done file: `hold` verifies install/ and the daily starts.

The next leg is the caller's: the maalc-live-test skill's steps under T2, on the same install with no new `prep`; the bot
picks the run up with Resume, and `preflight.py plan --resumed` checks that it did.
`--now` needs no daily: it leaves at the first safe point the same way, and the hold stays (its pause lifted): start the
bot again under bot-b.log. It is the check that Resume picks the run up when no daily came.

Exit 0: left, the last line says what comes next. Exit 1: a step failed after the bot was told to end: the hold stays
paused for PAUSE minutes, the emulator is the caller's, look at the screenshots. Exit 2: it cannot start (T does not hold
the emulator, no bot runs, T2 was used before). Exit 3: the bot ended by itself before a safe point: the skill's steps 7
and 9 let the daily in.

**look** names the screen of each image as step 1 reads it (--glance: as the wait for it does, the map and the panel alone):
the tests' seam.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
if str(TOOLS) not in sys.path:  # run as a script, `live` is not importable until tools/ is on the path
    sys.path.insert(0, str(TOOLS))

from live import giveup, hold, queue, screen_probe  # noqa: E402
from local_dir import main_checkout  # noqa: E402

# The probe's order: what can stand over the map comes before it, as the map's icons read through it.
OVER_MAP = ("ParallelModePrompt", "ExtremeModePrompt", "HiddenBattle", "PopupButton", "HelpPager", "GiftGet", "ForfeitDialog",
            "ProgressPanel", "LevelWarning")
SAFE = ("MapNodePanel", "MirrorMap")  # the panel first: the map's icons read beside it
HOME = "HomeReached"
SCREENS = (*OVER_MAP, *SAFE, HOME)
PROBE = "GiveWayProbe"
LOOK_MS = 1500  # how long one look at the whole screen tries before it names none
GLANCE_MS = 0  # one pass over the two map templates: what the wait for a safe point costs the running bot

DUE_POLL = 15.0  # s between two looks at the queue
GLANCE_POLL = 0.3  # s between two glances: a map whose next node is planned takes its tap soon after it stands still
SETTLE = 3.0  # s a suspended bot's last tap has to change the screen (a node panel shows within about 0.5 s, #130)
PAUSE = 120  # min the hold stays paused when a step fails
MAP_LIMIT, HOME_LIMIT = 20.0, 90.0  # s the panel has to close, and To Window to reach the main window
MAP_POLL = 2.0  # s a Back key has to close the panel before the next look (giveup.STEPS waits the same)
QUEUED_LIMIT = 60.0  # s the next leg's ticket has to show (its process starts first)
FORFEITS = ("forfeit the run", "used: forfeit")  # battle_actions' lines as it sets RUN["forfeit"]: the map then forfeits
FORFEITED = "[maalc] forfeited the run"  # map_actions.forfeit
BOT_START = "[run] child pid"  # bot.py run starts a log's next run


class Failed(Exception):
    """A step failed after the bot was told to end: exit 1, its message says which."""


def forfeit_pending(run_log: Path) -> bool:
    """Whether the bot is on its way to forfeit the run: only its memory holds that, so a new bot would play on."""
    pending = False
    for line in run_log.read_text(encoding="utf-8", errors="replace").splitlines() if run_log.exists() else []:
        if FORFEITED in line or BOT_START in line:
            pending = False
        elif line.endswith(FORFEITS):
            pending = True
    return pending


def daily_waits(q: list[queue.Holder], task: str) -> bool | None:
    """Whether a --first ticket waits behind task's hold; None when task does not hold the resource."""
    if not q or q[0].name != queue.ticket_name(task):
        return None
    return any(h.first for h in q[1:])


def behind_the_daily(q: list[queue.Holder], name: str) -> bool:
    """Whether the ticket `name` waits with --first ones alone between it and the holder."""
    i = next((i for i, h in enumerate(q) if h.name == queue.ticket_name(name)), 0)
    return i > 0 and all(h.first for h in q[1:i + 1])


def next_leg_command(task: str, scratch: Path, timeout: float, recording: str | None) -> list[str]:
    """The hold of the next leg: the maalc-live-test skill's step 1 with --first."""
    folder, live = scratch / task, TOOLS / "live"
    return [sys.executable, str(live / "queue.py"), "run", "--resource", "emulator", "--name", task, "--first", "--",
            sys.executable, str(live / "backup.py"), "hold", "--label", task, "--done", str(folder / "done"),
            "--timeout", f"{timeout:g}", "--guard", str(folder / "bot*.log"),
            *(["--stop-recording", recording] if recording else [])]


@dataclass
class World:
    """What leaving does to the emulator, the bot and the queue; a test gives its own."""
    holders: Callable[[], list[queue.Holder]]
    bot_runs: Callable[[], bool]
    forfeit_pending: Callable[[], bool]
    glance: Callable[[], str | None]  # one of SAFE, or None
    look: Callable[[], str | None]  # one of SCREENS, or None
    suspend: Callable[[], Callable[[], None]]  # suspends the bot; gives back what resumes it
    end_bot: Callable[[], None]
    lift_finger: Callable[[], None]
    back: Callable[[], None]
    to_window: Callable[[], bool]  # RecoverL2: whether it went through
    shot: Callable[[str], None]
    pause: Callable[[float | None], None]  # minutes; None lifts it
    queue_next: Callable[[], None]
    stop_recording: Callable[[], None]
    done: Callable[[], None]
    say: Callable[[str], None] = print
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


def wait_until(w: World, limit: float, good: Callable[[], bool], poll: float = 1.0) -> bool:
    end = w.clock() + limit
    while not good():
        if w.clock() >= end:
            return False
        w.sleep(poll)
    return True


def stop_at_safe_point(w: World) -> bool:
    """End the bot at a safe point; False when it ended by itself before one."""
    while w.bot_runs():
        if w.forfeit_pending() or w.glance() is None:
            w.sleep(GLANCE_POLL)
            continue
        resume, ending = w.suspend(), False
        try:
            w.sleep(SETTLE)
            screen = w.look()
            safe = screen in SAFE and not w.forfeit_pending()
            w.say(f"suspended on {screen}: " + ("safe" if safe else "not safe, the bot goes on"))
            if safe:
                w.shot("safe-point")
                w.pause(PAUSE)  # before the bot ends: the hold's timeout would hand the emulator on
                ending = True
                w.end_bot()
                return True
        finally:
            if not ending:  # what is left of a bot told to end stays suspended: it must not tap
                resume()
        w.sleep(GLANCE_POLL)
    return False


def to_main_window(w: World) -> None:
    """From the map the bot was ended on to the main window; the run stays in progress."""
    w.lift_finger()

    def on_map() -> bool:
        screen = w.look()
        if screen == "MapNodePanel":
            w.back()
        return screen in ("MirrorMap", "ProgressPanel")  # a Back key too many opens Dungeon Progress: RecoverL2 goes on from it

    if not wait_until(w, MAP_LIMIT, on_map, MAP_POLL):
        raise Failed(f"the map did not come back in {MAP_LIMIT:g} s")
    if not w.to_window():
        raise Failed("To Window did not go through (RecoverL2)")
    if not wait_until(w, HOME_LIMIT, lambda: w.look() == HOME):
        raise Failed(f"the main window did not show in {HOME_LIMIT:g} s after To Window")
    w.shot("main-window")


def hand_over(w: World, task: str, next_task: str) -> None:
    """The next leg behind the daily, then the hold ended."""
    w.queue_next()
    if not wait_until(w, QUEUED_LIMIT, lambda: behind_the_daily(w.holders(), next_task)):
        raise Failed(f"the ticket of {next_task} is not behind the daily's after {QUEUED_LIMIT:g} s")
    w.say(f"{next_task} queued behind the daily")
    w.stop_recording()
    w.done()
    w.pause(None)
    w.say(f"{task} gave way; next: wait for `[queue] start {queue.ticket_name(next_task)}` in {next_task}'s hold.log, then "
          "steps 2, 5 and 6 under it on the same install (no prep), with `preflight.py plan --resumed`")


def watch(w: World, task: str, next_task: str | None) -> int:
    """next_task None: a deliberate break (--now), the hold kept."""
    if daily_waits(w.holders(), task) is None or not w.bot_runs():
        w.say(f"stop: {task} does not hold the emulator, or its bot does not run")
        return 2
    while next_task and not daily_waits(w.holders(), task):
        if not w.bot_runs():
            w.say("the bot ended and no daily task waits: nothing to give way to")
            return 3
        w.sleep(DUE_POLL)
    w.say(f"{'the daily task waits' if next_task else 'a deliberate break'}: waiting for a safe point")
    try:
        if not stop_at_safe_point(w):
            w.say("the bot ended by itself before a safe point: steps 7 and 9 let the daily in")
            return 3
        to_main_window(w)
        if next_task:
            hand_over(w, task, next_task)
        else:
            w.pause(None)
            w.say("on the main window, the hold stays: start the bot again under bot-b.log, with `preflight.py plan --resumed`")
        return 0
    except Failed as why:
        w.say(f"failed: {why}. The bot was told to end and the hold of {task} is paused for {PAUSE} min: look at the screen")
        w.shot("failed")
        return 1


def probe_override(screens=SCREENS, timeout_ms: int = LOOK_MS) -> dict:
    """The pipeline override of one look: `screens` tried in order, each with its action switched off."""
    own = {n: giveup.DIALOG_NODES[n] for n in screens if n in giveup.DIALOG_NODES}
    return screen_probe.override(PROBE, screens, timeout_ms, own)


def look(t) -> str | None:
    return screen_probe.look(t, PROBE, probe_override(), SCREENS)


def glance(t) -> str | None:
    return screen_probe.look(t, PROBE, probe_override(SAFE, GLANCE_MS), SAFE)


def to_window(t) -> bool:
    return t.post_task("RecoverL2").wait().succeeded


def bot_processes(pid: int) -> list:
    """The bot's processes, the detached root last, without an adb server and what runs under it (#687)."""
    import psutil

    from live.device import below_adb, bot_tree

    tree = bot_tree(pid)
    kept = below_adb(tree)
    return [*(p for p in tree if p not in kept), psutil.Process(pid)]


def suspend(procs: list) -> Callable[[], None]:
    from live.device import each

    held = [p for p in procs if each(p.suspend)]

    def resume():
        for p in held:
            each(p.resume)
    return resume


def end(procs: list, wait: float = 10) -> None:
    """End these processes; one that ended meanwhile is fine, one that stays is a failure."""
    import psutil

    for p in procs:
        try:
            p.kill()
        except psutil.Error:  # gone, or refused: the wait below tells
            pass
    _, left = psutil.wait_procs(procs, timeout=wait)
    if left:
        raise Failed(f"the bot's processes {[p.pid for p in left]} did not end")


def run(a) -> int:
    scratch = main_checkout() / ".local" / "scratch"
    folder = scratch / a.task
    bot_log, run_log = a.bot_log or folder / "bot.log", a.run_log or folder / "run.log"

    def say(line):
        print(time.strftime("%H:%M:%S"), line, flush=True)

    if a.next and any((scratch / a.next / name).exists() for name in ("hold.log", "done")):
        say(f"stop: {a.next} was used before (it has a hold.log or a done file): give the next leg a fresh name")
        return 2
    doc = queue.detached_doc(bot_log)
    if doc is None:
        say(f"stop: no bot was started with --log {bot_log}")
        return 2

    os.environ["MAAFW_BINARY_PATH"] = str(a.install.resolve() / "maafw")
    from maa.toolkit import Toolkit

    from live import backup, device

    out = a.out or folder / "give-way"
    out.mkdir(parents=True, exist_ok=True)
    Toolkit.init_option(str(out / "maa"))
    ctl = device.connect(a.port)
    t = giveup.tasker(ctl, a.install.resolve() / "resource/base")
    return watch(World(
        holders=lambda: queue.holders(queue.queue_dir("emulator")),
        bot_runs=lambda: queue.detached_running(bot_log),
        forfeit_pending=lambda: forfeit_pending(run_log),
        glance=lambda: glance(t),
        look=lambda: look(t),
        suspend=lambda: suspend(bot_processes(doc["pid"])),
        end_bot=lambda: end(bot_processes(doc["pid"])),
        lift_finger=lambda: ctl.post_touch_up().wait(),
        back=lambda: ctl.post_click_key(giveup.BACK.code).wait(),
        to_window=lambda: to_window(t),
        shot=lambda name: device.shot(ctl, out / f"{device.stamp()}-{name}.png"),
        pause=lambda minutes: say(hold.pause(folder, minutes)),
        queue_next=lambda: queue.detach(next_leg_command(a.next, scratch, a.timeout, a.recording), scratch / a.next / "hold.log"),
        stop_recording=lambda: backup.stop_recording(a.recording) if a.recording else None,
        done=lambda: (folder / "done").write_text("gave way\n", encoding="utf-8"),
        say=say), a.task, a.next)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("watch")
    p.add_argument("--task", required=True, help="the task whose hold has the emulator")
    p.add_argument("--install", type=Path, required=True, help="the install the bot runs on")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--next", help="a fresh task name, for the leg after the daily")
    which.add_argument("--now", action="store_true", help="a deliberate break: no daily needed, the hold stays")
    p.add_argument("--recording", help="the screenrec profile to stop before the hold ends, and the next hold's --stop-recording")
    p.add_argument("--timeout", type=float, default=7200, help="the next hold's --timeout")
    p.add_argument("--port", type=int, default=16384)
    p.add_argument("--out", type=Path)
    p.add_argument("--bot-log", type=Path)
    p.add_argument("--run-log", type=Path)
    p = sub.add_parser("look")
    p.add_argument("--glance", action="store_true", help="as the wait for a safe point sees it")
    p.add_argument("--json", action="store_true", help="the names as one JSON line at the end")
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)
    if a.command == "watch":
        return run(a)
    named = giveup.look_files(a.images, REPO / "assets/resource/base", glance if a.glance else look)
    if a.json:
        print(json.dumps(named))
    return 0


if __name__ == "__main__":
    sys.exit(main())
