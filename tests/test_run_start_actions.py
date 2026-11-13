"""A run's start actions (agent/run_start_actions.py): the plan, the team, starlight and its graces, the starting gift and its search, and the theme pack.

Split out of tests/test_actions.py (#713); the fake Maa context and the helpers other files share stay there."""

from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
import run_start_actions
import gifts
import recovery
import gift_search
import pack_cover
import run_start
import settlement
from settings import gift_tables
from agent_patch import patch_all
import test_actions

from test_actions import SCREENS, argv, listed, moved, no_fixed_wait, page, page_until, screens, taps

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def bgr(path):
    """A capture as MaaFramework hands it to the agent: BGR."""
    return np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1]


def test_plan_run_waits_for_the_enter_dialog_after_pressing_enter(context, clock, monkeypatch):
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 3, "hard_from_floor": 1, "gift_list": "default", "enabled": True}
    run = {"runs": 0, "stop_when_weekly_bonus_out": False, "difficulty": "normal", "target_floor": 5}
    patch_all(monkeypatch, "load_settings", lambda root, need_team=False: {"run": run, "teams": [team], "gift_lists": []})
    patch_all(monkeypatch, "pick_team", lambda teams, difficulty: team)
    monkeypatch.setattr(settlement, "runs_done", lambda done, limit: False)
    monkeypatch.setattr(recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(recovery, "floor_limit", lambda runs, team, target: 1800)
    actions.TASK["modules"] = 20  # read on the Drive page (#369)
    page(context, {(400, 325, 480, 45): lambda clicks, looks: "Will you enter X?" if clicks and looks >= 3 else None})
    assert run_start_actions.PlanRun().run(context, argv())
    assert taps(context) == [(1108, 494)]
    no_fixed_wait(clock)


@pytest.mark.parametrize(("setting", "expected"), [("auto", "normal"), ("hard", "hard")])
def test_a_planned_run_of_a_team_that_never_switches_to_hard(context, clock, monkeypatch, setting, expected):
    # #137: auto with weekly bonuses left decides hard, but this team's switch to hard is off: the run is NORMAL.
    # Only the global "hard" makes it HARD (every floor, hard_wanted).
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 0, "hard_from_floor": None, "gift_list": "default", "enabled": True}
    run = {"runs": None, "stop_when_weekly_bonus_out": False, "difficulty": setting, "target_floor": 5}
    patch_all(monkeypatch, "load_settings", lambda root, need_team=False: {"run": run, "teams": [team], "gift_lists": []})
    patch_all(monkeypatch, "pick_team", lambda teams, difficulty: team)
    monkeypatch.setattr(run_start, "run_difficulty", lambda setting, weekly, target: "hard")
    monkeypatch.setattr(recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(recovery, "floor_limit", lambda runs, team, target: 1800)
    actions.TASK["modules"] = 20  # read on the Drive page (#369)
    page(context, {})
    run_start_actions.PlanRun().run(context, argv())
    assert actions.RUN["difficulty"] == expected


def team_picker(context, title, after_confirm):
    """The team list shows TEAMS #3 at y 390; title(clicks, looks) is the card's title text, after_confirm(clicks, looks) the next page."""
    page(context, {tuple(run_start_actions.TEAM_LIST): [("TEAMS #3", (100, 380, 80, 20))], (220, 112, 210, 26): title,
                   (1160, 522, 60, 34): "63", (400, 230, 480, 90): after_confirm})


def infinity_switch(context, monkeypatch, takes):
    """The entry page's Parallel Superposition Mode reads ON until a tap on INFINITY MIRROR takes (if it does)."""
    taps, stops = [], []
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: stops.append(reason) or False)

    def ocr(context, image, roi, only_rec=False):
        if roi == run_start_actions.INFINITY_TITLE:
            # As the bot's MaaFramework log read the entry page live, OFF and the red ON (2026-11-08)
            text = "Parallel Superposition Mode : OFF" if takes and taps else "PParallel Superposition Mode : oN "
            return [(text, (894, 333, 316, 17))]
        return []
    patch_all(monkeypatch, "ocr", ocr)
    return taps, stops, run_start_actions.ParallelModeOff().run(context, None)


def test_a_parallel_superposition_switch_left_on_is_switched_off(context, clock, monkeypatch):
    # #94: the bot never plays past floor 5.
    taps, stops, result = infinity_switch(context, monkeypatch, takes=True)
    assert result is True and taps == [run_start_actions.INFINITY_BUTTON] and stops == []


def test_a_parallel_superposition_switch_that_stays_on_stops_the_task(context, clock, monkeypatch):
    taps, stops, result = infinity_switch(context, monkeypatch, takes=False)
    assert result is False and taps == [run_start_actions.INFINITY_BUTTON] * 2 and len(stops) == 1


def test_select_team_waits_for_the_title_after_the_tap_and_for_the_page_after_confirm(context, clock, monkeypatch):
    patch_all(monkeypatch, "scroll", lambda *a: None)  # the drag to the top has its own waits
    actions.RUN["team"] = {"game_team": 3}
    team_picker(context, lambda clicks, looks: "TEAMS #1" if looks < 4 else "TEAMS #3",
                lambda clicks, looks: "lower than the recommended level" if clicks >= 2 else None)
    assert run_start_actions.SelectTeam().run(context, argv())
    assert taps(context) == [(130, 390), (1145, 587)]
    no_fixed_wait(clock)
    assert context.tasker.controller.post_screencap.call_count > 4  # looked until the title changed


def test_select_team_taps_the_card_again_when_the_title_never_changed(context, clock):
    actions.RUN["team"] = {"game_team": 3}
    team_picker(context, lambda clicks, looks: "TEAMS #1" if clicks < 2 else "TEAMS #3",
                lambda clicks, looks: "recommended level" if clicks >= 3 else None)
    assert run_start_actions.SelectTeam().run(context, argv())
    assert taps(context) == [(130, 390), (130, 390), (1145, 587)]


def team_list(context, monkeypatch, first, title, blank=0):
    """A picker list of TEAMS #1-#20 showing 7 rows from #first (the 7th cut off at the edge), its title TEAMS #title
    until a row is tapped; the OCR boxes move by a pixel from one look to the next, as live (2026-10-27). blank: looks
    that read no row. Returns the state: the row numbers tapped and the drags (dy > 0: the content down, to the top)."""
    state = {"first": first, "title": title, "tapped": [], "drags": [], "looks": 0}
    rows = lambda: {n: 309 + 36 * (n - state["first"]) for n in range(state["first"], state["first"] + 7)}

    def ocr(context, image, roi, only_rec=False):
        if roi == run_start_actions.TEAM_LIST:
            state["looks"] += 1
            if state["looks"] <= blank:
                return []
            return [(f"TEAMS #{n}", (100, y - 10 + state["looks"] % 2, 80, 20)) for n, y in rows().items()]
        return [(f"TEAMS #{state['title']}", tuple(roi))] if roi == run_start_actions.TEAM_TITLE else []

    def scroll(context, x, y, dx, dy):
        state["drags"].append(dy)
        state["first"] = min(max(state["first"] - 4 * (1 if dy > 0 else -1), 1), 14)  # 140 px = 4 rows

    def click(x, y):
        if x == 130:
            n = next((n for n, ry in rows().items() if abs(ry - y) < 18), None)
            state["tapped"].append(n)
            state["title"] = n or state["title"]
        return MagicMock()
    patch_all(monkeypatch, "ocr", ocr)
    patch_all(monkeypatch, "scroll", scroll)
    context.tasker.controller.post_click.side_effect = click
    return state


