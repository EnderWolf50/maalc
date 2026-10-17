"""Custom actions: the choices MirrorHub hands to the Agent (ADR 0002).

The Pipeline decides which screen is up; these decide what to pick on it.
Coordinates are on the 1280x720 screenshot (spec 07).
"""

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

import battle
import gift_search
import map_route
import recovery
import rewards
import run_start
import settlement
import shop
from settings import SettingsError, load_settings
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
STARLIGHT_AVAILABLE = [1010, 30, 80, 28]
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
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


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
            if node and node.name not in ("MirrorDungeon", "MirrorHub", "Stuck", "GlobalStuck"):
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
        if STUCK["watch"].see(kind, recovery.thumb(image), time.monotonic()):
            stuck(f"{kind}: the screen did not change")
        elif recovery.over_time(kind, RUN.get("deadline"), time.time()):
            RUN.pop("deadline")  # once a floor: the next floor starts the clock again
            stuck(f"floor {RUN.get('floor', '?')} over its time limit", level=2)


@AgentServer.custom_action("Recover")
class Recover(CustomAction):
    """Run the recovery level the Ladder gives (Pipeline RecoverL1-3), or stop (spec 06).

    MirrorHub's timeout (GlobalStuck, no flag set) counts as a stuck on the last screen handed out.
    A level that does not go through climbs straight to the next one.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        flag = STUCK["flag"] or (f"{STUCK['kind']}, then nothing recognised", 1, "MirrorHub recognised nothing for 60 s")
        STUCK["flag"] = None
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
        for key in ("turn", "battle_start", "map_misses", "event_tried"):
            RUN.pop(key, None)
        return True


@AgentServer.custom_action("Halt")
class Halt(CustomAction):
    """Stop on a screen the bot must not act on (the maintenance notice); the reason goes to the log."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return stop(context, f"{argv.node_name}: {json.loads(argv.custom_action_param or '""')}")


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
        RUN.clear()
        # planned: the bot picked the team itself, so the rotation cursor may move after the claim.
        limit = recovery.floor_limit(recovery.read_runs(ROOT), team["id"])
        # guard: the run's guard turns left (spec 03 section 8), counted across its battles.
        # floor_limit: each floor's time; the first clock runs from here, PickThemePack restarts it (spec 06).
        RUN.update(settings=settings, team=team, difficulty=difficulty, planned=True, start=settlement.now(), deadline=time.time() + limit,
                   floor_limit=limit, guard=team["guard_turns"])
        STUCK["ladder"] = recovery.Ladder()
        log(f"new run: {difficulty}, team {team['name']!r} (TEAMS #{team['game_team']}), weekly bonuses left {weekly}, time limit {limit / 60:.0f} min a floor")
        tap(context, 1108, 494, wait=1.5)
        return True


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Pick the team's in-game TEAMS #N slot, check the title, press Confirm."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if "settings" not in RUN:
            # The plan is made on the entry page (weekly bonuses); the back arrow leads there.
            log("team picker without a run plan: back to the entry page")
            tap(context, 97, 42, wait=2)
            return True
        n = RUN["team"]["game_team"]
        for _ in range(15):
            image = screen(context)
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
                tap(context, 130, move[1], wait=1.5)
                image = screen(context)
                title = text(context, image, [220, 112, 210, 26])
                if re.search(rf"#\s*{n}\b", title):
                    bonus = number(text(context, image, [1160, 522, 60, 34]))
                    log(f"team TEAMS #{n}, Starlight Bonus {bonus}")
                    tap(context, 1145, 587, wait=2)
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
    """Available starlight, or None when it reads like "0+60": then owned starlight is being spent."""
    t = text(context, image, STARLIGHT_AVAILABLE)
    return None if "+" in t else number(t)


