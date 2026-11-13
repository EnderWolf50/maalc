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
import gift_cells
import gift_search
import hub_text
import luxcavation
import lunacy
import map_route
import pack_cover
import pass_missions
import recovery
import rewards
import run_start
import settlement
import shop
from gifts import effective, main_keyword, purchases, recipe_fusion, resolve_list, state, want_kind
from ocrtext import compact, digits, floor_number, fraction, has, normalize
from ocrtext import fractions as text_fractions
from settings import GIFT_KEYWORDS, SettingsError, data_dir, gift_tables, load_settings, vestige_ids
from team_queue import migrate_cursor, pick_team, requeue, resumed_team

# Same <root> as main.ROOT; resource/ sits under it in a release, under assets/ in the repo.
ROOT = Path(__file__).resolve().parent.parent

# This run's plan, made on the entry page: {"settings", "team", "difficulty"}.
# Memory only (ADR 0003); an agent restarted mid-run makes one up from the team queue (current_run). TaskStart
# keeps it for the same task when the client interrupted the last one (no done, no stop): the run is picked up as before
# the task chain.
RUN = {}
# This task's own state (#364, ADR 0010), reset by TaskStart: the runs claimed since it started (the run count stop,
# spec 01; never saved), why it is done ("done", None while it runs), which ends it a success (TaskDone), its entry
# node, and "ended" once done() or stop() ended it. Set as a task needs them: "modules" and "gate_backs" (the mirror's new
# run gate), "settled" (a mirror run claimed or given up: none is under way until the next is planned, #436),
# "forfeits" (the forfeit reasons of the runs given up since the last claim: too many in a row stop the task, #560),
# "assemble" (Assemble Modules' reads and confirms), "charge" (Charge Enkephalin's count and its steps), "l3"
# (restart_game's restarts that went through, #520).
TASK = {"runs": 0, "done": None}
# Stuck detection and recovery (spec 06), memory only: the last node seen ("node", its id) and the
# screen type it handled ("kind"), a pending stuck for MirrorHub's Stuck node ("flag": (kind, start
# level, reason)), this run's Ladder, this launch's game restarts ("restarts", a recovery.Restarts), and the reason
# of an account-level stop this launch ("halted", #362 D8): every later task then fails at its entry; the TapUntil
# nodes with a settle whose tap the game took since its last recovery or restart, and when ("taken", #58).
STUCK = {"node": None, "kind": None, "flag": None, "watch": recovery.Watchdog(), "ladder": recovery.Ladder(),
         "restarts": recovery.Restarts(), "taken": {},
         "away": recovery.Away(),  # the game out of front while the hub recognises nothing (#530)
         "updates": 0,  # game restarts for update notices since this agent started (AcceptUpdate)
         "halted": None}
SCREENS = deque(maxlen=20)  # the last screens MirrorHub handed out: the evidence on a stop
LOG = deque(maxlen=500)


def end_battle():
    """The battle is over: the next one starts its turns and its clock afresh."""
    RUN.pop("turn", None)
    RUN.pop("battle_start", None)


WEEKLY_SLOTS = (922, 960, 998)  # x of the 3 Weekly Bonuses slots on the entry page, y 285-297
TEAM_LIST = [75, 292, 115, 245]
ENTER_DIALOG = [400, 325, 480, 45]  # "Will you enter ...?"
TEAM_TITLE = [220, 112, 210, 26]  # "TEAMS #n" over the card list
TO_BATTLE = (1145, 588)  # the team page's button before a Luxcavation battle
LEVEL_WARNING = [400, 230, 480, 90]  # "... lower than the recommended level ..."
STARLIGHT_HEADER = [890, 30, 115, 28]  # "Available"
STARLIGHT_DIALOG = [480, 210, 320, 35]  # "Continue with selected effects?"
STARTING_GIFT_HEADER = [780, 145, 230, 35]  # "Selected E.G.O Gift"
STARLIGHT_AVAILABLE = [1010, 30, 80, 28]
STARLIGHT_NOTE = [660, 395, 320, 90]  # the line under Convert Starlight to Cost: "unspent" when off, "remaining" when on
STARLIGHT_OWNED = [830, 30, 90, 28]  # "4035", "4035-60" while owned starlight pays
GRACE_ORIGIN_X, GRACE_ORIGIN_Y = (138, 152), (152, 390)  # top-left of card 1; step 198 px per column
PACK_TITLES = [120, 400, 1040, 100]  # up to 5 cards (live: 5 with two Theme Pack Selection +1 graces)
# #246, recordings: dealt cards slide in and swing until ~2.8 s after the deal; their titles are read once they stop.
PACK_CARDS = [120, 170, 1040, 360]
CARDS_SETTLE = 4.0  # s; a page still swinging by then is read anyway
# The theme pack page's Refresh button (frame, icon and word): lit while a free refresh is left, greyed once none is,
# with or without its `n/m` (#482: one free refresh shows none). How many of its px are brighter than REFRESH_BRIGHT
# (max channel), on the pack pages of 46 live runs' recordings (2026-10-22 to 11-07, 288 frames): lit 765-2108 (253
# frames), greyed 0 (35 frames, the brightest px 54-56). The ThemePack captures of tests/screens: lit 1176-1321, greyed 0.
REFRESH_BUTTON = (1001, 25, 163, 45)
REFRESH_BRIGHT, REFRESH_LIT_MIN = 120, 100


def log(msg):
    LOG.append(f"{time.strftime('%H:%M:%S')} {msg}")
    print(f"[maalc] {msg}", flush=True)


def screen(context):
    return context.tasker.controller.post_screencap().wait().get()


def tap(context, x, y, wait=1.0):
    context.tasker.controller.post_click(x, y).wait()
    time.sleep(wait)


def back(context):
    """Android's back key (BACK_KEY)."""
    context.tasker.controller.post_click_key(BACK_KEY).wait()


def box_centre(box):
    """(x, y) of an [x, y, w, h] box's centre."""
    x, y, w, h = box
    return x + w // 2, y + h // 2


def param(raw, default=None):
    """A node's custom_action_param or custom_recognition_param, parsed; default when it is empty."""
    return json.loads(raw) if raw else default


def next_names(context, node):
    """The names of the node's next list, in order."""
    return [n["name"] for n in context.get_node_data(node)["next"]]


def flag_hit(**detail):
    """A recognition hit on a state, not a place on screen: its box the screen's first pixel."""
    return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail=detail)


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


def gone(context, spec, image):
    """A done(image) for until(): the words of spec ({"roi", "expected"}) that matched in image read there no more.

    Their own words, not the whole pattern: ClaimPopup's Rewards Acquired turns into Pass Level Up, which the same
    pattern matches. Nothing matching in image: nothing to wait for, done at once.
    """
    found = re.search(spec["expected"], normalize(text(context, image, spec["roi"])), re.I)
    return lambda image: found is None or found[0] not in normalize(text(context, image, spec["roi"]))


def tap_then(context, x, y, done, timeout=2.0, lively="HomeReached"):
    """Tap, then until() done(image) holds: that image, or None after timeout s (#115).

    The wait also tells the watchdog whether the game took the tap (#440): no page, every screenshot of the wait the
    same as its first to the byte (a frozen game repeats its bytes), and that screenshot the screen of lively, a node of
    recovery.LIVELY (the main window, whose banners always move on a live game; the title for its own tap, #506), is a
    dead tap. Not other still pages: a live game's map, or the title under a dialog, can let a tap go by.
    recovery.DEAD_TAPS of them in a row flag the game frozen, a stuck from L3, for the hub's Stuck node (GoHome's
    HomeFrozen).
    """
    shots = {"first": None, "still": True}

    def watch(image):
        if shots["first"] is None:
            shots["first"] = image
        elif shots["still"] and not np.array_equal(image, shots["first"]):
            shots["still"] = False
        return done(image)

    tap(context, x, y, wait=0)
    image = until(context, watch, timeout=timeout)
    first = shots["first"]
    dead = image is None and shots["still"] and seen(context, first, lively) is not None
    if why := STUCK["watch"].tapped(recovery.thumb(first) if dead else None):
        stuck(f"{recovery.LIVELY[lively]} {why}", level=3)
    return image


def log_change(node, image, began):
    """Log how long the screen after a node's tap or key took to come, from before it (image: until()'s, None when it
    never did); a live run reads each wait from these lines (#254)."""
    log(f"{node}: {'screen changed' if image is not None else 'no change'} after {time.monotonic() - began:.1f} s")


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


def still(context, timeout=2.0, roi=None, share=0.03, runs=1):
    """The first screenshot that looks like the one 0.2 s before it: a fade in or out has ended; None after timeout s.
    With roi (x, y, w, h), only that part is compared; share is recovery.same_screen's. runs: that many alike pairs
    in a row, for a swing, which looks alike 0.1 s either side of its turn (#246).

    MirrorHub, polling every 300 ms, can hand out a page while it is still fading in or the last one fading out.
    """
    def thumb(image):
        if roi:
            x, y, w, h = roi
            image = image[y:y + h, x:x + w]
        return recovery.thumb(image)
    last, alike = [thumb(screen(context))], [0]

    def done(image):
        small = thumb(image)
        alike[0] = alike[0] + 1 if recovery.same_screen(last[0], small, share) else 0
        last[0] = small
        return alike[0] >= runs
    return until(context, done, timeout=timeout, least=0.2)


class PageGone(Exception):
    """The page an action works on went away mid-action (#118): by hand, a popup, a disconnect."""


class PageEnded(PageGone):
    """The page gave way to the one it ends on (ENDS_ON)."""


def on_page(context, image, *nodes):
    """The first of nodes (MirrorHub's screen nodes) that hits on image, or None."""
    return next((n for n in nodes if seen(context, image, n)), None)


POPUPS = ("Connecting", "RetryPopup", "PopupButton")  # MirrorHub's global popups: answered before any page
# Windows that leave a page's anchor readable under them, answered by MirrorHub before that page. #213: a GET! window
# over the map after a fight leaves its buttons (MirrorMap) lit. Not the shop's: Shop closes its own GET! windows.
COVERS = {"MirrorMap": ("GiftGet",)}
# Windows that hide a page's anchor where the action's own taps close them anyway: they pass its guard as its page.
# #309: an event's GET! windows, over its page or the map it ends on, close on any tap, the text taps on the dead corner too.
TAPPED_THROUGH = {"Event": ("GiftGet",)}
# The page an action's page gives way to, looked for after its own and its TAPPED_THROUGH windows: seen, the page is gone
# without the 1 s look again (#511). MirrorMap hits under the GET! windows an event ends with too: GiftGet first.
ENDS_ON = {"Event": ("MirrorMap",)}


def page_guard(context, home, image=None):
    """Before a tap: a screenshot that still shows home (MirrorHub's node for the action's page) or one of its
    TAPPED_THROUGH windows; PageEnded at once on the page it ends on (ENDS_ON); else PageGone.

    ADR 0007, #118: an action that taps on for long checks its page first, so a screen changed under it is
    handed back to MirrorHub at once instead of tapped blind until the action gives up. A miss is looked at
    again for up to 1 s: a page fading or a dialog dropping in can hide its anchor for a moment.
    A global popup reads through to the page under it (maatools: the title's nodes hit under RetryCountdown.png), so
    one of POPUPS showing is the page gone too: MirrorHub answers it first. So is one of home's COVERS.
    image: a screenshot just taken, looked at first.
    """
    pages, ends = (home, *TAPPED_THROUGH.get(home, ())), ENDS_ON.get(home, ())

    def shown(im):
        page = on_page(context, im, *POPUPS, *COVERS.get(home, ()), *pages, *ends)
        if page in ends:
            raise PageEnded(home)
        return page in pages

    if image is not None and shown(image):
        return image
    image = until(context, shown, timeout=1.0)
    if image is None:
        raise PageGone(home)
    return image


def hub_name(context):
    """The hub of the task under way, for the log: the first node down its entry's next chain that lists TaskDone, as
    every hub does (#364). MirrorDungeon's is MirrorHub, ExpLuxcavation's ExpHub (live-1 F4), past the pass page's hub,
    which lists no TaskDone (#429): the chain goes on through the first next that has a next of its own, not a hub's
    Stuck node. The entry itself is not one, though ChargeEnkephalin's next list also names TaskDone (a count of 0
    ends there)."""
    entry = name = TASK.get("entry") or "MirrorDungeon"
    for _ in range(8):
        data = context.get_node_data(name) or {}
        nexts = [n["name"] for n in data.get("next", [])]
        if "TaskDone" in nexts and name != entry:
            return name
        if not (nexts := [n for n in nexts if n != "TaskDone" and (context.get_node_data(n) or {}).get("next")]):
            break
        name = nexts[0]
    return "the hub"


def hands_back(run):
    """An action's run(): PageGone ends it with True, for the task's hub (MirrorHub, ExpHub, ...) to look at the screen
    now up (#118). SettingsError (settings that do not load, as when current_run makes the run plan up after a restart
    mid-run) ends it through the stop procedure, as any bad settings do (#668)."""
    @functools.wraps(run)
    def wrapped(self, context, argv):
        try:
            return run(self, context, argv)
        except PageGone as e:
            log(f"{type(self).__name__}: {e} is gone: back to {hub_name(context)}")
            return True
        except SettingsError as e:
            return stop(context, str(e))
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


def scroll(context, x, y, dx, dy, ignored=None):
    """Drag the content under (x, y) by (dx, dy) px and let go without a fling (spec 07).

    The game's drag threshold eats the first move, so the finger first moves 10 px and rests 0.1 s (a move
    right after it can be eaten too), then moves (dx, dy) in 20 px moves 10 ms apart. The game flings the content
    on with the speed the finger still has at the lift, decaying while it rests, so it rests SCROLL_HOLD s first.
    ignored(image) judges a screenshot taken as the rest starts: when it says the content did not follow the finger,
    nothing moves to fling, so the finger lifts at once and that screenshot is returned (#486). Else None, the
    screenshot's time taken out of the rest.
    """
    d = max(abs(dx), abs(dy), 1)
    lx, ly = x + round(10 * dx / d), y + round(10 * dy / d)
    press(context, [(x, y), (lx, ly), (lx + dx, ly + dy)], settle=0, dwell=0.1, pause=0.01, step=20)
    end = time.monotonic() + SCROLL_HOLD
    image = screen(context) if ignored else None
    stayed = image is not None and ignored(image)
    if not stayed:
        time.sleep(max(0.0, end - time.monotonic()))
    context.tasker.controller.post_touch_up().wait()
    return image if stayed else None


# Live 2026-10-18 (#114): with these moves (~1000 px/s) a 0.55 s rest left at most 1 px of fling in 126 drags of
# 50-300 px on the map, the team list and the gift grid, 0.62-0.77 s each (1 px and 0.73-1.25 s before);
# 0.5 s left 2 px, 0.4 s 6 px. Resting 0.05 s after the threshold move, 1 drag in ~200 lost a whole 20 px move.
# At ~330 px/s the fling was +1/+6/+19/+58/+176 px for 0.5/0.3/0.2/0.1/0 s.
SCROLL_HOLD = 0.55


def drag(context, points, settle=0.3, dwell=0.1, hold=0.0, pause=0.02, step=10):
    """One touch through points: down on the first, settle s, then step px moves pause s apart, dwell s on each point.

    Lifts on the last point after hold s; at once by default: a finger held on a battle skill opens its details.
    """
    press(context, points, settle, dwell, pause, step)
    time.sleep(hold)
    context.tasker.controller.post_touch_up().wait()


def press(context, points, settle, dwell, pause, step):
    """drag without its rest and lift: the finger goes down and moves through points, and stays down on the last."""
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


def ocr(context, image, roi, only_rec=False):
    """Every OCR result in roi as (text, (x, y, w, h)); only_rec reads roi as one line, no text detection."""
    detail = context.run_recognition("ReadText", image, {"ReadText": {"recognition": "OCR", "roi": roi, "only_rec": only_rec}})
    return [(r.text, tuple(r.box)) for r in (detail.all_results if detail else [])]


def text(context, image, roi, only_rec=False):
    return " ".join(t for t, _ in ocr(context, image, roi, only_rec))


def number(s):
    found = re.sub(r"\D", "", s)
    return int(found) if found else None


def module_count(context, image):
    """The Enkephalin Modules the bottom-left panel shows (main window, Drive, Luxcavation, any page with the panel); None
    when the panel is not on the screen or its number does not read (#367).

    The panel's x moves between pages, so the round Module icon is found first (ModuleIcon) and the digits read as one
    line to its right: the dark field ends 78 px after the icon's left edge, its digits right-aligned.
    """
    detail = context.run_recognition("ModuleIcon", image)
    if not detail or not detail.hit:
        return None
    x, y, w, h = detail.best_result.box
    return digits(text(context, image, [x + w + 2, y + 2, 50, h - 4], only_rec=True))


def address(context):
    return context.tasker.controller.info.get("adb_serial", "default")


def run_team(settings, team):
    """The team a run plays: the settings' team plus `list`, the gift list it uses, and `keyword`, its main keyword, which
    that list decides (spec 04 section 13)."""
    gift_list = resolve_list(team["gift_list"], settings["gift_lists"])
    return {**team, "list": gift_list, "keyword": main_keyword(gift_list)}


def current_run(context):
    """The run plan; made up from settings and the team queue when the agent restarted mid-run."""
    if "settings" not in RUN:  # a run plan, not just counters left by an action
        settings = load_settings(ROOT, need_team=True)
        run = settings["run"]
        # The weekly bonuses left when the run began are not known: the difficulty is known when both answers agree.
        began = {run_start.run_difficulty(run["difficulty"], left, run["target_floor"]) for left in (0, 1)}
        difficulty = began.pop() if len(began) == 1 else None
        team, known = resumed_team(settings["teams"], difficulty)
        RUN.update(settings=settings, team=run_team(settings, team), difficulty=difficulty, planned=known)
        # The guard turns left are unknown after a restart: they count as used up (spec 03 section 8).
        how = "from the team queue" if known else "assumed: the team queue does not tell the run's team"
        log(f"no run plan in memory: team {team['name']!r} {how}, difficulty {difficulty or 'unknown'}, no guard turns")
    return RUN


# Stuck detection, recovery and the stop procedure (spec 06).
def stuck(reason, level=1):
    """Hand the screen being handled to recovery: the hub's Stuck node picks it up next (MirrorHub's Recover, a daily
    hub's DailyRecover). level: the least recovery level it starts at.

    Returns True, for the action to return: its [JumpBack] leads to the hub.
    """
    log(f"stuck: {reason}")
    STUCK["flag"] = (None, level, reason)  # StuckFlag fills in the screen type
    return True


def done(reason):
    """This task has nothing left to do (#364): TaskDone, next on the hub, ends it a success and the client's list goes
    on. Not the stop procedure: no evidence, no runs.jsonl line, no webhook.

    Returns True, for the action to return: its [JumpBack] leads to the hub.
    """
    log(f"done: {reason}")
    TASK.update(done=reason, ended=True)
    return True


def run_line(run, outcome, hard, floors, bonuses=0):
    """This run's runs.jsonl line (spec 06 執行記錄)."""
    team = run["team"] if run.get("planned") else None
    counts = STUCK["ladder"].counts
    target = run.get("settings", {}).get("run", {}).get("target_floor", 5)
    return {
        "start": run.get("start"), "end": settlement.now(),
        "team": team and team["id"], "team_name": team and team["name"],
        "difficulty": None if hard is None else "hard" if hard else "normal", "weekly_bonus": bonuses,
        "target": target, "floors": floors, "target_reached": settlement.target_reached(floors, target),
        "result": outcome, "l1": counts[1], "l2": counts[2], "l3": counts[3],
        **({"gift_search": run["gift_search"]} if "gift_search" in run else {}),
    }


def stop(context, reason, line=None, whole_list=False):
    """The stop procedure (spec 06 停止程序): evidence, a `stop` line in runs.jsonl, the webhook.

    line is this run's line when the caller knows it better (Settle); otherwise one is made up from the run plan, in a
    Mirror Dungeon task that stops before it touched the run too, unless it ended one already (#436). whole_list: an account-level stop (maintenance,
    an outdated client, a download or the terms with their auto setting off, an update that keeps coming back), which
    every later task would meet too: post_stop then empties the client's queue (#364). Returns False, for the action to
    return: that ends the task.
    """
    log(f"stop: {reason}")
    TASK["ended"] = True
    if line is None and TASK.get("entry") == "MirrorDungeon" and not TASK.get("settled"):
        try:
            current_run(context)
        except SettingsError as e:
            log(f"no runs.jsonl line: {e}")
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
    settings = settings_now()
    url = settings and settings["run"]["webhook_url"]
    if url:
        body = json.dumps({**(line or {}), "reason": reason, "evidence": str(folder)}, ensure_ascii=False).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=10).close()
            log("webhook sent")
        except (OSError, ValueError) as e:
            log(f"webhook failed: {e}")
    if whole_list:
        log("account-level stop: the rest of the task list is cancelled")
        STUCK["halted"] = reason  # a client that hands over one task at a time (MFAAvalonia) is not reached by post_stop
        context.tasker.post_stop()
    return False


