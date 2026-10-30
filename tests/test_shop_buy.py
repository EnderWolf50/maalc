"""Shop.buy and Shop.buy_offers: what the shop buys off the team's gift list (#298); the reading of cells is test_shop_cells."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
import gifts
import test_actions
from settings import gift_tables
from test_actions import NO_GOSSYPIUM, OLD_DOLL_SHOP, buying, cells_read, live_shop, reads, wants

clock, context = test_actions.clock, test_actions.context  # its fixtures


def plates_read(monkeypatch, *ids):
    """read_plates reads the name plates of the offers as ids (None: unread); test_gift_cells reads real ones (#329)."""
    def read_plates(context, image, centres):
        assert len(centres) == len(ids)  # one plate per slot, on the slot's own cell
        return [{"text": f"plate {i}", "id": i} for i in ids]
    monkeypatch.setattr(actions, "read_plates", read_plates)


def shelf(context, prices, cost, short=(), purchased=()):
    """A shop showing offers priced prices (the first four in a row), `cost` Cost, those of index `short` tagged Not Enough Cost
    and those of `purchased` Purchased;
    a purchase takes its price off the Cost. The offer cells tapped are in the list returned."""
    xs = [570, 725, 880, 1035]
    lines = [r for x, p in zip(xs, prices) for r in [("Gift", (x, 333, 90, 17)), (str(p), (x + 30, 306, 40, 24))]]
    lines += [("Not Enough Cost", (xs[i] + 10, 260, 80, 17)) for i in short]
    lines += [("Purchased", (xs[i] + 10, 260, 80, 17)) for i in purchased]
    costs, tapped = [cost], []

    def click(x, y):
        tapped.append((x, y))
        if (x, y) == actions.PURCHASE:
            costs.append(costs[-1] - prices[max(i for i, c in enumerate(xs) if c - 30 < tapped[-2][0])])
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        shown = {tuple(actions.OFFER_GRID): lines, tuple(actions.SHOP_COST): [(str(costs[-1]), (560, 120, 60, 30))],
                 tuple(actions.DIALOG_TITLE): [("Purchase E.G.O Gifts", (500, 100, 260, 40))],
                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in shown]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    return [t for t in tapped if t[1] == 268]


def test_an_offer_too_dear_is_skipped_for_the_next_in_the_queue_with_the_reserve_kept(context, monkeypatch):
    # #298: queue 9053, 9009, 9003 priced 150, 200, 120 on a 400 Cost with 100 reserve: 9053 fits (250 left), 9009 would
    # leave 50, 9003 leaves 130.
    shelf(context, [150, 200, 120], 400)
    cells_read(monkeypatch, ("Burn", 3, 9053), ("Burn", 2, 9009), ("Burn", 1, 9003))
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9009, 9003), reserve_cost=100), {"wanted": None, "sold": False}) == 2
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [880 + 50, 620]


def test_gifts_of_one_tier_are_bought_in_the_queue_order_not_the_cheaper_first(context, monkeypatch):
    # #298: 9053 and 9071 are both Burn III; the list puts the dearer 9053 first and 300 Cost holds only one of them.
    shelf(context, [250, 100], 300)
    cells_read(monkeypatch, ("Burn", 3, 9071), ("Burn", 3, 9053))
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9071)), {"wanted": None, "sold": False}) == 1
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [775]


def test_an_offer_the_shop_cannot_tell_is_not_bought(context, monkeypatch):
    # #298: an id the icon match did not find (a gift the table lacks, a covered cell) is kept, not bought.
    shelf(context, [100, 90], 500)
    cells_read(monkeypatch, ("Burn", 3), ("Burn", 3, 9053))
    assert actions.Shop.buy_offers(context, buying(wants(9053)), {"wanted": None, "sold": False}) == 1
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [775]


