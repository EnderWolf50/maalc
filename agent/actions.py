"""Custom actions: the choices MirrorHub hands to the Agent (ADR 0002).

The Pipeline decides which screen is up; these decide what to pick on it.
Coordinates are on the 1280x720 screenshot (spec 07).
"""

import json
import re
import time
from pathlib import Path

import numpy as np
import yaml
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import battle
import map_route
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
        unaffordable = run["settings"]["run"]["starlight_unaffordable"]
        buys, missed = run_start.starlight_purchases(plan, available, unaffordable)
        for n, level, price in missed:
            log(f"grace {n} {level} costs {price}: not bought")
        if missed and unaffordable == "stop":
            log("stop: a planned grace is unaffordable")
            return False
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
        seen = None
        for _ in range(10):  # ponytail: stop when a refresh changes nothing; read `Refresh n/m` if that misfires
            cards = pack_titles(context, screen(context))
            if not cards:
                log("stop: no theme pack titles read")
                return False
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
                RUN["floor_hard"] = hard  # the map does not show it; RouteMap's weights need it
                return True
            # The arrows sit left of HARD, right of NORMAL; switching re-rolls the packs.
            log(f"floor {floor}: switch to {move.upper()}")
            tap(context, 965 if move == "hard" else 850, 46, wait=2.5)
        log(f"stop: floor {floor} difficulty did not switch to {'HARD' if want else 'NORMAL'}")
        return False


# Map page (spec 03 section 7). Offsets are from the MapBus template's top-left corner.
BUS_HOME = (446, 320)  # map panned ~70 px down from rest (bus at 446, 248): top-row badges clear the resource bar
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
        tap(context, *ENTER, wait=2)
        if not seen(context, screen(context), "MapNodePanel"):
            log("entered the node")
            return True
    log("stop: Enter on the node panel did nothing")
    return False


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
    Nothing taking a tap is a stop; stuck handling is #31.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("forfeit"):
            return forfeit(context)
        image, bus = self.find_bus(context)
        bx, by = bus or (446, 248)  # no bus found: assume the map at rest
        slots = self.read_slots(context, image, bx, by) if bus else {}
        log("map: " + (", ".join(f"{r} {t} ({'?' if n is None else n} onward)" for r, (t, n) in slots.items()) or "no linked slot read"))
        order = map_route.rank(slots, map_weights(context))

        def centre(row):
            return bx + SLOT[0], by + SLOT[1] + map_route.ROW_DY[row]

        tries = [(f"{r} {slots[r][0]}", centre(r)) for r in order]
        tries += [("the bus", (bx + 22, by + 37))] + [(f"{r} slot", centre(r)) for r in map_route.ROWS if r not in order]
        for name, (x, y) in tries:
            tap(context, x, y, wait=2)
            if seen(context, screen(context), "MapNodePanel"):
                log(f"map: take {name}")
                return enter_node(context)
        log("stop: no node on the map took a tap")
        return False

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
            # Live: pans are uneven (a slow 70 px swipe moved the map 90 px, a 55 px one 35 px),
            # so look again after each. Start left of the bus, on map background.
            swipe(context, 300, 400, 300 + int(dx * 0.78), 400 + int(dy * 0.78), ms=1000, wait=1.5)

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
        image = screen(context)
        count = participants(context, image)
        if not count:
            return True  # page fading in or out: let MirrorHub look again
        alive, need = count[1], run["team"]["min_alive"]
        RUN["alive"] = alive  # the shop's heal reads it (spec 03 section 13)
        if alive < need:
            log(f"stop: {alive} sinners alive, team {run['team']['name']!r} stops below {need}")
            return False
        if "Details" not in text(context, image, DETAILS_BUTTON):
            tap(context, 826, 125, wait=1.5)  # its » folds the details view (skills, E.G.O), which hides the order marks
            image = screen(context)
        dead = dead_sinners(image)
        if len(dead) != 12 - alive:
            log(f"formation: {12 - alive} dead by the count, grey cards {sorted(dead)}")
        order = battle.formation_order(run_start.resolve_plan(run["settings"], run["team"], "deployment_order"), dead)
        if battle.formation_matches(order_marks(context, image), order):
            log(f"formation as planned, {alive} alive")
        elif not self.pick(context, order):
            return False
        for _ in range(3):
            tap(context, *TO_BATTLE, wait=3)
            if not participants(context, screen(context)):
                return True
        log("stop: Chain To Battle! did nothing")
        return False

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
            log("stop: Clear Selection did not clear the formation")
            return False
        for n, sinner in enumerate(order, 1):
            for _ in range(2):  # a tap within ~1 s of the last one can be lost
                tap(context, *card_xy(battle.SINNERS.index(sinner), CARD_TAP_Y), wait=1.2)
                if count_reaches(n):
                    break
            else:
                log(f"stop: tapping {sinner} did not pick them")
                return False
        log(f"formation re-picked: {', '.join(order)}")
        return True


# Battle (spec 03 section 8). Offsets are from the BattleTurn (Win Rate label) template's top-left.
WIN_RATE = (20, 14)
START_DISC = (-66, 26)
TURN_NUMBER = [55, 57, 45, 30]


def disc_lit(image, x, y):
    # Lit: HSV V ~254 at the disc centre, unlit ~133 (spec 07: the START label fails on snow maps).
    return image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 200


@AgentServer.custom_action("PlayTurn")
class PlayTurn(CustomAction):
    """Win Rate, check the START disc lit (2 tries), press it, check the turn plays (spec 03 section 8, 06)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        x, y = argv.box[0], argv.box[1]
        dx, dy = x + START_DISC[0], y + START_DISC[1]
        time.sleep(1)  # taps during the turn's opening animation do nothing
        image = screen(context)
        turn = text(context, image, TURN_NUMBER, only_rec=True).strip() or None
        RUN["turn"] = battle.same_turn(RUN.get("turn"), turn)
        if RUN["turn"][1] > 3:
            log(f"stop: turn {turn} unchanged after 3 submits")
            return False
        for _ in range(2):
            if disc_lit(image, dx, dy):
                break
            # Win Rate toggles: pressed while on, it clears the skills again; hence the check first.
            tap(context, x + WIN_RATE[0], y + WIN_RATE[1], wait=1.5)
            image = screen(context)
        if not disc_lit(image, dx, dy):
            log(f"turn {turn}: START did not light")
            return True
        tap(context, dx, dy, wait=0)
        for _ in range(6):
            time.sleep(0.5)
            image = screen(context)
            if seen(context, image, "BattlePause") or not seen(context, image, "BattleTurn"):
                log(f"turn {turn}: started")
                return True
        log(f"turn {turn}: START did not start the turn")
        return True


@AgentServer.custom_action("Victory")
class Victory(CustomAction):
    """VICTORY ends the battle; it needs no tap. The encounter's retry count starts over."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if "turn" in RUN:
            log("victory")
        RUN.pop("turn", None)
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
            log("stop: retries used up")
            return False
        for _ in range(3):
            tap(context, *DEFEAT_OPTIONS[choice], wait=1.2)  # the options are cards: pick one, then Confirm
            tap(context, *DEFEAT_CONFIRM, wait=2.5)
            if "participating" not in text(context, screen(context), DEFEAT_TEXT):
                break
        else:
            log(f"stop: the DEFEAT dialog did not take {choice}")
            return False
        RUN.pop("turn", None)
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
            log(f"stop: forfeit: {want!r} did not {'show' if shown else 'go'}")
            return False
    RUN.pop("forfeit")
    log("forfeited the run")
    return True