TEAM_PAGES = {"mirror": run_start_actions.SelectTeam, "luxcavation": run_start_actions.LuxSelectTeam}


@pytest.mark.parametrize("caller", TEAM_PAGES)
def test_a_team_already_on_the_title_is_neither_dragged_to_nor_tapped(context, clock, monkeypatch, caller):
    actions.RUN["team"] = {"game_team": 3}
    state = team_list(context, monkeypatch, first=1, title=3)
    assert TEAM_PAGES[caller]().run(context, argv())
    assert state["tapped"] == [] and state["drags"] == []


@pytest.mark.parametrize("caller", TEAM_PAGES)
def test_a_team_row_on_show_is_tapped_without_a_drag(context, clock, monkeypatch, caller):
    # Live 2026-10-27: TEAMS #3 on show from the start, yet the list was dragged 10 times first (to the top it was at).
    actions.RUN["team"] = {"game_team": 3}
    state = team_list(context, monkeypatch, first=1, title=1)
    assert TEAM_PAGES[caller]().run(context, argv())
    assert state["tapped"] == [3] and state["drags"] == []


@pytest.mark.parametrize("caller", TEAM_PAGES)
@pytest.mark.parametrize(("first", "target", "towards"), [(1, 12, "down"), (11, 2, "up")])
def test_a_team_row_off_show_is_scrolled_to_from_where_the_list_is(context, clock, monkeypatch, caller, first, target, towards):
    # #226: the list opens wherever it was left; it moves from there towards the row, never to the top first.
    actions.RUN["team"] = {"game_team": target}
    state = team_list(context, monkeypatch, first=first, title=first)
    assert TEAM_PAGES[caller]().run(context, argv())
    assert state["tapped"] == [target]
    assert state["drags"] and all((d < 0) == (towards == "down") for d in state["drags"])
    assert len(state["drags"]) <= 3  # 4 rows a drag


@pytest.mark.parametrize("caller", TEAM_PAGES)
def test_a_team_list_that_reads_no_row_is_dragged_to_its_top_first(context, clock, monkeypatch, caller):
    # No row read: where the list is is unknown, so it goes to the top, as before #226's fix; the boxes moving by a
    # pixel at rest do not keep it dragging.
    actions.RUN["team"] = {"game_team": 8}
    state = team_list(context, monkeypatch, first=11, title=11, blank=1)
    assert TEAM_PAGES[caller]().run(context, argv())
    assert state["tapped"] == [8]
    drags = state["drags"]
    top = max(i for i, d in enumerate(drags) if d > 0)
    assert all(d > 0 for d in drags[:top + 1]) and all(d < 0 for d in drags[top + 1:])  # all the way up, then down
    assert len(drags) <= 6


def test_select_team_makes_a_plan_for_an_abandoned_empty_run_instead_of_backing_out(context, clock, monkeypatch):
    # #128 (live 2026-10-18): Resume on a run paused before team selection reaches the picker with no plan in memory;
    # backing out to the entry page, which only offers Resume, looped every 8 s.
    team = {"id": 1, "name": "t", "game_team": 3, "guard_turns": 0, "gift_list": "default", "enabled": True, "usage": "any"}
    patch_all(monkeypatch, "load_settings", lambda root, need_team=False: {"run": {"difficulty": "normal", "target_floor": 5}, "teams": [team], "gift_lists": []})
    actions.RUN.clear()
    team_picker(context, "TEAMS #3", lambda clicks, looks: "recommended level" if clicks else None)
    assert run_start_actions.SelectTeam().run(context, argv())
    assert taps(context) == [(1145, 587)]  # TEAMS #3 already on the title: Confirm, no back arrow (97, 42)
    assert actions.RUN["team"] == {**team, "keyword": "Burn", "list": gifts.resolve_list("default", [])}


def test_starlight_enter_waits_for_the_confirm_dialog(context, clock, monkeypatch):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "skip"}}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"priority": [], "levels": []})  # nothing to buy
    page(context, {tuple(run_start_actions.STARLIGHT_AVAILABLE): "63",
                   (480, 210, 320, 35): lambda clicks, looks: "Continue with selected effects?" if clicks and looks >= 3 else None})
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(1195, 672)]
    no_fixed_wait(clock)


def test_starlight_confirm_waits_for_the_starting_gift_page(context, clock, monkeypatch):
    actions.RUN["settings"] = {}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"convert_leftover": False})
    page(context, {(660, 395, 320, 90): "Any unspent Starlight will be added to your Dungeon clear rewards",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks and looks >= 4 else None})
    assert run_start_actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(738, 530)]
    no_fixed_wait(clock)


def starlight_page(context, available, owned):
    """The starlight page with Available and the Owned box as texts or f(clicks, looks); card 1's price reads 10."""
    page(context, {tuple(run_start_actions.STARLIGHT_AVAILABLE): available, tuple(run_start_actions.STARLIGHT_OWNED): owned,
                   (250, 149, 80, 28): "10", (480, 210, 320, 35): "Continue with selected effects?"})


def buy_grace_1(monkeypatch, unaffordable):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": unaffordable}}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"priority": [1], "levels": ["base"] + ["none"] * 9})


def test_a_configured_grace_is_bought_with_owned_starlight_when_available_falls_short(context, clock, monkeypatch):
    # #96: the user chose the grace, so owned starlight pays the 5 that Available (5 of 10) cannot (live: "0+5").
    buy_grace_1(monkeypatch, "stop")
    starlight_page(context, lambda clicks, looks: "5" if clicks == 0 else "0+5", lambda clicks, looks: "4035" if clicks == 0 else "4035-5")
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(230, 252), (1195, 672)]
    assert actions.RUN["starlight_unspent"] == 0


def test_a_grace_tap_waits_for_available_to_drop_not_a_fixed_1_s(context, clock, monkeypatch):
    # #58: the card's tap slept 1 s before Available was read; it is read every 0.2 s now, at most that 1 s.
    buy_grace_1(monkeypatch, "stop")
    starlight_page(context, lambda clicks, looks: "20" if clicks == 0 else "10", "0")
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(230, 252), (1195, 672)] and actions.RUN["starlight_unspent"] == 10
    no_fixed_wait(clock)


