"""Custom actions: the choices MirrorHub hands to the Agent (ADR 0002).

The Pipeline decides which screen is up; these decide what to pick on it.
Coordinates are on the 1280x720 screenshot (spec 07).
"""

import functools
import json
import re
import time
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
import yaml
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.define import Rect

import battle
import gift_search
import hub_text
import map_route
import recovery
import rewards
import run_start
import settlement
import shop
from ocrtext import compact, digits, has, normalize
from settings import SCHEMA, SettingsError, load_settings
from state import next_cursor, pick_team, read_cursor, write_cursor

# Same <root> as main.ROOT; resource/ sits under it in a release, under assets/ in the repo.
ROOT = Path(__file__).resolve().parent.parent
RESOURCE = next(p for p in (ROOT / "resource", ROOT / "assets" / "resource") if p.is_dir())

# This run's plan, made on the entry page: {"settings", "team", "difficulty"}.
# Memory only (ADR 0003); an agent restarted mid-run falls back to current_run's guess.
RUN = {}
SETTLED = {"runs": 0}  # runs claimed since this agent started: the run count stop (spec 01); never saved
# Stuck detection and recovery (spec 06), memory only: the last node seen ("node", its id) and the
# screen type it handled ("kind"), a pending stuck for MirrorHub's Stuck node ("flag": (kind, start
# level, reason)), this run's Ladder, and the game restarts since this agent started ("l3").
STUCK = {"node": None, "kind": None, "flag": None, "watch": recovery.Watchdog(), "ladder": recovery.Ladder(), "l3": 0}
SCREENS = deque(maxlen=20)  # the last screens MirrorHub handed out: the evidence on a stop
LOG = deque(maxlen=500)

WEEKLY_SLOTS = (922, 960, 998)  # x of the 3 Weekly Bonuses slots on the entry page, y 285-297
TEAM_LIST = [75, 292, 115, 245]
ENTER_DIALOG = [400, 325, 480, 45]  # "Will you enter ...?"
TEAM_TITLE = [220, 112, 210, 26]  # "TEAMS #n" over the card list
LEVEL_WARNING = [400, 230, 480, 90]  # "... lower than the recommended level ..."
STARLIGHT_HEADER = [890, 30, 115, 28]  # "Available"
STARLIGHT_DIALOG = [480, 210, 320, 35]  # "Continue with selected effects?"
STARTING_GIFT_HEADER = [780, 145, 230, 35]  # "Selected E.G.O Gift"
STARLIGHT_AVAILABLE = [1010, 30, 80, 28]
STARLIGHT_NOTE = [660, 395, 320, 90]  # the line under Convert Starlight to Cost: "unspent" when off, "remaining" when on
STARLIGHT_OWNED = [830, 30, 90, 28]  # "4035", "4035-60" while owned starlight pays
GRACE_ORIGIN_X, GRACE_ORIGIN_Y = (138, 152), (152, 390)  # top-left of card 1; step 198 px per column
PACK_TITLES = [120, 400, 1040, 100]  # up to 5 cards (live: 5 with two Theme Pack Selection +1 graces)


def log(msg):
    LOG.append(f"{time.strftime('%H:%M:%S')} {msg}")
    print(f"[maalc] {msg}", flush=True)


def screen(context):
    return context.tasker.controller.post_screencap().wait().get()


def tap(context, x, y, wait=1.0):
    context.tasker.controller.post_click(x, y).wait()
    time.sleep(wait)


def until(context, done, timeout=2.0, least=0.0, every=0.2):
    """Screenshots every `every` s until done(image) holds: that image, or None after timeout s (#58).

    least: s to wait before the first look, where the game ignores taps during an animation.
    """
    time.sleep(least)
    end = time.monotonic() + timeout
    while True:
        image = screen(context)
        if done(image):
            return image
        if time.monotonic() >= end:
            return None
        time.sleep(every)


def shows(context, roi, pattern, flags=re.I):
    """A done(image) for until(): the OCR text in roi matches pattern."""
    return lambda image: re.search(pattern, normalize(text(context, image, roi)), flags) is not None


def tap_then(context, x, y, done, timeout=2.0):
    """Tap, then until() done(image) holds: that image, or None after timeout s (#115)."""
    tap(context, x, y, wait=0)
    return until(context, done, timeout=timeout)


def tap_moved(context, x, y, timeout=1.0):
    """Tap, then until() the screen moves: that screen, or None after timeout s (nothing took the tap)."""
    before = screen(context)
    return tap_then(context, x, y, lambda im: moved(before, im), timeout=timeout)


def tap_settled(context, x, y, timeout=1.5):
    """Tap, wait for the screen to move, then for it to stop (still): a page or dialog that animates in or out.

    A still() straight after the tap can look before the animation starts and see a screen at rest.
    """
    tap_moved(context, x, y, timeout)
    return still(context, timeout=timeout)


def tap_shown(context, x, y, done, timeout=2.0, rest=1.5):
    """tap_then(), then still(): a page or dialog read or tapped on once it stops moving. Its last screenshot, or None
    when done(image) never held."""
    image = tap_then(context, x, y, done, timeout=timeout)
    if image is None:
        return None
    settled = still(context, timeout=rest)
    return image if settled is None else settled


def still(context, timeout=2.0):
    """The first screenshot that looks like the one 0.2 s before it: a fade in or out has ended; None after timeout s.

    MirrorHub, polling every 300 ms, can hand out a page while it is still fading in or the last one fading out.
    """
    last = [recovery.thumb(screen(context))]

    def done(image):
        small = recovery.thumb(image)
        same = recovery.same_screen(last[0], small)
        last[0] = small
        return same
    return until(context, done, timeout=timeout, least=0.2)


class PageGone(Exception):
    """The page an action works on went away mid-action (#118): by hand, a popup, a disconnect."""


def on_page(context, image, *nodes):
    """The first of nodes (MirrorHub's screen nodes) that hits on image, or None."""
    return next((n for n in nodes if seen(context, image, n)), None)


POPUPS = ("Connecting", "RetryPopup", "PopupButton")  # MirrorHub's global popups: answered before any page


def page_guard(context, home, image=None):
    """Before a tap: a screenshot that still shows home (MirrorHub's node for the action's page); else PageGone.

    ADR 0007, #118: an action that taps on for long checks its page first, so a screen changed under it is
    handed back to MirrorHub at once instead of tapped blind until the action gives up. A miss is looked at
    again for up to 1 s: a page fading or a dialog dropping in can hide its anchor for a moment.
    A global popup reads through to the page under it (maatools: the title's nodes hit under RetryCountdown.png), so
    one of POPUPS showing is the page gone too: MirrorHub answers it first.
    image: a screenshot just taken, looked at first.
    """
    def shown(im):
        return on_page(context, im, *POPUPS, home) == home

    if image is not None and shown(image):
        return image
    image = until(context, shown, timeout=1.0)
    if image is None:
        raise PageGone(home)
    return image


CLEAR_CACHE_AFTER_NODES = 200  # ~6 min: a 24-min stretch of a live run's log had 784 nodes


def clear_long_task_cache(context, argv):
    """Clear MaaFramework's runtime cache once the task has CLEAR_CACHE_AFTER_NODES nodes (#176).

    The cache keeps every node's and recognition's detail until clear_cache, and a whole dungeon run is one task.
    Only the end of an action may clear it: the clear drops the task's own detail too, and without it every custom
    recognition and action of the task misses, including those the action's own run_recognition and run_task reach
    (they share the task's id); the end of the action's node writes it back right after. A hands_back action run
    inside a run_task would leave the rest of that subtask without it; none is (RecoverL1-3 have no custom node).
    """
    detail = getattr(argv, "task_detail", None)  # (the tests' argv has none)
    if detail and len(detail.node_id_list) >= CLEAR_CACHE_AFTER_NODES:
        context.tasker.clear_cache()


def hands_back(run):
    """An action's run(): PageGone ends it with True, for MirrorHub to look at the screen now up (#118).

    It then clears the runtime cache of a long task (clear_long_task_cache).
    """
    @functools.wraps(run)
    def wrapped(self, context, argv):
        try:
            return run(self, context, argv)
        except PageGone as e:
            log(f"{type(self).__name__}: {e} is gone: back to MirrorHub")
            return True
        finally:
            clear_long_task_cache(context, argv)
    return wrapped


def grid_moved(before, after):
    """Whether the gift search grid shows other gifts: a tab switched, or a scroll went somewhere."""
    return np.abs(after[228:625, 85:775].astype(int) - before[228:625, 85:775].astype(int)).mean() >= 2


def moved(before, after):
    """Whether any 40x40 block of the screen changed by more than 8 levels: a tap took (#58)."""
    return bool((np.abs(recovery.thumb(before) - recovery.thumb(after)) > 8).any())


def swipe(context, x1, y1, x2, y2, ms=500, wait=1.0):
    context.tasker.controller.post_swipe(x1, y1, x2, y2, ms).wait()
    time.sleep(wait)


def scroll(context, x, y, dx, dy):
    """Drag the content under (x, y) by (dx, dy) px and let go without a fling (spec 07).

    The game's drag threshold eats the first move, so the finger first moves 10 px and rests 0.1 s (a move
    right after it can be eaten too), then moves (dx, dy) in 20 px moves 10 ms apart. The game flings the content
    on with the speed the finger still has at the lift, decaying while it rests, so it rests SCROLL_HOLD s first.
    """
    d = max(abs(dx), abs(dy), 1)
    lx, ly = x + round(10 * dx / d), y + round(10 * dy / d)
    drag(context, [(x, y), (lx, ly), (lx + dx, ly + dy)], settle=0, dwell=0.1, hold=SCROLL_HOLD, pause=0.01, step=20)


# Live 2026-10-18 (#114): with these moves (~1000 px/s) a 0.55 s rest left at most 1 px of fling in 126 drags of
# 50-300 px on the map, the team list and the gift grid, 0.62-0.77 s each (1 px and 0.73-1.25 s before);
# 0.5 s left 2 px, 0.4 s 6 px. Resting 0.05 s after the threshold move, 1 drag in ~200 lost a whole 20 px move.
# At ~330 px/s the fling was +1/+6/+19/+58/+176 px for 0.5/0.3/0.2/0.1/0 s.
SCROLL_HOLD = 0.55


def drag(context, points, settle=0.3, dwell=0.1, hold=0.0, pause=0.02, step=10):
    """One touch through points: down on the first, settle s, then step px moves pause s apart, dwell s on each point.

    Lifts on the last point after hold s; at once by default: a finger held on a battle skill opens its details.
    """
    ctl = context.tasker.controller
    ctl.post_touch_down(*points[0]).wait()
    time.sleep(settle)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        n = max(1, max(abs(x1 - x0), abs(y1 - y0)) // step)
        for k in range(1, n + 1):
            ctl.post_touch_move(round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n)).wait()
            time.sleep(pause)
        if (x1, y1) != points[-1]:
            time.sleep(dwell)
    time.sleep(hold)
    ctl.post_touch_up().wait()


def ocr(context, image, roi, only_rec=False):
    """Every OCR result in roi as (text, (x, y, w, h)); only_rec reads roi as one line, no text detection."""
    detail = context.run_recognition("ReadText", image, {"ReadText": {"recognition": "OCR", "roi": roi, "only_rec": only_rec}})
    return [(r.text, tuple(r.box)) for r in (detail.all_results if detail else [])]


def text(context, image, roi, only_rec=False):
    return " ".join(t for t, _ in ocr(context, image, roi, only_rec))


def number(s):
    found = re.sub(r"\D", "", s)
    return int(found) if found else None


def address(context):
    return context.tasker.controller.info.get("adb_serial", "default")


def current_run(context):
    """The run plan; made up from settings and the rotation cursor when the agent restarted mid-run."""
    if "settings" not in RUN:  # a run plan, not just counters left by an action
        settings = load_settings(ROOT)
        difficulty = settings["run"]["difficulty"]
        difficulty = None if difficulty == "auto" else difficulty
        cursor = read_cursor(ROOT, address(context))
        team = pick_team(settings["teams"], cursor, difficulty or "hard") or pick_team(settings["teams"], cursor, "normal")
        RUN.update(settings=settings, team=team, difficulty=difficulty)
        # The guard turns left are unknown after a restart: they count as used up (spec 03 section 8).
        log(f"no run plan in memory: assuming team {team['name']!r}, difficulty {difficulty or 'unknown'}, no guard turns")
    return RUN


# Stuck detection, recovery and the stop procedure (spec 06).
def stuck(reason, level=1):
    """Hand the screen being handled to recovery: MirrorHub's Stuck node picks it up next.

    Returns True, for the action to return: its [JumpBack] leads to MirrorHub.
    """
    log(f"stuck: {reason}")
    STUCK["flag"] = (None, level, reason)  # StuckFlag fills in the screen type
    return True


def run_line(run, outcome, hard, floors, bonuses=0):
    """This run's runs.jsonl line (spec 06 執行記錄)."""
    team = run["team"] if run.get("planned") else None
    counts = STUCK["ladder"].counts
    return {
        "start": run.get("start"), "end": settlement.now(),
        "team": team and team["id"], "team_name": team and team["name"],
        "difficulty": "hard" if hard else "normal", "weekly_bonus": bonuses,
        "floors": floors, "result": outcome, "l1": counts[1], "l2": counts[2], "l3": counts[3],
        **({"gift_search": run["gift_search"]} if "gift_search" in run else {}),
    }


def stop(context, reason, line=None):
    """The stop procedure (spec 06 停止程序): evidence, a `stop` line in runs.jsonl, the webhook.

    line is this run's line when the caller knows it better (Settle); otherwise one is made up while a
    run is under way. Returns False, for the action to return: that ends the task.
    """
    log(f"stop: {reason}")
    if line is None and "settings" in RUN:
        line = run_line(RUN, "stop", RUN.get("floor_hard", RUN.get("difficulty") == "hard"), max(RUN.get("floor", 1) - 1, 0))
    if line:
        settlement.append_run(ROOT, line)
    folder = ROOT / "logs" / "evidence" / settlement.now().replace(":", "-")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for i, image in enumerate([*SCREENS, screen(context)]):  # the last one: the screen now
            (folder / f"{i:02}.png").write_bytes(recovery.png(image))
        (folder / "agent.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
        log(f"evidence: {folder}")
    except OSError as e:
        log(f"evidence not saved: {e}")
    settings = RUN.get("settings")
    if settings is None:
        try:
            settings = load_settings(ROOT)
        except SettingsError:
            settings = None
    url = settings and settings["run"]["webhook_url"]
    if url:
        body = json.dumps({**(line or {}), "reason": reason, "evidence": str(folder)}, ensure_ascii=False).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=10).close()
            log("webhook sent")
        except (OSError, ValueError) as e:
            log(f"webhook failed: {e}")
    return False


# MirrorHub's own steps, no screen: the watchdog keeps the screen handled before them.
PASS_NODES = ("BattleHUD", "BattleHUDLost", "HubText", "HubTextLost")


@AgentServer.custom_recognition("StuckFlag")
class StuckFlag(CustomRecognition):
    """MirrorHub's Stuck node: watches every screen it hands out, hits while a stuck waits for recovery.

    It runs first on each MirrorHub pass, so the task's last node is the screen just
    handled and argv.image what it left: the watchdog, the evidence and the run time limit work from them.
    """

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        ids = argv.task_detail.node_id_list
        if ids and ids[-1] != STUCK["node"]:
            STUCK["node"] = ids[-1]
            node = context.tasker.get_node_detail(ids[-1])
            if node and node.name not in ("MirrorDungeon", "MirrorHub", "Stuck", "GlobalStuck", *PASS_NODES):
                self.see(node.name, argv.image)
        if STUCK["flag"] and STUCK["flag"][0] is None:
            STUCK["flag"] = (STUCK["kind"], *STUCK["flag"][1:])  # reported by the action of the node just handled
        return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={}) if STUCK["flag"] else None

    @staticmethod
    def see(kind, image):
        STUCK["kind"] = kind
        SCREENS.append(image)
        STUCK["ladder"].progress(kind)
        if STUCK["flag"]:
            return
        if why := STUCK["watch"].see(kind, recovery.thumb(image), time.monotonic()):
            stuck(f"{kind}: {why}")
        elif recovery.over_time(kind, RUN.get("deadline"), time.time()):
            RUN.pop("deadline")  # once a floor: the next floor starts the clock again
            stuck(f"floor {RUN.get('floor', '?')} over its time limit", level=2)


AgentServer.custom_recognition("HubText")(hub_text.HubText)


