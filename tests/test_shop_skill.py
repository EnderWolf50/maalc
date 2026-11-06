"""Skill replacement in the shop (#455): the flow on a fake shop, and the dialog's pixel readers on the real captures.

The OCR of the real captures (the slot's sinner, Skills Owned, the Cost, the prices, to_main's tell) is test_shop_skill_screens.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
import shop
import test_actions
from test_actions import argv, buying, replacing, shop_team, wants
from test_shop import skill_entry

clock, context = test_actions.clock, test_actions.context  # its fixtures
SCREENS = Path(__file__).resolve().parent / "screens"
NAME_X = [570, 725, 880, 1035]  # where a slot's name line starts, per column (test_shop_buy.shelf's grid)
PRICES = {"s1_s2": 45, "s2_s3": 75, "s1_s3": 120}


def slot_tap(column):
    """Where Shop taps the slot of a column: 50 px over its price line's centre (open_offer)."""
    return NAME_X[column] + 50, 318 - 50


class Game:
    """A shop whose first slots are Replace <sinner>'s Skill, with a dialog that reacts to taps as #453 saw it.

    sinners: [(sinner, counts)] by column; cost: the Cost; dim: the swaps shown dimmed; dialog: the sinner the dialog
    names (None: the slot's); pays: whether the final Confirm takes the price (else the Cost stays); drop: what it takes
    instead of the price; asks: the price the second layer asks (None: the option's); lights: whether a tapped option lights
    up; refreshed: the sinners a normal refresh puts up. OCR reads per ROI what the state shows; the pixel readers are
    patched (their real readings are tested below on the captures).
    """

    def __init__(self, context, monkeypatch, sinners, cost, dim=(), dialog=None, pays=True, drop=None, asks=None,
                 lights=True, owned_text=None, refreshed=None):
        self.sinners, self.cost, self.dim, self.dialog, self.pays, self.drop = list(sinners), cost, set(dim), dialog, pays, drop
        self.asks, self.lights, self.owned_text, self.refreshed = asks, lights, owned_text, refreshed
        self.state, self.open, self.picked, self.bought, self.taps = "main", None, None, set(), []
        context.tasker.controller.post_click.side_effect = self.click
        context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
            lambda: np.full((720, 1280, 3), len(self.taps) * 20 % 256, np.uint8)
        context.run_recognition.side_effect = self.recognition
        monkeypatch.setattr(actions.shop, "option_lit", lambda image, box: self.lit(box))
        monkeypatch.setattr(actions.shop, "option_picked", lambda image, frame: self.picked is not None
                            and frame == actions.REPLACE_FRAMES[self.picked])

    def lit(self, box):
        return next(k for k, b in actions.REPLACE_PRICES.items() if b == box) not in self.dim

    def click(self, x, y):
        at = (x, y)
        self.taps.append(at)
        if self.state == "main":
            column = next((c for c in range(len(self.sinners)) if slot_tap(c) == at), None)
            if column is not None and column not in self.bought:
                self.state, self.open, self.picked = "dialog", column, None
            elif at == actions.REFRESH["normal"][0] and self.refreshed:
                self.cost, self.sinners, self.bought, self.refreshed = self.cost - 100, self.refreshed, set(), None
            elif at == actions.BOTTOM_RIGHT:
                self.state = "leave"
        elif self.state == "leave":
            self.state = "left" if at == actions.LEAVE_CONFIRM else "main"
        elif self.state == "dialog":
            swap = next((k for k, p in actions.REPLACE_OPTIONS.items() if p == at), None)
            if swap and swap not in self.dim and self.lights:
                self.picked = swap
            elif at == actions.REPLACE_CONFIRM and self.picked:
                self.state = "ask"
            elif at == actions.REPLACE_CANCEL:
                self.state = "main"
        elif self.state == "ask":
            if at == actions.REPLACE_CONFIRM:
                if self.pays:
                    self.cost -= PRICES[self.picked] if self.drop is None else self.drop
                    self.bought.add(self.open)
                self.state = "main"
            elif at == actions.REPLACE_CANCEL:
                self.state, self.picked = "dialog", None
        return MagicMock()

    def shown(self):
        """{roi: [(text, box)]} the screen shows now."""
        if self.state == "left":
            return {}
        if self.state in ("main", "leave"):
            lines = []
            for c, (sinner, _) in enumerate(self.sinners):
                x = NAME_X[c]
                lines += [(f"Replace {sinner}'s Skill", (x, 333, 131, 17)), ("??", (x + 30, 306, 40, 24))]
                lines += [("Purchased", (x + 10, 260, 80, 17))] if c in self.bought else []
            shown = {tuple(actions.OFFER_GRID): lines, tuple(actions.SHOP_COST): [(str(self.cost), (560, 120, 60, 30))],
                     tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))]}
            return shown | ({tuple(actions.LEAVE_DIALOG): [("Leave the shop?", (480, 325, 300, 35))]} if self.state == "leave" else {})
        sinner, counts = self.sinners[self.open]
        owned = self.owned_text or "SKILL 1x{} SKILL 2x{} SKILL 3x{}".format(*counts)
        shown = {tuple(actions.DIALOG_TITLE): [("Skills Owned", (610, 104, 90, 14)), (owned, (617, 134, 216, 16))],
                 tuple(actions.REPLACE_TITLE): [(f"Replace {self.dialog or sinner}'s Skill", (213, 124, 355, 28))],
                 tuple(actions.REPLACE_OWNED): [("Skills Owned", (610, 104, 90, 14)), (owned, (617, 134, 216, 16))],
                 # The dialog's Cost digits overlap the Refresh fee's box: to_main must not take the dialog for the main page.
                 tuple(actions.REFRESH["normal"][1]): [("35", (1020, 140, 20, 20))],
                 **{tuple(box): [(str(PRICES[k]), (box[0] + 20, 206, 30, 20))] for k, box in actions.REPLACE_PRICES.items()}}
        if self.state == "dialog":
            shown[tuple(actions.REPLACE_COST)] = [(str(self.cost), (1020, 127, 41, 25))]
        else:
            price = self.asks or PRICES[self.picked]
            shown[tuple(actions.REPLACE_ASK)] = [(f"Spend {price} Cost to replace this Skill?", (440, 493, 400, 16))]
            shown[tuple(actions.REPLACE_PREVIEW)] = [(f"{self.cost} ▸ {self.cost - price}", (985, 127, 113, 25))]
        return shown

    def recognition(self, name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in self.shown().get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None


def logged(monkeypatch):
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    return lines


def gregor_shop(context, monkeypatch, **game):
    """Gregor under Uptie 3 (#453: SKILL 3x0, 75 and 120 dim), 350 Cost, the team wanting him at 1/3/2."""
    return Game(context, monkeypatch, [("Gregor", (3, 2, 0))], 350, dim=("s2_s3", "s1_s3"), **game)


GREGOR = shop_team({"skill_replacement": replacing(skill_entry("Gregor", 1, 3, 2))})


def test_the_default_plan_taps_nothing_and_reads_nothing(context, monkeypatch):
    # #264 User Story 3: no sinner listed, or every target at 3/2/1: the shop plays as before.
    game = gregor_shop(context, monkeypatch)
    for team in (shop_team({}), shop_team({"skill_replacement": replacing(skill_entry("Gregor", 3, 2, 1))})):
        assert actions.Shop.replace_skills(context, team, {}) == 0
    assert game.taps == [] and not context.run_recognition.called


def test_a_slot_is_opened_an_option_picked_confirmed_twice_and_the_cost_checked(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    visit = {}
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 1
    assert game.taps == [slot_tap(0), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM]
    assert lines == ["shop: \"Replace Gregor's Skill\": 'Gregor' counts not read this run, toward 1/3/2: open",
                     "shop: 'Gregor': Skills Owned 3/2/0, s1_s2 45, s2_s3 75 dim, s1_s3 120 dim, 350 Cost, reserve 0: try s1_s2",
                     "shop: replaced 'Gregor' s1_s2 (skill 1 -> 2) for 45: 350 -> 305 Cost"]
    assert actions.RUN["skills"] == {"Gregor": [2, 3, 0]} and visit["replaced"] == ["Gregor"]
    # The slot now shows Purchased: the step after a refresh skips it.
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 0 and len(game.taps) == 4


def test_no_page_guard_runs_between_the_paying_confirm_and_the_main_page(context, monkeypatch):
    # #455 graft 1: CONNECTING shows after the final Confirm where the global Connecting popup is matched; a guarded read
    # there would hand the shop back in the middle of the payment.
    game = gregor_shop(context, monkeypatch)
    guarded = []
    monkeypatch.setattr(actions, "page_guard", lambda context, home, image=None: guarded.append(len(game.taps)) or actions.screen(context))
    actions.Shop.replace_skills(context, GREGOR, {})
    paid = len(game.taps)  # the final Confirm is the last tap
    assert game.taps[-1] == actions.REPLACE_CONFIRM and guarded and max(guarded) < paid


def test_an_unchanged_cost_is_not_retried(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch, pays=False), logged(monkeypatch)
    visit = {}
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 0
    assert game.taps.count(actions.REPLACE_CONFIRM) == 2
    assert "shop: 'Gregor' s1_s2 for 45: 350 -> 350 Cost: the Cost did not change; taking it as not replaced" in lines
    assert not [line for line in lines if line.startswith("shop: replaced")]  # #264 log: "replaced" is a swap that went through
    assert actions.RUN["skills"] == {"Gregor": [3, 2, 0]} and visit["replaced"] == ["Gregor"]
    actions.Shop.replace_skills(context, GREGOR, visit)  # the pass after a refresh: handled this visit
    assert game.taps.count(slot_tap(0)) == 1 and "\"Replace Gregor's Skill\": 'Gregor' handled this visit: skip" in lines[-1]


def test_a_cost_that_drops_by_another_amount_forgets_the_counts(context, monkeypatch):
    # #455 graft 2: a remembered deck never runs ahead of the game's; the next dialog reads it again.
    gregor_shop(context, monkeypatch, drop=60)
    lines = logged(monkeypatch)
    assert actions.Shop.replace_skills(context, GREGOR, {}) == 0
    assert "shop: 'Gregor' s1_s2 for 45: 350 -> 290 Cost: the Cost dropped by 60, not the price: the counts are not known" in lines
    assert actions.RUN["skills"] == {} and not [line for line in lines if line.startswith("shop: replaced")]


def test_a_dialog_of_another_sinner_is_cancelled(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch, dialog="Rodion"), logged(monkeypatch)
    visit = {}
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL]
    assert "shop: the dialog is 'Rodion''s, not 'Gregor''s: cancel" in lines and visit["replaced"] == ["Gregor"]


@pytest.mark.parametrize("game, line", [
    ({"owned_text": "SKILL 1x3 SKILL 2x2"}, "shop: 'Gregor': Skills Owned unread or not 5-6 cards: cancel"),
    ({"lights": False}, "shop: 'Gregor': s1_s2 did not light up: cancel"),
])
def test_a_dialog_that_does_not_read_or_react_is_cancelled_before_any_confirm(context, monkeypatch, game, line):
    played, lines = gregor_shop(context, monkeypatch, **game), logged(monkeypatch)
    visit = {}
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 0
    assert played.taps[0] == slot_tap(0) and played.taps[-1] == actions.REPLACE_CANCEL
    assert actions.REPLACE_CONFIRM not in played.taps and line in lines and visit["replaced"] == ["Gregor"]
    assert any(line.startswith("shop: 'Gregor': Skills Owned ") and ", 350 Cost, reserve 0: try " in line for line in lines)  # #264 log


def test_an_unread_cost_buys_nothing(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    shown = game.shown
    game.shown = lambda: {k: v for k, v in shown().items() if k != tuple(actions.REPLACE_COST)}
    actions.Shop.replace_skills(context, GREGOR, {})
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL] and "shop: the Cost reads nothing: cancel" in lines
    assert "shop: 'Gregor': Skills Owned 3/2/0, s1_s2 45, s2_s3 75 dim, s1_s3 120 dim, unread Cost, reserve 0: try s1_s2" in lines
    assert actions.RUN["skills"] == {"Gregor": [3, 2, 0]}  # the counts read are kept


def test_a_second_layer_that_asks_another_price_is_cancelled(context, monkeypatch):
    # #455 graft 3: the "Spend N Cost" line and the "350 ▸ 305" preview both say the chosen price before the paying tap.
    game, lines = gregor_shop(context, monkeypatch, asks=75), logged(monkeypatch)
    assert actions.Shop.replace_skills(context, GREGOR, {}) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CANCEL,
                         actions.REPLACE_CANCEL]  # the second layer's Cancel, then to_main's on the first
    assert "shop: 'Gregor': the dialog asks 75 and previews 75 off 350, not 45: cancel" in lines and game.cost == 350


