"""Skill replacement in the shop (#455) and ID Skill Search (#456): the flow on a fake shop, and the dialog's and the sinner
bar's pixel readers on the real captures.

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
from test_pipeline import load_nodes
from test_shop import MEURSAULT_ONCE, RYOSHU_TWICE, skill_entry

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
        assert actions.Shop.skill_step(context, team, {}) == 0
    assert game.taps == [] and not context.run_recognition.called


def test_a_slot_is_opened_an_option_picked_confirmed_twice_and_the_cost_checked(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    visit = {}
    assert actions.Shop.skill_step(context, GREGOR, visit) == 1
    assert game.taps == [slot_tap(0), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM]
    assert lines == ["shop: \"Replace Gregor's Skill\": 'Gregor' counts not read this run, toward 1/3/2: open",
                     "shop: 'Gregor': Skills Owned 3/2/0, s1_s2 45, s2_s3 75 dim, s1_s3 120 dim, 350 Cost, reserve 0: try s1_s2",
                     "shop: replaced 'Gregor' s1_s2 (skill 1 -> 2) for 45: 350 -> 305 Cost"]
    assert actions.RUN["skills"] == {"Gregor": [2, 3, 0]} and visit["skill_tapped"] == ["Gregor"]
    # The slot now shows Purchased: the step after a refresh skips it.
    assert actions.Shop.skill_step(context, GREGOR, visit) == 0 and len(game.taps) == 4


def test_no_page_guard_runs_between_the_paying_confirm_and_the_main_page(context, monkeypatch):
    # #455 graft 1: CONNECTING shows after the final Confirm where the global Connecting popup is matched; a guarded read
    # there would hand the shop back in the middle of the payment.
    game = gregor_shop(context, monkeypatch)
    guarded = []
    monkeypatch.setattr(actions, "page_guard", lambda context, home, image=None: guarded.append(len(game.taps)) or actions.screen(context))
    actions.Shop.skill_step(context, GREGOR, {})
    paid = len(game.taps)  # the final Confirm is the last tap
    assert game.taps[-1] == actions.REPLACE_CONFIRM and guarded and max(guarded) < paid


def test_an_unchanged_cost_is_not_retried(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch, pays=False), logged(monkeypatch)
    visit = {}
    assert actions.Shop.skill_step(context, GREGOR, visit) == 0
    assert game.taps.count(actions.REPLACE_CONFIRM) == 2
    assert "shop: 'Gregor' s1_s2 for 45: 350 -> 350 Cost: the Cost did not change; taking it as not replaced" in lines
    assert not [line for line in lines if line.startswith("shop: replaced")]  # #264 log: "replaced" is a swap that went through
    assert actions.RUN["skills"] == {"Gregor": [3, 2, 0]} and visit["skill_tapped"] == ["Gregor"]
    actions.Shop.skill_step(context, GREGOR, visit)  # the pass after a refresh: handled this visit
    assert game.taps.count(slot_tap(0)) == 1 and "\"Replace Gregor's Skill\": 'Gregor' handled this visit: skip" in lines[-1]


def test_a_cost_that_drops_by_another_amount_forgets_the_counts(context, monkeypatch):
    # #455 graft 2: a remembered deck never runs ahead of the game's; the next dialog reads it again.
    gregor_shop(context, monkeypatch, drop=60)
    lines = logged(monkeypatch)
    assert actions.Shop.skill_step(context, GREGOR, {}) == 0
    assert "shop: 'Gregor' s1_s2 for 45: 350 -> 290 Cost: the Cost dropped by 60, not the price: the counts are not known" in lines
    assert actions.RUN["skills"] == {} and not [line for line in lines if line.startswith("shop: replaced")]


def test_a_dialog_of_another_sinner_is_cancelled(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch, dialog="Rodion"), logged(monkeypatch)
    visit = {}
    assert actions.Shop.skill_step(context, GREGOR, visit) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL]
    assert "shop: the dialog is 'Rodion''s, not 'Gregor''s: cancel" in lines and visit["skill_tapped"] == ["Gregor"]


@pytest.mark.parametrize("game, line", [
    ({"owned_text": "SKILL 1x3 SKILL 2x2"}, "shop: 'Gregor': Skills Owned unread or not 5-6 cards: cancel"),
    ({"lights": False}, "shop: 'Gregor': s1_s2 did not light up: cancel"),
])
def test_a_dialog_that_does_not_read_or_react_is_cancelled_before_any_confirm(context, monkeypatch, game, line):
    played, lines = gregor_shop(context, monkeypatch, **game), logged(monkeypatch)
    visit = {}
    assert actions.Shop.skill_step(context, GREGOR, visit) == 0
    assert played.taps[0] == slot_tap(0) and played.taps[-1] == actions.REPLACE_CANCEL
    assert actions.REPLACE_CONFIRM not in played.taps and line in lines and visit["skill_tapped"] == ["Gregor"]
    assert any(line.startswith("shop: 'Gregor': Skills Owned ") and ", 350 Cost, reserve 0: try " in line for line in lines)  # #264 log


def test_an_unread_cost_buys_nothing(context, monkeypatch):
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    shown = game.shown
    game.shown = lambda: {k: v for k, v in shown().items() if k != tuple(actions.REPLACE_COST)}
    actions.Shop.skill_step(context, GREGOR, {})
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL] and "shop: the Cost reads nothing: cancel" in lines
    assert "shop: 'Gregor': Skills Owned 3/2/0, s1_s2 45, s2_s3 75 dim, s1_s3 120 dim, unread Cost, reserve 0: try s1_s2" in lines
    assert actions.RUN["skills"] == {"Gregor": [3, 2, 0]}  # the counts read are kept


def test_a_second_layer_that_asks_another_price_is_cancelled(context, monkeypatch):
    # #455 graft 3: the "Spend N Cost" line and the "350 ▸ 305" preview both say the chosen price before the paying tap.
    game, lines = gregor_shop(context, monkeypatch, asks=75), logged(monkeypatch)
    assert actions.Shop.skill_step(context, GREGOR, {}) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CANCEL,
                         actions.REPLACE_CANCEL]  # the second layer's Cancel, then to_main's on the first
    assert "shop: 'Gregor': the dialog asks 75 and previews 75 off 350, not 45: cancel" in lines and game.cost == 350


def test_a_swap_nobody_can_afford_is_judged_again_after_the_next_refresh(context, monkeypatch):
    # The bot cancelled before any Confirm because nothing was affordable: the sinner leaves the visit's handled list.
    game, lines = gregor_shop(context, monkeypatch), logged(monkeypatch)
    game.cost = 40
    visit = {}
    assert actions.Shop.skill_step(context, GREGOR, visit) == 0
    assert game.taps == [slot_tap(0), actions.REPLACE_CANCEL] and visit["skill_tapped"] == []
    assert "shop: 'Gregor': no swap toward 1/3/2 is lit, priced and affordable: cancel" in lines
    game.cost = 400  # a sale since
    assert actions.Shop.skill_step(context, GREGOR, visit) == 1


def test_two_slots_with_cost_for_one_swap_go_to_the_first_listed(context, monkeypatch):
    # #264: Don Quixote's slot comes first on the grid, Gregor first in the list; 80 Cost pays one 45.
    game = Game(context, monkeypatch, [("Don Quixote", (3, 2, 1)), ("Gregor", (3, 2, 1))], 80)
    team = shop_team({"skill_replacement": replacing(skill_entry("Gregor", 2, 3, 1), skill_entry("Don Quixote", 2, 3, 1))})
    visit = {}
    assert actions.Shop.skill_step(context, team, visit) == 1
    assert game.taps == [slot_tap(1), actions.REPLACE_OPTIONS["s1_s2"], actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM,
                         slot_tap(0), actions.REPLACE_CANCEL]
    assert visit["skill_tapped"] == ["Gregor"] and actions.RUN["skills"] == {"Gregor": [2, 3, 1], "Don Quixote": [3, 2, 1]}


def test_a_sinner_read_at_the_target_is_not_opened_at_the_next_shop(context, monkeypatch):
    game = Game(context, monkeypatch, [("Gregor", (1, 3, 2))], 350)
    actions.Shop.skill_step(context, GREGOR, {})  # one open: the counts read, nothing to do
    lines = logged(monkeypatch)
    actions.Shop.skill_step(context, GREGOR, {})  # the next shop, a new visit
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
    assert actions.Shop.skill_step(context, team, visit) == 1
    assert slot_tap(1) not in game.taps and visit["skill_tapped"] == ["Gregor"]
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
    actions.Shop.skill_step(context, team, visit)
    assert actions.Shop.buy(context, team, visit)
    assert opened == ["Gregor", "Rodion"] and visit["refreshes"]["normal"] == 1


@pytest.mark.parametrize("recovered", [False, True])
def test_a_hand_back_mid_dialog_is_not_paid_again(context, monkeypatch, recovered):
    # ADR 0007: the sinner is marked before the tap, as the heal is. A recovery in between keeps the mark too (#459 drops
    # only the fusion scan).
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
    assert actions.RUN["shop"]["skill_tapped"] == ["Gregor"] and game.state == "dialog"
    monkeypatch.setattr(actions.Shop, "replace_skill", staticmethod(real))
    if recovered:
        actions.forget_game_state()
    lines = logged(monkeypatch)
    assert actions.Shop().run(context, argv())  # MirrorHub enters the same visit again: to_main cancels the dialog first
    assert game.taps.count(slot_tap(0)) == 1 and actions.REPLACE_CONFIRM not in game.taps and game.cost == 350
    assert "shop: \"Replace Gregor's Skill\": 'Gregor' handled this visit: skip" in lines


def test_a_visit_heals_then_replaces_skills_then_buys(context, monkeypatch):
    # #264 時機: the heal first, the skills before the sell -> buy -> fuse rounds.
    actions.RUN["team"] = shop_team({"heal": "full"})
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    steps = []
    for step in ("heal", "skill_step", "sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a, step=step: steps.append(step) and False))
    actions.Shop().run(context, argv())
    assert steps == ["heal", "skill_step", "sell", "buy", "fuse"]


def test_buying_goes_on_after_a_swap(context, monkeypatch):
    actions.RUN["team"] = shop_team({"heal": "none", "skill_replacement": replacing(skill_entry("Gregor", 1, 3, 2))})
    game = gregor_shop(context, monkeypatch)
    bought = []
    monkeypatch.setattr(actions.Shop, "buy", staticmethod(lambda context, team, visit: bought.append(list(visit["skill_tapped"])) and False))
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


def test_the_select_mode_title_box_is_the_shop_nodes():
    # One box written twice: Shop.way_out reads SELECT_TITLE, MirrorHub's Shop node matches ShopSelectSinner (#456).
    select = next(r for r in load_nodes("mirror_dungeon.json")["Shop"]["any_of"] if r["sub_name"] == "ShopSelectSinner")
    assert select["roi"] == actions.SELECT_TITLE


ID_PRICES = {"cost": {"s1_s2": 90, "s2_s3": 150, "s1_s3": 240}, "starlight": {"s1_s2": 25, "s2_s3": 50, "s1_s3": 75}}
ID_SLOT = slot_tap(0)


def portrait(sinner):
    return actions.SHOP_PORTRAIT_X[actions.battle.SINNERS.index(sinner)], 655


class IdGame:
    """A Super Shop whose first slot is ID Skill Search, as #456's captures saw it (spec 02 「ID Skill Search」).

    decks: {sinner: counts} of the living sinners; dead: sinners grey on the bar (their portrait takes no tap); hidden: dead
    ones the bar reads as alive (their portrait takes no tap either); cost, starlight: what is owned; mode: the payment the
    dialog opens in; switches: whether the double arrow switches it; pays: whether the paying Confirm takes the price;
    asks: the second layer's text (None: the price in the mode's unit). Its slot taps into select mode (the Refresh fee still
    reads there); a portrait opens the Replace dialog at the ID prices, whose Cancel and paying Confirm land on the main page.
    replace: the sinners whose Replace <sinner>'s Skill slots stand in the next columns, each opening its dialog at the
    Replace prices in Cost. made: [(how, sinner, swap)] of the swaps paid, how "replace" or "search".
    """

    def __init__(self, context, monkeypatch, decks, cost=868, starlight=3433, dead=(), hidden=(), mode="cost",
                 switches=True, pays=True, asks=None, purchased=False, replace=()):
        self.decks, self.cost, self.starlight, self.dead, self.hidden = dict(decks), cost, starlight, set(dead), set(hidden)
        self.mode, self.opens_in, self.switches, self.pays, self.asks, self.purchased = mode, mode, switches, pays, asks, purchased
        self.state, self.open, self.picked, self.taps = "main", None, None, []
        self.replace, self.via, self.bought, self.made = list(replace), None, set(), []
        context.tasker.controller.post_click.side_effect = self.click
        context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
            lambda: np.full((720, 1280, 3), len(self.taps) * 20 % 256, np.uint8)
        context.run_recognition.side_effect = self.recognition
        monkeypatch.setattr(actions.shop, "option_lit", lambda image, box: self.lit(box))
        monkeypatch.setattr(actions.shop, "option_picked", lambda image, frame: self.picked is not None
                            and frame == actions.REPLACE_FRAMES[self.picked])
        monkeypatch.setattr(actions, "bar_dead", lambda image: set(self.dead))

    def lit(self, box):
        swap, counts = next(k for k, b in actions.REPLACE_PRICES.items() if b == box), self.decks[self.open]
        # skill 3 locked: the two swaps into it dim; no skill 1 card (#658 capture): the two swaps out of it dim
        return not (swap != "s1_s2" and counts[2] == 0) and not (swap != "s2_s3" and counts[0] == 0)

    def prices(self):
        return PRICES if self.via is not None else ID_PRICES[self.mode]

    def price(self):
        return self.prices()[self.picked]

    def click(self, x, y):
        at = (x, y)
        self.taps.append(at)
        if self.state == "main":
            column = next((c for c, _ in enumerate(self.replace, 1) if slot_tap(c) == at and c not in self.bought), None)
            if at == ID_SLOT and not self.purchased:
                self.state = "select"
            elif column is not None:
                self.state, self.open, self.picked, self.via, self.mode = "dialog", self.replace[column - 1], None, column, "cost"
            elif at == actions.BOTTOM_RIGHT:
                self.state = "leave"
        elif self.state == "leave":
            self.state = "left" if at == actions.LEAVE_CONFIRM else "main"
        elif self.state == "select":
            sinner = next((s for s in self.decks if portrait(s) == at), None)
            if sinner and sinner not in self.dead | self.hidden:
                self.state, self.open, self.picked, self.mode, self.via = "dialog", sinner, None, self.opens_in, None
            elif at == actions.BOTTOM_RIGHT:
                self.state = "main"  # Return
        elif self.state == "dialog":
            swap = next((k for k, p in actions.REPLACE_OPTIONS.items() if p == at), None)
            if swap and self.lit(actions.REPLACE_PRICES[swap]):
                self.picked = swap
            elif at == actions.PAY_SWITCH and self.switches and self.via is None:
                self.mode = "starlight" if self.mode == "cost" else "cost"
            elif at == actions.REPLACE_CONFIRM and self.picked:
                self.state = "ask"
            elif at == actions.REPLACE_CANCEL:
                self.state = "main"  # not back to select mode (#456 capture)
        elif self.state == "ask":
            if at == actions.REPLACE_CONFIRM:
                if self.pays:
                    if self.mode == "cost":
                        self.cost -= self.price()
                    else:
                        self.starlight -= self.price()
                    self.decks[self.open] = shop.after_swap(self.decks[self.open], self.picked, actions.data("shop.yaml")["skill_replacement"])
                    self.made.append(("search" if self.via is None else "replace", self.open, self.picked))
                    if self.via is None:
                        self.purchased = True
                    else:
                        self.bought.add(self.via)
                self.state = "main"
            elif at == actions.REPLACE_CANCEL:
                self.state, self.picked = "dialog", None
        return MagicMock()

    def shown(self):
        if self.state == "left":
            return {}
        if self.state in ("main", "leave", "select"):
            x = NAME_X[0]
            lines = [("ID Skill Search", (x + 5, 333, 95, 17)), ("??", (x + 30, 306, 40, 24))]
            lines += [("Purchased", (x + 10, 260, 80, 17))] if self.purchased else []
            for c, sinner in enumerate(self.replace, 1):
                lines += [(f"Replace {sinner}'s Skill", (NAME_X[c], 333, 131, 17)), ("??", (NAME_X[c] + 30, 306, 40, 24))]
                lines += [("Purchased", (NAME_X[c] + 10, 260, 80, 17))] if c in self.bought else []
            shown = {tuple(actions.OFFER_GRID): lines, tuple(actions.SHOP_COST): [(str(self.cost), (560, 120, 60, 30))],
                     tuple(actions.REFRESH["normal"][1]): [("15", (980, 145, 30, 20))]}
            if self.state == "select":  # the Refresh fee still reads: to_main must not take it for the main page
                shown[tuple(actions.SELECT_TITLE)] = [("Select a Sinner for Skill Replacement.", (450, 20, 380, 24))]
            if self.state == "leave":
                shown[tuple(actions.LEAVE_DIALOG)] = [("Leave the shop?", (480, 325, 300, 35))]
            return shown
        sinner, counts = self.open, self.decks[self.open]
        owned = "SKILL 1x{} SKILL 2x{} SKILL 3x{}".format(*counts)
        shown = {tuple(actions.DIALOG_TITLE): [("Skills Owned", (610, 104, 90, 14)), (owned, (617, 134, 216, 16))],
                 tuple(actions.REPLACE_TITLE): [(f"Replace {sinner}'s Skill", (213, 124, 355, 28))],
                 tuple(actions.REPLACE_OWNED): [("Skills Owned", (610, 104, 90, 14)), (owned, (617, 134, 216, 16))],
                 tuple(actions.REFRESH["normal"][1]): [("86", (1020, 140, 20, 20))],
                 **{tuple(box): [(str(self.prices()[k]), (box[0] + 20, 206, 30, 20))] for k, box in actions.REPLACE_PRICES.items()}}
        funds = self.cost if self.mode == "cost" else self.starlight
        if self.state == "dialog":
            shown[tuple(actions.REPLACE_COST)] = [(str(funds), (1035, 127, 60, 25))]
        else:
            unit = "Cost" if self.mode == "cost" else "Starlight"
            shown[tuple(actions.REPLACE_ASK)] = [(self.asks or f"Spend {self.price()} {unit} to replace this Skill?", (440, 493, 400, 16))]
            shown[tuple(actions.REPLACE_PREVIEW)] = [(f"{funds} ▸ {funds - self.price()}", (985, 127, 113, 25))]
        return shown

    def recognition(self, name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in self.shown().get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None


def searching(*entries, pay="cost", enabled=True, reserve=0):
    return shop_team({"reserve_cost": reserve, "skill_replacement": {
        **replacing(*entries), "id_skill_search": {"enabled": enabled, "pay": pay}}})


RYOSHU = skill_entry("Ryōshū", 1, 3, 2)


def test_id_skill_search_switched_off_taps_nothing_and_reads_nothing(context, monkeypatch):
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)})
    for team in (searching(RYOSHU, enabled=False), searching(skill_entry("Ryōshū", 3, 2, 1))):
        assert actions.Shop.id_skill_search(context, team, {}) is None
    assert game.taps == [] and not context.run_recognition.called


def test_id_skill_search_picks_a_sinner_swaps_and_checks_the_cost(context, monkeypatch):
    # The capture's swap: Ryōshū 2/3/1, s1_s3 for 240 Cost, 868 -> 628.
    game, lines, visit = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}), logged(monkeypatch), {}
    assert actions.Shop.id_skill_search(context, searching(RYOSHU), visit) == 1
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.REPLACE_OPTIONS["s1_s3"], actions.REPLACE_CONFIRM,
                         actions.REPLACE_CONFIRM]
    assert lines == ["shop: ID Skill Search: 'Ryōshū' counts not read this run, toward 1/3/2: try",
                     "shop: ID Skill Search: 'Ryōshū': Skills Owned 2/3/1, s1_s2 90, s2_s3 150, s1_s3 240, 868 Cost, "
                     "reserve 0: try s1_s3",
                     "shop: ID Skill Search: replaced 'Ryōshū' s1_s3 (skill 1 -> 3) for 240: 868 -> 628 Cost"]
    assert game.cost == 628 and actions.RUN["skills"] == {"Ryōshū": [1, 3, 2]} and visit["id_searched"]
    assert actions.Shop.id_skill_search(context, searching(RYOSHU), visit) is None and len(game.taps) == 5  # once a visit


def test_id_skill_search_switches_to_starlight_and_checks_the_slot_and_the_cost(context, monkeypatch):
    # The dialog opened on Cost in the capture (tests/screens/ShopIdSkillSearchDialog.png; whether the game keeps the payment
    # mode is unverified, #456); the double arrow switches it, and the prices must read 25/50/75 before
    # anything is judged. Starlight is out of reach after the swap (the slot no longer opens): the slot's Purchased and an
    # unchanged Cost are the check.
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight", reserve=900), {}) == 1
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.PAY_SWITCH, actions.REPLACE_OPTIONS["s1_s3"],
                         actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM]
    assert "shop: ID Skill Search: 'Ryōshū': Skills Owned 2/3/1, s1_s2 25, s2_s3 50, s1_s3 75, 3433 starlight "\
           "(no reserve): try s1_s3" in lines
    assert lines[-1] == ("shop: ID Skill Search: replaced 'Ryōshū' s1_s3 (skill 1 -> 3) for 75 starlight: 3433 -> 3358 starlight "
                         "(unread after the dialog), the slot reads Purchased, the Cost stays 868")
    assert (game.starlight, game.cost) == (3358, 868) and actions.RUN["skills"] == {"Ryōshū": [1, 3, 2]}


def test_id_skill_search_goes_down_the_list_to_the_first_sinner_with_a_feasible_swap(context, monkeypatch):
    # #456: Yi Sang dead (grey on the bar), Meursault read at his target, Gregor's dialog with no swap (2/3/0: skill 3
    # locked, skill 2 at its target): Cancel lands on the main page, so the slot is tapped again for Ryōshū.
    game = IdGame(context, monkeypatch, {"Yi Sang": (3, 2, 1), "Meursault": (2, 3, 1), "Gregor": (2, 3, 0), "Ryōshū": (2, 3, 1)},
                  dead=["Yi Sang"])
    actions.note_skills("Meursault", (1, 3, 2))
    team = searching(skill_entry("Yi Sang", 2, 2, 2), skill_entry("Meursault", 1, 3, 2), skill_entry("Gregor", 1, 3, 2), RYOSHU)
    visit, lines = {}, logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, team, visit) == 1
    assert game.taps == [ID_SLOT, portrait("Gregor"), actions.REPLACE_CANCEL, ID_SLOT, portrait("Ryōshū"),
                         actions.REPLACE_OPTIONS["s1_s3"], actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM]
    assert lines[:4] == ["shop: ID Skill Search: 'Yi Sang' is dead (grey on the shop's bar): skip",
                         "shop: ID Skill Search: 'Meursault' is at 1/3/2 (read this run): skip",
                         "shop: ID Skill Search: 'Gregor' counts not read this run, toward 1/3/2: try",
                         "shop: ID Skill Search: 'Ryōshū' counts not read this run, toward 1/3/2: try"]
    assert "shop: ID Skill Search: 'Gregor': no swap toward 1/3/2 is lit, priced and affordable in Cost: cancel" in lines
    assert visit["id_tried"] == ["Gregor", "Ryōshū"] and actions.RUN["skills"]["Gregor"] == [2, 3, 0]


def test_id_skill_search_keeps_the_cost_reserve(context, monkeypatch):
    # 300 Cost, reserve 100: 240 would break it; s1_s2 is not wanted from 2/3/1. Nothing paid, Cancel to the main page.
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, cost=300), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, reserve=100), {}) == 0
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.REPLACE_CANCEL] and game.cost == 300
    assert "shop: ID Skill Search: 'Ryōshū': Skills Owned 2/3/1, s1_s2 90, s2_s3 150, s1_s3 240, 300 Cost, reserve 100: try s1_s3" in lines


def test_too_little_starlight_is_no_swap(context, monkeypatch):
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, starlight=74), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight"), {}) == 0
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.PAY_SWITCH, actions.REPLACE_CANCEL]
    assert "shop: ID Skill Search: 'Ryōshū': no swap toward 1/3/2 is lit, priced and affordable in starlight: cancel" in lines
    assert (game.starlight, game.cost, game.state) == (74, 868, "main")


def test_a_payment_that_does_not_switch_is_cancelled(context, monkeypatch):
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, switches=False), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight"), {}) == 0
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.PAY_SWITCH, actions.REPLACE_CANCEL] and game.cost == 868
    assert ("shop: ID Skill Search: 'Ryōshū': prices s1_s2 90, s2_s3 150, s1_s3 240: the payment does not show starlight: "
            "cancel") in lines


def test_a_dialog_whose_prices_do_not_read_is_cancelled_without_a_switch(context, monkeypatch):
    # #264: a swap is feasible only with its price read. With none read the payment is unknown: the double arrow would flip a
    # dialog already on the wanted payment, so nothing is tapped but Cancel.
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}), logged(monkeypatch)
    shown = game.shown
    game.shown = lambda: {k: v for k, v in shown().items() if list(k) not in actions.REPLACE_PRICES.values()}
    assert actions.Shop.id_skill_search(context, searching(RYOSHU), {}) == 0
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.REPLACE_CANCEL] and game.mode == "cost"
    assert "shop: ID Skill Search: 'Ryōshū': prices s1_s2 None, s2_s3 None, s1_s3 None: the payment is unknown: cancel" in lines


def test_a_dialog_already_in_starlight_is_switched_back_for_cost(context, monkeypatch):
    # Whether the payment persists between openings is uncaptured: it is read every time, never assumed.
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, mode="starlight")
    assert actions.Shop.id_skill_search(context, searching(RYOSHU), {}) == 1
    assert actions.PAY_SWITCH in game.taps and (game.cost, game.starlight) == (628, 3433)


def short_dim_price(game, mode):
    """#658: in mode, the dim s1_s2 price reads a digit short (live: the red 90 as 9)."""
    shown, box = game.shown, actions.REPLACE_PRICES["s1_s2"]

    def misread():
        out = shown()
        if game.state == "dialog" and game.mode == mode and not game.lit(box):
            out[tuple(box)] = [(t[:-1], b) for t, b in out[tuple(box)]]
        return out
    game.shown = misread