@AgentServer.custom_action("BuyStarlight")
class BuyStarlight(CustomAction):
    """Select graces per the team's starlight plan, then press Enter (spec 03 section 4).

    Live 2026-10-14: tapping a card selects it at the level its + / ++ buttons show;
    the buttons only set the level (tapping the lit one turns it back to base).
    A card dearer than Available is still selected, paid from owned starlight:
    so every price is checked here first and Available re-read after every tap.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        plan = run_start.resolve_plan(run["settings"], run["team"], "starlight")
        image = screen(context)
        available = read_available(context, image)
        if available is None:
            return stop(context, "starlight page already spends owned starlight")
        unaffordable = run["settings"]["run"]["starlight_unaffordable"]
        buys, missed = run_start.starlight_purchases(plan, available, unaffordable)
        for n, level, price in missed:
            log(f"grace {n} {level} costs {price}: not bought")
        if missed and unaffordable == "stop":
            return stop(context, "a planned grace is unaffordable")
        for n, level, price in buys:
            x, y = grace_box(n)
            if grace_selected(image, n):
                log(f"grace {n} already selected")
                continue
            if not self.set_level(context, n, level):
                return stuck(f"could not set grace {n} to {level}")
            for _ in range(2):
                tap(context, x + 92, y + 100)
                image = screen(context)
                now = read_available(context, image)
                if now != available:
                    break
            if now is None:
                tap(context, x + 92, y + 100)  # undo: never pay with owned starlight
                return stop(context, f"grace {n} would spend owned starlight")
            if now != available - price:
                return stop(context, f"grace {n} {level}: Available {available} -> {now}, expected -{price}")
            log(f"grace {n} {level} for {price}, {now} left")
            available = now
        tap(context, 1195, 672, wait=1.5)
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
            if "-" in text(context, image, [870, 165, 85, 25]):
                tap(context, 543, 530)
                return stop(context, "the graces would spend owned starlight")
            # The line under the checkbox: "Any unspent Starlight will be added ..." when off,
            # "Coverts any remaining Starlight ..." when on.
            note = text(context, image, [660, 395, 320, 90]).lower()
            on = True if "remaining" in note else False if "unspent" in note else None
            if on == want:
                tap(context, 738, 530, wait=2)
                return True
            if on is not None:
                tap(context, 727, 363)
        return stuck("could not set Convert Starlight to Cost")


@AgentServer.custom_action("PickStartingGift")
class PickStartingGift(CustomAction):
    """Open the team keyword's cabinet, take its gifts in order until Select n/m is full, press Select."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        keyword = team["keyword"]
        self.set_gift_search(context, bool(team["gift_search"]["enabled"] and team["gift_search"]["gifts"]))
        if not self.full(context):
            for _ in range(3):
                image = screen(context)
                label = next((b for t, b in ocr(context, image, [145, 145, 590, 430]) if t.strip().lower() == keyword.lower()), None)
                if label:
                    break
                scroll(context, 440, 480, 0, -250)  # Pierce and Blunt sit below the fold
            else:
                return stuck(f"no {keyword} cabinet")
            x, y, w, h = label
            tap(context, x + w // 2, y + h // 2 + 75)
            for gift_y in (262, 370, 475):
                if self.full(context):
                    break
                tap(context, 970, gift_y, wait=1.5)
        # Live: the first tap on Select right after picking is often ignored.
        for _ in range(4):
            tap(context, 1080, 587, wait=2.5)
            image = screen(context)
            if "GET" in text(context, image, [520, 160, 240, 40]) or "Selected" not in text(context, image, [780, 145, 230, 35]):
                log(f"starting gift: {keyword}")
                return True
        return stuck("Select did not take the starting gift")

    @staticmethod
    def set_gift_search(context, want):
        """Turn the Activate Gift Search switch on only for a team with gifts to search (spec 03 section 5).

        Live 2026-10-16: off skips the E.G.O Gift Search page; the next run keeps the switch (back on after a restart).
        An unread switch is left alone: the search page, if it comes, refuses or picks anyway.
        """
        for _ in range(3):
            shown = text(context, screen(context), [1100, 145, 85, 28]).upper()
            on = False if "OFF" in shown else True if "ON" in shown else None
            if on is None or on == want:
                return
            tap(context, 1140, 158, wait=1)
            log(f"Activate Gift Search: {'on' if want else 'off'}")

    @staticmethod
    def full(context):
        """Select n/m reads n == m."""
        m = re.search(r"(\d)\s*/\s*(\d)", text(context, screen(context), [990, 565, 190, 45]))
        return bool(m) and m[1] == m[2]


# E.G.O Gift Search page (live 2026-10-16, 1.117.0). Tabs left to right, 62 px apart.
SEARCH_TABS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
SEARCH_COUNT = [1010, 550, 190, 50]  # "Select 0/3"
SEARCH_OWNED = ([935, 26, 120, 38], [1065, 26, 80, 38])  # "1315-270" and "1045"
SEARCH_PANEL_Y = (205, 316, 427)  # name lines of the Selected E.G.O Gift panel's 3 entries
SEARCH_SELECT = (1100, 575)
SEARCH_REFUSE = (922, 575)
SEARCH_DIALOG = [400, 315, 480, 60]  # "Consume 70 Starlight to search and obtain these E.G.O Gifts?"
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

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        search = run["team"]["gift_search"]
        wanted = search["gifts"] if search["enabled"] else []
        names = [g["name"] for g in wanted]
        if "Consume" in text(context, screen(context), SEARCH_DIALOG):
            tap(context, *SEARCH_DIALOG_BUTTONS["cancel"], wait=1.5)  # left open by an earlier try: check the picks again
        tried, dropped = [], 0
        while True:
            image = screen(context)
            count = gift_search.select_count(text(context, image, SEARCH_COUNT))
            if count is None:
                return True  # fading in or out: let MirrorHub look again
            chosen = self.chosen(context, image, names)
            unwanted = [k for k, c in enumerate(chosen) if c not in names]
            if unwanted and dropped < 3:
                # Left over from a tap that missed: tapping its panel entry unselects it (live 2026-10-16).
                log(f"gift search: unselecting {chosen[unwanted[0]]}, not in the team's list")
                tap(context, 1000, SEARCH_PANEL_Y[unwanted[0]] + 45, wait=1.5)
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
            tap(context, *SEARCH_REFUSE, wait=1.5)
            return True
        owned = gift_search.owned_starlight(*(text(context, image, roi) for roi in SEARCH_OWNED))
        # Select asks "Consume N Starlight to search and obtain these E.G.O Gifts?"; the GET! windows are MirrorHub's.
        for _ in range(3):
            tap(context, *SEARCH_SELECT, wait=2)
            ask = text(context, screen(context), SEARCH_DIALOG)
            if "Consume" in ask:
                break
        else:
            return stuck("Select did not ask to consume starlight")
        tap(context, *SEARCH_DIALOG_BUTTONS["confirm"], wait=2)
        price = number(ask.split("Starlight")[0])
        before = owned[0] if owned else None
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
            image = screen(context)
            cells = gift_search.gift_cells(image)
            for score, x, y in GiftSearch.icon_scores(context, image, entry["id"], [c for c in cells if c[2] == gift["tier"]])[:2]:
                if score < ICON_MIN:
                    break
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
            if np.abs(screen(context)[228:625, 85:775].astype(int) - image[228:625, 85:775].astype(int)).mean() < 2:
                return False  # the end of the tab
        return False

    @staticmethod
    def open_tab(context, keyword):
        """Open keyword's tab at its top: switching tabs resets the scroll (live 2026-10-16), so via a neighbour."""
        i = SEARCH_TABS.index(keyword)
        tap(context, 113 + 62 * (i + 1 if i == 0 else i - 1), 190, wait=0.6)
        tap(context, 113 + 62 * i, 190, wait=1)

    @staticmethod
    def scroll(context, distance):
        """Drag the grid up by distance px (down when negative), in strokes that stay inside it.

        Dragged past the tab's end, the grid springs back after the lift: wait that out.
        """
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
        tap(context, x, y, wait=1)
        new = [t for t in GiftSearch.chosen(context, screen(context), []) if t not in before]
        if new and run_start.match_pack(new[0], [name]):
            return True
        if new:
            log(f"gift search: the icon match picked {new[0]}, not {name}: unselected")
            tap(context, x, y, wait=1)
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

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        m = re.search(r"FLOOR\s*(\d)", text(context, image, [480, 100, 320, 40]))
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
        seen = None
        for _ in range(10):  # ponytail: stop when a refresh changes nothing; read `Refresh n/m` if that misfires
            cards = pack_titles(context, screen(context))
            if not cards:
                return stuck("no theme pack titles read")
            ranked = run_start.rank_packs([lines for _, lines in cards], names, marks)
            log(f"floor {floor} packs: " + ", ".join(f"{t} ({r})" for t, r in ranked))
            ranks = [r for _, r in ranked]
            titles = [t for t, _ in ranked]
            if not all(r == "avoid" for r in ranks) or titles == seen:
                break
            seen = titles
            tap(context, 1083, 47, wait=3)
        i = run_start.pick_pack(ranks)
        x = cards[i][0]
        log(f"floor {floor}: pull {ranked[i][0]!r}")
        swipe(context, x, 330, x, 650, ms=600, wait=0)
        # The page fades out slowly; do not let MirrorHub pull twice.
        until(context, lambda im: "FLOOR" not in text(context, im, [480, 100, 320, 40]), timeout=9)
        return True

    @staticmethod
    def set_difficulty(context, floor, want):
        for _ in range(4):
            shown = text(context, screen(context), [830, 30, 160, 35]).upper()
            hard = True if "HARD" in shown else False if "NORMAL" in shown else None
            if hard is None:
                time.sleep(1)
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
            tap(context, 965 if move == "hard" else 850, 46, wait=2.5)
        return False


# Map page (spec 03 section 7). Offsets are from the MapBus template's top-left corner.
BUS_HOME = (446, 320)  # map panned ~70 px down from rest (bus at 446, 248): top-row badges clear the resource bar
BUS_REST = (446, 248)
SLOT = (279, 37)  # middle-row slot centre; map_route.ROW_DY gives the other rows
LINKS = {
    "up": ("MapLinkUp", (90, -115, 110, 110)),
    "mid": ("MapLinkMid", (95, -10, 110, 80)),
    "down": ("MapLinkDown", (85, 85, 110, 110)),
}
MARKS = {  # node -> (mark, roi around the slot centre)
    "MapNodeBoss": ("boss", (-40, -40, 80, 80)),
    "MapNodeFocusedHex": ("focused", (-80, -60, 160, 120)),
    "MapNodeFocusedRound": ("focused", (-75, -60, 150, 120)),
    "MapNodeCost": ("cost", (-60, -80, 120, 60)),
    "MapNodeGift": ("gift", (-60, -80, 120, 60)),
    "MapNodeEvent": ("event", (-60, -60, 120, 120)),
    "MapNodeShop": ("shop", (-60, -60, 120, 120)),
}
ENTER = (1133, 543)
MAP_RETRIES = 3  # RouteMap calls per floor that may enter nothing before the map is stuck
MAP_LOOKS = 4  # looks, 1 s apart, for a linked slot before the fallback taps
PANEL_REWARDS = [700, 495, 110, 30]  # the "Clear Rewards" label
PANEL_COST = [730, 545, 40, 35]  # the number by its Cost coin


def seen(context, image, node, roi=None):
    """The node's hit on image, its roi overridden and clipped to the screen; None on a miss."""
    override = None
    if roi:
        x, y, w, h = roi
        x0, y0 = max(0, x), max(0, y)
        override = {node: {"roi": [x0, y0, min(1280, x + w) - x0, min(720, y + h) - y0]}}
    detail = context.run_recognition(node, image, override)
    return detail if detail and detail.hit else None


def map_weights(context):
    run = current_run(context)
    hard = run.get("floor_hard", run["difficulty"] == "hard")
    data = yaml.safe_load((RESOURCE / "base" / "data" / "map_weights.yaml").read_text(encoding="utf-8"))
    return data["hard" if hard else "normal"]


def enter_node(context):
    """On the node selection panel: log its Clear Rewards, press Enter until the panel is gone."""
    # Only logged: events show no Clear Rewards, a shop shows the next boss's (spec 03 section 7).
    image = screen(context)
    cost = number(text(context, image, PANEL_COST)) if "Rewards" in text(context, image, PANEL_REWARDS) else None
    log(f"node panel: Clear Rewards Cost {cost}")
    for _ in range(3):
        tap(context, *ENTER, wait=0)
        if until(context, lambda im: not seen(context, im, "MapNodePanel")) is not None:
            log("entered the node")
            until(context, lambda im: not seen(context, im, "MirrorMap"), timeout=3)  # the map fades out
            return True
    return stuck("Enter on the node panel did nothing")


@AgentServer.custom_action("EnterNode")
class EnterNode(CustomAction):
    """The node selection panel is already up (e.g. after a restart): enter the node."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return enter_node(context)


@AgentServer.custom_action("RouteMap")
class RouteMap(CustomAction):
    """Pick the next node and enter it (spec 03 section 7).

    Slots linked to the bus (a chevron on the link) are typed by their marks, ranked by
    map_route.rank and tapped in that order until the node panel (MapNodePanel) shows. After them come
    the fallbacks: the bus (a node reached but not entered), then the slots not tried yet.
    Nothing taking a tap spends one of the floor's map retries; when they run out, the map is stuck (spec 06).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("forfeit"):
            return forfeit(context)
        for _ in range(MAP_LOOKS):  # live: right after a floor's theme pack, the map shows before its bus and links
            if still(context) is None:
                return True  # still fading in or out: let MirrorHub look again
            image, bus = self.find_bus(context)
            bx, by = bus or BUS_REST  # no bus found: assume the map at rest
            slots = self.read_slots(context, image, bx, by) if bus else {}
            if slots:
                break
            time.sleep(1)
        log("map: " + (", ".join(f"{r} {t} ({'?' if n is None else n} onward)" for r, (t, n) in slots.items()) or "no linked slot read"))
        order = map_route.rank(slots, map_weights(context))

        def centre(row):
            return bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]

        tries = [(f"{r} {slots[r][0]}", centre(r)) for r in order]
        tries += [("the bus", (bx + 22, by + 37))] + [(f"{r} slot", centre(r)) for r in map_route.ROWS if r not in order]
        for name, (x, y) in tries:
            tap(context, x, y, wait=0)
            if until(context, lambda im: seen(context, im, "MapNodePanel")) is not None:
                log(f"map: take {name}")
                return enter_node(context)
        RUN["map_misses"] = RUN.get("map_misses", 0) + 1
        if RUN["map_misses"] >= MAP_RETRIES:
            return stuck(f"no node on the map took a tap, {MAP_RETRIES} times this floor")
        log("map: no node took a tap; MirrorHub looks again")
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
            # At rest only the top row hides under the resource bar: no link up, nothing to pan for (#58).
            rest = abs(bx - BUS_REST[0]) <= 30 and abs(by - BUS_REST[1]) <= 25
            if rest and not seen(context, image, LINKS["up"][0], (bx + LINKS["up"][1][0], by + LINKS["up"][1][1], *LINKS["up"][1][2:])):
                return image, (bx, by)
            # Look again after each pan. Start left of the bus, on map background.
            scroll(context, 300, 400, dx, dy)
            time.sleep(0.5)

    @staticmethod
    def read_slots(context, image, bx, by):
        """{row: (node type, routes onward or None)} for the slots linked to the bus."""
        v = image.max(axis=2)
        slots = {}
        for row in map_route.ROWS:
            node, (rx, ry, rw, rh) = LINKS[row]
            if not seen(context, image, node, (bx + rx, by + ry, rw, rh)):
                continue
            cx, cy = bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]
            marks = {mark for n, (mark, (ox, oy, w, h)) in MARKS.items() if seen(context, image, n, (cx + ox, cy + oy, w, h))}
            slots[row] = (map_route.node_type(marks), map_route.routes(v, cx, cy))
        return slots


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