def test_a_swap_nobody_can_afford_is_judged_again_after_the_next_refresh(context, monkeypatch):
    # The bot cancelled before any Confirm because nothing was affordable: the sinner leaves the visit's handled list.
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    game.cost = 40
    visit = {}
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL] and visit["replaced"] == []
    assert "shop: 'Gregor': no swap toward 1/3/2 is lit, priced and affordable: cancel" in lines
    game.cost = 400  # a sale since
    assert actions.Shop.replace_skills(context, GREGOR, visit) == 1


def test_two_slots_with_cost_for_one_swap_go_to_the_first_listed(context, monkeypatch):
    # #264: Don Quixote's slot comes first on the grid, Gregor first in the list; 80 Cost pays one 45.
    game = Game(context, monkeypatch, [("Don Quixote", (3, 2, 1)), ("Gregor", (3, 2, 1))], 80)
    team = shop_team({"skill_replacement": replacing(skill_entry("Gregor", 2, 3, 1), skill_entry("Don Quixote", 2, 3, 1))})
    visit = {}
    assert actions.Shop.replace_skills(context, team, visit) == 1
    assert game.taps == [slot_tap(1), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM,
                         slot_tap(0), actions.REPLACE_CANCEL]
    assert visit["replaced"] == ["Gregor"] and actions.RUN["skills"] == {"Gregor": [2, 3, 1], "Don Quixote": [3, 2, 1]}