def test_a_grace_level_tap_waits_for_the_price_not_a_fixed_1_s(context, clock, monkeypatch):
    # #58: the + button's tap slept 1 s before the price was read again.
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "stop"}}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"priority": [1], "levels": ["plus"] + ["none"] * 9})
    page(context, {tuple(run_start_actions.STARLIGHT_AVAILABLE): lambda clicks, looks: "30" if clicks < 2 else "10",
                   tuple(run_start_actions.STARLIGHT_OWNED): "0", (250, 149, 80, 28): lambda clicks, looks: "10" if clicks == 0 else "20",
                   (480, 210, 320, 35): "Continue with selected effects?"})
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(188, 355), (230, 252), (1195, 672)]
    no_fixed_wait(clock)


def test_graces_beyond_available_and_owned_follow_starlight_unaffordable_skip(context, clock, monkeypatch):
    buy_grace_1(monkeypatch, "skip")
    starlight_page(context, "5", "2")
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(1195, 672)]  # nothing bought, Enter only


def test_graces_beyond_available_and_owned_follow_starlight_unaffordable_stop(context, clock, monkeypatch):
    stopped = []
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: stopped.append(reason) or False)
    buy_grace_1(monkeypatch, "stop")
    starlight_page(context, "5", "2")
    assert run_start_actions.BuyStarlight().run(context, argv()) is False
    assert stopped == ["a planned grace is unaffordable"] and taps(context) == []


def test_the_confirm_dialog_is_confirmed_when_the_graces_spent_owned_starlight(context, clock, monkeypatch):
    # #96: "-60" in the dialog's Owned box is the consented spend, not a reason to cancel.
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"convert_leftover": False})
    page(context, {(870, 165, 85, 25): "-60", (660, 395, 320, 90): "Any unspent Starlight will be added",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks else None})
    assert run_start_actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(738, 530)]


def test_convert_starlight_to_cost_is_switched_without_a_fixed_wait(context, clock, monkeypatch):
    # #115: the checkbox tap slept 1 s; the note under it says when it took.
    actions.RUN["settings"] = {}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"convert_leftover": True})
    page(context, {tuple(run_start_actions.STARLIGHT_NOTE): lambda clicks, looks: "Coverts any remaining Starlight" if clicks and looks >= 3 else "Any unspent Starlight will be added",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks >= 2 else None})
    assert run_start_actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(727, 363), (738, 530)]
    no_fixed_wait(clock)


SELECT_COUNT, SEARCH_SWITCH, GIFT_POPUP = (990, 565, 190, 45), (1100, 145, 85, 28), (520, 160, 240, 40)


def starting_gift_page(context, selects_at=2, rules=None):
    """The Burn cabinet is on the page; Select reads 0/1, 1/1 after selects_at taps, and Select (the tap after) pops the GET window up."""
    page(context, {SELECT_COUNT: lambda clicks, looks: "1/1" if clicks >= selects_at else "0/1",
                   (145, 145, 590, 430): [("Burn", (200, 300, 60, 20))],
                   tuple(run_start_actions.STARTING_GIFT_HEADER): lambda clicks, looks: "Selected E.G.O Gift" if clicks <= selects_at else None,
                   GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks > selects_at else None,
                   SEARCH_SWITCH: "ON", **(rules or {})})
    actions.RUN["team"] = {"keyword": "Burn", "gift_search": {"enabled": True, "gifts": [{"name": "x"}]}}


def test_the_starting_gift_is_picked_without_a_fixed_wait(context, clock):
    starting_gift_page(context)
    assert run_start_actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(230, 385), (970, 262), (1080, 587)]  # cabinet, first gift, Select
    assert sum(clock) < 1.5


def test_the_gift_search_switch_is_waited_for_not_slept_on(context, clock):
    # Select already reads 1/1 (the gift is picked); the switch reads OFF until it is tapped and the page has looked again.
    starting_gift_page(context, selects_at=0, rules={SEARCH_SWITCH: lambda clicks, looks: "OFF" if looks < 4 else "ON"})
    assert run_start_actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(1140, 158), (1080, 587)]  # the switch, then Select
    assert sum(clock) < 1.5


def test_a_planned_run_plays_the_main_keyword_of_the_teams_list(context, clock, monkeypatch):
    settings = {**listed("Bleed"), "run": {"runs": None, "stop_when_weekly_bonus_out": False, "difficulty": "normal", "target_floor": 5}}
    patch_all(monkeypatch, "load_settings", lambda root, need_team=False: settings)
    monkeypatch.setattr(recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(recovery, "floor_limit", lambda runs, team, target: 1800)
    monkeypatch.setattr(settlement, "runs_done", lambda done, limit: False)
    actions.RUN.clear()
    assert actions.current_run(context)["team"]["keyword"] == "Bleed"  # the agent restarted mid-run
    actions.RUN.clear()
    actions.TASK["modules"] = 20  # read on the Drive page (#369)
    page(context, {})
    run_start_actions.PlanRun().run(context, argv())
    assert actions.RUN["team"]["keyword"] == "Bleed"


def test_the_starting_gift_comes_from_the_cabinet_of_the_lists_first_keyword(context, clock):
    settings = listed("Bleed")
    starting_gift_page(context, rules={(145, 145, 590, 430): [("Burn", (200, 300, 60, 20)), ("Bleed", (200, 400, 60, 20))]})
    actions.RUN["team"] = {**actions.RUN["team"], **actions.run_team(settings, settings["teams"][0])}
    assert run_start_actions.PickStartingGift().run(context, argv())
    assert taps(context)[0] == (230, 485)  # the Bleed label's centre, 75 px down


GIFT_NAME = (320, 405, 180, 80)


def test_an_acquired_gift_popup_is_closed_and_waited_out_without_a_fixed_delay(context, clock):
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks == 0 else None, GIFT_NAME: "Wound Clerid"})
    assert run_start_actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]
    no_fixed_wait(clock)


SPIDERWEB = {"name": "Spiderweb Entangled in Red", "keyword": "Burn", "tier": 2}


def search_page(context, rules=None):
    """The search page with Spiderweb picked (Select 1/1, 70 starlight): Select asks to consume, Confirm shows the GET window."""
    page(context, {tuple(run_start_actions.SEARCH_COUNT): "Select 1/1", (922, 205, 270, 34): "Spiderweb Entangled in Red",
                   tuple(run_start_actions.SEARCH_OWNED[0]): "1542-70", tuple(run_start_actions.SEARCH_OWNED[1]): "1472",
                   tuple(run_start_actions.SEARCH_DIALOG): lambda clicks, looks: "Consume 70 Starlight to search and obtain these E.G.O Gifts?" if clicks == 1 else None,
                   GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks >= 2 else None, **(rules or {})})
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [SPIDERWEB]}}


