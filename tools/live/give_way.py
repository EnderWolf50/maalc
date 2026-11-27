"""A live run that holds the emulator gives way to the daily task, or takes a deliberate break, at a safe point (#853).

    uv run --group probe python tools/live/give_way.py watch --task T --install DIR (--next T2 [--recording PROFILE] [--timeout S] | --now)
        [--port 16384] [--out DIR] [--bot-log FILE] [--run-log FILE]
    uv run --group probe python tools/live/give_way.py look [--glance | --home] [--json] IMAGE...

Start `watch` detached beside the bot (`queue.py detach --log <local>/scratch/T/give-way.log -- ...`; a name the hold's
`--guard` glob of bot logs does not match). Its files default to the task's folder: bot.log, run.log, done and, for the
screenshots, give-way/.

**watch** waits until a `--first` ticket (the daily task, queue.py) stands behind T's, then for a safe point, and leaves:

  1. Safe point: the bare map (MirrorMap) shows, and the run log has no forfeit under way (only the bot's memory holds it: a
     new bot would play on). It suspends the bot's processes but an adb server and reads the whole screen, at once and
     again after SETTLE s for a tap already sent: the map or a node's panel it opened (MapNodePanel) is safe, a window over
     the map (OVER_MAP) is not. When it is not, or the ticket left, it resumes the bot and looks again.
  2. It pauses the hold of T (queue.py pause), ends the bot's processes, lifts a finger a cut swipe may have left down,
     closes a node panel with the Back key and goes to the main window with the pipeline's RecoverL2 (Dungeon Progress,
     To Window, Pause Exploration Confirm): the run stays in progress, and the daily's pre-flight reads `ok` there. The
     Event / System Notifs window over it is closed with the Back key (no live run has shown it); no other window is
     touched, and the expired-run dialog ends the step at once.
  3. It stops the recording PROFILE and queues the next leg T2 with `--first`, so it stands right behind the daily and ahead
     of the tasks that wait: one of them would start on an account with the run in progress. Then it creates T's done
     file: `hold` verifies install/ and the daily starts.

The next leg is the caller's: the maalc-live-test skill's steps under T2, on the same install with no new `prep`; the bot
picks the run up with Resume, and `preflight.py plan --resumed` checks that it did.
`--now` needs no daily: it leaves at the first safe point the same way, and the hold stays (its pause lifted): start the
bot again under bot-b.log. It is the check that Resume picks the run up when no daily came.

Exit 0: left, the last line says what comes next. Exit 1: a step failed after the bot was told to end: the hold stays
paused for PAUSE minutes, the emulator is the caller's, look at the screenshots. Exit 2: the bot was not told to end (T
does not hold the emulator, no bot runs, T2 was used before, the emulator did not answer). Exit 3: the bot ended by itself before a safe point: the skill's steps 7
and 9 let the daily in.

`watch --device pc` (#949) is refused on the PC client's window, with why: leaving takes the Back key and RecoverL2's
taps, which this version's PC window controller does not take (spec #922 D6; its input comes with #946).

**look** names the screen of each image as step 1 reads it (--glance: as the wait for it does, the map and the panel alone;
--home: as the wait for the main window does): the tests' seam.
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

from live import device, giveup, hold, queue, screen_probe  # noqa: E402
from live.preflight import BOT_START  # noqa: E402
from local_dir import main_checkout  # noqa: E402

# The probe's order: what can stand over the map comes before it, as the map's icons read through it.
OVER_MAP = ("ParallelModePrompt", "ExtremeModePrompt", "HiddenBattle", "PopupButton", "HelpPager", "GiftGet", "ForfeitDialog",
            "ProgressPanel", "RecoverPauseConfirm", "LevelWarning")  # RecoverPauseConfirm: the Save your progress dialog
SAFE = ("MapNodePanel", "MirrorMap")  # the panel first: the map's icons read beside it
HOME = "HomeReached"
SCREENS = (*OVER_MAP, *SAFE, HOME)
# The wait for the main window: the dialogs and the server's popups before the notice window, so no Back key answers one.
EXPIRED, NOTICE = "PreviousSessionExpired", "Notices"
SERVER_POPUPS = ("Connecting", "RetryPopup", "MaintenanceNotice", "ClientOutdated", "DeviceRooted", "UpdateDialog",
                 "UserAgreement", "DownloadDialog", "Downloading", "Loading")  # popups.json's ServerPopups, and Connecting
DIALOG = "DialogButton"
HOME_SCREENS = (EXPIRED, *OVER_MAP, *SERVER_POPUPS, *SAFE, DIALOG, NOTICE, HOME)
HOME_NODES = {
    # Notices reads any title that ends in Notifs, and the expired-run dialog's is "Notifs" alone: here only the window's
    # two tabs count. The bot's own node stays (#935): its Back key is also its answer to other "Notifs" titles.
    NOTICE: {"expected": "(Event|System)\\s*Notifs$"},
    # A dialog over the notice window, such as a quit dialog the Back key opened: its tabs still read beside it. The window
    # has no such button, and its text is told by the line's end.
    DIALOG: {"recognition": "OCR", "roi": [340, 380, 600, 180], "expected": "(Cancel|Confirm|Close|OK)$"},
}
PROBE = "GiveWayProbe"
LOOK_MS = 1500  # how long one look at the whole screen tries before it names none
GLANCE_MS = 0  # one pass over the two map templates: what the wait for a safe point costs the running bot
HOME_MS = 0  # one pass over HOME_SCREENS: a window that opens or fades is looked at again, not waited out

DUE_POLL = 15.0  # s between two looks at the queue
GLANCE_POLL = 0.3  # s between two glances: a map whose next node is planned takes its tap soon after it stands still
SETTLE = 3.0  # s a suspended bot's last tap has to change the screen (a node panel shows within about 0.5 s, #130)
PAUSE = 120  # min the hold stays paused when a step fails
MAP_LIMIT, HOME_LIMIT = 20.0, 90.0  # s the panel has to close, and To Window to reach the main window
NOTICE_PRESSES, NOTICE_WAIT = 3, 2.0  # Back keys on the notice window, and s one has to close it (the bot's Notices waits 1.5)
MAP_POLL = 2.0  # s a Back key has to close the panel before the next look (giveup.STEPS waits the same)
QUEUED_LIMIT = 60.0  # s the next leg's ticket has to show (its process starts first)
FORFEITS = ("forfeit the run", "used: forfeit")  # battle_actions' lines as it sets RUN["forfeit"]: the map then forfeits
FORFEITED = "[maalc] forfeited the run"  # map_actions.forfeit


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


def holds(q: list[queue.Holder], task: str) -> bool:
    return bool(q) and q[0].name == queue.ticket_name(task)


def first_waits(q: list[queue.Holder], task: str) -> bool:
    """Whether a --first ticket (the daily's) waits behind task's hold."""
    return holds(q, task) and any(h.first for h in q[1:])


def next_in_line(q: list[queue.Holder], name: str) -> bool:
    """Whether the ticket `name` waits with --first ones alone (the daily's, unless it left meanwhile) before it."""
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
    look_home: Callable[[], str | None]  # one of HOME_SCREENS, or None
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


def settled_screen(w: World) -> str | None:
    """What a suspended bot's screen shows: at once when that is not safe, so the bot is not held long, else once a tap
    already sent has had SETTLE s to change it."""
    screen = w.look()
    if screen in SAFE:
        w.sleep(SETTLE)
        screen = w.look()
    return screen


def stop_at_safe_point(w: World, due: Callable[[], bool]) -> bool:
    """End the bot at a safe point while due() holds; False when it ended by itself before one. Failed only once the bot
    was told to end: any other exception leaves it running."""
    said = False
    while w.bot_runs():
        if not due():
            w.sleep(DUE_POLL)
            continue
        if not said:
            w.say("waiting for a safe point")
            said = True
        # The bare map alone: on a node's panel the bot may be about to tap Enter, and one held past its wait taps on an old screen.
        if w.glance() != "MirrorMap" or w.forfeit_pending():
            w.sleep(GLANCE_POLL)
            continue
        resume, ending = w.suspend(), False
        try:
            screen = settled_screen(w)
            if not w.bot_runs():
                return False
            safe = screen in SAFE and not w.forfeit_pending() and due()
            w.say(f"suspended on {screen}: " + ("safe" if safe else "not safe or no longer due, the bot goes on"))
            if safe:
                w.shot("safe-point")
                w.pause(PAUSE)  # before the bot ends: the hold's timeout would hand the emulator on
                ending = True
                try:
                    w.end_bot()
                except Exception as e:
                    raise Failed(f"the bot did not end: {e}") from e
                return True
        finally:
            if not ending:  # what is left of a bot told to end stays suspended: it must not tap
                resume()
        w.sleep(GLANCE_POLL)
    return False


def home_screen_or_fail(w: World) -> str | None:
    screen = w.look_home()
    if screen == EXPIRED:
        raise Failed(f"{EXPIRED} shows (the previous session has expired): not answered, it is a person's to decide")
    return screen


def close_notice(w: World, press: int) -> bool:
    """One Back key on the notice window over the main window, if it still shows SETTLE s later (a dialog that opens or a
    window that fades has changed by then): on the main window the Back key may open the quit dialog. Whether it pressed."""
    w.sleep(SETTLE)
    w.shot(f"notice-{press}")
    if home_screen_or_fail(w) != NOTICE:
        return False
    w.back()
    w.say(f"the notice window is up: Back key {press} of {NOTICE_PRESSES}")
    w.sleep(NOTICE_WAIT)
    w.shot(f"notice-{press}-after")
    return True


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

    presses = 0

    def on_home() -> bool:
        nonlocal presses
        screen = home_screen_or_fail(w)
        if screen == NOTICE:
            if presses == NOTICE_PRESSES:
                raise Failed(f"the notice window stayed after {presses} Back keys")
            presses += close_notice(w, presses + 1)
            screen = home_screen_or_fail(w)  # at once: HOME_LIMIT may have run out meanwhile
        return screen == HOME

    if not wait_until(w, HOME_LIMIT, on_home):
        raise Failed(f"the main window did not show in {HOME_LIMIT:g} s after To Window")
    w.shot("main-window")


def hand_over(w: World, task: str, next_task: str) -> None:
    """The next leg behind the daily, then the hold ended. The recording goes first: the hold stops it itself 60 s after the
    bot ended, and two stops would remux one file."""
    w.stop_recording()
    w.queue_next()
    if not wait_until(w, QUEUED_LIMIT, lambda: next_in_line(w.holders(), next_task)):
        raise Failed(f"the ticket of {next_task} is not ahead of the plain ones after {QUEUED_LIMIT:g} s")
    w.say(f"{next_task} queued ahead of the plain tickets")
    w.done()
    w.pause(None)
    w.say(f"{task} gave way; next: wait for `[queue] start {queue.ticket_name(next_task)}` in {next_task}'s hold.log, then "
          "steps 2, 5 and 6 under it on the same install (no prep), with `preflight.py plan --resumed`")


def failed(w: World, task: str, why: Exception) -> int:
    w.say(f"failed: {why!r}. The bot was told to end and the hold of {task} is paused for {PAUSE} min: look at the screen")
    try:
        w.shot("failed")
    except Exception as e:  # the emulator may be what failed
        w.say(f"no screenshot: {e!r}")
    return 1


def watch(w: World, task: str, next_task: str | None) -> int:
    """next_task None: a deliberate break (--now), the hold kept."""
    def due() -> bool:
        return next_task is None or first_waits(w.holders(), task)

    if not holds(w.holders(), task) or not w.bot_runs():
        w.say(f"stop: {task} does not hold the emulator, or its bot does not run")
        return 2
    try:
        left = stop_at_safe_point(w, due)
    except Failed as why:
        return failed(w, task, why)
    except Exception as e:
        w.say(f"stop: {e!r} before the bot was told to end: the bot goes on, start the watch again")
        return 2
    if not left:
        w.say("the bot ended by itself: " + ("steps 7 and 9 let the daily in" if due() else "no daily waits, nothing to give way to"))
        return 3
    try:
        to_main_window(w)
        if next_task:
            hand_over(w, task, next_task)
        else:
            w.pause(None)
            w.say("on the main window, the hold stays: start the bot again under bot-b.log, with `preflight.py plan --resumed`")
    except Exception as why:
        return failed(w, task, why)
    return 0


def probe_override(screens=SCREENS, timeout_ms: int = LOOK_MS) -> dict:
    """The pipeline override of one look: `screens` tried in order, each with its action switched off."""
    own = {n: node for n, node in (giveup.DIALOG_NODES | HOME_NODES).items() if n in screens}
    nodes = screen_probe.override(PROBE, screens, timeout_ms, own)
    nodes[PROBE] |= {"pre_delay": 0, "post_delay": 0}  # the map a bot reads stands 0.5 s and more: each glance counts
    return nodes


def look(t) -> str | None:
    return screen_probe.look(t, PROBE, probe_override(), SCREENS)


def glance(t) -> str | None:
    return screen_probe.look(t, PROBE, probe_override(SAFE, GLANCE_MS), SAFE)


def look_home(t) -> str | None:
    return screen_probe.look(t, PROBE, probe_override(HOME_SCREENS, HOME_MS), HOME_SCREENS)


def to_window(t) -> bool:
    return t.post_task("RecoverL2").wait().succeeded


def bot_processes(pid: int) -> list:
    """The bot's processes, the detached root last, without an adb server and what runs under it (#687)."""
    import psutil

    from live.device import below_adb, bot_tree

    try:
        tree = bot_tree(pid)
        kept = below_adb(tree)
        return [*(p for p in tree if p not in kept), psutil.Process(pid)]
    except psutil.NoSuchProcess:  # the bot has just ended
        return []


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

    from live import backup

    out = a.out or folder / "give-way"
    out.mkdir(parents=True, exist_ok=True)
    Toolkit.init_option(str(out / "maa"))
    try:
        ctl = device.connect(a.port)
    except SystemExit as e:  # no device on the port
        say(f"stop: {e}")
        return 2
    t = giveup.tasker(ctl, a.install.resolve() / "resource/base")
    return watch(World(
        holders=lambda: queue.holders(queue.queue_dir("emulator")),
        bot_runs=lambda: queue.detached_running(bot_log),
        forfeit_pending=lambda: forfeit_pending(run_log),
        glance=lambda: glance(t),
        look=lambda: look(t),
        look_home=lambda: look_home(t),
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
    device.add_device(p)
    p.add_argument("--out", type=Path)
    p.add_argument("--bot-log", type=Path)
    p.add_argument("--run-log", type=Path)
    p = sub.add_parser("look")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--glance", dest="look", action="store_const", const=glance, default=look, help="as the wait for a safe point sees it")
    how.add_argument("--home", dest="look", action="store_const", const=look_home, help="as the wait for the main window sees it")
    p.add_argument("--json", action="store_true", help="the names as one JSON line at the end")
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)
    if a.command == "watch":
        if a.now and a.recording:
            ap.error("--now keeps the hold and its recording: no --recording")
        if a.device == "pc":
            print(f"refused: give_way.py watch leaves with the Back key and RecoverL2's taps, and {device.NO_INPUT}",
                  flush=True)
            return 1
        return run(a)
    named = giveup.look_files(a.images, REPO / "assets/resource/base", a.look)
    if a.json:
        print(json.dumps(named))
    return 0


if __name__ == "__main__":
    sys.exit(main())