NO_SKILL_1 = skill_entry("Ryōshū", 0, 1, 5)  # #658's team: Ryōshū 0/2/4 wants s2_s3 alone


def test_a_misread_dim_price_still_tells_cost_and_the_swap_is_made(context, monkeypatch):
    # #658 live: 9 dim, 150, 240 dim was "the payment is unknown: cancel"; 150 and 240 tell Cost.
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (0, 2, 4)}, cost=685), logged(monkeypatch)
    short_dim_price(game, "cost")
    assert actions.Shop.id_skill_search(context, searching(NO_SKILL_1), {}) == 1
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.REPLACE_OPTIONS["s2_s3"], actions.REPLACE_CONFIRM,
                         actions.REPLACE_CONFIRM]
    assert ("shop: ID Skill Search: 'Ryōshū': Skills Owned 0/2/4, s1_s2 9 dim, s2_s3 150, s1_s3 240 dim, 685 Cost, reserve 0: "
            "try s2_s3") in lines
    assert game.cost == 535 and actions.RUN["skills"] == {"Ryōshū": [0, 1, 5]}


def test_a_misread_dim_price_after_the_switch_still_shows_starlight(context, monkeypatch):
    # The switch waits for the prices to tell starlight: a dim 25 read as 2 is left out there too.
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (0, 2, 4)}, cost=685), logged(monkeypatch)
    short_dim_price(game, "starlight")
    assert actions.Shop.id_skill_search(context, searching(NO_SKILL_1, pay="starlight"), {}) == 1
    assert game.taps == [ID_SLOT, portrait("Ryōshū"), actions.PAY_SWITCH, actions.REPLACE_OPTIONS["s2_s3"],
                         actions.REPLACE_CONFIRM, actions.REPLACE_CONFIRM]
    assert ("shop: ID Skill Search: 'Ryōshū': Skills Owned 0/2/4, s1_s2 2 dim, s2_s3 50, s1_s3 75 dim, 3433 starlight "
            "(no reserve): try s2_s3") in lines
    assert (game.starlight, game.cost) == (3383, 685) and actions.RUN["skills"] == {"Ryōshū": [0, 1, 5]}