def test_the_search_is_bought_with_looks_at_the_dialog_and_the_popup_not_fixed_waits(context, clock):
    search_page(context)
    assert run_start_actions.GiftSearch().run(context, argv())
    assert taps(context) == [run_start_actions.SEARCH_SELECT, run_start_actions.SEARCH_DIALOG_BUTTONS["confirm"]]
    no_fixed_wait(clock)


def test_the_owned_starlight_before_the_search_leaves_out_the_starlight_not_spent_on_graces(context, clock):
    # #73 (live 2026-10-17): the Owned box read 1542 with 1482 on the main page: the team's unspent Starlight Bonus 60 is in it.
    search_page(context)
    actions.RUN["starlight_unspent"] = 60
    run_start_actions.GiftSearch().run(context, argv())
    assert actions.RUN["gift_search"] == {"gifts": ["Spiderweb Entangled in Red"], "starlight": 70, "owned_before": 1482, "owned_after": 1412}


def test_the_owned_starlight_is_as_read_when_nothing_was_left_unspent(context, clock):
    search_page(context)
    run_start_actions.GiftSearch().run(context, argv())
    assert actions.RUN["gift_search"]["owned_before"] == 1542


def test_refusing_the_search_waits_for_the_forgo_dialog(context, clock):
    page(context, {tuple(run_start_actions.SEARCH_COUNT): "Select 0/3", (480, 330, 320, 35): lambda clicks, looks: "Forgo" if clicks else None})
    actions.RUN["team"] = {"gift_search": {"enabled": False, "gifts": []}}
    assert run_start_actions.GiftSearch().run(context, argv())
    assert taps(context) == [run_start_actions.SEARCH_REFUSE]
    no_fixed_wait(clock)


def test_the_unspent_starlight_is_kept_for_the_search_unless_it_is_converted(context, clock, monkeypatch):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "skip"}}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"priority": [], "levels": [], "convert_leftover": True})
    page(context, {tuple(run_start_actions.STARLIGHT_AVAILABLE): "63", (660, 395, 320, 90): "Any unspent Starlight will be added"})
    run_start_actions.BuyStarlight().run(context, argv())
    assert actions.RUN["starlight_unspent"] == 63
    page(context, {(660, 395, 320, 90): "Coverts any remaining Starlight"})  # Convert Starlight to Cost is on, as planned
    run_start_actions.ConfirmStarlight().run(context, argv())
    assert actions.RUN["starlight_unspent"] == 0


def test_the_difficulty_switch_waits_for_the_label_not_2_5_seconds(context, clock):
    page(context, {(830, 30, 160, 35): lambda clicks, looks: "NORMAL" if not clicks else "HARD"})
    assert run_start_actions.PickThemePack.set_difficulty(context, 1, True)
    assert taps(context) == [(965, 46)]
    no_fixed_wait(clock)


def test_a_difficulty_label_not_readable_yet_is_looked_at_again_not_slept_on(context, clock):
    page(context, {(830, 30, 160, 35): lambda clicks, looks: "HARD" if looks >= 3 else None})
    assert run_start_actions.PickThemePack.set_difficulty(context, 1, True)
    no_fixed_wait(clock)


REFRESH = (1083, 47)


# A floor page's screenshots (#482): Refresh lit with no count (one free refresh), and greyed once it is used.
PACK_LIT, PACK_GREY = (bgr(SCREENS / f"{name}.png") for name in ("ThemePack", "ThemePackRefreshGrey"))


def pack_page(context, monkeypatch, floor, setting, mode, covers=None, spent_after=None, grey_after=None):
    """PickThemePack on a fake floor page of two cards weighing -5 and read as packs the data file lacks (a new pair
    after each of 4 refreshes; a 5th changes nothing: used up). Returns (refresh taps, log lines); covers collects the
    cover reader each page's ranking is handed (#274). The button reads `0/3` after spent_after refreshes, unread if None
    (#319); the screen is PACK_GREY after grey_after refreshes, PACK_LIT before or if None (#482)."""
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: (PACK_GREY if grey_after is not None and len(taps) >= grey_after else PACK_LIT).copy()
    actions.RUN.update(settings={"run": {"theme_pack_refresh": setting}}, team={"hard_from_floor": 0}, difficulty=None)
    plan = {"weights": {}, "threshold": 0, "unlisted": -5, "event_packs": mode}
    art = {"Hello Bus": "S.E.A."}
    packs = {"S.E.A.": {"N": [2], "H": [2, 3]}, "Extreme Pack": {"X": True}}
    patch_all(monkeypatch, "theme_pack_plan", lambda settings, team: (plan, packs, set(), art))

    def rank_packs(cards, names, plan, title_art, cover):
        assert title_art == art  # every page, a refreshed one too, gets the data file's title art (#246)
        assert names == ["S.E.A."]  # floors 1-5 never read a card as an EXTREME-only pack (#387)
        covers.append(cover)
        return [(c[0], -5, "name") for c in cards]
    monkeypatch.setattr(run_start, "rank_packs", rank_packs)
    covers = [] if covers is None else covers
    monkeypatch.setattr(pack_cover, "read_cover", lambda page, x, allowed: ("Cover pack", page, x, allowed))
    lines = []
    patch_all(monkeypatch, "log", lines.append)
    taps = []
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    patch_all(monkeypatch, "seen", lambda context, image, node: node == "PackRefreshSpent" and spent_after is not None
              and len(taps) >= spent_after)

    def ocr(context, image, roi, only_rec=False):
        page = min(taps.count(REFRESH), 4)
        return {
            (480, 100, 320, 40): [(f"FLOOR {floor}", (560, 110, 80, 20))] if not context.tasker.controller.post_swipe.called else [],
            (830, 30, 160, 35): [("NORMAL", (900, 40, 60, 20))],
            tuple(run_start_actions.PACK_TITLES): [(f"Pack {page}a", (200, 420, 90, 20)), (f"Pack {page}b", (500, 420, 90, 20))],
        }.get(tuple(roi), [])
    patch_all(monkeypatch, "ocr", ocr)

    run_start_actions.PickThemePack().run(context, None)
    assert context.tasker.controller.post_swipe.call_count == 1  # one card is pulled whatever the page
    return taps.count(REFRESH), lines


def test_theme_pack_titles_are_read_once_the_cards_stop_swinging(context, monkeypatch):
    # #246, recordings: dealt cards swing for ~2.8 s. Read mid-swing, a card not landed yet was left out and title
    # art was misread. Every read waits for the cards to stop, the refreshed page's too.
    order = []
    patch_all(monkeypatch, "still", lambda context, **kw:
              order.append(("still", tuple(kw.get("roi") or ()), kw.get("runs"), kw.get("timeout"))) or actions.screen(context))
    real = run_start_actions.pack_titles
    patch_all(monkeypatch, "pack_titles", lambda context, image: order.append("read") or real(context, image))
    pack_page(context, monkeypatch, 2, "once", "weight")
    reads = [i for i, o in enumerate(order) if o == "read"]
    assert len(reads) == 2  # the page and the refreshed page
    assert all(order[i - 1] == ("still", tuple(run_start_actions.PACK_CARDS), 2, run_start_actions.CARDS_SETTLE) for i in reads)
    assert run_start_actions.CARDS_SETTLE >= 3  # the swing's ~2.8 s fits