def test_the_first_in_the_queue_too_dear_is_sold_for_before_anything_is_bought(context, monkeypatch):
    # #298: 9053 is first and costs 300 on a 250 Cost; 9003 (120) would fit but waits for the sale. Once the sale was tried
    # (visit["sold"]), 9003 is bought.
    shelf(context, [300, 120], 250, short=[0])
    cells_read(monkeypatch, ("Burn", 3, 9053), ("Burn", 1, 9003))
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003)), visit) == 0 and visit["wanted"] == 300
    visit = {"wanted": None, "sold": True}
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003)), visit) == 1 and visit["wanted"] is None


def test_a_dimmed_offer_is_told_by_its_plate_and_sold_for_when_it_is_the_first(context, monkeypatch):
    # #329: a Not Enough Cost offer is dimmed, its tier and icon unread (id None); its name plate still reads. The plate
    # says 9053, first of the queue: sell first, buy nothing.
    shelf(context, [300, 120], 250, short=[0])
    cells_read(monkeypatch, ("Burn", None), ("Burn", 1, 9003))
    plates_read(monkeypatch, 9053, 9003)
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003)), visit) == 0 and visit["wanted"] == 300


def test_a_dimmed_offer_that_is_not_wanted_or_unread_holds_nothing_back(context, monkeypatch):
    # #329: the plate says 9005 (Bleed II, not wanted); the badge alone no longer stands for the first Burn gift (#298's guess).
    shelf(context, [300, 120], 250, short=[0])
    cells_read(monkeypatch, ("Burn", None), ("Burn", 1, 9003))
    plates_read(monkeypatch, 9005, 9003)
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003)), visit) == 1 and visit["wanted"] is None
    # an unread plate on a dimmed Burn badge: unknown, not guessed to be 9053
    shelf(context, [300, 120], 250, short=[0])
    plates_read(monkeypatch, None, 9003)
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003)), visit) == 1 and visit["wanted"] is None


def test_the_plate_names_a_gift_the_icon_could_not(context, monkeypatch):
    # #329: the icon is unread, the plate reads 9053: bought.
    shelf(context, [100], 500)
    cells_read(monkeypatch, ("Burn", 3))
    plates_read(monkeypatch, 9053)
    assert actions.Shop.buy_offers(context, buying(wants(9053)), {"wanted": None, "sold": False}) == 1


def test_an_offer_whose_icon_and_plate_name_two_gifts_is_unknown_and_not_bought(context, monkeypatch):
    # #329: the icon says 9053 and the plate 9009, both wanted: neither is trusted, the log has both.
    shelf(context, [100], 500)
    cells_read(monkeypatch, ("Burn", 3, 9053))
    plates_read(monkeypatch, 9009)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9009)), {"wanted": None, "sold": False}) == 0
    assert any("9053" in line and "9009" in line and "unknown" in line for line in lines)


def test_every_cell_of_the_shop_is_logged_with_its_id_purchased_ones_too(context, monkeypatch):
    # #329: a Not Enough Cost cell and a Purchased one name their gift in the log; the Purchased one is never bought.
    shelf(context, [300, 120, 100], 250, short=[0], purchased=[2])
    cells_read(monkeypatch, ("Burn", None), ("Burn", 1, 9003))
    plates_read(monkeypatch, 9053, 9003, 9009)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    assert actions.Shop.buy_offers(context, buying(wants(9053, 9003, 9009)), {"wanted": None, "sold": True}) == 1
    shown = "\n".join(lines)
    assert "9053 Dust to Dust" in shown and "9009" in shown and "Purchased" in shown
    assert "plate 'plate 9003'" in shown and "plate 'plate 9009' 9009" in shown  # an on-sale cell's line names its plate too
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [725 + 50]


COUPLED = 9092  # Coupled Oscillation, Tremor IV: [9031, 9091, 9165], all three sold by the shop