@AgentServer.custom_action("TaskStart")
class TaskStart(CustomAction):
    """A task's entry node (#364, ADR 0010): a task list runs its tasks on one agent, so what the last task left in
    memory goes: its Ladder, the watchdog, the screens kept for evidence, this task's runs and restarts. The run goes too
    once the last task ended (done, stop); one the client interrupted stays for the same task, which picks it up (#362 D3).
    The failed game restarts in a row and the update restarts (STUCK restarts, updates) still count per bot launch. After
    an account-level stop this launch the task fails here, before any tap, evidence or webhook (#362 D8): it would meet
    the same screen."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if STUCK["halted"]:
            log(f"skip: account-level stop earlier this launch ({STUCK['halted']}): {argv.node_name} not run")
            return False
        if TASK.get("ended", True) or TASK.get("entry") != argv.node_name or "settings" not in RUN:
            RUN.clear()
        else:
            log(f"the last {argv.node_name} was interrupted: its run is picked up")
        TASK.clear()
        TASK.update(runs=0, done=None, entry=argv.node_name, ended=False)
        STUCK.update(node=None, kind=None, flag=None, watch=recovery.Watchdog(), ladder=recovery.Ladder())
        SCREENS.clear()
        log(f"task {argv.node_name} started")
        if argv.node_name == "MirrorDungeon" and (note := migrate_cursor(ROOT, address(context))):
            log(note)
        return True


# A hub's own steps, no screen: the watchdog keeps the screen handled before them. The hubs themselves are found by
# their next list, which names the Stuck node (StuckFlag). ChargePanel and the pass missions' claims repeat on the same
# picture on purpose (a window that stays open after Confirm, a row to claim after a row): a count of them is not a stuck,
# so each bounds itself (ChargePanel's reads and Cancels, the claims' max_hit).
PASS_NODES = ("BattleHUD", "BattleHUDLost", "HubText", "HubTextLost", "ExpText", "ExpTextLost", "ChargePanel",
              "PassDailyClaim", "PassWeeklyClaim", "PassSeasonalClaim", "PassSeasonalEndClaim")


@AgentServer.custom_recognition("StuckFlag")
class StuckFlag(CustomRecognition):
    """A hub's Stuck node (MirrorHub's Stuck, ExpStuck, AssembleStuck ...): watches every screen the hub hands out, hits while
    a stuck waits for recovery.

    It runs first on each pass of a hub, so the task's last node is the screen just
    handled and argv.image what it left: the watchdog, the evidence and the run time limit work from them. A pass with
    no node handled since the last one may read the foreground (Away): the game out of front for a while starts a stuck
    at L3, sooner than the hub's timeout (#530).
    """

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        ids = argv.task_detail.node_id_list
        now = time.monotonic()
        if ids and ids[-1] != STUCK["node"]:
            STUCK["node"] = ids[-1]
            STUCK["away"].handled(now)
            node = context.tasker.get_node_detail(ids[-1])
            if node and node.name not in ("MirrorDungeon", "GlobalStuck", argv.node_name, *PASS_NODES) and not self.hub(context, node.name, argv.node_name):
                self.see(node.name, argv.image)
        elif not STUCK["flag"] and STUCK["away"].due(now) and (why := STUCK["away"].read(foreground(context), now)):
            self.away(why, argv.image)
        if STUCK["flag"] and STUCK["flag"][0] is None:
            STUCK["flag"] = (STUCK["kind"], *STUCK["flag"][1:])  # reported by the action of the node just handled
        return flag_hit() if STUCK["flag"] else None

    @staticmethod
    def hub(context, name, stuck_node):
        """Whether the node is a hub, not a screen: its next list holds this Stuck node."""
        return stuck_node in next_names(context, name)

    @staticmethod
    def away(why, image):
        """The game out of front while the hub recognised nothing: a stuck at L3, as Recover gives a hub timeout with the
        game out of front (#86), on the same screen type, and its screen kept in logs/unknown/ as a timeout keeps it."""
        keep_unknown(image)
        reason = f"nothing recognised; {why}"
        log(f"stuck: {reason}")
        STUCK["flag"] = (nothing_recognised(), 3, reason)

    @staticmethod
    def see(kind, image):
        STUCK["kind"] = kind
        SCREENS.append(image)
        STUCK["ladder"].progress(kind)
        STUCK["restarts"].progress(kind)
        if STUCK["flag"]:
            return
        if kind == "Downloading":  # the game is away; the floor gets its whole time once the download is done
            restart_floor_clock()
        if why := STUCK["watch"].see(kind, recovery.thumb(image), time.monotonic()):
            stuck(f"{kind}: {why}")
        elif recovery.over_time(kind, RUN.get("deadline"), time.time()):
            RUN.pop("deadline")  # once a floor: the next floor starts the clock again
            stuck(f"floor {RUN.get('floor', '?')} over its time limit", level=2)


AgentServer.custom_recognition("HubText")(hub_text.HubText)


@AgentServer.custom_recognition("GameAway")
class GameAway(CustomRecognition):
    """GoHome's HomeGameAway: hits when another app (the launcher, the Play Store) or no window has the focus, so the
    game is started without waiting for a hub timeout (#365). Not when the front package cannot be read."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        app = foreground(context)
        return flag_hit(app=app) if app not in (None, recovery.GAME) else None


@AgentServer.custom_recognition("LuxCountMode")
class LuxCountMode(CustomRecognition):
    """Hits when the Luxcavation task LuxStart began runs in count mode (#431): ExpCountMode, which skips the pass page."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        return flag_hit() if RUN["lux"]["mode"] == "count" else None


# The Luxcavation tasks (#366, #368): their settings key (custom_action_param of LuxStart) -> name, Modules a battle.
LUX = {"exp": ("EXP Luxcavation", luxcavation.EXP_COST), "thread": ("Thread Luxcavation", luxcavation.THREAD_COST)}


@AgentServer.custom_action("LuxStart")
class LuxStart(TaskStart):
    """A Luxcavation task's entry (#366, #368), its param the settings key ("exp", "thread"): TaskStart, then the team
    luxcavation.<key> names, whose guard turns the battle plays (spec 03 section 8), its mode (#431), count and retries (#367).
    No team picked, or settings that do not load: the stop procedure, before any tap."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not super().run(context, argv):
            return False
        key = json.loads(argv.custom_action_param)
        name, cost = LUX[key]
        try:
            settings = load_settings(ROOT)
        except SettingsError as e:
            return stop(context, str(e))
        opts = settings["luxcavation"][key]
        team = next((t for t in settings["teams"] if t["id"] == opts["team"]), None)
        if team is None:
            return stop(context, f"{name} has no team: pick one in the settings GUI's Daily tab")
        # Not RUN["settings"]: that is a Mirror Dungeon run, which the stop procedure writes to runs.jsonl.
        # lux: this task's battles (spec 03 section 15): mode, daily or count (#431); target, count's wins this run or the
        # day's in daily mode (luxcavation.DAILY); today, those won today as read (plan) and seen, what was read, for the
        # log; fights, the battles this run fights, None until planned; the battles won and the retries used, the last
        # battle's result.
        mode = opts["mode"]
        target = opts["count"] if mode == "count" else luxcavation.DAILY[key]
        RUN.update(team=team, guard=team["guard_turns"],
                   lux={"name": name, "cost": cost, "mode": mode, "target": target, "today": None, "seen": None, "fights": None,
                        "retries": opts["retries"], "modules": None, "won": 0, "retried": 0, "result": None,
                        "consecutive": opts["consecutive"], "size": 1})
        log(f"{name}: team {team['name']!r} (TEAMS #{team['game_team']}), {team['guard_turns']} guard turns, "
            + (f"mode count, {target} wins this run" if mode == "count" else "mode daily")
            + f", {opts['retries']} retries, consecutive {'on' if opts['consecutive'] else 'off'}")
        return True


def modules_now(context, timeout=3):
    """The Modules the panel shows now (module_count), looked for up to timeout s: None when it never reads."""
    found = []
    until(context, lambda image: found.append(module_count(context, image)) or found[-1] is not None, timeout)
    return found[-1]


@AgentServer.custom_action("OpenDrive")
class OpenDrive(CustomAction):
    """NavDrive: the Drive page has the Modules panel (tests/screens/Drive.png), the entry page the next tap opens has
    none. Read the number for PlanRun's gate (#369) before tapping Mirror Dungeons; None when it does not read. Then
    until the entry page's text shows (param {"next": {"roi", "expected"}, "timeout": s}), not a fixed 3 s (#58)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        TASK["modules"] = module_count(context, screen(context))
        p = json.loads(argv.custom_action_param)
        began = time.monotonic()
        image = tap_then(context, *box_centre(argv.box), shows(context, p["next"]["roi"], p["next"]["expected"]),
                         timeout=p["timeout"])
        log_change(argv.node_name, image, began)
        return True


@AgentServer.custom_action("LuxHome")
class LuxHome(CustomAction):
    """A Luxcavation task's step after LuxStart (EXP in daily mode: after the pass page): the main window, then the Modules
    the panel shows (#367). A panel that does not read stops the task: nothing is known to be safe to spend. Count mode
    plans the task here, as does the param {"plan": true} (EXP, whose battles won today were read on the pass page);
    Thread in daily mode plans on the Thread tab, where its Daily Bonuses show (LuxEnter)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not go_home(context):
            return False
        lux = RUN["lux"]
        lux["modules"] = modules_now(context)
        if lux["modules"] is None:
            return stop(context, f"{lux['name']}: the Modules number did not read on the main window")
        log(f"{lux['name']}: Modules {lux['modules']} on the main window")
        if lux["mode"] == "count" or (param(argv.custom_action_param) or {}).get("plan"):
            over = plan(context, lux["today"], lux["seen"])
            return True if over is None else over
        return True


def plan(context, today, seen):
    """The battles this run fights (luxcavation.fights): count mode, the target; daily mode (#429), the day's target less
    `today`, the battles won today as read (None: it did not read), `seen` what was read, for the log. Nothing read or
    nothing left: the main window and done, nothing fought; else the Modules must cover the battles at the hardest
    stage's cost (spec 03 section 15), or the task is skipped the same way. None: RUN["lux"]["fights"] is set and the
    battles go on; else what the action returns."""
    lux = RUN["lux"]
    fights = luxcavation.fights(lux["mode"], lux["target"], today)
    if fights is None:
        return finish(context, f"{lux['name']}: {seen}: nothing fought")
    lux["today"] = today
    head = (f"{lux['name']}: count mode, {fights} this run" if lux["mode"] == "count"
            else f"{lux['name']}: {seen} ({today} won today), {lux['target']} a day")
    if fights == 0:
        return finish(context, f"{head}: nothing to fight")
    need = luxcavation.needed(lux["cost"], fights)
    if luxcavation.decide(lux["modules"], lux["cost"], fights, 0, 0, lux["retries"]) == luxcavation.SKIP:
        return finish(context, f"{head}: Modules {lux['modules']} < {need} needed for {fights}, skipped")
    lux["fights"] = fights
    log(f"{head}: Modules {lux['modules']} >= {need} needed, fight {fights}")
    return None


@AgentServer.custom_action("ExpPassRead")
class ExpPassRead(CustomAction):
    """The pass page's Daily tab (ExpPassHub): its Clear EXP Luxcavation row, found by its text (PassExpRow) and read
    by its look (pass_missions.row_done): done is 1 won today, under way 0 (#429). The rows may still slide in, so it
    looks for up to 3 s; never found, or the param {"lost": true} (60 s with no pass page), is no read. Nothing is
    tapped."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        lux = RUN["lux"]
        found = []
        lost = (param(argv.custom_action_param) or {}).get("lost")
        if not lost:
            def row(image):
                detail = context.run_recognition("PassExpRow", image)
                if detail and detail.hit:
                    x, y, w, h = detail.best_result.box
                    found.append(pass_missions.row_done(image, pass_missions.nearest_row(y + h // 2)))
                return bool(found)
            until(context, row, timeout=3)
        if found:
            lux["today"] = int(found[-1])
            lux["seen"] = f"the pass's Clear EXP Luxcavation row {'done' if found[-1] else 'under way'}"
        elif lost:
            lux["seen"] = "the pass page was not reached in 60 s"
        else:
            lux["seen"] = "the pass's Clear EXP Luxcavation row did not read"
        log(f"{lux['name']}: {lux['seen']}")
        return True


def battle_over(context):
    """A Luxcavation battle was entered (RUN["entered"]) and the page it started from shows again: count its result
    (LuxResult sets it) and say what next (luxcavation.decide, #367). None: the next battle, or the same one again after a
    defeat; else what the action returns: True once the main window is reached and the task done, False from the stop
    procedure."""
    lux = RUN["lux"]
    RUN.pop("entered")
    result, lux["result"] = lux["result"], None
    if result is None:
        return stop(context, f"{lux['name']}: back on the page with no results page seen")
    step = luxcavation.decide(lux["modules"], lux["cost"], lux["fights"], lux["won"], lux["retried"], lux["retries"], result,
                              lux["size"])
    lux["won"] += lux["size"] * (result == "win")
    # Each battle has its own retries, as the mirror's wipe retries: a win starts the next battle at 0 (review S6).
    lux["retried"] = 0 if result == "win" else lux["retried"] + (step == luxcavation.RETRY)
    log(f"{lux['name']}: {result}, {lux['won']} of {lux['fights']} won, {lux['retried']} of {lux['retries']} retries of this battle used: {step}")
    if step == luxcavation.FINISH:
        return finish(context, f"{lux['name']}: {lux['won']} won")
    if step == luxcavation.STOP:
        return stop(context, f"{lux['name']}: defeated with the {lux['retries']} retries used up")
    RUN["guard"] = RUN["team"]["guard_turns"]  # each battle guards its first turns (2026-10-27)
    return None


# The Consecutive Battle box of each page that has one (live 2026-10-27, 1280x720): the title's OCR roi (short of its arrow,
# which the OCR reads as a 7), a narrower roi on its "x N", the title to tap (opens and closes the row), and the row's y with
# the x of 1<<, -, +, >>10. The EXP and Thread boxes sit on their card, whose place changes (the EXP tab's rightmost open stage
# is the middle card where the 10th is locked): theirs are given for the card whose Enter has the centre in ENTER_AT, and
# move by how far the Enter in use is from it. Level Select's box does not move.
CONSECUTIVE = {
    "exp": ([990, 240, 205, 30], [1135, 240, 50, 28], (1110, 254), 286, {"one": 1008, "minus": 1038, "plus": 1179, "ten": 1209}),
    "thread": ([250, 212, 230, 28], [400, 212, 50, 28], (370, 226), 259, {"one": 272, "minus": 305, "plus": 436, "ten": 469}),
    "level": ([510, 170, 225, 26], [680, 170, 45, 26], (640, 183), 217, {"one": 530, "minus": 563, "plus": 716, "ten": 749}),
}
ENTER_AT = {"exp": (1079, 479), "thread": (372, 481)}  # the centre of LuxExpEnter on stage 9 at the right, of LuxThreadEnter


def consecutive_box(box, enter=None):
    """CONSECUTIVE[box] for the card whose Enter has its centre at `enter` (x, y): the rois, the title tap, the row's y and
    the buttons' xs moved by its distance from ENTER_AT. `enter` None (Level Select), or a page of no card: as given."""
    title, digit, (title_x, title_y), row_y, buttons = CONSECUTIVE[box]
    if box not in ENTER_AT or enter is None:
        return title, digit, (title_x, title_y), row_y, buttons
    dx, dy = enter[0] - ENTER_AT[box][0], enter[1] - ENTER_AT[box][1]
    return ([title[0] + dx, title[1] + dy, *title[2:]], [digit[0] + dx, digit[1] + dy, *digit[2:]], (title_x + dx, title_y + dy),
            row_y + dy, {name: x + dx for name, x in buttons.items()})


def consecutive_now(context, image, box, enter=None):
    """The N of the Consecutive Battle title on `box`'s page (1-10), None when it does not read: the narrow roi on its "x N"
    first, which reads the yellow 4 the whole title's detection misses (Level Select, live 2026-10-27), then the title.
    `enter`: the centre of the Enter the card's box is above (consecutive_box)."""
    title, digit = consecutive_box(box, enter)[:2]
    return (luxcavation.parse_consecutive(text(context, image, digit, only_rec=True))
            or luxcavation.parse_consecutive(text(context, image, title)))


def set_consecutive(context, box, target, enter=None):
    """Set the Consecutive Battle of `box`'s page (the card of the Enter at `enter`) to `target` and read it back: the N it
    shows at the end, None when it never read. The game resets it to 1 on leaving Luxcavation and after a result, so each
    entry sets it (live 2026-10-28)."""
    _, _, (title_x, title_y), row_y, buttons = consecutive_box(box, enter)
    shown = []
    until(context, lambda im: shown.append(consecutive_now(context, im, box, enter)) or shown[-1] is not None, timeout=3)
    if shown[-1] is None:
        log(f"Consecutive Battle ({box}): does not read, wants x{target}")
        return None
    log(f"Consecutive Battle ({box}): shows x{shown[-1]}, wants x{target}")
    if shown[-1] == target:
        return target
    tap(context, title_x, title_y, wait=0.5)  # open the row
    keys = luxcavation.presses(shown[-1], target)
    log(f"Consecutive Battle ({box}): pressed {', '.join(keys)}")
    for name in keys:
        tap(context, buttons[name], row_y, wait=0.3)
    tap(context, title_x, title_y, wait=0.5)  # close it again
    shown.clear()
    until(context, lambda im: shown.append(consecutive_now(context, im, box, enter)) or shown[-1] == target, timeout=3)
    log(f"Consecutive Battle ({box}): {'does not read' if shown[-1] is None else f'shows x{shown[-1]}'} after closing the row"
        + ("" if shown[-1] == target else f", wanted x{target}"))
    return shown[-1]


@AgentServer.custom_action("LuxEnter")
class LuxEnter(CustomAction):
    """An Enter of a Luxcavation page (the node's box): the EXP tab's rightmost open stage (LuxExpEnter), the Thread
    tab's open card (LuxThreadEnter), the bottom row of the card's Level Select, its hardest level (LuxThreadLevel). Tap
    it until the page goes. The param {"opens_battle": false} marks the card's Enter, which opens the Level Select, not
    the battle (#368). Back on the page a battle started from: the battle is over (battle_over). Where the task fights
    consecutively, the param's "box" names the page's Consecutive Battle (CONSECUTIVE): it is set to the wins left, up
    to 10, before the tap (#375); one that will not read or set stops the task, so no battle starts at the wrong count.
    A task not planned yet (Thread's first look at its card, in daily mode) reads the tab's Daily Bonuses and plans first
    (#429): n left of 3 is 3 - n won today."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("entered"):
            over = battle_over(context)
            if over is not None:
                return over
        opts = param(argv.custom_action_param) or {}
        lux = RUN["lux"]
        if lux["fights"] is None:  # Thread in daily mode only: count mode was planned in LuxHome
            n = luxcavation.read_bonuses(ocr_texts(context, screen(context), "ThreadBonuses"))
            shown = "Daily Bonuses did not read" if n is None else f"Daily Bonuses {n}/{luxcavation.DAILY_BONUSES}"
            over = plan(context, None if n is None else luxcavation.DAILY_BONUSES - n, shown)
            if over is not None:
                return over
        cx, cy = box_centre(argv.box)
        if lux["consecutive"]:
            want = lux["size"] = luxcavation.batch(lux["fights"], lux["won"], True)
            got = set_consecutive(context, opts["box"], want, (cx, cy))
            if got != want:
                return stop(context, f"{lux['name']}: Consecutive Battle {'did not read' if got is None else f'shows x{got}'}, wanted x{want}")
        if tap_then(context, cx, cy, lambda im: seen(context, im, argv.node_name) is None, timeout=3) is not None:
            RUN["entered"] = opts.get("opens_battle", True)
            RUN["team_picked"] = False
            log(f"{RUN['lux']['name']}: {argv.node_name} at ({cx}, {cy})")
        return True


LUX_CONFIRM = (1125, 570)  # the results page's Confirm (live 2026-10-27)


@AgentServer.custom_action("LuxResult")
class LuxResult(CustomAction):
    """The results page after a Luxcavation battle (live-1 F2, pipeline LuxResult): its Victory or Defeat is the result of
    the battle entered (RUN["entered"]), kept for battle_over; then Confirm until the page goes. Neither word read yet:
    the page is still fading in, and the hub looks again. A defeat (by hand, Give Up: no confirm dialog) takes no
    Module and no Daily Bonus (live 2026-10-27)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        image = screen(context)
        result = "win" if seen(context, image, "LuxWon") else "lose" if seen(context, image, "LuxLost") else None
        if result is None:
            return True
        end_battle()
        if RUN.get("entered") and RUN["lux"]["result"] is None:
            RUN["lux"]["result"] = result
            log(f"{RUN['lux']['name']}: results page, {'Victory' if result == 'win' else 'Defeat'}")
        tap_then(context, *LUX_CONFIRM, lambda im: seen(context, im, "LuxResult") is None, timeout=4)
        return True


@AgentServer.custom_action("StopTask")
class StopTask(CustomAction):
    """End the task a failure through the stop procedure (evidence, log, webhook); the param says why. Not the whole list:
    the next task of the client's list starts from its own GoHome."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return stop(context, f"{argv.node_name}: {param(argv.custom_action_param, '')}")


def go_home(context):
    """Run the GoHome task here (spec 01): True once it ended on the main window (HomeReached), False when it did not
    (GoHome has run the stop procedure itself). Not the task's status: a sub-task that stopped the tasker (Halt in a
    battle) ends succeeded too (#514)."""
    detail = context.run_task("GoHome")
    last = detail and detail.node_id_list and context.tasker.get_node_detail(detail.node_id_list[-1])
    return bool(last and last.name == "HomeReached")


def restart_game(context, reason, kind=None):
    """L3 outside the mirror's Ladder (spec 06), for GoHome's HomeLost and the daily hubs' DailyRecover: RecoverL3 within
    the task's L3_PER_TASK that went through (one that did not is not counted, as Ladder.failed uncharges the run) and the
    launch's Restarts, then GoHome's back keys, game starts and Window tab taps count afresh and the game state is
    forgotten. kind: the screen type the game is stuck on; None for HomeLost, which no hub read. True once RecoverL3
    ran, through or not (GoHome goes on from wherever it left the game); False after the stop procedure."""
    if TASK.get("l3", 0) >= recovery.L3_PER_TASK:
        return stop(context, f"{reason}; game restarted {recovery.L3_PER_TASK} times this task")
    if why := STUCK["restarts"].attempt(kind):
        return stop(context, f"{reason}; {why}")
    log(f"recovery L3: {reason} (restart {STUCK['restarts'].in_a_row} of {recovery.L3_FAILED_IN_A_ROW} in a row, "
        f"{TASK.get('l3', 0) + 1} of {recovery.L3_PER_TASK} this task)")
    detail = context.run_task("RecoverL3")
    if detail and detail.status.succeeded:
        TASK["l3"] = TASK.get("l3", 0) + 1
    else:
        log("L3 did not go through")
    for node in ("HomeBack", "HomeGameAway", "HomeWindowTab"):
        context.clear_hit_count(node)
    forget_game_state()
    return True


@AgentServer.custom_recognition("StuckWaiting")
class StuckWaiting(CustomRecognition):
    """GoHome's HomeFrozen: hits while a stuck waits for recovery. In GoHome only tap_then's dead taps on the title raise
    one (#506). Not StuckFlag: GoHome feeds no watchdog."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        return flag_hit() if STUCK["flag"] else None


@AgentServer.custom_action("HomeFrozen")
class HomeFrozen(CustomAction):
    """GoHome on a game frozen on the title (#506): restart it (restart_game); GoHome goes on from the new title."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        _, _, reason = STUCK["flag"]
        STUCK["flag"] = None
        return restart_game(context, reason)


def hub_knows(context, hub, node):
    """A done(image) for until(): one of the nodes of hub's next list but node hits, a screen the hub knows besides it."""
    known = [n for n in next_names(context, hub) if n != node]
    return lambda image: any(seen(context, image, n) for n in known)


@AgentServer.custom_recognition("StaysUnknown")
class StaysUnknown(CustomRecognition):
    """Hits once none of the hub's other screens (the nodes of its next but this one; param {"hub", "timeout": s}) shows
    on a screenshot for timeout s. GoHome's back key (HomeBack) waits out a moment no template reads this way: the
    title's glitch warps the whole picture for about 1 s (#495; live 2026-11-08, 3 glitches of 0.9-1.3 s, NavTitle
    0.51-0.61). A screen that shows in the meantime is the hub's next pass, not the back key's."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        p = json.loads(argv.custom_recognition_param)
        if until(context, hub_knows(context, p["hub"], argv.node_name), timeout=p["timeout"]) is not None:
            return None
        return flag_hit()


@AgentServer.custom_action("HomeLost")
class HomeLost(CustomAction):
    """GoHome's on_error (#362 D4): 60 s of nothing known, or the back key used up; HomeConnecting's, its param saying why
    (#540). The game is restarted (restart_game) and GoHome goes again from the title; once the restarts are used up, the
    stop procedure ends the task."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return restart_game(context, param(argv.custom_action_param) or "the main window was not reached")


@AgentServer.custom_action("DailyRecover")
class DailyRecover(CustomAction):
    """A daily hub's Stuck node (#440, spec 06): the daily pages have L3 only. A stuck that starts at L3, a game frozen on
    the main window (tap_then), restarts the game; GoHome takes it to the main window and the node's next goes back to its
    hub, whose taps count afresh (two dead taps are MailOpen's whole max_hit): the task's own flow, TASK and the run's plan
    kept, the game state forgotten as after any recovery. Any other stuck ends the task through the stop procedure, the
    param saying why."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        kind, level, reason = STUCK["flag"]
        STUCK["flag"] = None
        if level < 3:
            return stop(context, f"{argv.node_name}: {param(argv.custom_action_param, '')}")
        if not restart_game(context, reason, kind):
            return False
        hub = context.get_node_data(argv.node_name)["next"][0]["name"]
        for node in next_names(context, hub):
            context.clear_hit_count(node)
        return go_home(context)


@AgentServer.custom_action("GoHomeRun")
class GoHomeRun(CustomAction):
    """A daily task's first step, after its TaskStart: the main window, wherever the last task left the game."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return go_home(context)


@AgentServer.custom_action("MailDone")
class MailDone(CustomAction):
    """ClaimMail's end, on the empty Mailbox: the main window, then done with what this run did (live-2 G3: a box emptied
    by Claim All said "no mail to claim")."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return finish(context, "mail claimed" if context.get_hit_count("MailClaimAll") else "no mail to claim")


AgentServer.custom_recognition("PassClaimable")(pass_missions.PassClaimable)
PASS_CLAIMS = ("PassDailyClaim", "PassWeeklyClaim", "PassSeasonalClaim", "PassSeasonalEndClaim")  # a hit taps one row


@AgentServer.custom_action("PassFinish")
class PassFinish(CustomAction):
    """ClaimPassMissions' last step: the main window (GoHome), then done with the rows tapped this run (live-1 F6: a run
    with nothing to claim said "pass missions claimed")."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        n = sum(context.get_hit_count(node) for node in PASS_CLAIMS)
        return finish(context, f"pass missions: {n} row(s) claimed" if n else "pass missions: nothing to claim")



@AgentServer.custom_recognition("DoneFlag")
class DoneFlag(CustomRecognition):
    """TaskDone, on every task's hub: hits once an action found nothing left to do (done); its empty next ends the task
    a success (#364)."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        return flag_hit(done=TASK["done"]) if TASK["done"] else None


# Assemble Enkephalin Modules (#370, pipeline/assemble_modules.json).
MODULE_COST = 20  # Enkephalin per module
ENK_BAR = (440, 640)  # the resource panel's Enkephalin bar: opens the Charge Enkephalin window
ASSEMBLE_MAX = (805, 328)  # the Modules tab's >> (the most)
MODULES_TAB = (505, 226)  # the Charge Enkephalin window's Modules tab (live 720p, 2026-10-26)
PANEL_CONFIRM, PANEL_CANCEL = (760, 534), (520, 534)  # the Charge Enkephalin window's Confirm and Cancel, on every tab
ASSEMBLE_TRIES = 3  # reads, taps of >> and Confirms the task spends before it gives up


def fractions(results):
    """Every "n / cap" of OCR results [(text, box)], left to right, as (n, cap)."""
    return [f for t, _ in sorted(results, key=lambda r: r[1][0]) for f in text_fractions(t)]


def node_results(context, image, node):
    """Every (text, box) the OCR node read on image, hit or not."""
    detail = context.run_recognition(node, image)
    return [(r.text, tuple(r.box)) for r in (detail.all_results if detail else [])]


def read_fractions(context, image, node):
    return fractions(node_results(context, image, node))


def panel_read(context, image):
    """The window's Enkephalin before and after, [(n, cap), (n, cap)], each read on its own side of the arrow; [] unless
    both read."""
    before, after = read_fractions(context, image, "AssembleBefore"), read_fractions(context, image, "AssembleAfter")
    return before[:1] + after[-1:] if before and after else []


def cancel_stop(context, reason):
    """The stop procedure, its evidence the window itself (live-3 H1), then Cancel closes the window; False."""
    stop(context, reason)
    tap(context, *PANEL_CANCEL, wait=0.5)
    return False


def on_modules_tab(context, image):
    """The Modules tab's own prompt ("Would you like to assemble Enkephalin Modules?") is up. The Use Lunacy tab shows the
    Enkephalin before and after as well, so the two "n / cap" alone do not tell the tabs apart: a Confirm there spends
    Lunacy."""
    detail = context.run_recognition("AssemblePrompt", image)
    return bool(detail and detail.hit)


def too_many(context, image):
    detail = context.run_recognition("AssembleTooMany", image)
    return bool(detail and detail.hit)


def open_enkephalin(context):
    """The Enkephalin bar, then until the Charge Enkephalin window shows (3 s at most): the hub's next look at the main
    window would tap the bar again (#362, instead of a fixed 1.5 s)."""
    tap_then(context, *ENK_BAR, lambda im: seen(context, im, "EnkephalinWindow") is not None, timeout=3)


@AgentServer.custom_action("AssembleMain")
class AssembleMain(CustomAction):
    """The main window, reached by GoHome or already there: the task's one way out and its way in. With the Enkephalin
    under a module's cost, or the game's refusal seen, it is done; after a Confirm the bar must read lower than before
    it; else the bar opens the window."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        a = TASK.setdefault("assemble", {"reads": 0, "confirms": 0})
        read = read_fractions(context, screen(context), "EnkephalinBar")
        if not read:
            a["reads"] += 1
            return True if a["reads"] < ASSEMBLE_TRIES else stop(context, "the Enkephalin bar could not be read")
        a["reads"], n = 0, read[0][0]
        if a.get("end"):
            return done(a["end"])
        if "before" in a:
            if n < a["before"]:
                return done(f"Enkephalin {a['before']} -> {n}, assembled")
            time.sleep(1)  # the bar counts down; read it again before judging
            a["checks"] = a.get("checks", 0) + 1
            return True if a["checks"] < ASSEMBLE_TRIES else stop(context, f"Enkephalin still {n} after Confirm")
        if n < MODULE_COST:
            return done(f"Enkephalin {n} < {MODULE_COST}, nothing to assemble")
        log(f"assemble: Enkephalin {n}, opening the window")
        open_enkephalin(context)
        return True


@AgentServer.custom_action("AssemblePanel")
class AssemblePanel(CustomAction):
    """The Charge Enkephalin window: its Modules tab first (the window opens on the tab it was left on, #362 D7), then on
    it (its prompt and the Enkephalin before and after read), >> for the most modules, Confirm. Only the tab, >>, Confirm
    and Cancel are tapped. Not on the Modules tab, or a number that stops reading after >>: the stop procedure, then
    Cancel, never Confirm (Use Lunacy's Confirm spends Lunacy). The game's refusal ends the task; a window over a task
    already decided is cancelled.

    Confirm leaves the window open (live-1 F1, tests/screens/EnkephalinAssembled.png): a "Module Assembled 134 > 135"
    toast, the Enkephalin down, "Insufficient Enkephalin." where the prompt was and Confirm greyed. The drop read there
    decides the task and Cancel closes the window; the prompt back with nothing changed is a Confirm that did not take."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        a = TASK.setdefault("assemble", {"reads": 0, "confirms": 0})
        image = screen(context)
        if too_many(context, image):
            a["end"] = "too many Enkephalin Modules in storage"
            back(context)
            return True
        if a.get("end"):
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        if "before" in a and (step := self.after_confirm(context, a, image)) is not None:
            return step
        tap(context, *MODULES_TAB, wait=0.7)
        image = screen(context)
        read = panel_read(context, image) if on_modules_tab(context, image) else []
        if not read:  # not the Modules tab, or not up yet
            a["reads"] += 1
            if a["reads"] < ASSEMBLE_TRIES:
                return True
            return cancel_stop(context, "the Charge Enkephalin window shows no Modules tab")
        a["reads"] = 0
        before, after = read[0][0], read[-1][0]
        if before < MODULE_COST:
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        for _ in range(ASSEMBLE_TRIES):  # >> goes to the most the Enkephalin allows; ask again until nothing changes
            if after < MODULE_COST:
                break
            tap(context, *ASSEMBLE_MAX, wait=0.5)
            image = screen(context)
            if too_many(context, image):
                a["end"] = "too many Enkephalin Modules in storage"
                back(context)
                return True
            again = panel_read(context, image) if on_modules_tab(context, image) else []
            if not again:
                return cancel_stop(context, "the Modules tab did not read after >>: Confirm not pressed")
            if again[-1][0] == after:
                break
            after = again[-1][0]
        a["confirms"] += 1
        if a["confirms"] > ASSEMBLE_TRIES:
            return cancel_stop(context, f"Confirm did not take: Enkephalin still {before}")
        log(f"assemble: Enkephalin {before} -> {after}, Confirm")
        a["before"] = before
        tap(context, *PANEL_CONFIRM, wait=0.5)
        return True

    @staticmethod
    def after_confirm(context, a, image):
        """The window after a Confirm (a["before"] set), what run() returns: the drop read sets a["end"] and Cancel closes
        the window (True); nothing read yet is looked at again (True) up to ASSEMBLE_TRIES times, then the stop procedure
        (False). None: the prompt shows again with the Enkephalin unchanged, a Confirm that did not take, for run() to
        press again."""
        read = panel_read(context, image)
        if read and read[0][0] < a["before"]:
            a["end"] = f"Enkephalin {a['before']} -> {read[0][0]}, assembled"
            log(f"assemble: {a['end']}")
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        if on_modules_tab(context, image):
            return None
        a["checks"] = a.get("checks", 0) + 1
        if a["checks"] < ASSEMBLE_TRIES:
            return True
        return cancel_stop(context, f"Enkephalin still {a['before']} after Confirm")


# Lunacy for Enkephalin (#373, pipeline/charge_enkephalin.json): the Charge Enkephalin window's Use Lunacy tab.
LUNACY_TAB = (639, 226)  # the Use Lunacy tab (live 720p, 2026-10-26); Confirm and Cancel are taken to sit where the Modules tab's do
CHARGE_TRIES = 3  # reads of the prompt and price, and Cancels over a decided task, the task spends before it gives up


@AgentServer.custom_action("ChargeStart")
class ChargeStart(TaskStart):
    """ChargeEnkephalin's entry: TaskStart, then charge_enkephalin.count, the day's target Daily Count (#429). 0, the
    default, ends the task at once, a success, before GoHome or any tap: the window is never opened, so the Use Lunacy
    tab is never touched."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not super().run(context, argv):
            return False
        try:
            count = load_settings(ROOT)["charge_enkephalin"]["count"]
        except SettingsError as e:
            return stop(context, str(e))
        TASK["charge"] = {"count": count, "reads": 0, "opened": 0, "charged": 0}
        return done("charge_enkephalin.count is 0: Lunacy left alone") if count == 0 else True


@AgentServer.custom_action("ChargeMain")
class ChargeMain(CustomAction):
    """The main window: the task's one way out and its way in. Done once the panel decided so; else the Enkephalin bar
    opens the window (once per charge and one more for the price that ends it, never more than the table has)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        c = TASK["charge"]
        if c.get("end"):
            return done(c["end"])
        c["opened"] += 1
        if c["opened"] > lunacy.DAILY_MAX + 1:
            return stop(context, f"the Charge Enkephalin window opened {c['opened'] - 1} times, more than a day has charges")
        open_enkephalin(context)
        return True


@AgentServer.custom_action("ChargePanel")
class ChargePanel(CustomAction):
    """The Charge Enkephalin window: its Use Lunacy tab (it opens on Modules), which shows the price, the Daily Count and
    the Recharge prompt (live 2026-10-27). The price must be the table's at the Daily Count, and the count one up after
    each Confirm (lunacy.check); else Cancel, and the task ends (a success at the day's target, a failure when the
    screen is not what it should be). Use Boxes has the same prompt and no Daily Count: never confirmed. A tab that
    does not read before this run's first Confirm is not known to be short of the target: Cancel, a success with
    nothing charged (#429); after a Confirm it is the stop procedure. Only the tab, Confirm and Cancel are tapped."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        c = TASK["charge"]
        if c.get("end"):  # a window over a task already decided; exempt from the same-screen watchdog, so bounded here
            c["cancels"] = c.get("cancels", 0) + 1
            if c["cancels"] > CHARGE_TRIES:
                return stop(context, f"the Charge Enkephalin window stayed open after {CHARGE_TRIES} more Cancels")
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        tap(context, *LUNACY_TAB, wait=0.7)
        image = screen(context)
        prompt = context.run_recognition("ChargePrompt", image)
        price, used = None, None
        if prompt and prompt.hit:
            price = lunacy.read_price(ocr_texts(context, image, "ChargePrice"))
            used = lunacy.read_count(ocr_texts(context, image, "ChargeCount"))
        if used is None or (price is None and used < c["count"]):  # at the target the price is not needed
            c["reads"] += 1
            if c["reads"] < CHARGE_TRIES:
                return True
            tap(context, *PANEL_CANCEL, wait=0.5)
            unread = "the Use Lunacy tab's " + ("prompt and Daily Count" if used is None else f"price (Daily Count {used}/{lunacy.DAILY_MAX})")
            if c["charged"] == 0:
                c["end"] = f"{unread} did not read, target {c['count']}: nothing charged"
                log(f"charge: {c['end']}")
                return True
            return stop(context, f"{unread} could not be read after a Confirm")
        c["reads"] = 0
        verdict, why = lunacy.check(price, used, c["charged"], c["count"], c.get("expected"))
        log(f"charge: {why}")
        if verdict == lunacy.CHARGE:
            c["charged"] += 1
            c["expected"] = used + 1  # a Daily Count that stays is a Confirm that did nothing
            tap(context, *PANEL_CONFIRM, wait=1.0)
            return True
        tap(context, *PANEL_CANCEL, wait=0.5)
        if verdict == lunacy.DONE:
            c["end"] = why
            return True
        return stop(context, why)


def ocr_texts(context, image, node):
    """Every text the OCR node read on image, hit or not."""
    return [t for t, _ in node_results(context, image, node)]


@AgentServer.custom_action("Recover")
class Recover(CustomAction):
    """Run the recovery level the Ladder gives (Pipeline RecoverL1-3), or stop (spec 06).

    MirrorHub's timeout (GlobalStuck, no flag set) counts as a stuck on the last screen handed out.
    A level that does not go through climbs straight to the next one.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        unknown = STUCK["flag"] is None  # MirrorHub's own timeout: a screen it has no node for
        flag = STUCK["flag"] or (nothing_recognised(), 1, "MirrorHub recognised nothing for 60 s")
        STUCK["flag"] = None
        if unknown:  # also during a download: its progress screen is one to have a capture of
            keep_unknown(screen(context))
        if STUCK["watch"].held(time.monotonic()):
            log(f"{flag[2]}: a download is under way, waiting")
            return True
        kind, start, reason = flag
        if unknown and (app := foreground(context)) not in (None, recovery.GAME):
            # #86: the Play Store, the home screen, or a game whose window never took focus (live, black 5 min after
            # an update): the back key and To Window do nothing there, so the game is restarted at once.
            start, reason = 3, f"{reason}; {recovery.not_in_front(app)}"
        while True:
            level, why = STUCK["ladder"].stuck(kind, start, STUCK["restarts"])
            if level is None:
                return stop(context, f"{reason}; {why}")
            log(f"recovery L{level}: {reason}")
            detail = context.run_task(f"RecoverL{level}")
            if detail and detail.status.succeeded:
                break
            log(f"L{level} did not go through")
            STUCK["ladder"].failed(level)
        forget_game_state()
        return True


def nothing_recognised():
    """The screen type of a stuck on a screen no node recognised: the last one handed out, then nothing. Any screen a hub
    hands out after it gets past it."""
    return f"{STUCK['kind']}, then nothing recognised"


def keep_unknown(image):
    """Keep a screen no node recognised in logs/unknown/ (recovery.keep_capture)."""
    try:
        recovery.keep_capture(ROOT, "unknown", image, settlement.now().replace(":", "-"), recovery.UNKNOWN_KEEP)
    except OSError as e:
        log(f"unknown screen not saved: {e}")


def foreground(context):
    """The package in front (recovery.focused_package), None when it cannot be read (not an adb controller, a failed
    shell job)."""
    job = context.tasker.controller.post_shell("dumpsys window").wait()
    try:  # a failed job may still hand out the last command's output
        return recovery.focused_package(job.get()) if job.succeeded else None
    except RuntimeError:
        return None


def forget_game_state():
    """The game came back from a recovery or a restart: drop the streak, the battle clock and the map retries.

    A shop visit keeps the rest of RUN["shop"] (what it paid for or tapped, Shop lists it) but not fuse_scanned: a fuse
    page that made none may have been a game that took no tap (#459), so the next round reads it again."""
    STUCK["watch"].reset()
    STUCK["taken"].clear()
    for key in ("turn", "battle_start", "map_misses", "event_tried", "map_plan", "map_entered"):
        RUN.pop(key, None)
    RUN.get("shop", {}).pop("fuse_scanned", None)
    RUN["resumed"] = True


def run_continued():
    """Whether this agent process did not see the run's floor from its theme pack on: a restart or a recovery since (#379)."""
    return bool(RUN.get("resumed")) or "floor" not in RUN


def restart_floor_clock():
    """The floor time limit starts over (spec 06 每層超時); only in a run the bot started, which has floor_limit."""
    if "floor_limit" in RUN:
        RUN["deadline"] = time.time() + RUN["floor_limit"]


def settings_now():
    """This run's settings, else the file's; None when it cannot be read."""
    if "settings" in RUN:
        return RUN["settings"]
    try:
        return load_settings(ROOT)
    except SettingsError:
        return None


def allowed(key):
    """run.<key> of the settings (auto_accept_terms, auto_download); on, the default, when they cannot be read."""
    settings = settings_now()
    return True if settings is None else settings["run"][key]


DISMISSED_AT = {}  # node name -> time.monotonic() of its last kept screen (GAPPED nodes only)
DISMISSED_GAP = 60  # seconds: RetryPopup keeps coming back on a dropped link, so it is kept once per gap
GAPPED = {"RetryPopup"}  # the only node kept at most once per gap; every other node is kept each time


def popup_button(detail):
    """The text of the button PopupButton recognised: its PopupButtonText sub-result, which the And already read."""
    for sub in getattr(detail.best_result, "sub_results", []):
        if sub.name == "PopupButtonText" and sub.best_result:
            return sub.best_result.text
    return ""


@AgentServer.custom_action("DismissShot")
class DismissShot(CustomAction):
    """Keep the screen in logs/dismissed/ (run.keep_dismissed_screens), then close it (#244): the back key with
    {"back": true}, else a tap on the recognised box. File name: time and node, so what the bot closed can be told later.
    RetryPopup: one screen per DISMISSED_GAP, or a dropped link fills the folder with one popup.
    "until": a node that hits once the popup is gone (the main window's lit tab under the Mailbox); every 0.2 s, at
    most "timeout" s, until it hits and the popup's own node misses, instead of a post_delay (#258).
    "known": a hub; every 0.2 s, at most "timeout" s, until one of its other screens shows (hub_knows), instead of a
    post_delay (HomeBack, #58).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        p = param(argv.custom_action_param) or {}  # "null" when the node sets none
        now = time.monotonic()
        gap = DISMISSED_GAP if argv.node_name in GAPPED else 0
        keep = allowed("keep_dismissed_screens") and now - DISMISSED_AT.get(argv.node_name, -gap) >= gap
        popup = argv.node_name == "PopupButton"
        image = screen(context) if keep or popup else None  # one capture for the kept screen and the popup's text
        if keep:
            stamp = f"{settlement.now().replace(':', '-')}-{argv.node_name}"
            try:
                recovery.keep_capture(ROOT, "dismissed", image, stamp, recovery.DISMISSED_KEEP)
                if gap:
                    DISMISSED_AT[argv.node_name] = now
                log(f"{argv.node_name}: screen kept in logs/dismissed/{stamp}.png")
            except OSError as e:
                log(f"{argv.node_name}: screen not saved: {e}")
        if popup:  # what was closed, e.g. the previous session's "Please claim your rewards" (#382)
            log(f"popup: {text(context, image, DIALOG_TEXT)!r}: pressed {popup_button(argv.reco_detail)!r}")
        began = time.monotonic() if "until" in p or "known" in p else None
        if p.get("back"):
            back(context)
        else:
            context.tasker.controller.post_click(*box_centre(argv.box)).wait()
        if "until" in p:
            def closed(im):
                return seen(context, im, p["until"]) is not None and seen(context, im, argv.node_name) is None
            log_change(argv.node_name, until(context, closed, timeout=p["timeout"]), began)
        if "known" in p:
            log_change(argv.node_name, until(context, hub_knows(context, p["known"], argv.node_name),
                                             timeout=p["timeout"]), began)
        return True


@AgentServer.custom_action("ConfirmDownload")
class ConfirmDownload(CustomAction):
    """Confirm the title's download dialog (the matched button), then hold the stuck detection until its progress
    screen (Downloading, a waiting screen) is up. The floor's clock starts over: the download takes the game away (#86).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not allowed("auto_download"):
            return stop(context, "the game asks to download data: run.auto_download is off", whole_list=True)
        context.tasker.controller.post_click(*box_centre(argv.box)).wait()
        STUCK["watch"].hold(time.monotonic(), recovery.DOWNLOAD_HOLD)
        restart_floor_clock()  # live 2026-10-21: 32 min of download would trip it, and L3 mid-download
        log(f"download confirmed: nothing counts as stuck for {recovery.DOWNLOAD_HOLD // 60} min")
        return True


UPDATE_RESTARTS = 2  # game restarts for update notices per bot launch: one that keeps coming back stops the bot


@AgentServer.custom_action("AcceptUpdate")
class AcceptUpdate(CustomAction):
    """Press the game's own update notice (UpdateDialog), then restart the game: it closes itself or goes back to the
    title, and the download dialog comes up there (ConfirmDownload). Not a stuck: no recovery level is charged."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not allowed("auto_download"):
            return stop(context, "the game has an update: run.auto_download is off", whole_list=True)
        if STUCK["updates"] >= UPDATE_RESTARTS:
            return stop(context, f"the game asked for an update {UPDATE_RESTARTS + 1} times since the bot started", whole_list=True)
        STUCK["updates"] += 1
        context.tasker.controller.post_click(*box_centre(argv.box)).wait()
        log("game update accepted: restarting the game")
        time.sleep(3)  # kept (#58): the game takes the tap before it is stopped; once per game update, nothing to time
        detail = context.run_task("RecoverL3")
        if not (detail and detail.status.succeeded):
            log("the restart after the update did not reach the title")
        forget_game_state()
        return True


# The User Agreement's two "I agree." boxes (top-left of their inside, AGREE_SIZE square) and its Confirm, live 2026-10-21.
AGREE_BOXES, AGREE_SIZE = ((338, 452), (828, 452)), 19
AGREE_CONFIRM = (831, 513)


def agree_ticked(image, x, y):
    """A white tick in the box; unticked it is black inside (live: 0 % of its pixels over 150 grey, ticked 26-30 %).

    Read only once UserAgreement hit: on 6 other screens of tests/screens both boxes read ticked (test_title_dialogs).
    """
    return (image[y:y + AGREE_SIZE, x:x + AGREE_SIZE].mean(axis=2) > 150).mean() > 0.1


@AgentServer.custom_action("AcceptTerms")
class AcceptTerms(CustomAction):
    """Tick both boxes of the title's User Agreement, then Confirm once both read ticked (run.auto_accept_terms)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not allowed("auto_accept_terms"):
            return stop(context, "User Agreement: run.auto_accept_terms is off", whole_list=True)
        image = screen(context)
        for x, y in AGREE_BOXES:
            if not agree_ticked(image, x, y):
                image = tap_then(context, x + AGREE_SIZE // 2, y + AGREE_SIZE // 2, lambda i, x=x, y=y: agree_ticked(i, x, y))
                if image is None:
                    log("User Agreement: a box did not tick")
                    return True  # MirrorHub looks again
        if not all(agree_ticked(image, x, y) for x, y in AGREE_BOXES):
            return True
        tap(context, *AGREE_CONFIRM, wait=2)  # kept (#58, #258): once per game update, no log has one to time
        log("User Agreement accepted")
        return True


@AgentServer.custom_action("Halt")
class Halt(CustomAction):
    """Stop on a screen the bot must not act on (the maintenance notice, a client too old for the server); the reason
    goes to the log and the webhook. An account-level stop: the whole task list ends."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return stop(context, f"{argv.node_name}: {param(argv.custom_action_param, '')}", whole_list=True)


# s after a taken tap that TapUntil's settle holds: a login's CONNECTINGs, GoHome's 60 s wait on each, and the gaps
# between them (#58). A title met later (a session expired) is tapped at once.
SETTLE_WITHIN = 120


@AgentServer.custom_action("TapUntil")
class TapUntil(CustomAction):
    """A Click node that waits for the page that follows instead of a post_delay (#115).

    Param: {"target": [x, y, w, h], "next": {"roi": [...], "expected": regex} or a list of them (any),
    "gone": {"roi": [...], "expected": regex}, "left": true, "until": node, "timeout": s (default 3), "lively": a node of
    recovery.LIVELY}; any of "next", "gone", "left" and "until", the first to hold ends it. The page it leaves may still
    read like itself for a moment; MirrorHub would act on it twice.
    gone: the node's own roi and expected (#254), for a page whose next one is not known or reads the same (ClaimPopup).
    left: the node's own recognition misses, for a node that is no OCR (a template: the daily pages' tabs and buttons).
    until: that node's recognition hits, for a next page a template knows. The Window tab glows on the old page before
    the main window comes, and that glow misses the tab's own template (#496).
    lively: the screen whose still wait is a dead tap (tap_then), HomeReached by default.
    settle: s; within SETTLE_WITHIN s of a taken tap of this node (a page came), and no recovery or restart since, a
    later hit first waits up to settle s for a page to come by itself or the node to miss, and taps only when neither
    does. The title between two CONNECTINGs of one login (#58): the game's own gap, which a tap there does not answer.
    No target: the node's box.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        p = json.loads(argv.custom_action_param)
        x, y = box_centre(p.get("target", argv.box))
        nxt = p.get("next", [])
        pages = [shows(context, n["roi"], n["expected"]) for n in (nxt if isinstance(nxt, list) else [nxt])]
        if "gone" in p:
            pages.append(gone(context, p["gone"], screen(context)))
        if p.get("left"):
            pages.append(lambda im: seen(context, im, argv.node_name) is None)
        if "until" in p:
            pages.append(lambda im: seen(context, im, p["until"]) is not None)
        began = time.monotonic()
        if "settle" in p and began - STUCK["taken"].get(argv.node_name, -SETTLE_WITHIN) < SETTLE_WITHIN:
            if until(context, lambda im: any(page(im) for page in pages) or seen(context, im, argv.node_name) is None,
                     timeout=p["settle"]) is not None:
                log(f"{argv.node_name}: not tapped again, the screen moved on by itself (or a glitch hid it) after "
                    f"{time.monotonic() - began:.1f} s")
                return True
            log(f"{argv.node_name}: still up {p['settle']} s after its last tap was taken: tapped again")
            began = time.monotonic()
        image = tap_then(context, x, y, lambda im: any(page(im) for page in pages), timeout=p.get("timeout", 3),
                         lively=p.get("lively", "HomeReached"))
        if "settle" in p and image is not None:
            STUCK["taken"][argv.node_name] = time.monotonic()
        log_change(argv.node_name, image, began)
        return True


def finish(context, reason):
    """A task with nothing left to do: the main window (GoHome) first, as a daily task's end (live-2 G4), then done."""
    return go_home(context) and done(reason)


@AgentServer.custom_action("PlanRun")
class PlanRun(CustomAction):
    """Entry page, no run under way: check settings, pick difficulty and team, press Enter (spec 03 sections 1, 2).

    Nothing left to do (the run count reached, the weekly bonuses out, no enabled team, none for the difficulty) ends
    the task a success at the main window (GoHome, then done; live-2 G4); bad settings fail it (returning False), and
    so do settings that forfeit run after run (the stop procedure, settlement.forfeits_stop).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            settings = load_settings(ROOT)
        except SettingsError as e:
            log(f"stop: {e}")
            return False
        if not any(t["enabled"] for t in settings["teams"]):
            return finish(context, "no enabled team")
        hsv_v = screen(context)[285:297].max(axis=2)  # V of HSV
        # Live: a filled slot reads V ~240, an empty one ~5 (2026-10-15).
        weekly = sum(hsv_v[:, x:x + 30].mean() > 40 for x in WEEKLY_SLOTS)
        run = settings["run"]
        if settlement.runs_done(TASK["runs"], run["runs"]):
            return finish(context, f"{TASK['runs']} of {run['runs']} runs done")
        if why := settlement.forfeits_stop(TASK.get("forfeits", [])):
            return stop(context, why)
        if run["stop_when_weekly_bonus_out"] and weekly == 0:
            return finish(context, "weekly bonuses used up")
        difficulty = run_start.run_difficulty(run["difficulty"], weekly, run["target_floor"])
        team = pick_team(settings["teams"], difficulty)
        if team is None:
            return finish(context, f"no enabled team may run {difficulty}")
        if run_start.team_difficulty(run["difficulty"], difficulty, team["hard_from_floor"]) != difficulty:
            log(f"team {team['name']!r} never switches to hard and the difficulty is {run['difficulty']}: a normal run")
            difficulty = "normal"
        # The entry page has no Modules panel (tests/screens/EntryNewRun.png): the Drive page's read (OpenDrive) is this trip's.
        step = settlement.new_run_gate(TASK.get("modules", settlement.NOT_SEEN), TASK.get("gate_backs", 0))
        if step == "back":  # not through Drive since the last run: back out, the hub's navigation reads it on the way in
            TASK["gate_backs"] = TASK.get("gate_backs", 0) + 1
            log("new run: the Modules were not read on the way here, back to the Drive page to read them")
            back(context)
            return True
        modules = TASK.pop("modules", None)
        TASK.pop("gate_backs", None)
        if step == "done":
            return finish(context, f"Modules {modules} < {settlement.CLAIM_COST}, one Claim could not be paid: no new run")
        if modules is None:
            log("new run: the Modules number did not read, starting anyway")
        else:
            log(f"new run: Modules {modules} >= {settlement.CLAIM_COST}")
        RUN.clear()
        # planned: the run's team is known (picked here, or after a restart the queue's, current_run), so the claim may
        # move it to the end of the queue and runs.jsonl names it.
        limit = recovery.floor_limit(recovery.read_runs(ROOT), team["id"], run["target_floor"])
        # guard: the run's guard turns left (spec 03 section 8), counted across its battles.
        # floor_limit: each floor's time; the first clock runs from here, PickThemePack restarts it (spec 06).
        RUN.update(settings=settings, team=run_team(settings, team), difficulty=difficulty, planned=True, start=settlement.now(), deadline=time.time() + limit,
                   floor_limit=limit, guard=team["guard_turns"], packs=[])
        STUCK["ladder"] = recovery.Ladder()
        log(f"new run: {difficulty}, team {team['name']!r} (TEAMS #{team['game_team']}), weekly bonuses left {weekly}, time limit {limit / 60:.0f} min a floor")
        tap_then(context, 1108, 494, shows(context, ENTER_DIALOG, "Will you enter"), timeout=3)
        return True


INFINITY_TITLE = [890, 330, 330, 28]  # entry page: "Parallel Superposition Mode : ON" / "OFF" (the pipeline's roi)
INFINITY_BUTTON = (1053, 377)  # INFINITY MIRROR under it


@AgentServer.custom_action("ParallelModeOff")
class ParallelModeOff(CustomAction):
    """Entry page with Parallel Superposition Mode ON: tap INFINITY MIRROR until it reads OFF (#94, spec 02).

    v1 never plays past floor 5 (#434 opens it for a target above 5); the prompt after floor 5 (ParallelModePrompt)
    is cancelled as a second guard.
    Still ON after two taps: stop, nothing else is tried.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        for _ in range(2):
            if tap_then(context, *INFINITY_BUTTON, shows(context, INFINITY_TITLE, r":\s*[O0]FF"), timeout=3) is not None:
                log("Parallel Superposition Mode switched OFF")
                return True
        return stop(context, "Parallel Superposition Mode stays ON after tapping INFINITY MIRROR")


def team_rows(context, image):
    """The picker list's fully shown rows: {slot number: y of its centre}."""
    visible = {}
    for t, (x, y, w, h) in ocr(context, image, TEAM_LIST):
        m = re.search(r"#\s*(\d+)", t)
        if m and 300 <= y + h // 2 <= 515:  # rows cut off at the list edge do not count
            visible[int(m[1])] = y + h // 2
    return visible


def team_list_top(context, home="TeamSelect"):
    """Drag the picker list to its top, a stroke at a time until the rows on show stay (#226): it opens where it was left.

    The rows' numbers, not their y: OCR boxes move by a pixel or two at rest (live 2026-10-27: 10 drags at the top)."""
    seen = None
    for k in range(15):
        rows = set(team_rows(context, page_guard(context, home)))
        if rows and rows == seen:  # no rows read is not a list at rest
            log(f"team list at its top after {k - 1} drags that moved it")
            return
        seen = rows
        scroll(context, 130, 340, 0, 140)
    log("team list still moving after 15 drags: looking for the team from here")


def pick_team_slot(context, n, home="TeamSelect"):
    """Have the title read the in-game TEAMS #N: that screenshot, or None when 15 strokes found no such row.

    Already on the title: nothing to do. Else tap its row, scrolling from where the list is towards it (team_list_move);
    the list goes to its top first only when no row reads (#226). Only the number counts: a team's name is the user's.
    home: the node of the page (the mirror's TeamSelect, LuxTeamSelect) for page_guard."""
    titled = shows(context, TEAM_TITLE, rf"#\s*{n}\b")
    image = page_guard(context, home)
    if titled(image):
        return image
    if not team_rows(context, image):
        team_list_top(context, home)
        image = None
    for _ in range(15):
        visible = team_rows(context, page_guard(context, home) if image is None else image)
        image = None
        move = run_start.team_list_move(visible, n)
        if move == "down":
            scroll(context, 130, 480, 0, -140)
        elif move == "up":
            scroll(context, 130, 340, 0, 140)
        else:
            shot = tap_then(context, 130, move[1], titled)
            if shot is not None:
                return shot
    return None


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Pick the team's in-game TEAMS #N slot (pick_team_slot), press Confirm."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # No plan here means a run resumed on the entry page, paused before team selection: the entry page only
        # offers Resume again, so backing out looped (#128). Make one up from settings, as after a restart.
        n = current_run(context)["team"]["game_team"]
        image = pick_team_slot(context, n)
        if image is None:
            return stop(context, f"could not select TEAMS #{n}")
        RUN["planned"] = True  # the title reads the slot: the run's team is known, whatever the queue fits (#436)
        bonus = number(text(context, image, [1160, 522, 60, 34]))
        log(f"team TEAMS #{n}, Starlight Bonus {bonus}")
        # LevelWarning when the team is under the recommended level, else the starlight page; the team page
        # reads through the warning, so leaving it early would have MirrorHub pick the team twice.
        warning, starlight = shows(context, LEVEL_WARNING, "recommended level"), shows(context, STARLIGHT_HEADER, "Available")
        tap_then(context, 1145, 587, lambda im: warning(im) or starlight(im), timeout=4)
        return True


@AgentServer.custom_action("LuxSelectTeam")
class LuxSelectTeam(CustomAction):
    """A Luxcavation hub's team page (#366, shared by the EXP and Thread hubs): the mirror's page, with To Battle! where
    it has Confirm. Pick RUN["team"]'s in-game slot once, then press To Battle! until the page goes. The task's Enter
    action drops RUN["team_picked"] when it enters a stage: each battle picks again."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        n = RUN["team"]["game_team"]
        if not RUN.get("team_picked"):
            if pick_team_slot(context, n, "LuxTeamSelect") is None:
                return stop(context, f"Luxcavation: could not select TEAMS #{n}")
            RUN["team_picked"] = True
            log(f"Luxcavation: TEAMS #{n}")
        # A dialog over the page reads through it: the page staying is for the hub's watchdog to judge.
        if tap_then(context, *TO_BATTLE, lambda im: not seen(context, im, "LuxTeamSelect"), timeout=4) is None:
            log("Luxcavation: To Battle! pressed, the team page stays")
        return True


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
                # Until Available reads what the grace leaves, at most the 1 s the tap slept (#58); any other number is
                # read once that 1 s is over, as before, so a number still counting down is not judged.
                image = tap_then(context, x + 92, y + 100, lambda im: read_available(context, im) == available - price,
                                 timeout=1.0)
                image = screen(context) if image is None else image
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
        def shown(image):
            price = number(text(context, image, [x + 112, y - 3, 80, 28]))
            return price // base if price and price % base == 0 else None

        for _ in range(4):
            now = shown(screen(context))
            if now == want:
                return True
            if now not in (1, 2, 3):
                time.sleep(0.5)  # kept: the price did not read (a fade, OCR); read it again
                continue
            button = want if want > 1 else now  # back to base = tap the lit button again
            page_guard(context, "StarlightPage")
            # until the price shows the level, at most the 1 s the tap slept (#58)
            tap_then(context, x + (50 if button == 2 else 132), y + 203, lambda im: shown(im) == want, timeout=1.0)
        return False


@AgentServer.custom_action("ConfirmStarlight")
class ConfirmStarlight(CustomAction):
    """Set Convert Starlight to Cost per the plan, press Confirm."""

    @hands_back
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
SEARCH_TABS = tuple(GIFT_KEYWORDS)  # the schema's keyword enum is the tabs, in order
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
SEARCH_ICON_MIN = 0.65
GRID_MID = 420  # a dragged-to gift's row lands here: whole rows above and below it


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
        return [run_start.match_name(t, names) or t for t in texts if t.strip()]

    @staticmethod
    def pick(context, gift):
        """Select gift: find its icon among its tier's cells, tap it once, and check the panel names it.

        The observation table's order says how far down the tab the gift sits, so the tab is dragged
        straight there; when the icon is not on that screen (the account lacks a gift above it, or the drag
        fell short) the tab is searched from the top, screen by screen. Cells are never tapped to read names.
        """
        tab = [g for g in gift_tables()[0] if g["keyword"] == gift["keyword"]]
        entry = next((g for g in tab if g["tier"] == gift["tier"] and run_start.match_name(g["en"], [gift["name"]])), None)
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
                if score < SEARCH_ICON_MIN:
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
        if new and run_start.match_name(new[0], [name]):
            return True
        if new:
            log(f"gift search: the icon match picked {new[0]}, not {name}: unselected")
            page_guard(context, "GiftSearch")  # the tap above waited up to 1 s
            tap_then(context, x, y, lambda im: GiftSearch.chosen(context, im, []) == before, timeout=1)
        return False


def theme_pack_plan(settings, team):
    """(the team's plan, the data file's packs (name -> floors), its event packs, its title art reads): the default plan or
    the user's (spec 04 section 8)."""
    file = data("theme_packs.yaml")
    ref = team["theme_pack_plan"]
    plan = file["default_plan"] if ref == "default" else next(p for p in settings["theme_pack_plans"] if p["id"] == ref)
    return plan, file["packs"], set(file["event_packs"]), file["title_art"]


@functools.cache
def pack_ids():
    """Pack name -> id, every pack of the data file's `pack_ids`."""
    return data("theme_packs.yaml")["pack_ids"]


def run_packs():
    """The ids of the theme packs the run pulled so far, or None when unknown: the agent restarted mid-run (ADR 0003). The gift list's exclusive recipes lock their materials all the same when it is None (gifts.lockers, #306)."""
    return RUN.get("packs")


def note_pack(name):
    """Note the pack PickThemePack pulled in the run; a run that lost its earlier floors leaves it unknown, a pack the data file
    has no id for (most EXTREME-only packs, an event pack newer than the file) is skipped and the rest stay noted."""
    if "packs" not in RUN:
        return
    ids = pack_ids()
    if name not in ids:
        log(f"pack {name!r} has no id: left out of the run's packs")
        return
    # A re-run (BokGak) shows the original's title: a card whose BokGak line was read is already the copy's name (one id), else the
    # pull may be either: note both (some recipes name only the re-run).
    RUN["packs"] += [i for i in (ids[name], ids.get(f"{name} BokGak")) if i is not None and i not in RUN["packs"]]


def pack_titles(context, image):
    """Cards left to right as (x centre, [text lines top to bottom]); see run_start.pack_cards."""
    return run_start.pack_cards(ocr(context, image, PACK_TITLES))


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


def refresh_lit(image):
    """Whether the theme pack page's Refresh button is lit: REFRESH_LIT_MIN of its px over REFRESH_BRIGHT (#482)."""
    x, y, w, h = REFRESH_BUTTON
    return bool((image[y:y + h, x:x + w].max(axis=2) > REFRESH_BRIGHT).sum() >= REFRESH_LIT_MIN)


@AgentServer.custom_action("PickThemePack")
class PickThemePack(CustomAction):
    """Set this floor's difficulty, then pull the best pack: highest weight, leftmost first (spec 03 sections 2, 6)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        floor = floor_number(text(context, image, [480, 100, 320, 40]))
        if floor is None:
            return True  # page fading in or out: let MirrorHub look again
        if floor != RUN.get("floor"):
            RUN.pop("after_shop", None)
            if floor == 1:
                RUN.pop("floors_hard", None)  # a floor 1 after a later floor is a new run's: no difficulty of the last one stays (#382)
            RUN.pop("resumed", None)  # this floor's map comes up from its theme pack
            TASK.pop("modules", None)  # a run is under way: Claim will take 5, the next one reads the Modules again (#369)
            RUN.update(floor=floor, map_misses=0)  # a new floor's map gets a fresh retry quota (spec 06)
            restart_floor_clock()
            STUCK["ladder"].floor(floor, run["settings"].get("run", {}).get("target_floor", 5))  # floors 6 and 11 refill L2/L3 (#435)
        want = None if run["difficulty"] is None else run_start.hard_wanted(floor, run["difficulty"] == "hard", run["team"]["hard_from_floor"])
        if not self.set_difficulty(context, floor, want):
            return stuck(f"floor {floor} difficulty did not switch to {'HARD' if want else 'NORMAL'}")

        plan, file_packs, event_packs, file_art = theme_pack_plan(run["settings"], run["team"])
        packs, names, title_art = run_start.floor_reads(file_packs, plan["weights"], file_art, floor)  # #387: the floor's packs
        setting = run["settings"]["run"]["theme_pack_refresh"]
        prev = None
        for used in range(10):  # a greyed button or its `0/m` ends it (#319, #482); unread, a refresh that changes nothing does
            settled = still(context, timeout=CARDS_SETTLE, roi=PACK_CARDS, runs=2)
            if settled is None:
                log(f"floor {floor}: the cards still moved after {CARDS_SETTLE:g} s")
            page = page_guard(context, "ThemePack", settled)
            cards = pack_titles(context, page)
            if not cards:
                return stuck("no theme pack titles read")
            ranked = run_start.rank_packs([lines for _, lines in cards], names, plan, title_art,
                                          lambda i, allowed: pack_cover.read_cover(page, cards[i][0], allowed))
            slots = run_start.event_slots(floor, [t for t, _, _ in ranked], event_packs, packs)
            log(f"floor {floor} packs, threshold {plan['threshold']}: "
                + ", ".join(f"{t} ({w}{', event' if e else ''})" for (t, w, _), e in zip(ranked, slots)))
            log(f"floor {floor} card reads: " + ", ".join(f"{t} <- {how}" for t, _, how in ranked))  # #274: which path named each card
            titles = [t for t, _, _ in ranked]
            i, meets = run_start.pick_pack([w for _, w, _ in ranked], slots, plan)
            if not run_start.refresh_wanted(meets, setting, used) or titles == prev:
                break
            if not refresh_lit(page) or seen(context, page, "PackRefreshSpent"):
                log(f"floor {floor}: no free refresh left")
                break
            prev = titles
            # A fixed 3 s (#258): the new hand swings in and stood still 2.71-2.97 s after the tap (the 5 refreshes that
            # dealt one on the 2026-10-29 and 2026-11-08 recordings, tools/tap_waits.py), so the still() above would read
            # it at most 0.3 s sooner.
            tap(context, 1083, 47, wait=3)
        x = cards[i][0]
        log(f"floor {floor}: pull {ranked[i][0]!r} ({ranked[i][1]}{'' if meets else ', below the threshold'})")
        swipe(context, x, 330, x, 650, ms=600, wait=0)
        note_pack(ranked[i][0])
        RUN["fresh_floor"] = True  # find_bus: the new map takes no drag for its first seconds
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
                RUN.setdefault("floors_hard", {})[floor] = hard  # what Settle's weekly bonuses count on (#382)
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
# px off BUS_HOME, across and down, at which find_bus takes the bus as home (#26 picked them; nothing measured them).
# RouteMap.read_on leaves a drag back this short undone (#490): live, the 1 px one left after each 510 px drag back did
# not move the map (2026-11-06, 5 of 5).
BUS_SLACK = (30, 25)
BUS_REST = (446, 248)
SLOT = (279, 37)  # middle-row slot centre; map_route.ROW_DY gives the other rows
BUS_TAP = (22, 37)  # px off the bus box's top-left where it is tapped and where its links start


def slot_centre(bx, by, row):
    """(x, y) of the slot in row of the column after the bus at (bx, by)."""
    return bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]


def bus_tap(bx, by):
    """(x, y) of the bus at (bx, by) to tap, and where its links start."""
    return bx + BUS_TAP[0], by + BUS_TAP[1]


LINKS = {
    "up": ("MapLinkUp", (90, -115, 110, 110)),
    "mid": ("MapLinkMid", (95, -10, 110, 80)),
    "down": ("MapLinkDown", (85, 85, 110, 110)),
}
BUS_PROBE = 1.0  # s a first tap on the bus waits for the node panel (#130)
BUS_LINK = 60  # line_contrast of a lit link from the bus; links between other nodes read up to ~50
MARKS = {  # node -> (mark, roi around the slot centre)
    "MapNodeBoss": ("boss", (-40, -40, 80, 80)),
    "MapNodeFocusedHex": ("ring", (-80, -60, 160, 120)),  # the WARNING ring: Risky's and Abnormality's (#91)
    "MapNodeFocusedRound": ("ring", (-75, -60, 150, 120)),
    "MapNodeCost": ("cost", (-60, -80, 120, 60)),
    "MapNodeGift": ("gift", (-60, -80, 120, 60)),
    "MapNodeEvent": ("event", (-60, -60, 120, 120)),
    "MapNodeShop": ("shop", (-60, -60, 120, 120)),
}
# The shop's icon in grey, each with its own threshold: the plain one, the "+" variant (a star at the top left, a "+" at the
# bottom right, hard floors) and one torn-frame capture (#287)
SHOP_ICONS = ("MapNodeShopIcon", "MapNodeShopIconPlus", "MapNodeShopIconTorn")
FEATURE_MATCH = {"MapNodeFocusedHex", "MapNodeEvent", "MapNodeShop"}  # the pipeline's FeatureMatch nodes
FEATURE_PAD, FEATURE_ALIGN = 64, 32  # px of the screen kept around a FeatureMatch roi; grid of the cut's corner
ENTER = (1133, 543)
BACK_KEY = 4  # Android's back key (L1's too): closes the node panel
MAP_RETRIES = 3  # RouteMap calls per floor that may enter nothing before the map is stuck
MAP_LOOKS = 4  # looks, 1 s apart, for a linked slot before the fallback taps
# #202: columns up to this x are typed by their Cost too: with the bus at the far left, its two columns (329, 584).
# Past them only the marks, which miss the WARNING ring (#238); a drag brings those columns here to be read again.
MAP_NEAR = 650
BAR_BOTTOM = 60  # the resource bar's border: y 59-60 on the map captures
MAP_DRAGS = 3  # drags of two columns RouteMap.read_on makes at most: the first screen shows four, a floor ~7 and the boss
PANEL_REWARDS = [700, 495, 110, 30]  # the "Clear Rewards" label
PANEL_COST = [730, 545, 40, 35]  # the number by its Cost coin
MAP_TITLE = [40, 85, 240, 35]  # "Exploring Floor 3", top left
MAP_LEAVING = 6  # s RouteMap waits for the last floor's map to give way to this floor's
MAP_PAN_LIMIT = 8  # s find_bus drags a fresh NORMAL map again that took none of its drags
# px (a pan's larger axis) from which find_bus looks as the finger stops whether the map ignored the pan (#486). On the six
# runs' recordings every find_bus pan was 396 px: at its last move the bus had moved 0 px on the 20 ignored ones and trailed
# the finger by 126 px at most on the 108 taken ones. A shorter pan, taken, may not have moved yet: it rests as before.
PAN_LOOK_MIN = 300
BUS_JITTER = 3  # px the bus's match moves on a map that did not move
# #473: back on the map from a fight's loading screen or its reward pages, the game ignores taps on the still map for a
# time that differs by run, with no sign on screen (over 1.46 s after the fade-in on 2026-11-07, under 1.32 s on
# 2026-11-06). Recordings of 5 runs, recovery.same_screen's blocks: a node tap the game took moved 52.4% of them or more,
# from 0.13-0.23 s after it was sent (75 taps); one it ignored moved 1.0% at most over 2 s (26 taps, 3 runs), and the
# next touch, at most 2.6 s later, was always taken.
MAP_ANSWER = 0.7  # s a tap on the map has to answer (its node panel, or the screen moving) before follow taps again
MAP_TAP_LIMIT = 4  # s follow taps its node again, and find_bus drags the map again (#486), while the map ignores touches


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
    if not marks.keys() & {"boss", "ring", "cost", "gift", "shop"} and (hit := shop_icon(context, image, cx, cy)):
        marks["shop"] = hit
    return marks


def shop_icon(context, image, cx, cy):
    """The hit of the shop's icon (MapNodeShopIcon) around the node centred at (cx, cy), whatever the pack's colours.

    The icon takes the theme pack's hue: cyan and orange packs (live 2026-10-18) matched none of the colour
    templates. TemplateMatch CCOEFF on the brightness alone (max over the channels) is blind to hue and to the
    pack's brightness: the shop scored 0.49-1.0 on 12 packs' captures, anything else 0.31 at most.
    The "+" variant of the hard floors scored 0.33-0.39 on it, so it has its own templates; the best score of the three decides.
    """
    ox, oy, w, h = MARKS["MapNodeShop"][1]
    window = image[max(0, cy + oy):cy + oy + h, max(0, cx + ox):cx + ox + w]
    if window.shape[0] < 40 or window.shape[1] < 70:
        return None
    grey = np.repeat(window.max(axis=2)[..., None], 3, axis=2)
    box = (0, 0, window.shape[1], window.shape[0])
    hits = [hit for n in SHOP_ICONS if (hit := seen(context, grey, n, box))]
    return max(hits, key=lambda hit: hit.best_result.score, default=None)


def node_at(context, image, cx, cy, marks=None, costs=True):
    """The type of the map node centred at (cx, cy), by its marks and Cost number (map_route.node_type).

    No mark at all where the badges (80 px above the centre) sit under the resource bar: unknown, not an
    event; a fight's Cost coin may be hidden there (the top row with the map at rest). With costs, a coin the bar
    cuts counts when its number shows below it (coin_cut_by_bar).
    #91: with costs, a fight's kind is its Cost number looked up in the floor's difficulty's node_costs
    (map_weights.yaml), as read: a number unread or not in the table leaves the marks to decide (cost_miss logs it).
    The boss' Costs are in the table too: a boss whose red glow went unmatched reads as the boss by its Cost.
    Only the columns up to MAP_NEAR are read so: further out the badges may be dim (offline, MirrorMap.png's
    85 two columns out read 8 with the crop before #284). Those come near as RouteMap.read_on drags the map, and a planned slot is read
    again once next to the bus (RouteMap.follow).
    """
    marks = node_marks(context, image, cx, cy) if marks is None else marks
    under_bar = cy - 80 < BAR_BOTTOM
    if costs and under_bar and not marks.keys() & {"cost", "boss"} and (coin := coin_cut_by_bar(context, image, cx, cy)):
        marks = {**marks, "cost": coin}
    if not marks and under_bar:
        return "unknown"
    if not (costs and "cost" in marks and "boss" not in marks):
        return map_route.node_type(set(marks))
    difficulty, table = difficulty_costs(context)
    found = coin_text(context, image, marks["cost"].box)
    cost = coin_number(found)
    kind = map_route.node_type(set(marks), table.get(cost))
    log(f"map: node at {cx}, {cy} reads Cost {cost}: {kind}")
    if cost not in table:
        cost_miss(image, marks["cost"].box, cx, cy, found, difficulty)
    return kind


def coin_cut_by_bar(context, image, cx, cy):
    """The hit of the node's Cost coin with its top rows under the resource bar, None when there is none (#522).

    Its number, read from the coin box's bottom row as coin_text reads it, decides: a coin wholly under the bar scores
    as high (0.60-0.79 on the top-row battles of MapBoss.png at 215, 72, MapEvent.png and MapRock.png at 725, 72,
    MapFocused.png at 470, 72), and its number's crop lands on the bar's resource counts (MapFocused's read 19).
    """
    ox, oy, w, h = MARKS["MapNodeCost"][1]
    coin = seen(context, image, "MapNodeCostCut", (cx + ox, cy + oy, w, h))
    if not coin or coin.box[1] + coin.box[3] < BAR_BOTTOM:
        return None
    _, table = difficulty_costs(context)
    return coin if coin_number(coin_text(context, image, coin.box)) in table else None


def difficulty_costs(context):
    difficulty = "hard" if is_hard(context) else "normal"
    return difficulty, map_data()["node_costs"][difficulty]


def coin_text(context, image, box):
    """The OCR text of the number printed beside a map node's Cost coin (box): coin_number makes it a number.

    The game's font, right-aligned, 8 px a digit and 14 rows tall: the digits fill x+w-12 .. x+w+12, y+24 .. y+37
    (measured on every labelled coin: the glyph rows never move), and the crop ends on their last row (#284): a lit
    link's pale arrow starts on y+38, right under the number, as cream as the digits, and the crop that kept it joined
    the 5 of a 75 or 85 to the arrow's tip (read '7' or '8'); a crop one row shorter clips the digits (a 180 read 18T).
    A row more above (the coin's frame) read an 85 as B5 once. The digits are the
    bright, barely saturated pixels; each keeps its own shading, dark on white, rather than going plain black: its
    1 px counters are what tell an 8 from a 0, and a black cut-out loses them (8 read B). A white margin: the OCR
    reads a glyph on the crop's edge badly (#257; spec 03 section 7).
    """
    x, y, w, _ = box
    part = image[y + 24:y + 38, max(0, x + w - 13):x + w + 13]
    bright = part.max(axis=2)
    mask = (bright > 100) & (saturation(part) < 120)
    plain = np.where(mask, 255 - bright, 255).astype(np.uint8)[..., None].repeat(3, axis=2)
    plain = np.pad(plain, ((6, 6), (6, 6), (0, 0)), constant_values=255)
    return text(context, plain, [0, 0, plain.shape[1], plain.shape[0]], only_rec=True)


def coin_number(found):
    """The Cost number in coin_text's OCR text; None for a part read (coin_part says which)."""
    digits = re.sub(r"\D", "", found)
    return None if coin_part(digits) else int(digits)


def coin_part(digits):
    """Why the digits of a Cost read are only part of a number, or None when they make one."""
    return "no digits" if not digits else "one digit" if len(digits) < 2 else "leading 0" if digits[0] == "0" else None


def cost_miss(image, box, cx, cy, found, difficulty):
    """Log why a Cost coin's read is no Cost of the floor's difficulty, and keep its crop in logs/cost (#284)."""
    digits = re.sub(r"\D", "", found)
    why = coin_part(digits) or f"{digits} is no {difficulty} Cost"
    x, y, w, h = box
    stamp = f"{settlement.now().replace(':', '-')}_{cx}_{cy}"
    try:
        recovery.keep_capture(ROOT, "cost", image[max(0, y - 8):y + h + 24, max(0, x - 8):x + w + 24], stamp, recovery.COST_KEEP)
        kept = f", crop logs/cost/{stamp}.png"
    except OSError as e:
        kept = f", crop not saved: {e}"
    log(f"map: Cost miss at {cx}, {cy} ({difficulty}): {why}, OCR {found!r}{kept}")


def map_data():
    return data("map_weights.yaml")


def is_hard(context):
    """Whether this floor is on hard: set_difficulty's floor_hard, else the run's difficulty."""
    run = current_run(context)
    return run.get("floor_hard", run.get("difficulty") == "hard")


def map_weights(context):
    return map_data()["hard" if is_hard(context) else "normal"]


def map_floor(context, image):
    """The floor number the map's title shows; None when it is covered or unreadable.

    Swept 2026-10-19 over every 0.25 s from the 10 theme pack pulls of two runs: the last floor's number, a gap,
    the new one; never a third number. tests/screens/MapBoss.png reads "Floar 3".
    """
    return floor_number(text(context, image, MAP_TITLE), r"fl[a-z]*")


def enter_node(context):
    """On the node selection panel: log its Clear Rewards, press Enter until the panel is gone."""
    # Only logged: events show no Clear Rewards, a shop shows the next boss's (spec 03 section 7).
    image = screen(context)
    cost = number(text(context, image, PANEL_COST)) if has(text(context, image, PANEL_REWARDS), "Rewards") else None
    log(f"node panel: Clear Rewards Cost {cost}")
    leave_shop()  # a shop left without its Leave (#118): the next shop is a new visit
    for _ in range(3):
        tap(context, *ENTER, wait=0)
        if until(context, lambda im: not seen(context, im, "MapNodePanel")) is not None:
            log("entered the node")
            RUN.pop("fresh_floor", None)
            RUN.pop("after_shop", None)
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

    A gift window over the map, or the last floor's map still up after a theme pack (wait_for_floor), goes back
    to MirrorHub first.
    Slots linked to the bus (its lit line or a chevron on it) are typed by their marks, ranked by
    map_route.rank over the columns read (on screen, then on a NORMAL floor the rest, two columns a drag: read_on)
    and, the map dragged back to the bus, tapped in that order until the node panel (MapNodePanel)
    shows. After them come the fallbacks: the bus (a node reached but not entered; first after a restart or a
    recovery, #88; in such a continued run the bus is tapped before any read when no slot is linked to it, #379), then the slots not tried yet. No bus on screen: the map is dragged about for it (#61).
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
        image = still(context)
        if image is None:
            return True  # still fading in or out: let MirrorHub look again
        if seen(context, image, "GiftGet"):
            log("map: an E.G.O gift window covers the map; MirrorHub takes it")
            return True
        if not self.wait_for_floor(context, image):
            return True  # MirrorHub looks again once the map is this floor's
        if not self.unzoom(context):  # its slots sit off where the offsets put them: L2 puts the map back
            if seen(context, screen(context), "MapNodePanel"):  # L2 needs the map: enter the node instead
                return enter_node(context)
            return stuck("the map stays zoomed in on the bus", level=2)
        if self.follow(context):
            return enter_node(context)
        RUN.pop("map_plan", None)
        if not RUN.get("map_entered") and self.tap_bus_first(context):
            return enter_node(context)
        for _ in range(MAP_LOOKS):  # live: right after a floor's theme pack, the map shows before its bus and links
            if (image := still(context)) is None:
                return True  # still fading in or out: let MirrorHub look again
            if seen(context, image, "GiftGet"):  # live 2026-10-19: it slid in over the map after a fight
                log("map: an E.G.O gift window covers the map; MirrorHub takes it")
                return True
            image, bus = self.find_bus(context)
            bx, by = bus or BUS_REST  # no bus found: assume the map at rest
            slots = self.read_slots(context, image, bx, by) if bus else {}
            if slots:
                break
            time.sleep(1)  # kept (#58): the bus and links come after the map stands still; MAP_LOOKS looks 1 s apart
        if not bus and self.search_bus(context):  # #61: the map dragged off by hand
            image, bus = self.find_bus(context)
            bx, by = bus or BUS_REST
            slots = self.read_slots(context, image, bx, by) if bus else {}
        log("map: column 1: " + (", ".join(f"{r} {t} ({'?' if n is None else n} onward)" for r, (t, n) in slots.items()) or "no linked slot read"))
        if slots and RUN.get("after_shop"):  # #279: the page handled last was the shop, so the only node to take is the boss
            if changed := map_route.boss_after_shop({"bus": ("shop", None)}, slots):
                log(f"map: left the shop; column 1 {', '.join(changed)} read as something else than the boss")
            else:
                log("map: left the shop; column 1 is the boss")
        ahead = self.read_ahead(context, image, bx + SLOT[0], by + SLOT[1], slots) if slots else []
        if slots and not RUN.get("floor_hard"):  # #202: the rest of the floor, two columns a drag; a HARD map does not pan (#129)
            ahead, bus = self.read_on(context, image, bus, slots, ahead)
            bx, by = bus or BUS_REST
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

        ranked = [(f"{r} {slots[r][0]}", slot_centre(bx, by, r)) for r in order]
        on_bus = [("the bus", bus_tap(bx, by))]
        # #88: after a restart or a recovery the bus may stand on a node not entered yet; its own tap opens it.
        tries = ranked + on_bus if RUN.get("map_entered") else on_bus + ranked
        tries += [(f"{r} slot", slot_centre(bx, by, r)) for r in map_route.ROWS if r not in order]
        # #130: a bus tap on a node already entered shows nothing; a panel shows within ~0.5 s, so that probe is short.
        probe = not RUN.get("map_entered")
        for name, (x, y) in tries:
            if RouteMap.tap_for_panel(context, x, y, BUS_PROBE if probe and name == "the bus" else 2.0):
                log(f"map: take {name}")
                if steps is not None and (x, y) == ranked[0][1]:  # the path's first node: follow the rest
                    RUN["map_plan"] = {"floor": RUN.get("floor"), "steps": steps}
                RUN["map_entered"] = True
                return enter_node(context)
        page_guard(context, "MirrorMap")  # #213: a GET! window that rose during the last tap's wait is no miss
        if not bus:  # #61: L2's To Window and Resume put the map back; L1's back key does nothing here
            return stuck("no bus on the map, even after dragging it about", level=2)
        RUN["map_misses"] = RUN.get("map_misses", 0) + 1
        if RUN["map_misses"] >= MAP_RETRIES:
            return stuck(f"no node on the map took a tap, {MAP_RETRIES} times this floor")
        log("map: no node took a tap; MirrorHub looks again")
        return True

    @staticmethod
    def wait_for_floor(context, image):
        """Whether the map is this floor's, after waiting out the last floor's, still up after a theme pack pull.

        Live 2026-10-19 (8 of 8 floors after the first): the last floor's map stayed ~3 s after the pull, its bus
        driving off to the exit; RouteMap dragged it, then read the new floor with its bus at rest.
        A title that keeps another number for MAP_LEAVING s is a misread: it is not looked at again this floor.
        """
        floor, shown = RUN.get("floor"), map_floor(context, image)
        if floor is None or shown in (None, floor) or RUN.get("title_off") == floor:
            return True
        log(f"map: floor {shown}'s map is up, floor {floor} next; waiting for it")
        if until(context, lambda im: map_floor(context, im) == floor, timeout=MAP_LEAVING) is not None:
            return False  # MirrorHub looks again: the new map may still be fading in
        log(f"map: the title stays floor {shown}; reading the map as it is")
        RUN["title_off"] = floor
        return True

    @staticmethod
    def tap_for_panel(context, x, y, timeout, image=None):
        """Whether a tap at (x, y) opened the node panel (MapNodePanel) within timeout s; the page is checked first."""
        page_guard(context, "MirrorMap", image=image)
        tap(context, x, y, wait=0)
        return until(context, lambda im: seen(context, im, "MapNodePanel"), timeout=timeout) is not None

    @staticmethod
    def tap_until_answered(context, x, y, image):
        """Tap (x, y), the page checked before each tap, until the map answers: its node panel (MapNodePanel) shows or
        the screen leaves the one the first check passed (recovery.same_screen). Whether it did; no tap is made again
        once MAP_TAP_LIMIT s have passed since the first (#473)."""
        before, end = recovery.thumb(page_guard(context, "MirrorMap", image=image)), time.monotonic() + MAP_TAP_LIMIT

        def answered(im):
            return seen(context, im, "MapNodePanel") or not recovery.same_screen(before, recovery.thumb(im))
        while True:
            tap(context, x, y, wait=0)
            if until(context, answered, timeout=MAP_ANSWER) is not None:
                return True
            if time.monotonic() >= end:
                return False
            log(f"map: no answer to the tap at {x}, {y}; tapping again")
            page_guard(context, "MirrorMap")

    @staticmethod
    def tap_bus_first(context):
        """Whether the bus, tapped where it stands, opened its node panel; only in a continued run (#379).

        A continued run is one this agent process did not see the earlier floors of (a restart: no floor in memory)
        or that came back from a recovery (forget_game_state); a run's first floor taps no bus first, it has no node
        entered yet and the tap would only wait BUS_PROBE s.
        Live: the bus stood on the Boss with no slot to its right; the looks and pans for a linked slot cost ~21 s
        (11 drags at the map's edge) before the bus was tapped (#88). A bus with no linked slot is tapped at once,
        without panning; with a slot linked, or the panel not showing within BUS_PROBE s, the full read follows.
        """
        if not run_continued():
            return False
        image = still(context)
        bus = seen(context, image, "MapBus") if image is not None else None
        if not bus or RouteMap.read_slots(context, image, bus.box[0], bus.box[1]):
            return False
        if not RouteMap.tap_for_panel(context, *bus_tap(bus.box[0], bus.box[1]), BUS_PROBE, image=image):
            return False
        log("map: column 1: no linked slot read")
        log("map: take the bus")
        RUN["map_entered"] = True
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
        page_guard(context, "MirrorMap", image=image)
        if tap_then(context, *box_centre(zoomed.box), lambda im: seen(context, im, "MapNodePanel")) is None:
            log("map: the zoomed bus took no tap")
            return False
        back(context)
        if until(context, lambda im: seen(context, im, "MapBus"), timeout=3) is None:
            log("map: still zoomed in after the back key")
            return False
        RUN["map_entered"] = False
        RUN.pop("map_plan", None)  # its next step starts past the bus's node: read the map again
        return True

    @staticmethod
    def find_bus(context):
        """A screenshot and the bus's top-left in it, after panning the bus to BUS_HOME.

        Up to three pans that move the bus. A pan that leaves the bus where it was (the map ignored it) does not count
        and is made again, for up to MAP_TAP_LIMIT s (#486: after a fade-in the game ignores the map's touches for a
        while); on a floor's fresh NORMAL map (no node entered since the theme pack) for up to MAP_PAN_LIMIT s: live
        2026-10-19, a new map took no drag for its first seconds. Once a pan has moved the bus, one that does not is
        the map's edge. On a pan of PAN_LOOK_MIN px or more, a screenshot as the finger stops that shows the bus where
        it was lifts the finger at once and is the next look: no rest, no 0.5 s wait (#486).
        """
        def stays(hit, at):  # a MapBus hit within BUS_JITTER of at: the map has not moved
            return hit is not None and at is not None and abs(hit.box[0] - at[0]) <= BUS_JITTER and abs(hit.box[1] - at[1]) <= BUS_JITTER

        limit = MAP_PAN_LIMIT if RUN.get("fresh_floor") and not RUN.get("floor_hard") else MAP_TAP_LIMIT  # a HARD map does not pan (#129)
        end, pans, last, moved = time.monotonic() + limit, 0, None, False
        image = screen(context)
        while True:
            bus = seen(context, image, "MapBus")
            if not bus:
                return image, None
            bx, by = bus.box[0], bus.box[1]
            dx, dy = BUS_HOME[0] - bx, BUS_HOME[1] - by
            if abs(dx) <= BUS_SLACK[0] and abs(dy) <= BUS_SLACK[1]:
                return image, (bx, by)
            held = stays(bus, last)
            if held and moved:
                return image, (bx, by)  # live 2026-10-21 NORMAL: the map's left edge stopped the bus at 196
            moved = last is not None and not held
            if held:
                if time.monotonic() > end:
                    log(f"map: the bus stayed at {bx}, {by} through {limit} s of drags")
                    return image, (bx, by)
            else:
                if pans == 3:
                    return image, (bx, by)
                pans += 1
            # Look again after each pan. Start on map background: between the first and second columns,
            # between the middle and bottom rows. #213: a GET! window rising over the map ends the pans.
            page_guard(context, "MirrorMap", image=image)
            last = (bx, by)
            look = max(abs(dx), abs(dy)) >= PAN_LOOK_MIN
            image = scroll(context, min(bx + SLOT[0] + map_route.COLUMN_DX // 2, 1100), by + SLOT[1] + 106, dx, dy,
                           ignored=(lambda im: stays(seen(context, im, "MapBus"), last)) if look else None)
            if image is None:
                time.sleep(0.5)  # kept (#58): the map coasts on after the lift; the look after the pan reads it at rest
                image = screen(context)

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
            time.sleep(0.5)  # kept (#58): the map coasts on after the lift
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
                cx, cy = slot_centre(bx, by, row)
                slots[row] = (node_at(context, image, cx, cy), map_route.routes(v, cx, cy))
        return slots

    @staticmethod
    def linked(context, image, bx, by, row):
        """Whether the slot in row is linked to the bus.

        Live 2026-10-18, bus at the far left: the chevrons scored 0.75-0.84 against 0.8, the lit link
        itself 157-171 against -2 unlinked; either one counts.
        """
        node, (rx, ry, rw, rh) = LINKS[row]
        lit = map_route.line_contrast(image.max(axis=2), *bus_tap(bx, by), *slot_centre(bx, by, row))
        return lit is not None and lit >= BUS_LINK or bool(seen(context, image, node, (bx + rx, by + ry, rw, rh)))

    @staticmethod
    def follow(context):
        """Tap the next node of this floor's planned path; whether its node panel showed (#111).

        Only that slot is read, and the map is dragged (bus to the far left) only when it sits under the
        resource bar or the buttons. False, for a full read, whenever in doubt: no plan or a used-up one,
        the slot not linked to the bus or not of the planned type (the bus not where the plan put it, or a
        misread from afar), or no panel after its tap, made again while the map ignores it (#473).
        """
        plan = RUN.get("map_plan")
        if not plan or plan["floor"] != RUN.get("floor") or not plan["steps"]:
            return False
        row, node = plan["steps"][0]
        image = screen(context)
        bus = seen(context, image, "MapBus")
        bus = bus and tuple(bus.box[:2])

        def clear(bx, by):  # the slot's node, badges included, clear of the resource bar and the buttons
            x, y = slot_centre(bx, by, row)
            return x + 80 <= 1200 and y - 80 >= BAR_BOTTOM
        if not bus or not clear(*bus):
            image, bus = RouteMap.find_bus(context)
        if not bus or not RouteMap.linked(context, image, *bus, row):
            log(f"map: planned {row} {node} not linked to the bus; reading the map again")
            return False
        cx, cy = slot_centre(*bus, row)
        kind = "boss" if RUN.get("after_shop") else node_at(context, image, cx, cy)  # #279: the shop was the last page
        if kind != node:
            log(f"map: planned {row} {node} reads {kind}; reading the map again")
            return False
        if not RouteMap.tap_until_answered(context, cx, cy, image):
            log(f"map: planned {row} {node} took no tap in {MAP_TAP_LIMIT} s; reading the map again")
            return False
        if until(context, lambda im: seen(context, im, "MapNodePanel")) is None:
            log(f"map: planned {row} {node} moved the map but showed no panel; reading the map again")
            return False
        log(f"map: follow plan {row} {node}")
        plan["steps"] = plan["steps"][1:]
        return True

    @staticmethod
    def read_ahead(context, image, x, y, before, first=2):
        """The columns on screen past the one at x (its middle row's centre at y), whose nodes are before's rows.

        For map_route.rank. A node counts when a link into it from the column before reads (map_route.line_contrast);
        only rows next to each other link. Every node leads on, so one with no link read onward takes its brightest
        (map_route.FAINT_LINK, #212). A node up to MAP_NEAR is typed by its Cost too, past it by its marks (#238).
        The read ends at the screen's edge, at a column with nothing linked or dark (no mark and no light on any
        node: hard mode shows two columns), or after the boss: none at all when before holds it (#279), and none past
        the column after a shop (map_route.boss_after_shop). first: the first column's number, for the log.
        """
        dx, dy = map_route.COLUMN_DX, map_route.ROW_DY
        v, ahead = image.max(axis=2), []
        if map_route.has_kind(before, "boss"):  # #279: its red glow reads 7.7-12.4 towards the next column, as a faint link
            return ahead
        while x + dx + 80 <= 1200:  # MapNodeFocusedHex reads 80 px either side; buttons from x 1205
            x += dx
            column, lit = {}, False
            links = map_route.links({(r, row): map_route.line_contrast(v, x - dx, y + dy[r], x, y + dy[row]) or 0
                                     for r in map_route.ROWS for row in map_route.ROWS if map_route.near(r, row)})
            for row in map_route.ROWS:
                linked, ry = {src for src, dst in links if dst == row and src in before}, y + dy[row]
                if linked:
                    marks = node_marks(context, image, x, ry)
                    column[row] = (node_at(context, image, x, ry, marks, costs=x <= MAP_NEAR), linked)
                    # A node with no mark may still be lit: a red pack's dim "?" (live 2026-10-18) reads 48-60
                    # here; hard mode's dark columns read 0.
                    lit = lit or bool(marks) or np.percentile(v[ry - 45:ry + 45, x - 45:x + 45], 90) >= 20
            if not lit and not (column and map_route.has_kind(before, "shop")):  # #279: the boss after a shop may read dark
                break
            n = first + len(ahead)
            glow = [row for row, (t, _) in column.items() if t == "boss"]
            if changed := map_route.boss_after_shop(before, column):  # #279: the shop decides, the boss' glow only helps
                log(f"map: column {n}: after the shop, so the boss; {', '.join(changed)} read as something else")
            elif glow and not map_route.has_kind(before, "shop"):
                log(f"map: column {n}: the boss' glow without a shop before it")
            ahead.append(column)
            RouteMap.log_column(n, column)
            if map_route.has_kind(column, "boss"):
                break
            before = column
        return ahead

    @staticmethod
    def log_column(n, column):
        log(f"map: column {n}: " + ", ".join(f"{r} {t} (from {'/'.join(sorted(src))})" for r, (t, src) in column.items()))

    @staticmethod
    def retype(context, image, column, x, y, n):
        """Type column n, read from afar, again by its Cost now that it sits at x, up to MAP_NEAR (in place).

        The boss stays one: it was told by the shop before it (#279), a dark one reads as an event here.
        """
        for row, (kind, linked) in column.items():
            column[row] = (kind if kind == "boss" else node_at(context, image, x, y + map_route.ROW_DY[row]), linked)
        RouteMap.log_column(n, column)

    @staticmethod
    def read_on(context, image, bus, slots, ahead):
        """The floor past the screen's right edge (#202): (ahead read on, two columns a drag; the bus, back home).

        Each drag moves the map two columns left, measured on the frames before and after it (map_route.shift).
        The read goes on (read_ahead) from the last column read whose next two then sit up to MAP_NEAR, so they are
        read again with their Cost (#238) and replace what was read of them from afar, and the links into them
        join them to the columns read before; the column read on from, if it was past MAP_NEAR before the drag, and
        what a near read ending sooner keeps past it, up to MAP_NEAR, are typed again by their Cost (retype). The read ends at the boss, a read that ends short of the screen's edge
        with nothing read past it (hard mode's two columns), a drag that moves the map less than half a column or
        leaves no column to read on from (its edge), or one that cannot be measured (what was read stands), or after
        MAP_DRAGS drags.
        The map is then dragged back as far, less a remainder within BUS_SLACK, and the bus found again (find_bus).
        """
        dx, (bx, by) = map_route.COLUMN_DX, bus
        x0, y, moved, undo = bx + SLOT[0], by + SLOT[1], 0, 0
        edge = x0 + len(ahead) * dx + dx + 80 > 1200  # the last column read was the last on screen: more may follow
        for _ in range(MAP_DRAGS):
            columns = [slots, *ahead]
            if not edge or map_route.has_kind(columns[-1], "boss"):
                break
            page_guard(context, "MirrorMap", image=image)
            scroll(context, x0 + 5 * dx // 2, y + 106, -2 * dx, 0)  # from map background, as find_bus: between columns and rows
            time.sleep(0.5)  # kept (#58): the map coasts on after the lift, and map_route.shift reads the drag at rest
            after = screen(context)
            s = map_route.shift(image.max(axis=2), after.max(axis=2), 2 * dx + 20)  # the drag, its threshold move and some fling
            undo += 2 * dx if s is None else s
            # Read on from the last column whose next two come up to MAP_NEAR, typed by their Cost.
            k = None if s is None else max((i for i in range(len(columns)) if x0 + i * dx - moved - s <= MAP_NEAR - 2 * dx), default=None)
            if k is None or s < dx // 2:
                log(f"map: a drag moved the map {'an unknown distance' if s is None else f'{s} px'}; planning on what was read")
                break
            moved, image = moved + s, after
            log(f"map: dragged the map {s} px; reading on from column {k + 2}")
            if k and x0 + k * dx - moved + s > MAP_NEAR:  # read from afar before this drag; at x 120 or more now
                RouteMap.retype(context, image, columns[k], x0 + k * dx - moved, y, k + 1)
            more = RouteMap.read_ahead(context, image, x0 + k * dx - moved, y, columns[k], first=k + 2)
            edge = x0 + (k + len(more)) * dx - moved + dx + 80 > 1200
            if (tail := ahead[k + len(more):]) and not (more and map_route.has_kind(more[-1], "boss")):
                # A near read ending short: what was read past it stays, up to an edge; near now, by its Cost.
                for i, column in enumerate(tail, start=k + len(more) + 1):
                    if (x := x0 + i * dx - moved) <= MAP_NEAR:
                        RouteMap.retype(context, image, column, x, y, i + 1)
                more, edge = more + tail, True
            if not more:
                break
            ahead = ahead[:k] + more
        if not undo:
            return ahead, bus
        while undo > BUS_SLACK[0]:
            page_guard(context, "MirrorMap")
            scroll(context, x0 + dx // 2, y + 106, min(undo, 2 * dx), 0)
            time.sleep(0.5)  # kept (#58): the map coasts on after the lift
            undo -= 2 * dx
        bus = RouteMap.find_bus(context)[1]
        if not bus and RouteMap.search_bus(context):
            bus = RouteMap.find_bus(context)[1]
        return ahead, bus


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
PICK_RETAP = 1.0  # s; a card tap that has not raised the count by then is tapped again (the old fixed wait guessed a tap within ~1 s of the last is lost, #253)
PICK_SETTLE = 1.5  # s; after a repeated tap the count is watched this long for a fall back: the first tap may have taken late (#253: the count showed 0.3-1.2 s after a tap, recordings, unverified)


def card_xy(i, ys):
    return CARD_X[i % 6], ys[i // 6]


def participants(context, image):
    """(selected, alive) from Total Participants, or None when it is not readable."""
    return fraction(text(context, image, PARTICIPANTS))


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
        end_battle()  # a new battle: its clock and turn count start over, also when the last VICTORY went unseen (#80)
        image = still(context)
        count = image is not None and participants(context, image)
        if not count:
            return True  # page fading in or out: let MirrorHub look again
        alive, need = count[1], run["team"]["min_alive"]
        RUN["alive"] = alive  # the shop's heal reads it (spec 03 section 13)
        if not has(text(context, image, DETAILS_BUTTON), "Details"):
            # its » folds the details view (skills, E.G.O), which hides the order marks
            tap_shown(context, 826, 125, lambda im: has(text(context, im, DETAILS_BUTTON), "Details"), timeout=1.5)
            image = screen(context)
        dead = dead_sinners(image)
        if len(dead) != 12 - alive:
            # The grey cards say who is dead, which the order needs; they decide (#616).
            log(f"formation: {12 - alive} dead by the count, grey cards {sorted(dead)}: the grey cards decide")
        order = battle.formation_order(run_start.resolve_plan(run["settings"], run["team"], "deployment_order"), dead)
        log(f"formation: {len(order)} of the deployment order alive, {alive} alive on screen, team needs {need}")
        if len(order) < need:  # need 0: no check; only the deployment order's sinners count (#616)
            # Like used-up wipe retries (#137): stop, or back out to the map, where RouteMap forfeits.
            reason = f"{len(order)} sinners of the deployment order alive, team {run['team']['name']!r} needs {need}"
            if run["settings"]["run"]["after_retries"] == "stop":
                return stop(context, reason)
            log(f"{reason}: forfeit the run")
            RUN["forfeit"] = reason
            # MirrorHub must not find the page again and back out twice.
            tap_then(context, *FORMATION_BACK, lambda im: seen(context, im, "Formation") is None, timeout=2)
            return True
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
        """Clear Selection, then tap the order card by card, each tap checked by the count going up by one (#253).

        Every tap is followed at once by until()'s looks at the count. A card whose count was read but is not n after
        PICK_RETAP s is tapped again. A second tap on a card that took the first one picks it off, so after a repeated
        tap the count is watched PICK_SETTLE s for a fall back, which is one more tap (the repeats wait PICK_SETTLE s
        for the count too); once that fall back shows, the later cards wait PICK_SETTLE s for their first tap as well.
        A count that could not be read for the whole wait (a page still moving) is waited for once more before the
        card is tapped again. Two taps after which the count was not n end the pick as stuck, for recovery.
        """
        def count_is(n, seen=None):
            def done(image):
                count = participants(context, image)
                if count and seen is not None:
                    seen.append(count[0])
                return count is not None and count[0] == n
            return done

        def fell_from(n):
            return lambda image: (count := participants(context, image)) is not None and count[0] != n

        dialog = []

        def cleared(image):
            dialog[:] = [has(text(context, image, RESET_DIALOG), "Reset Deployment")]
            return dialog[0] or count_is(0)(image)

        start, retaps, first_wait = time.monotonic(), 0, PICK_RETAP
        for _ in range(3):
            page_guard(context, "Formation")
            image = tap_then(context, *CLEAR_SELECTION, cleared, timeout=1.5)
            if image is not None and dialog[0]:
                image = tap_then(context, *RESET_CONFIRM, count_is(0), timeout=3)
            if image is not None:  # the count 0 it waited for
                break
        else:
            stuck("Clear Selection did not clear the formation")
            return False
        for n, sinner in enumerate(order, 1):
            picked, misses = False, 0  # taps (3 at most) after which the count was not n, 2 of them end the pick
            for attempt in range(3):
                page_guard(context, "Formation")
                seen = []
                done = count_is(n, seen)
                wait = first_wait if attempt == 0 else PICK_SETTLE  # a repeat has nothing to gain by hurrying
                image = tap_then(context, *card_xy(battle.SINNERS.index(sinner), CARD_TAP_Y), done, timeout=wait)
                if image is None and not seen:
                    image = until(context, done, timeout=wait)
                if image is not None:
                    if attempt == 0 or until(context, fell_from(n), timeout=PICK_SETTLE) is None:
                        picked = True
                        break
                    first_wait = PICK_SETTLE  # a tap took late: the next cards' first taps wait as long
                retaps += 1
                misses += image is None
                if misses == 2:
                    break
            if not picked:
                stuck(f"tapping {sinner} did not pick them")
                return False
        log(f"formation re-picked: {', '.join(order)}")
        log(f"formation pick took {time.monotonic() - start:.1f} s, {retaps} taps repeated")
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
# EgoCard (#468): in the daily run of 2026-11-07 the card was up after `turn 1: started`, still on TURN 1; what opened it
# there is unverified (a long press on a portrait opens it). A hold that meets it lifts at once, not after HOLD_LIMIT.
BATTLE_LEFT = BATTLE_POPUPS + ("Victory", "WipeDialog", "Event", "ClaimPopup", "Loading", "EgoCard")


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
        # screen moving), and a tap in the turn's opening can do nothing: act on a still HUD only. Live
        # 2026-10-21 (#229): a swarm of enemies kept the battlefield moving for good; turn 3 waited 18 min, twice.
        image = still(context, timeout=1, roi=battle.hud_band(argv.box), share=battle.HUD_MOVED)
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

        A staggered slot (battle.staggered, #427) acts no skill this turn and a tap on its portrait swaps nothing: it is
        neither tapped nor compared, and the chain makes no stop on it. The other slots guard, and the turn counts as a
        guard turn. With every slot staggered there is nothing to pick: START is pressed as it is (#69), and the turn
        counts too.
        """
        xs = battle.slot_xs(x)
        image = lower_skills(context, [lower_x(sx) for sx in xs])  # live: a first turn slides the portraits in late
        staggered = battle.staggered(image, xs)
        if all(staggered):  # #69: the plaque shows with no skill picked
            log("guard: every slot staggered, nothing to pick")
            page_guard(context, "BattleTurn", image=image)
            return press_start(context, disc)
        if any(staggered):
            log(f"guard: slots {[n for n, s in enumerate(staggered, 1) if s]} staggered, the rest on guard")
        numbers = [n for n, s in enumerate(staggered, 1) if not s]  # the slots that act: their numbers and x
        acting = [sx for sx, s in zip(xs, staggered) if not s]
        lows = [lower_x(sx) for sx in acting]
        before = [guard_score(image, lx) for lx in lows]
        page_guard(context, "BattleTurn", image=image)
        for sx in acting:  # ponytail: one check per batch of portrait taps (0.1 s apart), not a screenshot per tap
            tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        image = lower_skills(context, lows, before)
        after = [guard_score(image, lx) for lx in lows]
        shown = battle.guard_shown(before, after)
        unsure = [i for i, s in enumerate(shown) if s is None]
        if unsure:  # live: the glow on a unit's slot flickers; swap those back and compare once more
            page_guard(context, "BattleTurn", image=image)
            for i in unsure:
                tap(context, acting[i], SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
            image = lower_skills(context, [lows[i] for i in unsure], [after[i] for i in unsure])
            again = battle.guard_shown([after[i] for i in unsure], [guard_score(image, lows[i]) for i in unsure])
            for i, s in zip(unsure, again):
                shown[i] = s
        if None in shown:
            log(f"guard: cannot tell the guard skill of slots {[n for n, s in zip(numbers, shown) if s is None]}")
            return False
        page_guard(context, "BattleTurn", image=image)
        for sx, on in zip(acting, shown):
            if not on:
                tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        chain = battle.guard_chain(xs, staggered)
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
        end_battle()
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

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        settings = current_run(context)["settings"]["run"]
        used = RUN.get("wipes", 0)
        choice = battle.after_wipe(used, settings["wipe_retries"], settings["after_retries"])
        log(f"wipe: {used} of {settings['wipe_retries']} retries used: {choice}")
        if choice == "stop":
            return stop(context, "retries used up")
        for _ in range(3):
            tap_settled(context, *DEFEAT_OPTIONS[choice], timeout=1.2)  # the options are cards: pick one, then Confirm
            if tap_then(context, *DEFEAT_CONFIRM, lambda im: not has(text(context, im, DEFEAT_TEXT), "participating"),
                        timeout=2.5) is not None:
                break
        else:
            return stuck(f"the DEFEAT dialog did not take {choice}")
        end_battle()
        if choice == "retry":
            RUN["wipes"] = used + 1
        else:
            RUN["forfeit"] = "wipe retries used up"  # Accept results lands on the map; RouteMap forfeits from there
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
        def answered(im):
            return has(text(context, im, roi), want) == shown

        for _ in range(3):
            # the panel and the dialog take the next tap once they stop moving
            if (tap_shown if shown else tap_then)(context, *xy, answered, timeout=2) is not None:
                break
        else:
            return stuck(f"forfeit: {want!r} did not {'show' if shown else 'go'}")
    # The map can stay up a moment after Quit; RouteMap, back on it with no forfeit flag, would pick a node.
    until(context, lambda im: not Shop.on_map(context, im), timeout=2)
    RUN["forfeited"] = RUN.pop("forfeit")  # why, for the forfeits in a row Settle counts
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
EVENT_CARD = (940, 195)  # a check's card at the right: alone, it waits for this tap to open its prompt (card_alone)
EVENT_TEXT_TAPS = 30
# A text tap every EVENT_TAP_EVERY s, the lit button's pixels looked at after each, the page's text only every
# EVENT_READ_EVERY taps: live 2026-10-20, a screenshot and 3 OCRs after each tap made it one every 0.3-1.1 s whatever
# the wait, and the text kept up at 0.15 s (no tap lost; the user's own taps 0.15 s).
EVENT_TAP_EVERY, EVENT_READ_EVERY = 0.15, 3
EVENT_TAKE = 1.5  # s a tap on an event page has to show
EVENT_LABELS = {"skip", "proceed", "continue", "commence"}  # the Event node's expected, compact()ed
EVENT_BUTTON_LABEL = [1040, 612, 190, 66]  # the Event node's roi; on most maps the bottom bar's lever reads there (#511)
# s the map an event ends on holds still before Event hands back: GET! windows come over it, and close on the corner taps
# (#309). The 2026-10-23 window recording, 28 event ends (#511): the map held still at most 0.23 s before a window came;
# the last map stopped moving 0-0.27 s after it showed.
EVENT_MAP_REST = 0.4
EVENT_LIMIT = 180  # s one event may take before recovery L1 (AALC allows 300); a boss quiz of several rounds stays well under
EVENT_ODDS_WAIT = 2.0  # s after a check's prompt first shows that no odds read hands back to MirrorHub, not a sinner (#380); live: the odds came 1.8 s after
EVENT_GAP = 30  # s between two Event calls after which the next call is another event
EVENT_LEAST = 0.5 # s after a tap before the screen counts as moved: a fade's first frames are the same page
CHOICE_X = 925  # the option list's middle
CHOICE_STEP = 150  # px per drag of a list that scrolls: about a card (130-150 px), so none is skipped
CHOICE_SCROLLS = 6  # drags at most to an end of the list


def data(name):
    return yaml.safe_load((data_dir() / name).read_text(encoding="utf-8")) or {}


@functools.cache
def event_table():
    """data/event_table.json's events (spec 03 section 10, #93), read once."""
    return json.loads((data_dir() / "event_table.json").read_text(encoding="utf-8"))["events"]


def red_button(image):
    b, g, r = image[640:650, 1080:1180].reshape(-1, 3).mean(0)
    return r > 150 and r - b > 70


def card_alone(image):
    """A check's card at the right with nothing under it (live 2026-10-28, J1, tests/screens/LuxEventCard.png): a
    Luxcavation battle's event shows it after SKIP, SKIP grey, and goes on only once the card is tapped. Its lit frame's
    bottom strip over a black panel; under the prompt or a check's result the panel is lit."""
    b, g, r = image[230:240, 760:1120].reshape(-1, 3).mean(0)
    return r > 90 and g > 75 and image[290:300, 700:1180].mean() < 10


@AgentServer.custom_action("Event")
class Event(CustomAction):
    """One step on an event page: press the lit button, open a check's card, pick a checker or an option, else advance
    the text (spec 03 section 10). The mirror's, and a Luxcavation battle's (ExpText, J1)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # One event's clock: a call more than EVENT_GAP s after the last starts the next event's (#92).
        now = time.monotonic()
        event = RUN.get("event")
        if event is None or now - event["last"] > EVENT_GAP:
            event = RUN["event"] = {"since": now, "last": now, "checked": set()}
        event["last"] = now
        if now - event["since"] > EVENT_LIMIT:
            RUN.pop("event")
            return stuck(f"one event went on over {EVENT_LIMIT} s")
        image = still(context)
        if image is None:
            log("event: the page did not hold still; MirrorHub looks again")
            return True
        tried = RUN.setdefault("event_tried", set())  # this question's options a tap did nothing on
        checked = event["checked"]  # portraits a tap did nothing on in this check
        if red_button(image):
            Event.advance(context, image, pressed_at=Event.press(context))
        elif card_alone(image):
            tap(context, *EVENT_CARD, wait=0)
            Event.settle(context, image)
        elif has(text(context, image, CHECK_PROMPT), "Choose a character"):
            # One read per portrait: read as a row, neighbouring captions run together ("HighVery Low").
            captions = [(text(context, image, [x - 38, 605, 76, 24], only_rec=True), x) for x in EVENT_PORTRAIT_X]
            # The odds are drawn after the prompt (#380): in the first EVENT_ODDS_WAIT s with none read, no blind first
            # sinner; past it a check that never draws them goes on sinner by sinner (#92).
            if all(rewards.odds_rank(t) is None for t, _ in captions) and now - event.setdefault("prompt_at", now) < EVENT_ODDS_WAIT:
                log("event check: no odds read yet; MirrorHub looks again")
                return True
            i = rewards.pick_checker(captions, checked, lowest=event.get("lowest", False))
            if i is None:  # all the odds read were tried: the next sinner not tried yet, round again when all are
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
            event.pop("prompt_at", None)
            run = RUN if "lux" in RUN else current_run(context)  # a Luxcavation battle's (J1): its team, no Mirror run plan
            story = [t for t, _ in sorted(ocr(context, image, EVENT_STORY), key=lambda r: (r[1][1], r[1][0]))]
            scrolls = rewards.choice_scrollbar(image) or any(None in c for c in rewards.choice_cards(image))
            options, image = self.read_choices(context, image, scrolls)
            if not options:
                return True
            overrides = data("events.yaml") | {o["question"]: o["option"] for o in run.get("settings", {}).get("event_overrides", [])}
            question = next(filter(None, (run_start.match_name(t, list(overrides)) for t in story + [" ".join(story)])), None) if overrides else None
            known = rewards.match_event(" ".join(story), event_table())
            # Grey options (taken in an earlier round of the same questions) and ones a tap did nothing on are closed.
            closed = {k for k, (t, is_open, _) in enumerate(options) if t in tried or not is_open}
            i, lowest = rewards.choice_plan([t for t, _, _ in options], run["team"]["keyword"], overrides.get(question), closed, known,
                                            want_of(run))
            shown = " | ".join(("(closed) " if k in closed else "") + t for k, (t, _, _) in enumerate(options))
            if i is None:
                log(f"event: {shown}: all closed, scroll for more")
                scroll(context, CHOICE_X, 420, 0, -CHOICE_STEP)  # in case the list scrolls with no sign of it
                return True
            log(f"event: {shown}: take {options[i][0]!r}" + (f" (override {question!r})" if question else "")
                + ("" if known else " (not in the event table: hint rules)") + (" (a wanted gift only a failed check gives: lowest odds)" if lowest else ""))
            y, image = self.into_view(context, image, options, i) if scrolls else (options[i][2], image)
            if y is None:
                log(f"event: {options[i][0]!r} not found again in the list")
                return True
            event["lowest"] = lowest  # for this option's check; the next option taken sets its own
            tap(context, CHOICE_X, y, wait=0)
            if until(context, lambda im: not Event.panel_same(image, im), timeout=EVENT_TAKE) is None:
                log(f"event: {options[i][0]!r} did nothing: try another")
                tried.add(options[i][0])
            # A lit card changes the panel before the page goes: MirrorHub reading Choices would take one again.
            elif (after := until(context, gone(context, {"roi": CHOICES_HEADER, "expected": "Choices"}, image), timeout=EVENT_TAKE)) is None:
                log(f"event: Choices still up {EVENT_TAKE} s after taking {options[i][0]!r}")
            else:
                Event.advance(context, after)
        else:
            tried.clear()
            Event.advance(context, image)
        return True

    @staticmethod
    def press(context):
        """Tap the lit button, and return when (time.monotonic()): the page it leads to starts its question's and its
        check's tries over."""
        RUN.get("event_tried", set()).clear()
        if event := RUN.get("event"):
            event["checked"].clear()
            event.pop("prompt_at", None)
        tap(context, *EVENT_BUTTON, wait=0)
        return time.monotonic()

    @staticmethod
    def advance(context, image, pressed_at=None):
        """Text running on (the button grey, or a press of it lit fading out): taps on a dead corner show it line by
        line, and a button that lights is pressed; keep on until there is something else to act on, for MirrorHub's
        next look (#557: handed back, a lit button waited 0.6-1.2 s for it).

        A Choices page or a check prompt shows up to EVENT_READ_EVERY - 1 taps late: a tap on the dead corner picks nothing.
        pressed_at: time.monotonic() of a tap on the lit button just now, image the screen it was tapped on (#188:
        MirrorHub's look after it paused the taps 1.6-5.3 s). The button stays lit while the press fades out, its
        label read once a screen that has not moved since the last (1 OCR, besides the page check every
        EVENT_READ_EVERY taps); the first screen without it is read before the next tap (3 OCRs). Lit with another
        label (SKIP, then Continue), it is the next button; lit EVENT_TAKE s on, the press was lost.
        Only two labels read whole tell another button: one read empty or in part while it fades ("Contnue") is not,
        as MirrorHub's Event node would still match the fading button and press it twice.
        A next button is pressed on the first screen that has not moved since the last (a press mid-fade is lost, #273),
        its label read whole, else MirrorHub presses it. A popup over it (CONNECTING after a taken option) is waited
        out as page_guard waits, before MirrorHub would answer it.
        On the map the event ends on, the taps go on until the screen a look saw it on has not changed for
        EVENT_MAP_REST s (#511).
        """
        last, pressed_label = 0.0, None  # None: not in a press's fade (any more)
        if pressed_at is not None:
            last, pressed_label = pressed_at, compact(text(context, image, EVENT_BUTTON_LABEL))
        shot_at = still_since = time.monotonic()
        thumb, map_seen_at = recovery.thumb(image), None
        for n in range(1, EVENT_TEXT_TAPS + 1):
            time.sleep(max(0.0, last + EVENT_TAP_EVERY - time.monotonic()))
            last = time.monotonic()
            if (n - 1) % EVENT_READ_EVERY == 0:  # on the last read's screenshot (#118, ADR 0007): an OCR a tap would undo the 0.15 s
                try:
                    page_guard(context, "Event", image=image)
                except PageEnded:
                    map_seen_at = shot_at
            if map_seen_at is not None and still_since <= map_seen_at and shot_at - still_since >= EVENT_MAP_REST:
                raise PageEnded("Event")
            tap(context, *EVENT_NEUTRAL, wait=0)
            image, shot_at = screen(context), time.monotonic()
            before, thumb = thumb, recovery.thumb(image)
            if moved := not recovery.same_screen(before, thumb):
                still_since = shot_at
            if red_button(image):
                if pressed_label is not None and time.monotonic() - pressed_at >= EVENT_TAKE:
                    break
                if moved:
                    continue
                label = compact(text(context, image, EVENT_BUTTON_LABEL))
                if pressed_label is not None and not (pressed_label in EVENT_LABELS and label in EVENT_LABELS and label != pressed_label):
                    continue
                if label not in EVENT_LABELS:
                    break
                if on_page(context, image, *POPUPS):
                    image = page_guard(context, "Event")
                    thumb = recovery.thumb(image)
                    continue
                pressed_at = last = Event.press(context)
                pressed_label = label
                continue
            read = n % EVENT_READ_EVERY == 0 or pressed_label is not None
            pressed_label = None
            if card_alone(image):
                break
            if not read:
                continue
            # The label roi reads empty off the event page, on a map too (MapCostFloor3.png): the map waits for the guard.
            if not text(context, image, EVENT_BUTTON_LABEL) and not on_page(context, image, *ENDS_ON["Event"]):
                break
            if any(has(text(context, image, roi), k) for k, roi in (("Choices", CHOICES_HEADER), ("Choose a character", CHECK_PROMPT))):
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
                if not run_start.match_name(t, [o[0] for o in options], margin=0):
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
                if name := run_start.match_name(t, texts, margin=0):
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
REWARD_CARDS = [130, 190, 1020, 280]  # the cards, for still(): they slide in over 0.27-0.97 s (#334)
CARD_TEXT = [130, 340, 1020, 120]
SELECTABLE = [880, 115, 170, 40]
CARD_CONFIRM = (808, 528)
CARD_ROUNDS = 12  # a look is a round: per tap up to CARD_REREADS rereads and the tap (a card of 3 that never reads: 9), then Confirm
CARD_REREADS = 2  # a card that reads as nothing is looked at again this often per tap before it is taken as it reads


@AgentServer.custom_action("RewardCard")
class RewardCard(CustomAction):
    """Take reward cards in the team's order until Selectable n/m is full, then Confirm; never Cancel (spec 03 section 11).

    #334: each look waits for the cards to stop moving, which the game ignores taps during. A card counts as taken
    when Selectable's count went up; a tap that did not raise it is made again on the same card.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        order = current_run(context)["team"]["reward_cards"]
        taken, rereads = set(), 0
        for _ in range(CARD_ROUNDS):
            image = page_guard(context, "RewardCard", image=still(context, roi=REWARD_CARDS, runs=2))
            m = re.search(r"(\d)\s*/\s*(\d)", text(context, image, SELECTABLE))
            if m and m[1] == m[2]:
                tap(context, *CARD_CONFIRM, wait=0)
                get = shows(context, GET_TITLE, "GET")  # a gift's popup leaves the title up: MirrorHub hands it to GiftGet (#377)
                until(context, lambda im: not has(text(context, im, REWARD_TITLE), "Encounter Reward") or get(im))
                return True
            if not m:  # no count to tell a tap by: the page is not up
                continue
            cards = columns(ocr(context, image, CARD_TEXT))
            if not cards or len(taken) == len(cards):
                time.sleep(1)  # kept (#58): the cards still slide in; the next round's still() reads them at rest
                continue
            types = [rewards.card_type(" ".join(lines)) for _, lines in cards]
            if None in types and rereads < CARD_REREADS:  # still sliding in, or misread: not ready
                rereads += 1
                continue
            i = rewards.pick_card(types, order, taken)
            log(f"reward cards: {', '.join(str(t) for t in types)}: take {types[i] or ' '.join(cards[i][1])!r}")
            tap(context, cards[i][0], 300, wait=0)
            before = int(m[1])

            def picked(im):  # Selectable's count went up: not a misread digit, not a tap that dropped the card again
                n = re.search(r"(\d)\s*/\s*\d", text(context, im, SELECTABLE))
                return n is not None and int(n[1]) > before
            if until(context, picked, timeout=1.5) is not None:
                taken.add(i)
                rereads = 0
        return stuck("reward card page did not fill Selectable")


GIFT_CARDS = [100, 150, 1080, 410]  # 1-4 cards; on the boss page the Mounting Trials half below each
GIFT_COUNT = [1060, 555, 160, 50]  # "Select 0/2"; "Select" alone on a page that takes one card (#494)
GIFT_SELECT = (1138, 579)
REFUSE_GIFT = [870, 560, 160, 40]
# A boss card's trial half, around the card's centre x: the Enemy Level Up badge's "+N" at its left (from x - 103), the
# trial's icon, its name, then its effect line, wrapped to two or three lines (tests/screens/BossGiftTrials*.png, #381).
TRIAL_HALF = (-125, 438, 250, 105)  # x from the centre, y, w, h
# Measured on the 10 boss cards of tests/screens (16 with two more 2026-10-28 frames, not committed):
TRIAL_NAME_FOOT = 470  # a name's box starts above it (y 444-451), an effect line's below (475+)
TRIAL_BADGE_X = -60  # a "+N" box starts left of the centre by more (-103), the name's by at most 24


def gift_count(context, image=None):
    return gift_search.select_count(text(context, screen(context) if image is None else image, GIFT_COUNT))


def gift_tier(image, x):
    """The tier (1-5) of the gift card centred at x, from the yellow numeral over its icon (shop.numeral), or None (#381).

    The numeral is 17 px tall, its top at y 212 on a boss page (220 on a fight's), left of the centre, I-III centred
    at x - 13 to x - 9; the icon's own yellow sits right of the window. Its strokes are counted as shop.tier counts a
    cell's: 2 px under the top and 3 over the foot. Every gift card of tests/screens (11 on 4 captures, tiers I-II)
    reads its gift data's tier (test_trial_screens.py), as do 6 more on two 2026-10-28 frames (a III among them); a IV or
    V is on no capture yet.
    """
    mask = shop.yellow(image[203:250, x - 26:x + 2])
    rows = np.flatnonzero(mask.any(axis=1))
    return shop.numeral(mask, rows[0] + 2, rows[0] + 14) if len(rows) >= 8 else None


def trial_card(context, image, x):
    """(Enemy Level Up N or None, the trial name's OCR, its effect line's OCR) of the boss gift card centred at x (#381).

    One OCR over the card's trial half (TRIAL_HALF): the whole page's misses badges (none of BossGiftTrials.png's 3);
    the half's read every badge, name and effect line of the 10 boss cards in tests/screens (test_trial_screens.py) and
    of 6 more on two 2026-10-28 frames. A wrapped effect line joins top to bottom.
    The icon reads as one or two stray letters ("X", "0x"): no name is that short.
    """
    dx, y, w, h = TRIAL_HALF
    level, name, line = None, [], []
    for t, (bx, by, _, _) in sorted(ocr(context, image, [x + dx, y, w, h]), key=lambda r: (r[1][1], r[1][0])):
        badge = re.fullmatch(r"\+\s*(\d)", t.strip())
        if badge and bx < x + TRIAL_BADGE_X:
            level = int(badge[1])
        elif by >= TRIAL_NAME_FOOT:
            line.append(t)
        elif len(compact(t)) >= 3 and not has(t, "Mounting"):
            name.append(t)
    return level, " ".join(name), " ".join(line)


def gift_cards(context, image):
    """(card centres x, each card's [(y, OCR line)], whether Mounting Trials hang under the cards) of a gift choice page (#418).

    The "Acquire E.G.O Gift" tab sits on each card's top-right corner, 114 px right of its centre; no tab, no centres.
    """
    results = ocr(context, image, GIFT_CARDS)
    centres = sorted(x + w - 114 for t, (x, y, w, h) in results if has(t, "Acquire"))
    lines = [[] for _ in centres]
    for t, (x, y, w, h) in results:
        i = min(range(len(centres)), key=lambda i: abs(centres[i] - x - w // 2), default=None)
        if i is not None and abs(centres[i] - x - w // 2) < 130 and not has(t, "Acquire"):
            lines[i].append((y, t))
    return centres, lines, any(has(t, "Mounting") for t, _ in results)


@AgentServer.custom_action("PickGift")
class PickGift(CustomAction):
    """Gift choice after a fight, an event or a boss: best cards until Select n/m is full, then Select (spec 03 section 12).

    Each card scores by its category (rewards.gift_score): pack-want 9 > want 6 > material 5.5 > main keyword 3 > other 2 >
    owned 0 (#416). When Mounting Trials hang under them (after a boss), each scores gift (main and other with its tier) -
    (trial + level x Enemy Level Up N), the trial told from the pool of the floor just cleared
    (data/trials.yaml, #381). Refuse Gift is never pressed: it hands out random trials.
    A gift the team avoids (#90) comes last: taken only when nothing else fills the count.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        centres, lines, trials = gift_cards(context, image)
        if not centres:
            return True  # page fading in or out: let MirrorHub look again
        table = data("trials.yaml")
        # The pool of the floor just cleared; every trial when the floor is unknown (the agent restarted mid-run).
        pool = rewards.trials_of(table, run.get("floor")) or rewards.trials_of(table, None)
        overrides = {o["trial"]: o["risk"] for o in run["settings"]["trial_risk_overrides"]}
        scores = rewards.scores(pool, table["model"], run.get("trial_coins", 0), overrides)
        avoid = [g["name"] for g in avoided_gifts(run["team"])]
        wanting = want_of(run)
        cards, names = [], []
        for x, card in zip(centres, lines):
            gift = " ".join(t for y, t in card if y < 410)
            owned = any(compact(t) == "owned" for _, t in card)
            kind = rewards.gift_kind(gift, run["team"]["keyword"], owned, avoid)
            gift_id = rewards.card_gift(card, GIFT_IDS)
            label = GIFT_NAMES[gift_id] if gift_id else repr(rewards.card_title(card))
            want = wanting(gift_id) if gift_id else None
            name, tier, cost, trial_note = None, None, None, None
            if trials:  # the tier counts on the boss page only (#381); a fight's page stays main > other > owned
                tier = gift_tier(image, x)
                level, read, line = trial_card(context, image, x)
                name, how = rewards.read_trial(read, line, pool)
                score = scores[name] if name else max(scores.values())  # unread: the pool's worst
                cost = rewards.burden(score, level, table["model"])
                trial_note = f"{name or '?'} +{'?' if level is None else level} score {score:g}"
                if not name or compact(read) != compact(name):  # the name read is not the trial's: what was, for the log
                    trial_note += f" ({f'by its {how}' if how else 'unread: the pool worst'}, read {read!r} / {line!r})"
            cards.append(rewards.Card(kind, tier, cost, label, gift_id, trial_note, rewards.category(kind, want)))
            names.append(name)
        ranked = rewards.rank_gifts(cards)
        log("gifts: " + ", ".join(rewards.card_line(c) for c in cards) + f": order {ranked}")

        def pick(i):
            before = gift_count(context, page_guard(context, "GiftChoice"))
            tap(context, centres[i], 300, wait=0)
            until(context, lambda im: gift_count(context, im) != before, timeout=1.5)

        taken = rewards.pick_gifts(ranked, lambda: text(context, screen(context), GIFT_COUNT), pick, trials)
        for _ in range(3):
            page_guard(context, "GiftChoice")
            tap(context, *GIFT_SELECT, wait=0)
            if until(context, lambda im: not has(text(context, im, REFUSE_GIFT), "Refuse")) is not None:
                # The run's Coin Power units so far, for the budget of pools past early_pools (spec 03 section 12)
                RUN["owned"] = RUN.get("owned", []) + [cards[i].gift_id for i in taken if cards[i].gift_id]  # held from now on
                coins = sum(table["trials"][names[i]]["effects"].get("coin", 0) for i in taken if names[i])
                if coins:
                    RUN["trial_coins"] = run.get("trial_coins", 0) + coins
                    log(f"trials: {RUN['trial_coins']} Coin Power units this run")
                return True
        return stuck("Select did not take the gifts")


# Shop (spec 03 section 13). The Super Shop has the same layout with up to 10 offers.
SHOP_COST = [540, 112, 110, 45]
REFRESH = {"normal": ((997, 122), [960, 140, 80, 30]), "keyword": ((1140, 122), [1100, 140, 80, 30])}  # button, fee
OFFER_GRID = [545, 215, 620, 300]
DIALOG_TITLE = [360, 80, 560, 115]  # Purchase E.G.O Gifts, Shop - Keyword Refresh, Fuse / Sell E.G.O Gift
PURCHASE_PREVIEW = [780, 145, 140, 40]  # "2864 > 2612": the Cost before and after
PURCHASE, PURCHASE_CANCEL = (747, 482), (525, 482)
KEYWORD_LABELS = [270, 300, 740, 200]  # the 10 keyword cards of both keyword dialogs
KEYWORD_REFRESH, KEYWORD_CANCEL = (785, 560), (495, 560)
GET_TITLE, GET_CONFIRM = [520, 160, 240, 40], (640, 532)
GET_NAME = [320, 405, 180, 80]  # the red plate under the gift's icon
PAGE_CLOSE, PAGE_OK = (490, 585), (788, 585)  # Close, and Fuse / Sell, on the fuse and sell pages
SHOP_BUTTONS = {"fuse": (295, 390), "sell": (395, 390), "heal": (197, 474)}
FUSE_CENTRE, FUSE_KEYWORD_OK = (365, 340), (788, 566)
FUSE_DIALOG_CONFIRM = (788, 583)  # "Fuse the selected E.G.O Gifts?"'s Confirm
# Grid cells by their centre (live 2026-10-16/18). Each cell's tier numerals sit top left, its keyword badge
# bottom right (none on a keywordless gift). The owned grids' third row shows half, its badges cut off: they scroll (#205).
# page: (the first cell's centre with the grid at its top, the step to the next column and row, the px under a centre
# that must show for the cell to be read: its badge, on the sell page its price). Rows 92 and 107 px apart on captures;
# a sell price's digits 38-53 px under the centre, and a sell grid of 3 rows scrolls 31 px to show its last whole (live
# 2026-10-21, #205).
OWNED_GRID = {"fuse": ((678, 294), (96, 92), 40), "sell": ((683, 258), (92, 107), 52)}
FUSE_CELLS, SELL_CELLS = ([(x + dx * c, y + dy * r) for r in range(3) for c in range(5)]
                          for (x, y), (dx, dy), _ in OWNED_GRID.values())
OFFER_CELLS = [(624 + 154 * c, y) for y in (265, 418) for c in range(4)]  # a shop at rest; the price line is 52 px under
# A Super Shop's grid scrolls to show its third row (live 2026-10-15, SuperShop.png and its scrolled capture): by 150 px, the
# second row where the first was. A drag from between the first two columns, 250 px, goes to either end.
OFFER_DRAG_X, OFFER_DRAG_PX = 701, 250
OFFER_ABOVE, OFFER_UNDER = 90, 25  # px a price line has its icon's top over it and its name's foot under it: what must show in the grid's box


def offer_whole(y):
    """Whether the offer whose price line is at y shows whole in OFFER_GRID's box (#341)."""
    return OFFER_GRID[1] + OFFER_ABOVE <= y <= OFFER_GRID[1] + OFFER_GRID[3] - OFFER_UNDER
# The fuse page's list: sections over the owned gifts (a fixed recipe's Fusion Available, #103) push them down. Their
# "E.G.O Gifts Owned" label's centre sits 66 px over the first owned row's (live: 228 and 294).
FUSE_LIST, OWNED_LABEL = [630, 195, 480, 305], 66
GRID_DRAG_X = 728  # a drag of the owned grid starts between its first two columns
GRID_STROKE = 215  # px a drag stroke moves the owned grid at most: it starts and ends inside the grid
GRID_SCROLLS = 20  # drags at most to the owned grid's end: 2 rows each, fewer when the game takes less of one
GRID_MARGIN = 6  # px a drag stops short of putting a row at the first row's place: a few px too far does not hide it
GRID_SLIP = 12  # px a drag may move the grid past the finger, either way, and still be measured
# A cell's centre at its tap against its read (centre, matched): the same gift 0-3 px off, the grid moved by a fraction
# of a px (resampled to 720p), differs by 9.9 at most, two gifts by 15.2 at least (Faint and Dark Vestige's jars), 24.6
# for 95 in 100; tests/shop's 5 fuse and sell captures (test_shop_scroll).
GRID_SAME = 12.5
# page: (its icon size over the GiftSearch template's, the grid's lower edge on screen)
CELL_PAGES = {"fuse": (1.1, 493), "sell": (1.1, 495), "offer": (0.8, 530)}
BADGES = tuple(k for k in GIFT_KEYWORDS if k != "Keywordless")
# On scaled cells (CCOEFF): its own badge 0.54-0.99, another keyword's up to 0.60 (the cell's best wins), a keywordless
# cell's best 0.41; 160 cells of 60 live captures.
BADGE_MIN = 0.5
GIFTS = gift_cells.load()  # every gift a cell may show (#297)
GIFT_NAMES = {e["id"]: e["en"] for e in GIFTS}
FUSION_IDS = {g["id"] for g in gift_tables()[1]}
GIFT_TIERS = {e["id"]: e["tier"] for e in GIFTS}
GIFT_IDS = {e["en"]: e["id"] for e in GIFTS}  # an English name plate's gift (#329)
CELL_ICON_ROI = 70  # px square around a cell's centre on the scaled grid where its icon is looked for: the biggest icon (54 px) +-8
# An EX gift's tier in the game data (TIER_5 beside TIER_EX: 9799 A Certain Philosophy, 9800 Wealth); its cell shows "EX"
# where the numerals go, so a cell with no numeral read and that "EX" (#449) or the Unselectable tag (#378) is matched
# against that tier's gifts, and a fusion whose GET! popup shows it made that tier
EX_TIER = 5
FUSE_CONFIRM = [300, 150, 680, 380]  # "Selected E.G.O Gifts 3/5" over "Fuse the selected E.G.O Gifts?"
FUSE_COUNT = r"(\d)\s*/\s*\d"  # its "3/5": the materials in
FUSE_NEUTRAL = (815, 160)  # above the owned grid, between Recipes and Fusion Guide: closes a tooltip, selects nothing
FORECAST_CHANCE = [428, 455, 62, 28]  # "90%" at the Forecasts row's right: the keyword's chance (60 / 90 / 99, 100 on a recipe)
FUSE_TRIES = 3  # groups the fuse page's forecast may turn down between two fusions before the page is closed (#285)
FUSIONS_PER_PAGE = 10  # fusions one fuse page makes before it is closed (#378): Shop.run's next round opens it again
TOOLTIP_CLOSE = {"fuse": FUSE_NEUTRAL}  # per page: where a tap closes a gift's tooltip, which hides the cells under it (#331)
SELL_COST = [960, 80, 160, 45]
SELL_GRID = [630, 210, 480, 290]  # the sell page's gifts with their prices under them
HEAL_TITLE, HEAL_COST = [130, 30, 220, 45], [1100, 90, 110, 50]
HEAL_OPTIONS = {"full": (1020, 330), "revive": (1020, 455)}
SHOP_PORTRAIT_X = [98 + 77 * i for i in range(12)]  # the shop's sinner bar (step 77, not the event bar's)
BOTTOM_RIGHT = (1130, 647)  # Leave on the shop; Return, Select or Leave on the heal pages
BOTTOM_LABEL = [1040, 615, 180, 65]  # its label (the Shop node's ShopLeave roi)
OUTSIDE = (40, 400)  # left of every shop dialog, on nothing
LEAVE_DIALOG, LEAVE_CONFIRM, LEAVE_CANCEL = [440, 320, 400, 45], (765, 493), (515, 493)
# The Replace <sinner>'s Skill dialog (#455; spec 02 「技能替換對話框」), measured on tests/screens/ShopReplaceSkill*.png. Both
# layers (the three options, then "Spend N Cost to replace this Skill?") keep the counts, Cancel and Confirm in place.
REPLACE_TITLE = [200, 118, 380, 40]  # "Replace Don Quixote's Skill" x 213-568, "Replace Gregor's Skill" 247-534, y 124-151
REPLACE_OWNED = [600, 102, 250, 52]  # "Skills Owned" over "SKILL 1x3 SKILL 2x2 SKILL 3x1" (x 617-833, y 134-149)
REPLACE_COST = [1012, 118, 100, 42]  # the Cost, digits from x 1020 (the coin ends at 1011, Keyword Refresh's dim label from 1129)
REPLACE_PREVIEW = [980, 115, 130, 45]  # 2nd layer: "350 ▸ 305", the Cost before and after (x 985-1098)
REPLACE_PRICES = {"s1_s2": [408, 206, 51, 20], "s2_s3": [734, 206, 52, 20], "s1_s3": [1059, 206, 52, 20]}  # 45, 75, 120
REPLACE_FRAMES = {"s1_s2": (156, 196, 311, 310), "s2_s3": (482, 196, 311, 310), "s1_s3": (808, 196, 311, 310)}
REPLACE_OPTIONS = {"s1_s2": (312, 340), "s2_s3": (638, 340), "s1_s3": (963, 340)}  # the frames' centres (tapped live, #453)
REPLACE_CANCEL, REPLACE_CONFIRM = (507, 542), (790, 542)
REPLACE_ASK = [420, 486, 440, 28]  # 2nd layer only: "Spend 45 Cost to replace this Skill?" (y 493-508)
# What DIALOG_TITLE reads on both layers, the counts line lying inside it: to_main's tell, at no extra OCR.
REPLACE_MARK = ("Skills Owned", "SKILL1x", "SKILL2x")
REPLACE_SETTLE = 4  # s the final Confirm waits for the main page's new Cost: CONNECTING ~0.3 s, the page ~0.6 s later (#453)
# ID Skill Search (#456; spec 02 「ID Skill Search」), measured on tests/screens/ShopIdSkillSearch*.png. Its slot opens the
# select mode; a portrait there opens the Replace dialog above, at its own prices; its Return is BOTTOM_RIGHT.
SELECT_TITLE = [430, 15, 420, 35]  # select mode: "Select a Sinner for Skill Replacement." (also the Shop node's ShopSelectSinner)
PAY_SWITCH = (957, 140)  # the dialog's double arrow left of its Cost: Cost <-> the owned starlight (the Cost box shows it)


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
        time.sleep(0.5)  # kept (#58): an OCR retry on a fresh screenshot, the Cost still fading in
    return None


# A portrait's mean saturation on the shop's main page: the dead 24-51 (over the old 30; by eye, the blue SP badge on a grey
# portrait), the living 83-158 (12 main-page captures of tests/screens, 144 portraits; test_shop_skill). Under a dialog or the
# fuse page the bar is shaded (62-92), and it is never read there.
BAR_GREY = 65


def bar_dead(image):
    """The sinners grey on the shop's sinner bar (SHOP_PORTRAIT_X, the game's order) of the main page: the dead, whose
    portrait takes no tap in ID Skill Search's select mode (#456 capture)."""
    return {sinner for x, sinner in zip(SHOP_PORTRAIT_X, battle.SINNERS)
            if saturation(image[630:680, x - 25:x + 25]).mean() < BAR_GREY}


def note_skills(sinner, owned):
    """RUN["skills"][sinner] = the counts (c1, c2, c3) read or made this run, or forgets them (owned None): the only writer
    (#264: a sinner read at the target is not opened again this run).

    It leaves with RUN (the claim, the give-up, a new run, a task change: the Mirror Dungeon left) and survives floors and
    hand-backs. A cache of the screen: the next dialog reads the counts again and overwrites it. A remembered deck never
    runs ahead of the game's (#455): an outcome not known is forgotten, which costs one more open at a later shop.
    """
    skills = RUN.setdefault("skills", {})
    if owned is None:
        skills.pop(sinner, None)
    else:
        skills[sinner] = list(owned)


def cell_state(cell, gift_list, owned=()):
    """What the list makes of the gift a cell shows, for the log (#299): "want", "keep", "locked" (a drop gift a wanted
    fusion not in `owned` needs), "drop", or "unknown" (the icon was not told)."""
    if cell["id"] is None:
        return "unknown"
    own = state(gift_list, cell["id"])
    return "locked" if own == "drop" and effective(gift_list, cell["id"], run_packs(), owned=owned) != "drop" else own


def note_owned(team, visit, cells):
    """The ids of the owned gifts `cells` show (an unknown one left out), kept as visit["owned"] for the visit's purchases
    (gifts.purchases). Each wanted fusion among them is logged once a visit: it locks and buys nothing more (the user,
    2026-10-30)."""
    visit["owned"] = owned = [c["id"] for c in cells if c["id"] is not None]
    visit.pop("bought", None)  # the page shows them
    told = visit.setdefault("owned_fusions", [])
    for i in owned:
        if i in FUSION_IDS and i not in told and state(team["list"], i) == "want":
            told.append(i)
            log(f"shop: wanted fusion {i} {GIFT_NAMES.get(i)} is owned: its materials are no longer bought or kept")
    return owned


def owned_now(visit):
    """A copy of the gifts the visit counts as owned (gifts.purchases): visit["owned"] once a page was read (note_owned), else
    only what this visit bought (visit["bought"]): an owned gift not read counts as none (spec 03), a gift bought counts."""
    return list(visit["owned"] if visit.get("owned") is not None else visit.get("bought", ()))


def leave_shop():
    """The shop visit RUN["shop"] is over, left by its Leave or without it (#118): the run holds what the visit counted as owned
    (owned_now), RUN["owned"], for the gift pages and events after it. A visit that read no owned page adds only what it bought."""
    visit = RUN.pop("shop", None)
    if visit and visit.get("owned") is not None:
        RUN["owned"] = owned_now(visit)
    elif visit:
        RUN["owned"] = RUN.get("owned", []) + owned_now(visit)


def want_of(run):
    """`want(gift_id)` -> "pack-want" | "want" | "material" | None for the team's list (gifts.want_kind), the run's packs and the
    gifts the run holds (RUN["owned"]: the last shop visit's, plus the cards taken on gift pages; the start gifts and the events'
    are not told). Always None for a team with no list. A wanted gift held is no want (#416: owned 0), a material is still counted."""
    gift_list, held = run["team"].get("list"), RUN.get("owned", [])

    def want(gift_id):
        kind = want_kind(gift_list, gift_id, run_packs(), held) if gift_list else None
        return None if kind in ("pack-want", "want") and gift_id in held else kind
    return want


def owned_change(visit, gone=(), got=()):
    """Take `gone` out of the gifts the visit counts as owned (owned_now) and add `got`, in place: a sale, a fusion, a
    purchase. Unread, `got` goes to visit["bought"] and `gone` is not looked for: the sale and the fusions read the owned
    gifts first, so only a purchase comes here then."""
    if visit.get("owned") is None:
        visit.setdefault("bought", []).extend(got)
        return
    for i in gone:
        visit["owned"].remove(i)
    visit["owned"].extend(got)


def buy_list(team, visit):
    """gifts.purchases for the team's list, the run's packs, the gifts the visit counts as owned (owned_now) and the floor's
    difficulty as set_difficulty read it (floor_hard; None when it was not read, #626: a HARD run plays NORMAL floors before
    hard_from_floor, so the run's difficulty does not stand in for it)."""
    return purchases(team["list"], run_packs(), owned_now(visit), hard=RUN.get("floor_hard"))


def cell_role(cell, team, page, avoid, owned=()):
    """"material" or "keep": what the shop may do with the owned gift a cell of page ("fuse" or "sell") shows (#299).

    Material only when the gift is known (its id was read, #297) and its effective state in the team's gift list is "drop"
    (not wanted, not kept, and no material of a wanted fusion not in `owned`: gifts.effective; a pack's exclusive fusion locks
    its materials only when the run pulled one of its packs, or run_packs is unknown, #306). A gift whose id is in `avoid` (White Gossypium for a team that does
    not hold it, #90) is material whatever the list says: the team's setting comes before the list's, as on the shelf. A
    vestige is never sold unless the team sells vestiges (sell_vestiges, #161), but still fuses. A cell the fuse page tags
    Unselectable (an EX gift, #378) is kept whatever the list says: the page does not take it in. The sell page has no such
    tag (read_cells): an EX gift there shows no numeral, so its id is unknown and it is kept as any unknown cell (unseen live).
    """
    if cell.get("unselectable"):
        return "keep"
    if cell["id"] in avoid:
        return "material"
    if cell["id"] is None or effective(team["list"], cell["id"], run_packs(), owned=owned) != "drop":
        return "keep"
    if page == "sell" and cell["id"] in vestige_ids() and not team.get("sell_vestiges", False):
        return "keep"
    return "material"


WHITE_GOSSYPIUM = 9020  # its id in data/gift_search.json


def avoided_gifts(team):
    """Gifts the team never takes or buys, and fuses or sells first: White Gossypium unless it allows it (#90)."""
    if team.get("allow_white_gossypium", True):
        return []
    g = next(e for e in gift_tables()[0] if e["id"] == WHITE_GOSSYPIUM)
    return [{"name": g["en"], "keyword": g["keyword"], "tier": g["tier"], "id": g["id"]}]


def template_hits(context, image, template, threshold):
    """[(score, (x, y))]: the centres where template matches on image (TemplateMatch CCOEFF, its green masked)."""
    h, w = image.shape[:2]
    node = {"recognition": "TemplateMatch", "template": template, "threshold": threshold, "method": 5,
            "green_mask": True, "roi": [0, 0, w, h]}
    detail = context.run_recognition("ShopCell", image, {"ShopCell": node})
    return [(r.score, (r.box[0] + r.box[2] / 2, r.box[1] + r.box[3] / 2)) for r in (detail.filtered_results if detail else [])]


def cell_id(context, grid, at, keyword, tier):
    """(the id of the gift whose icon is on the cell centred at `at` of the scaled grid, its score): None when unknown (#297).

    The icons of the gifts of the cell's keyword and tier (gift_cells.candidates) are matched in turn, CCOEFF with its
    green masked, within CELL_ICON_ROI of the centre; the best is the cell's gift when gift_cells.best accepts it. The
    matching stops at an icon of gift_cells.ICON_SURE: another candidate cannot tie it (a cell's lookalikes score 0.66 at most).
    When none of them is accepted, the keyword's other gifts are matched too (gift_cells.of_keyword: the tier numeral may be
    misread, #330), the earlier scores kept for the lead; there is no early stop, the twin of another tier (Dark and Faint
    Vestige) scores as high. A cell with no tier or badge read, or none of whose candidates match, is unknown: shops treat it as a gift to keep.
    """
    cx, cy = round(at[0]), round(at[1])
    h, w = grid.shape[:2]
    x, y = max(0, cx - CELL_ICON_ROI // 2), max(0, cy - CELL_ICON_ROI // 2)
    roi = [x, y, min(CELL_ICON_ROI, w - x), min(CELL_ICON_ROI, h - y)]
    scores = []

    def match_icons(pool, stop_when_sure):
        for e in pool:
            node = {"recognition": "TemplateMatch", "template": e["template"], "threshold": 0.0, "method": 5, "green_mask": True, "roi": roi}
            detail = context.run_recognition("ShopCellIcon", grid, {"ShopCellIcon": node})
            scores.append((e["id"], detail.best_result.score if detail and detail.best_result else 0.0))
            if stop_when_sure and scores[-1][1] >= gift_cells.ICON_SURE:
                break

    match_icons(gift_cells.candidates(GIFTS, keyword, tier), stop_when_sure=True)
    found = gift_cells.best(scores)
    if found is None:  # #330
        tried = {i for i, _ in scores}
        match_icons([e for e in gift_cells.of_keyword(GIFTS, keyword, tier) if e["id"] not in tried], stop_when_sure=False)
        found = gift_cells.best(scores)
    return found, max((s for _, s in scores), default=0.0)


def held(image, x, y, page):
    """Whether the cell of page centred at (x, y) holds a gift: textured (shop.filled), or on the fuse page tagged
    Unselectable (shop.unselectable: a gift drawn dim, flat as an empty cell, #378)."""
    return shop.filled(image, x, y) or (page == "fuse" and shop.unselectable(image, x, y))


def read_cells(context, image, cells, page):
    """The cells holding a gift of a shop grid read off one screenshot (#76, #112): [{"i", "x", "y", "tier", "keyword",
    "id", "score", "unselectable", "ex"}].

    The grid is scaled so gift icons are at their GiftSearch template's size, then each keyword's badge is matched once
    over it. keyword: the cell's best badge, "Keywordless" with none, None when the badge is below the grid's edge. An
    empty cell is flat (live: spread 1-2, a gift 41-84), unless the fuse page tags it Unselectable (held).
    id: the data's id of the gift the cell shows (cell_id), None when unknown, score the best icon's; tier is then that gift's.
    unselectable: the fuse page's tag (#378); ex: on the owned gifts' pages (fuse, sell) no numeral read, the green "EX" there
    instead (shop.ex_mark, #449). With either and no numeral, the cell's candidates are EX_TIER's.
    """
    scale, bottom = CELL_PAGES[page]
    half = shop.CELL_HALF
    tagged = {i for i, (x, y) in enumerate(cells) if page == "fuse" and shop.unselectable(image, x, y)}
    filled = [(i, x, y) for i, (x, y) in enumerate(cells) if i in tagged or shop.filled(image, x, y)]  # held
    if not filled:
        return []
    x0, y0 = min(x for _, x, _ in filled) - half, min(y for _, _, y in filled) - half
    x1, y1 = max(x for _, x, _ in filled) + half, min(bottom, max(y for _, _, y in filled) + half)
    grid = shop.rescale(image[y0:y1, x0:x1], 1 / scale)
    crops = {i: shop.cell_crop(image, x, y, scale) for i, x, y in filled}
    out = [{"i": i, "x": x, "y": y, "tier": shop.tier(crops[i]),
            "keyword": "Keywordless" if y + 40 <= bottom else None, "unselectable": i in tagged,
            "at": ((x - x0) / scale, (y - y0) / scale)} for i, x, y in filled]
    for c in out:
        c["ex"] = c["tier"] is None and page in OWNED_GRID and shop.ex_mark(crops[c["i"]])
    best = {}
    for keyword in BADGES:
        for score, (bx, by) in template_hits(context, grid, f"Shop/Badge{keyword}.png", BADGE_MIN):
            for c in out:  # a badge sits 12-40 px right of and below its cell's centre, on the scaled grid
                cx, cy = c["at"]
                if c["keyword"] and 12 <= bx - cx <= 40 and 12 <= by - cy <= 40 and score > best.get(c["i"], 0):
                    best[c["i"]], c["keyword"] = score, keyword
    for c in out:
        tier = EX_TIER if c["tier"] is None and (c["unselectable"] or c["ex"]) else c["tier"]
        c["id"], c["score"] = cell_id(context, grid, c.pop("at"), c["keyword"], tier)
        if c["id"] is not None:
            c["tier"] = GIFT_TIERS[c["id"]]  # the numeral may be misread (#330): the gift's own tier decides
    return out


def read_plates(context, image, centres):
    """The name plate under each offer cell centred at a (x, y) of centres: [{"text", "id"}], id None when it names no gift (#329).

    One OCR line per plate (only_rec) in the box gift_cells.plate_roi gives, dimmed and Purchased cells included. The box
    is relative to the cell's centre, so a grid dragged to another row reads just the same. On DirectML a line takes about
    31 ms once a det+rec pass has used the OCR instance; a plate-only instance read in 5 ms but cost 150 MB and 31 MB of
    package, so the plates share the default one (#329).
    """
    plates = []
    for x, y in centres:
        t = text(context, image, gift_cells.plate_roi(x, y), only_rec=True)
        plates.append({"text": t, "id": gift_cells.name_id(t, GIFT_IDS)})
    return plates


def offer_cell(slot):
    """The icon centre of an offer read by shop.read_slots: its column's, 52 px over its price line."""
    return min((x for x, _ in OFFER_CELLS[:4]), key=lambda x: abs(x - slot["x"])), slot["y"] - 52


def cell_line(cell, role):
    """One cell read for the log: "2 III Bleed 9042 Smokes and Wires (0.77): keep", an unknown gift "unknown (best 0.38)" (#297),
    a cell the fuse page tags Unselectable "... (0.78) unselectable: keep" (#378), a cell showing the green "EX" for its
    numerals "1 EX Keywordless 9799 A Certain Philosophy (0.78): keep" (#449)."""
    tier = "EX" if cell.get("ex") else "I II III IV V".split()[cell["tier"] - 1] if cell["tier"] else "?"
    tag = " unselectable" if cell.get("unselectable") else ""
    return f"{cell['i']} {tier} {cell['keyword'] or 'badge unread'} {gift_shown(cell)}{tag}: {role}"


def gift_shown(cell):
    """The gift a read cell was taken for, for the log: "9042 Smokes and Wires (0.77)", or "unknown (best 0.38)" (#297)."""
    named = GIFT_NAMES.get(cell["id"])
    if named and cell.get("by_plate"):  # told by its name plate alone (a dimmed cell, #329)
        return f"{cell['id']} {named} (plate)"
    return f"{cell['id']} {named} ({cell['score']:.2f})" if named else f"unknown (best {cell['score']:.2f})"


def close_tooltip(context, page, force=False):
    """A screenshot of page with no gift tooltip over its grid, the page checked (page_guard), #331.

    A tooltip comes up over a cell tapped and hides the cells under it. With one on show (shop.tooltip), or force (a cell
    was just tapped), the page's TOOLTIP_CLOSE spot is tapped and the screen waited on to move and stop. The tap comes
    first and the guard after it (ADR 0007): a tooltip over the fuse page hides Leave, so the page node reads nothing until
    it is closed. With none on show nothing is tapped or waited for (#378: 1.5 s a read, live), unless the guard does not
    find the page on that screenshot: a tooltip shop.tooltip missed may hide Leave, so it is tapped as with one.
    A page without a TOOLTIP_CLOSE spot: as it is.
    """
    image = screen(context)
    if page not in TOOLTIP_CLOSE:
        return page_guard(context, "Shop", image=image)
    if not force and not shop.tooltip(image):
        try:
            return page_guard(context, "Shop", image=image)
        except PageGone:
            pass
    tap_settled(context, *TOOLTIP_CLOSE[page], timeout=1.0)
    return page_guard(context, "Shop")


def read_clear(context, image, spots, page):
    """read_cells of spots on image, the cells that read unknown read again on a screenshot taken after one more tap
    on the page's TOOLTIP_CLOSE spot (#331): ([cell], [the screenshot each was read from]). The tap is made whether a
    tooltip shows or not: one shop.tooltip missed may be what hid them."""
    cells = read_cells(context, image, spots, page)
    shots = [image] * len(cells)
    unknown = [k for k, c in enumerate(cells) if c["id"] is None]
    if unknown and page in TOOLTIP_CLOSE:
        again = close_tooltip(context, page, force=True)
        for c in read_cells(context, again, [(cells[k]["x"], cells[k]["y"]) for k in unknown], page):
            k = unknown[c["i"]]
            cells[k], shots[k] = {**c, "i": cells[k]["i"]}, again
    return cells, shots


def owned_cells(context, page, grid=None):
    """Every gift of the fuse or sell page's owned grid, each read once where it shows whole (#205): ([cells], grid).

    The grid is read on show (read_cells, and the prices on the sell page), then dragged to bring its first cut-off
    row up to the first row's place (with none, the row under a full last row), until no cut-off cell holds a gift or a
    drag moves it no more. A cell is {"i", "x", "y", "tier", "keyword", "id", "score", "price", "look"}: i its place in the
    grid's order, y with the grid at its top, look its centre as read (cell_at finds it again by both); grid is
    {"page", "at": px scrolled, "top": at with the list at its top, "whole": the read went to the grid's end, "placed":
    False, the cells read (fused_cells places them), "missed": a cell not where the grid put it (cell_at)}. The list goes
    to its top first (owned_top).
    """
    (x0, y0), (dx, dy), under = OWNED_GRID[page]
    bottom = CELL_PAGES[page][1]
    out, done = [], set()
    grid, image = owned_top(context, page, grid)
    grid.update(whole=False, placed=False, missed=False)
    if image is None:
        log("shop: no E.G.O Gifts Owned on the fuse page: nothing read")
        return [], grid
    for _ in range(GRID_SCROLLS):
        image = close_tooltip(context, page)
        rows = range(max(0, grid["at"] // dy), grid["at"] // dy + 5)  # the last one all under the edge
        shown = [(5 * r + c, x0 + dx * c, y0 + dy * r - grid["at"]) for r in rows for c in range(5)]
        fresh = [(i, x, y) for i, x, y in shown if i not in done and whole(page, y)]
        done |= {i for i, _, _ in fresh}
        spots = [(x, y) for _, x, y in fresh]
        prices = shop.cell_prices(ocr(context, image, SELL_GRID), spots) if page == "sell" and spots else {}
        cells, shots = read_clear(context, image, spots, page)
        for c, shot in zip(cells, shots):
            i, _, y = fresh[c["i"]]
            out.append({**c, "i": i, "y": y + grid["at"], "price": prices.get(c["i"]), "look": centre(shot, c["x"], y)})
        cut = [y for _, x, y in shown if y + under > bottom and y - 25 < bottom and held(image[:bottom], x, y, page)]
        hidden = min(y for _, _, y in shown if y - 25 >= bottom)
        # A full row over the edge and the next one all under it (a drag the game took less of, or the grid's end): one
        # drag more tells them apart.
        full = not cut and all(held(image[:bottom], x0 + dx * c, hidden - dy, page) for c in range(5))
        if not cut and not full:
            grid["whole"] = True
            break
        moved, image = drag_grid(context, page, (min(cut) if cut else hidden) - y0 - GRID_MARGIN)
        grid["at"] += moved
        if abs(moved) <= 3:
            grid["whole"] = full
            log(f"shop: the {page} grid does not move: " + ("at its end" if full else "its cut-off cells stay unread"))
            break
    else:
        log(f"shop: the {page} grid still has cut-off cells after {GRID_SCROLLS} drags: they stay unread")
    log(f"shop: {page} grid read down {grid['at']} px")
    return out, grid


def owned_top(context, page, grid=None):
    """(grid, the screenshot) with page's list dragged to its top; on the fuse page the owned gifts placed by their label
    (owned_label), the screenshot None when it does not show.

    A page opens where its list was left (live 2026-10-21: the fuse page after a fusion), so a new grid's list goes to its
    top stroke by stroke (grid_top). A grid an earlier read of the page still open left (the fuse page after a fusion,
    #378) goes back by its top in one drag, and to its top stroke by stroke only when the label does not show then. The
    owned gifts are placed by their label whatever that drag measured: sections over them come and go with a fusion (#304).
    """
    (_, y0), _, _ = OWNED_GRID[page]
    kept = grid is not None
    close_tooltip(context, page)
    if kept:
        moved, image = drag_grid(context, page, grid["top"] - grid["at"])
        grid["at"] += moved
    else:
        grid, image = {"page": page, "at": 0, "top": 0}, grid_top(context, page)
    if page != "fuse":
        return grid, image
    label, image, up = owned_label(context, image)
    if label is None and kept:  # the drag back stopped short (a stroke the game took less of): owned_label looks only up
        log("shop: the owned gifts' label is not on show after the drag back: the fuse list goes to its top")
        label, image, up = owned_label(context, grid_top(context, page))
    if label is None:
        return grid, None
    grid["at"] = y0 - label - OWNED_LABEL  # negative: sections over the owned gifts push them down
    grid["top"] = grid["at"] - up
    if not whole(page, y0 - grid["at"]):
        log(f"shop: the owned gifts start at y {y0 - grid['at']}, under the sections over them")
        moved, image = drag_grid(context, page, -grid["at"] - GRID_MARGIN)
        grid["at"] += moved
    return grid, image


def owned_label(context, image):
    """(the centre y of the fuse page's "E.G.O Gifts Owned" label, the screenshot it shows on, the px the list was dragged
    up to show it). From the list's top, up a stroke at a time until it shows: a fixed recipe's section (#103, #78) or a
    limited fusion's sits over it, neither used (#205). (None, the last screenshot, px) when the list ends without it."""
    up = 0
    for _ in range(GRID_SCROLLS):
        box = next((b for t, b in ocr(context, image, FUSE_LIST) if has(t, "Gifts Owned")), None)
        if box:
            return box[1] + box[3] // 2, image, up
        moved, image = drag_grid(context, "fuse", GRID_STROKE)
        up += moved
        if abs(moved) <= 3:
            break
    return None, image, up


def grid_top(context, page):
    """The screenshot of page's list dragged down to its top, a stroke at a time until one moves it no more."""
    for _ in range(GRID_SCROLLS):
        moved, image = drag_grid(context, page, -GRID_STROKE)
        if abs(moved) <= 3:
            return image
    return image


def whole(page, y):
    """Whether a cell of page's owned grid centred at y on screen shows whole: its top and what must show under it."""
    (_, y0), _, under = OWNED_GRID[page]
    return y >= y0 - 3 and y + under <= CELL_PAGES[page][1]


def grid_shift(before, after, page, most):
    """How many px page's owned grid moved up from before to after (down: negative), 0 to most give or take GRID_SLIP:
    the shift under which the two screenshots' grids differ least."""
    (x0, y0), (dx, _), _ = OWNED_GRID[page]
    rows, cols = slice(y0 - 45, CELL_PAGES[page][1]), slice(x0 - 40, x0 + 4 * dx + 40, 3)
    a, b = (im[rows, cols].astype(np.int16).sum(axis=2) for im in (before, after))
    n = len(a)

    def diff(s):
        return np.abs(a[s:] - b[:n - s]).mean() if s >= 0 else np.abs(a[:n + s] - b[-s:]).mean()
    return min(range(min(0, most) - GRID_SLIP, max(0, most) + GRID_SLIP + 1), key=diff)


def drag_grid(context, page, d):
    """Drag page's owned grid up by d px (down when negative) in strokes inside it, each measured (grid_shift): the
    px it moved and the last screenshot. Dragged past an end the grid springs back: the stroke moved it less, and the
    drag stops there."""
    (_, y0), _, _ = OWNED_GRID[page]
    bottom = CELL_PAGES[page][1]
    image, moved = screen(context), 0
    n = -(-abs(d) // GRID_STROKE)
    for k in range(n):
        step = round(d * (k + 1) / n) - round(d * k / n)
        before = page_guard(context, "Shop", image=image)
        scroll(context, GRID_DRAG_X, bottom - 15 if step > 0 else y0 - 30, 0, -step)
        image = still(context, timeout=1.0)
        image = screen(context) if image is None else image
        s = grid_shift(before, image, page, step)
        moved += s
        if abs(s) < abs(step) - 3:
            break
    log(f"shop: {page} grid dragged {d} px, moved {moved}")
    return moved, image


def centre(image, x, y):
    """The grey centre of the grid cell at (x, y) in 4 px blocks, inside its frame (a picked cell's orange stays out):
    a fraction of a px moved blurs edges the blocks average out."""
    return image[y - 20:y + 20, x - 20:x + 20].astype(np.float32).mean(axis=2).reshape(10, 4, 10, 4).mean(axis=(1, 3))


def matched(image, x, y, look):
    """(difference, dy): where within 3 px of (x, y) the cell's centre is likeliest the one look was read from."""
    return min(((np.abs(centre(image, x, y + k) - look).mean(), k) for k in range(-3, 4)), key=lambda m: (m[0], abs(m[1])))


def into_view(context, grid, cell, rows_over=0):
    """Drag the grid to bring cell (owned_cells) whole into view, its row to the first row's place, or rows_over rows
    under it (the rows over it on show too) when it has as many over it: its y on screen."""
    (_, y0), (_, dy), _ = OWNED_GRID[grid["page"]]
    over = min(rows_over, (cell["y"] - y0) // dy) * dy
    for _ in range(3):  # a drag stopped short (an end, a stroke the game took less of) is followed by another
        y = cell["y"] - grid["at"]
        if whole(grid["page"], y):
            break
        grid["at"] += drag_grid(context, grid["page"], y - over - y0 - GRID_MARGIN)[0]
    return cell["y"] - grid["at"]


def cell_at(context, grid, cell):
    """Where cell (owned_cells) shows now: (x, y) on screen, the grid dragged first to bring it whole into view; None
    when its centre there is not the one read (the grid is not where it was measured to be): nothing is tapped, and
    grid["missed"] says so."""
    x, y = cell["x"], into_view(context, grid, cell)
    diff, k = matched(screen(context), x, y, cell["look"])
    if diff > GRID_SAME:
        log(f"shop: cell {cell['i']} is not where the grid puts it ({grid['page']} grid at {grid['at']} px, {diff:.1f})")
        grid["missed"] = True
        return None
    return x, y + k


def fused_cells(context, cells, grid, fusion):
    """The fuse page's owned gifts after `fusion` (Shop.fuse_ordinary's or fuse_recipe's), on the page kept open (#378):
    placed by it instead of read again ([cell], as owned_cells gives them), or None when they are to be read again (the
    reason logged).

    shop.fusion_places puts the gifts left and the gift made in the grid's new order: only when the last read went to the
    grid's end and gave every place a tier, in the page's order (the vestiges first, then highest tier first). After a
    recipe the owned gifts are placed by their label first (owned_top): its Fusion Available section may have gone, the
    list moved up (#304). The gift made's cell is dragged into view, a row over it on show too, and read: it is placed
    (fused_check) when its tier is the fusion's (a recipe's: its id; an ordinary one's, the tier its GET! popup showed,
    #451, tier V for an EX gift, #449),
    its id is read and no gift listed with that id or an unread one looks like it, every other cell on show looks as it was
    read (matched within GRID_SAME) and the places after the last hold no gift. A check that fails places the owned gifts
    by their label once (the list may have sprung back from its end, a section come or gone) and checks again. Each tap
    after it still checks its cell (cell_at).
    """
    (x0, y0), (dx, dy), _ = OWNED_GRID["fuse"]
    placed = grid.get("whole") and shop.fusion_places(cells, [c["i"] for c in fusion["gone"]], fusion["tier"], ((x0, y0), (dx, dy)))
    if not placed:
        log("shop: fuse page kept: " + ("the last read stopped short of the grid's end" if not grid.get("whole") else
                                        "the cells read give no order by tier") + ", owned gifts read again")
        return None
    new, k = placed
    recipe = fusion["gift"] is not None
    if recipe and owned_top(context, "fuse", grid)[1] is None:
        problem, cell = "no E.G.O Gifts Owned label after the recipe", None
    else:
        problem, cell = fused_check(context, new, k, grid, fusion)
    if problem is not None and not recipe:
        log(f"shop: fuse page kept: {problem}, the owned gifts are placed by their label")
        if owned_top(context, "fuse", grid)[1] is None:
            problem = "no E.G.O Gifts Owned label"
        else:
            problem, cell = fused_check(context, new, k, grid, fusion)
    if problem is not None:
        log(f"shop: fuse page kept: {problem}, owned gifts read again")
        return None
    new[k] = cell
    grid.update(placed=True, missed=False)
    log(f"shop: fuse page kept: owned gifts placed by the fusion (new gift read at cell {k})")
    return new


def misplaced(grid):
    """Whether a cell of the grid placed by a fusion (fused_cells) did not show where it was put (cell_at)."""
    return bool(grid.get("placed") and grid.get("missed"))


def fused_check(context, new, k, grid, fusion):
    """(None, the gift made's cell as read) when the screen shows the owned gifts as fused_cells placed them, else (what
    does not hold, None): the gift made's cell `new[k]` dragged into view and read, the other cells on show compared."""
    (x0, y0), (dx, dy), _ = OWNED_GRID["fuse"]
    y = into_view(context, grid, new[k], rows_over=1)
    image = close_tooltip(context, "fuse")
    for c in new:
        at = c["y"] - grid["at"]
        diff = matched(image, c["x"], at, c["look"])[0] if c["i"] != k and whole("fuse", at) else 0
        if diff > GRID_SAME:
            return f"cell {c['i']} is not where the fusion puts it ({diff:.1f})", None
    for j in range(len(new), len(new) + 10):
        at = y0 + dy * (j // 5) - grid["at"]
        if whole("fuse", at) and held(image, x0 + dx * (j % 5), at, "fuse"):
            return f"cell {j} holds a gift, after the last", None
    if not whole("fuse", y):
        return f"cell {k}, the gift made, is not on show", None
    read, shots = read_clear(context, image, [(new[k]["x"], y)], "fuse")
    if not read or read[0]["id"] is None:
        return f"the gift made reads {'unknown' if read else 'no gift'} at cell {k}", None
    cell = {**read[0], "i": k, "x": new[k]["x"], "y": new[k]["y"], "price": None, "look": centre(shots[0], new[k]["x"], y)}
    if cell["tier"] != fusion["tier"] or fusion["gift"] not in (None, cell["id"]):
        made = f"tier {fusion['tier']}" + (f" {fusion['gift']}" if fusion["gift"] else "")
        return f"cell {k} reads tier {cell['tier']} {gift_shown(cell)}, not the {made} made", None
    # A cell listed that looks like it and is not told apart by its id (the same id, or one unread): the gift made may be
    # that one still. Another id read is another gift: live, Old Wooden Doll (II) looked like Finifugality (III), #378.
    twin = next((c["i"] for c in new if c["i"] != k and c["id"] in (None, cell["id"])
                 and matched(shots[0], cell["x"], y, c["look"])[0] <= GRID_SAME), None)
    if twin is not None:
        return f"cell {k}, the gift made, looks like cell {twin}", None
    return None, cell


def fusions(cells, roles, slots, avoid, condition="any", refused=()):
    """shop.pick_fusion over the cells whose role is material and whose tier is read: [([cell index], tier)] (#77).

    The thresholds are the Super Shop's when the page has its 5 slots; a gift whose id is in avoid goes in first (#90);
    condition is the gift list's fusion_condition (#263); refused, the tiers (sorted) of the groups the page's forecast
    turned down (#285).
    """
    d = data("shop.yaml")
    materials = [(c["i"], c["tier"]) for c, r in zip(cells, roles) if r == "material" and c["tier"]]
    tiers = d["fusion_tiers"]["super_shop" if slots == 5 else "shop"]
    return shop.pick_fusion(materials, slots, tiers, d["fusion_points"], {c["i"] for c in cells if c["id"] in avoid},
                            condition, refused)


def read_forecast(context):
    """(the tier the fuse page's Forecasts row predicts, the keyword's chance in %), each None when unread (#285).

    The row shows once a material is in: waited for a second, not longer (a page whose row never reads is no loss).
    """
    image = until(context, shop.forecast_tier, timeout=1.0)
    if image is None:
        return None, None
    return shop.forecast_tier(image), number(text(context, image, FORECAST_CHANCE, only_rec=True))


def tap_keyword(context, keyword):
    """Tap the keyword's card in an open keyword dialog; False when its label is not read."""
    label = next((b for t, b in ocr(context, screen(context), KEYWORD_LABELS) if compact(t) == compact(keyword)), None)
    if label:
        x, y, w, h = label
        tap_moved(context, x + w // 2, y - 40)  # the card lights up
    return bool(label)


def gift_get(context):
    """Confirm the E.G.O Gift GET! popup after a purchase or a fusion: the screenshot its title was read on, None when none
    comes up in 4.5 s. Its gift's mark is on that screenshot already (#449: the 2026-11-04 recording at 30 fps shows the
    title and the "EX" from the popup's first frame, 0.3 s before the tap took it away)."""
    def title(image):
        return has(text(context, image, GET_TITLE), "GET")
    image = until(context, title, timeout=4.5)
    if image is None:
        return None
    for _ in range(3):  # a tap while the popup zooms in is lost
        if tap_then(context, *GET_CONFIRM, lambda im: not title(im), timeout=1.5) is not None:
            still(context, timeout=1.0)  # the popup fades out over the Cost
            break
    return image


def pick_cells(cells, materials):
    """One cell of `cells` per gift id of `materials` (repeats take another cell each)."""
    left, picked = list(cells), []
    for gift_id in materials:
        picked.append(left.pop(next(n for n, c in enumerate(left) if c["id"] == gift_id)))
    return picked


def recipe_places(team, cells, slots):
    """The places (`i`) of the cells the fuse page will make wanted fusions from (#300): every fusion the owned cells hold
    the materials of, one after another. A sale leaves them, and they are no ordinary fusion's materials."""
    left, held = list(cells), set()
    while recipe := recipe_fusion(team["list"], [c["id"] for c in left if c["id"] is not None], slots=slots):
        group = pick_cells(left, recipe["materials"])
        held |= {c["i"] for c in group}
        left = [c for c in left if c["i"] not in held]
    return held


@AgentServer.custom_action("Shop")
class Shop(CustomAction):
    """Heal, replace skills, then sell -> buy and refresh -> fuse until a round does nothing, then leave (spec 03 section 13).

    The visit's state (healed, refreshes used, the gift wanted and whether a sale was tried for it, whether the
    owned gifts were scanned for a fusion, the sinners whose Replace slot was tapped (skill_tapped), the sinners ID Skill
    Search tried (id_tried) and whether it was used (id_searched)) lives in RUN["shop"], so a re-entry from MirrorHub
    carries on; leaving drops it, and a recovery drops the fusion scan (forget_game_state, #459). Every spend keeps the
    team's reserve_cost.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        if not self.to_main(context):
            return True  # a page fading in or out: let MirrorHub look again
        RUN["after_shop"] = True  # #279: the next map's only node is the boss; cleared by the next node entered
        visit = RUN.setdefault("shop", {"healed": False, "refreshes": {"keyword": 0, "normal": 0}, "wanted": None, "sold": False})
        # The sale groups by the fuse page's slots and thresholds before that page was read: a Super Shop's red title tells (#263).
        if "slots" not in visit:
            visit["slots"] = 5 if shop.is_super(screen(context)) else 3
        if not visit["healed"]:
            visit["healed"] = True  # first: a heal handed back mid-way (#118) is not paid twice
            self.heal(context, team)
        self.skill_step(context, team, visit)  # after the heal, before the rounds (#264 時機)
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
                leave_shop()
                return True
            # The dialog slides down; Confirm takes no tap before it stops.
            page_guard(context, "Shop", image=image)
            if tap_shown(context, *BOTTOM_RIGHT, lambda im: has(text(context, im, LEAVE_DIALOG), "Leave the shop"),
                         timeout=1.5) is not None:
                log(f"shop: leave with {read_cost(context)} Cost")
                # Up to the old 2 s for the map: MirrorHub must not find the shop fading out and start a new visit.
                tap_then(context, *LEAVE_CONFIRM, lambda im: Shop.on_map(context, im), timeout=2)
                leave_shop()
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
            at = Shop.way_out(context, image)
            if at in ("map", "main"):
                return at == "main"
            if at is None:
                page_guard(context, "Shop", image=image)  # not a shop page MirrorHub knows: hand it back
                still(context, timeout=1.5)  # a page fading in or out
            else:
                tap_settled(context, *at)
        return False

    @staticmethod
    def way_out(context, image):
        """What image asks of to_main: "map" (the shop was left), "main" (the main page: its Refresh fee shows), the point to
        tap to close a page or dialog (a heal page's Return or Leave too), or None (a page the shop does not know)."""
        if Shop.on_map(context, image):
            return "map"
        title = text(context, image, DIALOG_TITLE)
        if has(text(context, image, GET_TITLE), "GET"):
            return GET_CONFIRM
        if has(title, "Purchase"):
            return PURCHASE_CANCEL
        # Before the Refresh fee: the dialog's Cost digits (x 1020-1061) overlap REFRESH["normal"]'s box (#455).
        if has(title, *REPLACE_MARK):
            return REPLACE_CANCEL
        if has(title, "Keyword Refresh"):
            return KEYWORD_CANCEL
        if has(title, "Keyword Selection"):
            return (490, 566)  # its Cancel
        if has(title, "Gift Info"):  # a bought offer tapped: only a tap outside it closes it
            return OUTSIDE
        if has(title, "E.G.O Gift"):  # the fuse or sell page, a keyword picked or not (#214)
            log(f"shop: {title!r} closed")
            return PAGE_CLOSE
        if has(text(context, image, LEAVE_DIALOG), "Leave the shop"):
            return LEAVE_CANCEL
        if has(text(context, image, HEAL_TITLE), "Heal"):
            return BOTTOM_RIGHT
        # Before the Refresh fee too: it still reads in ID Skill Search's select mode (#456), whose Return leaves it.
        if has(text(context, image, SELECT_TITLE), "Select a Sinner"):
            return BOTTOM_RIGHT
        if number(text(context, image, REFRESH["normal"][1])) is not None:
            return "main"
        return None

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
        grey = bar_dead(screen(context))
        dead = [x for x, sinner in zip(SHOP_PORTRAIT_X, battle.SINNERS) if sinner in grey]
        if "alive" in RUN and 12 - RUN["alive"] != len(dead):
            log(f"shop: {12 - RUN['alive']} dead at the last formation, {len(dead)} grey portraits")
        plan = shop.heal_plan(team["heal"], cost, team["reserve_cost"], len(dead), data("shop.yaml")["heal_cost"])
        log(f"shop: {cost} Cost, {len(dead)} dead, heal {team['heal']}: {plan or 'nothing'}")
        if not plan:
            return
        kind, n = plan
        for x in dead[:n] if kind == "revive" else [None]:
            page_guard(context, "Shop")
            if tap_shown(context, *SHOP_BUTTONS["heal"], lambda im: has(text(context, im, HEAL_TITLE), "Heal"), timeout=2) is None:
                log("shop: the heal page did not open")
                break
            before = read_cost(context, HEAL_COST)

            def paid(im):
                return cost_in(context, im, HEAL_COST) not in (None, before)
            if x is None:
                tap_shown(context, *HEAL_OPTIONS[kind], paid, timeout=1.5)
            else:
                tap_settled(context, *HEAL_OPTIONS[kind], timeout=1.5)
                # only a dead sinner takes the tap; then Select shows
                tap_shown(context, x, 655, lambda im: has(text(context, im, BOTTOM_LABEL), "Select"), timeout=1.2)
                tap_shown(context, *BOTTOM_RIGHT, paid, timeout=2)
            after = read_cost(context, HEAL_COST)
            log(f"shop: {kind}: {before} -> {after} Cost")
            if after == before:
                break
            if kind == "revive" and "alive" in RUN:
                RUN["alive"] += 1
            # the result's Leave: back to the shop
            tap_then(context, *BOTTOM_RIGHT, lambda im: not has(text(context, im, HEAL_TITLE), "Heal"), timeout=2)
            Shop.to_main(context)
        Shop.to_main(context)

    @staticmethod
    def skill_step(context, team, visit):
        """Replace skills (#264 時機, 先後): the listed sinners one by one in the list's order (shop.skill_walk), each
        finished before the next: their own Replace <sinner>'s Skill slot on this page first (#455; half ID Skill Search's
        price for the same swap), then, while they still want a swap by the run's counts (shop.search_turn), ID Skill Search
        on them (#456); how many swaps went through. Called after the heal and after each refresh that took; it never refreshes.

        visit["skill_tapped"] names the sinners whose Replace slot was tapped this visit, added before the tap as the heal's
        flag is (ADR 0007): a visit handed back mid-dialog and entered again does not pay twice. A sinner leaves it again only
        when the bot itself cancelled the dialog before any Confirm because no swap was lit, priced and affordable: the step
        after the next refresh judges it again. With every target at 3/2/1, or no sinner listed, nothing is read and nothing
        tapped. After a slot or a search that tapped, the grid is read again and the next slot found by its sinner (#264:
        whether a swapped slot moves is unseen); one gone is not tapped. ID Skill Search opened on a sinner whose dialog has
        no swap goes on down the list from them, past the sinners whose own Replace slot on this page is still to come.
        """
        listed = team["skill_replacement"]["sinners"]
        if not shop.any_change(listed):
            return 0
        conf, swaps = team["skill_replacement"]["id_skill_search"], data("shop.yaml")["skill_replacement"]
        tapped = visit.setdefault("skill_tapped", [])
        offers = Shop.skill_offers(context)
        plan = shop.skill_plan(listed, offers, RUN.get("skills", {}), tapped, swaps)
        for slot, _, why in plan:
            log(f"shop: {slot['name']!r}: {why}")
        waiting = {entry["sinner"] for _, entry, _ in plan if entry}  # the Replace slots still to come
        made, fresh = 0, True  # fresh: offers is the grid as it stands
        for kind, n in shop.skill_walk(listed, waiting):
            entry = listed[n]
            sinner = entry["sinner"]
            if kind == "replace":
                waiting.discard(sinner)
            elif not (conf["enabled"] and not visit.get("id_searched")
                      and shop.search_turn(entry, RUN.get("skills", {}), visit.get("id_tried", ()), swaps)):
                continue
            if not fresh:
                offers, fresh = Shop.skill_offers(context), True
            if kind == "replace":
                slot = next((s for s in shop.skill_slots(offers) if s["sinner"] == sinner and not s["purchased"]), None)
                if slot is None:
                    log(f"shop: {sinner!r}'s slot is no longer on the grid: skip")
                    continue
                tapped.append(sinner)  # first: a hand-back mid-dialog (#118) is not paid twice
                outcome = Shop.replace_skill(context, slot, entry, team["reserve_cost"], swaps)
                made += outcome == "replaced"
                if outcome == "unchosen":
                    tapped.remove(sinner)
            else:
                outcome = Shop.id_skill_search(context, team, visit, listed[n:], waiting, offers)
                if outcome is None:
                    continue  # nothing tapped: the grid read still stands
                made += outcome
            fresh = False
            if not Shop.to_main(context):
                break  # on the map: the shop was left
        return made

    @staticmethod
    def id_skill_search(context, team, visit, listed=None, waiting=(), offers=None):
        """ID Skill Search (#456): with the team's switch on, tap the Super Shop's slot, try the listed sinners in the list's
        order (shop.id_search_plan) on their dialog and make one swap, paid the team's way; 1 on a swap, 0 when the slot was
        opened for none, None when it was not tapped. skill_step calls it on a sinner's turn (#264 先後) with listed from
        that sinner on and `waiting`, the sinners whose own Replace slot on this page is still to come (skipped: half the
        price); offers is its grid read. Without them it tries the team's whole list on a grid it reads itself.

        A dialog's Cancel lands on the main page (#456 capture), so each next sinner taps the slot again; a portrait that
        opens nothing leaves the select mode up for the next one, and the last such leaves by Return. Each sinner is tried
        once a visit (visit["id_tried"], marked before its portrait's tap); visit["id_searched"] is set before the paying tap
        (the heal's rule) and when the slot shows Purchased: after either, the slot is never opened again this visit.
        """
        conf, team_list = team["skill_replacement"]["id_skill_search"], team["skill_replacement"]["sinners"]
        if not conf["enabled"] or not shop.any_change(team_list) or visit.get("id_searched"):
            return None
        slot = shop.id_search_slot(Shop.skill_offers(context) if offers is None else offers)
        if slot is None:
            return None
        if slot["purchased"]:
            log("shop: ID Skill Search: used already (Purchased): skip")
            visit["id_searched"] = True
            return None
        swaps, tried = data("shop.yaml")["skill_replacement"], visit.setdefault("id_tried", [])
        image = page_guard(context, "Shop")
        plan = shop.id_search_plan(team_list if listed is None else listed, RUN.get("skills", {}), tried, bar_dead(image),
                                   swaps, waiting)
        for _, why in plan:
            log(f"shop: ID Skill Search: {why}")
        entries = [entry for entry, _ in plan if entry]
        if not entries:
            log("shop: ID Skill Search: nobody to try: not opened")
            return None
        before, selecting = read_cost(context), False
        for entry in entries:
            if not selecting:
                if Shop.open_offer(context, slot, "Select a Sinner", SELECT_TITLE) is None:
                    visit["id_searched"] = True  # #264: a slot that opens nothing counts as handled
                    break
                selecting = True
            tried.append(entry["sinner"])  # first: a hand-back mid-dialog (#118) does not try it again
            outcome = Shop.id_search_swap(context, entry, conf["pay"], team["reserve_cost"], before, swaps, visit)
            if outcome == "replaced":
                return 1
            selecting = outcome == "no dialog"
            if visit.get("id_searched") or not (selecting or Shop.to_main(context)):
                return 0  # paid without proof, or on the map
        if selecting:
            log("shop: ID Skill Search: no listed sinner has a feasible swap: Return")
        Shop.to_main(context)  # select mode's Return (way_out)
        return 0

    @staticmethod
    def id_search_swap(context, entry, pay, reserve, before, swaps, visit):
        """One sinner in ID Skill Search's select mode: tap the portrait, read its dialog, put the payment on `pay`, make the
        swap shop.id_search_choice gives. "replaced"; "no dialog" (the select mode is still up); "unchosen" when cancelled
        before any Confirm; "handled" otherwise. before: the main page's Cost, which starlight must leave as it was.
        """
        sinner, head = entry["sinner"], "shop: ID Skill Search: "
        page_guard(context, "Shop")  # the Shop node reads the select mode's title
        image = tap_shown(context, SHOP_PORTRAIT_X[battle.SINNERS.index(sinner)], 655, shows(context, REPLACE_TITLE, "Replace"),
                          timeout=1.5, rest=1.0)
        if image is None:
            log(f"{head}{sinner!r}'s portrait opened no dialog")
            return "no dialog"
        read = Shop.read_replace_dialog(context, image)
        if read["sinner"] != sinner:
            log(f"{head}the dialog is {read['sinner']!r}'s, not {sinner!r}'s: cancel")
            Shop.cancel_replace(context)
            return "handled"
        if read["owned"] is not None:
            note_skills(sinner, read["owned"])  # the counts are real whatever follows
        # Never assumed to carry over: the dialog opened on Cost in the capture (tests/screens/ShopIdSkillSearchDialog.png);
        # whether the game keeps the payment mode is unverified (#456). The prices tell it; a switch must show the other prices.
        # With no price read the payment is unknown, and a switch could flip the wanted one away: cancel.
        mode = shop.pay_mode(read["prices"], swaps)
        if mode is None:
            log(f"{head}{sinner!r}: prices {Shop.price_line(read)}: the payment is unknown: cancel")
            Shop.cancel_replace(context)
            return "handled"
        if mode != pay:
            page_guard(context, "Shop")
            switched = tap_shown(context, *PAY_SWITCH, lambda im: shop.pay_mode(Shop.dialog_prices(context, im), swaps) == pay,
                                 timeout=1.5, rest=1.0)
            if switched is None:
                log(f"{head}{sinner!r}: prices {Shop.price_line(read)}: the payment does not show {pay}: cancel")
                Shop.cancel_replace(context)
                return "handled"
            read = Shop.read_replace_dialog(context, switched)
        owned, funds = read["owned"], read["cost"]
        unit, budget = ("Cost", f", reserve {reserve}") if pay == "cost" else ("starlight", " (no reserve)")
        wanted = [] if owned is None else shop.swaps_wanted(entry["target"], owned, entry["s1_s3_first"], swaps)
        log(f"{head}{sinner!r}: Skills Owned {'unread' if owned is None else shop.counts_line(owned)}, {Shop.price_line(read)}, "
            f"{'unread' if funds is None else funds} {unit}{budget}: try {', '.join(wanted) or 'nothing'}")
        if owned is None:
            log(f"{head}{sinner!r}: Skills Owned unread or not 5-6 cards: cancel")
            Shop.cancel_replace(context)
            return "handled"
        if funds is None:
            log(f"{head}the {unit} reads nothing: cancel")
            Shop.cancel_replace(context)
            return "handled"
        choice = shop.id_search_choice(entry, owned, read["lit"], read["prices"], funds, pay, reserve, swaps)
        if choice is None:
            log(f"{head}{sinner!r}: no swap toward {shop.counts_line(entry['target'])} is lit, priced and affordable in {unit}: cancel")
            Shop.cancel_replace(context)
            return "unchosen"
        swap, price = choice
        if not Shop.pay_swap(context, head, sinner, swap, price, funds, unit.capitalize(),
                             paying=lambda: visit.__setitem__("id_searched", True)):
            return "handled"
        if pay == "cost":
            return Shop.cost_paid(context, head, sinner, swap, price, funds, owned, swaps)
        # Starlight: the top right that showed it is gone with the dialog, and the slot no longer opens. The swap is proven by
        # the slot's Purchased and by the Cost left as it was; anything else forgets the counts (#455 graft 2).
        after = read_cost(context)
        bought = shop.id_search_slot(Shop.skill_offers(context))
        if after != before or not (bought and bought["purchased"]):
            log(f"{head}{sinner!r} {swap} for {price} starlight: the slot reads {'Purchased' if bought and bought['purchased'] else 'no Purchased'}, "
                f"the Cost {before} -> {after}: the counts are not known")
            note_skills(sinner, None)
            return "handled"
        sw = swaps[swap]
        log(f"{head}replaced {sinner!r} {swap} (skill {sw['from']} -> {sw['to']}) for {price} starlight: {funds} -> {funds - price} "
            f"starlight (unread after the dialog), the slot reads Purchased, the Cost stays {after}")
        note_skills(sinner, shop.after_swap(owned, swap, swaps))
        return "replaced"

    @staticmethod
    def dialog_prices(context, image):
        """The Replace dialog's three prices off image, each None when unread."""
        return {k: digits(text(context, image, box)) for k, box in REPLACE_PRICES.items()}

    @staticmethod
    def price_line(read):
        """"s1_s2 45, s2_s3 75 dim, s1_s3 120 dim": a dialog read's prices for the log."""
        return ", ".join(f"{k} {read['prices'][k]}{'' if read['lit'][k] else ' dim'}" for k in REPLACE_PRICES)

    @staticmethod
    def skill_offers(context):
        """The grid's slots as shop.read_slots gives them, one OCR pass (not read_offers' cells and plates). A Super Shop's
        grid is read at its top and after a drag down, as buy_offers reads it (#341), each slot with its "page"."""
        image = page_guard(context, "Shop")
        if not shop.is_super(image):
            return shop.read_slots(ocr(context, image, OFFER_GRID))
        top = [{**s, "page": 0} for s in shop.read_slots(ocr(context, Shop.drag_offers(context, down=False), OFFER_GRID))]
        lower = shop.read_slots(ocr(context, Shop.drag_offers(context, down=True), OFFER_GRID))
        return top + [{**s, "page": 1} for s in lower if offer_whole(s["y"]) and not any(shop.same_offer(s, k) for k in top)]

    @staticmethod
    def read_replace_dialog(context, image):
        """{"sinner", "owned", "cost", "prices", "lit"} off the dialog's screenshot: the title's sinner, the Skills Owned
        counts (None unless 5 or 6 cards), the Cost (None when 3 reads give no digit), each option's price (None when
        unread) and whether it is lit."""
        cost = cost_in(context, image, REPLACE_COST)
        return {"sinner": shop.sinner_named(text(context, image, REPLACE_TITLE)),
                "owned": shop.skills_owned(text(context, image, REPLACE_OWNED)),
                "cost": read_cost(context, REPLACE_COST) if cost is None else cost,
                "prices": Shop.dialog_prices(context, image),
                "lit": {k: shop.option_lit(image, box) for k, box in REPLACE_PRICES.items()}}

    @staticmethod
    def cancel_replace(context):
        """The dialog's Cancel, on either layer: the first goes back to the shop, the second to the first; the Cost stays (#453)."""
        tap_settled(context, *REPLACE_CANCEL)

    @staticmethod
    def replace_skill(context, slot, entry, reserve, swaps):
        """One dialog: open the slot, read it, pick the swap shop.skill_choice gives, Confirm twice, check the Cost.

        "replaced" on a swap; "unchosen" when the bot cancelled before any Confirm because no swap was lit, priced and
        affordable; "handled" otherwise. Each failure of #264's table writes one line; the caller's to_main closes whatever
        is left open. The run's memory of the counts (note_skills) never runs ahead of the game's.
        """
        sinner = slot["sinner"]
        image = Shop.open_offer(context, slot, "Replace", REPLACE_TITLE)
        if image is None:
            return "handled"
        read = Shop.read_replace_dialog(context, image)
        if read["sinner"] != sinner:
            log(f"shop: the dialog is {read['sinner']!r}'s, not {sinner!r}'s: cancel")
            Shop.cancel_replace(context)
            return "handled"
        owned, cost = read["owned"], read["cost"]
        wanted = [] if owned is None else shop.swaps_wanted(entry["target"], owned, entry["s1_s3_first"], swaps)
        log(f"shop: {sinner!r}: Skills Owned {'unread' if owned is None else shop.counts_line(owned)}, {Shop.price_line(read)}, "
            f"{'unread' if cost is None else cost} Cost, reserve {reserve}: try {', '.join(wanted) or 'nothing'}")
        if owned is None:
            log(f"shop: {sinner!r}: Skills Owned unread or not 5-6 cards: cancel")
            Shop.cancel_replace(context)
            return "handled"
        note_skills(sinner, owned)  # the counts are real whatever follows
        if cost is None:
            log("shop: the Cost reads nothing: cancel")
            Shop.cancel_replace(context)
            return "handled"
        choice = shop.skill_choice(entry, owned, read["lit"], read["prices"], cost, reserve, swaps)
        if choice is None:
            log(f"shop: {sinner!r}: no swap toward {shop.counts_line(entry['target'])} is lit, priced and affordable: cancel")
            Shop.cancel_replace(context)
            return "unchosen"
        swap, price = choice
        if not Shop.pay_swap(context, "shop: ", sinner, swap, price, cost, "Cost"):
            return "handled"
        return Shop.cost_paid(context, "shop: ", sinner, swap, price, cost, owned, swaps)

    @staticmethod
    def pay_swap(context, head, sinner, swap, price, funds, unit, paying=None):
        """In an open Replace dialog (a slot's or ID Skill Search's): pick swap, Confirm, check the second layer, Confirm again
        and wait for the main page; True when the dialog left after the paying tap, False otherwise (each failure logs one
        line starting with head; the caller's to_main closes what is left open).

        funds: the top right's number (the Cost, or the owned starlight, #456); unit: what the second layer asks, "Cost" or
        "Starlight". paying(), when given, runs just before the paying tap: a visit marked there is not paid twice.
        """
        page_guard(context, "Shop")
        tap(context, *REPLACE_OPTIONS[swap], wait=0)
        if until(context, lambda im: shop.option_picked(im, REPLACE_FRAMES[swap]), timeout=1.0) is None:
            log(f"{head}{sinner!r}: {swap} did not light up: cancel")
            Shop.cancel_replace(context)
            return False
        page_guard(context, "Shop")
        ask = tap_shown(context, *REPLACE_CONFIRM, shows(context, REPLACE_ASK, rf"spend\s*\d+\s*{unit}"), timeout=2, rest=1.0)
        if ask is None:
            log(f"{head}{sinner!r}: no second confirm asking {unit}: back to the shop")
            return False
        # The second layer is checked twice before the paying tap: its "Spend N Cost" and its "350 ▸ 305" preview, which also
        # catches a Cost misread too high (that would spend into the reserve).
        asked, previewed = number(text(context, ask, REPLACE_ASK)), shop.dialog_price(funds, text(context, ask, REPLACE_PREVIEW))
        if asked != price or previewed != price:
            log(f"{head}{sinner!r}: the dialog asks {asked} and previews {previewed} off {funds}, not {price}: cancel")
            Shop.cancel_replace(context)
            return False
        page_guard(context, "Shop")
        if paying:
            paying()
        tap(context, *REPLACE_CONFIRM, wait=0)
        # No page_guard from here until the dialog is gone: CONNECTING shows (#453) where the global Connecting popup is
        # matched, and a guarded read would hand the shop back in the middle of the payment. Only the Cost is polled; under the
        # dialog SHOP_COST reads no digit, so the wait ends on the main page's number (a new one for Cost).
        landed = until(context, lambda im: cost_in(context, im) not in (None, funds), timeout=REPLACE_SETTLE)
        if landed is None and has(text(context, screen(context), DIALOG_TITLE), *REPLACE_MARK):
            log(f"{head}{sinner!r}: the dialog is still up {REPLACE_SETTLE} s after Confirm: the swap is not known")
            note_skills(sinner, None)
            page_guard(context, "Shop")  # a real Connecting popup: MirrorHub waits it out
            return False
        still(context, timeout=1.5)
        return True

    @staticmethod
    def cost_paid(context, head, sinner, swap, price, cost, owned, swaps):
        """After a swap paid in Cost: "replaced" when the main page's Cost dropped by the price, else "handled"; the run's
        counts follow only what the Cost proves (#455 graft 2)."""
        after = read_cost(context)
        if after == cost:
            log(f"{head}{sinner!r} {swap} for {price}: {cost} -> {after} Cost: the Cost did not change; taking it as not replaced")
            return "handled"
        if after is None or cost - after != price:
            log(f"{head}{sinner!r} {swap} for {price}: {cost} -> {after} Cost: the Cost "
                f"{'reads nothing' if after is None else f'dropped by {cost - after}'}, not the price: the counts are not known")
            note_skills(sinner, None)
            return "handled"
        sw = swaps[swap]
        log(f"{head}replaced {sinner!r} {swap} (skill {sw['from']} -> {sw['to']}) for {price}: {cost} -> {after} Cost")
        note_skills(sinner, shop.after_swap(owned, swap, swaps))
        return "replaced"

    @staticmethod
    def buy(context, team, visit):
        """Buy the gifts of the team's list on show (buy_offers), then refresh while the rules allow; True on any spend.

        A first choice too dear for the reserve becomes visit["wanted"] for the next round's sell, and
        holds the purchases and the refresh back until that sell has been tried. A list with nothing to buy (gifts.purchases:
        it wants nothing the shop sells, and no wanted fusion lacks a gift the shop sells) buys nothing and never refreshes
        (#298). What a wanted fusion lacks depends on the owned gifts: a visit that has not read them reads the sell page first.
        Each refresh asks again with what was bought since: none once the list buys nothing more.
        """
        keyword, reserve, acted = team["keyword"], team["reserve_cost"], False
        to_buy = buy_list(team, visit)
        if visit.get("owned") is None and any(f for _, f in to_buy):
            Shop.read_owned(context, team, visit)
            to_buy = buy_list(team, visit)
        if not to_buy:
            log("shop: the gift list buys nothing the shop sells (no wanted gift, no wanted fusion's material): nothing bought, no refresh")
            return False
        while True:
            if Shop.buy_offers(context, team, visit):
                acted = True
                visit["fuse_scanned"] = False  # a new gift: the fusion grid has changed
            if visit["wanted"] and not visit["sold"]:
                return True  # sell first, next round
            if not buy_list(team, visit):
                log("shop: what was bought meets the gift list (no wanted gift, no wanted fusion's material left): no refresh")
                return acted
            cost = read_cost(context)
            if cost is None:
                log("shop: the Cost reads nothing: no refresh")
                return acted
            image = screen(context)
            fees = {k: number(text(context, image, roi)) for k, (_, roi) in REFRESH.items()}
            limits = {"keyword": team["shop_refresh_keyword"], "normal": team["shop_refresh_normal"]}
            choice = shop.refresh_choice(cost, reserve, visit["refreshes"], limits,
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
            visit["refreshes"][choice] += 1
            visit["sold"] = False
            acted = True
            Shop.skill_step(context, team, visit)  # a refresh can put another sinner's slot up (#264 時機)

    @staticmethod
    def read_owned(context, team, visit):
        """Read the owned gifts off the sell page into visit["owned"] (note_owned); nothing is tapped but the page's button.
        It stays unknown when the page does not open."""
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["sell"], shows(context, DIALOG_TITLE, "Sell"), timeout=2) is not None:
            note_owned(team, visit, owned_cells(context, "sell")[0])
        Shop.to_main(context)

    @staticmethod
    def buy_offers(context, team, visit):
        """Read the offers once, then buy the ones of the team's list shop.buy_plan picks, last cell first; how many bought.

        A gift is told by its icon (read_cells, #297) and by its name plate (read_plates, #329): one vote is enough, two that
        differ leave the cell unknown. Only an offer whose id is known and that gifts.purchases names (the list wants it, or a
        wanted fusion lacks it: buy_list) is bought, in that order (#298); one bought for a fusion is logged with it. Each
        gift bought counts as owned (owned_change) for the next and after a refresh, unread owned gifts or not, so a fusion is
        bought no more than it lacks. A Not
        Enough Cost offer is dimmed (no icon read) but its plate reads: with its id it may be the first choice, so the shop
        sells for it; it is never bought. Every cell, Purchased ones too, is logged with its id. Each purchase is checked on
        the Cost.
        """
        gift_list, reserve = team["list"], team["reserve_cost"]
        to_buy = buy_list(team, visit)
        place, reason = {i: n for n, (i, _) in enumerate(to_buy)}, dict(to_buy)

        def why(i):
            return f" for fusion {reason[i]} {GIFT_NAMES.get(reason[i])}" if reason.get(i) else ""
        visit["wanted"] = None
        cost = read_cost(context)
        if cost is None:
            log("shop: the Cost reads nothing: nothing bought")
            return 0
        avoided = avoided_gifts(team)
        image = screen(context)
        scrolls = shop.is_super(image)  # a Super Shop's third row shows after a scroll (#341)
        if scrolls:
            image = Shop.drag_offers(context, down=False)
        shown = Shop.read_offers(context, image)
        if scrolls:
            for slot in shown:
                slot["page"] = 0
            lower = Shop.read_offers(context, Shop.drag_offers(context, down=True), shown)
            log(f"shop: Super Shop scrolled: {len(lower)} more offers")
            for slot in lower:
                slot["page"] = 1
            shown += lower
        slots = [s for s in shown if shop.on_sale(s)]
        avoid = [g["name"] for g in avoided]
        avoid_ids = [g["id"] for g in avoided]
        offers, ids = [], {}
        for i, slot in enumerate(slots):
            cell, plate = slot["cell"], slot["plate"]
            icon, (named, split) = cell["id"], gift_cells.vote(cell["id"], plate["id"])
            if split:
                log(f"shop: {slot['name']!r}: the icon says {icon} {GIFT_NAMES.get(icon)}, the plate {plate['text']!r} says "
                    f"{plate['id']} {GIFT_NAMES.get(plate['id'])}: unknown")
            cell = {**cell, "id": named, "by_plate": icon is None and named is not None}
            if cell["id"] in avoid_ids or any(rewards.names_gift(slot["name"], n) for n in avoid):
                log(f"shop: {slot['name']!r} {slot['price']}: {gift_shown(cell)}, the team does not hold it (#90)")
                continue
            if slot["short"] and slot["price"] <= cost:
                log(f"shop: {slot['name']!r} {gift_shown(cell)} is tagged Not Enough Cost: its price {slot['price']} is a misread")
                continue
            rank = place.get(cell["id"])
            listed = cell_state(cell, gift_list, owned_now(visit))
            log(f"shop: {slot['name']!r} {slot['price']}: tier {cell['tier']} {cell['keyword']} {gift_shown(cell)}, plate {plate['text']!r}, {listed}"
                f"{'' if rank is None else f', place {rank}{why(cell['id'])}'}")
            if rank is not None:
                offers.append((i, rank, slot["price"]))
                ids[i] = cell["id"]
        plan, visit["wanted"] = shop.buy_plan(offers, cost, reserve, visit["sold"])
        if visit["wanted"]:
            log(f"shop: the first choice costs {visit['wanted']}, {cost} Cost is short: sell first")
        bought = 0
        for i in plan:
            slot = slots[i]
            if ids[i] not in dict(buy_list(team, visit)):
                log(f"shop: {slot['name']!r} {ids[i]}: no longer needed, what was bought meets its fusion")
                continue
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
            log(f"shop: bought {slot['name']!r} for {price}{why(ids[i])}: {cost} -> {after} Cost")
            if after is None or after == cost:
                log("shop: the Cost did not change; taking it as not bought")
                Shop.to_main(context)
                continue
            cost, bought = after, bought + 1
            owned_change(visit, got=[ids[i]])
        return bought

    @staticmethod
    def drag_offers(context, down):
        """Drag the offer grid to its last rows (down) or back to its top; the screenshot once it rests (#341)."""
        top, height = OFFER_GRID[1], OFFER_GRID[3]
        scroll(context, OFFER_DRAG_X, top + height - 15 if down else top + 15, 0, -OFFER_DRAG_PX if down else OFFER_DRAG_PX)
        image = still(context, timeout=1.0)
        return screen(context) if image is None else image

    @staticmethod
    def read_offers(context, image, known=None):
        """The offers of the grid on image as slots (shop.read_slots) with their "plate", and on-sale ones their "cell" and "short".

        known: the offers read off the grid before it was scrolled (#341): those are left out, and so is a cut-off one.
        Bought ones, skills and "??" log their plate (#329).
        """
        shown = shop.read_slots(ocr(context, image, OFFER_GRID))
        if known is not None:
            shown = [s for s in shown if offer_whole(s["y"]) and not any(shop.same_offer(s, k) for k in known)]
        for slot, plate in zip(shown, read_plates(context, image, [offer_cell(s) for s in shown]), strict=True):
            slot["plate"] = plate
            if not shop.on_sale(slot):  # bought, a skill or "??": never bought, its plate logged (#329)
                log(f"shop: {slot['name']!r}: {'Purchased' if slot['purchased'] else 'not on sale'}, plate {plate['text']!r} "
                    + (gift_shown({"id": plate["id"], "by_plate": True, "score": 0.0}) if plate["id"] else "unknown"))
        on_sale = [s for s in shown if shop.on_sale(s)]
        cells = {c["i"]: c for c in read_cells(context, image, [offer_cell(s) for s in on_sale], "offer")}
        for i, slot in enumerate(on_sale):
            slot["cell"] = cells.get(i, {"tier": None, "keyword": None, "id": None, "score": 0.0})
            slot["short"] = slot["short"] or shop.short_cell(image, *offer_cell(slot))
        return shown

    @staticmethod
    def find_offer(context, slot):
        """slot as the grid shows it now, whole in the grid's box; None when it is not found there (#341).

        A Super Shop's grid may be anywhere (a purchase can put it back): the offer is looked for by its column, price and name,
        and the grid is dragged to the end its page is at (slot["page"]: 1 the last rows) until it shows whole.
        """
        for _ in range(3):
            found = next((s for s in shop.read_slots(ocr(context, screen(context), OFFER_GRID))
                          if shop.same_offer(s, slot) and offer_whole(s["y"])), None)
            if found:
                return {**slot, "x": found["x"], "y": found["y"]}
            Shop.drag_offers(context, down=slot["page"] == 1)
        log(f"shop: {slot['name']!r} {slot['price']} not found in the grid")
        return None

    @staticmethod
    def open_offer(context, slot, title="Purchase", roi=DIALOG_TITLE):
        """Tap an offer; the screenshot of the dialog it opens (title read in roi: a purchase's, or a skill replacement's), or
        None when none opened."""
        # Its text and Cost preview are read once it stops.
        page_guard(context, "Shop")
        if "page" in slot:  # a Super Shop's grid scrolls: the offer is brought into view and read back first (#341)
            slot = Shop.find_offer(context, slot)
            if slot is None:
                return None
        image = tap_shown(context, slot["x"], slot["y"] - 50, shows(context, roi, title), timeout=1.5, rest=1.0)
        if image is not None:
            return image
        log(f"shop: {slot['name']!r} opened no {title.lower()} dialog")
        return None

    @staticmethod
    def sell(context, team, visit):
        """Sell the materials no fusion uses (fusions' leftovers, #79) when a wanted gift is too dear.

        Only a gift the team's list lets go is sold (owned_cells, cell_role, #299): one it wants, keeps, a wanted fusion
        locks or whose icon is unknown stays. No cell is tapped but to sell it: the grid is scrolled for the cut-off rows (#205).
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
        # The grid decides (#112, #205): each cell's tier, badge and icon (its id), its price under it.
        avoid = [g["id"] for g in avoided_gifts(team)]
        cells, grid = owned_cells(context, "sell")
        owned = note_owned(team, visit, cells)
        roles = [cell_role(c, team, "sell", avoid, owned) for c in cells]
        # A pack-exclusive fusion the run did not pull does not lock its materials (#306), but the fuse page still makes it
        # (#300): what a held recipe takes is not sold, which runs before the fusion.
        held = recipe_places(team, cells, visit.get("slots", 3))
        roles = ["keep" if c["i"] in held else r for c, r in zip(cells, roles)]
        log("shop: sell cells " + "; ".join(f"{cell_line(c, f'{r}, {cell_state(c, team['list'], owned)}')} {c['price']}" for c, r in zip(cells, roles)))
        gifts = [(c["i"], c["price"]) for c, r in zip(cells, roles) if r == "material" and c["price"]]
        avoided = {c["i"] for c in cells if c["id"] in avoid}  # sold first (#90)
        # The fusion still uses what may not be sold (#79): a vestige the team does not sell (kept on the sell page, material
        # on the fuse page, #161), and a material whose price is unread.
        fuse_only = [c["i"] for c, r in zip(cells, roles) if c["i"] not in held
                     and ((r == "keep" and cell_role(c, team, "fuse", avoid, owned) == "material") or (r == "material" and not c["price"]))]
        # The fusion is grouped without the avoided gifts, which are sold first (#90): a sale then breaks no group.
        materials = [c for c in cells if (c["i"] in dict(gifts) or c["i"] in fuse_only) and c["i"] not in avoided]
        condition = team["list"]["fusion_condition"]  # a group the condition refuses makes no fusion: its gifts are spare
        fused = {i for group, _ in fusions(materials, ["material"] * len(materials), visit.get("slots", 3), (), condition) for i in group}
        # Up to the team's sell_max_tier only (#161); an unread tier may be a V: not sold.
        tiers, top = {c["i"]: c["tier"] for c in cells}, team.get("sell_max_tier", 4)
        spare = [g for g in gifts if g[0] not in fused and (tiers[g[0]] or 9) <= top]
        picked = shop.to_sell(spare, wanted, cost, team["reserve_cost"], avoided)
        visit["fuse_scanned"] = visit.get("fuse_scanned") and not picked
        log(f"shop: {wanted} wanted, {cost} Cost, materials (cell, price) {gifts}, {sorted(fused)} fuse: sell {picked}")
        # The Cost read before any cell was picked: a picked cell shows "51 > 146", read as 51146 (#174).
        before, by_i = cost, {c["i"]: c for c in cells}
        for i in picked or []:
            price = dict(gifts)[i]
            asked = Shop.ask_sale(context, grid, by_i[i], before)
            if asked is False:
                break
            if asked is not None:
                if not re.search(rf"(?<!\d){price}(?!\d)", normalize(text(context, asked, DIALOG_TEXT))):
                    log(f"shop: the sale of cell {i} asks another price than {price}: cancelled")  # another cell picked
                    tap_settled(context, *DIALOG_CANCEL, timeout=1.0)
                    break
                tap(context, *DIALOG_CONFIRM, wait=0)
            # Only before + price is a sale: the preview of an unconfirmed one reads as 51146 (#174).
            sold = until(context, lambda im: cost_in(context, im, SELL_COST) == before + price, timeout=2)
            if sold is None:
                log(f"shop: sell cell {i} for {price}: not sold, {before} -> {read_cost(context, SELL_COST)} Cost")
                break
            log(f"shop: sold cell {i} for {price}: {before} -> {before + price} Cost")
            owned_change(visit, gone=[by_i[i]["id"]])
            before += price
            still(context, timeout=1.5)  # the dialog goes as the Cost turns: the next cell's tap waits for it
            if grid["at"]:  # the grid lost a cell, and may have moved up from its end: from its top again
                grid_top(context, "sell")
                grid["at"] = 0
        Shop.to_main(context)
        return bool(picked)

    @staticmethod
    def ask_sale(context, grid, cell, before):
        """Tap cell (owned_cells) on the sell page, then Sell: the screenshot of the dialog that asks "Sell [<gift>] for
        <price> Cost?", None when none came, False when the cell is not where the grid puts it (cell_at).

        No dialog and the Cost still reads `before` with no dialog up: nothing was picked (a picked cell previews the Cost as
        "51 > 146", #174), so the cell tap was not taken (#611): the cell is found again and tapped once more, then Sell.
        A Cost that reads anything else may be a pick whose Sell tap was lost: a second cell tap would unpick it.
        """
        asks = shows(context, DIALOG_TEXT, r"Sell.*Cost")
        for again in (False, True):
            at = cell_at(context, grid, cell)
            if at is None:
                return False
            page_guard(context, "Shop")
            tap_settled(context, *at, timeout=1.2)
            # Sell's dialog slides down from the top before Confirm takes a tap (#174).
            page_guard(context, "Shop")
            asked = tap_shown(context, *PAGE_OK, asks, timeout=2)
            if asked is not None or again:
                return asked
            image = screen(context)
            if cost_in(context, image, SELL_COST) != before or asks(image):
                return None
            log(f"shop: sell cell {cell['i']} tapped: nothing picked, tapped again")

    @staticmethod
    def fuse(context, team, visit):
        """Fuse the materials shop.pick_fusion picks into the main keyword, Wishmaking left unticked; True when one fused.

        The cells are read off the grid, scrolled for the cut-off rows (owned_cells, #112, #205): the gifts the team's list
        lets go and whose icon is known are the materials, the rest stay (cell_role, #299). No cell is tapped but to put it in. Each material
        tapped in is read back (place); one that does not show closes the page unfused. The page stays open after a fusion
        (#378, as AALC's fuse_useless_gifts): the owned gifts are placed by the fusion (fused_cells: only the gift made is
        read), else read again there, and the next fusion made, a wanted one first, until none is left or FUSIONS_PER_PAGE
        were made; then the page is closed. A cell placed by the fusion that does not show where it was put (cell_at) closes
        the page and opens it again, its owned gifts read from the top: materials may be in.
        A grid that made none is not read again until a purchase or a sale changes the owned gifts (#62), or a recovery
        (forget_game_state, #459).
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
        image = screen(context)
        if image[495:515, 263:283].max(axis=2).mean() > 60:  # unticked: V ~30
            log("shop: Wishmaking is ticked (it spends owned Starlight): no fusion")
            Shop.to_main(context)
            return False
        visit["slots"] = slots = shop.fuse_slots(image)  # the sale needs it too
        if seen(context, image, "ShopFusionAvailable"):
            log("shop: the fuse page shows Fusion Available: the owned gifts are read under it")
        avoid = [g["id"] for g in avoided_gifts(team)]
        grid, cells, fusion, fused_any = None, None, None, False
        for _ in range(FUSIONS_PER_PAGE):
            cells = fused_cells(context, cells, grid, fusion) if fusion else None
            if cells is None:
                cells, grid = owned_cells(context, "fuse", grid)
            owned = note_owned(team, visit, cells)
            roles = [cell_role(c, team, "fuse", avoid, owned) for c in cells]
            log(f"shop: fuse cells ({slots} slots) " + "; ".join(cell_line(c, f"{r}, {cell_state(c, team['list'], owned)}") for c, r in zip(cells, roles)))
            made = Shop.fuse_recipe(context, team, cells, grid, slots, visit)  # a wanted fusion comes before the ordinary one (#300)
            fusion = made if made is False else made or Shop.fuse_ordinary(context, team, visit, cells, roles, slots, grid, avoid)
            if not fusion and misplaced(grid):
                log("shop: a cell placed by the fusion is not where it was put: the fuse page is opened again")
                Shop.to_main(context)
                return Shop.fuse(context, team, visit) or fused_any
            if made is False:  # the page did not take the recipe, and may hold some of its materials: close it, then the ordinary fusion
                Shop.to_main(context)
                return Shop.fuse(context, team, visit) or fused_any  # fuse_recipe put the recipe in visit["recipes_failed"]: it is not tried again
            # Nothing to fuse, unconfirmed, refused or not read back: not the same scan again until the owned gifts change (#103).
            visit["fuse_scanned"] = not fusion
            if not fusion:
                break
            fused_any = True
        else:
            log(f"shop: {FUSIONS_PER_PAGE} fusions on one fuse page: it is closed, the next round opens it again")
        Shop.to_main(context)
        return fused_any

    @staticmethod
    def fuse_ordinary(context, team, visit, cells, roles, slots, grid, avoid):
        """The ordinary fusion of the cells read, fusions' first group put in (place): the fusion made, {"gone": its cells,
        "tier": the GET! popup's numeral (shop.got_tier, #451; EX_TIER when it shows an EX gift, shop.ex_got, #449; the
        page's forecast's when unread, the points' when that is unread too), "gift": None}, for fused_cells. A group the
        page's forecast turns down comes out again and the next is tried, FUSE_TRIES at most (#285); False on none left."""
        condition = team["list"]["fusion_condition"]
        refused = []
        while True:
            picks = fusions(cells, roles, slots, avoid, condition, refused)
            if not picks:
                log(f"shop: {roles.count('material')} materials on show, a fusion takes {shop.MIN_FUSION}"
                    + ("" if condition == "any" else f", and none meets the condition {condition}")
                    + (f", {len(refused)} turned down by the page's forecast" if refused else ""))
                return False
            group, tier = picks[0]
            group = sorted((next(c for c in cells if c["i"] == i) for i in group), key=lambda c: -c["y"])  # the grid's end first
            materials = ", ".join(cell_line(c, "material").rsplit(":", 1)[0] for c in group)
            if not Shop.place(context, group, slots, grid):
                return False
            # The page's own forecast beats the points (#285): a tier the condition refuses is not fused, whichever table
            # the game used. An unread row falls back to the points tier, which pick_fusion already checked.
            page_tier, chance = read_forecast(context)
            wanted = page_tier is None or shop.fusion_wanted(condition, page_tier, [(c["i"], c["tier"]) for c in group])
            act = ("fuse on the points tier" if page_tier is None else "fuse") if wanted else "turned down"
            log(f"shop: fuse forecast {materials}: points tier {tier}, page tier {page_tier or 'unread'}, chance "
                f"{f'{chance}%' if chance else 'unread'}, condition {condition}: {act}")
            if wanted:
                popup = Shop.press_fuse(context, len(group))
                log(f"shop: fuse {materials} into a tier {page_tier or tier} {team['keyword']} gift (condition {condition}): {'not confirmed' if popup is None else 'done'}")
                if popup is None:
                    return False
                owned_change(visit, gone=[c["id"] for c in group])
                if shop.ex_got(popup):  # #449: a fusion short of its 99% gives an EX gift
                    log("shop: the GET! popup shows an EX gift (green EX): the gift made is placed as tier V")
                    return {"gone": group, "tier": EX_TIER, "gift": None}
                # #451: the tier's gifts all taken, the game may give another tier than the table's
                made, expected = shop.got_tier(popup), page_tier or tier
                forecast = ("the forecast's" if page_tier else "the points'") + f" tier {expected}"
                if made is None:
                    log(f"shop: the GET! popup shows no tier numeral: the gift made is placed as {forecast}")
                elif made != expected:
                    log(f"shop: the GET! popup shows tier {made}, not {forecast}: the gift made is placed as tier {made}")
                return {"gone": group, "tier": made or expected, "gift": None}
            refused.append(tuple(sorted(c["tier"] for c in group)))
            if len(refused) >= FUSE_TRIES or not Shop.place(context, group, slots, grid, out=True):
                return False  # the page is closed, which empties it too

    @staticmethod
    def press_fuse(context, count):
        """Press Fuse with `count` materials in and confirm it when the dialog counts as many: the GET! popup's screenshot
        (gift_get), None when it did not come."""
        # Read again on the still screenshot: the one that matched was taken while the dialog zoomed in.
        page_guard(context, "Shop")
        image = tap_shown(context, *PAGE_OK, shows(context, FUSE_CONFIRM, FUSE_COUNT), timeout=2)
        m = image is not None and re.search(FUSE_COUNT, text(context, image, FUSE_CONFIRM))
        if not (m and int(m[1]) == count):
            return None
        tap(context, *FUSE_DIALOG_CONFIRM, wait=0)  # gift_get waits for its GET!
        return gift_get(context)

    @staticmethod
    def fuse_recipe(context, team, cells, grid, slots, visit):
        """Fuse the wanted fusion the owned cells hold the materials of (gifts.recipe_fusion, #300): the fusion made when made
        ({"gone": its cells, "tier": the recipe's, "gift": its id}, for fused_cells), False when tried and not (the recipe is
        added to visit["recipes_failed"], so this visit does not try it again; not when a cell placed by the last fusion was
        not where it was put, cell_at: the page is opened again), None when the list has none to make (or the page cannot hold it).

        The page needs a keyword picked before it unlocks, but a recipe's result does not depend on it (#304): the page's
        keyword stays, and the materials go in as for an ordinary fusion, each read back (place). The page recognises the
        recipe by itself once they are in (its Forecasts row reads III Guaranteed 100%, logged). A tier other than the recipe's
        cancels the fusion unpressed: the materials come back out and the ordinary fusion goes on (#300). The dialog's count must
        be theirs. A recipe the page cannot hold (a Lunar Memory's 5 materials on 3 slots) is passed over for the next wanted one.
        """
        failed = visit.setdefault("recipes_failed", [])
        cells = [c for c in cells if not c.get("unselectable")]  # the page takes none of them in (#378)
        recipe = recipe_fusion(team["list"], [c["id"] for c in cells if c["id"] is not None], slots=slots, skip=failed)
        if recipe is None:
            return None
        group = pick_cells(cells, recipe["materials"])
        group.sort(key=lambda c: -c["y"])  # the grid's end first, as an ordinary fusion's
        names = ", ".join(cell_line(c, "material").rsplit(":", 1)[0] for c in group)
        if not Shop.place(context, group, slots, grid):
            if not misplaced(grid):
                failed.append(recipe["gift"])
            return False
        tier, chance = read_forecast(context)
        recipe_tier = GIFT_TIERS.get(recipe["gift"])
        # The row's tier must be the recipe's own (a recipe's result is fixed, #304): else the page did not take these materials
        # as the recipe, and Fuse is not pressed. Only the tier is compared: the row shows no product name to read. Unread, or
        # a recipe of tier V (shop.forecast_tier never reads one), it goes on: a recipe has no points tier to fall back on.
        cancel = tier is not None and recipe_tier is not None and recipe_tier <= shop.FUSION_TOP_TIER and tier != recipe_tier
        made = not cancel and Shop.press_fuse(context, len(group)) is not None
        if made:
            owned_change(visit, gone=recipe["materials"], got=[recipe["gift"]])
        if not made:
            failed.append(recipe["gift"])
        if cancel:
            Shop.place(context, group, slots, grid, out=True)  # the materials back out; if one stays, the caller closes the page
        log(f"shop: recipe fusion {recipe['gift']} {GIFT_NAMES.get(recipe['gift'])} from {names}: page tier {tier or 'unread'}, chance "
            f"{f'{chance}%' if chance else 'unread'}: "
            + (f"cancelled, the recipe is tier {recipe_tier}" if cancel else "done" if made else "not confirmed"))
        return made and {"gone": group, "tier": recipe_tier, "gift": recipe["gift"]}

    @staticmethod
    def place(context, cells, slots, grid, out=False):
        """Tap cells into the fusion, each read back (#77); False at the first that does not show, nothing put in before.

        Each is dragged into view first (cell_at). After a tap one slot more holds a material and the tapped cell's
        frame turns orange: the gift went in, and it is the one meant (cell_at found it, the grid is not sorted again).
        out: the other way round (#285), the materials in taken out again: one slot fewer, the frame gone.
        A tap that changed nothing (the slots and the cell's frame as before it) was not taken (#611: the game kept the cell
        pressed, 1 tap in 147 live, its touch_up sent 53 ms after touch_down; the release is lost in the game or the emulator,
        out of the bot's reach): once the screen stops it is read again, and still unchanged, the cell is found again and
        tapped once more. Any other read-back gives up at once: that tap may have been taken, and another would undo it.
        """
        def reads(image, x, y):  # the slots holding a material, and whether the cell at (x, y) is framed
            return shop.placed(image, slots), shop.picked(image, x, y, CELL_PAGES["fuse"][1])
        filled = shop.placed(screen(context), slots)
        if filled != (len(cells) if out else 0):
            log(f"shop: {filled} materials in before any tap: " + ("not the group to take out" if out else "no fusion"))
            return False
        for n, c in enumerate(cells, 1):
            meant, unchanged = (len(cells) - n, len(cells) - n + 1) if out else (n, n - 1)
            for again in (False, True):
                at = cell_at(context, grid, c)
                if at is None:
                    return False
                x, y = at
                page_guard(context, "Shop")
                tap_moved(context, x, y, timeout=0.5)
                filled, framed = reads(close_tooltip(context, "fuse", force=True), x, y)  # its tooltip shades the grid, still fading in maybe
                if filled == unchanged and framed == out and not again:
                    still(context, timeout=1.0)  # a tap taken late shows now: no second tap then
                    filled, framed = reads(close_tooltip(context, "fuse"), x, y)
                    if filled == unchanged and framed == out:
                        log(f"shop: cell {c['i']} tapped: nothing changed, tapped again")
                        continue
                if filled != meant or framed == out:
                    log(f"shop: cell {c['i']} tapped: {filled} materials in, {'framed' if framed else 'not framed'}: "
                        + ("not taken out" if out else "no fusion"))
                    return False
                break
        return True


# Settlement (spec 03 section 14): the Exploration Reward window.
RESULT = [300, 400, 100, 85]  # "Floor 5 [NORMAL] 6/6" under the floor icon
WEEKLY_LEFT = [440, 230, 65, 50]  # "n/3"
TOGGLE_X, TOGGLE_ROI = (558, 660, 763), (-45, 237, 90, 30)  # the 3 weekly-bonus toggles: x centre, roi offset
GIVE_UP, CLAIM = (393, 544), (887, 544)
REWARD_TITLE_ROI = [500, 100, 280, 45]
DIALOG_TEXT = [360, 280, 560, 140]
FIRST_FLOOR = [96, 238, 64, 36]  # Dungeon Progress's floor 1 tile, left of the dialog: "[HARD] Floor1" (2026-10-29)
DIALOG_CANCEL, DIALOG_CONFIRM = (515, 493), (763, 493)


def reward_up(context, image):
    """Whether the Exploration Reward window's title reads; it does under its dialogs too."""
    return has(text(context, image, REWARD_TITLE_ROI), "Exploration Reward")


def claim_asks(context, image):
    """The window's dialog that shows (settlement.claim_dialog), or None."""
    return settlement.claim_dialog(text(context, image, DIALOG_TEXT))


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
    """Claim check, weekly-bonus toggles, then Claim or GiveUpRewards; then the team queue and runs.jsonl (spec 03 section 14).

    Claim is pressed only after the toggles read back exactly as wanted; anything unexpected stops.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        if claim_asks(context, image):
            # left over from an earlier try: back out and decide again
            tap_then(context, *DIALOG_CANCEL, lambda im: not claim_asks(context, im), timeout=1.5)
            return True
        lines = sorted(ocr(context, image, RESULT), key=lambda r: r[1][1])  # results come out of order
        result = settlement.read_result(" ".join(t for t, _ in lines))
        if not result:
            return True  # fading in: let MirrorHub look again
        floor, hard = result.floor, result.hard
        log(f"exploration reward: Floor {floor} [{(result.difficulty or '?').upper()}] {result.cleared}/{result.total}")
        if not settlement.claim_ok(result):
            return self.give_up(context, run, result)

        s, team = run["settings"]["run"], run["team"]
        left = number(text(context, image, WEEKLY_LEFT).split("/")[0])
        # The difficulty each floor was played on, as the theme pack page showed it: a run with no plan in memory (an
        # expired session's dialog came first, #382) counts the same. Floors not seen (a resumed run): the window's floor 1 tile.
        floors_hard = RUN.get("floors_hard", {})

        def first_tile():
            tile = text(context, image, FIRST_FLOOR)
            log(f"floors before {min(floors_hard, default=floor + 1)} were not seen: the window's floor 1 tile reads {tile!r}")
            return tile
        want = settlement.claim_bonuses(result, s["target_floor"], s["weekly_bonus_use"], s["weekly_bonus_amount"], left or 0, floors_hard, first_tile)
        for _ in range(6):
            states = toggles(context, page_guard(context, "ExplorationReward"))
            on = [i for i, v in enumerate(states) if v]
            if None in states and len(on) <= want:
                # an unread toggle may be ON: never claim on a guess
                until(context, lambda im: None not in toggles(context, im), timeout=1)
                continue
            if len(on) == want:
                break
            i = on[-1] if len(on) > want else states.index(False)
            tap_then(context, TOGGLE_X[i], 252, lambda im: toggles(context, im)[i] is (not states[i]), timeout=1.5)
        else:
            return stop(context, f"weekly bonus toggles read {states}, want {want} ON: not claiming")
        log(f"weekly bonuses left {left}, use {s['weekly_bonus_use']}/{s['weekly_bonus_amount']}: toggles {states} verified, {want} ON")

        # Live: Claim asks to confirm with bonuses left and none ON (2026-10-15), and with any ON (2026-10-16).
        # Confirm only the dialog of what the toggles were set and read back to; a bonus is spent only then.
        asked = "bonus" if want else "no_bonus"

        def answered(im):
            return not reward_up(context, im) or claim_asks(context, im) == asked
        tap_then(context, *CLAIM, answered, timeout=2)
        for _ in range(5):
            image = screen(context)
            if not reward_up(context, image):
                break
            if claim_asks(context, image) == asked:
                # it moves for about 0.5 s after its first frame (2026-10-29, 2026-11-08 recordings); tapped once still
                still(context, timeout=1.5)
                tap_then(context, *DIALOG_CONFIRM, lambda im: not reward_up(context, im), timeout=2)
                continue
            until(context, answered, timeout=1)
        else:
            # Anything else, too few Enkephalin Modules most likely: nothing more is tapped, so nothing is bought.
            return stop(context, f"Claim did not close the window: {text(context, image, DIALOG_TEXT)!r}",
                        run_line(run, "stop", hard, settlement.floors_passed(result), want))
        log(f"claimed with {want} weekly bonus(es)")
        self.record(run, result, want, "clear")
        log(requeue(ROOT, team["id"]) if run.get("planned") else "this run's team is not known: the team queue stays")
        RUN.clear()
        return True

    def give_up(self, context, run, result):
        """GiveUpRewards, then `End expedition without claiming rewards?` Confirm; no module is spent.

        A run that earned nothing (`Floor 1 [NORMAL] 0/6`) gets no dialog: the window closes on GiveUpRewards, a run
        given up all the same (live 2026-11-08, #586). The run is recorded once the window goes: one that stays would
        bring Settle back to give it up again and write a second line for it (#566). The dialog is confirmed again while
        it stays, as Claim's is.
        """
        def closed(im):
            return not reward_up(context, im)
        for _ in range(3):
            page_guard(context, "ExplorationReward")  # also under its give-up dialog (maatools: GiveUpDialog.png)
            image = tap_shown(context, *GIVE_UP, lambda im: claim_asks(context, im) == "giveup" or closed(im), timeout=1.5)
            if image is not None:
                break
        else:
            return stuck("GiveUpRewards brought up no `End expedition without claiming rewards?` and left the window up")
        for _ in range(5):
            if claim_asks(context, image) == "giveup":
                page_guard(context, "ExplorationReward", image=image)
                image = tap_then(context, *DIALOG_CONFIRM, closed, timeout=2)
            else:
                image = until(context, closed, timeout=1)
            if image is not None:
                break
            image = still(context, timeout=1.5)  # a dialog fading out is not tapped again
            if image is None:
                image = screen(context)
        else:
            return stuck("the Exploration Reward window stayed after its give-up Confirm")
        log("floor 5 not passed: gave up the rewards")
        self.record(run, result, 0, "giveup")
        RUN.clear()
        return True

    @staticmethod
    def record(run, result, bonuses, outcome):
        settlement.append_run(ROOT, run_line(run, outcome, result.hard, settlement.floors_passed(result), bonuses))
        counts = settlement.counts_as_run(outcome)
        TASK["runs"] += counts
        TASK["forfeits"] = [] if counts else [*TASK.get("forfeits", []), run.get("forfeited")]
        TASK["settled"] = True
        STUCK["ladder"] = recovery.Ladder()
