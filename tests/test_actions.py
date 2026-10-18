"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
import recovery


@pytest.fixture
def clock(monkeypatch):
    """A fake clock that time.sleep moves on; returns the list of sleeps."""
    now, sleeps = [1000.0], []

    def sleep(s):
        sleeps.append(s)
        now[0] += s
    monkeypatch.setattr(actions.time, "sleep", sleep)
    monkeypatch.setattr(actions.time, "monotonic", lambda: now[0])
    return sleeps


@pytest.fixture
def context(clock):
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    ctx.run_recognition.return_value = None  # OCR reads nothing, no node hits
    actions.RUN.clear()
    actions.RUN.update(settings={}, team={})  # a run plan in memory
    actions.STUCK["flag"] = None
    yield ctx
    actions.RUN.clear()
    actions.STUCK["flag"] = None


def test_a_missed_victory_does_not_carry_the_battle_clock_into_the_next_battle(context):
    # #80: the last battle ended without VICTORY being seen, its clock and turn count left behind.
    actions.RUN["battle_start"] = time.time() - recovery.BATTLE_LIMIT - 60
    actions.RUN["turn"] = (None, 3)
    actions.Formation().run(context, None)  # the next battle's formation (fading in: no count read)
    actions.PlayTurn().run(context, SimpleNamespace(box=[600, 400, 40, 20]))
    assert actions.STUCK["flag"] is None


def screens(context, values):
    """Each screenshot is a 720p image filled with the next value; the last one repeats."""
    images = [np.full((720, 1280, 3), v, np.uint8) for v in values]
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: images.pop(0) if len(images) > 1 else images[0]


def test_until_returns_the_first_screen_that_shows_the_change(context, clock):
    screens(context, [0, 0, 9, 0])
    image = actions.until(context, lambda im: im[0, 0, 0] == 9, timeout=3)
    assert image[0, 0, 0] == 9
    assert sum(clock) < 1  # polled, not a fixed wait


def test_until_gives_up_after_its_timeout(context, clock):
    screens(context, [0])
    assert actions.until(context, lambda im: False, timeout=2) is None
    assert 2 <= sum(clock) < 2.5


def test_until_waits_its_minimum_before_the_first_look(context, clock):
    screens(context, [9])
    actions.until(context, lambda im: True, timeout=2, least=0.6)
    assert sum(clock) == pytest.approx(0.6)


def test_still_waits_out_a_fade(context, clock):
    screens(context, [0, 40, 80, 120, 120])  # fading in, then still
    image = actions.still(context)
    assert image[0, 0, 0] == 120
    assert context.tasker.controller.post_screencap.call_count == 5


def test_a_formation_page_still_fading_in_is_read_once_it_is_still(context, monkeypatch):
    # Live (#58): read mid-fade, Total Participants gave 3 alive of 12.
    actions.RUN["team"] = {"min_alive": 5, "name": "t"}
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: False)
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: [])  # ends the action after the count
    screens(context, [60, 120, 120])
    reads_by_image = {60: "3/3", 120: "12/12"}

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        t = reads_by_image.get(int(image[0, 0, 0])) if roi == tuple(actions.PARTICIPANTS) else None
        return SimpleNamespace(all_results=[SimpleNamespace(text=t, box=(1125, 500, 60, 30))]) if t else None
    context.run_recognition.side_effect = run_recognition
    actions.Formation().run(context, None)
    assert actions.RUN["alive"] == 12


def test_event_text_is_tapped_through_until_the_choices_show(context):
    # The user's tip: taps on a dead corner run the text on; stop once there is something to pick.
    shots = []

    def screencap():
        shots.append(1)
        return np.full((720, 1280, 3), len(shots), np.uint8)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = screencap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        if roi == tuple(actions.CHOICES_HEADER) and image[0, 0, 0] >= 4:
            return SimpleNamespace(all_results=[SimpleNamespace(text="Choices", box=(700, 110, 100, 30))])
        if roi == tuple(actions.EVENT_BUTTON_LABEL):  # the grey button
            return SimpleNamespace(all_results=[SimpleNamespace(text="Continue", box=(1065, 625, 140, 40))])
        return None
    context.run_recognition.side_effect = run_recognition
    actions.Event().run(context, None)
    corner = [c for c in context.tasker.controller.post_click.call_args_list if c.args == actions.EVENT_NEUTRAL]
    assert len(corner) == 3


def bus_at(context, x, y, linked=()):
    """The map's bus at (x, y); the link nodes in linked hit, nothing else does."""
    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[x, y, 45, 75])
        return SimpleNamespace(hit=True) if name in linked else None
    context.run_recognition.side_effect = run_recognition