def test_a_material_a_wanted_fusion_lacks_is_bought_for_it_and_the_log_says_which(context, monkeypatch):
    # The user, 2026-10-30: the list wants 9092 only; its material 9031 keeps its drop state (locked) and is bought for it.
    shelf(context, [100], 500)
    cells_read(monkeypatch, ("Tremor", 1, 9031))
    plates_read(monkeypatch, 9031)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    assert actions.Shop.buy_offers(context, buying(wants(COUPLED)), {"wanted": None, "sold": False, "owned": [9091]}) == 1
    assert any("9031" in line and line.endswith(f"locked, place 0 for fusion {COUPLED} Coupled Oscillation") for line in lines)
    assert any(line.startswith("shop: bought") and f"for fusion {COUPLED} " in line for line in lines)


def test_no_material_is_bought_for_a_wanted_fusion_owned(context, monkeypatch):
    shelf(context, [100], 500)
    cells_read(monkeypatch, ("Tremor", 1, 9031))
    plates_read(monkeypatch, 9031)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    assert actions.Shop.buy_offers(context, buying(wants(COUPLED)), {"wanted": None, "sold": False, "owned": [COUPLED]}) == 0
    assert any("9031" in line and line.endswith("drop") for line in lines)


def test_a_material_owned_is_not_bought_again(context, monkeypatch):
    shelf(context, [100, 100], 500)
    cells_read(monkeypatch, ("Tremor", 1, 9031), ("Tremor", 2, 9165))
    plates_read(monkeypatch, 9031, 9165)
    assert actions.Shop.buy_offers(context, buying(wants(COUPLED)), {"wanted": None, "sold": False, "owned": [9031]}) == 1
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [725 + 50]


def test_a_group_short_of_one_buys_one_though_two_of_its_gifts_are_on_sale(context, monkeypatch):
    # The shared cases' fusion 507 takes 2 of 201, 202, 302; 202 is owned and 201, 302 are on sale: the first bought (the
    # last cell, 302) meets the need, so 201 is not bought.
    tables = json.loads((Path(__file__).parent / "gift_list_cases.json").read_text(encoding="utf-8"))["data"]
    monkeypatch.setattr(gifts, "_game_tables", lambda: tables)
    shelf(context, [100, 100], 500)
    cells_read(monkeypatch, ("Bleed", 3, 201), ("Keywordless", 3, 302))
    plates_read(monkeypatch, 201, 302)
    assert actions.Shop.buy_offers(context, buying(wants(507)), {"wanted": None, "sold": False, "owned": [202]}) == 1
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [725 + 50]


def test_white_gossypium_known_only_by_its_plate_is_not_bought(context, monkeypatch):
    # #329, #90: the icon is unread and the slot's line says only "Gift"; the plate reads White Gossypium (9020).
    shelf(context, [100, 100], 500)
    cells_read(monkeypatch, ("Bleed", 2), ("Bleed", 2, 9005))
    plates_read(monkeypatch, 9020, 9005)
    assert actions.Shop.buy_offers(context, NO_GOSSYPIUM, {"wanted": None, "sold": False}) == 1
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list if c.args[1] == 268]
    assert [x for x, _ in taps] == [725 + 50]


def refresh_shop(context):
    """A shop of 500 Cost whose refresh fees read 100 and 90, 410 Cost after a refresh: the taps."""
    refreshed = (actions.KEYWORD_REFRESH, actions.REFRESH["normal"][0])
    return live_shop(context, lambda taps: {tuple(actions.SHOP_COST): [("410" if any(t in taps for t in refreshed) else "500", (560, 120, 60, 30))],
                                            tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                                            tuple(actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))],
                                            tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]})