def test_cards_still_moving_after_the_wait_are_read_anyway_and_logged(context, monkeypatch):
    # #246: a card that never stops (an animated one) costs CARDS_SETTLE, not the floor.
    patch_all(monkeypatch, "still", lambda context, **kw: None)
    _, lines = pack_page(context, monkeypatch, 2, "none", "weight")
    assert f"floor 2: the cards still moved after {run_start_actions.CARDS_SETTLE:g} s" in lines
    assert lines[-1] == "floor 2: pull 'Pack 0a' (-5, below the threshold)"


@pytest.mark.parametrize(("setting", "refreshes"), [("none", 0), ("once", 1), ("all", 5)])
def test_a_theme_pack_page_below_the_threshold_is_refreshed_as_the_setting_says(context, monkeypatch, setting, refreshes):
    # #41, #240: every page's best pack is below the threshold. The log gives each card's weight, the threshold and the
    # pulled card; floor 2's new packs are plain packs.
    used, lines = pack_page(context, monkeypatch, 2, setting, "prefer")
    assert used == refreshes
    assert "floor 2 packs, threshold 0: Pack 0a (-5), Pack 0b (-5)" in lines
    assert lines[-1] == f"floor 2: pull 'Pack {min(refreshes, 4)}a' (-5, below the threshold)"


def test_a_spent_refresh_button_is_not_pressed_again(context, monkeypatch):
    # #319: `Refresh 0/3` greyed after the 3rd refresh: no 4th tap (was one more, then the unchanged cards stopped it)
    used, lines = pack_page(context, monkeypatch, 2, "all", "prefer", spent_after=3)
    assert used == 3
    assert "floor 2: no free refresh left" in lines
    assert lines[-1] == "floor 2: pull 'Pack 3a' (-5, below the threshold)"


def test_a_greyed_refresh_button_with_no_count_is_not_pressed_again(context, monkeypatch):
    # #482, #322: with one free refresh the button reads `Refresh` alone and greys once it is used (live 2026-11-07,
    # ThemePackRefreshGrey.png). One tap, not a second one on the grey button that changes nothing (about 4 s a floor).
    used, lines = pack_page(context, monkeypatch, 2, "all", "prefer", grey_after=1)
    assert used == 1
    assert "floor 2: no free refresh left" in lines
    assert lines[-1] == "floor 2: pull 'Pack 1a' (-5, below the threshold)"


def test_the_refresh_button_sweep_over_the_theme_pack_captures():
    # CODING_STANDARDS' sweep, #482: refresh_lit reads unlit the greyed buttons alone, with no count (HardLine1,
    # RefreshGrey) or #319's `0/3` (Refresh0, which PackRefreshSpent reads too); `Refresh` alone (ThemePack) and 1/3, 2/3,
    # 3/3, 4/4 read lit. Off the theme pack page its box is dark on most captures, but PickThemePack asks it only on a
    # page page_guard took for ThemePack.
    lit = {path.stem: run_start_actions.refresh_lit(bgr(path)) for path in sorted(SCREENS.glob("ThemePack*.png"))}
    assert [stem for stem, on in lit.items() if not on] == ["ThemePackHardLine1", "ThemePackRefresh0", "ThemePackRefreshGrey"]
    assert [stem for stem, on in lit.items() if on] == ["ThemePack", "ThemePackHardLine5", "ThemePackHardLineCover",
                                                        "ThemePackMiracle", "ThemePackNormal", "ThemePackRefresh1"]


def test_a_theme_pack_page_is_not_refreshed_by_a_spent_button_it_did_not_need(context, monkeypatch):
    # #319: a button not asked about (the best pack meets the threshold, or "none") is not read for its count
    used, lines = pack_page(context, monkeypatch, 2, "none", "weight", spent_after=0)
    assert used == 0
    assert "floor 2: no free refresh left" not in lines


def test_each_card_of_a_theme_pack_page_is_logged_with_the_path_that_read_it(context, monkeypatch):
    # #274: which of the paths (name, title_art, keyword, cover N, shared, unread) named each card
    _, lines = pack_page(context, monkeypatch, 2, "none", "weight")
    assert "floor 2 card reads: Pack 0a <- name, Pack 0b <- name" in lines


def test_the_cover_reader_of_a_theme_pack_page_looks_at_that_pages_card(context, monkeypatch):
    # #274: rank_packs gets a reader of the page just read: card i's x centre (the 2nd title spans 500-590) on that image
    covers = []
    pack_page(context, monkeypatch, 2, "none", "weight", covers)
    found = covers[0](1, {"Line 1"})
    assert found[0] == "Cover pack" and found[2] == 545 and found[3] == {"Line 1"}
    assert found[1].shape == (720, 1280, 3)


def test_floor_5s_leftmost_new_pack_is_taken_when_event_packs_are_preferred(context, monkeypatch):
    # #240: a pack the data file lacks, leftmost on floor 5, is a running event's: "prefer" takes it, no refresh.
    used, lines = pack_page(context, monkeypatch, 5, "all", "prefer")
    assert used == 0
    assert [lines[-3], lines[-1]] == ["floor 5 packs, threshold 0: Pack 0a (-5, event), Pack 0b (-5)", "floor 5: pull 'Pack 0a' (-5)"]


def test_the_pulled_pack_is_noted_by_id_for_the_run(context, monkeypatch):
    # #306: PickThemePack notes the pack it pulls (not the ones on screen) in the run; pulled twice, it is one note.
    patch_all(monkeypatch, "pack_ids", lambda: {"Pack 0a": 1004, "Pack 0b": 1005})
    actions.RUN["packs"] = [1011]
    pack_page(context, monkeypatch, 2, "none", "weight")
    assert actions.RUN["packs"] == [1011, 1004]
    pack_page(context, monkeypatch, 2, "none", "weight")
    assert actions.RUN["packs"] == [1011, 1004]


def test_a_pack_with_a_bokgak_re_run_notes_both_ids(context, monkeypatch):
    # #306: the re-run's card shows the same title, so a pull of "Pack 0a" may be either; some recipes name only the re-run.
    patch_all(monkeypatch, "pack_ids", lambda: {"Pack 0a": 1103, "Pack 0a BokGak": 1113})
    actions.RUN["packs"] = []
    pack_page(context, monkeypatch, 2, "none", "weight")
    assert actions.RUN["packs"] == [1103, 1113]


def test_a_card_read_as_the_bokgak_re_run_notes_only_the_re_run(monkeypatch):
    # #361: with the BokGak line read, the pulled name is the copy's own: its id alone, not the original's.
    patch_all(monkeypatch, "pack_ids", lambda: {"Pack 0a": 1103, "Pack 0a BokGak": 1113})
    actions.RUN["packs"] = []
    run_start_actions.note_pack("Pack 0a BokGak")
    assert actions.RUN["packs"] == [1113]


