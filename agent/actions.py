"""Custom actions: the choices MirrorHub hands to the Agent (ADR 0002).

The Pipeline decides which screen is up; these decide what to pick on it.
Coordinates are on the 1280x720 screenshot (spec 07).
"""

import json
import re
import time
from pathlib import Path

import yaml
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import run_start
from settings import SettingsError, load_settings
from state import pick_team, read_cursor

# Same <root> as main.ROOT; resource/ sits under it in a release, under assets/ in the repo.
ROOT = Path(__file__).resolve().parent.parent
RESOURCE = next(p for p in (ROOT / "resource", ROOT / "assets" / "resource") if p.is_dir())

# This run's plan, made on the entry page: {"settings", "team", "difficulty"}.
# Memory only (ADR 0003); an agent restarted mid-run falls back to current_run's guess.
RUN = {}

WEEKLY_SLOTS = (922, 960, 998)  # x of the 3 Weekly Bonuses slots on the entry page, y 285-297
TEAM_LIST = [75, 292, 115, 245]
STARLIGHT_AVAILABLE = [1010, 30, 80, 28]
GRACE_ORIGIN_X, GRACE_ORIGIN_Y = (138, 152), (152, 390)  # top-left of card 1; step 198 px per column
PACK_TITLES = [120, 400, 1040, 100]  # up to 5 cards (live: 5 with two Theme Pack Selection +1 graces)


def log(msg):
    print(f"[maalc] {msg}", flush=True)


def screen(context):
    return context.tasker.controller.post_screencap().wait().get()


def tap(context, x, y, wait=1.0):
    context.tasker.controller.post_click(x, y).wait()
    time.sleep(wait)


def swipe(context, x1, y1, x2, y2, ms=500, wait=1.0):
    context.tasker.controller.post_swipe(x1, y1, x2, y2, ms).wait()
    time.sleep(wait)


def ocr(context, image, roi):
    """Every OCR result in roi as (text, (x, y, w, h))."""
    detail = context.run_recognition("ReadText", image, {"ReadText": {"recognition": "OCR", "roi": roi}})
    return [(r.text, tuple(r.box)) for r in (detail.all_results if detail else [])]


def text(context, image, roi):
    return " ".join(t for t, _ in ocr(context, image, roi))


def number(s):
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def address(context):
    return context.tasker.controller.info.get("adb_serial", "default")


def current_run(context):
    """The run plan; made up from settings and the rotation cursor when the agent restarted mid-run."""
    if not RUN:
        settings = load_settings(ROOT)
        difficulty = settings["run"]["difficulty"]
        difficulty = None if difficulty == "auto" else difficulty
        cursor = read_cursor(ROOT, address(context))
        team = pick_team(settings["teams"], cursor, difficulty or "hard") or pick_team(settings["teams"], cursor, "normal")
        RUN.update(settings=settings, team=team, difficulty=difficulty)
        log(f"no run plan in memory: assuming team {team['name']!r}, difficulty {difficulty or 'unknown'}")
    return RUN