def test_the_shop_does_not_refresh_for_a_wanted_fusion_owned(context, monkeypatch):
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    taps = refresh_shop(context)
    team = buying(wants(COUPLED), shop_refresh_keyword=3)
    assert not actions.Shop.buy(context, team, {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": [COUPLED]}) and taps == []


def test_the_shop_refreshes_for_a_material_a_wanted_fusion_lacks(context, monkeypatch):
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    taps = refresh_shop(context)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": []}
    actions.Shop.buy(context, buying(wants(COUPLED), shop_refresh_keyword=1), visit)
    assert visit["refreshes"] == {"keyword": 1, "normal": 0} and taps


@pytest.mark.parametrize("keyword, normal, used", [
    (1, 0, {"keyword": 1, "normal": 0}),
    (0, 1, {"keyword": 0, "normal": 1}),  # the keyword refresh has no count left: the normal one goes on
    (0, 0, {"keyword": 0, "normal": 0}),  # a new team's default: no refresh (the user, 2026-10-30)
])
def test_each_refresh_kind_has_its_own_count(context, monkeypatch, keyword, normal, used):
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    refresh_shop(context)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": []}
    actions.Shop.buy(context, buying(wants(COUPLED), shop_refresh_keyword=keyword, shop_refresh_normal=normal), visit)
    assert visit["refreshes"] == used


def test_the_owned_gifts_are_read_off_the_sell_page_before_a_wanted_fusions_material_is_bought(context, monkeypatch):
    # The visit has not read them yet: the sell page shows Coupled Oscillation owned, so nothing is bought for it.
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    monkeypatch.setattr(actions, "owned_cells", lambda context, page: ([{"i": 0, "id": COUPLED}, {"i": 1, "id": None}], {}))
    taps = live_shop(context, lambda taps: {tuple(actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))]}
                     if taps[-1:] == [actions.SHOP_BUTTONS["sell"]] else {})
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    assert not actions.Shop.buy(context, buying(wants(COUPLED), shop_refresh_keyword=3), visit)
    assert visit["owned"] == [COUPLED] and taps[0] == actions.SHOP_BUTTONS["sell"]


def test_the_owned_gifts_are_not_read_for_a_list_whose_fusions_lack_nothing_the_shop_sells(context, monkeypatch):
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    taps = refresh_shop(context)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    actions.Shop.buy(context, buying(wants(9053, 9083), shop_refresh_keyword=0), visit)  # Lunar Memory: no shop material
    assert "owned" not in visit and actions.SHOP_BUTTONS["sell"] not in taps


VIOLIN = 9249  # A Small, Lovely Violin: [9706, 9707, 9431], specific to Dregs of the Manor (1016) and S.E.A. (1102)


def test_a_restarted_agent_still_buys_for_a_pack_fusion(context, monkeypatch):
    # The run's packs are unknown (RUN has none): the Violin's materials are bought all the same, though the run may never
    # have pulled its pack (the user, 2026-10-30: rather spend more than miss a wanted fusion).
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    refresh_shop(context)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": []}
    actions.Shop.buy(context, buying(wants(VIOLIN), shop_refresh_keyword=1), visit)
    assert visit["refreshes"]["keyword"] == 1


def test_a_pack_fusion_buys_in_a_run_of_its_pack(context, monkeypatch):
    actions.RUN["packs"] = [1016]
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    refresh_shop(context)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": []}
    actions.Shop.buy(context, buying(wants(VIOLIN), shop_refresh_keyword=1), visit)
    assert visit["refreshes"]["keyword"] == 1


def test_the_shop_stops_refreshing_once_what_it_bought_meets_the_list(context, monkeypatch):
    # The list wants the Violin alone; the run pulled Dregs of the Manor (1016) and holds 9707 and 9431; the shop shows 9706.
    # Once 9706 is bought the list buys nothing more: the two keyword refreshes left are not spent.
    actions.RUN["packs"] = [1016]

    def buy_offers(context, team, visit):
        if 9706 in visit["owned"]:
            return 0
        visit["owned"].append(9706)
        return 1
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(buy_offers))
    taps = refresh_shop(context)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}, "owned": [9707, 9431]}
    assert actions.Shop.buy(context, buying(wants(VIOLIN), shop_refresh_keyword=2), visit)
    assert visit["refreshes"] == {"keyword": 0, "normal": 0} and actions.KEYWORD_REFRESH not in taps
    assert any("no refresh" in line and "bought" in line for line in lines)


