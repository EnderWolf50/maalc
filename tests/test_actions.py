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


def test_confirm_download_taps_the_button_and_holds_the_watchdog(context, clock):
    # #86: after Confirm the download runs on a screen the hub does not know: it must not count as stuck.
    actions.STUCK["watch"].reset()
    actions.ConfirmDownload().run(context, SimpleNamespace(box=[700, 450, 100, 30]))
    context.tasker.controller.post_click.assert_called_once_with(750, 465)
    assert actions.STUCK["watch"].held(actions.time.monotonic() + 60)
    actions.STUCK["watch"].reset()


def test_recover_waits_out_a_download_without_climbing(context, clock, monkeypatch, tmp_path):
    # MirrorHub's own 60 s timeout lands in Recover while the download shows nothing it knows.
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    actions.STUCK["watch"].reset()
    actions.STUCK["watch"].hold(actions.time.monotonic(), 1800)
    before = dict(actions.STUCK["ladder"].counts)
    assert actions.Recover().run(context, None)
    assert actions.STUCK["ladder"].counts == before
    context.run_task.assert_not_called()
    actions.STUCK["watch"].reset()
