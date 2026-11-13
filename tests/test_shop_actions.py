"""The mirror's shop page actions (agent/shop_actions.py): offers, buying, selling, fusing, healing and skill replacement."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
import map_actions
import shop_actions
from test_shop import OLD_DOLL_SHOP
from agent_patch import patch_all
import test_actions

from test_actions import FUSE_PAGE, NO_GOSSYPIUM, SCREENS, SELLER, argv, buying, cells_read, fuse_slots, fusion_taps, live_shop, lost_tap_fuse_page, moved, owned_gifts, page_until, reads, sale_taps, sell_page, shop_team, taps, wants, with_ids

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def test_offers_are_read_once_and_bought_in_the_lists_order_from_the_back(context, monkeypatch):
    # #298: no purchase dialog is opened to read a keyword. Burn I 140 (9003), Bleed II 150 (9005, not wanted), Burn II
    # 200 (9009), Burn III 250 (9053) with 500 Cost; the list wants 9009, 9003, 9053 in that order: tier and price do not
    # count. 9009 then 9003 (the 9053 no longer fits), the last cell first so the other stays in place.
    offers = [("Ashes", (570, 333, 90, 17)), ("140", (600, 306, 40, 24)), ("Wound", (725, 333, 90, 17)),
              ("150", (755, 306, 40, 24)), ("Fiery", (880, 333, 90, 17)), ("200", (910, 306, 40, 24)),
              ("Dust", (1035, 333, 90, 17)), ("250", (1064, 306, 40, 24))]
    price_at = {620: 140, 775: 150, 930: 200, 1084: 250}
    costs, tapped = [500], []

    def click(x, y):
        tapped.append((x, y))
        if (x, y) == shop_actions.PURCHASE:
            costs.append(costs[-1] - price_at[tapped[-2][0]])
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(shop_actions.OFFER_GRID): offers, tuple(shop_actions.SHOP_COST): [(str(costs[-1]), (560, 120, 60, 30))],
                 tuple(shop_actions.DIALOG_TITLE): [("Purchase E.G.O Gifts", (500, 100, 260, 40))],
                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    cells_read(monkeypatch, ("Burn", 1, 9003), ("Bleed", 2, 9005), ("Burn", 2, 9009), ("Burn", 3, 9053))
    visit = {"wanted": None, "sold": False}
    assert shop_actions.Shop.buy_offers(context, buying(wants(9009, 9003, 9053)), visit) == 2
    offer_taps = [t for t in tapped if t[1] == 268]
    assert offer_taps == [(930, 268), (620, 268)]
    assert costs[-1] == 160 and visit["wanted"] is None


def test_a_glyph_on_an_offers_icon_opens_no_purchase_dialog(context, monkeypatch):
    # #216, live 2026-10-22: a "3" read in Old Wooden Doll's icon corner made a slot priced 3 named '214' whose cell
    # (read_cells found no badge) was opened to read its keyword. Skill slot first, the glyph, four gifts.
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    reads(context, {tuple(shop_actions.OFFER_GRID): OLD_DOLL_SHOP, tuple(shop_actions.SHOP_COST): [("787", (560, 120, 60, 30))]})
    cells_read(monkeypatch, ("Burn", 2), ("Bleed", 2), ("Pierce", 2), ("Blunt", 2))
    visit = {"wanted": None, "sold": False}
    assert shop_actions.Shop.buy_offers(context, buying(wants(9009)), visit) == 0
    assert not context.tasker.controller.post_click.called  # no cell opened to read its keyword
    assert visit["wanted"] is None


def test_an_offer_with_a_red_price_is_not_tapped_though_ocr_read_it_as_affordable(context, monkeypatch):
    # Live 2026-10-18: 106 Cost, Emerald Elytra's red 160 read as 16 and its Not Enough Cost tag not at all: it was
    # tapped and opened no purchase dialog. The cell's red says the Cost is short.
    image = np.zeros((720, 1280, 3), np.uint8)
    image[265 + 46:265 + 60, 778 - 15:778 + 15] = (0, 0, 200)  # the second cell's red price
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
    reads(context, {tuple(shop_actions.OFFER_GRID): [("Emerald Elytra", (735, 333, 90, 17)), ("16", (755, 306, 40, 24))],
                    tuple(shop_actions.SHOP_COST): [("106", (560, 120, 60, 30))]})
    cells_read(monkeypatch, ("Burn", 1, 9003))
    visit = {"wanted": None, "sold": False}
    assert shop_actions.Shop.buy_offers(context, buying(wants(9003)), visit) == 0
    assert not context.tasker.controller.post_click.called
    assert visit["wanted"] is None


@pytest.mark.parametrize("team, leftover, sold", [
    ({}, 5, False),  # a tier V no fusion takes (pick_fusion never does) is not sold by default
    ({"sell_max_tier": 5}, 5, True),
    ({"sell_max_tier": 2}, 3, False),  # a tier III leftover is over a lower limit
    ({"sell_max_tier": 3}, 3, True),
])
def test_a_sale_stops_at_the_teams_highest_tier(context, monkeypatch, team, leftover, sold):
    # #161: three tier II fuse; the fourth, the leftover, would cover the price.
    taps = sale_taps(context, monkeypatch, team, [90, 60, 70, 300], ("Bleed",), ("Tremor",),
                     ("Pierce",), ("Slash", leftover))
    assert taps == ([shop_actions.SELL_CELLS[3]] if sold else [])


@pytest.mark.parametrize("team, sold", [({}, False), ({"sell_vestiges": True}, True),
                                        ({"sell_vestiges": True, "sell_max_tier": 1}, True)])
def test_a_vestige_is_sold_only_when_the_team_allows_it(context, monkeypatch, team, sold):
    # #161: sell_vestiges alone decides (the list lets Dark Vestige go).
    taps = sale_taps(context, monkeypatch, team, [90, 60, 70, 95], ("Bleed",),
                     ("Tremor",), ("Pierce",), ("Keywordless", 1, 9991))
    assert taps.count(shop_actions.SELL_CELLS[3]) == int(sold)


def test_a_vestige_over_the_highest_tier_sold_stays(context, monkeypatch):
    # #161: sell_max_tier applies to vestiges too; a Twinkling Vestige (III) over a limit of II is not sold.
    taps = sale_taps(context, monkeypatch, {"sell_vestiges": True, "sell_max_tier": 2}, [90, 60, 70, 95],
                     ("Bleed",), ("Tremor",), ("Pierce",), ("Keywordless", 3, 9993))
    assert taps == []


def test_nothing_is_sold_when_every_material_fuses(context, monkeypatch):
    # #79: 3 materials make a fusion; a sale would only break it.
    assert sale_taps(context, monkeypatch, {}, [90, 60, 70], ("Bleed",), ("Tremor",), ("Pierce",)) == []


def test_a_sale_counts_the_fusion_materials_it_may_not_sell(context, monkeypatch):
    # #79: a vestige the team does not sell is still fusion material: Bleed and Tremor fuse with it, so neither is sold.
    taps = sale_taps(context, monkeypatch, {}, [90, 95, 60], ("Bleed",), ("Tremor",), ("Keywordless", 1, 9991))
    assert taps == []


@pytest.mark.parametrize("condition, sold", [("any", 3), ("upgrade", 0), ("tier4", 0)])
def test_a_sale_counts_only_the_fusions_the_condition_makes(context, monkeypatch, condition, sold):
    # #263: four tier I (9 points: a I, no upgrade, no IV). By "any" three fuse and the fourth, the 90 that covers
    # the price, goes; by the others none fuses, so the dearest (300) goes.
    taps = sale_taps(context, monkeypatch, {"fusion_condition": condition}, [300, 60, 70, 90],
                     *[(k, 1) for k in ("Bleed", "Tremor", "Pierce", "Slash")])
    assert taps == [shop_actions.SELL_CELLS[sold]]


@pytest.mark.parametrize("slots, condition, sells", [
    (None, "any", 3), (5, "any", 3),
    (None, "tier4", 0), (3, "tier4", 0), (5, "tier4", 3),
    (None, "upgrade", 0), (3, "upgrade", 0), (5, "upgrade", 3),
])
def test_a_sale_groups_by_the_slots_and_thresholds_of_the_shop(context, monkeypatch, slots, condition, sells):
    # #263: III + III + I is 23 points: a III in a shop, a IV in a Super Shop. Where the condition refuses it (tier4 and
    # upgrade in a shop) nothing fuses and the dearest gift (cell 0, 300) goes; where it holds, the Bleed I left over (cell
    # 3, 90) does. A visit that read no fuse page counts a shop's 3 slots.
    taps = sale_taps(context, monkeypatch, {"fusion_condition": condition}, [300, 60, 70, 90],
                     ("Bleed", 3), ("Tremor", 3), ("Pierce", 1), ("Slash", 1), slots=slots)
    assert taps == [shop_actions.SELL_CELLS[sells]]


@pytest.mark.parametrize("slots, condition, made", [
    (3, "any", True), (5, "any", True), (3, "upgrade", False), (5, "upgrade", True), (3, "tier4", False), (5, "tier4", True),
])
def test_a_fusion_reads_the_tier_by_the_shop_it_is_in(context, monkeypatch, slots, condition, made):
    # #263: III + III + I (23 points) is a III in a shop and a IV in a Super Shop.
    fused, taps, _ = fusion_taps(context, monkeypatch, {"fusion_condition": condition}, ("Bleed", 3),
                                 ("Tremor", 3), ("Pierce", 1), slots=slots)
    assert fused == made and taps == [int(made)] * 3


def test_a_shop_visit_counts_a_super_shops_five_slots_from_its_red_title(context, monkeypatch):
    # #263: before any fuse page was read, the sale already groups by the Super Shop's table.
    actions.RUN["team"] = shop_team({"heal": "none"})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))
    seen = []

    def sell(context, team, visit):
        seen.append(visit["slots"])
        raise actions.PageGone("Shop")  # ends the visit here: what sell saw is what is asked
    monkeypatch.setattr(shop_actions.Shop, "sell", staticmethod(sell))
    for name in ("Shop", "SuperShop"):
        actions.RUN.pop("shop", None)
        image = np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]
        context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
        assert shop_actions.Shop().run(context, argv())
    assert seen == [3, 5]


def test_a_sale_does_not_break_a_fusion_by_selling_white_gossypium(context, monkeypatch):
    # #79, #90: White Gossypium is sold first, so the fusion is grouped without it: Tremor, Pierce and Sinking fuse.
    # Its 50 alone does not cover the price: nothing is sold (grouped with it, Sinking would go too, and no fusion).
    taps = sale_taps(context, monkeypatch, {"allow_white_gossypium": False}, [50, 60, 70, 80], ("Bleed", 1, 9020),
                     ("Tremor", 1), ("Pierce", 1), ("Sinking", 1))
    assert taps == []


def test_a_sale_confirms_the_sell_dialog(context, monkeypatch):
    # #174 (live 2026-10-19): Sell asked "Sell [Today's Expression] for 95 Cost?" and the bot cancelled it.
    taps = live_shop(context, sell_page(lambda taps: actions.DIALOG_CONFIRM in taps))
    cells_read(monkeypatch, *with_ids([("Bleed",)]))
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    assert shop_actions.Shop.sell(context, SELLER, {"wanted": 145, "sold": False})
    assert taps.index(shop_actions.SELL_CELLS[0]) < taps.index(shop_actions.PAGE_OK) < taps.index(actions.DIALOG_CONFIRM)
    assert "shop: sold cell 0 for 95: 51 -> 146 Cost" in logs


def test_the_cost_preview_of_a_picked_cell_is_not_a_sale(context, monkeypatch):
    # #174: the picked cell's "51 > 146" read as 51146, and the bot took the Cost as changed: sold.
    live_shop(context, sell_page(lambda taps: False))
    cells_read(monkeypatch, *with_ids([("Bleed",)]))
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    shop_actions.Shop.sell(context, SELLER, {"wanted": 145, "sold": False})
    assert any("not sold" in line for line in logs)
    assert not any("sold cell" in line for line in logs)


def test_a_keyword_refresh_waits_for_the_new_cost_not_a_fixed_time(context, clock):
    # Live 2026-10-19: a keyword refresh slept 1.5 + 1 + 2 + 1 s; the screen stops 0.5-0.6 s after OK.
    def reads_now(taps):
        cost = "410" if shop_actions.KEYWORD_REFRESH in taps else "500"
        return {tuple(shop_actions.SHOP_COST): [(cost, (560, 120, 60, 30))],
                tuple(shop_actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                tuple(shop_actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))],
                tuple(shop_actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]}
    taps = live_shop(context, reads_now)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    assert shop_actions.Shop.buy(context, buying(wants(9053), shop_refresh_keyword=1), visit)
    assert visit["refreshes"] == {"keyword": 1, "normal": 0} and taps == [shop_actions.REFRESH["keyword"][0], (330, 360), shop_actions.KEYWORD_REFRESH]
    assert sum(clock) < 1.5


def test_a_keyword_refresh_checks_the_page_before_its_first_tap(context, clock, monkeypatch):
    # #118 (ADR 0007): the shop gone after its Cost was read, the refresh's first tap does not go out.
    def gone(context, home, image=None):
        raise actions.PageGone(home)
    patch_all(monkeypatch, "page_guard", gone)
    taps = live_shop(context, lambda taps: {tuple(shop_actions.SHOP_COST): [("500", (560, 120, 60, 30))],
                                            tuple(shop_actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                                            tuple(shop_actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))]})
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    with pytest.raises(actions.PageGone):
        shop_actions.Shop.buy(context, buying(wants(9053), shop_refresh_keyword=1), visit)
    assert taps == []


def test_the_leave_dialog_is_read_with_its_spaces_dropped(context, clock, monkeypatch):
    # #160: OCR drops spaces ("LEAVE THESHOP?"); has() compacts both sides, as main's Leave does.
    actions.RUN["team"] = shop_team({"heal": "none"})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(shop_actions.Shop, step, staticmethod(lambda *a: False))
    taps = live_shop(context, lambda taps: {tuple(shop_actions.LEAVE_DIALOG): [("LEAVE THESHOP?", (480, 325, 300, 35))]}
                     if taps else {})
    assert shop_actions.Shop().run(context, argv())
    assert shop_actions.LEAVE_CONFIRM in taps and actions.STUCK["flag"] is None


def test_a_team_without_white_gossypium_fuses_it_first(context, monkeypatch):
    # #90: a Bleed team that does not hold it: its icon makes it material, ahead of the other materials.
    reads(context, {**FUSE_PAGE, tuple(shop_actions.KEYWORD_LABELS): [("Bleed", (300, 400, 60, 20))]})
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, *with_ids([("Burn",), ("Tremor",), ("Pierce",)]), ("Bleed", 2, 9020), ("Bleed", 2, 9005))
    shop_actions.Shop.fuse(context, NO_GOSSYPIUM, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [taps.count(c) for c in shop_actions.FUSE_CELLS[:5]] == [1, 1, 0, 1, 0]


def test_a_team_without_white_gossypium_does_not_buy_it(context, monkeypatch):
    # #90: White Gossypium is a Bleed gift; the Bleed team buys the other Bleed offer only.
    offers = [("White Gossypium", (570, 333, 90, 17)), ("140", (600, 306, 40, 24)),
              ("Wound Clerid", (725, 333, 90, 17)), ("150", (755, 306, 40, 24))]
    costs, tapped = [500], []

    def click(x, y):
        tapped.append((x, y))
        if (x, y) == shop_actions.PURCHASE:
            costs.append(costs[-1] - 150)
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(shop_actions.OFFER_GRID): offers, tuple(shop_actions.SHOP_COST): [(str(costs[-1]), (560, 120, 60, 30))],
                 tuple(shop_actions.DIALOG_TITLE): [("Purchase E.G.O Gifts", (500, 100, 260, 40))],
                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    cells_read(monkeypatch, ("Bleed", 2, 9020), ("Bleed", 2, 9005))
    assert shop_actions.Shop.buy_offers(context, NO_GOSSYPIUM, {"wanted": None, "sold": False}) == 1
    assert [t for t in tapped if t[1] == 268] == [(775, 268)]


def test_a_fusion_puts_in_the_materials_that_make_the_highest_tier(context, monkeypatch):
    # #77: III + III + II make a tier IV; the three I would make only a tier I, made after it on the same page (#378): with
    # cells 1, 3 and 4 gone they are cells 0-2.
    fused, _, ok = fusion_taps(context, monkeypatch, {}, ("Bleed", 1), ("Bleed", 3), ("Pierce", 1),
                               ("Tremor", 2), ("Slash", 3), ("Sinking", 1))
    cells = [t for t in taps(context) if t in shop_actions.FUSE_CELLS]
    assert fused and ok and sorted(cells[:3]) == sorted(shop_actions.FUSE_CELLS[i] for i in (1, 3, 4))
    assert sorted(cells[3:]) == sorted(shop_actions.FUSE_CELLS[:3])


@pytest.mark.parametrize("condition, made", [(None, True), ("any", True), ("upgrade", False), ("tier4", False)])
def test_the_fusion_condition_decides_whether_three_tier_i_fuse(context, monkeypatch, condition, made):
    # #263: three I make a tier I (9 points): no upgrade, no IV. A team with no fusion_condition fuses as before.
    team = {"fusion_condition": condition} if condition else {}
    fused, taps, ok = fusion_taps(context, monkeypatch, team, *[("Bleed", 1)] * 3)
    assert (fused, ok, taps) == (made, made, [int(made)] * 3)


@pytest.mark.parametrize("condition, taps", [("any", [1, 1, 1]), ("upgrade", [0, 0, 0]), ("tier4", [0, 0, 0])])
def test_the_fusion_condition_on_a_tier_iii_that_makes_a_tier_iii(context, monkeypatch, condition, taps):
    # #263: III + II + I is 19 points: a tier III, no better than its III.
    fused, tapped, _ = fusion_taps(context, monkeypatch, {"fusion_condition": condition},
                                   ("Bleed", 3), ("Tremor", 2), ("Pierce", 1))
    assert fused == (condition == "any") and tapped == taps


@pytest.mark.parametrize("condition", ["any", "upgrade", "tier4"])
def test_the_fusion_condition_lets_an_upgrade_to_tier_iv_through(context, monkeypatch, condition):
    # #263: III + III + II is 26 points: a tier IV, over its III.
    fused, taps, ok = fusion_taps(context, monkeypatch, {"fusion_condition": condition},
                                  ("Bleed", 3), ("Tremor", 3), ("Pierce", 2))
    assert fused and ok and taps == [1, 1, 1]


def test_the_upgrade_condition_picks_the_group_that_is_one(context, monkeypatch):
    # #263: IV + II + II is the most (a IV), no upgrade of its IV; II + II + II (a III) is.
    fused, taps, _ = fusion_taps(context, monkeypatch, {"fusion_condition": "upgrade"},
                                 ("Bleed", 4), ("Tremor", 2), ("Pierce", 2), ("Slash", 2))
    assert fused and taps == [0, 1, 1, 1]


def test_a_refused_fusion_is_not_read_again_until_the_owned_gifts_change(context, monkeypatch):
    # #263: the same as a grid that makes none (#62).
    visit = {}
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, *with_ids([("Bleed", 1)] * 3))
    assert not shop_actions.Shop.fuse(context, shop_team({"fusion_condition": "tier4"}), visit)
    assert visit["fuse_scanned"]


def test_a_super_shop_fuses_up_to_5(context, monkeypatch):
    # #77: 5 tier I make a tier III by the Super Shop's thresholds; its confirm dialog reads 5/5.
    fused, taps, _ = fusion_taps(context, monkeypatch, {}, *[("Bleed", 1)] * 5, slots=5, confirm=5)
    assert fused and taps == [1] * 5


def test_a_material_that_does_not_show_in_the_fusion_closes_the_page(context, monkeypatch):
    # #77: the second tap put nothing in (or another gift): Close, no Fuse, and not the same scan again.
    visit = {}
    lost_tap_fuse_page(context, monkeypatch)
    assert not shop_actions.Shop.fuse(context, shop_team({}), visit)
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert shop_actions.PAGE_OK not in taps and shop_actions.PAGE_CLOSE in taps
    assert [taps.count(c) for c in shop_actions.FUSE_CELLS[:3]] == [1, 2, 0]  # stopped at the second, tapped again once (#611)
    assert visit["fuse_scanned"]


def test_a_fusion_is_not_confirmed_when_the_dialog_counts_other_materials(context, monkeypatch):
    fused, _, ok = fusion_taps(context, monkeypatch, {}, *[("Bleed",)] * 3, confirm=2)
    assert ok and not fused


def test_the_fusion_grid_is_not_scanned_again_while_the_owned_gifts_are_the_same(context, monkeypatch):
    # The fuse page with its keyword dialog, no materials: no fusion this visit.
    reads(context, FUSE_PAGE)
    scans = []
    patch_all(monkeypatch, "owned_cells", lambda *a: scans.append(a) or ([], {"page": "fuse", "at": 0}))
    team, visit = shop_team({}), {}
    assert not shop_actions.Shop.fuse(context, team, visit)
    taps = context.tasker.controller.post_click.call_count
    assert len(scans) == 1
    assert not shop_actions.Shop.fuse(context, team, visit)  # nothing bought or sold since
    assert context.tasker.controller.post_click.call_count == taps and len(scans) == 1


def test_the_shop_stops_tapping_once_the_map_shows(context, monkeypatch):
    # Live 2026-10-18: the shop was left by hand mid-visit; its next taps opened a map node's panel.
    cells_read(monkeypatch, ("Burn", 1, 9003), ("Burn", 1, 9087))
    offers = [("Bone Stake", (575, 333, 90, 17)), ("120", (600, 306, 40, 24)),
              ("Wrist Guards", (730, 333, 90, 17)), ("130", (755, 306, 40, 24))]

    def run_recognition(name, image, override=None):
        if name == "MirrorMap":  # the map shows once anything was tapped
            return SimpleNamespace(hit=True, box=[0, 0, 10, 10]) if context.tasker.controller.post_click.called else None
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(shop_actions.OFFER_GRID): offers, tuple(shop_actions.SHOP_COST): [("500", (560, 120, 60, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    visit = {"wanted": None, "sold": False}
    assert not shop_actions.Shop.buy_offers(context, buying(wants(9003, 9087)), visit)
    assert context.tasker.controller.post_click.call_count == 1  # the second offer is never tapped


def cost_reads(context, values):
    """The shop's Cost reads each of values in turn (None: nothing read), the last one from then on."""
    def run_recognition(name, image, override=None):
        if tuple((override or {}).get(name, {}).get("roi", ())) != tuple(shop_actions.SHOP_COST):
            return None
        t = values.pop(0) if len(values) > 1 else values[0]
        return SimpleNamespace(all_results=[SimpleNamespace(text=t, box=(560, 120, 60, 30))]) if t else None
    context.run_recognition.side_effect = run_recognition