def test_a_visit_that_could_not_read_the_owned_gifts_does_not_buy_a_fusions_material_twice(context, monkeypatch):
    # The sell page did not open (visit["owned"] stays None): an owned gift counts as none (spec 03), but what this visit
    # bought counts: after a refresh the shop shows 9031 again, and Coupled Oscillation lacks it no more.
    visit = {"wanted": None, "sold": False}
    for bought in (1, 0):
        shelf(context, [100], 500)
        cells_read(monkeypatch, ("Tremor", 1, 9031))
        plates_read(monkeypatch, 9031)
        assert actions.Shop.buy_offers(context, buying(wants(COUPLED)), visit) == bought
    assert visit.get("owned") is None and visit["bought"] == [9031]


def test_the_shop_does_not_refresh_when_the_list_buys_nothing(context):
    # #298: the buy queue is empty (nothing wanted): no offer read, no refresh, whatever the Cost.
    taps = live_shop(context, lambda taps: {tuple(actions.SHOP_COST): [("500", (560, 120, 60, 30))],
                                            tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                                            tuple(actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))]})
    team = buying(wants(), shop_refresh_keyword=3)
    assert not actions.Shop.buy(context, team, {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}) and taps == []


ROW = 153  # px between the offer rows; a Super Shop's grid scrolls 150 px at most (live 2026-10-15: SuperShop.png and its scrolled capture)
SCROLL_END = 150


