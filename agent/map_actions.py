"""The mirror's map: entering a node, routing the floor, and forfeiting the run."""

import re
import time

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import map_route
import recovery
import settlement
from actions import (ROOT, RUN, back, box_centre, current_run, data, hands_back, leave_shop, log, number, on_map,
                     page_guard, run_continued, saturation, screen, scroll, seen, still, stuck, tap, tap_shown,
                     tap_then, text, until)
from ocrtext import floor_number, has


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
ENTER = (1133, 543)
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
    until(context, lambda im: not on_map(context, im), timeout=2)
    RUN["forfeited"] = RUN.pop("forfeit")  # why, for the forfeits in a row Settle counts
    log("forfeited the run")
    return True