def test_id_skill_search_with_nobody_to_swap_leaves_by_return(context, monkeypatch):
    # The bar reads Gregor alive, but his portrait takes no tap: nobody else to try, the select mode is left by Return.
    game, lines = IdGame(context, monkeypatch, {"Gregor": (3, 2, 0)}, hidden=["Gregor"]), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(skill_entry("Gregor", 1, 3, 2)), {}) == 0
    assert game.taps == [ID_SLOT, portrait("Gregor"), actions.BOTTOM_RIGHT] and game.state == "main"
    assert lines[-2:] == ["shop: ID Skill Search: 'Gregor''s portrait opened no dialog",
                          "shop: ID Skill Search: no listed sinner has a feasible swap: Return"]


def test_id_skill_search_with_nobody_to_try_is_not_opened(context, monkeypatch):
    game, lines = IdGame(context, monkeypatch, {"Gregor": (3, 2, 0)}, dead=["Gregor"]), logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(skill_entry("Gregor", 1, 3, 2)), {}) is None
    assert game.taps == [] and lines[-1] == "shop: ID Skill Search: nobody to try: not opened"


def test_a_purchased_id_skill_search_is_never_opened(context, monkeypatch):
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, purchased=True), logged(monkeypatch)
    visit = {}
    assert actions.Shop.id_skill_search(context, searching(RYOSHU), visit) is None
    assert game.taps == [] and visit["id_searched"] and lines == ["shop: ID Skill Search: used already (Purchased): skip"]