@AgentServer.custom_action("Recover")
class Recover(CustomAction):
    """Run the recovery level the Ladder gives (Pipeline RecoverL1-3), or stop (spec 06).

    MirrorHub's timeout (GlobalStuck, no flag set) counts as a stuck on the last screen handed out.
    A level that does not go through climbs straight to the next one.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        unknown = STUCK["flag"] is None  # MirrorHub's own timeout: a screen it has no node for
        flag = STUCK["flag"] or (f"{STUCK['kind']}, then nothing recognised", 1, "MirrorHub recognised nothing for 60 s")
        STUCK["flag"] = None
        if unknown:  # also during a download: its progress screen is one to have a capture of
            try:
                recovery.keep_unknown(ROOT, screen(context), settlement.now().replace(":", "-"))
            except OSError as e:
                log(f"unknown screen not saved: {e}")
        if STUCK["watch"].held(time.monotonic()):
            log(f"{flag[2]}: a download is under way, waiting")
            return True
        kind, start, reason = flag
        while True:
            level, why = STUCK["ladder"].stuck(kind, start, STUCK["l3"])
            if level is None:
                return stop(context, f"{reason}; {why}")
            log(f"recovery L{level}: {reason}")
            STUCK["l3"] += level == 3
            detail = context.run_task(f"RecoverL{level}")
            if detail and detail.status.succeeded:
                break
            log(f"L{level} did not go through")
            STUCK["ladder"].failed(level)
        STUCK["watch"].reset()
        for key in ("turn", "battle_start", "map_misses", "event_tried", "map_plan", "map_entered"):
            RUN.pop(key, None)
        return True


@AgentServer.custom_action("ConfirmDownload")
class ConfirmDownload(CustomAction):
    """Confirm the title's download dialog (the matched button), then let the download run without a stuck.

    Its progress screen is not known, so MirrorHub may recognise nothing for a long while (#86).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        x, y, w, h = argv.box
        context.tasker.controller.post_click(x + w // 2, y + h // 2).wait()
        STUCK["watch"].hold(time.monotonic(), recovery.DOWNLOAD_HOLD)
        log(f"download confirmed: nothing counts as stuck for {recovery.DOWNLOAD_HOLD // 60} min")
        return True


@AgentServer.custom_action("Halt")
class Halt(CustomAction):
    """Stop on a screen the bot must not act on (the maintenance notice); the reason goes to the log."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return stop(context, f"{argv.node_name}: {json.loads(argv.custom_action_param or '""')}")


@AgentServer.custom_action("TapUntil")
class TapUntil(CustomAction):
    """A Click node that waits for the page that follows instead of a post_delay (#115).

    Param: {"target": [x, y, w, h], "next": {"roi": [...], "expected": regex} or a list of them (any), "timeout": s (default 3)}.
    The page it leaves may still read like itself for a moment; MirrorHub would act on it twice.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        p = json.loads(argv.custom_action_param)
        x, y, w, h = p["target"]
        pages = [shows(context, n["roi"], n["expected"]) for n in (p["next"] if isinstance(p["next"], list) else [p["next"]])]
        tap_then(context, x + w // 2, y + h // 2, lambda im: any(page(im) for page in pages), timeout=p.get("timeout", 3))
        return True


@AgentServer.custom_action("PlanRun")
class PlanRun(CustomAction):
    """Entry page, no run under way: check settings, pick difficulty and team, press Enter (spec 03 sections 1, 2).

    Returning False fails the task: that is the stop.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            settings = load_settings(ROOT)
        except SettingsError as e:
            log(f"stop: {e}")
            return False
        hsv_v = screen(context)[285:297].max(axis=2)  # V of HSV
        # Live: a filled slot reads V ~240, an empty one ~5 (2026-10-15).
        weekly = sum(hsv_v[:, x:x + 30].mean() > 40 for x in WEEKLY_SLOTS)
        run = settings["run"]
        if settlement.runs_done(SETTLED["runs"], run["runs"]):
            log(f"stop: {SETTLED['runs']} of {run['runs']} runs done")
            return False
        if run["stop_when_weekly_bonus_out"] and weekly == 0:
            log("stop: weekly bonuses used up")
            return False
        difficulty = run_start.run_difficulty(run["difficulty"], weekly)
        team = pick_team(settings["teams"], read_cursor(ROOT, address(context)), difficulty)
        if team is None:
            log(f"stop: no enabled team may run {difficulty}")
            return False
        if run_start.team_difficulty(run["difficulty"], difficulty, team["hard_from_floor"]) != difficulty:
            log(f"team {team['name']!r} never switches to hard and the difficulty is {run['difficulty']}: a normal run")
            difficulty = "normal"
        RUN.clear()
        # planned: the bot picked the team itself, so the rotation cursor may move after the claim.
        limit = recovery.floor_limit(recovery.read_runs(ROOT), team["id"])
        # guard: the run's guard turns left (spec 03 section 8), counted across its battles.
        # floor_limit: each floor's time; the first clock runs from here, PickThemePack restarts it (spec 06).
        RUN.update(settings=settings, team=team, difficulty=difficulty, planned=True, start=settlement.now(), deadline=time.time() + limit,
                   floor_limit=limit, guard=team["guard_turns"])
        STUCK["ladder"] = recovery.Ladder()
        log(f"new run: {difficulty}, team {team['name']!r} (TEAMS #{team['game_team']}), weekly bonuses left {weekly}, time limit {limit / 60:.0f} min a floor")
        tap_then(context, 1108, 494, shows(context, ENTER_DIALOG, "Will you enter"), timeout=3)
        return True


INFINITY_TITLE = [890, 330, 330, 28]  # entry page: "Parallel Superposition Mode : ON" / "OFF" (the pipeline's roi)
INFINITY_BUTTON = (1053, 377)  # INFINITY MIRROR under it


@AgentServer.custom_action("ParallelModeOff")
class ParallelModeOff(CustomAction):
    """Entry page with Parallel Superposition Mode ON: tap INFINITY MIRROR until it reads OFF (#94, spec 02).

    The bot never plays past floor 5; the prompt after floor 5 (ParallelModePrompt) is cancelled as a second guard.
    Still ON after two taps: stop, nothing else is tried.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        for _ in range(2):
            if tap_then(context, *INFINITY_BUTTON, shows(context, INFINITY_TITLE, r":\s*[O0]FF"), timeout=3) is not None:
                log("Parallel Superposition Mode switched OFF")
                return True
        return stop(context, "Parallel Superposition Mode stays ON after tapping INFINITY MIRROR")


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Pick the team's in-game TEAMS #N slot, check the title, press Confirm."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # No plan here means a run resumed on the entry page, paused before team selection: the entry page only
        # offers Resume again, so backing out looped (#128). Make one up from settings, as after a restart.
        n = current_run(context)["team"]["game_team"]
        for _ in range(15):
            image = page_guard(context, "TeamSelect")
            visible = {}
            for t, (x, y, w, h) in ocr(context, image, TEAM_LIST):
                m = re.search(r"#\s*(\d+)", t)
                if m and 300 <= y + h // 2 <= 515:  # rows cut off at the list edge do not count
                    visible[int(m[1])] = y + h // 2
            move = run_start.team_list_move(visible, n)
            if move == "down":
                scroll(context, 130, 480, 0, -140)
            elif move == "up":
                scroll(context, 130, 340, 0, 140)
            else:
                image = tap_then(context, 130, move[1], shows(context, TEAM_TITLE, rf"#\s*{n}\b"))
                if image is not None:
                    bonus = number(text(context, image, [1160, 522, 60, 34]))
                    log(f"team TEAMS #{n}, Starlight Bonus {bonus}")
                    # LevelWarning when the team is under the recommended level, else the starlight page; the team page
                    # reads through the warning, so leaving it early would have MirrorHub pick the team twice.
                    warning, starlight = shows(context, LEVEL_WARNING, "recommended level"), shows(context, STARLIGHT_HEADER, "Available")
                    tap_then(context, 1145, 587, lambda im: warning(im) or starlight(im), timeout=4)
                    return True
        return stop(context, f"could not select TEAMS #{n}")


def grace_box(n):
    """Top-left corner of grace card n (1-10)."""
    col, row = (n - 1) % 5, (n - 1) // 5
    return GRACE_ORIGIN_X[row] + 198 * col, GRACE_ORIGIN_Y[row]


def grace_selected(image, n):
    # A selected card is washed white: mean V ~135 against ~60.
    x, y = grace_box(n)
    return image[y + 2:y + 222, x + 2:x + 182].max(axis=2).mean() > 100


def read_available(context, image):
    """Starlight left of Available; negative by what owned starlight pays when it reads like "0+60" (#96)."""
    t = text(context, image, STARLIGHT_AVAILABLE)
    m = re.fullmatch(r"\D*(\d+)\s*\+\s*(\d+)\D*", t)
    return int(m[1]) - int(m[2]) if m else number(t)


@AgentServer.custom_action("BuyStarlight")
class BuyStarlight(CustomAction):
    """Select graces per the team's starlight plan, then press Enter (spec 03 section 4).

    Live 2026-10-14: tapping a card selects it at the level its + / ++ buttons show;
    the buttons only set the level (tapping the lit one turns it back to base).
    A card dearer than Available is still selected, paid from owned starlight: choosing the grace is the
    user's consent to that (#96), so only Available plus Owned bounds the purchases, and Available is
    re-read after every tap.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        plan = run_start.resolve_plan(run["settings"], run["team"], "starlight")
        image = screen(context)
        available = read_available(context, image)
        if available is None:
            return stuck("could not read Available on the starlight page")
        owned = re.match(r"\D*(\d+)", text(context, image, STARLIGHT_OWNED))
        unaffordable = run["settings"]["run"]["starlight_unaffordable"]
        # Back from MirrorHub (#118): Available already has the graces selected so far taken off.
        paid = sum(run_start.grace_price(n, level) for n, level in enumerate(plan["levels"], 1)
                   if level != "none" and grace_selected(image, n))
        buys, missed = run_start.starlight_purchases(plan, available + paid + (int(owned[1]) if owned else 0), unaffordable)
        for n, level, price in missed:
            log(f"grace {n} {level} costs {price}: not bought")
        if missed and unaffordable == "stop":
            return stop(context, "a planned grace is unaffordable")
        for n, level, price in buys:
            x, y = grace_box(n)
            image = page_guard(context, "StarlightPage")
            if grace_selected(image, n):
                log(f"grace {n} already selected")
                continue
            if not self.set_level(context, n, level):
                return stuck(f"could not set grace {n} to {level}")
            for _ in range(2):
                page_guard(context, "StarlightPage")
                tap(context, x + 92, y + 100)
                image = screen(context)
                now = read_available(context, image)
                if now != available:
                    break
            if now != available - price:
                page_guard(context, "StarlightPage", image=image)  # gone after the tap: back from MirrorHub, `paid` counts it
                return stop(context, f"grace {n} {level}: Available {available} -> {now}, expected -{price}")
            log(f"grace {n} {level} for {price}, {now} left" if now >= 0 else f"grace {n} {level} for {price}, {-now} paid from owned starlight")
            available = now
        run["starlight_unspent"] = max(available, 0)  # added to the Owned box at once unless ConfirmStarlight converts it (#73)
        tap_then(context, 1195, 672, shows(context, STARLIGHT_DIALOG, "Continue with selected"), timeout=3)
        return True

    @staticmethod
    def set_level(context, n, level):
        x, y = grace_box(n)
        base = run_start.GRACE_BASE[n - 1]
        want = run_start.LEVEL_MULT[level]
        for _ in range(4):
            price = number(text(context, screen(context), [x + 112, y - 3, 80, 28]))
            shown = price // base if price and price % base == 0 else None
            if shown == want:
                return True
            if shown not in (1, 2, 3):
                time.sleep(0.5)
                continue
            button = want if want > 1 else shown  # back to base = tap the lit button again
            page_guard(context, "StarlightPage")
            tap(context, x + (50 if button == 2 else 132), y + 203)
        return False


@AgentServer.custom_action("ConfirmStarlight")
class ConfirmStarlight(CustomAction):
    """Set Convert Starlight to Cost per the plan, press Confirm."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        want = run_start.resolve_plan(run["settings"], run["team"], "starlight")["convert_leftover"]
        for _ in range(4):
            image = screen(context)
            # The line under the checkbox: "Any unspent Starlight will be added ..." when off,
            # "Coverts any remaining Starlight ..." when on.
            note = text(context, image, STARLIGHT_NOTE)
            on = True if has(note, "remaining") else False if has(note, "unspent") else None
            if on == want:
                if want:
                    run["starlight_unspent"] = 0
                # The dialog stays up behind the game's Connecting; MirrorHub would confirm it twice.
                tap_then(context, 738, 530, shows(context, STARTING_GIFT_HEADER, "Selected E"), timeout=4)
                return True
            if on is not None:
                tap_then(context, 727, 363, lambda im: has(text(context, im, STARLIGHT_NOTE), "remaining" if want else "unspent"))
        return stuck("could not set Convert Starlight to Cost")


@AgentServer.custom_action("PickStartingGift")
class PickStartingGift(CustomAction):
    """Open the team keyword's cabinet, take its gifts in order until Select n/m is full, press Select."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        keyword = team["keyword"]
        self.set_gift_search(context, bool(team["gift_search"]["enabled"] and team["gift_search"]["gifts"]))
        if not self.full(context):
            for _ in range(3):
                image = page_guard(context, "StartingGift")
                label = next((b for t, b in ocr(context, image, [145, 145, 590, 430]) if compact(t) == compact(keyword)), None)
                if label:
                    break
                scroll(context, 440, 480, 0, -250)  # Pierce and Blunt sit below the fold
            else:
                return stuck(f"no {keyword} cabinet")
            x, y, w, h = label
            tap(context, x + w // 2, y + h // 2 + 75, wait=0)
            still(context, timeout=1.5)  # the cabinet's gifts slide in
            for gift_y in (262, 370, 475):
                before = self.count(context, page_guard(context, "StartingGift"))
                if before and before[0] == before[1]:
                    break
                tap_then(context, 970, gift_y, lambda im: self.count(context, im) != before, timeout=1.5)
            still(context, timeout=1.0)  # Live: Select ignores a tap in the picking animation
        # Live: the first tap on Select right after picking is often ignored.
        header, popup = shows(context, STARTING_GIFT_HEADER, "Selected"), shows(context, GET_TITLE, "GET")
        for _ in range(4):
            page_guard(context, "StartingGift")
            if tap_then(context, 1080, 587, lambda im: popup(im) or not header(im), timeout=2.5) is not None:
                log(f"starting gift: {keyword}")
                return True
        return stuck("Select did not take the starting gift")

    @staticmethod
    def set_gift_search(context, want):
        """Turn the Activate Gift Search switch on only for a team with gifts to search (spec 03 section 5).

        Live 2026-10-16: off skips the E.G.O Gift Search page; the next run keeps the switch (back on after a restart).
        An unread switch is left alone: the search page, if it comes, refuses or picks anyway.
        """
        def switch(image):
            shown = text(context, image, [1100, 145, 85, 28])
            return False if has(shown, "OFF") else True if has(shown, "ON") else None

        for _ in range(3):
            on = switch(page_guard(context, "StartingGift"))
            if on is None or on == want:
                return
            tap_then(context, 1140, 158, lambda im: switch(im) == want, timeout=1.5)
            log(f"Activate Gift Search: {'on' if want else 'off'}")

    @staticmethod
    def count(context, image=None):
        """The (n, m) strings of Select n/m, or None."""
        m = re.search(r"(\d)\s*/\s*(\d)", text(context, screen(context) if image is None else image, [990, 565, 190, 45]))
        return m.groups() if m else None

    @staticmethod
    def full(context):
        """Select n/m reads n == m."""
        n = PickStartingGift.count(context)
        return bool(n) and n[0] == n[1]


@AgentServer.custom_action("GiftGet")
class GiftGet(CustomAction):
    """Close the E.G.O Gift GET! popups, one after another, until none is up (#115).

    A search or a cabinet that gives n gifts pops n windows. The name plate tells the next window from the one
    just closed, which is closed once the screen is still, with no pass of MirrorHub in between. Taps are never
    sent ahead: under the last window lies the page the gifts came from (the search grid or the starting gift
    page), where one would pick; a window fading out still shows its title over a half-drawn plate.
    A window still up with the same name after the wait: the tap was lost, and MirrorHub looks again.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        title = shows(context, GET_TITLE, "GET")
        image = screen(context)
        for _ in range(GIFT_WINDOWS):
            before = text(context, image, GET_NAME).strip()

            def closed(im):
                if not title(im):
                    return True
                now = text(context, im, GET_NAME).strip()
                return bool(before and now and now != before)
            image = tap_then(context, *GET_CONFIRM, closed, timeout=2)
            if image is not None and title(image):
                image = still(context, timeout=1)
            if image is None or not title(image):
                return True
        return True


GIFT_WINDOWS = 6  # GET! windows GiftGet closes in one go: a cabinet's gifts or a search's 3, with room to spare


# E.G.O Gift Search page (live 2026-10-16, 1.117.0). Tabs left to right, 62 px apart.
GRID_SWITCH_TIMEOUT = 5  # s a tab's gifts may take to show; they change in well under that, an empty tab pays it all
SEARCH_TABS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
SEARCH_COUNT = [1010, 550, 190, 50]  # "Select 0/3"
SEARCH_OWNED = ([935, 26, 120, 38], [1065, 26, 80, 38])  # "1315-270" and "1045"
SEARCH_PANEL_Y = (205, 316, 427)  # name lines of the Selected E.G.O Gift panel's 3 entries
SEARCH_SELECT = (1100, 575)
SEARCH_REFUSE = (922, 575)
SEARCH_DIALOG = [400, 315, 480, 60]  # "Consume 70 Starlight to search and obtain these E.G.O Gifts?"
FORGO_DIALOG = [480, 330, 320, 35]  # Refuse Gift's "Forgo ...?"
SEARCH_DIALOG_BUTTONS = {"cancel": (513, 495), "confirm": (765, 495)}
# A gift's icon (image/GiftSearch/<id>.png) scores 0.71-0.97 on its own cell, other cells up to ~0.75 (2026-10-16):
# low enough to try a dark icon; the panel name check undoes a lookalike.
ICON_MIN = 0.65
GRID_MID = 420  # a dragged-to gift's row lands here: whole rows above and below it


def gift_data():
    """data/gift_search.json: the observation table, tab by tab, in page order."""
    return json.loads((RESOURCE / "base" / "data" / "gift_search.json").read_text(encoding="utf-8"))["gifts"]


@AgentServer.custom_action("GiftSearch")
class GiftSearch(CustomAction):
    """E.G.O Gift Search (spec 03 section 5): the team's gifts in its order until Select n/m is full, then Select.

    Off, no gifts, or none of them found: Refuse Gift (the Forgo dialog is MirrorHub's). Gifts cost owned
    starlight; choosing them in the settings is the user's consent (#54). A gift is found by its icon among
    the cells of its tier (pick), tapped once, and kept only when the panel names it.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        search = run["team"]["gift_search"]
        wanted = search["gifts"] if search["enabled"] else []
        names = [g["name"] for g in wanted]
        if has(text(context, screen(context), SEARCH_DIALOG), "Consume"):
            # left open by an earlier try: check the picks again
            tap_then(context, *SEARCH_DIALOG_BUTTONS["cancel"], lambda im: not has(text(context, im, SEARCH_DIALOG), "Consume"), timeout=1.5)
        tried, dropped = [], 0
        while True:
            image = page_guard(context, "GiftSearch")
            count = gift_search.select_count(text(context, image, SEARCH_COUNT))
            if count is None:
                return True  # fading in or out: let MirrorHub look again
            chosen = self.chosen(context, image, names)
            unwanted = [k for k, c in enumerate(chosen) if c not in names]
            if unwanted and dropped < 3:
                # Left over from a tap that missed: tapping its panel entry unselects it (live 2026-10-16).
                log(f"gift search: unselecting {chosen[unwanted[0]]}, not in the team's list")
                tap_then(context, 1000, SEARCH_PANEL_Y[unwanted[0]] + 45, lambda im: self.chosen(context, im, names) != chosen, timeout=1.5)
                dropped += 1
                continue
            gift = gift_search.next_gift(wanted, chosen, tried, count)
            if gift is None:
                break
            tried.append(gift)
            if not self.pick(context, gift):
                log(f"gift search: {gift['name']} ({gift['keyword']} tier {gift['tier']}) not picked: not on the page, owned or unaffordable")
        if not chosen or unwanted:
            log("gift search: refused" + (f", {chosen} would not unselect" if unwanted else ""))
            tap_then(context, *SEARCH_REFUSE, shows(context, FORGO_DIALOG, "Forgo"), timeout=2)
            return True
        owned = gift_search.owned_starlight(*(text(context, image, roi) for roi in SEARCH_OWNED))
        # Select asks "Consume N Starlight to search and obtain these E.G.O Gifts?"; the GET! windows are MirrorHub's.
        for _ in range(3):
            page_guard(context, "GiftSearch")
            asked = tap_then(context, *SEARCH_SELECT, shows(context, SEARCH_DIALOG, "Consume"), timeout=2)
            if asked is not None:
                ask = text(context, asked, SEARCH_DIALOG)
                break
        else:
            return stuck("Select did not ask to consume starlight")
        # Live (run13c): the dialog reads while it still drops in on its chains, and a tap then does nothing.
        page_guard(context, "GiftSearch", image=still(context, timeout=1.5))  # also under its Consume dialog (maatools: GiftSearchConfirm.png)
        # The search page reads through the dialog and again before the first window: leaving early would buy twice.
        tap_then(context, *SEARCH_DIALOG_BUTTONS["confirm"], shows(context, GET_TITLE, "GET"), timeout=4)
        price = number(ask.split("Starlight")[0])
        # The Owned box counts the Starlight left unspent on the starlight page (#73): not the account's before the run.
        before = owned[0] - RUN.get("starlight_unspent", 0) if owned else None
        after = before - price if before is not None and price is not None else None
        log(f"gift search: bought {', '.join(chosen)} for {price} owned starlight; owned starlight {before} -> {after}")
        run["gift_search"] = {"gifts": chosen, "starlight": price, "owned_before": before, "owned_after": after}
        return True

    @staticmethod
    def chosen(context, image, names):
        """The gifts the Selected E.G.O Gift panel lists, as the team's names where they match."""
        texts = [text(context, image, [922, y, 270, 34]) for y in SEARCH_PANEL_Y]
        return [run_start.match_pack(t, names) or t for t in texts if t.strip()]

    @staticmethod
    def pick(context, gift):
        """Select gift: find its icon among its tier's cells, tap it once, and check the panel names it.

        The observation table's order says how far down the tab the gift sits, so the tab is dragged
        straight there; when the icon is not on that screen (the account lacks a gift above it, or the drag
        fell short) the tab is searched from the top, screen by screen. Cells are never tapped to read names.
        """
        tab = [g for g in gift_data() if g["keyword"] == gift["keyword"]]
        entry = next((g for g in tab if g["tier"] == gift["tier"] and run_start.match_pack(g["en"], [gift["name"]])), None)
        if entry is None:
            log(f"gift search: {gift['name']} is not in data/gift_search.json")
            return False
        start = time.time()
        GiftSearch.open_tab(context, gift["keyword"])
        y = gift_search.expected_cell(tab, entry["en"])[1]
        guessed = y > gift_search.LAST_Y
        if guessed:
            GiftSearch.scroll(context, y - GRID_MID)
            # Line the grid up by the section headers on screen, not by the distance dragged.
            y = gift_search.cell_y(tab, entry["en"], gift_search.section_headers(screen(context)))
            if y is not None and abs(y - GRID_MID) > 140:
                GiftSearch.scroll(context, y - GRID_MID)
        for _ in range(12):
            image = page_guard(context, "GiftSearch")
            cells = gift_search.gift_cells(image)
            for k, (score, x, y) in enumerate(GiftSearch.icon_scores(context, image, entry["id"], [c for c in cells if c[2] == gift["tier"]])[:2]):
                if score < ICON_MIN:
                    break
                if k:
                    image = page_guard(context, "GiftSearch")  # the first candidate's tap and wait lie behind this one
                if GiftSearch.tap_and_check(context, image, x, y, gift["name"]):
                    log(f"gift search: {gift['name']} selected in {time.time() - start:.1f} s (icon {score:.2f})")
                    return True
            if guessed:
                guessed = False
                log(f"gift search: {gift['name']} is not where the table puts it: searching {gift['keyword']} from the top")
                GiftSearch.open_tab(context, gift["keyword"])
                continue
            if any(tier < gift["tier"] for _, _, tier in cells):
                return False  # the tiers below have started: the wanted tier is done
            GiftSearch.scroll(context, 300)
            if not grid_moved(image, screen(context)):
                return False  # the end of the tab
        return False

    @staticmethod
    def open_tab(context, keyword):
        """Open keyword's tab at its top: switching tabs resets the scroll (live 2026-10-16), so via a neighbour."""
        i = SEARCH_TABS.index(keyword)
        for x, attempts in ((113 + 62 * (i + 1 if i == 0 else i - 1), 1), (113 + 62 * i, 2)):
            # Live (run13): the tab lights up at once, its gifts a few looks later; a tap sent before then was
            # lost, or the grid read showed the last tab's gifts. Wait for the gifts to change, then the fade.
            # Live 2026-10-20 (#190): Keywordless's grid took over 1.6 s, so a 1 s wait read Blunt's gifts.
            before = page_guard(context, "GiftSearch")
            for attempt in range(attempts):  # the wanted tab's tap may be lost: the grid then never moves, so tap it again
                if attempt:
                    page_guard(context, "GiftSearch")  # the retry comes after GRID_SWITCH_TIMEOUT: the page may be gone by then
                if tap_then(context, x, 190, lambda im: grid_moved(before, im), timeout=GRID_SWITCH_TIMEOUT) is not None:
                    break
            else:
                log(f"gift search: the grid did not change after tapping the tab at x={x}")
            still(context, timeout=1)

    @staticmethod
    def scroll(context, distance):
        """Drag the grid up by distance px (down when negative), in strokes that stay inside it.

        Dragged past the tab's end, the grid springs back after the lift: wait that out.
        """
        page_guard(context, "GiftSearch")  # the tab's tap and fade lie between the last look and this drag
        while abs(distance) > 20:
            step = max(-300, min(distance, 300))
            scroll(context, 430, 590 if step > 0 else 290, 0, -step)
            distance -= step
        time.sleep(0.5)

    @staticmethod
    def icon_scores(context, image, gid, cells):
        """[(score, x, y)] best first: the gift's icon (data/gift_search.json id) matched on each cell, TM_CCORR_NORMED."""
        node = {"recognition": "TemplateMatch", "template": f"GiftSearch/{gid}.png", "threshold": 0.0, "method": 3, "green_mask": True}
        out = []
        for x, y, _ in cells:
            detail = context.run_recognition("GiftIcon", image, {"GiftIcon": {**node, "roi": [x - 40, y - 40, 80, 80]}})
            out.append((detail.best_result.score if detail and detail.best_result else 0.0, x, y))
        return sorted(out, reverse=True)

    @staticmethod
    def tap_and_check(context, image, x, y, name):
        """Tap a cell; True when the panel's new entry is name, else tap it off again (a lookalike icon)."""
        before = GiftSearch.chosen(context, image, [])
        after = tap_then(context, x, y, lambda im: GiftSearch.chosen(context, im, []) != before, timeout=1)
        new = [t for t in GiftSearch.chosen(context, after if after is not None else screen(context), []) if t not in before]
        if new and run_start.match_pack(new[0], [name]):
            return True
        if new:
            log(f"gift search: the icon match picked {new[0]}, not {name}: unselected")
            page_guard(context, "GiftSearch")  # the tap above waited up to 1 s
            tap_then(context, x, y, lambda im: GiftSearch.chosen(context, im, []) == before, timeout=1)
        return False


def theme_pack_marks(settings, team):
    data = yaml.safe_load((RESOURCE / "base" / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))
    plan = team["theme_pack_plan"]
    marks = data["default_plan"] if plan == "default" else next(p["marks"] for p in settings["theme_pack_plans"] if p["id"] == plan)
    return data["packs"] + list(marks), marks or {}


def pack_titles(context, image):
    """Cards left to right as (x centre, [text lines top to bottom]).

    All-caps lines are CAUTION stamps or CLEAR BONUS, never a title; the LIMBUS COMPANY logo
    above the title may still slip in as the top line (run_start.match_card drops it).
    """
    return columns([r for r in ocr(context, image, PACK_TITLES) if re.search(r"[a-z]", r[0])])


def columns(results):
    """OCR results grouped into cards left to right as (x centre, [lines top to bottom]); lines within 80 px are one card."""
    lines = sorted((x + w // 2, y, t) for t, (x, y, w, h) in results)
    groups = []
    for line in lines:
        if groups and line[0] - groups[-1][-1][0] < 80:
            groups[-1].append(line)
        else:
            groups.append([line])
    return [(g[0][0], [t for _, _, t in sorted(g, key=lambda line: line[1])]) for g in groups]


@AgentServer.custom_action("PickThemePack")
class PickThemePack(CustomAction):
    """Set this floor's difficulty, then pull the best pack: prefer > neutral > avoid, leftmost first (spec 03 sections 2, 6)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        m = re.search(r"floor\s*(\d)", normalize(text(context, image, [480, 100, 320, 40])))
        if not m:
            return True  # page fading in or out: let MirrorHub look again
        floor = int(m[1])
        if floor != RUN.get("floor"):
            RUN.update(floor=floor, map_misses=0)  # a new floor's map gets a fresh retry quota (spec 06)
            if "floor_limit" in RUN:  # a run the bot started: the floor time limit starts over
                RUN["deadline"] = time.time() + RUN["floor_limit"]
        want = None if run["difficulty"] is None else run_start.hard_wanted(floor, run["difficulty"] == "hard", run["team"]["hard_from_floor"])
        if not self.set_difficulty(context, floor, want):
            return stuck(f"floor {floor} difficulty did not switch to {'HARD' if want else 'NORMAL'}")

        names, marks = theme_pack_marks(run["settings"], run["team"])
        setting = run["settings"]["run"]["theme_pack_refresh"]
        seen = None
        for used in range(10):  # ponytail: stop when a refresh changes nothing; read `Refresh n/m` if that misfires
            cards = pack_titles(context, page_guard(context, "ThemePack"))
            if not cards:
                return stuck("no theme pack titles read")
            ranked = run_start.rank_packs([lines for _, lines in cards], names, marks)
            log(f"floor {floor} packs: " + ", ".join(f"{t} ({r})" for t, r in ranked))
            ranks = [r for _, r in ranked]
            titles = [t for t, _ in ranked]
            if not run_start.refresh_wanted(ranks, setting, used) or titles == seen:
                break
            seen = titles
            tap(context, 1083, 47, wait=3)
        i = run_start.pick_pack(ranks)
        x = cards[i][0]
        log(f"floor {floor}: pull {ranked[i][0]!r}")
        swipe(context, x, 330, x, 650, ms=600, wait=0)
        # The page fades out slowly; do not let MirrorHub pull twice.
        until(context, lambda im: not has(text(context, im, [480, 100, 320, 40]), "FLOOR"), timeout=9)
        return True

    @staticmethod
    def set_difficulty(context, floor, want):
        def label(image):
            shown = text(context, image, [830, 30, 160, 35])
            return True if has(shown, "HARD") else False if has(shown, "NORMAL") else None

        for _ in range(4):
            hard = label(page_guard(context, "ThemePack"))
            if hard is None:
                until(context, lambda im: label(im) is not None, timeout=1)
                continue
            move = run_start.difficulty_move(floor, hard, want)
            if move is None:
                if want is not None and hard != want:
                    log(f"floor {floor} stays HARD: a run never goes back to NORMAL")
                log(f"floor {floor}: {'HARD' if hard else 'NORMAL'}")
                RUN["floor_hard"] = hard  # the map does not show it; RouteMap's weights need it
                return True
            # The arrows sit left of HARD, right of NORMAL; switching re-rolls the packs.
            log(f"floor {floor}: switch to {move.upper()}")
            tap_then(context, 965 if move == "hard" else 850, 46, lambda im: label(im) == (move == "hard"), timeout=2.5)
            still(context, timeout=1.5)  # the packs re-roll
        return False


# Map page (spec 03 section 7). Offsets are from the MapBus template's top-left corner.
# The bus at the far left: the screen shows it and four columns (#111; the user's hard-mode capture, bus at 47, 311).
# Panned ~70 px down from rest (bus at 446, 248): top-row badges clear the resource bar.
BUS_HOME = (50, 320)
BUS_REST = (446, 248)
SLOT = (279, 37)  # middle-row slot centre; map_route.ROW_DY gives the other rows
LINKS = {
    "up": ("MapLinkUp", (90, -115, 110, 110)),
    "mid": ("MapLinkMid", (95, -10, 110, 80)),
    "down": ("MapLinkDown", (85, 85, 110, 110)),
}
BUS_PROBE = 1.0  # s a first tap on the bus waits for the node panel (#130)
BUS_LINK = 60  # line_contrast of a lit link from the bus; links between other nodes read up to ~50
MARKS = {  # node -> (mark, roi around the slot centre)
    "MapNodeBoss": ("boss", (-40, -40, 80, 80)),
    "MapNodeFocusedHex": ("focused", (-80, -60, 160, 120)),
    "MapNodeFocusedRound": ("focused", (-75, -60, 150, 120)),
    "MapNodeCost": ("cost", (-60, -80, 120, 60)),
    "MapNodeGift": ("gift", (-60, -80, 120, 60)),
    "MapNodeEvent": ("event", (-60, -60, 120, 120)),
    "MapNodeShop": ("shop", (-60, -60, 120, 120)),
}
FEATURE_MATCH = {"MapNodeFocusedHex", "MapNodeEvent", "MapNodeShop"}  # the pipeline's FeatureMatch nodes
FEATURE_PAD, FEATURE_ALIGN = 64, 32  # px of the screen kept around a FeatureMatch roi; grid of the cut's corner
ENTER = (1133, 543)
BACK_KEY = 4  # Android's back key (L1's too): closes the node panel
MAP_RETRIES = 3  # RouteMap calls per floor that may enter nothing before the map is stuck
MAP_LOOKS = 4  # looks, 1 s apart, for a linked slot before the fallback taps
PANEL_REWARDS = [700, 495, 110, 30]  # the "Clear Rewards" label
PANEL_COST = [730, 545, 40, 35]  # the number by its Cost coin


def seen(context, image, node, roi=None):
    """The node's hit on image, its roi overridden and clipped to the screen; None on a miss.

    #156: FeatureMatch runs SIFT over the whole image it is handed, its roi only masking the keypoints:
    ~0.18 s per template on a full screen whatever the roi (41 map captures offline, #163). So a FEATURE_MATCH node gets the roi with a
    FEATURE_PAD margin cut out (corner on a FEATURE_ALIGN grid, as SIFT's octaves halve), the box put back.
    Only detail.box is put back: best_result and the result lists stay in the cut-out's coordinates.
    """
    override, dx, dy = None, 0, 0
    if roi:
        x, y, w, h = roi
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(1280, x + w), min(720, y + h)
        if node in FEATURE_MATCH:
            dx, dy = (max(0, v - FEATURE_PAD) // FEATURE_ALIGN * FEATURE_ALIGN for v in (x0, y0))
            image = image[dy:y1 + FEATURE_PAD, dx:x1 + FEATURE_PAD]
        override = {node: {"roi": [x0 - dx, y0 - dy, x1 - x0, y1 - y0]}}
    detail = context.run_recognition(node, image, override)
    if not detail or not detail.hit:
        return None
    if dx or dy:
        detail.box = Rect(detail.box[0] + dx, detail.box[1] + dy, detail.box[2], detail.box[3])
    return detail


def node_marks(context, image, cx, cy):
    """The marks seen around the map node centred at (cx, cy): {mark: hit}.

    The shop is also looked for by its icon's shape alone (shop_icon) where nothing says a fight or the boss.
    """
    marks = {mark: hit for n, (mark, (ox, oy, w, h)) in MARKS.items() if (hit := seen(context, image, n, (cx + ox, cy + oy, w, h)))}
    if not marks.keys() & {"boss", "focused", "cost", "shop"} and (hit := shop_icon(context, image, cx, cy)):
        marks["shop"] = hit
    return marks


def shop_icon(context, image, cx, cy):
    """The hit of the shop's icon (MapNodeShopIcon) around the node centred at (cx, cy), whatever the pack's colours.

    The icon takes the theme pack's hue: cyan and orange packs (live 2026-10-18) matched none of the colour
    templates. TemplateMatch CCOEFF on the brightness alone (max over the channels) is blind to hue and to the
    pack's brightness: the shop scored 0.49-1.0 on 12 packs' captures, anything else 0.31 at most.
    """
    ox, oy, w, h = MARKS["MapNodeShop"][1]
    window = image[max(0, cy + oy):cy + oy + h, max(0, cx + ox):cx + ox + w]
    if window.shape[0] < 40 or window.shape[1] < 70:
        return None
    grey = np.repeat(window.max(axis=2)[..., None], 3, axis=2)
    return seen(context, grey, "MapNodeShopIcon", (0, 0, window.shape[1], window.shape[0]))


def node_at(context, image, cx, cy, marks=None, costs=True):
    """The type of the map node centred at (cx, cy), by its marks (map_route.node_type).

    No mark at all where the badges (80 px above the centre) sit under the resource bar: unknown, not an
    event; a fight's Cost coin may be hidden there (the top row with the map at rest).
    #91: Risky has no template and its Cost coin alone read as a battle. With costs, a coin alone whose
    number reads as none of the battle costs is taken for Risky; an unread number leaves it a battle.
    Only the column next to the bus is read so: past it the badges are dim (offline, MirrorMap.png's
    85 two columns out read 8). A planned slot is read again once next to the bus (RouteMap.follow).
    """
    marks = node_marks(context, image, cx, cy) if marks is None else marks
    if not marks and cy - 80 < 60:
        return "unknown"
    kind = map_route.node_type(set(marks))
    if kind == "battle" and costs:
        cost = coin_number(context, image, marks["cost"].box)
        if cost is not None and cost not in map_data()["battle_costs"]:
            log(f"map: a Cost coin alone at {cx}, {cy} reads {cost}, no battle cost: risky")
            kind = "risky"
    return kind


def coin_number(context, image, box):
    """The number printed beside a map node's Cost coin (box), or None when none reads (#91).

    Offline on 13 nodes of 7 captures: OCR of the bare badge read 75 as 25 or 5; of the bright,
    near-white digits cut out (as order_marks does) every battle's 75 or 85 right, dim ones too.
    A 3-digit number may lose its first digit (375 read 75): only fights carrying 3-digit costs do.
    A single digit is a part read: None.
    """
    x, y, w, _ = box
    part = image[max(0, y + 8):y + 38, max(0, x + w - 8):x + w + 32]
    mask = (part.max(axis=2) > 170) & (saturation(part) < 90)
    plain = np.where(mask[..., None], 0, 255).astype(np.uint8).repeat(3, axis=2)
    found = re.sub(r"\D", "", text(context, plain, [0, 0, plain.shape[1], plain.shape[0]], only_rec=True))
    return int(found) if len(found) >= 2 else None


def map_data():
    return yaml.safe_load((RESOURCE / "base" / "data" / "map_weights.yaml").read_text(encoding="utf-8"))


def map_weights(context):
    run = current_run(context)
    hard = run.get("floor_hard", run["difficulty"] == "hard")
    return map_data()["hard" if hard else "normal"]


def enter_node(context):
    """On the node selection panel: log its Clear Rewards, press Enter until the panel is gone."""
    # Only logged: events show no Clear Rewards, a shop shows the next boss's (spec 03 section 7).
    image = screen(context)
    cost = number(text(context, image, PANEL_COST)) if has(text(context, image, PANEL_REWARDS), "Rewards") else None
    log(f"node panel: Clear Rewards Cost {cost}")
    RUN.pop("shop", None)  # a shop left without its Leave (#118): the next shop is a new visit
    for _ in range(3):
        tap(context, *ENTER, wait=0)
        if until(context, lambda im: not seen(context, im, "MapNodePanel")) is not None:
            log("entered the node")
            until(context, lambda im: not seen(context, im, "MirrorMap"), timeout=3)  # the map fades out
            return True
    return stuck("Enter on the node panel did nothing")


@AgentServer.custom_action("EnterNode")
class EnterNode(CustomAction):
    """The node selection panel is already up (e.g. after a restart): enter the node, or forfeit the run."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("forfeit"):  # backed out of the formation page (#137): the panel may still be up
            return forfeit(context)
        return enter_node(context)


@AgentServer.custom_action("RouteMap")
class RouteMap(CustomAction):
    """Pick the next node and enter it (spec 03 section 7).

    Slots linked to the bus (its lit line or a chevron on it) are typed by their marks, ranked by
    map_route.rank over the columns on screen and tapped in that order until the node panel (MapNodePanel)
    shows. After them come the fallbacks: the bus (a node reached but not entered; first after a restart or a
    recovery, #88), then the slots not tried yet. No bus on screen: the map is dragged about for it (#61).
    Nothing taking a tap spends one of the floor's map retries; when they run out, the map is stuck (spec 06);
    with no bus found at all, at once at L2. A map zoomed in on the bus is reset first (unzoom); one that stays so goes
    to L2 at once too, or into the node when its panel stays up (L2 starts from the map's gear).
    When the best path's first node is entered, the rest of the path is the floor's plan: the next calls
    follow it (follow) until it is used up or does not fit the map.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("forfeit"):
            return forfeit(context)
        if still(context) is None:
            return True  # still fading in or out: let MirrorHub look again
        if not self.unzoom(context):  # its slots sit off where the offsets put them: L2 puts the map back
            if seen(context, screen(context), "MapNodePanel"):  # L2 needs the map: enter the node instead
                return enter_node(context)
            return stuck("the map stays zoomed in on the bus", level=2)
        if self.follow(context):
            return enter_node(context)
        RUN.pop("map_plan", None)
        for _ in range(MAP_LOOKS):  # live: right after a floor's theme pack, the map shows before its bus and links
            if still(context) is None:
                return True  # still fading in or out: let MirrorHub look again
            image, bus = self.find_bus(context)
            bx, by = bus or BUS_REST  # no bus found: assume the map at rest
            slots = self.read_slots(context, image, bx, by) if bus else {}
            if slots:
                break
            time.sleep(1)
        if not bus and self.search_bus(context):  # #61: the map dragged off by hand
            image, bus = self.find_bus(context)
            bx, by = bus or BUS_REST
            slots = self.read_slots(context, image, bx, by) if bus else {}
        log("map: column 1: " + (", ".join(f"{r} {t} ({'?' if n is None else n} onward)" for r, (t, n) in slots.items()) or "no linked slot read"))
        ahead = self.read_ahead(context, image, bx, by, slots) if slots else []
        read = [t for column in (slots, *ahead) for t, _ in column.values()]
        map_route.shop_before_boss(slots, ahead)  # #146: the shop's icon takes the theme pack's colours
        if read != [t for column in (slots, *ahead) for t, _ in column.values()]:
            log("map: the column before the boss is the shop")
        weights = map_weights(context)
        order = map_route.rank(slots, weights, ahead)
        steps = None
        if order:
            score, path = map_route.paths(slots, weights, ahead)[order[0]]
            nodes = [c[r][0] for r, c in zip(path, (slots, *ahead))]
            log(f"map: path {' > '.join(f'{r} {t}' for r, t in zip(path, nodes))}, score {score}")
            steps = map_route.steps(path, nodes)
            if steps is None:  # #212: a path no link joins; take its first node and read the map again after
                log("map: the path steps two rows; no plan")

        def centre(row):
            return bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]

        ranked = [(f"{r} {slots[r][0]}", centre(r)) for r in order]
        on_bus = [("the bus", (bx + 22, by + 37))]
        # #88: after a restart or a recovery the bus may stand on a node not entered yet; its own tap opens it.
        tries = ranked + on_bus if RUN.get("map_entered") else on_bus + ranked
        tries += [(f"{r} slot", centre(r)) for r in map_route.ROWS if r not in order]
        # #130: a bus tap on a node already entered shows nothing; a panel shows within ~0.5 s, so that probe is short.
        probe = not RUN.get("map_entered")
        for name, (x, y) in tries:
            page_guard(context, "MirrorMap")
            tap(context, x, y, wait=0)
            if until(context, lambda im: seen(context, im, "MapNodePanel"), timeout=BUS_PROBE if probe and name == "the bus" else 2.0) is not None:
                log(f"map: take {name}")
                if steps is not None and (x, y) == ranked[0][1]:  # the path's first node: follow the rest
                    RUN["map_plan"] = {"floor": RUN.get("floor"), "steps": steps}
                RUN["map_entered"] = True
                return enter_node(context)
        if not bus:  # #61: L2's To Window and Resume put the map back; L1's back key does nothing here
            return stuck("no bus on the map, even after dragging it about", level=2)
        RUN["map_misses"] = RUN.get("map_misses", 0) + 1
        if RUN["map_misses"] >= MAP_RETRIES:
            return stuck(f"no node on the map took a tap, {MAP_RETRIES} times this floor")
        log("map: no node took a tap; MirrorHub looks again")
        return True

    @staticmethod
    def unzoom(context):
        """Whether the map is at its default zoom, after resetting it if it was zoomed in on the bus (#194).

        Backing out of a node's formation leaves the camera zoomed in ~1.8x on the bus (MapBusZoomed), where
        it stays (#162: 32 s, 5 drags and 4 taps changed nothing). The node panel zooms in the same way and
        closing it puts the map back at rest (#111, 2026-10-18). The bus stands on the node backed out of, so
        its tap opens that panel; closed, the bus's node is known to take a tap: it goes first (#88).
        """
        image = screen(context)
        if seen(context, image, "MapBus") or not (zoomed := seen(context, image, "MapBusZoomed")):
            return True
        log("map: zoomed in on the bus; opening and closing its node panel")
        x, y, w, h = zoomed.box
        page_guard(context, "MirrorMap", image=image)
        if tap_then(context, x + w // 2, y + h // 2, lambda im: seen(context, im, "MapNodePanel")) is None:
            log("map: the zoomed bus took no tap")
            return False
        context.tasker.controller.post_click_key(BACK_KEY).wait()
        if until(context, lambda im: seen(context, im, "MapBus"), timeout=3) is None:
            log("map: still zoomed in after the back key")
            return False
        RUN["map_entered"] = False
        RUN.pop("map_plan", None)  # its next step starts past the bus's node: read the map again
        return True

    @staticmethod
    def find_bus(context):
        """A screenshot and the bus's top-left in it, after panning the bus to BUS_HOME."""
        for attempt in range(4):
            image = screen(context)
            bus = seen(context, image, "MapBus")
            if not bus:
                return image, None
            bx, by = bus.box[0], bus.box[1]
            dx, dy = BUS_HOME[0] - bx, BUS_HOME[1] - by
            if abs(dx) <= 30 and abs(dy) <= 25 or attempt == 3:
                return image, (bx, by)
            # Look again after each pan. Start on map background: between the first and second columns,
            # between the middle and bottom rows.
            scroll(context, min(bx + SLOT[0] + map_route.COLUMN_DX // 2, 1100), by + SLOT[1] + 106, dx, dy)
            time.sleep(0.5)

    @staticmethod
    def search_bus(context):
        """Drag the map about, looking for the bus after each drag; whether it showed (#61).

        Live 2026-10-16: a map dragged by hand left the bus off the top of the screen. The drags go
        250 px down and up, 400 px right and left of where the map was, then back.
        """
        at = (0, 0)
        for to in ((0, 250), (0, -250), (400, 0), (-400, 0), (0, 0)):
            dx, dy = to[0] - at[0], to[1] - at[1]
            page_guard(context, "MirrorMap")
            scroll(context, 640 - dx // 2, 340 - dy // 2, dx, dy)
            time.sleep(0.5)
            at = to
            if seen(context, screen(context), "MapBus"):
                log(f"map: the bus showed after dragging the map {to}")
                return True
        return False

    @staticmethod
    def read_slots(context, image, bx, by):
        """{row: (node type, routes onward or None)} for the slots linked to the bus."""
        v = image.max(axis=2)
        slots = {}
        for row in map_route.ROWS:
            if RouteMap.linked(context, image, bx, by, row):
                cx, cy = bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]
                slots[row] = (node_at(context, image, cx, cy), map_route.routes(v, cx, cy))
        return slots

    @staticmethod
    def linked(context, image, bx, by, row):
        """Whether the slot in row is linked to the bus.

        Live 2026-10-18, bus at the far left: the chevrons scored 0.75-0.84 against 0.8, the lit link
        itself 157-171 against -2 unlinked; either one counts.
        """
        node, (rx, ry, rw, rh) = LINKS[row]
        lit = map_route.line_contrast(image.max(axis=2), bx + 22, by + 37, bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row])
        return lit is not None and lit >= BUS_LINK or bool(seen(context, image, node, (bx + rx, by + ry, rw, rh)))

    @staticmethod
    def follow(context):
        """Tap the next node of this floor's planned path; whether its node panel showed (#111).

        Only that slot is read, and the map is dragged (bus to the far left) only when it sits under the
        resource bar or the buttons. False, for a full read, whenever in doubt: no plan or a used-up one,
        the slot not linked to the bus or not of the planned type (the bus not where the plan put it, or a
        misread from afar), or its tap showing no panel.
        """
        plan = RUN.get("map_plan")
        if not plan or plan["floor"] != RUN.get("floor") or not plan["steps"]:
            return False
        row, node = plan["steps"][0]
        image = screen(context)
        bus = seen(context, image, "MapBus")
        bus = bus and tuple(bus.box[:2])

        def clear(bx, by):  # the slot's node, badges included, clear of the resource bar and the buttons
            return bx + SLOT[0] + 80 <= 1200 and by + SLOT[1] + map_route.ROW_DY[row] - 80 >= 60
        if not bus or not clear(*bus):
            image, bus = RouteMap.find_bus(context)
        if not bus or not RouteMap.linked(context, image, *bus, row):
            log(f"map: planned {row} {node} not linked to the bus; reading the map again")
            return False
        bx, by = bus
        cx, cy = bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]
        kind = node_at(context, image, cx, cy)
        if kind != node:
            log(f"map: planned {row} {node} reads {kind}; reading the map again")
            return False
        page_guard(context, "MirrorMap", image=image)
        tap(context, cx, cy, wait=0)
        if until(context, lambda im: seen(context, im, "MapNodePanel")) is None:
            log(f"map: planned {row} {node} took no tap; reading the map again")
            return False
        log(f"map: follow plan {row} {node}")
        plan["steps"] = plan["steps"][1:]
        return True

    @staticmethod
    def read_ahead(context, image, bx, by, slots):
        """The columns beyond the first on screen, for map_route.rank.

        A node counts when a link into it from the column before reads (map_route.line_contrast); only rows
        next to each other link. Every node leads on, so one with no link read onward takes its brightest
        (map_route.FAINT_LINK, #212). The read ends at the screen's edge, at a column with nothing linked or
        dark (no mark and no light on any node: hard mode shows two columns), or after the boss.
        """
        dx, dy = map_route.COLUMN_DX, map_route.ROW_DY
        v, x, ahead = image.max(axis=2), bx + SLOT[0], []

        def y(row):
            return by + SLOT[1] + dy[row]
        while x + dx + 80 <= 1200:  # MapNodeFocusedHex reads 80 px either side; buttons from x 1205
            x += dx
            before, column, lit = ahead[-1] if ahead else slots, {}, False
            links = map_route.links({(r, row): map_route.line_contrast(v, x - dx, y(r), x, y(row)) or 0
                                     for r in map_route.ROWS for row in map_route.ROWS if map_route.near(r, row)})
            for row in map_route.ROWS:
                linked = {src for src, dst in links if dst == row and src in before}
                if linked:
                    marks = node_marks(context, image, x, y(row))
                    column[row] = (node_at(context, image, x, y(row), marks, costs=False), linked)
                    # A node with no mark may still be lit: a red pack's dim "?" (live 2026-10-18) reads 48-60
                    # here; hard mode's dark columns read 0.
                    lit = lit or bool(marks) or np.percentile(v[y(row) - 45:y(row) + 45, x - 45:x + 45], 90) >= 20
            if not lit:
                break
            ahead.append(column)
            log(f"map: column {len(ahead) + 1}: " + ", ".join(f"{r} {t} (from {'/'.join(sorted(n))})" for r, (t, n) in column.items()))
            if any(t == "boss" for t, _ in column.values()):
                break
        return ahead


# Formation page (spec 03 section 3). Cards are in battle.SINNERS order, two rows of six.
CARD_X = [295 + round(132.2 * i) for i in range(6)]  # card centres
CARD_ART_Y = ((180, 300), (380, 500))
CARD_NUMBER_Y = (211, 410)  # centre of the order mark on each row
CARD_TAP_Y = (290, 488)  # the card's name plate
PARTICIPANTS = [1125, 500, 100, 45]  # "10/11": selected / alive
DETAILS_BUTTON = [860, 110, 125, 30]  # reads "Details" in the card view
CLEAR_SELECTION = (1145, 479)
RESET_DIALOG = [450, 330, 380, 35]  # Clear Selection asks "Reset Deployment Order?"
RESET_CONFIRM = (767, 497)
TO_BATTLE = (1145, 588)


def card_xy(i, ys):
    return CARD_X[i % 6], ys[i // 6]


def participants(context, image):
    """(selected, alive) from Total Participants, or None when it is not readable."""
    m = re.search(r"(\d+)\s*/\s*(\d+)", text(context, image, PARTICIPANTS))
    return (int(m[1]), int(m[2])) if m else None


def saturation(image):
    """HSV S (0-255) of a BGR image."""
    hi, lo = image.max(axis=2).astype(int), image.min(axis=2).astype(int)
    return (hi - lo) * 255 // np.maximum(hi, 1)


def dead_sinners(image):
    """Sinners whose card is grey: mean S ~2 against 65+ for any living card, picked or not."""
    dead = set()
    for i, sinner in enumerate(battle.SINNERS):
        x, (y0, y1) = CARD_X[i % 6], CARD_ART_Y[i // 6]
        if saturation(image[y0:y1, x - 50:x + 50]).mean() < 30:
            dead.add(sinner)
    return dead


def order_marks(context, image):
    """{sinner: order mark or None}.

    The marks (orange SELECTED, cyan BACKUP) are cut out by colour first: OCR on the card art
    misread 4, 6 and 9 in live captures; on the mask, one line per card, it read all 22 right.
    """
    mask = (image.max(axis=2) > 200) & (saturation(image) > 120)
    plain = np.where(mask[..., None], 0, 255).astype(np.uint8).repeat(3, axis=2)
    marks = {}
    for i, sinner in enumerate(battle.SINNERS):
        x, y = card_xy(i, CARD_NUMBER_Y)
        t = text(context, plain, [x - 25, y - 23, 50, 46], only_rec=True).strip()
        marks[sinner] = int(t) if t.isdigit() else None
    return marks


FORMATION_BACK = (98, 43)  # the formation page's back arrow, top left


@AgentServer.custom_action("Formation")
class Formation(CustomAction):
    """Re-pick the deployment order, skipping the dead, then Chain To Battle! (spec 03 section 3).

    The game keeps the last battle's picks: they are read off the cards and redone only when they differ.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        # A new battle: its clock and turn count start over, also when the last VICTORY went unseen (#80).
        RUN.pop("turn", None)
        RUN.pop("battle_start", None)
        image = still(context)
        count = image is not None and participants(context, image)
        if not count:
            return True  # page fading in or out: let MirrorHub look again
        alive, need = count[1], run["team"]["min_alive"]
        RUN["alive"] = alive  # the shop's heal reads it (spec 03 section 13)
        if alive < need:  # need 0: no check
            # Like used-up wipe retries (#137): stop, or back out to the map, where RouteMap forfeits.
            reason = f"{alive} sinners alive, team {run['team']['name']!r} needs {need}"
            if run["settings"]["run"]["after_retries"] == "stop":
                return stop(context, reason)
            log(f"{reason}: forfeit the run")
            RUN["forfeit"] = True
            tap(context, *FORMATION_BACK, wait=2)
            return True
        if not has(text(context, image, DETAILS_BUTTON), "Details"):
            tap(context, 826, 125, wait=1.5)  # its » folds the details view (skills, E.G.O), which hides the order marks
            image = screen(context)
        dead = dead_sinners(image)
        if len(dead) != 12 - alive:
            log(f"formation: {12 - alive} dead by the count, grey cards {sorted(dead)}")
        order = battle.formation_order(run_start.resolve_plan(run["settings"], run["team"], "deployment_order"), dead)
        if not order:  # a short order (sinners left out) with all its sinners dead
            return stop(context, f"no sinner in team {run['team']['name']!r}'s deployment order is alive")
        if battle.formation_matches(order_marks(context, image), order):
            log(f"formation as planned, {alive} alive")
        elif not self.pick(context, order):
            return True  # pick() handed it to recovery
        for _ in range(3):
            page_guard(context, "Formation")
            tap(context, *TO_BATTLE, wait=0)
            if until(context, lambda im: not participants(context, im), timeout=3) is not None:
                return True
        return stuck("Chain To Battle! did nothing")

    @staticmethod
    def pick(context, order):
        """Clear Selection, then tap the order card by card, each tap checked by the count going up by one."""
        def count_reaches(n):
            for _ in range(6):
                count = participants(context, screen(context))
                if count and count[0] == n:
                    return True
                time.sleep(0.5)
            return False

        for _ in range(3):
            page_guard(context, "Formation")
            tap(context, *CLEAR_SELECTION, wait=1.5)
            if has(text(context, screen(context), RESET_DIALOG), "Reset Deployment"):
                tap(context, *RESET_CONFIRM)
            if count_reaches(0):
                break
        else:
            stuck("Clear Selection did not clear the formation")
            return False
        for n, sinner in enumerate(order, 1):
            for _ in range(2):  # a tap within ~1 s of the last one can be lost
                page_guard(context, "Formation")
                tap(context, *card_xy(battle.SINNERS.index(sinner), CARD_TAP_Y), wait=1.2)
                if count_reaches(n):
                    break
            else:
                stuck(f"tapping {sinner} did not pick them")
                return False
        log(f"formation re-picked: {', '.join(order)}")
        return True


# Battle (spec 03 section 8). Offsets are from the BattleTurn (Win Rate label) template's top-left.
WIN_RATE = (20, 14)
START_DISC = (-66, 26)
TURN_NUMBER = [55, 57, 45, 30]
SLOT_PORTRAIT_Y = 665  # tapping a slot's portrait swaps its lower skill and its guard skill
LOWER_Y = 577  # a slot's lower skill, at rest (while a drag is down it sits at y 665: battle.guard_chain)
# Live 2026-10-18 (#119): portrait taps 52 ms apart lost 9 of 28, 72 ms apart 1 of 28, 83-350 ms apart none
# of 168; this wait plus ~50 ms for the tap puts them 150 ms apart.
GUARD_TAP_WAIT = 0.1


def lower_x(x):
    """x of a slot's lower skill: the skill rows lean in towards the middle (x ~604) by about 6%."""
    return round(x + (604 - x) * 0.06)


def guard_score(image, x):
    """(brown, texture) at a lower skill, for battle.guard_shown; guard icons are flat brown (~(150, 100, 50) RGB)."""
    p = image[LOWER_Y - 14:LOWER_Y + 14, x - 14:x + 14].astype(int)
    b, g, r = p[..., 0], p[..., 1], p[..., 2]
    v = p.sum(axis=2)
    texture = np.abs(np.diff(v, axis=0)).mean() + np.abs(np.diff(v, axis=1)).mean()
    return float(((r > 90) & (r - g > 20) & (g - b > 10)).mean()), float(texture)


def lower_skills(context, xs, before=None, timeout=1.5):
    """The first screenshot whose lower skills at xs read as they did 0.1 s before, after every one of them
    swapped from before (battle.guard_shown tells); without before, every one shows something. The last
    screenshot after timeout s. Live (#119): a swap shows 0.1-0.6 s after the tap and fades for ~0.4 s."""
    last = [None]

    def done(image):
        now = [guard_score(image, x) for x in xs]
        steady = last[0] is not None and all(abs(a[1] - b[1]) <= 2 for a, b in zip(now, last[0]))
        last[0] = now
        changed = None not in battle.guard_shown(before, now) if before else min(t for _, t in now) > 20
        return steady and changed
    image = until(context, done, timeout=timeout, every=0.1)
    return screen(context) if image is None else image


def win_rate_on(context, image, x, y):
    """Whether the Win Rate label at (x, y) shows pressed (on): its two templates match each other at only 0.70."""
    node = {"template": "Battle/BattleTurnPressed.png", "roi": [x - 10, y - 10, 60, 49]}
    detail = context.run_recognition("BattleTurn", image, {"BattleTurn": node})
    return bool(detail and detail.hit)


def start_shown(context, image, disc):
    """Whether the START plaque hangs over the disc: the game shows it only once every slot has a skill (#145).

    The disc lights as soon as any slot is linked, so it cannot tell a chain that ended short. Live 2026-10-18:
    the plaque template scored 0.58-1.0 with it (0.58-0.66 mid-swing) and 0.20-0.35 without it on 431 screens
    of every floor, the snow maps included; it swings in 0.53-0.7 s after the drag's lift, after START works.
    """
    x, y = disc
    return seen(context, image, "BattleStart", [x - 45, y - 75, 95, 45]) is not None


def turn_started(context, image):
    """The turn plays out: the pause button is up, or the Win Rate label is gone."""
    return seen(context, image, "BattlePause") is not None or seen(context, image, "BattleTurn") is None


# Live 2026-10-18 (#145): a turn starts 0.45-0.7 s after START. Right after a drag the panel tilts back for
# ~0.15 s and the Win Rate label does not match: the first look waits START_LEAST s.
START_WAIT = 1.5
START_LEAST = 0.3
# The plaque appears tilted on the disc's right once the chain is complete, rests there ~0.3 s and swings up to
# the top: upright (template >= 0.5) 0.33-0.47 s after the panel levels, settled from 0.40-0.53 s (30 fps
# recording, 3 drags; 0.48-0.71 s after the lift in 73 drags polled by screenshot). A minimised emulator held it
# mid-swing for over 2 s, so "no plaque" is only concluded after this much more polling.
PLAQUE_WAIT = 1.5


def press_start(context, disc):
    """Press START: whether the turn starts. Pressed once more when it did not although the plaque shows
    (looked for up to PLAQUE_WAIT s: it can still be swinging in)."""
    for _ in range(2):
        tap(context, *disc, wait=0)
        if until(context, lambda im: turn_started(context, im), timeout=START_WAIT, least=START_LEAST) is not None:
            return True
        if until(context, lambda im: start_shown(context, im, disc), timeout=PLAQUE_WAIT, every=0.1) is None:
            return False
    return False


# #150: a finger held on the screen while a turn plays speeds up its E.G.O animations (user, 2026-10-18; no
# difference seen on turns without one: 5.9 s held, 6.4 s not, over 16 turns). The top-left corner held then
# touched nothing (docs/perf/2026-10-18-guard-chain-145.md); a lift there is a tap on whatever screen follows.
HOLD_SPOT = (1, 1)
HOLD_EVERY = 0.3  # s between looks, MirrorHub's rate_limit
HOLD_LIMIT = 6  # s at most per hold (a turn without E.G.O plays ~6 s): then MirrorHub (its watchdog, recovery) looks; BattlePause holds a longer turn again
# Screens that can follow a turn, besides the next turn: the finger lifts before their node acts.
BATTLE_POPUPS = ("Connecting", "RetryPopup", "PopupButton")  # template-gated: looked for while a turn plays, no OCR (#157)
BATTLE_LEFT = BATTLE_POPUPS + ("Victory", "WipeDialog", "Event", "ClaimPopup", "Loading")


def hold_turn(context):
    """Hold a finger on HOLD_SPOT while the turn plays: until the next turn waits for input, a screen of
    BATTLE_LEFT shows, the task is stopping or HOLD_LIMIT s. Always lifted on return, also on an error:
    a finger left down keeps the panel tilted and MirrorHub blind (#145)."""
    end = time.monotonic() + HOLD_LIMIT
    try:
        context.tasker.controller.post_touch_down(*HOLD_SPOT).wait()
        while time.monotonic() < end and not context.tasker.stopping:
            time.sleep(HOLD_EVERY)
            image = screen(context)
            if seen(context, image, "BattlePause"):  # playing (the Win Rate label can still match in a turn's first frames)
                if any(seen(context, image, n) for n in BATTLE_POPUPS):
                    return  # a popup over the turn (the network)
                continue
            if seen(context, image, "BattleTurn") or any(seen(context, image, n) for n in BATTLE_LEFT):
                return
    finally:
        # Fetched again: in the agent, one kept from before the looks failed its touch up with an access
        # violation (live 2026-10-20, every hold), and the finger stayed down until the next tap.
        context.tasker.controller.post_touch_up().wait()


@AgentServer.custom_action("HoldTurn")
class HoldTurn(CustomAction):
    """BattlePause: a turn playing out (after a hold timed out, a recovery or an agent restart): hold_turn."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        hold_turn(context)
        return True


# The guard chain drag, slower on each try (#145, live 2026-10-18, 12 slots). The game links a slot only if it
# draws a frame while the finger is on it; during the drag it draws 9-30 frames a second, fewer under load
# or with its window covered or minimised. 10 px moves 10 ms apart and no rest (#119) missed 7 of 88 drags
# whose frames came within 90 ms (p90) and 27 of 43 slower; a 0.03 s rest on each slot 0 of 90 and 11 of 32;
# a 0.1 s rest 14 of 14 at 9-12 frames a second (16 cores busy). A miss costs ~2 s to see and clear.
GUARD_DRAGS = ({"settle": 0.05, "dwell": 0.03, "hold": 0.05, "pause": 0.01},
               {"settle": 0.05, "dwell": 0.1, "hold": 0.1, "pause": 0.02},
               {"settle": 0.05, "dwell": 0.2, "hold": 0.1, "pause": 0.02})


@AgentServer.custom_action("PlayTurn")
class PlayTurn(CustomAction):
    """Guard or Win Rate (one tap), press the START disc, check the turn plays (spec 03 section 8, 06)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        x, y = argv.box[0], argv.box[1]
        dx, dy = x + START_DISC[0], y + START_DISC[1]
        if time.time() - RUN.setdefault("battle_start", time.time()) > recovery.BATTLE_LIMIT:
            return stuck(f"battle over {recovery.BATTLE_LIMIT // 60} min", level=2)  # skips L1 (spec 06)
        # Live 2026-10-17: the Win Rate label also matches in the first frames of a turn playing out (the
        # screen moving), and a tap in the turn's opening can do nothing: act on a still screen only.
        image = still(context, timeout=1)
        if image is None:
            return True  # moving: MirrorHub looks again
        turn = text(context, image, TURN_NUMBER, only_rec=True).strip() or None
        tries = battle.same_turn(RUN.get("turn"), turn)
        if tries[1] > 3:
            return stuck(f"turn {turn} unchanged after 3 submits")
        guarded = False
        if RUN.get("guard", 0) > 0 and tries[1] == 1:  # a turn submitted again plays as before #52
            if battle.gear_hollow(image, battle.slot_xs(x)[0] - 86, 576):
                # #127: a focused encounter. Its skills are dragged one by one onto enemy skill slots that move
                # with the camera; no chain starts from the ring. The guard turns wait for a battle that has one.
                log(f"turn {turn}: hollow left gear (focused encounter): Win Rate, guard turns kept")
            else:
                guarded = self.guard(context, x, (dx, dy))
                if not guarded:
                    log(f"turn {turn}: guard did not take, Win Rate instead")
        started = True
        if guarded:
            RUN["guard"] = battle.guard_left(RUN["guard"], guarded)
            log(f"turn {turn}: started on guard, {RUN['guard']} guard turns left")
        elif self.win_rate(context, x, y, (dx, dy), turn):
            log(f"turn {turn}: started")
        else:
            started = False
            log(f"turn {turn}: START did not start the turn")
        RUN["turn"] = tries  # counted once submitted: a hand-back (#118) is no submit
        if started:
            hold_turn(context)
        return True

    @staticmethod
    def win_rate(context, x, y, disc, turn):
        """Win Rate (one tap), then START at once: whether the turn started. If it did not, the picks are
        cleared at the left gear and Win Rate and START are tried once more, here rather than on MirrorHub's
        next looks (#145: those took 3 submits, a stuck and recovery L1, ~23 s)."""
        for attempt in range(2):
            image = screen(context)
            for _ in range(2):
                if battle.disc_lit(image, *disc) or start_shown(context, image, disc):
                    break
                # Win Rate toggles: a second tap clears the skills the first picked, so it is tapped again only
                # when its label does not show pressed: live, a tap in the turn's opening did nothing (#58).
                image = page_guard(context, "BattleTurn", image=image)
                tap(context, x + WIN_RATE[0], y + WIN_RATE[1], wait=0)
                lit = until(context, lambda im: battle.disc_lit(im, *disc), timeout=1.5)
                image = screen(context) if lit is None else lit
                if lit is not None or win_rate_on(context, image, x, y):
                    break
                log(f"turn {turn}: Win Rate did not take")
            if press_start(context, disc):
                return True
            xs = battle.slot_xs(x)
            if attempt == 0 and xs:
                # A chain left short (the disc lights, START does nothing) or picks the game dropped.
                log(f"turn {turn}: START did not start the turn: clearing the picks for Win Rate again")
                page_guard(context, "BattleTurn")
                tap(context, *battle.guard_chain(xs)[0], wait=0)
                until(context, lambda im: not battle.disc_lit(im, *disc), timeout=1)
        return False

    @staticmethod
    def guard(context, x, disc):
        """Pick every slot's guard skill and press START: whether the turn started on guard.

        A portrait tap swaps the slot's lower skill and its guard skill, and the game can keep the swap
        from turn to turn, so every portrait is tapped once and the lower skills compared before and
        after (the check that every slot shows its guard skill); the slots that went off guard are
        tapped back. Then one drag from the left gear through every slot's lower skill picks them
        (battle.guard_chain); no Win Rate. START is pressed right after it. The picked icons cannot be told
        apart reliably (banners, chain and glow cover them) and the disc lights with one slot linked, so a turn
        that does not start means the chain ended short (#145): a tap on the left gear clears it (a chain
        cannot be continued from its last slot) and a slower drag links it again (GUARD_DRAGS). A drag that
        links nothing (a hollow gear, #127) is not tried again.
        """
        xs = battle.slot_xs(x)
        lows = [lower_x(sx) for sx in xs]
        image = lower_skills(context, lows)  # live: a battle's first turn slides the portraits in late
        before = [guard_score(image, lx) for lx in lows]
        page_guard(context, "BattleTurn", image=image)
        for sx in xs:  # ponytail: one check per batch of portrait taps (0.1 s apart), not a screenshot per tap
            tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        image = lower_skills(context, lows, before)
        after = [guard_score(image, lx) for lx in lows]
        shown = battle.guard_shown(before, after)
        unsure = [i for i, s in enumerate(shown) if s is None]
        if unsure:  # live: the glow on a unit's slot flickers; swap those back and compare once more
            page_guard(context, "BattleTurn", image=image)
            for i in unsure:
                tap(context, xs[i], SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
            image = lower_skills(context, [lows[i] for i in unsure], [after[i] for i in unsure])
            again = battle.guard_shown([after[i] for i in unsure], [guard_score(image, lows[i]) for i in unsure])
            for i, s in zip(unsure, again):
                shown[i] = s
        if None in shown:
            log(f"guard: cannot tell the guard skill of slots {[i + 1 for i, s in enumerate(shown) if s is None]}")
            return False
        page_guard(context, "BattleTurn", image=image)
        for sx, on in zip(xs, shown):
            if not on:
                tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        chain = battle.guard_chain(xs)
        for n, params in enumerate(GUARD_DRAGS, 1):
            page_guard(context, "BattleTurn")
            drag(context, chain, **params)
            # Live (#145): the panel tilts back for ~0.15 s after the lift; a START pressed in it was lost 4 times
            # in 18. The Win Rate label matching again says it is back.
            until(context, lambda im: seen(context, im, "BattleTurn") is not None, timeout=1, every=0.05)
            if press_start(context, disc):
                return True
            image = screen(context)
            if not battle.disc_lit(image, *disc):
                log("guard: the chain drag linked nothing")
                return False
            log(f"guard: START did not start the turn after chain drag {n} ({params['dwell']} s a slot): clearing it")
            page_guard(context, "BattleTurn", image=image)
            tap(context, *chain[0], wait=0)
            until(context, lambda im: not battle.disc_lit(im, *disc), timeout=1)
        return False


@AgentServer.custom_action("Victory")
class Victory(CustomAction):
    """VICTORY ends the battle; it needs no tap. The encounter's retry count starts over."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if "turn" in RUN:
            log("victory")
        RUN.pop("turn", None)
        RUN.pop("battle_start", None)
        RUN["wipes"] = 0
        return True


DEFEAT_OPTIONS = {"retry": (790, 354), "forfeit": (790, 446)}  # Retry Stage, Accept results
DEFEAT_CONFIRM = (645, 527)
DEFEAT_TEXT = [330, 360, 270, 50]


@AgentServer.custom_action("Wipe")
class Wipe(CustomAction):
    """DEFEAT dialog: Retry Stage up to wipe_retries times, then stop or forfeit (spec 03 section 9).

    Accept results only on the way to forfeiting: it keeps the deaths.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        settings = current_run(context)["settings"]["run"]
        used = RUN.get("wipes", 0)
        choice = battle.after_wipe(used, settings["wipe_retries"], settings["after_retries"])
        log(f"wipe: {used} of {settings['wipe_retries']} retries used: {choice}")
        if choice == "stop":
            return stop(context, "retries used up")
        for _ in range(3):
            tap(context, *DEFEAT_OPTIONS[choice], wait=1.2)  # the options are cards: pick one, then Confirm
            tap(context, *DEFEAT_CONFIRM, wait=2.5)
            if not has(text(context, screen(context), DEFEAT_TEXT), "participating"):
                break
        else:
            return stuck(f"the DEFEAT dialog did not take {choice}")
        RUN.pop("turn", None)
        RUN.pop("battle_start", None)
        if choice == "retry":
            RUN["wipes"] = used + 1
        else:
            RUN["forfeit"] = True  # Accept results lands on the map; RouteMap forfeits from there
        return True


GEAR = (1232, 45)
FORFEIT = (541, 435)
FORFEIT_CONFIRM = (760, 488)
FORFEIT_DIALOG = [450, 335, 380, 40]


def forfeit(context):
    """Map after Accept results: settings panel, Forfeit, Confirm `Quit exploring the dungeon?` (spec 03 section 9)."""
    steps = [
        (GEAR, [520, 212, 240, 30], "Dungeon Progress", True),
        (FORFEIT, FORFEIT_DIALOG, "Quit exploring", True),
        (FORFEIT_CONFIRM, FORFEIT_DIALOG, "Quit exploring", False),
    ]
    for xy, roi, want, shown in steps:
        for _ in range(3):
            tap(context, *xy, wait=2)
            if has(text(context, screen(context), roi), want) == shown:
                break
        else:
            return stuck(f"forfeit: {want!r} did not {'show' if shown else 'go'}")
    RUN.pop("forfeit")
    log("forfeited the run")
    return True


# Events, reward cards and gifts (spec 03 sections 10-12).
EVENT_BUTTON = (1130, 645)  # SKIP / Proceed / Continue / Commence share it; grey while it does nothing
EVENT_STORY = [60, 320, 580, 200]
CHOICES_HEADER = [690, 105, 170, 45]
CHOICE_ROWS = [690, 170, 480, 440]
CHECK_PROMPT = [850, 295, 300, 50]
EVENT_PORTRAIT_X = [77 + round(69.3 * i) for i in range(12)]  # 7 in a boss's mid-battle event, from the left
EVENT_PORTRAIT_Y = 655
EVENT_NEUTRAL = (5, 5)  # top-left corner: nothing there on any event page
EVENT_TEXT_TAPS = 30
# A text tap every EVENT_TAP_EVERY s, the lit button's pixels looked at after each, the page's text only every
# EVENT_READ_EVERY taps: live 2026-10-20, a screenshot and 3 OCRs after each tap made it one every 0.3-1.1 s whatever
# the wait, and the text kept up at 0.15 s (no tap lost; the user's own taps 0.15 s).
EVENT_TAP_EVERY, EVENT_READ_EVERY = 0.15, 3
EVENT_TAKE = 1.5  # s a tap on an event page has to show
EVENT_LABELS = {"skip", "proceed", "continue", "commence"}  # the Event node's expected, compact()ed
EVENT_BUTTON_LABEL = [1040, 612, 190, 66]  # the Event node's roi: empty once the event page is gone
EVENT_LIMIT = 180  # s one event may take before recovery L1 (AALC allows 300); a boss quiz of several rounds stays well under
EVENT_GAP = 30  # s between two Event calls after which the next call is another event
EVENT_LEAST = 0.5 # s after a tap before the screen counts as moved: a fade's first frames are the same page
CHOICE_X = 925  # the option list's middle
CHOICE_STEP = 150  # px per drag of a list that scrolls: about a card (130-150 px), so none is skipped
CHOICE_SCROLLS = 6  # drags at most to an end of the list


def data(name):
    return yaml.safe_load((RESOURCE / "base" / "data" / name).read_text(encoding="utf-8")) or {}


@functools.cache
def event_table():
    """data/event_table.json's events (spec 03 section 10, #93), read once."""
    return json.loads((RESOURCE / "base" / "data" / "event_table.json").read_text(encoding="utf-8"))["events"]


def red_button(image):
    b, g, r = image[640:650, 1080:1180].reshape(-1, 3).mean(0)
    return r > 150 and r - b > 70


@AgentServer.custom_action("Event")
class Event(CustomAction):
    """One step on an event page: press the lit button, pick a checker or an option, else advance the text (spec 03 section 10)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        # One event's clock: a call more than EVENT_GAP s after the last starts the next event's (#92).
        now = time.monotonic()
        event = RUN.get("event")
        if event is None or now - event["last"] > EVENT_GAP:
            event = RUN["event"] = {"since": now, "last": now, "checked": set()}
        event["last"] = now
        if now - event["since"] > EVENT_LIMIT:
            RUN.pop("event")
            return stuck(f"one event went on over {EVENT_LIMIT} s")
        tried = RUN.setdefault("event_tried", set())  # this question's options a tap did nothing on
        checked = event["checked"]  # portraits a tap did nothing on in this check
        if red_button(image):
            tried.clear()
            checked.clear()
            tap(context, *EVENT_BUTTON, wait=0)
            Event.advance(context, image, pressed_at=time.monotonic())
        elif has(text(context, image, CHECK_PROMPT), "Choose a character"):
            # One read per portrait: read as a row, neighbouring captions run together ("HighVery Low").
            captions = [(text(context, image, [x - 38, 605, 76, 24], only_rec=True), x) for x in EVENT_PORTRAIT_X]
            i = rewards.pick_checker(captions, checked)
            if i is None:  # no odds read (or all tried): the next sinner not tried yet, round again when all are
                i = next((k for k in range(len(captions)) if k not in checked), None)
                if i is None:
                    checked.clear()
                    i = 0
            log(f"event check: {', '.join(t for t, _ in captions) or 'no odds read'}: take sinner {i + 1}")
            tap(context, captions[i][1], EVENT_PORTRAIT_Y, wait=0)
            if Event.settle(context, image) is None:
                checked.add(i)
        elif has(text(context, image, CHOICES_HEADER), "Choices"):
            checked.clear()
            story = [t for t, _ in sorted(ocr(context, image, EVENT_STORY), key=lambda r: (r[1][1], r[1][0]))]
            scrolls = rewards.choice_scrollbar(image) or any(None in c for c in rewards.choice_cards(image))
            options, image = self.read_choices(context, image, scrolls)
            if not options:
                return True
            overrides = data("events.yaml") | {o["question"]: o["option"] for o in run["settings"]["event_overrides"]}
            question = next(filter(None, (run_start.match_pack(t, list(overrides)) for t in story + [" ".join(story)])), None) if overrides else None
            known = rewards.match_event(" ".join(story), event_table())
            # Grey options (taken in an earlier round of the same questions) and ones a tap did nothing on are closed.
            closed = {k for k, (t, is_open, _) in enumerate(options) if t in tried or not is_open}
            i = rewards.pick_choice([t for t, _, _ in options], run["team"]["keyword"], overrides.get(question), closed, known)
            shown = " | ".join(("(closed) " if k in closed else "") + t for k, (t, _, _) in enumerate(options))
            if i is None:
                log(f"event: {shown}: all closed, scroll for more")
                scroll(context, CHOICE_X, 420, 0, -CHOICE_STEP)  # in case the list scrolls with no sign of it
                return True
            log(f"event: {shown}: take {options[i][0]!r}" + (f" (override {question!r})" if question else "")
                + ("" if known else " (not in the event table: hint rules)"))
            y, image = self.into_view(context, image, options, i) if scrolls else (options[i][2], image)
            if y is None:
                log(f"event: {options[i][0]!r} not found again in the list")
                return True
            tap(context, CHOICE_X, y, wait=0)
            if until(context, lambda im: not Event.panel_same(image, im), timeout=EVENT_TAKE) is None:
                log(f"event: {options[i][0]!r} did nothing: try another")
                tried.add(options[i][0])
        else:
            tried.clear()
            Event.advance(context, image)
        return True

    @staticmethod
    def advance(context, image, pressed_at=None):
        """Text running on (the button grey, or a press of it lit fading out): taps on a dead corner show it line by
        line; keep tapping until there is something to act on, for MirrorHub's next look.

        A Choices page or a check prompt shows up to EVENT_READ_EVERY - 1 taps late: a tap on the dead corner picks nothing.
        pressed_at: time.monotonic() of a tap on the lit button just now, image the screen it was tapped on (#188:
        MirrorHub's look after it paused the taps 1.6-5.3 s). The button stays lit while the press fades out, its
        label read once a screen (1 OCR, besides the page check every EVENT_READ_EVERY taps); the first screen
        without it is read before the next tap (3 OCRs). Lit with another label (SKIP, then Continue), it is the
        next button; lit EVENT_TAKE s on, the press was lost.
        Only two labels read whole tell another button: one read empty or in part while it fades ("Contnue") is not,
        as MirrorHub's Event node would still match the fading button and press it twice.
        """
        last, pressed_label = 0.0, None  # None: not in a press's fade (any more)
        if pressed_at is not None:
            last, pressed_label = pressed_at, compact(text(context, image, EVENT_BUTTON_LABEL))
        for n in range(1, EVENT_TEXT_TAPS + 1):
            time.sleep(max(0.0, last + EVENT_TAP_EVERY - time.monotonic()))
            last = time.monotonic()
            if (n - 1) % EVENT_READ_EVERY == 0:  # on the last read's screenshot (#118, ADR 0007): an OCR a tap would undo the 0.15 s
                page_guard(context, "Event", image=image)
            tap(context, *EVENT_NEUTRAL, wait=0)
            image = screen(context)
            if red_button(image):
                if pressed_label is None or time.monotonic() - pressed_at >= EVENT_TAKE:
                    break
                label = compact(text(context, image, EVENT_BUTTON_LABEL))
                if pressed_label in EVENT_LABELS and label in EVENT_LABELS and label != pressed_label:
                    break
                continue
            read = n % EVENT_READ_EVERY == 0 or pressed_label is not None
            pressed_label = None
            if read and (not text(context, image, EVENT_BUTTON_LABEL) or any(
                    has(text(context, image, roi), k) for k, roi in (("Choices", CHOICES_HEADER), ("Choose a character", CHECK_PROMPT)))):
                break

    @staticmethod
    def settle(context, before):
        """Wait for a tap to show on screen, at most EVENT_TAKE s; MirrorHub looks again after.

        Returns the screen that moved, None when the tap did nothing.
        """
        return until(context, lambda im: moved(before, im), timeout=EVENT_TAKE, least=EVENT_LEAST)

    @staticmethod
    def panel_same(before, after):
        """Whether the choice panel looks as it did: a tap on it did nothing."""
        x, y, w, h = CHOICE_ROWS
        return recovery.same_screen(*(recovery.thumb(i[y:y + h, x:x + w]) for i in (before, after)))

    @staticmethod
    def shown(context, image, scrolls):
        """The options on screen as [(text, y of its first line)]; in a list that scrolls only those whose frame shows whole."""
        rows = [(" ".join(lines), y) for y, lines in Event.rows(ocr(context, image, CHOICE_ROWS))]
        if not scrolls:
            return rows
        whole = [(top, bottom) for top, bottom in rewards.choice_cards(image) if top is not None and bottom is not None]
        return [(t, y) for t, y in rows if any(top < y < bottom for top, bottom in whole)]

    @staticmethod
    def drag(context, image, dy):
        """Scroll the option list by dy px (dy < 0 shows what is below); the screen after, None when it did not move."""
        page_guard(context, "Event", image=image)
        scroll(context, CHOICE_X, 420 if dy < 0 else 260, 0, dy)
        after = screen(context)
        # Pixel by pixel, not panel_same's thumbnails: cards about a drag apart look alike in those.
        y0, y1 = rewards.CHOICE_LIST_Y
        return after if np.abs(after[y0:y1, 690:1170].astype(int) - image[y0:y1, 690:1170]).mean() >= 2 else None

    @staticmethod
    def read_choices(context, image, scrolls):
        """Every option as [(text, open, y of its first line where read)] top to bottom, and the screen it ends on.

        A list that scrolls (#93) is dragged to its top, then down a card at a time without a fling, each
        option read once its frame shows whole; the same text read again is the same option.
        """
        if not scrolls:
            return [(t, rewards.choice_open(image, y), y) for t, y in Event.shown(context, image, False)], image
        for _ in range(CHOICE_SCROLLS):  # to the top
            after = Event.drag(context, image, CHOICE_STEP)
            if after is None:
                break
            image = after
        options = []
        for _ in range(CHOICE_SCROLLS):
            for t, y in Event.shown(context, image, True):
                if not run_start.match_pack(t, [o[0] for o in options], margin=0):
                    options.append((t, rewards.choice_open(image, y), y))
            after = Event.drag(context, image, -CHOICE_STEP)
            if after is None:
                break
            image = after
        if not options:  # no whole frame read: take the list as it reads
            return Event.read_choices(context, image, False)
        return options, image

    @staticmethod
    def into_view(context, image, options, i):
        """(y to tap, screen) for option i of a list that scrolls, dragged until its frame shows whole; (None, screen) when not found.

        A screen with none of the options read (#196: one the read missed) is dragged on the same way, up first
        (read_choices ends at the bottom), turning once at an end of the list. It gives up at an end of the
        list the options on screen put the pick beyond, or at the second end with none of them read.
        """
        texts = [t for t, _, _ in options]
        step, turned = CHOICE_STEP, False
        for _ in range(2 * CHOICE_SCROLLS + 1):
            seen = {}  # option index -> y, for the options on screen
            for t, y in Event.shown(context, image, True):
                if name := run_start.match_pack(t, texts, margin=0):
                    seen.setdefault(texts.index(name), y)
            if i in seen:
                return seen[i], image
            if seen:
                step = CHOICE_STEP if min(seen) > i else -CHOICE_STEP
            after = Event.drag(context, image, step)
            if after is None:
                if turned or seen:  # both ends with none read, or the end the options on screen put it beyond
                    return None, image
                step, turned = -step, True
            else:
                image = after
        return None, image

    @staticmethod
    def rows(results):
        """Option rows top to bottom as (y of the first line, [lines]); a gap over 50 px starts a new row."""
        rows = []
        for t, (x, y, w, h) in sorted(results, key=lambda r: r[1][1]):
            if rows and y - rows[-1][2] < 50:
                rows[-1][1].append(t)
                rows[-1][2] = y
            else:
                rows.append([y + h // 2, [t], y])
        return [(y, lines) for y, lines, _ in rows]


REWARD_TITLE = [290, 112, 490, 48]
CARD_TEXT = [130, 340, 1020, 120]
SELECTABLE = [880, 115, 170, 40]
CARD_CONFIRM = (808, 528)


@AgentServer.custom_action("RewardCard")
class RewardCard(CustomAction):
    """Take reward cards in the team's order until Selectable n/m is full, then Confirm; never Cancel (spec 03 section 11)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        order = current_run(context)["team"]["reward_cards"]
        taken = set()
        for _ in range(5):
            image = page_guard(context, "RewardCard")
            m = re.search(r"(\d)\s*/\s*(\d)", text(context, image, SELECTABLE))
            if m and m[1] == m[2]:
                tap(context, *CARD_CONFIRM, wait=0)
                until(context, lambda im: not has(text(context, im, REWARD_TITLE), "Encounter Reward"))
                return True
            cards = columns(ocr(context, image, CARD_TEXT))
            if not cards or len(taken) == len(cards):
                time.sleep(1)
                continue
            types = [rewards.card_type(" ".join(lines)) for _, lines in cards]
            i = rewards.pick_card(types, order, taken)
            log(f"reward cards: {', '.join(str(t) for t in types)}: take {types[i] or ' '.join(cards[i][1])!r}")
            tap(context, cards[i][0], 300, wait=0)
            until(context, lambda im: text(context, im, SELECTABLE) != text(context, image, SELECTABLE), timeout=1.5)
            taken.add(i)
        return stuck("reward card page did not fill Selectable")


GIFT_CARDS = [100, 150, 1080, 410]  # 1-4 cards; on the boss page the Mounting Trials half below each
GIFT_COUNT = [1060, 555, 160, 50]  # "Select 0/2"; no count with one card
GIFT_SELECT = (1138, 579)
REFUSE_GIFT = [870, 560, 160, 40]
TRIAL_NAME_Y = (440, 475)  # top of the trial name line; the effect line under it starts ~485


def gift_count(context, image=None):
    m = re.search(r"(\d)\s*/\s*(\d)", text(context, screen(context) if image is None else image, GIFT_COUNT))
    return (int(m[1]), int(m[2])) if m else None


@AgentServer.custom_action("PickGift")
class PickGift(CustomAction):
    """Gift choice after a fight, an event or a boss: best cards until Select n/m is full, then Select (spec 03 section 12).

    Cards are main keyword > other > owned; when Mounting Trials hang under them (after a boss),
    each scores gift - weight x trial risk. Refuse Gift is never pressed: it hands out random trials.
    A gift the team avoids (#90) comes last: taken only when nothing else fills the count.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        results = ocr(context, image, GIFT_CARDS)
        # The "Acquire E.G.O Gift" tab sits on each card's top-right corner, 114 px right of its centre.
        centres = sorted(x + w - 114 for t, (x, y, w, h) in results if has(t, "Acquire"))
        if not centres:
            return True  # page fading in or out: let MirrorHub look again
        lines = [[] for _ in centres]
        for t, (x, y, w, h) in results:
            i = min(range(len(centres)), key=lambda i: abs(centres[i] - x - w // 2))
            if abs(centres[i] - x - w // 2) < 130 and not has(t, "Acquire"):
                lines[i].append((y, t))
        trials = any(has(t, "Mounting") for t, _ in results)
        risks = data("trial_risks.yaml") | {o["trial"]: o["risk"] for o in run["settings"]["trial_risk_overrides"]}
        avoid = [g["name"] for g in avoided_gifts(run["team"])]
        cards = []
        for card in lines:
            gift = " ".join(t for y, t in card if y < 410)
            owned = any(compact(t) == "owned" for _, t in card)
            names = [t for y, t in card if TRIAL_NAME_Y[0] <= y < TRIAL_NAME_Y[1]]
            risk = min((rewards.trial_risk(t, risks) for t in names), default=rewards.MAX_RISK) if trials else None
            cards.append((rewards.gift_kind(gift, run["team"]["keyword"], owned, avoid), risk))
        ranked = rewards.rank_gifts(cards, run["team"]["trial_risk_weight"])
        log("gifts: " + ", ".join(k + ("" if r is None else f"/risk {r}") for k, r in cards) + f": order {ranked}")

        def pick(i):
            before = gift_count(context, page_guard(context, "GiftChoice"))
            tap(context, centres[i], 300, wait=0)
            until(context, lambda im: gift_count(context, im) != before, timeout=1.5)

        rewards.pick_gifts(ranked, lambda: gift_count(context), pick)
        for _ in range(3):
            page_guard(context, "GiftChoice")
            tap(context, *GIFT_SELECT, wait=0)
            if until(context, lambda im: not has(text(context, im, REFUSE_GIFT), "Refuse")) is not None:
                return True
        return stuck("Select did not take the gifts")


# Shop (spec 03 section 13). The Super Shop has the same layout with up to 10 offers.
SHOP_COST = [540, 112, 110, 45]
REFRESH = {"normal": ((997, 122), [960, 140, 80, 30]), "keyword": ((1140, 122), [1100, 140, 80, 30])}  # button, fee
OFFER_GRID = [545, 215, 620, 300]
DIALOG_TITLE = [360, 80, 560, 115]  # Purchase E.G.O Gifts, Shop - Keyword Refresh, Fuse / Sell E.G.O Gift
PURCHASE_TEXT = [525, 210, 400, 220]
PURCHASE_PREVIEW = [780, 145, 140, 40]  # "2864 > 2612": the Cost before and after
PURCHASE, PURCHASE_CANCEL = (747, 482), (525, 482)
KEYWORD_LABELS = [270, 300, 740, 200]  # the 10 keyword cards of both keyword dialogs
KEYWORD_REFRESH, KEYWORD_CANCEL = (785, 560), (495, 560)
GET_TITLE, GET_CONFIRM = [520, 160, 240, 40], (640, 532)
GET_NAME = [320, 405, 180, 80]  # the red plate under the gift's icon
PAGE_CLOSE, PAGE_OK = (490, 585), (788, 585)  # Close, and Fuse / Sell, on the fuse and sell pages
SHOP_BUTTONS = {"fuse": (295, 390), "sell": (395, 390), "heal": (197, 474)}
FUSE_CENTRE, FUSE_KEYWORD_OK = (365, 340), (788, 566)
# Grid cells by their centre (live 2026-10-16/18). Each cell's tier numerals sit top left, its keyword badge
# bottom right (none on a keywordless gift). The owned grids' third row shows half: its badges are cut off.
FUSE_CELLS = [(678 + 96 * c, y) for y in (294, 385, 477) for c in range(5)]
OFFER_CELLS = [(624 + 154 * c, y) for y in (265, 418) for c in range(4)]  # a shop at rest; the price line is 52 px under
SELL_CELLS = [(683 + 92 * c, y) for y in (258, 363, 473) for c in range(5)]
# page: (its icon size over the GiftSearch template's, the grid's lower edge on screen)
CELL_PAGES = {"fuse": (1.1, 493), "sell": (1.1, 495), "offer": (0.8, 530)}
BADGES = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt"]
# On scaled cells (CCOEFF): its own badge 0.54-0.99, another keyword's up to 0.60 (the cell's best wins), a keywordless
# cell's best 0.41; 160 cells of 60 live captures. An observed gift's icon: Spiderweb's thin lines 0.5-0.6, others 0.86+.
BADGE_MIN, ICON_KEEP = 0.5, 0.45
FUSE_TOOLTIP = [600, 180, 680, 440]
TOOLTIP_HEAD = "ogift"  # a gift tooltip's "E.G.O GIFT" heading line, compacted
FUSE_CONFIRM = [300, 150, 680, 380]  # "Selected E.G.O Gifts 3/5" over "Fuse the selected E.G.O Gifts?"
FUSE_COUNT = r"(\d)\s*/\s*\d"  # its "3/5": the materials in
FUSE_NEUTRAL = (715, 229)  # the E.G.O Gifts Owned label: closes a tooltip, selects nothing
SELL_PANEL, SELL_PRICE, SELL_COST = [150, 160, 420, 360], [500, 160, 60, 45], [960, 80, 160, 45]
SELL_GRID = [630, 210, 480, 290]  # the sell page's gifts with their prices under them
HEAL_TITLE, HEAL_COST = [130, 30, 220, 45], [1100, 90, 110, 50]
HEAL_OPTIONS = {"full": (1020, 330), "revive": (1020, 455)}
SHOP_PORTRAIT_X = [98 + 77 * i for i in range(12)]  # the shop's sinner bar (step 77, not the event bar's)
BOTTOM_RIGHT = (1130, 647)  # Leave on the shop; Return, Select or Leave on the heal pages
OUTSIDE = (40, 400)  # left of every shop dialog, on nothing
LEAVE_DIALOG, LEAVE_CONFIRM, LEAVE_CANCEL = [440, 320, 400, 45], (765, 493), (515, 493)


def tooltip_head(lines):
    """The box of a gift tooltip's "E.G.O GIFT" heading among OCR lines [(text, box)], or None. Its end, not a part:
    the grid's "E.G.O Gifts Owned" label sits in FUSE_TOOLTIP too."""
    return next((b for t, b in lines if compact(t).endswith(TOOLTIP_HEAD)), None)


def cost_in(context, image, roi=SHOP_COST):
    """The Cost OCR reads in roi of image (digits), None without a digit."""
    return digits(text(context, image, roi))


def read_cost(context, roi=SHOP_COST):
    """The Cost in roi, read again on a fresh screenshot when OCR gives no digit; None when 3 reads give none (#82).

    None is never a Cost of 0: a caller that needs the Cost does nothing on None and logs it.
    """
    for _ in range(3):
        cost = cost_in(context, screen(context), roi)
        if cost is not None:
            return cost
        time.sleep(0.5)
    return None


def kept_gifts(team):
    """Gift names the shop keeps, for a tooltip's or panel's text: the team's observed (#103) and kept gifts (#77)."""
    return [g["name"] for g in team["gift_search"]["gifts"] + team.get("keep_gifts", [])]


# Vestiges, tier I-V in this order (#161; LocalizeLimbusCompany EN/EGOgift_MirrorDungeon.json, ids 9991-9995): the settings
# schema lists them for keep_gifts, so the GUI and the agent share one list. They have no badge; their icons
# (image/GiftSearch/<id>.png, from the game client like the Gift Search ones) differ only in the jar's fill: the tier
# read off the cell tells them apart (read_cells).
VESTIGES = SCHEMA["$defs"]["vestige"]["properties"]["name"]["enum"]
VESTIGE_ICONS = [{"name": n, "keyword": "Keywordless", "tier": t, "id": 9990 + t} for t, n in enumerate(VESTIGES, 1)]


def loose_vestiges(team, page):
    """The vestiges the shop uses on page ("fuse" or "sell"): only fusion or sale material, their own kind, so the
    keywordless setting never applies to them (the user, #161). Those the team names in keep_gifts stay; on the sell
    page all stay unless the team sells them (sell_vestiges)."""
    if page == "sell" and not team.get("sell_vestiges", False):
        return []
    return [v for v in VESTIGES if v not in kept_gifts(team)]


def cell_role(cell, team, page, avoid):
    """shop.gift_role of a cell read_cells read on page ("fuse" or "sell"), by the team's settings."""
    return shop.gift_role(cell["keyword"], cell["gift"], kept_keywords(team, page), avoid, loose_vestiges(team, page))


def tooltip_use(lines, team, avoid):
    """What the shop may do with a gift known only by its tooltip's or panel's lines (its badge cut off, or its price):
    "keep", "fuse" (fusion material it does not sell), "sell" (either) or "avoid" (either, first: #90).

    By the name first: an avoided gift, a kept one (kept_gifts), a vestige (loose_vestiges), a keywordless gift
    (data/keywordless_gifts.json, tiers I-V), which the keywordless setting alone decides (kept_keywords; the user,
    #161). Only another gift is told by its text: kept when it names a kept keyword (kept_text, spec 03 section 12).
    """
    text = " ".join(lines)
    if rewards.gift_kind(text, team["keyword"], False, avoid) == "avoid":
        return "avoid"
    if any(shop.protected(t, kept_gifts(team)) for t in lines):
        return "keep"
    if any(shop.protected(t, VESTIGES) for t in lines):
        return "sell" if team.get("sell_vestiges", False) else "fuse"  # one the team keeps returned above
    if any(shop.protected(t, keywordless_names()) for t in lines):
        if "Keywordless" in kept_keywords(team, "fuse"):
            return "keep"
        return "fuse" if "Keywordless" in kept_keywords(team, "sell") else "sell"
    return "keep" if kept_text(text, team) else "sell"


@functools.cache
def keywordless_names():
    """data/keywordless_gifts.json: the keywordless Mirror Dungeon gifts' English names, tiers I-V (#161)."""
    return data("keywordless_gifts.json")["names"]


def kept_keywords(team, page):
    """The keywords whose gifts the shop keeps on page ("fuse" or "sell"): the main one, the team's keep_keywords
    (#77) and "Keywordless" as the team's keywordless setting says (#161): "keep" on both pages, "fuse" on the sell
    page only (fusion material, never sold), "fuse_or_sell" on neither."""
    use = team.get("keywordless", "keep")
    keywordless = use == "keep" or (use == "fuse" and page == "sell")
    return {team["keyword"], *team.get("keep_keywords", ())} | ({"Keywordless"} if keywordless else set())


def kept_icons(team):
    """The gifts the shop keeps by their icon ({"name", "keyword", "tier"}) with its id in data/gift_search.json:
    the team's observed gifts (#103) and its keep_gifts (#77)."""
    table = gift_data()
    out = []
    for g in team["gift_search"]["gifts"] + team.get("keep_gifts", []):
        entry = next((e for e in table if e["keyword"] == g["keyword"] and e["tier"] == g["tier"]
                      and run_start.match_pack(e["en"], [g["name"]])), None)
        if entry and all(o["id"] != entry["id"] for o in out):
            out.append({**g, "id": entry["id"]})
    return out


def kept_text(text, team):
    """Whether a tooltip's or panel's text names a keyword the team keeps (kept_keywords; spec 03 section 12's rule)."""
    return any(rewards.gift_kind(text, k, False) == "main" for k in kept_keywords(team, "fuse") - {"Keywordless"})


WHITE_GOSSYPIUM = 9020  # its id in data/gift_search.json


def avoided_gifts(team):
    """Gifts the team never takes or buys, and fuses or sells first: White Gossypium unless it allows it (#90).

    Shaped like kept_icons, for read_cells' icon match.
    """
    if team.get("allow_white_gossypium", True):
        return []
    g = next(e for e in gift_data() if e["id"] == WHITE_GOSSYPIUM)
    return [{"name": g["en"], "keyword": g["keyword"], "tier": g["tier"], "id": g["id"]}]


def template_hits(context, image, template, threshold):
    """[(score, (x, y))]: the centres where template matches on image (TemplateMatch CCOEFF, its green masked)."""
    h, w = image.shape[:2]
    node = {"recognition": "TemplateMatch", "template": template, "threshold": threshold, "method": 5,
            "green_mask": True, "roi": [0, 0, w, h]}
    detail = context.run_recognition("ShopCell", image, {"ShopCell": node})
    return [(r.score, (r.box[0] + r.box[2] / 2, r.box[1] + r.box[3] / 2)) for r in (detail.filtered_results if detail else [])]


def read_cells(context, image, cells, page, gifts=()):
    """The filled cells of a shop grid read off one screenshot (#76, #112): [{"i", "x", "y", "tier", "keyword", "gift"}].

    The grid is scaled so gift icons are at their GiftSearch template's size, then each keyword's badge and each
    kept gift's icon (gifts, kept_icons) is matched once over it. keyword: the cell's best badge,
    "Keywordless" with none, None when the badge is below the grid's edge; gift: the kept gift whose icon
    matched, when its keyword and tier agree with the cell's. An empty cell is flat (live: spread 1-2, a gift 41-84).
    """
    scale, bottom = CELL_PAGES[page]
    half = shop.CELL_HALF
    filled = [(i, x, y) for i, (x, y) in enumerate(cells) if image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15]
    if not filled:
        return []
    x0, y0 = min(x for _, x, _ in filled) - half, min(y for _, _, y in filled) - half
    x1, y1 = max(x for _, x, _ in filled) + half, min(bottom, max(y for _, _, y in filled) + half)
    grid = shop.rescale(image[y0:y1, x0:x1], 1 / scale)
    out = [{"i": i, "x": x, "y": y, "tier": shop.tier(shop.cell_crop(image, x, y, scale)),
            "keyword": "Keywordless" if y + 40 <= bottom else None, "gift": None,
            "at": ((x - x0) / scale, (y - y0) / scale)} for i, x, y in filled]
    best = {}
    for keyword in BADGES:
        for score, (bx, by) in template_hits(context, grid, f"Shop/Badge{keyword}.png", BADGE_MIN):
            for c in out:  # a badge sits 12-40 px right of and below its cell's centre, on the scaled grid
                cx, cy = c["at"]
                if c["keyword"] and 12 <= bx - cx <= 40 and 12 <= by - cy <= 40 and score > best.get(c["i"], 0):
                    best[c["i"]], c["keyword"] = score, keyword
    for g in gifts:
        for score, (bx, by) in template_hits(context, grid, f"GiftSearch/{g['id']}.png", ICON_KEEP):
            for c in out:
                cx, cy = c["at"]
                # A vestige only where the tier was read: the five jars match each other's cells too (VESTIGES).
                tiers = (g["tier"],) if g["name"] in VESTIGES else (None, g["tier"])
                if abs(bx - cx) < 16 and abs(by - cy) < 16 and c["keyword"] in (None, g["keyword"]) and c["tier"] in tiers:
                    c["gift"] = g["name"]
    for c in out:
        del c["at"]
    return out


def offer_cell(slot):
    """The icon centre of an offer read by shop.read_slots: its column's, 52 px over its price line."""
    return min((x for x, _ in OFFER_CELLS[:4]), key=lambda x: abs(x - slot["x"])), slot["y"] - 52


def cell_line(cell, role):
    """One cell read for the log: "0 III Keywordless Spiderweb Entangled in Red: keep"."""
    tier = "I II III IV V".split()[cell["tier"] - 1] if cell["tier"] else "?"
    return f"{cell['i']} {tier} {cell['keyword'] or 'badge unread'}{' ' + cell['gift'] if cell['gift'] else ''}: {role}"


def tooltip_up(context):
    """Whether a gift tooltip shows over the fuse page now (tooltip_head on a fresh screenshot)."""
    return tooltip_head(ocr(context, screen(context), FUSE_TOOLTIP)) is not None


def fusions(cells, roles, slots, avoid):
    """shop.pick_fusion over the cells whose role is material and whose tier is read: [([cell index], tier)] (#77).

    The thresholds are the Super Shop's when the page has its 5 slots; an avoided gift goes in first (#90).
    """
    d = data("shop.yaml")
    materials = [(c["i"], c["tier"]) for c, r in zip(cells, roles) if r == "material" and c["tier"]]
    tiers = d["fusion_tiers"]["super_shop" if slots == 5 else "shop"]
    return shop.pick_fusion(materials, slots, tiers, d["fusion_points"], {c["i"] for c in cells if c["gift"] in avoid})


def tap_keyword(context, keyword):
    """Tap the keyword's card in an open keyword dialog; False when its label is not read."""
    label = next((b for t, b in ocr(context, screen(context), KEYWORD_LABELS) if compact(t) == compact(keyword)), None)
    if label:
        x, y, w, h = label
        tap_moved(context, x + w // 2, y - 40)  # the card lights up
    return bool(label)


def gift_get(context):
    """Confirm the E.G.O Gift GET! popup after a purchase or a fusion; False when none comes up in 4.5 s."""
    def title(image):
        return has(text(context, image, GET_TITLE), "GET")
    if until(context, title, timeout=4.5) is None:
        return False
    for _ in range(3):  # a tap while the popup zooms in is lost
        if tap_then(context, *GET_CONFIRM, lambda im: not title(im), timeout=1.5) is not None:
            still(context, timeout=1.0)  # the popup fades out over the Cost
            break
    return True


@AgentServer.custom_action("Shop")
class Shop(CustomAction):
    """Heal, then sell -> buy and refresh -> fuse until a round does nothing, then leave (spec 03 section 13).

    The visit's state (healed, refreshes used, the gift wanted and whether a sale was tried for it, whether the
    owned gifts were scanned for a fusion) lives in RUN["shop"], so a re-entry from MirrorHub carries on; leaving drops it. Every spend keeps the team's reserve_cost.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        if not self.to_main(context):
            return True  # a page fading in or out: let MirrorHub look again
        visit = RUN.setdefault("shop", {"healed": False, "refreshes": 0, "wanted": None, "sold": False})
        if not visit["healed"]:
            visit["healed"] = True  # first: a heal handed back mid-way (#118) is not paid twice
            self.heal(context, team)
        for _ in range(shop.ROUNDS):
            if not self.to_main(context):
                break  # left already: the leave below finds the map
            acted = self.sell(context, team, visit)
            acted = self.buy(context, team, visit) or acted
            acted = self.fuse(context, team, visit) or acted
            if not acted:
                break
        else:
            log(f"shop: still acting after {shop.ROUNDS} rounds")
        for _ in range(3):
            image = screen(context)
            if Shop.on_map(context, image):
                log("shop: already out of the shop")
                RUN.pop("shop", None)
                return True
            # The dialog slides down; Confirm takes no tap before it stops.
            page_guard(context, "Shop", image=image)
            if tap_shown(context, *BOTTOM_RIGHT, lambda im: has(text(context, im, LEAVE_DIALOG), "Leave the shop"),
                         timeout=1.5) is not None:
                log(f"shop: leave with {read_cost(context)} Cost")
                # Up to the old 2 s for the map: MirrorHub must not find the shop fading out and start a new visit.
                tap_then(context, *LEAVE_CONFIRM, lambda im: Shop.on_map(context, im), timeout=2)
                RUN.pop("shop")
                return True
        return stuck("Leave did not bring up `Leave the shop?`")

    @staticmethod
    def on_map(context, image):
        """Whether image shows the map (or its node panel): the shop was left."""
        return on_page(context, image, "MirrorMap", "MapNodePanel") is not None

    @staticmethod
    def to_main(context):
        """Back out of any shop page or dialog; True once the main shop (its Refresh fee) shows.

        False at once on the map: the shop was left (live 2026-10-18, by hand mid-visit), and a tap
        meant for a shop page lands on a map node.
        """
        for _ in range(5):
            image = screen(context)
            if Shop.on_map(context, image):
                return False
            title = text(context, image, DIALOG_TITLE)
            heal = has(text(context, image, HEAL_TITLE), "Heal")
            if has(text(context, image, GET_TITLE), "GET"):
                at = GET_CONFIRM
            elif has(title, "Purchase"):
                at = PURCHASE_CANCEL
            elif has(title, "Keyword Refresh"):
                at = KEYWORD_CANCEL
            elif has(title, "Keyword Selection"):
                at = (490, 566)  # its Cancel
            elif has(title, "Gift Info"):  # a bought offer tapped: only a tap outside it closes it
                at = OUTSIDE
            elif has(title, "E.G.O Gift"):  # the fuse or sell page; a tooltip may cover Close
                if tooltip_head(ocr(context, image, FUSE_TOOLTIP)):
                    tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)  # it fades: Close would land on it
                at = PAGE_CLOSE
            elif has(text(context, image, LEAVE_DIALOG), "Leave the shop"):
                at = LEAVE_CANCEL
            elif heal:
                tap(context, *BOTTOM_RIGHT, wait=1.5)  # the heal pages keep their fixed waits: not seen live
                continue
            elif number(text(context, image, REFRESH["normal"][1])) is not None:
                return True
            else:
                page_guard(context, "Shop", image=image)  # not a shop page MirrorHub knows: hand it back
                still(context, timeout=1.5)  # a page fading in or out
                continue
            tap_settled(context, *at)
        return False

    @staticmethod
    def heal(context, team):
        """Heal everyone once, or revive the dead, per the team's heal setting.

        The dead are the grey portraits on the shop's sinner bar; the count from the last formation
        (RUN["alive"]) is only checked against them, as the shop shows deaths since then too.
        """
        if team["heal"] == "none":
            return  # nothing to decide: skip the Cost and portrait reads
        cost = read_cost(context)
        if cost is None:
            log("shop: the Cost reads nothing: no heal")
            return
        image = screen(context)
        dead = [x for x in SHOP_PORTRAIT_X if saturation(image[630:680, x - 25:x + 25]).mean() < 30]
        if "alive" in RUN and 12 - RUN["alive"] != len(dead):
            log(f"shop: {12 - RUN['alive']} dead at the last formation, {len(dead)} grey portraits")
        plan = shop.heal_plan(team["heal"], cost, team["reserve_cost"], len(dead), data("shop.yaml")["heal_cost"])
        log(f"shop: {cost} Cost, {len(dead)} dead, heal {team['heal']}: {plan or 'nothing'}")
        if not plan:
            return
        kind, n = plan
        for x in dead[:n] if kind == "revive" else [None]:
            page_guard(context, "Shop")
            tap(context, *SHOP_BUTTONS["heal"], wait=2)
            if not has(text(context, screen(context), HEAL_TITLE), "Heal"):
                log("shop: the heal page did not open")
                break
            before = read_cost(context, HEAL_COST)
            tap(context, *HEAL_OPTIONS[kind], wait=1.5)
            if x is not None:
                tap(context, x, 655, wait=1.2)  # only a dead sinner takes the tap; then Select shows
                tap(context, *BOTTOM_RIGHT, wait=2)
            after = read_cost(context, HEAL_COST)
            log(f"shop: {kind}: {before} -> {after} Cost")
            if after == before:
                break
            if kind == "revive" and "alive" in RUN:
                RUN["alive"] += 1
            tap(context, *BOTTOM_RIGHT, wait=2)  # the result's Leave: back to the shop
            Shop.to_main(context)
        Shop.to_main(context)

    @staticmethod
    def buy(context, team, visit):
        """Buy the main-keyword gifts on show (buy_offers), then refresh while the rules allow; True on any spend.

        A first choice too dear for the reserve becomes visit["wanted"] for the next round's sell, and
        holds the purchases and the refresh back until that sell has been tried.
        """
        keyword, reserve, acted = team["keyword"], team["reserve_cost"], False
        while True:
            if Shop.buy_offers(context, team, visit):
                acted = True
                visit["fuse_scanned"] = False  # a new gift: the fusion grid has changed
            if visit["wanted"] and not visit["sold"]:
                return True  # sell first, next round
            cost = read_cost(context)
            if cost is None:
                log("shop: the Cost reads nothing: no refresh")
                return acted
            image = screen(context)
            fees = {k: number(text(context, image, roi)) for k, (_, roi) in REFRESH.items()}
            choice = shop.refresh_choice(cost, reserve, visit["refreshes"], team["shop_refresh_limit"],
                                         fees["normal"], fees["keyword"], data("shop.yaml")["refresh_margin"])
            if not choice:
                return acted
            page_guard(context, "Shop")
            if choice == "keyword":
                tap_settled(context, *REFRESH[choice][0])  # the keyword dialog zooms in
                if not tap_keyword(context, keyword):
                    log("shop: no keyword dialog on the refresh")
                    Shop.to_main(context)
                    return acted
                page_guard(context, "Shop")
                tap(context, *KEYWORD_REFRESH, wait=0)
            else:
                tap(context, *REFRESH[choice][0], wait=0)
            # The Cost drops, then the offers reload (CONNECTING): read them once both are done.
            until(context, lambda im: cost_in(context, im) not in (None, cost), timeout=3)
            still(context, timeout=1.5)
            after = read_cost(context)
            log(f"shop: {choice} refresh for {fees[choice]}: {cost} -> {after} Cost")
            if after == cost:
                Shop.to_main(context)
                return acted
            visit["refreshes"] += 1
            visit["sold"] = False
            acted = True

    @staticmethod
    def buy_offers(context, team, visit):
        """Read the offers once, then buy the main-keyword ones shop.buy_plan picks, last cell first; how many bought.

        A gift's keyword is its offer's badge (read_cells, #76); only an offer whose badge is unread is opened
        to read its purchase dialog (spec 03 section 12's text rule). Each purchase is checked on the Cost.
        """
        keyword, reserve = team["keyword"], team["reserve_cost"]
        visit["wanted"] = None
        # ponytail: only the offers on show; a Super Shop's last 2 of 10 need a scroll first.
        cost = read_cost(context)
        if cost is None:
            log("shop: the Cost reads nothing: nothing bought")
            return 0
        image = screen(context)
        slots = [s for s in shop.read_slots(ocr(context, image, OFFER_GRID)) if shop.on_sale(s)]
        avoided = avoided_gifts(team)
        cells = {c["i"]: c for c in read_cells(context, image, [offer_cell(s) for s in slots], "offer", avoided)}
        avoid = [g["name"] for g in avoided]
        offers = []
        for i, slot in enumerate(slots):
            cell = cells.get(i, {"tier": None, "keyword": None, "gift": None})
            if cell["gift"] in avoid or any(rewards.names_gift(slot["name"], n) for n in avoid):
                log(f"shop: {slot['name']!r} {slot['price']}: the team does not hold it (#90)")
                continue
            slot["short"] = slot["short"] or shop.short_cell(image, *offer_cell(slot))
            if slot["short"] and slot["price"] <= cost:
                log(f"shop: {slot['name']!r} is tagged Not Enough Cost: its price {slot['price']} is a misread")
                continue
            kind = cell["keyword"]
            if kind is None and shop.buyable(slot, cost):
                kind = Shop.dialog_keyword(context, slot, keyword, avoid)
                if kind is False:
                    return 0  # the shop is gone
            log(f"shop: {slot['name']!r} {slot['price']}: tier {cell['tier']} {kind}")
            if kind == keyword:
                offers.append((i, cell["tier"], slot["price"]))
        plan, visit["wanted"] = shop.buy_plan(offers, cost, reserve, visit["sold"])
        if visit["wanted"]:
            log(f"shop: the first choice costs {visit['wanted']}, {cost} Cost is short: sell first")
        bought = 0
        for i in plan:
            slot = slots[i]
            image = Shop.open_offer(context, slot)
            if image is None:
                if not Shop.to_main(context):
                    return bought
                continue
            price = shop.dialog_price(cost, text(context, image, PURCHASE_PREVIEW)) or slot["price"]
            if not shop.can_spend(cost, price, reserve):
                tap_settled(context, *PURCHASE_CANCEL, timeout=1.0)
                log(f"shop: {slot['name']!r} costs {price}, {cost} Cost is short")
                continue
            page_guard(context, "Shop")
            tap(context, *PURCHASE, wait=0)
            gift_get(context)
            after = read_cost(context)
            log(f"shop: bought {slot['name']!r} for {price}: {cost} -> {after} Cost")
            if after is None or after == cost:
                log("shop: the Cost did not change; taking it as not bought")
                Shop.to_main(context)
                continue
            cost, bought = after, bought + 1
        return bought

    @staticmethod
    def open_offer(context, slot):
        """Tap an offer; the screenshot of its purchase dialog, or None when none opened."""
        # Its text and Cost preview are read once it stops.
        page_guard(context, "Shop")
        image = tap_shown(context, slot["x"], slot["y"] - 50, shows(context, DIALOG_TITLE, "Purchase"), timeout=1.5, rest=1.0)
        if image is not None:
            return image
        log(f"shop: {slot['name']!r} opened no purchase dialog")
        return None

    @staticmethod
    def dialog_keyword(context, slot, keyword, avoid=()):
        """An offer's keyword from its purchase dialog's text: keyword when main, else "other" (an avoided gift too);
        None when no dialog opened, False when the shop is gone (to_main). The dialog is cancelled."""
        image = Shop.open_offer(context, slot)
        if image is None:
            return None if Shop.to_main(context) else False
        kind = rewards.gift_kind(text(context, image, PURCHASE_TEXT), keyword, False, avoid)
        tap_settled(context, *PURCHASE_CANCEL, timeout=1.0)
        return keyword if kind == "main" else "other"

    @staticmethod
    def sell(context, team, visit):
        """Sell the materials no fusion uses (fusions' leftovers, #79) when a wanted main gift is too dear.

        Kept like the fusion's (read_cells, cell_role): the team's kept keywords and gifts (#77) are never sold. A cell
        is tapped for its panel only when its badge or its price is below the grid's edge (tooltip_use).
        """
        wanted = visit["wanted"]
        if not wanted or visit["sold"]:
            return False
        visit["sold"] = True
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["sell"], shows(context, DIALOG_TITLE, "Sell"), timeout=2) is None:  # the grid slides in
            Shop.to_main(context)
            return False
        cost = read_cost(context, SELL_COST)
        if cost is None:
            log("shop: the sell page's Cost reads nothing: nothing sold")
            Shop.to_main(context)
            return False
        # One screenshot decides (#112): each cell's badge and icon, its price under it.
        image = screen(context)
        avoid = [g["name"] for g in avoided_gifts(team)]
        cells = read_cells(context, image, SELL_CELLS, "sell", kept_icons(team) + avoided_gifts(team) + VESTIGE_ICONS)
        roles = [cell_role(c, team, "sell", avoid) for c in cells]
        prices = shop.cell_prices(ocr(context, image, SELL_GRID), SELL_CELLS)
        log("shop: sell cells " + "; ".join(f"{cell_line(c, r)} {prices.get(c['i'])}" for c, r in zip(cells, roles)))
        gifts = [(c["i"], prices[c["i"]]) for c, r in zip(cells, roles) if r == "material" and c["i"] in prices]
        avoided = {c["i"] for c in cells if c["gift"] in avoid}  # sold first (#90)
        # The fusion still uses what may not be sold (#79): a vestige the team does not sell, a keywordless gift under
        # "fuse" (#161). Both are told off the grid: kept on the sell page, material on the fuse page.
        fuse_only = [c["i"] for c, r in zip(cells, roles) if r == "keep" and cell_role(c, team, "fuse", avoid) == "material"]
        # A badge or price below the grid's edge: the panel a tap shows decides (tooltip_use).
        for c, r in zip(cells, roles):
            if not (r == "unknown" or (r == "material" and c["i"] not in prices)):
                continue
            i, x, y = c["i"], c["x"], c["y"]
            page_guard(context, "Shop")
            tap_settled(context, x, y, timeout=1.2)
            image = screen(context)
            lines = [t for t, _ in ocr(context, image, SELL_PANEL)]
            panel = " ".join(lines)
            price = number(text(context, image, SELL_PRICE))
            use = tooltip_use(lines, team, avoid)
            if use in ("sell", "avoid") and price and not has(panel, "Select the"):
                gifts.append((i, price))
                if use == "avoid":
                    avoided.add(i)
            elif use != "keep":
                fuse_only.append(i)
            log(f"shop: sell cell {i}: {use}, {panel[:40]!r}")
        # The fusion is grouped without the avoided gifts, which are sold first (#90): a sale then breaks no group.
        # ponytail: a Super Shop's 5 slots are known once its fuse page was read; 3 until then.
        materials = [c for c in cells if (c["i"] in dict(gifts) or c["i"] in fuse_only) and c["i"] not in avoided]
        fused = {i for group, _ in fusions(materials, ["material"] * len(materials), visit.get("slots", 3), ()) for i in group}
        # Up to the team's sell_max_tier only (#161); an unread tier may be a V: not sold.
        tiers, top = {c["i"]: c["tier"] for c in cells}, team.get("sell_max_tier", 4)
        spare = [g for g in gifts if g[0] not in fused and (tiers[g[0]] or 9) <= top]
        picked = shop.to_sell(spare, wanted, cost, team["reserve_cost"], avoided)
        visit["fuse_scanned"] = visit.get("fuse_scanned") and not picked
        log(f"shop: {wanted} wanted, {cost} Cost, materials (cell, price) {gifts}, {sorted(fused)} fuse: sell {picked}")
        # The Cost read before any cell was picked: a picked cell shows "51 > 146", read as 51146 (#174).
        before = cost
        for i in picked or []:
            price = dict(gifts)[i]
            page_guard(context, "Shop")
            tap_settled(context, *SELL_CELLS[i], timeout=1.2)
            # Sell asks "Sell [<gift>] for <price> Cost?"; it slides down from the top before Confirm takes a tap (#174).
            page_guard(context, "Shop")
            if tap_shown(context, *PAGE_OK, shows(context, DIALOG_TEXT, r"Sell.*Cost"), timeout=2) is not None:
                tap(context, *DIALOG_CONFIRM, wait=0)
            # Only before + price is a sale: the preview of an unconfirmed one reads as 51146 (#174).
            sold = until(context, lambda im: cost_in(context, im, SELL_COST) == before + price, timeout=2)
            if sold is None:
                log(f"shop: sell cell {i} for {price}: not sold, {before} -> {read_cost(context, SELL_COST)} Cost")
                break
            log(f"shop: sold cell {i} for {price}: {before} -> {before + price} Cost")
            before += price
            still(context, timeout=1.5)  # the dialog goes as the Cost turns: the next cell's tap waits for it
        Shop.to_main(context)
        return bool(picked)

    @staticmethod
    def tooltip(context, last):
        """The tooltip of the cell just tapped: (its lines, its name), or ([], None) when none shows.

        Polled until a tooltip names a gift other than last: a stale read logged the same gift twice (#103).
        """
        for _ in range(8):
            time.sleep(0.2)
            lines = [(t, b) for t, b in ocr(context, screen(context), FUSE_TOOLTIP) if not has(t, "Owned")]
            head = tooltip_head(lines)
            if head:
                name = min(((b[1] - head[1], t) for t, b in lines if b[1] > head[1] + 10 and re.search(r"[a-z]{3}", t)),
                           default=(0, "?"))[1]
                if name != last:
                    return lines, name
        return [], None

    @staticmethod
    def recipe_shown(context, image, visit):
        """True, and the fuse page closed for this visit's owned gifts, when it shows a Fusion Available section.

        #103 (live 2026-10-17): the section lists a fixed recipe's result above E.G.O Gifts Owned and pushes
        the owned grid down, so FUSE_CELLS miss; the bot stuck on the page. Fixed recipes are #78's.
        """
        if not seen(context, image, "ShopFusionAvailable"):
            return False
        log("shop: the fuse page shows Fusion Available (a fixed recipe): closed, no fusion")
        visit["fuse_scanned"] = True
        Shop.to_main(context)
        return True

    @staticmethod
    def fuse(context, team, visit):
        """Fuse the materials shop.pick_fusion picks into the main keyword, Wishmaking left unticked; True when one fused.

        The cells are read off one screenshot (read_cells, #112): the gifts the team keeps stay (kept_keywords,
        kept_icons, #77), the rest are materials, the vestiges by their icon and the keywordless gifts by the team's
        setting (cell_role, #161). A cell whose badge is cut off is tapped for its tooltip (tooltip_use), and out
        again, only while the others make no fusion. Each material tapped in is read
        back (place); one that does not show closes the page unfused. One fusion a call, as the grid changes with it.
        A grid that made none is not read again until a purchase or a sale changes the owned gifts (#62).
        """
        if visit.get("fuse_scanned"):
            return False
        keyword = team["keyword"]
        # The page zooms in: a tap before it stops is lost.
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["fuse"], shows(context, DIALOG_TITLE, "Fuse"), timeout=2) is None:
            Shop.to_main(context)
            return False
        tap_settled(context, *FUSE_CENTRE)
        if not tap_keyword(context, keyword):
            log("shop: no keyword dialog on the fusion")
            Shop.to_main(context)
            return False
        tap_settled(context, *FUSE_KEYWORD_OK)
        if tooltip_up(context) and not Shop.close_tooltip(context):
            log("shop: a tooltip stays up on the fuse page: no fusion this visit")
            visit["fuse_scanned"] = True
            Shop.to_main(context)
            return False
        image = screen(context)
        if image[495:515, 263:283].max(axis=2).mean() > 60:  # unticked: V ~30
            log("shop: Wishmaking is ticked (it spends owned Starlight): no fusion")
            Shop.to_main(context)
            return False
        visit["slots"] = slots = shop.fuse_slots(image)  # before a recipe closes the page: the sale needs it too
        if Shop.recipe_shown(context, image, visit):
            return False
        # ponytail: the 15 cells on show; a scroll would find more when 13+ of them are kept.
        avoid = [g["name"] for g in avoided_gifts(team)]
        cells = read_cells(context, image, FUSE_CELLS, "fuse", kept_icons(team) + avoided_gifts(team) + VESTIGE_ICONS)
        roles = [cell_role(c, team, "fuse", avoid) for c in cells]
        log(f"shop: fuse cells ({slots} slots) " + "; ".join(cell_line(c, r) for c, r in zip(cells, roles)))
        picks = fusions(cells, roles, slots, avoid)
        if not picks and "unknown" in roles:
            roles = Shop.tooltip_roles(context, team, cells, roles, avoid)
            picks = fusions(cells, roles, slots, avoid)
        if not picks:
            visit["fuse_scanned"] = True
            log(f"shop: {roles.count('material')} materials on show, a fusion takes {shop.MIN_FUSION}")
            Shop.to_main(context)
            return False
        group, tier = picks[0]
        group = [next(c for c in cells if c["i"] == i) for i in group]
        materials = ", ".join(cell_line(c, "material").rsplit(":", 1)[0] for c in group)
        fused = False
        if Shop.place(context, group, slots) and not Shop.recipe_shown(context, screen(context), visit):
            # Read again on the still screenshot: the one that matched was taken while the dialog zoomed in.
            page_guard(context, "Shop")
            image = tap_shown(context, *PAGE_OK, shows(context, FUSE_CONFIRM, FUSE_COUNT), timeout=2)
            m = image is not None and re.search(FUSE_COUNT, text(context, image, FUSE_CONFIRM))
            if m and int(m[1]) == len(group):
                tap(context, 788, 583, wait=0)  # the dialog's Confirm; gift_get waits for its GET!
                fused = gift_get(context)
            log(f"shop: fuse {materials} into a tier {tier} {keyword} gift: {'done' if fused else 'not confirmed'}")
        # Unconfirmed or not read back: not the same scan again until the owned gifts change (#103).
        visit["fuse_scanned"] = not fused
        Shop.to_main(context)
        return fused

    @staticmethod
    def close_tooltip(context):
        """Close a tooltip the fuse page came back with, over the third row and Leave (the Shop node's anchor); False
        when one stays up.

        Live 2026-10-21: one stayed from a cell the grid had moved (Emerald Elytra) through every visit of the page. A
        neutral tap closes a cell's tooltip but left that one; a cell's own took its place: the first cell's, in and out
        (by hand: in, out with its tooltip still up, then the neutral tap). The page is told by its title before each:
        page_guard's Leave is under the tooltip (ADR 0007).
        """
        def on_fuse_page():
            if not has(text(context, screen(context), DIALOG_TITLE), "Fuse"):
                raise PageGone("Shop")
        on_fuse_page()
        tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)  # a tooltip fades
        if tooltip_up(context):
            on_fuse_page()
            tap_moved(context, *FUSE_CELLS[0], timeout=0.5)
            tap_moved(context, *FUSE_CELLS[0], timeout=1.2)  # out of the fusion again
            tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)
        return not tooltip_up(context)

    @staticmethod
    def tooltip_roles(context, team, cells, roles, avoid):
        """roles with each "unknown" cell (its badge cut off, no icon matched) decided by its tooltip (tooltip_use):
        tapped in for it, then out again. A gift the tooltip does not name is kept: live 2026-10-18, Spiderweb
        Entangled in Red's long tooltip read none.
        """
        roles, last = list(roles), None
        for n in [n for n, r in enumerate(roles) if r == "unknown"]:
            c = cells[n]
            x, y = c["x"], c["y"]
            page_guard(context, "Shop")
            tap(context, x, y, wait=0)
            lines, name = Shop.tooltip(context, last)
            if name is None:
                page_guard(context, "Shop")  # a tooltip that names nothing may be no shop at all
            tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)  # its tooltip fades: the next tap would land on it
            # A tooltip read is the fuse page, checked again once it is closed: a third-row cell's tooltip covers
            # Leave, the Shop node's anchor (live 2026-10-21, the bot looped on the fuse page under recovery).
            page_guard(context, "Shop")
            tap_moved(context, x, y, timeout=1.2)  # out of the fusion again
            tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)
            if name is None:
                log(f"shop: the gift at {x},{y} read no name: kept out of the fusion")
                roles[n] = "keep"
                continue
            last = name
            roles[n] = "keep" if tooltip_use([t for t, _ in lines], team, avoid) == "keep" else "material"
            log(f"shop: cell {c['i']} tooltip names {name!r}: {roles[n]}")
        return roles

    @staticmethod
    def place(context, cells, slots):
        """Tap cells into the fusion, each read back (#77); False at the first that does not show, nothing put in before.

        After a tap one slot more holds a material and the tapped cell's frame turns orange: the gift went in, and
        it is the one meant (the grid stays in place).
        """
        filled = shop.placed(screen(context), slots)
        if filled:
            log(f"shop: {filled} materials in before any tap: no fusion")
            return False
        for n, c in enumerate(cells, 1):
            page_guard(context, "Shop")
            tap_moved(context, c["x"], c["y"], timeout=0.5)
            tap_settled(context, *FUSE_NEUTRAL, timeout=1.0)  # closes its tooltip, which shades the grid
            image = screen(context)
            filled, framed = shop.placed(image, slots), shop.picked(image, c["x"], c["y"], CELL_PAGES["fuse"][1])
            if filled != n or not framed:
                log(f"shop: cell {c['i']} tapped: {filled} of {n} materials in, {'framed' if framed else 'not framed'}: no fusion")
                return False
        return True


# Settlement (spec 03 section 14): the Exploration Reward window.
RESULT = [300, 400, 100, 85]  # "Floor 5 [NORMAL] 6/6" under the floor icon
WEEKLY_LEFT = [440, 230, 65, 50]  # "n/3"
TOGGLE_X, TOGGLE_ROI = (558, 660, 763), (-45, 237, 90, 30)  # the 3 weekly-bonus toggles: x centre, roi offset
GIVE_UP, CLAIM = (393, 544), (887, 544)
REWARD_TITLE_ROI = [500, 100, 280, 45]
DIALOG_TEXT = [360, 280, 560, 140]
DIALOG_CANCEL, DIALOG_CONFIRM = (515, 493), (763, 493)


def toggles(context, image):
    """Each weekly-bonus toggle as True (ON), False (OFF) or None (unread)."""
    out = []
    for x in TOGGLE_X:
        dx, y, w, h = TOGGLE_ROI
        t = text(context, image, [x + dx, y, w, h], only_rec=True)
        out.append(False if has(t, "OFF") else True if has(t, "ON") else None)
    return out


@AgentServer.custom_action("Settle")
class Settle(CustomAction):
    """Goal check, weekly-bonus toggles, then Claim or GiveUpRewards; then the cursor and runs.jsonl (spec 03 section 14).

    Claim is pressed only after the toggles read back exactly as wanted; anything unexpected stops.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        if settlement.claim_dialog(text(context, image, DIALOG_TEXT)):
            tap(context, *DIALOG_CANCEL, wait=1.5)  # left over from an earlier try: back out and decide again
            return True
        lines = sorted(ocr(context, image, RESULT), key=lambda r: r[1][1])  # results come out of order
        result = settlement.read_result(" ".join(t for t, _ in lines))
        if not result:
            return True  # fading in: let MirrorHub look again
        floor, hard, cleared, total = result
        log(f"exploration reward: Floor {floor} [{'HARD' if hard else 'NORMAL'}] {cleared}/{total}")
        if not settlement.goal_met(result):
            return self.give_up(context, run, result)

        s, team = run["settings"]["run"], run["team"]
        left = number(text(context, image, WEEKLY_LEFT).split("/")[0])
        all_hard = run.get("planned", False) and run["difficulty"] == "hard" and team["hard_from_floor"] in (1, None)
        want = settlement.bonus_toggles(s["weekly_bonus_use"], s["weekly_bonus_amount"], hard, left or 0, all_hard)
        for _ in range(6):
            states = toggles(context, page_guard(context, "ExplorationReward"))
            on = [i for i, v in enumerate(states) if v]
            if None in states and len(on) <= want:
                time.sleep(1)  # an unread toggle may be ON: never claim on a guess
                continue
            if len(on) == want:
                break
            i = on[-1] if len(on) > want else states.index(False)
            tap(context, TOGGLE_X[i], 252, wait=1.5)
        else:
            return stop(context, f"weekly bonus toggles read {states}, want {want} ON: not claiming")
        log(f"weekly bonuses left {left}, use {s['weekly_bonus_use']}/{s['weekly_bonus_amount']}: toggles {states} verified, {want} ON")

        tap(context, *CLAIM, wait=2)
        for _ in range(5):
            image = screen(context)
            if not has(text(context, image, REWARD_TITLE_ROI), "Exploration Reward"):
                break
            # Live: Claim asks to confirm with bonuses left and none ON (2026-10-15), and with any ON (2026-10-16).
            # Confirm only the dialog of what the toggles were set and read back to; a bonus is spent only then.
            if settlement.claim_dialog(text(context, image, DIALOG_TEXT)) == ("bonus" if want else "no_bonus"):
                tap(context, *DIALOG_CONFIRM, wait=2)
                continue
            time.sleep(1)
        else:
            # Anything else, too few Enkephalin Modules most likely: nothing more is tapped, so nothing is bought.
            return stop(context, f"Claim did not close the window: {text(context, image, DIALOG_TEXT)!r}",
                        run_line(run, "stop", hard, settlement.floors_passed(result), want))
        log(f"claimed with {want} weekly bonus(es)")
        self.record(run, result, want, "clear")
        if run.get("planned"):
            cursor = next_cursor(run["settings"]["teams"], team["id"])
            if cursor:
                write_cursor(ROOT, address(context), cursor)
                log(f"rotation cursor -> {cursor}")
        else:
            log("team not picked by the bot this run: rotation cursor stays")
        RUN.clear()
        return True

    def give_up(self, context, run, result):
        """GiveUpRewards, then `End expedition without claiming rewards?` Confirm; no module is spent."""
        for _ in range(3):
            page_guard(context, "ExplorationReward")  # also under its give-up dialog (maatools: GiveUpDialog.png)
            tap(context, *GIVE_UP, wait=1.5)
            image = screen(context)
            if settlement.claim_dialog(text(context, image, DIALOG_TEXT)) == "giveup":
                break
        else:
            return stuck("GiveUpRewards brought up no `End expedition without claiming rewards?`")
        page_guard(context, "ExplorationReward", image=image)
        tap(context, *DIALOG_CONFIRM, wait=2)
        log("goal not met: gave up the rewards")
        self.record(run, result, 0, "giveup")
        RUN.clear()
        return True

    @staticmethod
    def record(run, result, bonuses, outcome):
        settlement.append_run(ROOT, run_line(run, outcome, result[1], settlement.floors_passed(result), bonuses))
        SETTLED["runs"] += settlement.counts_as_run(outcome)
        STUCK["ladder"] = recovery.Ladder()
