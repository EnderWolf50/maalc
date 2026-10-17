"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import json
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


def test_the_fusion_grid_is_not_scanned_again_while_the_owned_gifts_are_the_same(context):
    # The fuse page with its keyword dialog, every cell empty: no fusion this visit.
    reads(context, {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
                    tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]})
    team, visit = {"keyword": "Burn", "gift_search": {"gifts": []}}, {}
    assert not actions.Shop.fuse(context, team, visit)
    taps = context.tasker.controller.post_click.call_count
    assert taps > len(actions.FUSE_CELLS)  # the grid was scanned
    assert not actions.Shop.fuse(context, team, visit)  # nothing bought or sold since
    assert context.tasker.controller.post_click.call_count == taps


def test_the_teams_observed_gift_is_kept_out_of_a_fusion(context):
    # The user (#103): Spiderweb Entangled in Red, found by gift search, kept getting fused away.
    gift = [("E.G.O GIFT", (1030, 305, 100, 25)), ("Spiderweb Entangled in Red", (1010, 340, 180, 22)),
            ("Slash damage +10%", (1000, 380, 200, 20))]
    reads = {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
             tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))], tuple(actions.FUSE_TOOLTIP): gift}

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in reads.get(roi, [])]
        return SimpleNamespace(all_results=results) if results else None
    context.run_recognition.side_effect = run_recognition
    team = {"keyword": "Burn", "gift_search": {"gifts": [{"name": "Spiderweb Entangled in Red"}]}}
    assert not actions.Shop.fuse(context, team, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert taps.count(actions.FUSE_CELLS[0]) == 2  # tapped in, then out again


# The run's opening (#115): every wait is a look at the next page, never a fixed delay.
def page(context, rules):
    """OCR reads rules[roi] there and nothing elsewhere. A rule is a text, [(text, box)], or f(clicks, looks) -> either or None."""
    clicks = context.tasker.controller.post_click
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        rule = rules.get(roi)
        rule = rule(clicks.call_count, shots.call_count) if callable(rule) else rule
        if not rule:
            return None
        results = [SimpleNamespace(text=rule, box=roi)] if isinstance(rule, str) else [SimpleNamespace(text=t, box=b) for t, b in rule]
        return SimpleNamespace(all_results=results, hit=True, best_result=None)
    context.run_recognition.side_effect = run_recognition


def argv(param=None, node="Node"):
    return SimpleNamespace(custom_action_param=json.dumps(param), node_name=node, box=[0, 0, 1, 1])


def no_fixed_wait(clock):
    assert max(clock, default=0) <= 0.25, clock  # only until()'s 0.2 s looks


def taps(context):
    return [c.args for c in context.tasker.controller.post_click.call_args_list]


def test_tap_until_taps_the_target_and_waits_for_the_page_that_follows(context, clock):
    page(context, {(10, 20, 30, 40): lambda clicks, looks: "Next Page" if looks >= 3 else None})
    param = {"target": [100, 200, 40, 20], "next": {"roi": [10, 20, 30, 40], "expected": "^Next"}}
    assert actions.TapUntil().run(context, argv(param))
    assert taps(context) == [(120, 210)]
    assert context.tasker.controller.post_screencap.call_count == 3
    no_fixed_wait(clock)


def test_tap_until_takes_any_of_several_next_pages(context, clock):
    page(context, {(1, 1, 10, 10): "Resume"})
    param = {"target": [100, 200, 40, 20], "next": [{"roi": [10, 20, 30, 40], "expected": "^TEAMS$"}, {"roi": [1, 1, 10, 10], "expected": "Resume"}]}
    assert actions.TapUntil().run(context, argv(param))
    no_fixed_wait(clock)
    assert sum(clock) == 0


def test_tap_until_gives_up_after_its_timeout_and_leaves_the_page_to_the_hub(context, clock):
    page(context, {})
    param = {"target": [100, 200, 40, 20], "next": {"roi": [10, 20, 30, 40], "expected": "Next"}, "timeout": 2}
    assert actions.TapUntil().run(context, argv(param))
    assert 2 <= sum(clock) < 2.5


def test_plan_run_waits_for_the_enter_dialog_after_pressing_enter(context, clock, monkeypatch):
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 3}
    run = {"runs": 0, "stop_when_weekly_bonus_out": False, "difficulty": "normal"}
    monkeypatch.setattr(actions, "load_settings", lambda root: {"run": run, "teams": [team]})
    monkeypatch.setattr(actions, "pick_team", lambda teams, cursor, difficulty: team)
    monkeypatch.setattr(actions, "read_cursor", lambda root, address: None)
    monkeypatch.setattr(actions.settlement, "runs_done", lambda done, limit: False)
    monkeypatch.setattr(actions.recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(actions.recovery, "floor_limit", lambda runs, team: 1800)
    page(context, {(400, 325, 480, 45): lambda clicks, looks: "Will you enter X?" if clicks and looks >= 3 else None})
    assert actions.PlanRun().run(context, argv())
    assert taps(context) == [(1108, 494)]
    no_fixed_wait(clock)


def team_picker(context, title, after_confirm):
    """The team list shows TEAMS #3 at y 390; title(clicks, looks) is the card's title text, after_confirm(clicks, looks) the next page."""
    page(context, {tuple(actions.TEAM_LIST): [("TEAMS #3", (100, 380, 80, 20))], (220, 112, 210, 26): title,
                   (1160, 522, 60, 34): "63", (400, 230, 480, 90): after_confirm})


def test_select_team_waits_for_the_title_after_the_tap_and_for_the_page_after_confirm(context, clock):
    actions.RUN["team"] = {"game_team": 3}
    team_picker(context, lambda clicks, looks: "TEAMS #1" if looks < 4 else "TEAMS #3",
                lambda clicks, looks: "lower than the recommended level" if clicks >= 2 else None)
    assert actions.SelectTeam().run(context, argv())
    assert taps(context) == [(130, 390), (1145, 587)]
    no_fixed_wait(clock)
    assert context.tasker.controller.post_screencap.call_count > 4  # looked until the title changed


def test_select_team_taps_the_card_again_when_the_title_never_changed(context, clock):
    actions.RUN["team"] = {"game_team": 3}
    team_picker(context, lambda clicks, looks: "TEAMS #1" if clicks < 2 else "TEAMS #3",
                lambda clicks, looks: "recommended level" if clicks >= 3 else None)
    assert actions.SelectTeam().run(context, argv())
    assert taps(context) == [(130, 390), (130, 390), (1145, 587)]


def test_starlight_enter_waits_for_the_confirm_dialog(context, clock, monkeypatch):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "skip"}}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"priority": [], "levels": []})  # nothing to buy
    page(context, {tuple(actions.STARLIGHT_AVAILABLE): "63",
                   (480, 210, 320, 35): lambda clicks, looks: "Continue with selected effects?" if clicks and looks >= 3 else None})
    assert actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(1195, 672)]
    no_fixed_wait(clock)