def super_shop(context, monkeypatch, n=10, red=True, reset_on_buy=False, cost=2000):
    """A shop of n offers, 4 a row, priced 100 + index, over gifts of the first Burn ids; its grid drags (actions.scroll) from 0
    to SCROLL_END and the OCR reads the offers that show whole. red: the title is a Super Shop's. reset_on_buy: a
    purchase puts the grid back to its top. The game's state is in the dict returned: "at", "cost", "bought", "scrolls"."""
    ids = [g["id"] for g in gift_tables()[0] if g["keyword"] == "Burn"][:n]
    xs = [570, 725, 880, 1035]
    game = {"at": 0, "cost": cost, "opened": None, "bought": [], "scrolls": 0, "ids": ids}
    image = np.zeros((720, 1280, 3), np.uint8)
    if red:
        image[108:138, 190:320] = (0, 0, 200)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image

    def scroll(context, x, y, dx, dy):
        game["scrolls"] += 1
        game["at"] = min(max(game["at"] - dy, 0), SCROLL_END)
    monkeypatch.setattr(actions, "scroll", scroll)

    def click(x, y):
        if (x, y) == actions.PURCHASE:
            game["bought"].append(game["opened"])
            game["cost"] -= 100 + game["opened"]
            game["at"] = 0 if reset_on_buy else game["at"]
            game["opened"] = None
        else:  # an offer's icon, 50 px over its price line
            game["opened"] = next((i for i in range(n) if abs(xs[i % 4] + 50 - x) < 30 and abs(268 + ROW * (i // 4) - game["at"] - y) < 25), None)
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click

    def offers():
        lines = []
        for i in range(n):
            dy = ROW * (i // 4) - game["at"]
            if 306 + dy >= 215 and 333 + dy + 17 <= 515:  # whole in the grid's box
                lines += [(f"Gift {i}", (xs[i % 4], 333 + dy, 90, 17)), (str(100 + i), (xs[i % 4] + 30, 306 + dy, 40, 24))]
        return lines

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        shown = {tuple(actions.OFFER_GRID): offers(), tuple(actions.SHOP_COST): [(str(game["cost"]), (560, 120, 60, 30))],
                 tuple(actions.DIALOG_TITLE): [("Purchase E.G.O Gifts", (500, 100, 260, 40))] if game["opened"] is not None else [],
                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}.get(roi, [])
        results = [SimpleNamespace(text=t, box=b) for t, b in shown]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition

    def offer_at(x, y):  # the offer whose cell centre (x, y) is, by the grid's position now
        return ids[round((y + game["at"] - 266) / ROW) * 4 + round((x - 624) / 154)]

    def read_cells(context, image, cells, page):
        return [{"i": i, "x": x, "y": y, "tier": 2, "keyword": "Burn", "id": offer_at(x, y), "score": 0.9}
                for i, (x, y) in enumerate(cells)]
    monkeypatch.setattr(actions, "read_cells", read_cells)
    monkeypatch.setattr(actions, "read_plates", lambda context, image, centres: [{"text": f"plate {offer_at(x, y)}", "id": offer_at(x, y)}
                                                                                 for x, y in centres])
    return game


def test_a_super_shops_last_two_offers_are_read_after_a_scroll_and_bought(context, monkeypatch):
    # #341: 10 offers, the last 2 only show with the grid scrolled; the list wants exactly them.
    game = super_shop(context, monkeypatch)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    ids = game["ids"]
    assert actions.Shop.buy_offers(context, buying(wants(ids[9], ids[8])), {"wanted": None, "sold": False}) == 2
    assert sorted(game["bought"]) == [8, 9]
    for i in range(10):  # every offer is read, once: the 2 rows both screens show are not counted twice
        assert len([line for line in lines if f"'Gift {i}' {100 + i}:" in line]) == 1, i


def test_an_offer_on_both_screens_is_bought_once(context, monkeypatch):
    # #341: Gift 5 sits in the second row, which the grid shows before and after the scroll.
    game = super_shop(context, monkeypatch)
    assert actions.Shop.buy_offers(context, buying(wants(game["ids"][5])), {"wanted": None, "sold": False}) == 1
    assert game["bought"] == [5]


def test_the_offer_bought_is_the_one_read_when_a_purchase_puts_the_grid_back_on_top(context, monkeypatch):
    # #341: after Gift 9 is bought the game shows the grid at its top; Gift 8 (first screen's row 3... read after the scroll)
    # is brought into view again and checked by its name and price before the tap, not tapped at its old place.
    game = super_shop(context, monkeypatch, reset_on_buy=True)
    ids = game["ids"]
    assert actions.Shop.buy_offers(context, buying(wants(ids[9], ids[8], ids[1])), {"wanted": None, "sold": False}) == 3
    assert sorted(game["bought"]) == [1, 8, 9]


def test_a_shop_of_8_offers_is_not_scrolled(context, monkeypatch):
    # #341: a shop's title is tan: nothing scrolls.
    game = super_shop(context, monkeypatch, n=8, red=False)
    assert actions.Shop.buy_offers(context, buying(wants(game["ids"][5])), {"wanted": None, "sold": False}) == 1
    assert game["bought"] == [5] and game["scrolls"] == 0


def test_a_super_shop_of_8_offers_reads_nothing_new_after_the_scroll(context, monkeypatch):
    # #341: the grid does not move when there is no third row: the second read adds no offer, the first one is still bought.
    game = super_shop(context, monkeypatch, n=8)
    assert actions.Shop.buy_offers(context, buying(wants(game["ids"][0])), {"wanted": None, "sold": False}) == 1
    assert game["bought"] == [0]


def test_an_offer_whose_badge_reads_nothing_is_not_opened_to_read_its_keyword(context, monkeypatch):
    # #297: the purchase dialog is no longer a second reading of the keyword: of 205 offer cells on 55 live pages, 155 read a
    # tier and badge (154 named by their icon) and 50 are skills or dimmed offers; none had its badge cut off. A cell that is
    # not read at all is not a gift to buy.
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    reads(context, {tuple(actions.OFFER_GRID): OLD_DOLL_SHOP, tuple(actions.SHOP_COST): [("787", (560, 120, 60, 30))]})
    monkeypatch.setattr(actions, "read_cells", lambda *args: [])
    visit = {"wanted": None, "sold": False}
    assert actions.Shop.buy_offers(context, buying(wants(9009)), visit) == 0
    assert not context.tasker.controller.post_click.called
    assert visit["wanted"] is None