def test_a_sinner_read_at_the_target_is_not_opened_at_the_next_shop(context, monkeypatch):
    game = Game(context, monkeypatch, [("Gregor", (1, 3, 2))], 350)
    actions.Shop.replace_skills(context, GREGOR, {})  # one open: the counts read, nothing to do
    lines = logged(monkeypatch)
    actions.Shop.replace_skills(context, GREGOR, {})  # the next shop, a new visit
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL]
    assert lines == ["shop: \"Replace Gregor's Skill\": 'Gregor' is at 1/3/2 (read this run): skip"]


def test_the_counts_leave_with_the_run_when_its_rewards_are_given_up(context, monkeypatch):
    # #455: cleared on leaving the Mirror Dungeon. RUN goes as a whole at the claim, the give-up (here), a new run and a
    # task change; a new floor or a hand-back keeps it.
    actions.note_skills("Gregor", (2, 3, 0))
    monkeypatch.setattr(actions.Settle, "record", staticmethod(lambda *a: None))
    test_actions.reads(context, {tuple(actions.DIALOG_TEXT): [("End expedition without claiming rewards?", (420, 300, 440, 30))]})
    assert actions.Settle().give_up(context, actions.RUN, None)
    assert "skills" not in actions.RUN


def test_a_slot_gone_from_the_grid_after_a_swap_is_not_tapped(context, monkeypatch):
    # #264: the grid is read again after each slot; whether a swapped slot moves is unseen. Here Don Quixote's slot is gone.
    game = Game(context, monkeypatch, [("Gregor", (3, 2, 1)), ("Don Quixote", (3, 2, 1))], 500)
    team = shop_team({"skill_replacement": replacing(skill_entry("Gregor", 2, 3, 1), skill_entry("Don Quixote", 2, 3, 1))})
    click = game.click

    def swap_hides_the_second(x, y):
        if (x, y) == actions.REPLACE_CONFIRM and game.state == "ask":
            game.sinners = game.sinners[:1]
        return click(x, y)
    context.tasker.controller.post_click.side_effect = swap_hides_the_second
    lines, visit = logged(monkeypatch), {}
    assert actions.Shop.replace_skills(context, team, visit) == 1
    assert slot_tap(1) not in game.taps and visit["replaced"] == ["Gregor"]
    assert "shop: 'Don Quixote''s slot is no longer on the grid: skip" in lines