def test_an_unread_cost_is_read_again_not_taken_as_0(context):
    # #82: one empty OCR read made the Cost 0, and the whole shop was skipped as too dear.
    cost_reads(context, [None, "33O2"])
    assert shop_actions.read_cost(context) == 3302


def test_a_cost_that_stays_unread_is_none(context):
    cost_reads(context, [None])
    assert shop_actions.read_cost(context) is None
    assert context.run_recognition.call_count > 1  # read again before giving up


def test_a_fusion_taps_no_cell_once_the_shop_is_gone(context, guarded):
    # Live 2026-10-18: the shop left by hand mid-visit; its taps went on onto the map for ~50 s.
    reads(context, FUSE_PAGE)
    owned_gifts(context, shop_actions.FUSE_CELLS[10:12])
    page_until(context, "Shop", 4)  # gone after Fuse, the centre, Burn and its OK
    with pytest.raises(actions.PageGone):
        shop_actions.Shop.fuse(context, shop_team({}), {})
    assert not set(taps(context)) & set(shop_actions.FUSE_CELLS)


def test_a_shop_visit_left_by_hand_is_handed_back_and_forgotten_at_the_next_node(context, guarded, monkeypatch):
    actions.RUN["team"] = shop_team({"heal": "none"})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))
    monkeypatch.setattr(shop_actions.Shop, "sell", staticmethod(lambda *a: False))
    monkeypatch.setattr(shop_actions.Shop, "buy", staticmethod(lambda *a: actions.page_guard(context, "Shop")))
    assert shop_actions.Shop().run(context, argv())  # the shop is gone: True for MirrorHub, not a stuck
    assert actions.STUCK["flag"] is None and "shop" in actions.RUN
    assert actions.RUN["after_shop"]  # #279: the page handled last, so RouteMap's one node is the boss
    map_actions.enter_node(context)
    assert "shop" not in actions.RUN and "after_shop" not in actions.RUN