def test_a_map_not_readable_yet_is_read_again_before_any_tap(context, monkeypatch):
    # Live (#58): 2 s after a theme pack pull the hub saw a map with no bus or link to read; a fallback slot was entered.
    looks = []

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            looks.append(1)
            return SimpleNamespace(hit=True, box=[446, 248, 45, 75]) if len(looks) > 1 else None
        return SimpleNamespace(hit=True) if name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 + actions.SLOT[0], 248 + actions.SLOT[1])  # the middle row's battle


def test_a_map_at_rest_is_not_panned_when_no_link_leads_up(context):
    bus_at(context, 446, 248, linked=("MapLinkMid", "MapLinkDown"))
    _, bus = actions.RouteMap.find_bus(context)
    assert bus == (446, 248)
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_map_at_rest_is_panned_when_a_link_leads_up(context):
    # The top row's marks sit under the resource bar until the map is panned down.
    bus_at(context, 446, 248, linked=("MapLinkUp",))
    actions.RouteMap.find_bus(context)
    context.tasker.controller.post_touch_down.assert_called()


def win_rate_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == (984 + 20, 531 + 14)]


def test_a_turn_label_on_a_moving_screen_is_not_played(context):
    # Live (#58): the label matched in the first frames of a turn playing out; Win Rate and START were tapped.
    screens(context, [0, 60, 120, 180, 240, 30, 90, 150, 210, 20, 80, 140])
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    context.tasker.controller.post_click.assert_not_called()


def test_a_win_rate_tap_lost_in_the_turns_opening_is_tapped_again(context, monkeypatch):
    # Live (#58): 0.3 s after the label showed, a Win Rate tap did nothing: label not pressed, disc unlit.
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: len(win_rate_taps(context)) >= 2)
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert len(win_rate_taps(context)) == 2


def test_a_pressed_win_rate_is_not_tapped_again_while_the_disc_reads_unlit(context, monkeypatch):
    # #69: Win Rate on, the disc dim (staggered slots): a second tap would clear the picks.
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: False)
    pressed = "Battle/BattleTurnPressed.png"

    def run_recognition(name, image, override=None):
        node = (override or {}).get(name, {})
        if name == "BattleTurn" and node.get("template") == pressed and win_rate_taps(context):
            return SimpleNamespace(hit=True, box=[984, 531, 40, 29])
        return None
    context.run_recognition.side_effect = run_recognition
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert len(win_rate_taps(context)) == 1


def test_a_turn_starts_after_win_rate_lights_the_disc(context, monkeypatch):
    lit = iter([False, True])  # unlit on the turn's first look, lit after the Win Rate tap
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: next(lit, True))
    assert actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))


def reads(context, texts):
    """OCR reads texts[roi] (a list of (text, box)) in that roi, nothing elsewhere; no other node hits."""
    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in texts.get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition


def owned_gifts(context, cells=actions.FUSE_CELLS):
    """Screenshots whose cells hold a gift (a textured square); the rest stay flat."""
    image = np.zeros((720, 1280, 3), np.uint8)
    for x, y in cells:
        image[y - 30:y + 30, x - 30:x + 30] = np.random.default_rng(0).integers(0, 255, (60, 60, 3), np.uint8)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image


def cells_read(monkeypatch, *readings):
    """read_cells reads the first cells of any grid as readings [(keyword, observed gift[, tier])], tier 2 by default
    (test_shop_cells checks the reading itself on live captures)."""
    def read_cells(context, image, cells, page, gifts=()):
        return [{"i": i, "x": cells[i][0], "y": cells[i][1], "tier": (t or [2])[0], "keyword": k, "gift": g}
                for i, (k, g, *t) in enumerate(readings)]
    monkeypatch.setattr(actions, "read_cells", read_cells)


FUSE_PAGE = {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
             tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]}
SPIDERWEB = {"name": "Spiderweb Entangled in Red", "keyword": "Keywordless", "tier": 3}


def test_a_fusion_taps_only_the_materials_its_cells_show(context, monkeypatch):
    # #112: one screenshot decides; no tooltip is opened. Spiderweb (observed), Burn (main) and keywordless gifts stay.
    reads(context, FUSE_PAGE)
    cells_read(monkeypatch, ("Keywordless", SPIDERWEB["name"]), ("Bleed", None), ("Burn", None), ("Keywordless", None),
               ("Tremor", None), ("Pierce", None), ("Sinking", None), (None, None))
    actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": [SPIDERWEB]}}, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [taps.count(c) for c in actions.FUSE_CELLS[:8]] == [0, 1, 0, 0, 1, 1, 0, 0]
    assert actions.PAGE_OK in taps
    rois = [(c.args[2] or {}).get(c.args[0], {}).get("roi") for c in context.run_recognition.call_args_list]
    assert actions.FUSE_TOOLTIP not in rois