def test_a_pulled_pack_without_an_id_is_skipped_and_the_packs_noted_so_far_stay(context, monkeypatch):
    # #310 review: a pack the data file lacks (an EXTREME-only pack, an event's, a plan's own) is not noted; the packs noted
    # before it, and the ones after it, still are, so the exclusive recipes of the known packs stay open.
    patch_all(monkeypatch, "pack_ids", lambda: {})
    actions.RUN["packs"] = [1011]
    pack_page(context, monkeypatch, 2, "none", "weight")
    assert actions.run_packs() == [1011]
    patch_all(monkeypatch, "pack_ids", lambda: {"Pack 0a": 1004})
    run_start_actions.note_pack("Pack 0a")
    assert actions.run_packs() == [1011, 1004]


def test_a_run_without_a_packs_note_stays_unknown_after_a_pull(context, monkeypatch):
    # #306: the agent restarted mid-run, the earlier floors' packs are lost: one later pull does not make a list of it.
    patch_all(monkeypatch, "pack_ids", lambda: {"Pack 0a": 1004})
    pack_page(context, monkeypatch, 3, "none", "weight")
    assert actions.run_packs() is None


def test_a_new_run_starts_with_no_packs_taken(context, clock, monkeypatch):
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 3, "hard_from_floor": 1, "gift_list": "default", "enabled": True}
    run = {"runs": 0, "stop_when_weekly_bonus_out": False, "difficulty": "normal", "target_floor": 5}
    patch_all(monkeypatch, "load_settings", lambda root, need_team=False: {"run": run, "teams": [team], "gift_lists": []})
    patch_all(monkeypatch, "pick_team", lambda teams, difficulty: team)
    monkeypatch.setattr(settlement, "runs_done", lambda done, limit: False)
    monkeypatch.setattr(recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(recovery, "floor_limit", lambda runs, team, target: 1800)
    actions.RUN["packs"] = [1004, 1005]  # the last run's
    actions.TASK["modules"] = 20  # read on the Drive page (#369)
    page(context, {})
    run_start_actions.PlanRun().run(context, argv())
    assert actions.run_packs() == []


def test_a_search_tab_opens_without_fixed_waits(context, clock):
    clicks = context.tasker.controller.post_click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect =         lambda: np.full((720, 1280, 3), 20 * clicks.call_count, np.uint8)  # each tab shows at once
    run_start_actions.GiftSearch.open_tab(context, "Bleed")
    assert len(taps(context)) == 2
    no_fixed_wait(clock)
    assert sum(clock) < 1  # was 1.6 s of sleep


def test_a_picked_gift_is_checked_once_the_panel_shows_it(context, clock):
    page(context, {(922, 205, 270, 34): lambda clicks, looks: "Spiderweb Entangled in Red" if clicks else None})
    assert run_start_actions.GiftSearch.tap_and_check(context, np.zeros((720, 1280, 3), np.uint8), 300, 300, SPIDERWEB["name"])
    no_fixed_wait(clock)


def test_n_acquired_gift_popups_are_closed_in_one_action(context, clock):
    # #115: n gifts, n popups: the title stays up and the gift's name changes. Each next window is closed once the
    # screen is still, without a pass of MirrorHub in between.
    names = ["Wound Clerid", "Spiderweb", "Ashes to Ashes"]
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks < 3 else None,
                   GIFT_NAME: lambda clicks, looks: names[min(clicks, 2)]})
    assert run_start_actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)] * 3
    no_fixed_wait(clock)


def test_a_name_plate_read_mid_fade_out_is_not_taken_for_the_next_window(context, clock):
    # The last window fading out still shows its title, its plate half drawn ("Spiderw"): a tap then lands on the page
    # under it, the search grid, and picks a gift. The next window is tapped only once the screen is still.
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if looks < 4 else None,
                   GIFT_NAME: lambda clicks, looks: "Spiderweb" if looks < 3 else "Spiderw"})
    assert run_start_actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]


def test_the_next_gift_popup_is_tapped_once_it_has_stopped_moving(context, clock):
    # The next window slides in (looks 2-4 differ), then holds still (looks 4 and 5 match): its Confirm is tapped after that.
    screens(context, [0, 40, 80, 120, 120])
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get
    tapped_at = []
    context.tasker.controller.post_click.side_effect = lambda x, y: tapped_at.append(shots.call_count) or MagicMock()
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks < 2 else None,
                   GIFT_NAME: lambda clicks, looks: "Wound Clerid" if clicks == 0 else "Spiderweb"})
    assert run_start_actions.GiftGet().run(context, argv())
    assert len(tapped_at) == 2 and tapped_at[1] >= 5


def test_a_gift_popup_confirm_that_did_not_take_is_left_to_the_hub(context, clock):
    # Same title, same name for the whole wait: the tap was lost; MirrorHub sees the window again.
    page(context, {GIFT_POPUP: "E.G.O Gift GET!", GIFT_NAME: "Wound Clerid"})
    assert run_start_actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]