def test_a_refresh_that_shows_another_sinner_is_judged_again(context, monkeypatch):
    # #264 時機, attachment 106 -> 107: a refresh put Rodion's slot where Gregor's was.
    Game(context, monkeypatch, [("Gregor", (3, 2, 0))], 350, refreshed=[("Rodion", (3, 2, 1))])
    opened = []

    def replace_skill(context, slot, entry, reserve, swaps):
        opened.append(slot["sinner"])
        return "handled"
    monkeypatch.setattr(actions.Shop, "replace_skill", staticmethod(replace_skill))
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: 0))
    team = buying(wants(9053), shop_refresh_normal=1,
                  skill_replacement=replacing(skill_entry("Gregor", 1, 3, 2), skill_entry("Rodion", 3, 0, 3)))
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    actions.Shop.replace_skills(context, team, visit)
    assert actions.Shop.buy(context, team, visit)
    assert opened == ["Gregor", "Rodion"] and visit["refreshes"]["normal"] == 1


def test_a_hand_back_mid_dialog_is_not_paid_again(context, monkeypatch):
    # ADR 0007: the sinner is marked before the tap, as the heal is.
    actions.RUN["team"] = shop_team({"heal": "none", "skill_replacement": replacing(skill_entry("Gregor", 1, 3, 2))})
    game = gregor_shop(context, monkeypatch)
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a: False))
    real = actions.Shop.replace_skill

    def gone(context, slot, entry, reserve, swaps):
        context.tasker.controller.post_click(*slot_tap(0))  # the dialog opened, then a popup took the screen
        raise actions.PageGone("Shop")
    monkeypatch.setattr(actions.Shop, "replace_skill", staticmethod(gone))
    assert actions.Shop().run(context, argv())
    assert actions.RUN["shop"]["replaced"] == ["Gregor"] and game.state == "dialog"
    monkeypatch.setattr(actions.Shop, "replace_skill", staticmethod(real))
    lines = logged(monkeypatch)
    assert actions.Shop().run(context, argv())  # MirrorHub enters the same visit again: to_main cancels the dialog first
    assert game.taps.count(slot_tap(0)) == 1 and actions.REPLACE_CONFIRM not in game.taps and game.cost == 350
    assert "shop: \"Replace Gregor's Skill\": 'Gregor' handled this visit: skip" in lines