def test_a_starlight_second_layer_that_does_not_ask_starlight_is_not_paid(context, monkeypatch):
    # The starlight second layer has no capture (#456); only "Spend <price> Starlight" with a matching preview is paid.
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, asks="Spend 75 Cost to replace this Skill?")
    lines = logged(monkeypatch)
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight"), {}) == 0
    assert game.taps.count(actions.REPLACE_CONFIRM) == 1 and (game.starlight, game.cost, game.state) == (3433, 868, "main")
    assert "shop: ID Skill Search: 'Ryōshū': no second confirm asking Starlight: back to the shop" in lines


def test_a_starlight_swap_without_purchased_forgets_the_counts(context, monkeypatch):
    game, lines = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, pays=False), logged(monkeypatch)
    visit = {}
    assert actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight"), visit) == 0
    assert lines[-1] == ("shop: ID Skill Search: 'Ryōshū' s1_s3 for 75 starlight: the slot reads no Purchased, the Cost "
                         "868 -> 868: the counts are not known")
    assert actions.RUN["skills"] == {} and visit["id_searched"]
    actions.Shop.id_skill_search(context, searching(RYOSHU, pay="starlight"), visit)  # after a refresh: not again
    assert game.taps.count(ID_SLOT) == 1


@pytest.mark.parametrize("recovered", [False, True])
def test_a_hand_back_at_the_paying_tap_does_not_pay_twice(context, monkeypatch, recovered):
    # #264 Implementation Decisions (the heal's rule, ADR 0007): the visit is marked before the paying tap. Here the tap is
    # lost to a popup (nothing paid, the slot not Purchased): the visit memory alone keeps the re-entered visit from paying,
    # a recovery in between too (#459 drops only the fusion scan).
    actions.RUN["team"] = searching(RYOSHU) | {"heal": "none"}
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)})
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a: False))
    click = game.click

    def popup_at_the_paying_tap(x, y):
        if (x, y) == actions.REPLACE_CONFIRM and game.state == "ask":
            raise actions.PageGone("Shop")
        return click(x, y)
    context.tasker.controller.post_click.side_effect = popup_at_the_paying_tap
    assert actions.Shop().run(context, argv())
    assert actions.RUN["shop"]["id_searched"] and game.state == "ask"
    context.tasker.controller.post_click.side_effect = click
    if recovered:
        actions.forget_game_state()
    lines = logged(monkeypatch)
    assert actions.Shop().run(context, argv())  # MirrorHub enters the same visit again: to_main cancels both layers
    assert game.taps.count(ID_SLOT) == 1 and game.cost == 868 and game.state == "left"
    assert game.taps[-4:-2] == [actions.REPLACE_CANCEL, actions.REPLACE_CANCEL]
    assert not [line for line in lines if "ID Skill Search" in line]