def test_a_search_tab_tap_waits_for_the_neighbour_tab_to_show_first(context, clock):
    # Live 2026-10-18 (run13): the tapped tab lights up at once but its gifts show a few looks later; the
    # Keywordless tap sent before Blunt's gifts showed was lost, or the grid read still showed Blunt's, and
    # Spiderweb was searched for on the wrong tab ("not on the page").
    tab, pending = ["Poise"], []

    def click(x, y):
        if not pending:  # a tap while a switch is still on its way does nothing
            pending.append([run_start_actions.SEARCH_TABS[(x - 113) // 62], 3])
        return MagicMock()

    def shot():
        image = np.zeros((720, 1280, 3), np.uint8)
        if pending:
            pending[0][1] -= 1
            if pending[0][1] < 0:
                tab[0] = pending.pop()[0]
            else:
                image[165:215, 85:775] = 255  # the tap's light on the tab bar, before the gifts change
        image[228:625, 85:775] = 20 * run_start_actions.SEARCH_TABS.index(tab[0])
        return image
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = shot
    run_start_actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless" and not pending  # the Keywordless gifts show when it returns


def test_a_search_tab_whose_gifts_take_two_seconds_is_waited_for_not_read_early(context, clock):
    # Live 2026-10-20 (#190): Keywordless lit at once but its grid took over 1.6 s; the 1 s wait timed out and
    # the bot read Blunt's gifts: "Spiderweb ... not on the page", and the gift went unbought.
    tab, tapped = ["Poise"], {}

    def click(x, y):
        tapped.update(tab=run_start_actions.SEARCH_TABS[(x - 113) // 62], at=actions.time.monotonic())
        return MagicMock()

    def shot():
        if tapped and actions.time.monotonic() - tapped["at"] >= (2.0 if tapped["tab"] == "Keywordless" else 0.5):
            tab[0] = tapped["tab"]
        return np.full((720, 1280, 3), 20 * run_start_actions.SEARCH_TABS.index(tab[0]), np.uint8)
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = shot
    run_start_actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless"


def test_a_search_tab_tap_that_did_nothing_is_tapped_again(context, clock):
    # #190: the grid not moving for the whole wait means the tap was lost: tap the tab once more, not read on.
    tab, own_taps = ["Poise"], []

    def click(x, y):
        name = run_start_actions.SEARCH_TABS[(x - 113) // 62]
        if name == "Keywordless":
            own_taps.append(name)
        if name != "Keywordless" or len(own_taps) > 1:  # the first Keywordless tap is lost
            tab[0] = name
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: np.full((720, 1280, 3), 20 * run_start_actions.SEARCH_TABS.index(tab[0]), np.uint8)
    run_start_actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless" and len(own_taps) == 2


def test_a_search_tab_is_not_tapped_again_once_the_page_is_gone(context, clock, guarded):
    # #118 + #190: the second tap comes after the 5 s wait; the search page may have been left by then.
    page_until(context, "GiftSearch", 2)  # the neighbour's tap and the first Keywordless tap went out
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: np.zeros((720, 1280, 3), np.uint8)
    with pytest.raises(actions.PageGone):
        run_start_actions.GiftSearch.open_tab(context, "Keywordless")
    assert len(taps(context)) == 2


def test_a_search_tab_is_not_tapped_once_the_page_is_gone_after_the_neighbours_tap(context, guarded):
    # #118: the wait after the neighbour's tap is as long as the retry's; the wanted tab's first tap is guarded too.
    page_until(context, "GiftSearch", 1)
    with pytest.raises(actions.PageGone):
        run_start_actions.GiftSearch.open_tab(context, "Keywordless")
    assert len(taps(context)) == 1


def test_a_search_grid_is_not_dragged_once_the_page_is_gone(context, guarded):
    # #118: the drag after open_tab comes behind the tab's tap and fade; a page left meanwhile is not dragged.
    page_until(context, "GiftSearch", 0)
    with pytest.raises(actions.PageGone):
        run_start_actions.GiftSearch.scroll(context, 600)
    assert moved(context) == 0


def test_the_second_icon_candidate_is_not_tapped_once_the_page_is_gone(context, guarded, monkeypatch):
    # #118: the first candidate's tap and wait lie between the look and the second tap.
    page_until(context, "GiftSearch", 1)
    entry = next(g for g in gift_tables()[0] if g["keyword"] == "Burn")
    gift = {"name": entry["en"], "keyword": "Burn", "tier": entry["tier"]}
    monkeypatch.setattr(run_start_actions.GiftSearch, "open_tab", staticmethod(lambda *a: None))
    monkeypatch.setattr(run_start_actions.GiftSearch, "scroll", staticmethod(lambda *a: None))
    monkeypatch.setattr(gift_search, "gift_cells", lambda im: [(500, 300, gift["tier"]), (600, 300, gift["tier"])])
    monkeypatch.setattr(run_start_actions.GiftSearch, "icon_scores", staticmethod(lambda *a: [(0.9, 500, 300), (0.9, 600, 300)]))
    monkeypatch.setattr(run_start_actions.GiftSearch, "tap_and_check", staticmethod(lambda c, im, x, y, n: bool(c.tasker.controller.post_click(x, y)) and False))
    with pytest.raises(actions.PageGone):
        run_start_actions.GiftSearch.pick(context, gift)
    assert taps(context) == [(500, 300)]


def test_a_lookalike_pick_is_not_unselected_on_a_page_that_is_gone(context, guarded, monkeypatch):
    # #118: the tap that picked the wrong gift waited up to 1 s; the tap that undoes it is guarded.
    page_until(context, "GiftSearch", 1)
    monkeypatch.setattr(run_start_actions.GiftSearch, "chosen", staticmethod(lambda c, im, names: ["Other"] if c.tasker.controller.post_click.called else []))
    with pytest.raises(actions.PageGone):
        run_start_actions.GiftSearch.tap_and_check(context, np.zeros((720, 1280, 3), np.uint8), 500, 300, "Wanted")
    assert taps(context) == [(500, 300)]


def test_the_consume_dialog_is_confirmed_once_it_stops_dropping_in(context, clock):
    # Live 2026-10-18 (run13c): Confirm was tapped as soon as "Consume" read, while the dialog still slid down
    # on its chains; the tap did nothing, no GET window came, and every GiftSearch call after it did the same.
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get
    clicks, state = context.tasker.controller.post_click, {"select": None, "bought": False}

    def click(x, y):
        if (x, y) == run_start_actions.SEARCH_SELECT:
            state["select"] = shots.call_count
        elif (x, y) == run_start_actions.SEARCH_DIALOG_BUTTONS["confirm"] and shots.call_count >= state["select"] + 4:
            state["bought"] = True  # the dialog has stopped: the tap takes
        return MagicMock()

    def shot():
        moving = state["select"] is not None and shots.call_count < state["select"] + 4
        return np.full((720, 1280, 3), 40 * (shots.call_count % 5) if moving else 0, np.uint8)
    search_page(context, {tuple(run_start_actions.SEARCH_DIALOG): lambda c, l: "Consume 70 Starlight to search and obtain these E.G.O Gifts?"
                            if state["select"] is not None and not state["bought"] else None,
                          GIFT_POPUP: lambda c, l: "E.G.O Gift GET!" if state["bought"] else None})
    clicks.side_effect = click
    shots.side_effect = shot
    assert run_start_actions.GiftSearch().run(context, argv())
    assert state["bought"]


def test_a_team_list_gone_is_handed_back_not_stopped_on(context, guarded, monkeypatch):
    actions.RUN["team"] = {"game_team": 3}
    patch_all(monkeypatch, "stop", lambda *a, **k: pytest.fail("stopped"))
    team_picker(context, "TEAMS #1", lambda clicks, looks: None)
    assert run_start_actions.SelectTeam().run(context, argv())
    assert taps(context) == []


def test_the_theme_pack_page_reads_its_floor_in_any_case(context, monkeypatch):
    # #138: "Floor 3" is floor 3, as the page-gone wait after the pull already reads it.
    patch_all(monkeypatch, "text", lambda *a, **k: "Floor 3")
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)
    actions.RUN["difficulty"] = None
    run_start_actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == 3


def test_a_new_floor_forgets_the_shop_left_before_the_boss(context, monkeypatch):
    # #279: the boss' floor ends with the boss; the next floor's first map is read by its marks again.
    patch_all(monkeypatch, "text", lambda *a, **k: "Floor 3")
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)
    actions.RUN.update(difficulty=None, floor=2, after_shop=True)
    run_start_actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == 3 and "after_shop" not in actions.RUN


@pytest.mark.parametrize("shown, floor", [("SELECT FLOOR 10 THEME PACK", 10), ("Select Floor 12 Theme Pack", 12), ("SELECT FLOOR 15 THEME PACK", 15)])
def test_the_theme_pack_page_reads_a_two_digit_floor(context, monkeypatch, shown, floor):
    # #383: floors run to 15; "Floor 12" is not floor 1.
    patch_all(monkeypatch, "text", lambda *a, **k: shown)
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)
    actions.RUN["difficulty"] = None
    run_start_actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == floor


def test_floor_10_to_11_restarts_the_clock_and_the_map_quota(context, monkeypatch):
    # #383: 10 -> 11 is a new floor: the clock restarts and map_misses is back to 0.
    patch_all(monkeypatch, "text", lambda *a, **k: "SELECT FLOOR 11 THEME PACK")
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)
    restarted = []
    patch_all(monkeypatch, "restart_floor_clock", lambda: restarted.append(1))
    actions.RUN.update(difficulty=None, floor=10, map_misses=3)
    run_start_actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == 11 and actions.RUN["map_misses"] == 0 and restarted == [1]


def test_a_new_floor_tells_the_ladder_the_floor_and_the_run_target(context, monkeypatch):
    # #435: a target-15 run's recovery allowance refills at floors 6 and 11 (recovery.Ladder.floor).
    patch_all(monkeypatch, "text", lambda *a, **k: "SELECT FLOOR 6 THEME PACK")
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)
    seen = []
    monkeypatch.setattr(actions.STUCK["ladder"], "floor", lambda floor, target: seen.append((floor, target)))
    actions.RUN.update(difficulty=None, floor=5, settings={"run": {"target_floor": 15}})
    run_start_actions.PickThemePack().run(context, None)
    assert seen == [(6, 15)]


@pytest.mark.parametrize("action, team", [
    (run_start_actions.PickStartingGift, {"keyword": "Burn", "gift_search": {"enabled": False, "gifts": []}}),
    (run_start_actions.GiftSearch, {"gift_search": {"enabled": True, "gifts": [{"name": "Phlebotomy Pack"}]}}),
])
def test_a_gift_page_gone_is_handed_back_untouched(context, guarded, action, team):
    actions.RUN["team"] = team
    assert action().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_a_theme_pack_page_gone_is_handed_back_untouched(context, guarded, monkeypatch):
    patch_all(monkeypatch, "text", lambda *a, **k: "FLOOR 1")
    actions.RUN["difficulty"] = None
    assert run_start_actions.PickThemePack().run(context, None)
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def starlight(monkeypatch, available):
    """A starlight page planning graces 1 and 2 at base (10 each), Available reading available in turn (the last for
    good: the grace tap's wait reads it too, #58), nothing owned."""
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "stop"}}
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: {"priority": [1, 2], "levels": ["base", "base"] + ["none"] * 8})
    reads = list(available)
    patch_all(monkeypatch, "read_available", lambda context, image: reads.pop(0) if len(reads) > 1 else reads[0])
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: pytest.fail(reason))