@AgentServer.custom_action("Halt")
class Halt(CustomAction):
    """End the task on a screen the bot must not act on yet; the reason goes to the log."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        reason = json.loads(argv.custom_action_param or '""')
        log(f"halt at {argv.node_name}: {reason}")
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
        # ponytail: filled slots are only assumed bright; live captures so far only show empty ones (V ~5).
        weekly = sum(hsv_v[:, x:x + 30].mean() > 40 for x in WEEKLY_SLOTS)
        run = settings["run"]
        if run["stop_when_weekly_bonus_out"] and weekly == 0:
            log("stop: weekly bonuses used up")
            return False
        difficulty = run_start.run_difficulty(run["difficulty"], weekly)
        team = pick_team(settings["teams"], read_cursor(ROOT, address(context)), difficulty)
        if team is None:
            log(f"stop: no enabled team may run {difficulty}")
            return False
        RUN.clear()
        RUN.update(settings=settings, team=team, difficulty=difficulty)
        log(f"new run: {difficulty}, team {team['name']!r} (TEAMS #{team['game_team']}), weekly bonuses left {weekly}")
        tap(context, 1108, 494, wait=1.5)
        return True


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Pick the team's in-game TEAMS #N slot, check the title, press Confirm."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not RUN:
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
                swipe(context, 130, 480, 130, 340)
            elif move == "up":
                swipe(context, 130, 340, 130, 480)
            else:
                tap(context, 130, move[1], wait=1.5)
                image = screen(context)
                title = text(context, image, [220, 112, 210, 26])
                if re.search(rf"#\s*{n}\b", title):
                    bonus = number(text(context, image, [1160, 522, 60, 34]))
                    log(f"team TEAMS #{n}, Starlight Bonus {bonus}")
                    tap(context, 1145, 587, wait=2)
                    return True
        log(f"stop: could not select TEAMS #{n}")
        return False


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
            log("stop: starlight page already spends owned starlight")
            return False
        buys, missed = run_start.starlight_purchases(plan, available, run["settings"]["run"]["starlight_unaffordable"])
        for n, level, price in missed:
            log(f"grace {n} {level} costs {price}: not bought")
        for n, level, price in buys:
            x, y = grace_box(n)
            if grace_selected(image, n):
                log(f"grace {n} already selected")
                continue
            if not self.set_level(context, n, level):
                log(f"stop: could not set grace {n} to {level}")
                return False
            for _ in range(2):
                tap(context, x + 92, y + 100)
                image = screen(context)
                now = read_available(context, image)
                if now != available:
                    break
            if now is None:
                tap(context, x + 92, y + 100)  # undo: never pay with owned starlight
                log(f"stop: grace {n} would spend owned starlight")
                return False
            if now != available - price:
                log(f"stop: grace {n} {level}: Available {available} -> {now}, expected -{price}")
                return False
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
                log("stop: the graces would spend owned starlight")
                return False
            # The line under the checkbox: "Any unspent Starlight will be added ..." when off,
            # "Coverts any remaining Starlight ..." when on.
            note = text(context, image, [660, 395, 320, 90]).lower()
            on = True if "remaining" in note else False if "unspent" in note else None
            if on == want:
                tap(context, 738, 530, wait=2)
                return True
            if on is not None:
                tap(context, 727, 363)
        log("stop: could not set Convert Starlight to Cost")
        return False


@AgentServer.custom_action("PickStartingGift")
class PickStartingGift(CustomAction):
    """Open the team keyword's cabinet, take its gifts in order until Select n/m is full, press Select."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        keyword = current_run(context)["team"]["keyword"]
        if not self.full(context):
            for _ in range(3):
                image = screen(context)
                label = next((b for t, b in ocr(context, image, [145, 145, 590, 430]) if t.strip().lower() == keyword.lower()), None)
                if label:
                    break
                swipe(context, 440, 480, 440, 230)  # Pierce and Blunt sit below the fold
            else:
                log(f"stop: no {keyword} cabinet")
                return False
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
        log("stop: Select did not take the starting gift")
        return False

    @staticmethod
    def full(context):
        """Select n/m reads n == m."""
        m = re.search(r"(\d)\s*/\s*(\d)", text(context, screen(context), [990, 565, 190, 45]))
        return bool(m) and m[1] == m[2]


def theme_pack_marks(settings, team):
    data = yaml.safe_load((RESOURCE / "base" / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))
    plan = team["theme_pack_plan"]
    marks = data["default_plan"] if plan == "default" else next(p["marks"] for p in settings["theme_pack_plans"] if p["id"] == plan)
    return data["packs"] + list(marks), marks or {}


def pack_titles(context, image):
    """Cards left to right as (x centre, [text lines top to bottom]); lines within 80 px belong to one card.

    All-caps lines are CAUTION stamps or CLEAR BONUS, never a title; the LIMBUS COMPANY logo
    above the title may still slip in as the top line (run_start.match_card drops it).
    """
    lines = sorted((x + w // 2, y, t) for t, (x, y, w, h) in ocr(context, image, PACK_TITLES) if re.search(r"[a-z]", t))
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
        want = None if run["difficulty"] is None else run_start.hard_wanted(floor, run["difficulty"] == "hard", run["team"]["hard_from_floor"])
        if not self.set_difficulty(context, floor, want):
            return False

        names, marks = theme_pack_marks(run["settings"], run["team"])
        refreshed = False
        while True:
            cards = pack_titles(context, screen(context))
            if not cards:
                log("stop: no theme pack titles read")
                return False
            ranked = run_start.rank_packs([lines for _, lines in cards], names, marks)
            log(f"floor {floor} packs: " + ", ".join(f"{t} ({r})" for t, r in ranked))
            ranks = [r for _, r in ranked]
            if all(r == "avoid" for r in ranks) and not refreshed:
                refreshed = True
                tap(context, 1083, 47, wait=3)
                continue
            break
        i = run_start.pick_pack(ranks)
        x = cards[i][0]
        log(f"floor {floor}: pull {ranked[i][0]!r}")
        swipe(context, x, 330, x, 650, ms=600)
        for _ in range(8):  # the page fades out slowly; do not let MirrorHub pull twice
            if "FLOOR" not in text(context, screen(context), [480, 100, 320, 40]):
                break
            time.sleep(1)
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
                return True
            # The arrows sit left of HARD, right of NORMAL; switching re-rolls the packs.
            log(f"floor {floor}: switch to {move.upper()}")
            tap(context, 965 if move == "hard" else 850, 46, wait=2.5)
        log(f"stop: floor {floor} difficulty did not switch to {'HARD' if want else 'NORMAL'}")
        return False