def test_to_main_leaves_the_select_mode_by_return_though_the_refresh_fee_reads(context, monkeypatch):
    # #456: in the select mode the Refresh fee still reads; MirrorHub's Shop node reads the title there (pipeline), and
    # to_main taps Return.
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)})
    game.state = "select"
    assert actions.Shop.to_main(context)
    assert game.taps == [actions.BOTTOM_RIGHT] and game.state == "main"


def test_the_step_runs_after_the_heal_and_again_after_a_refresh(context, monkeypatch):
    # #264 時機: both times of the step; the order inside it is the walk below.
    Game(context, monkeypatch, [("Gregor", (3, 2, 0))], 350, refreshed=[("Rodion", (3, 2, 1))])
    steps = []
    monkeypatch.setattr(actions.Shop, "skill_step", staticmethod(lambda *a: steps.append("skill_step") and 0))
    monkeypatch.setattr(actions.Shop, "buy_offers", staticmethod(lambda *a: steps.append("buy_offers") and 0))
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    assert actions.Shop.buy(context, buying(wants(9053), shop_refresh_normal=1), visit)
    assert steps == ["buy_offers", "skill_step", "buy_offers"]


FRESH = {"Ryōshū": (3, 2, 1), "Meursault": (3, 2, 1)}


@pytest.mark.parametrize("replace, cost, made", [
    # #264 先後's examples, list 1 Ryōshū, 2 Meursault, paying Cost: s1_s2 is 45 in a Replace slot, 90 in ID Skill Search.
    (["Ryōshū", "Meursault"], 180, [("replace", "Ryōshū"), ("search", "Ryōshū"), ("replace", "Meursault")]),  # three swaps
    (["Ryōshū", "Meursault"], 150, [("replace", "Ryōshū"), ("search", "Ryōshū")]),  # two: Ryōshū twice, Meursault not
    (["Ryōshū", "Meursault"], 60, [("replace", "Ryōshū")]),  # one: Ryōshū's slot
    (["Meursault"], 300, [("search", "Ryōshū"), ("replace", "Meursault")]),  # no Replace Ryōshū: ID Skill Search first
])
def test_the_step_finishes_each_listed_sinner_before_the_next(context, monkeypatch, replace, cost, made):
    game = IdGame(context, monkeypatch, FRESH, cost=cost, replace=replace)
    assert actions.Shop.skill_step(context, searching(RYOSHU_TWICE, MEURSAULT_ONCE), {}) == len(made)
    assert [(how, sinner) for how, sinner, _ in game.made] == made