def test_a_visit_heals_then_replaces_skills_then_buys(context, monkeypatch):
    # #264 時機: the heal first, the skills before the sell -> buy -> fuse rounds.
    actions.RUN["team"] = shop_team({"heal": "full"})
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    steps = []
    for step in ("heal", "replace_skills", "sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a, step=step: steps.append(step) and False))
    actions.Shop().run(context, argv())
    assert steps == ["heal", "replace_skills", "sell", "buy", "fuse"]


def test_buying_goes_on_after_a_swap(context, monkeypatch):
    actions.RUN["team"] = shop_team({"heal": "none", "skill_replacement": replacing(skill_entry("Gregor", 1, 3, 2))})
    game = gregor_shop(context, monkeypatch)
    bought = []
    monkeypatch.setattr(actions.Shop, "buy", staticmethod(lambda context, team, visit: bought.append(list(visit["replaced"])) and False))
    for step in ("sell", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a: False))
    assert actions.Shop().run(context, argv())
    assert bought == [["Gregor"]] and game.cost == 305 and actions.REPLACE_CONFIRM in game.taps


def test_to_main_cancels_the_dialog_though_its_cost_reads_as_a_refresh_fee(context, monkeypatch):
    # The dialog's Cost digits overlap REFRESH["normal"]'s box: the dialog's branch comes before the fee's.
    game = gregor_shop(context, monkeypatch)
    game.state, game.open = "dialog", 0
    assert actions.Shop.to_main(context)
    assert game.taps == [actions.REPLACE_CANCEL]
    game.state, game.picked, game.taps[:] = "ask", "s1_s2", []
    assert actions.Shop.to_main(context)
    assert game.taps == [actions.REPLACE_CANCEL, actions.REPLACE_CANCEL]  # the second layer, then the first


def test_the_swap_table_matches_the_dialog_options():
    # One hand-synced list: the data file's swaps are the dialog's three options, each named after what it moves.
    swaps = actions.data("shop.yaml")["skill_replacement"]
    assert set(actions.REPLACE_OPTIONS) == set(actions.REPLACE_PRICES) == set(actions.REPLACE_FRAMES) == set(swaps)
    assert all(k == f"s{v['from']}_s{v['to']}" for k, v in swaps.items())
    assert {k: v["shop"] for k, v in swaps.items()} == PRICES  # the prices #453 saw on the dialog, left to right 45, 75, 120


def capture(name):
    return np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]


DIALOGS = ["ShopReplaceSkillAll", "ShopReplaceSkillDimmed", "ShopReplaceSkillPickedLeft", "ShopReplaceSkillPickedMiddle",
           "ShopReplaceSkillPickedRight"]