def test_starlight_confirm_waits_for_the_starting_gift_page(context, clock, monkeypatch):
    actions.RUN["settings"] = {}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"convert_leftover": False})
    page(context, {(660, 395, 320, 90): "Any unspent Starlight will be added to your Dungeon clear rewards",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks and looks >= 4 else None})
    assert actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(738, 530)]
    no_fixed_wait(clock)


SELECT_COUNT, SEARCH_SWITCH, GIFT_POPUP = (990, 565, 190, 45), (1100, 145, 85, 28), (520, 160, 240, 40)


def starting_gift_page(context, selects_at=2, rules=None):
    """The Burn cabinet is on the page; Select reads 0/1, 1/1 after selects_at taps, and Select (the tap after) pops the GET window up."""
    page(context, {SELECT_COUNT: lambda clicks, looks: "1/1" if clicks >= selects_at else "0/1",
                   (145, 145, 590, 430): [("Burn", (200, 300, 60, 20))],
                   tuple(actions.STARTING_GIFT_HEADER): lambda clicks, looks: "Selected E.G.O Gift" if clicks <= selects_at else None,
                   GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks > selects_at else None,
                   SEARCH_SWITCH: "ON", **(rules or {})})
    actions.RUN["team"] = {"keyword": "Burn", "gift_search": {"enabled": True, "gifts": [{"name": "x"}]}}


def test_the_starting_gift_is_picked_without_a_fixed_wait(context, clock):
    starting_gift_page(context)
    assert actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(230, 385), (970, 262), (1080, 587)]  # cabinet, first gift, Select
    assert sum(clock) < 1.5


def test_the_gift_search_switch_is_waited_for_not_slept_on(context, clock):
    # Select already reads 1/1 (the gift is picked); the switch reads OFF until it is tapped and the page has looked again.
    starting_gift_page(context, selects_at=0, rules={SEARCH_SWITCH: lambda clicks, looks: "OFF" if looks < 4 else "ON"})
    assert actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(1140, 158), (1080, 587)]  # the switch, then Select
    assert sum(clock) < 1.5


GIFT_NAME = (320, 405, 180, 80)


def test_an_acquired_gift_popup_is_closed_and_waited_out_without_a_fixed_delay(context, clock):
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks == 0 else None, GIFT_NAME: "Wound Clerid"})
    assert actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]
    no_fixed_wait(clock)


SPIDERWEB = {"name": "Spiderweb Entangled in Red", "keyword": "Burn", "tier": 2}