def test_the_order_holds_when_id_skill_search_pays_starlight(context, monkeypatch):
    # #264 先後: starlight spends no Cost; the order is the same as with Cost enough for every swap.
    game = IdGame(context, monkeypatch, FRESH, cost=100, replace=["Ryōshū", "Meursault"])
    assert actions.Shop.skill_step(context, searching(RYOSHU_TWICE, MEURSAULT_ONCE, pay="starlight"), {}) == 3
    assert [(how, sinner) for how, sinner, _ in game.made] == [("replace", "Ryōshū"), ("search", "Ryōshū"), ("replace", "Meursault")]
    assert (game.cost, game.starlight) == (10, 3408)


def test_a_search_with_no_swap_for_its_sinner_goes_down_the_list_past_a_replace_slot_to_come(context, monkeypatch):
    # #264 先後: opened on Ryōshū, whose dialog has no swap (2/3/0: skill 3 locked, skill 2 at its target), ID Skill Search
    # passes Meursault, whose own Replace slot on this page comes first at half the price, and swaps Yi Sang.
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 0), "Meursault": (3, 2, 1), "Yi Sang": (3, 2, 1)}, replace=["Meursault"])
    lines = logged(monkeypatch)
    team = searching(RYOSHU, MEURSAULT_ONCE, skill_entry("Yi Sang", 2, 3, 1))
    assert actions.Shop.skill_step(context, team, {}) == 2
    assert [(how, sinner) for how, sinner, _ in game.made] == [("search", "Yi Sang"), ("replace", "Meursault")]
    assert game.taps[:4] == [ID_SLOT, portrait("Ryōshū"), actions.REPLACE_CANCEL, ID_SLOT] and portrait("Meursault") not in game.taps
    assert "shop: ID Skill Search: 'Meursault' has a Replace slot on this page, used first: skip" in lines