def test_a_shop_gone_before_leave_is_handed_back_not_stuck(context, guarded, monkeypatch):
    actions.RUN["team"] = shop_team({"heal": "none"})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(shop_actions.Shop, step, staticmethod(lambda *a: False))
    assert shop_actions.Shop().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


@pytest.mark.parametrize("step, visit", [("sell", {"wanted": 100, "sold": False}), ("fuse", {})])
def test_a_shop_gone_before_the_sell_or_fuse_button_taps_nothing(context, guarded, step, visit):
    with pytest.raises(actions.PageGone):
        getattr(shop_actions.Shop, step)(context, shop_team({"heal": "none"}), visit)
    assert moved(context) == 0


def test_a_heal_handed_back_mid_way_is_not_paid_again(context, monkeypatch):
    actions.RUN["team"] = shop_team({"heal": "full"})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))

    def heal(context, team):
        raise actions.PageGone("Shop")  # the heal page left by hand, or a popup over it
    monkeypatch.setattr(shop_actions.Shop, "heal", staticmethod(heal))
    assert shop_actions.Shop().run(context, argv())
    assert actions.RUN["shop"]["healed"]


def test_a_fusion_gone_after_a_cell_tap_taps_nothing_more(context, guarded, monkeypatch):
    # The first material went in; with the shop gone then, the next material does not go out.
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, *with_ids([("Bleed",), ("Tremor",), ("Pierce",)]))
    page_until(context, "Shop", 5)  # gone after Fuse, the centre, Burn, its OK and the first cell (no tooltip: no neutral tap, #378)
    with pytest.raises(actions.PageGone):
        shop_actions.Shop.fuse(context, shop_team({}), {})
    taps_made = [t for t in taps(context) if t != shop_actions.FUSE_NEUTRAL]
    assert taps_made[4] in shop_actions.FUSE_CELLS and not set(taps_made[5:]) & set(shop_actions.FUSE_CELLS)