def test_a_starlight_page_gone_is_handed_back_untouched(context, guarded, monkeypatch):
    starlight(monkeypatch, [20])
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert moved(context) == 0


def test_a_starlight_page_handed_back_after_one_grace_still_buys_the_next(context, monkeypatch):
    # #118: back from MirrorHub with grace 1 bought: Available reads 10, grace 1 already selected.
    starlight(monkeypatch, [10, 0])
    patch_all(monkeypatch, "grace_selected", lambda image, n: n == 1)
    monkeypatch.setattr(run_start_actions.BuyStarlight, "set_level", staticmethod(lambda *a: True))
    assert run_start_actions.BuyStarlight().run(context, argv())
    x, y = run_start_actions.grace_box(2)
    assert (x + 92, y + 100) in taps(context)


def test_a_starlight_page_gone_after_a_grace_tap_is_handed_back_not_stopped(context, guarded, monkeypatch):
    starlight(monkeypatch, [20, None])
    monkeypatch.setattr(run_start_actions.BuyStarlight, "set_level", staticmethod(lambda *a: True))
    page_until(context, "StarlightPage", 1)
    assert run_start_actions.BuyStarlight().run(context, argv())
    assert len(taps(context)) == 1


def test_a_gift_search_gone_after_a_pick_does_not_press_select(context, guarded, monkeypatch):
    gift = {"name": "Phlebotomy Pack", "keyword": "Bleed", "tier": 1}
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [gift]}}
    monkeypatch.setattr(gift_search, "select_count", lambda text: (0, 1))
    monkeypatch.setattr(run_start_actions.GiftSearch, "chosen", staticmethod(lambda *a: ["Phlebotomy Pack"]))
    picks = iter([gift])
    monkeypatch.setattr(gift_search, "next_gift", lambda *a: next(picks, None))
    monkeypatch.setattr(run_start_actions.GiftSearch, "pick", staticmethod(lambda context, gift: actions.tap(context, 400, 400, wait=0) or True))
    page_until(context, "GiftSearch", 1)
    assert run_start_actions.GiftSearch().run(context, argv())
    assert taps(context) == [(400, 400)] and actions.STUCK["flag"] is None


def test_a_gift_search_gone_under_its_consume_dialog_is_not_confirmed(context, guarded, monkeypatch):
    ctl = context.tasker.controller
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [{"name": "Phlebotomy Pack"}]}}
    monkeypatch.setattr(gift_search, "select_count", lambda text: (1, 1))
    monkeypatch.setattr(run_start_actions.GiftSearch, "chosen", staticmethod(lambda *a: ["Phlebotomy Pack"]))
    monkeypatch.setattr(gift_search, "next_gift", lambda *a: None)
    patch_all(monkeypatch, "text", lambda context, image, roi, only_rec=False:
              "Consume 70 Starlight" if roi == run_start_actions.SEARCH_DIALOG and ctl.post_click.call_count else "")
    page_until(context, "GiftSearch", 1)  # gone once Select brought its dialog up
    assert run_start_actions.GiftSearch().run(context, argv())
    assert taps(context) == [run_start_actions.SEARCH_SELECT]


def test_a_starting_gift_page_gone_after_a_gift_tap_does_not_press_select(context, guarded, monkeypatch):
    actions.RUN["team"] = {"keyword": "Burn", "gift_search": {"enabled": False, "gifts": []}}
    monkeypatch.setattr(run_start_actions.PickStartingGift, "set_gift_search", staticmethod(lambda *a: None))
    monkeypatch.setattr(run_start_actions.PickStartingGift, "full", staticmethod(lambda *a: False))
    monkeypatch.setattr(run_start_actions.PickStartingGift, "count", staticmethod(lambda *a: (0, 1)))
    patch_all(monkeypatch, "ocr", lambda *a, **k: [("Burn", (200, 200, 60, 20))])
    page_until(context, "StartingGift", 2)  # the cabinet, then its first gift
    assert run_start_actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(230, 285), (970, 262)]