def test_offers_are_read_once_and_bought_high_tier_first_from_the_back(context, monkeypatch):
    # #76: no purchase dialog is opened to read a keyword. Burn T1 140, Bleed T2 150, Burn T2 200, Burn T3 250 with
    # 500 Cost: T3 then T2 (the T1 no longer fits), the last cell first so the other stays in place.
    offers = [("Ashes", (570, 333, 90, 17)), ("140", (600, 306, 40, 24)), ("Wound", (725, 333, 90, 17)),
              ("150", (755, 306, 40, 24)), ("Fiery", (880, 333, 90, 17)), ("200", (910, 306, 40, 24)),
              ("Dust", (1035, 333, 90, 17)), ("250", (1064, 306, 40, 24))]
    price_at = {620: 140, 775: 150, 930: 200, 1084: 250}
    costs, tapped = [500], []

    def click(x, y):
        tapped.append((x, y))
        if (x, y) == actions.PURCHASE:
            costs.append(costs[-1] - price_at[tapped[-2][0]])
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(actions.OFFER_GRID): offers, tuple(actions.SHOP_COST): [(str(costs[-1]), (560, 120, 60, 30))],
                 tuple(actions.DIALOG_TITLE): [("Purchase E.G.O Gifts", (500, 100, 260, 40))],
                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    cells_read(monkeypatch, ("Burn", None, 1), ("Bleed", None, 2), ("Burn", None, 2), ("Burn", None, 3))
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, {"keyword": "Burn", "reserve_cost": 0}, visit) == 2
    offer_taps = [t for t in tapped if t[1] == 268]
    assert offer_taps == [(1084, 268), (930, 268)]
    assert costs[-1] == 50 and visit["wanted"] is None


def test_an_offer_with_a_red_price_is_not_tapped_though_ocr_read_it_as_affordable(context, monkeypatch):
    # Live 2026-10-18: 106 Cost, Emerald Elytra's red 160 read as 16 and its Not Enough Cost tag not at all: it was
    # tapped and opened no purchase dialog. The cell's red says the Cost is short.
    image = np.zeros((720, 1280, 3), np.uint8)
    image[265 + 46:265 + 60, 778 - 15:778 + 15] = (0, 0, 200)  # the second cell's red price
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
    reads(context, {tuple(actions.OFFER_GRID): [("Emerald Elytra", (735, 333, 90, 17)), ("16", (755, 306, 40, 24))],
                    tuple(actions.SHOP_COST): [("106", (560, 120, 60, 30))]})
    cells_read(monkeypatch, ("Burn", None, 1))
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, {"keyword": "Burn", "reserve_cost": 0}, visit) == 0
    assert not context.tasker.controller.post_click.called
    assert visit["wanted"] is None


def test_a_sale_reads_keywords_and_prices_off_the_grid_and_taps_only_what_it_sells(context, monkeypatch):
    # #112: no gift is tapped to read its panel. Non-main gifts Bleed, Tremor, Pierce, Sinking: one is left over
    # from a fusion of 3, the dearest (Tremor, 120) goes.
    prices = [90, 300, 200, 120, 60, 80]
    lines = [(str(p), (x - 3, y + 37, 26, 20)) for p, (x, y) in zip(prices, actions.SELL_CELLS)]
    reads(context, {tuple(actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                    tuple(actions.SELL_COST): [("100", (980, 90, 60, 30))], tuple(actions.SELL_GRID): lines})
    cells_read(monkeypatch, ("Bleed", None), ("Burn", None), ("Keywordless", None), ("Tremor", None), ("Pierce", None),
               ("Sinking", None))
    visit = {"wanted": 180, "sold": False}
    assert actions.Shop.sell(context, {"keyword": "Burn", "reserve_cost": 0, "gift_search": {"gifts": []}}, visit)
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [c for c in taps if c in actions.SELL_CELLS] == [actions.SELL_CELLS[3]]
    rois = [(c.args[2] or {}).get(c.args[0], {}).get("roi") for c in context.run_recognition.call_args_list]
    assert actions.SELL_PANEL not in rois


def test_the_fusion_grid_is_not_scanned_again_while_the_owned_gifts_are_the_same(context):
    # The fuse page with its keyword dialog, every cell empty: no fusion this visit.
    reads(context, {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
                    tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]})
    owned_gifts(context)
    team, visit = {"keyword": "Burn", "gift_search": {"gifts": []}}, {}
    assert not actions.Shop.fuse(context, team, visit)
    taps = context.tasker.controller.post_click.call_count
    assert taps > len(actions.FUSE_CELLS)  # the grid was scanned
    assert not actions.Shop.fuse(context, team, visit)  # nothing bought or sold since
    assert context.tasker.controller.post_click.call_count == taps