@AgentServer.custom_action("Formation")
class Formation(CustomAction):
    """Re-pick the deployment order, skipping the dead, then Chain To Battle! (spec 03 section 3).

    The game keeps the last battle's picks: they are read off the cards and redone only when they differ.
    """

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
        if alive < need:
            return stop(context, f"{alive} sinners alive, team {run['team']['name']!r} stops below {need}")
        if "Details" not in text(context, image, DETAILS_BUTTON):
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
            tap(context, *CLEAR_SELECTION, wait=1.5)
            if "Reset Deployment" in text(context, screen(context), RESET_DIALOG):
                tap(context, *RESET_CONFIRM)
            if count_reaches(0):
                break
        else:
            stuck("Clear Selection did not clear the formation")
            return False
        for n, sinner in enumerate(order, 1):
            for _ in range(2):  # a tap within ~1 s of the last one can be lost
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


@AgentServer.custom_action("PlayTurn")
class PlayTurn(CustomAction):
    """Guard or Win Rate (one tap), press the START disc, check the turn plays (spec 03 section 8, 06)."""

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
        RUN["turn"] = battle.same_turn(RUN.get("turn"), turn)
        if RUN["turn"][1] > 3:
            return stuck(f"turn {turn} unchanged after 3 submits")
        guarded = False
        if RUN.get("guard", 0) > 0 and RUN["turn"][1] == 1:  # a turn submitted again plays as before #52
            guarded, image = self.guard(context, x, (dx, dy))
            if not guarded:
                log(f"turn {turn}: guard did not take, Win Rate instead")
        for _ in range(2):
            if battle.disc_lit(image, dx, dy):
                break
            # Win Rate toggles: a second tap clears the skills the first picked, so it is tapped again only
            # when its label does not show pressed: live, a tap in the turn's opening did nothing (#58).
            tap(context, x + WIN_RATE[0], y + WIN_RATE[1], wait=0)
            lit = until(context, lambda im: battle.disc_lit(im, dx, dy), timeout=1.5)
            image = screen(context) if lit is None else lit
            if lit is not None or win_rate_on(context, image, x, y):
                break
            log(f"turn {turn}: Win Rate did not take")
        if not battle.disc_lit(image, dx, dy):
            # Live 2026-10-17 (#69): a ready disc that read unlit stalled the battle. The check below tells
            # whether the press started the turn; an unready disc is not expected to (unverified live).
            log(f"turn {turn}: START reads unlit, pressing it anyway")
        tap(context, dx, dy, wait=0)
        if until(context, lambda im: seen(context, im, "BattlePause") or not seen(context, im, "BattleTurn"), timeout=3) is not None:
            if guarded:
                RUN["guard"] = battle.guard_left(RUN["guard"], guarded)
                log(f"turn {turn}: started on guard, {RUN['guard']} guard turns left")
            else:
                log(f"turn {turn}: started")
            return True
        log(f"turn {turn}: START did not start the turn")
        return True

    @staticmethod
    def guard(context, x, disc):
        """Pick every slot's guard skill: (whether the START disc lit, the screen after).

        A portrait tap swaps the slot's lower skill and its guard skill, and the game can keep the swap
        from turn to turn, so every portrait is tapped once and the lower skills compared before and
        after (the check that every slot shows its guard skill); the slots that went off guard are
        tapped back. Then one drag from the left gear through every slot's lower skill picks them
        (battle.guard_chain); no Win Rate. Live, the picked icons could not be told apart reliably
        (banners, chain and glow cover them), so the picks are not read back: the lit disc says
        every slot has a pick.
        """
        xs = battle.slot_xs(x)
        lows = [lower_x(sx) for sx in xs]
        image = lower_skills(context, lows)  # live: a battle's first turn slides the portraits in late
        before = [guard_score(image, lx) for lx in lows]
        for sx in xs:
            tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        image = lower_skills(context, lows, before)
        after = [guard_score(image, lx) for lx in lows]
        shown = battle.guard_shown(before, after)
        unsure = [i for i, s in enumerate(shown) if s is None]
        if unsure:  # live: the glow on a unit's slot flickers; swap those back and compare once more
            for i in unsure:
                tap(context, xs[i], SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
            image = lower_skills(context, [lows[i] for i in unsure], [after[i] for i in unsure])
            again = battle.guard_shown([after[i] for i in unsure], [guard_score(image, lows[i]) for i in unsure])
            for i, s in zip(unsure, again):
                shown[i] = s
        if None in shown:
            log(f"guard: cannot tell the guard skill of slots {[i + 1 for i, s in enumerate(shown) if s is None]}")
            return False, image
        for sx, on in zip(xs, shown):
            if not on:
                tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        # Live (#119): 10 px moves 10 ms apart, 0.05 s settle, no dwell: 0.7 s and 30/30 guard picks; 20 ms
        # apart with 0.3 s settle and 0.1 s dwell took 2.2 s. Twice as fast (20 px moves) picked upper skills.
        drag(context, battle.guard_chain(xs), settle=0.05, dwell=0, pause=0.01)
        lit = until(context, lambda im: battle.disc_lit(im, *disc), timeout=1.5)
        return lit is not None, screen(context) if lit is None else lit


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
            if "participating" not in text(context, screen(context), DEFEAT_TEXT):
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
            if (want in text(context, screen(context), roi)) == shown:
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
EVENT_BUTTON_LABEL = [1040, 612, 190, 66]  # the Event node's roi: empty once the event page is gone
EVENT_LEAST = 0.5  # s after a tap before the screen counts as moved: a fade's first frames are the same page


def data(name):
    return yaml.safe_load((RESOURCE / "base" / "data" / name).read_text(encoding="utf-8")) or {}


def red_button(image):
    b, g, r = image[640:650, 1080:1180].reshape(-1, 3).mean(0)
    return r > 150 and r - b > 70


@AgentServer.custom_action("Event")
class Event(CustomAction):
    """One step on an event page: press the lit button, pick a checker or an option, else advance the text (spec 03 section 10)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        tried = RUN.setdefault("event_tried", set())  # this question's options a tap did nothing on
        if red_button(image):
            tried.clear()
            tap(context, *EVENT_BUTTON, wait=0)
            Event.settle(context, image)
        elif "Choose a character" in text(context, image, CHECK_PROMPT):
            # One read per portrait: read as a row, neighbouring captions run together ("HighVery Low").
            captions = [(text(context, image, [x - 38, 605, 76, 24], only_rec=True), x) for x in EVENT_PORTRAIT_X]
            i = rewards.pick_checker(captions)
            log(f"event check: {', '.join(t for t, _ in captions) or 'no odds read'}: take {captions[i][0] if i is not None else 'the first'}")
            tap(context, captions[i][1] if i is not None else 77, EVENT_PORTRAIT_Y, wait=0)
            Event.settle(context, image)
        elif "Choices" in text(context, image, CHOICES_HEADER):
            options = [(" ".join(lines), y) for y, lines in self.rows(ocr(context, image, CHOICE_ROWS))]
            if not options:
                return True
            overrides = data("events.yaml") | {o["question"]: o["option"] for o in run["settings"]["event_overrides"]}
            story = [t for t, _ in ocr(context, image, EVENT_STORY)]
            question = next(filter(None, (run_start.match_pack(t, list(overrides)) for t in story + [" ".join(story)])), None) if overrides else None
            # Grey options (taken in an earlier round of the same questions) and ones a tap did nothing on are closed.
            closed = {k for k, (t, y) in enumerate(options) if t in tried or not rewards.choice_open(image, y)}
            i = rewards.pick_choice([t for t, _ in options], run["team"]["keyword"], overrides.get(question), closed)
            shown = " | ".join(("(closed) " if k in closed else "") + t for k, (t, _) in enumerate(options))
            if i is None:
                log(f"event: {shown}: all closed, scroll for more")
                swipe(context, 925, 520, 925, 220, wait=1.5)  # the list scrolls when it holds more than fits
                return True
            log(f"event: {shown}: take {options[i][0]!r}" + (f" (override {question!r})" if question else ""))
            tap(context, 925, options[i][1], wait=0)
            if until(context, lambda im: not Event.panel_same(image, im), timeout=1.5) is None:
                log(f"event: {options[i][0]!r} did nothing: try another")
                tried.add(options[i][0])
        else:
            tried.clear()
            # Text running on (the button grey): taps on a dead corner show it line by line; keep tapping
            # until there is something to act on, for MirrorHub's next look.
            for _ in range(EVENT_TEXT_TAPS):
                tap(context, *EVENT_NEUTRAL, wait=0.2)
                image = screen(context)
                if red_button(image) or not text(context, image, EVENT_BUTTON_LABEL) or any(k in text(context, image, roi) for k, roi in
                                            (("Choices", CHOICES_HEADER), ("Choose a character", CHECK_PROMPT))):
                    break
        return True

    @staticmethod
    def settle(context, before):
        """Wait for a tap to show on screen, at most the 1.5 s it used to wait; MirrorHub looks again after."""
        until(context, lambda im: moved(before, im), timeout=1.5, least=EVENT_LEAST)

    @staticmethod
    def panel_same(before, after):
        """Whether the choice panel looks as it did: a tap on it did nothing."""
        x, y, w, h = CHOICE_ROWS
        return recovery.same_screen(*(recovery.thumb(i[y:y + h, x:x + w]) for i in (before, after)))

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

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        order = current_run(context)["team"]["reward_cards"]
        taken = set()
        for _ in range(5):
            image = screen(context)
            if "Encounter Reward" not in text(context, image, REWARD_TITLE):
                return True  # gone (or fading in): let MirrorHub look again
            m = re.search(r"(\d)\s*/\s*(\d)", text(context, image, SELECTABLE))
            if m and m[1] == m[2]:
                tap(context, *CARD_CONFIRM, wait=0)
                until(context, lambda im: "Encounter Reward" not in text(context, im, REWARD_TITLE))
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
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        results = ocr(context, image, GIFT_CARDS)
        # The "Acquire E.G.O Gift" tab sits on each card's top-right corner, 114 px right of its centre.
        centres = sorted(x + w - 114 for t, (x, y, w, h) in results if "Acquire" in t)
        if not centres:
            return True  # page fading in or out: let MirrorHub look again
        lines = [[] for _ in centres]
        for t, (x, y, w, h) in results:
            i = min(range(len(centres)), key=lambda i: abs(centres[i] - x - w // 2))
            if abs(centres[i] - x - w // 2) < 130 and "Acquire" not in t:
                lines[i].append((y, t))
        trials = any("Mounting" in t for t, _ in results)
        risks = data("trial_risks.yaml") | {o["trial"]: o["risk"] for o in run["settings"]["trial_risk_overrides"]}
        cards = []
        for card in lines:
            gift = " ".join(t for y, t in card if y < 410)
            owned = any(re.fullmatch(r"\W*Owned\W*", t) for _, t in card)
            names = [t for y, t in card if TRIAL_NAME_Y[0] <= y < TRIAL_NAME_Y[1]]
            risk = min((rewards.trial_risk(t, risks) for t in names), default=rewards.MAX_RISK) if trials else None
            cards.append((rewards.gift_kind(gift, run["team"]["keyword"], owned), risk))
        ranked = rewards.rank_gifts(cards, run["team"]["trial_risk_weight"])
        log("gifts: " + ", ".join(k + ("" if r is None else f"/risk {r}") for k, r in cards) + f": order {ranked}")

        def pick(i):
            before = gift_count(context)
            tap(context, centres[i], 300, wait=0)
            until(context, lambda im: gift_count(context, im) != before, timeout=1.5)

        rewards.pick_gifts(ranked, lambda: gift_count(context), pick)
        for _ in range(3):
            tap(context, *GIFT_SELECT, wait=0)
            if until(context, lambda im: "Refuse" not in text(context, im, REFUSE_GIFT)) is not None:
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
PAGE_CLOSE, PAGE_OK = (490, 585), (788, 585)  # Close, and Fuse / Sell, on the fuse and sell pages
SHOP_BUTTONS = {"fuse": (295, 390), "sell": (395, 390), "heal": (197, 474)}
FUSE_CENTRE, FUSE_KEYWORD_OK = (365, 340), (788, 566)
FUSE_CELLS = [(677 + 96 * c, y) for y in (293, 385, 468) for c in range(5)]  # the third row shows half
FUSE_TOOLTIP = [600, 180, 680, 440]
FUSE_CONFIRM = [300, 150, 680, 380]  # "Selected E.G.O Gifts 3/5" over "Fuse the selected E.G.O Gifts?"
FUSE_NEUTRAL = (715, 229)  # the E.G.O Gifts Owned label: closes a tooltip, selects nothing
SELL_CELLS = [(683 + 96 * c, y) for y in (258, 365, 462) for c in range(5)]
SELL_PANEL, SELL_PRICE, SELL_COST = [150, 160, 420, 360], [500, 160, 60, 45], [960, 80, 160, 45]
HEAL_TITLE, HEAL_COST = [130, 30, 220, 45], [1100, 90, 110, 50]
HEAL_OPTIONS = {"full": (1020, 330), "revive": (1020, 455)}
SHOP_PORTRAIT_X = [98 + 77 * i for i in range(12)]  # the shop's sinner bar (step 77, not the event bar's)
BOTTOM_RIGHT = (1130, 647)  # Leave on the shop; Return, Select or Leave on the heal pages
OUTSIDE = (40, 400)  # left of every shop dialog, on nothing
LEAVE_DIALOG, LEAVE_CONFIRM, LEAVE_CANCEL = [440, 320, 400, 45], (765, 493), (515, 493)


def read_cost(context, roi=SHOP_COST):
    return number(text(context, screen(context), roi))


def kept_gifts(team):
    """Gift names the shop never fuses or sells: the team's observed gifts and every keywordless gift (#103).

    Keywordless gifts are told by name (data/gift_search.json's Keywordless tab): the tooltip names no keyword.
    """
    return [g["name"] for g in team["gift_search"]["gifts"]] + [g["en"] for g in gift_data() if g["keyword"] == "Keywordless"]


def tap_keyword(context, keyword):
    """Tap the keyword's card in an open keyword dialog; False when its label is not read."""
    label = next((b for t, b in ocr(context, screen(context), KEYWORD_LABELS) if t.strip().upper() == keyword.upper()), None)
    if label:
        x, y, w, h = label
        tap(context, x + w // 2, y - 40)
    return bool(label)


def gift_get(context):
    """Confirm the E.G.O Gift GET! popup after a purchase or a fusion."""
    for _ in range(4):
        if "GET" in text(context, screen(context), GET_TITLE):
            tap(context, *GET_CONFIRM, wait=1.5)
            return True
        time.sleep(0.5)
    return False


@AgentServer.custom_action("Shop")
class Shop(CustomAction):
    """Heal, then sell -> buy and refresh -> fuse until a round does nothing, then leave (spec 03 section 13).

    The visit's state (healed, refreshes used, keywords read, whether the owned gifts were scanned for a
    fusion) lives in RUN["shop"], so a re-entry from MirrorHub carries on; leaving drops it. Every spend keeps the team's reserve_cost.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        if not self.to_main(context):
            return True  # a page fading in or out: let MirrorHub look again
        visit = RUN.setdefault("shop", {"healed": False, "refreshes": 0, "kinds": {}, "wanted": None, "sold": False})
        if not visit["healed"]:
            self.heal(context, team)
            visit["healed"] = True
        for _ in range(shop.ROUNDS):
            acted = self.sell(context, team, visit)
            acted = self.buy(context, team, visit) or acted
            acted = self.fuse(context, team, visit) or acted
            if not acted:
                break
        else:
            log(f"shop: still acting after {shop.ROUNDS} rounds")
        for _ in range(3):
            tap(context, *BOTTOM_RIGHT, wait=1.5)
            if "Leave the shop" in text(context, screen(context), LEAVE_DIALOG):
                log(f"shop: leave with {read_cost(context)} Cost")
                tap(context, *LEAVE_CONFIRM, wait=2)
                RUN.pop("shop")
                return True
        return stuck("Leave did not bring up `Leave the shop?`")

    @staticmethod
    def to_main(context):
        """Back out of any shop page or dialog; True once the main shop (its Refresh fee) shows."""
        for _ in range(5):
            image = screen(context)
            title = text(context, image, DIALOG_TITLE)
            heal = "Heal" in text(context, image, HEAL_TITLE)
            if "GET" in text(context, image, GET_TITLE):
                tap(context, *GET_CONFIRM, wait=1.5)
            elif "Purchase" in title:
                tap(context, *PURCHASE_CANCEL)
            elif "Keyword Refresh" in title:
                tap(context, *KEYWORD_CANCEL)
            elif "Keyword Selection" in title:
                tap(context, 490, 566)  # its Cancel
            elif "Gift Info" in title:  # a bought offer tapped: only a tap outside it closes it
                tap(context, *OUTSIDE)
            elif "E.G.O Gift" in title:  # the fuse or sell page; a tooltip may cover Close
                tap(context, *FUSE_NEUTRAL)
                tap(context, *PAGE_CLOSE, wait=1.5)
            elif "Leave the shop" in text(context, image, LEAVE_DIALOG):
                tap(context, *LEAVE_CANCEL)
            elif heal:
                tap(context, *BOTTOM_RIGHT, wait=1.5)
            elif number(text(context, image, REFRESH["normal"][1])) is not None:
                return True
            else:
                time.sleep(1)
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
        image = screen(context)
        dead = [x for x in SHOP_PORTRAIT_X if saturation(image[630:680, x - 25:x + 25]).mean() < 30]
        if "alive" in RUN and 12 - RUN["alive"] != len(dead):
            log(f"shop: {12 - RUN['alive']} dead at the last formation, {len(dead)} grey portraits")
        plan = shop.heal_plan(team["heal"], cost or 0, team["reserve_cost"], len(dead), data("shop.yaml")["heal_cost"])
        log(f"shop: {cost} Cost, {len(dead)} dead, heal {team['heal']}: {plan or 'nothing'}")
        if not plan:
            return
        kind, n = plan
        for x in dead[:n] if kind == "revive" else [None]:
            tap(context, *SHOP_BUTTONS["heal"], wait=2)
            if "Heal" not in text(context, screen(context), HEAL_TITLE):
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
        """Buy each affordable main-keyword gift on show, then refresh while the rules allow; True on any spend.

        A main gift too dear for the reserve becomes visit["wanted"] for the next round's sell, and
        holds the refresh back until that sell has been tried.
        """
        keyword, reserve, acted = team["keyword"], team["reserve_cost"], False
        while True:
            if Shop.buy_one(context, keyword, reserve, visit):
                acted = True
                visit["fuse_scanned"] = False  # a new gift: the fusion grid has changed
                continue  # live: a bought offer moves to the end of the grid, so read the offers again
            if visit["wanted"] and not visit["sold"]:
                return True  # sell first, next round
            image = screen(context)
            cost = number(text(context, image, SHOP_COST))
            fees = {k: number(text(context, image, roi)) for k, (_, roi) in REFRESH.items()}
            choice = shop.refresh_choice(cost or 0, reserve, visit["refreshes"], team["shop_refresh_limit"],
                                         fees["normal"], fees["keyword"], data("shop.yaml")["refresh_margin"])
            if not choice:
                return acted
            tap(context, *REFRESH[choice][0], wait=1.5)
            if choice == "keyword":
                if not tap_keyword(context, keyword):
                    log("shop: no keyword dialog on the refresh")
                    Shop.to_main(context)
                    return acted
                tap(context, *KEYWORD_REFRESH, wait=2)
            time.sleep(1)
            after = read_cost(context)
            log(f"shop: {choice} refresh for {fees[choice]}: {cost} -> {after} Cost")
            if after == cost:
                Shop.to_main(context)
                return acted
            visit["refreshes"] += 1
            visit["sold"] = False
            acted = True

    @staticmethod
    def buy_one(context, keyword, reserve, visit):
        """Buy the first affordable main-keyword gift on show; True when one was bought.

        A gift's keyword is read from its purchase dialog (spec 03 section 12's text rule), once per name.
        """
        visit["wanted"] = None
        # ponytail: only the offers on show; a Super Shop's last 2 of 10 need a scroll first.
        for slot in shop.read_slots(ocr(context, screen(context), OFFER_GRID)):
            name, price = slot["name"], slot["price"]
            if not shop.buyable(slot) or visit["kinds"].get(name) == "other":
                continue
            cost = read_cost(context)
            tap(context, slot["x"], slot["y"] - 50, wait=1.5)
            image = screen(context)
            if "Purchase" not in text(context, image, DIALOG_TITLE):
                log(f"shop: {name!r} opened no purchase dialog")
                Shop.to_main(context)
                continue
            price = shop.dialog_price(cost, text(context, image, PURCHASE_PREVIEW)) or price
            kind = visit["kinds"].setdefault(name, rewards.gift_kind(text(context, image, PURCHASE_TEXT), keyword, False))
            if kind != "main" or not shop.can_spend(cost or 0, price, reserve):
                tap(context, *PURCHASE_CANCEL)
                if kind == "main":
                    visit["wanted"] = min(price, visit["wanted"] or price)
                log(f"shop: {name!r} {price}: {kind}" + (f", {cost} Cost is short" if kind == "main" else ""))
                continue
            tap(context, *PURCHASE, wait=2)
            gift_get(context)
            after = read_cost(context)
            log(f"shop: bought {name!r} for {price}: {cost} -> {after} Cost")
            if after == cost:
                log("shop: the Cost did not change; taking it as not bought")
                visit["kinds"][name] = "other"  # do not try it again
                Shop.to_main(context)
                continue
            return True
        return False

    @staticmethod
    def sell(context, team, visit):
        """Sell leftover non-main gifts (what fusion cannot group by 3) when a wanted main gift is too dear."""
        wanted = visit["wanted"]
        if not wanted or visit["sold"]:
            return False
        visit["sold"] = True
        tap(context, *SHOP_BUTTONS["sell"], wait=2)
        if "Sell" not in text(context, screen(context), DIALOG_TITLE):
            Shop.to_main(context)
            return False
        cost = number(text(context, screen(context), SELL_COST))
        gifts, keep = [], kept_gifts(team)
        for i, (x, y) in enumerate(SELL_CELLS):
            tap(context, x, y, wait=1.2)
            image = screen(context)
            lines = [t for t, _ in ocr(context, image, SELL_PANEL)]
            panel = " ".join(lines)
            price = number(text(context, image, SELL_PRICE))
            if any(shop.protected(t, keep) for t in lines):
                log(f"shop: sell cell {i} kept: {panel[:40]!r}")
            elif price and "Select the" not in panel and rewards.gift_kind(panel, team["keyword"], False) != "main":
                gifts.append((i, price))
        picked = shop.to_sell(gifts, wanted, cost or 0, team["reserve_cost"])
        visit["fuse_scanned"] = visit.get("fuse_scanned") and not picked
        log(f"shop: {wanted} wanted, {cost} Cost, non-main (cell, price) {gifts}: sell {picked}")
        for i in picked or []:
            before = number(text(context, screen(context), SELL_COST))
            tap(context, *SELL_CELLS[i], wait=1.2)
            tap(context, *PAGE_OK, wait=2)
            after = number(text(context, screen(context), SELL_COST))
            log(f"shop: sold cell {i}: {before} -> {after} Cost")
            if after == before:
                break  # ponytail: no Sell confirm dialog handled; none seen yet
        Shop.to_main(context)
        return bool(picked)

    @staticmethod
    def tooltip(context, last):
        """The tooltip of the cell just tapped: (its lines, its name), or ([], None) when none shows.

        Polled until a tooltip names a gift other than last: a stale read logged the same gift twice (#103).
        """
        for _ in range(8):
            time.sleep(0.2)
            lines = [(t, b) for t, b in ocr(context, screen(context), FUSE_TOOLTIP) if "Owned" not in t]
            head = next((b for t, b in lines if re.search(r"O\s*GIFT$", t)), None)
            if head:
                name = min(((b[1] - head[1], t) for t, b in lines if b[1] > head[1] + 10 and re.search(r"[a-z]{3}", t)),
                           default=(0, "?"))[1]
                if name != last:
                    return lines, name
        return [], None

    @staticmethod
    def fuse(context, team, visit):
        """Fuse 3 non-main gifts into the main keyword, Wishmaking left unticked; True when one fused.

        A tap on a gift shows its tooltip (its keyword, by spec 03 section 12's text rule) and puts it
        in the fusion, so a main gift is tapped again to take it back out. A grid that held too few
        non-main gifts is not scanned again until a purchase or a sale changes the owned gifts (#62).
        """
        if visit.get("fuse_scanned"):
            return False
        keyword = team["keyword"]
        tap(context, *SHOP_BUTTONS["fuse"], wait=2)
        if "Fuse" not in text(context, screen(context), DIALOG_TITLE):
            Shop.to_main(context)
            return False
        tap(context, *FUSE_CENTRE, wait=1.5)
        if not tap_keyword(context, keyword):
            log("shop: no keyword dialog on the fusion")
            Shop.to_main(context)
            return False
        tap(context, *FUSE_KEYWORD_OK, wait=1.5)
        if screen(context)[495:515, 263:283].max(axis=2).mean() > 60:  # unticked: V ~30
            log("shop: Wishmaking is ticked (it spends owned Starlight): no fusion")
            Shop.to_main(context)
            return False
        picked, last, keep = [], None, kept_gifts(team)
        # ponytail: the 15 cells on show; a scroll would find more when 13+ of them are main gifts.
        for x, y in FUSE_CELLS:
            tap(context, x, y, wait=0)
            lines, name = Shop.tooltip(context, last)
            tap(context, *FUSE_NEUTRAL)
            if name is None:
                continue  # an empty cell, or a tap that only closed the last tooltip
            last = name
            main = rewards.gift_kind(" ".join(t for t, _ in lines), keyword, False) == "main"
            if main or shop.protected(name, keep):
                if not main:
                    log(f"shop: {name!r} kept out of the fusion")
                tap(context, x, y, wait=1.2)  # out of the fusion again
                tap(context, *FUSE_NEUTRAL)
                continue
            picked.append(name)
            if len(picked) == 3:
                break
        fused = False
        if len(picked) == 3:
            tap(context, *PAGE_OK, wait=2)
            m = re.search(r"(\d)\s*/\s*\d", text(context, screen(context), FUSE_CONFIRM))
            if m and m[1] == "3":
                tap(context, 788, 583, wait=2.5)  # the dialog's Confirm
                fused = gift_get(context)
            log(f"shop: fuse {picked} into {keyword}: {'done' if fused else 'not confirmed'}")
        else:
            visit["fuse_scanned"] = True
            log(f"shop: {len(picked)} non-main gifts on show, a fusion takes 3")
        Shop.to_main(context)
        return fused


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
        t = text(context, image, [x + dx, y, w, h], only_rec=True).upper()
        out.append(False if "OFF" in t else True if "ON" in t else None)
    return out


@AgentServer.custom_action("Settle")
class Settle(CustomAction):
    """Goal check, weekly-bonus toggles, then Claim or GiveUpRewards; then the cursor and runs.jsonl (spec 03 section 14).

    Claim is pressed only after the toggles read back exactly as wanted; anything unexpected stops.
    """

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
        all_hard = run.get("planned", False) and run["difficulty"] == "hard" and team["hard_from_floor"] <= 1
        want = settlement.bonus_toggles(s["weekly_bonus_use"], s["weekly_bonus_amount"], hard, left or 0, all_hard)
        for _ in range(6):
            states = toggles(context, screen(context))
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
            if "Exploration Reward" not in text(context, image, REWARD_TITLE_ROI):
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
            tap(context, *GIVE_UP, wait=1.5)
            if settlement.claim_dialog(text(context, screen(context), DIALOG_TEXT)) == "giveup":
                break
        else:
            return stuck("GiveUpRewards brought up no `End expedition without claiming rewards?`")
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