@pytest.mark.parametrize("name, lit", [
    ("ShopReplaceSkillAll", ["s1_s2", "s2_s3", "s1_s3"]),  # Don Quixote, 3/2/1
    ("ShopReplaceSkillDimmed", ["s1_s2"]),  # Gregor, skill 3 locked: 75 and 120 red
    ("ShopReplaceSkillPickedLeft", ["s1_s2"]),
    ("ShopReplaceSkillPickedMiddle", ["s1_s2", "s2_s3", "s1_s3"]),
    ("ShopReplaceSkillPickedRight", ["s1_s2", "s2_s3", "s1_s3"]),
])
def test_a_dimmed_option_is_told_by_its_red_price(name, lit):
    image = capture(name)
    assert [k for k, box in actions.REPLACE_PRICES.items() if shop.option_lit(image, box)] == lit


@pytest.mark.parametrize("name, picked", [
    ("ShopReplaceSkillAll", []), ("ShopReplaceSkillDimmed", []), ("ShopReplaceSkillPickedLeft", ["s1_s2"]),
    ("ShopReplaceSkillPickedMiddle", ["s2_s3"]), ("ShopReplaceSkillPickedRight", ["s1_s3"]),
    ("ShopReplaceSkillConfirm", []), ("ShopReplaceSkillConnecting", []),
])
def test_the_picked_option_is_told_by_its_orange_frame(name, picked):
    image = capture(name)
    assert [k for k, frame in actions.REPLACE_FRAMES.items() if shop.option_picked(image, frame)] == picked


def screens_1280():
    for path in sorted(SCREENS.glob("*.png")):
        img = Image.open(path)
        if img.size == (1280, 720):
            yield path.stem, np.asarray(img.convert("RGB"))[:, :, ::-1]


def test_the_lit_price_sweep_over_tests_screens():
    # CODING_STANDARDS' sweep: option_lit is asked only on the dialog's first layer, after its title named the slot's sinner.
    # Over every 1280x720 screen of tests/screens (221 of them), a price box reads lit on the dialogs and on 9 other screens,
    # none a shop page: orange art where a box sits (a battle's skill card, a map node, a gift). The second layer (Confirm,
    # Connecting) reads none: its skill cards cover the prices. #456's ID Skill Search dialogs (live 2026-11-07, the same
    # dialog with prices 90/150/240 in Cost or 25/50/75 in Starlight) read as the captures show: Gregor's skill 3 is locked,
    # so only s1_s2 is lit; Ryōshū's three are.
    hits = {stem: [k for k, box in actions.REPLACE_PRICES.items() if shop.option_lit(image, box)] for stem, image in screens_1280()}
    assert {k: v for k, v in hits.items() if v and k not in DIALOGS} == {
        "BattleTurnFocused": ["s1_s2"], "BossGiftTrialsHard": ["s2_s3"], "FormationDetails": ["s2_s3"],
        "LuxConsecThread10Open": ["s1_s2"], "LuxConsecThread2Open": ["s1_s2"], "LuxTeamSelect": ["s1_s2"],
        "LuxTeamSelectChain": ["s1_s2"], "MapZoomed": ["s2_s3"], "StartingGiftPicked": ["s1_s2", "s2_s3", "s1_s3"],
        "ShopIdSkillSearchAll": ["s1_s2", "s2_s3", "s1_s3"],
        **{f"ShopIdSkillSearch{n}": ["s1_s2"] for n in ("Dialog", "Picked", "Starlight")}}


def test_the_picked_frame_sweep_over_tests_screens():
    # CODING_STANDARDS' sweep: option_picked is asked only after an option's tap on the dialog. Over every 1280x720 screen
    # of tests/screens, a frame reads picked on the three Picked captures, the one tapped, and on one battle screen (an
    # orange-lit skill where the right frame's edge runs); no shop page. #456's ID Skill Search dialog with s1_s2 tapped
    # (ShopIdSkillSearchPicked) reads its tapped frame.
    hits = {stem: [k for k, frame in actions.REPLACE_FRAMES.items() if shop.option_picked(image, frame)] for stem, image in screens_1280()}
    assert {k: v for k, v in hits.items() if v} == {"BattleTurnFocused": ["s1_s3"], "ShopIdSkillSearchPicked": ["s1_s2"],
                                                     "ShopReplaceSkillPickedLeft": ["s1_s2"],
                                                     "ShopReplaceSkillPickedMiddle": ["s2_s3"], "ShopReplaceSkillPickedRight": ["s1_s3"]}