def test_a_search_never_goes_back_up_the_list(context, monkeypatch):
    # #264 先後: on Meursault's turn ID Skill Search starts from him; Ryōshū, listed before him, was passed already.
    IdGame(context, monkeypatch, FRESH, replace=["Ryōshū"])
    calls = []
    monkeypatch.setattr(actions.Shop, "replace_skill", staticmethod(lambda *a: "handled"))
    monkeypatch.setattr(actions.Shop, "id_skill_search", staticmethod(
        lambda context, team, visit, listed, waiting, offers: calls.append([e["sinner"] for e in listed]) or 0))
    visit = {"id_tried": ["Ryōshū"]}  # his turn came after his slot; as if it opened nothing for him
    actions.Shop.skill_step(context, searching(RYOSHU_TWICE, MEURSAULT_ONCE), visit)
    assert calls == [["Meursault"]]


def test_the_search_judges_on_the_counts_the_replace_slot_left(context, monkeypatch):
    # Ryōshū's Replace slot took him to 1/3/2: ID Skill Search takes no turn on him, and nobody else is listed.
    game = IdGame(context, monkeypatch, {"Ryōshū": (2, 3, 1)}, replace=["Ryōshū"])
    assert actions.Shop.skill_step(context, searching(RYOSHU), {}) == 1
    assert game.made == [("replace", "Ryōshū", "s1_s3")] and ID_SLOT not in game.taps


def test_a_slot_used_this_visit_is_not_used_again_after_a_refresh(context, monkeypatch):
    # Each slot once a visit. 60 Cost: Ryōshū's slot (45); ID Skill Search on him (90) and, once Meursault's slot (45) found
    # nothing affordable, on Meursault, both cancelled. The pass after a sale (more Cost) skips Ryōshū's bought slot and the
    # ID Skill Search that tried both, and opens Meursault's slot again: the bot cancelled it before any Confirm.
    game = IdGame(context, monkeypatch, FRESH, cost=60, replace=["Ryōshū", "Meursault"])
    team, visit = searching(RYOSHU_TWICE, MEURSAULT_ONCE), {}
    assert actions.Shop.skill_step(context, team, visit) == 1
    game.cost = 300
    assert actions.Shop.skill_step(context, team, visit) == 1
    assert [(how, sinner) for how, sinner, _ in game.made] == [("replace", "Ryōshū"), ("replace", "Meursault")]
    assert game.taps.count(ID_SLOT) == 2 and visit["id_tried"] == ["Ryōshū", "Meursault"]
    assert visit["skill_tapped"] == ["Ryōshū", "Meursault"]


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


HARD_ALIVE = ["Ryōshū", "Meursault", "Gregor"]  # #453's and #456's runs: the other nine dead