def search_page(context, **rules):
    """The search page with Spiderweb picked (Select 1/1, 70 starlight): Select asks to consume, Confirm shows the GET window."""
    page(context, {tuple(actions.SEARCH_COUNT): "Select 1/1", (922, 205, 270, 34): "Spiderweb Entangled in Red",
                   tuple(actions.SEARCH_OWNED[0]): "1542-70", tuple(actions.SEARCH_OWNED[1]): "1472",
                   tuple(actions.SEARCH_DIALOG): lambda clicks, looks: "Consume 70 Starlight to search and obtain these E.G.O Gifts?" if clicks == 1 else None,
                   GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks >= 2 else None, **rules})
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [SPIDERWEB]}}


def test_the_search_is_bought_with_looks_at_the_dialog_and_the_popup_not_fixed_waits(context, clock):
    search_page(context)
    assert actions.GiftSearch().run(context, argv())
    assert taps(context) == [actions.SEARCH_SELECT, actions.SEARCH_DIALOG_BUTTONS["confirm"]]
    no_fixed_wait(clock)


def test_the_owned_starlight_before_the_search_leaves_out_the_starlight_not_spent_on_graces(context, clock):
    # #73 (live 2026-10-17): the Owned box read 1542 with 1482 on the main page: the team's unspent Starlight Bonus 60 is in it.
    search_page(context)
    actions.RUN["starlight_unspent"] = 60
    actions.GiftSearch().run(context, argv())
    assert actions.RUN["gift_search"] == {"gifts": ["Spiderweb Entangled in Red"], "starlight": 70, "owned_before": 1482, "owned_after": 1412}


def test_the_owned_starlight_is_as_read_when_nothing_was_left_unspent(context, clock):
    search_page(context)
    actions.GiftSearch().run(context, argv())
    assert actions.RUN["gift_search"]["owned_before"] == 1542


def test_refusing_the_search_waits_for_the_forgo_dialog(context, clock):
    page(context, {tuple(actions.SEARCH_COUNT): "Select 0/3", (480, 330, 320, 35): lambda clicks, looks: "Forgo" if clicks else None})
    actions.RUN["team"] = {"gift_search": {"enabled": False, "gifts": []}}
    assert actions.GiftSearch().run(context, argv())
    assert taps(context) == [actions.SEARCH_REFUSE]
    no_fixed_wait(clock)


def test_the_unspent_starlight_is_kept_for_the_search_unless_it_is_converted(context, clock, monkeypatch):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "skip"}}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"priority": [], "levels": [], "convert_leftover": True})
    page(context, {tuple(actions.STARLIGHT_AVAILABLE): "63", (660, 395, 320, 90): "Any unspent Starlight will be added"})
    actions.BuyStarlight().run(context, argv())
    assert actions.RUN["starlight_unspent"] == 63
    page(context, {(660, 395, 320, 90): "Coverts any remaining Starlight"})  # Convert Starlight to Cost is on, as planned
    actions.ConfirmStarlight().run(context, argv())
    assert actions.RUN["starlight_unspent"] == 0


def test_the_difficulty_switch_waits_for_the_label_not_2_5_seconds(context, clock):
    page(context, {(830, 30, 160, 35): lambda clicks, looks: "NORMAL" if not clicks else "HARD"})
    assert actions.PickThemePack.set_difficulty(context, 1, True)
    assert taps(context) == [(965, 46)]
    no_fixed_wait(clock)


def test_a_difficulty_label_not_readable_yet_is_looked_at_again_not_slept_on(context, clock):
    page(context, {(830, 30, 160, 35): lambda clicks, looks: "HARD" if looks >= 3 else None})
    assert actions.PickThemePack.set_difficulty(context, 1, True)
    no_fixed_wait(clock)


def test_a_search_tab_opens_without_fixed_waits(context, clock):
    actions.GiftSearch.open_tab(context, "Bleed")
    assert len(taps(context)) == 2
    no_fixed_wait(clock)
    assert sum(clock) < 1  # was 1.6 s of sleep


def test_a_picked_gift_is_checked_once_the_panel_shows_it(context, clock):
    page(context, {(922, 205, 270, 34): lambda clicks, looks: "Spiderweb Entangled in Red" if clicks else None})
    assert actions.GiftSearch.tap_and_check(context, np.zeros((720, 1280, 3), np.uint8), 300, 300, SPIDERWEB["name"])
    no_fixed_wait(clock)


def test_the_next_acquired_gift_popup_counts_as_the_last_one_closed(context, clock):
    # n gifts, n popups: the title never leaves the screen, the gift's name changes.
    page(context, {GIFT_POPUP: "E.G.O Gift GET!", GIFT_NAME: lambda clicks, looks: "Wound Clerid" if clicks == 0 else "Spiderweb"})
    assert actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]
    assert sum(clock) < 0.5