def test_the_teams_observed_gift_is_kept_out_of_a_fusion(context, monkeypatch):
    # The user (#103): Spiderweb Entangled in Red, found by gift search, kept getting fused away.
    # A cell whose badge is unread falls back to its tooltip: the name keeps it.
    cells_read(monkeypatch, (None, None))
    gift = [("E.G.O GIFT", (1030, 305, 100, 25)), ("Spiderweb Entangled in Red", (1010, 340, 180, 22)),
            ("Slash damage +10%", (1000, 380, 200, 20))]
    reads = {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
             tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))], tuple(actions.FUSE_TOOLTIP): gift}

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in reads.get(roi, [])]
        return SimpleNamespace(all_results=results) if results else None
    context.run_recognition.side_effect = run_recognition
    owned_gifts(context)
    team = {"keyword": "Burn", "gift_search": {"gifts": [SPIDERWEB]}}
    assert not actions.Shop.fuse(context, team, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert taps.count(actions.FUSE_CELLS[0]) == 2  # tapped in, then out again


def test_the_shop_stops_tapping_once_the_map_shows(context):
    # Live 2026-10-18: the shop was left by hand mid-visit; its next taps opened a map node's panel.
    offers = [("Bone Stake", (575, 333, 90, 17)), ("120", (600, 306, 40, 24)),
              ("Wrist Guards", (730, 333, 90, 17)), ("130", (755, 306, 40, 24))]

    def run_recognition(name, image, override=None):
        if name == "MirrorMap":  # the map shows once anything was tapped
            return SimpleNamespace(hit=True, box=[0, 0, 10, 10]) if context.tasker.controller.post_click.called else None
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(actions.OFFER_GRID): offers, tuple(actions.SHOP_COST): [("500", (560, 120, 60, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    visit = {"wanted": None, "sold": False}
    assert not actions.Shop.buy_offers(context, {"keyword": "Burn", "reserve_cost": 0}, visit)
    assert context.tasker.controller.post_click.call_count == 1  # the second offer is never tapped


def test_only_the_filled_fusion_cells_are_tapped_and_an_unnamed_gift_comes_out_again(context):
    # Live 2026-10-18: 5 gifts owned, 10 empty cells tapped at 3.4 s each; Spiderweb read no name and stayed in.
    # Two gifts in the third row, whose badges the grid's edge cuts off: their tooltips decide.
    reads(context, FUSE_PAGE)
    owned_gifts(context, actions.FUSE_CELLS[10:12])
    assert not actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [taps.count(c) for c in actions.FUSE_CELLS] == [0] * 10 + [2, 2] + [0] * 3


def test_a_fuse_page_showing_a_fixed_recipe_is_closed_and_not_tried_again(context):
    # #103 (tests/screens/ShopFuseRecipe.png): a "Fusion Available" section pushed the owned gifts down and
    # the bot stuck on the fuse page. It is closed untouched; the owned gifts must change before another try.
    texts = {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
             tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]}

    def run_recognition(name, image, override=None):
        if name == "ShopFusionAvailable":
            return SimpleNamespace(hit=True, box=[640, 215, 150, 30])
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in texts.get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    owned_gifts(context)
    team, visit = {"keyword": "Burn", "gift_search": {"gifts": []}}, {}
    assert not actions.Shop.fuse(context, team, visit)
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert not set(taps) & set(actions.FUSE_CELLS)
    assert actions.PAGE_CLOSE in taps
    assert not actions.Shop.fuse(context, team, visit)
    assert context.tasker.controller.post_click.call_count == len(taps)


def cost_reads(context, values):
    """The shop's Cost reads each of values in turn (None: nothing read), the last one from then on."""
    def run_recognition(name, image, override=None):
        if tuple((override or {}).get(name, {}).get("roi", ())) != tuple(actions.SHOP_COST):
            return None
        t = values.pop(0) if len(values) > 1 else values[0]
        return SimpleNamespace(all_results=[SimpleNamespace(text=t, box=(560, 120, 60, 30))]) if t else None
    context.run_recognition.side_effect = run_recognition


def test_an_unread_cost_is_read_again_not_taken_as_0(context):
    # #82: one empty OCR read made the Cost 0, and the whole shop was skipped as too dear.
    cost_reads(context, [None, "33O2"])
    assert actions.read_cost(context) == 3302


def test_a_cost_that_stays_unread_is_none(context):
    cost_reads(context, [None])
    assert actions.read_cost(context) is None
    assert context.run_recognition.call_count > 1  # read again before giving up