@pytest.mark.parametrize("name, alive", [
    *[(n, list(actions.battle.SINNERS)) for n in ("Shop", "ShopHeal", "SuperShop")],
    *[(n, HARD_ALIVE) for n in ("ShopReplaceSkillCancelled", "ShopReplaceSkillDone", "ShopReplaceSkillRefreshed",
                                "ShopReplaceSkillClippedGregor", "ShopReplaceSkillClippedMeursault", "SuperShopIdSkillSearch",
                                "SuperShopScrolled", "ShopIdSkillSearchDone", "ShopIdSkillSearchSelect")],
])
def test_the_dead_are_the_grey_portraits_of_the_shops_main_page(name, alive):
    # Every capture of tests/screens that shows the shop's main page (or the select mode over it): the bar the heal and ID
    # Skill Search read. A dead portrait reads up to 51, over the old 30.
    image = capture(name)
    assert [s for s in actions.battle.SINNERS if s not in actions.bar_dead(image)] == alive


def test_the_grey_portrait_sweep_over_the_shop_captures():
    # CODING_STANDARDS' sweep: bar_dead over all 33 shop captures of tests/screens. On the 12 main pages (the test above) it
    # reads the dead right. Over a dialog the bar is shaded and it names Faust alone (62-64; on the HARD ones nine are dead),
    # or nobody (#658's): wrong both ways, and neither the heal nor ID Skill Search reads the bar there. The fuse and purchase
    # pages name nobody. Off the shop (134 of the other 197 1280x720 screens name someone) there is no bar at that place, and
    # it is never asked.
    main = {"Shop", "ShopHeal", "SuperShop", "ShopReplaceSkillCancelled", "ShopReplaceSkillDone", "ShopReplaceSkillRefreshed",
            "ShopReplaceSkillClippedGregor", "ShopReplaceSkillClippedMeursault", "SuperShopIdSkillSearch", "SuperShopScrolled",
            "ShopIdSkillSearchDone", "ShopIdSkillSearchSelect"}
    shop_screens = {stem: image for stem, image in screens_1280() if stem.startswith(("Shop", "SuperShop"))}
    assert len(shop_screens) == 33 and main <= set(shop_screens)
    off_main = {stem: sorted(actions.bar_dead(image)) for stem, image in shop_screens.items() if stem not in main}
    assert {stem: dead for stem, dead in off_main.items() if dead} == {
        stem: ["Faust"] for stem in ("ShopIdSkillSearchAll", "ShopIdSkillSearchConfirm", "ShopIdSkillSearchConnecting",
                                     "ShopIdSkillSearchDialog", "ShopIdSkillSearchPicked", "ShopIdSkillSearchStarlight",
                                     "ShopReplaceSkillConfirm", "ShopReplaceSkillConnecting", "ShopReplaceSkillDimmed",
                                     "ShopReplaceSkillPickedLeft")}


def screens_1280():
    for path in sorted(SCREENS.glob("*.png")):
        img = Image.open(path)
        if img.size == (1280, 720):
            yield path.stem, np.asarray(img.convert("RGB"))[:, :, ::-1]


def test_the_lit_price_sweep_over_tests_screens():
    # CODING_STANDARDS' sweep: option_lit is asked only on the dialog's first layer, after its title named the slot's sinner.
    # Over every 1280x720 screen of tests/screens (230 of them), a price box reads lit on the dialogs and on 9 other screens,
    # none a shop page: orange art where a box sits (a battle's skill card, a map node, a gift). The second layer (Confirm,
    # Connecting) reads none: its skill cards cover the prices. #456's ID Skill Search dialogs (live 2026-11-07, the same
    # dialog with prices 90/150/240 in Cost or 25/50/75 in Starlight) are dialogs too and read as the captures show:
    # Gregor's skill 3 is locked, so only s1_s2 is lit; Ryōshū's three are. #658's Ryōshū has no skill 1: only s2_s3 is lit.
    id_dialogs = {"ShopIdSkillSearchAll": ["s1_s2", "s2_s3", "s1_s3"], "ShopIdSkillSearchDimmed": ["s2_s3"],
                  **{f"ShopIdSkillSearch{n}": ["s1_s2"] for n in ("Dialog", "Picked", "Starlight")}}
    hits = {stem: [k for k, box in actions.REPLACE_PRICES.items() if shop.option_lit(image, box)] for stem, image in screens_1280()}
    assert {k: hits[k] for k in id_dialogs} == id_dialogs
    assert {k: v for k, v in hits.items() if v and k not in DIALOGS and k not in id_dialogs} == {
        "BattleTurnFocused": ["s1_s2"], "BossGiftTrialsHard": ["s2_s3"], "FormationDetails": ["s2_s3"],
        "LuxConsecThread10Open": ["s1_s2"], "LuxConsecThread2Open": ["s1_s2"], "LuxTeamSelect": ["s1_s2"],
        "LuxTeamSelectChain": ["s1_s2"], "MapZoomed": ["s2_s3"], "StartingGiftPicked": ["s1_s2", "s2_s3", "s1_s3"]}


def test_the_picked_frame_sweep_over_tests_screens():
    # CODING_STANDARDS' sweep: option_picked is asked only after an option's tap on the dialog. Over every 1280x720 screen
    # of tests/screens, a frame reads picked on the three Picked captures, the one tapped, and on one battle screen (an
    # orange-lit skill where the right frame's edge runs); no shop page. #456's ID Skill Search dialog with s1_s2 tapped
    # (ShopIdSkillSearchPicked) reads its tapped frame.
    hits = {stem: [k for k, frame in actions.REPLACE_FRAMES.items() if shop.option_picked(image, frame)] for stem, image in screens_1280()}
    assert {k: v for k, v in hits.items() if v} == {"BattleTurnFocused": ["s1_s3"], "ShopIdSkillSearchPicked": ["s1_s2"],
                                                     "ShopReplaceSkillPickedLeft": ["s1_s2"],
                                                     "ShopReplaceSkillPickedMiddle": ["s2_s3"], "ShopReplaceSkillPickedRight": ["s1_s3"]}
