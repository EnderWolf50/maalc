"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import itertools
import json
import math
import time
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT, MagicMock

import numpy as np
import pytest
from PIL import Image

from maa.define import Rect

import actions
import recovery

REAL_GUARD = actions.page_guard
SCREENS = Path(__file__).resolve().parent / "screens"


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
def context(clock, monkeypatch):
    # The action's page stays up: #118's guard is driven on its own (page_until).
    monkeypatch.setattr(actions, "page_guard", lambda context, home, image=None: actions.screen(context) if image is None else image)
    monkeypatch.setattr(actions, "FEATURE_MATCH", set())  # fakes read every roi in screen coordinates: no cut-outs
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    ctx.run_recognition.return_value = None  # OCR reads nothing, no node hits
    ctx.tasker.controller.post_shell.return_value.wait.return_value.get.return_value = ""  # focus not read
    ctx.tasker.stopping = False
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


def test_still_wants_its_runs_of_alike_screenshots_in_a_row(context, clock):
    # #246: a swinging card looks alike 0.1 s either side of its turn, so one alike pair is not still yet.
    screens(context, [0, 40, 40, 80, 80, 80])
    assert actions.still(context, runs=2)[0, 0, 0] == 80


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


def few_alive(context, monkeypatch, after_retries, min_alive):
    """A formation page with 4 of 12 alive; the stops and taps it leads to."""
    actions.RUN.update(team={"min_alive": min_alive, "name": "t"}, settings={"run": {"after_retries": after_retries}})
    stops, taps = [], []
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: stops.append(reason) or False)
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: [])  # ends the action after the count
    reads(context, {tuple(actions.PARTICIPANTS): [("4/4", (1125, 500, 60, 30))]})
    result = actions.Formation().run(context, None)
    return result, stops, taps


def test_too_few_alive_forfeits_the_run_like_used_up_wipe_retries(context, monkeypatch):
    # #137: fewer than K alive goes the way of after_retries; forfeit backs out to the map, RouteMap forfeits there.
    result, stops, taps = few_alive(context, monkeypatch, "forfeit", 5)
    assert result is True and stops == []
    assert actions.RUN["forfeit"] is True
    assert taps == [actions.FORMATION_BACK]


def test_too_few_alive_stops_when_used_up_wipe_retries_stop(context, monkeypatch):
    result, stops, taps = few_alive(context, monkeypatch, "stop", 5)
    assert result is False and len(stops) == 1 and taps == []


def test_no_alive_check_at_0(context, monkeypatch):
    result, stops, taps = few_alive(context, monkeypatch, "forfeit", 0)
    assert all("deployment order" in s for s in stops)  # only the empty order (the stub) stops it
    assert "forfeit" not in actions.RUN


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


def event_text(context, choices_from=None, red_from=None, red_to=float("inf"), label_to=float("inf"), skip_to=0, misread=()):
    """Event text running on: screenshot n (1 = Event.run's own) shows the Choices from choices_from on, the lit
    button from red_from on until red_to and the button's label until label_to (SKIP until skip_to, then Continue,
    read "Contnue" on the screenshots in misread); returns the rois OCR read, in order."""
    shots, reads = [], []

    def screencap():
        shots.append(1)
        image = np.zeros((720, 1280, 3), np.uint8)
        image[0, 0, 0] = len(shots)
        if red_from and red_from <= len(shots) < red_to:
            image[640:650, 1080:1180] = (0, 0, 200)
        return image
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = screencap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        reads.append(roi)
        if roi == tuple(actions.CHOICES_HEADER) and choices_from and image[0, 0, 0] >= choices_from:
            return SimpleNamespace(all_results=[SimpleNamespace(text="Choices", box=(700, 110, 100, 30))])
        if roi == tuple(actions.EVENT_BUTTON_LABEL) and image[0, 0, 0] < label_to:
            label = "SKIP" if image[0, 0, 0] < skip_to else "Contnue" if image[0, 0, 0] in misread else "Continue"
            return SimpleNamespace(all_results=[SimpleNamespace(text=label, box=(1065, 625, 140, 40))])
        return None
    context.run_recognition.side_effect = run_recognition
    return reads


def corner_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == actions.EVENT_NEUTRAL]


def test_event_text_is_tapped_every_0_15_s_and_read_every_third_tap(context, clock):
    # Live 2026-10-20: a screenshot and 3 OCRs after each tap made it one every 0.3-1.1 s, whatever its wait; the
    # text keeps up with a tap every 0.15 s (the user by hand; no tap lost live). The Choices show after tap 4.
    reads = event_text(context, choices_from=6)
    actions.Event().run(context, None)
    assert len(corner_taps(context)) == 6  # read at taps 3 and 6
    assert reads.count(tuple(actions.EVENT_BUTTON_LABEL)) == 2
    assert sum(clock) == pytest.approx(5 * actions.EVENT_TAP_EVERY)


def test_event_text_stops_on_the_lit_button_without_reading_text(context, clock):
    # The button's pixels are looked at after each tap: a tap after it lit is wasted (live: 1-3 a burst).
    reads = event_text(context, red_from=3)
    actions.Event().run(context, None)
    assert len(corner_taps(context)) == 2
    assert tuple(actions.EVENT_BUTTON_LABEL) not in reads


def button_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == actions.EVENT_BUTTON]


def test_the_text_is_tapped_on_right_after_the_lit_button(context, clock):
    # The user (#188): after the red button the taps paused ~1.6-5.3 s (live 2026-10-20: a 0.5 s settle, then
    # MirrorHub's 200 ms delays and its look). Now the corner taps go on at the same 0.15 s in the same call;
    # the button still lit while its press fades out is no button to press again.
    event_text(context, red_from=1, red_to=3, choices_from=7)
    actions.Event().run(context, None)
    clicks = context.tasker.controller.post_click.call_args_list
    assert clicks[0].args == actions.EVENT_BUTTON and len(button_taps(context)) == 1
    assert len(corner_taps(context)) == 6  # 2 while it fades, read at once on the first unlit screen, then every third
    waits = [s for s in clock if s]  # tap(wait=0) sleeps 0
    assert waits[0] == pytest.approx(actions.EVENT_TAP_EVERY) and max(waits) <= actions.EVENT_TAP_EVERY


def test_no_corner_tap_once_the_lit_button_left_the_event(context, clock):
    # The last Continue ends the event: the first screen without the lit button is read before another tap.
    event_text(context, red_from=1, red_to=3, label_to=3)
    actions.Event().run(context, None)
    assert len(corner_taps(context)) == 2  # both on the fading event page


def test_a_lit_button_that_became_another_is_handed_back_at_once(context, clock):
    # A check's result page: SKIP pressed, Continue lit in its place (spec 02), with no unlit screen between.
    event_text(context, red_from=1, skip_to=3)
    actions.Event().run(context, None)
    assert len(button_taps(context)) == 1 and len(corner_taps(context)) == 2


@pytest.mark.parametrize("label_to, misread", [
    (3, ()),  # read empty mid-fade
    (1, ()),  # read empty before the press
    (float("inf"), (1,)),  # read in part before the press
    (3, (2,)),  # read in part mid-fade
])
def test_a_label_not_read_whole_while_it_fades_is_no_other_button(context, clock, label_to, misread):
    # Handed back, MirrorHub's Event node would still match the fading button and press it again.
    event_text(context, red_from=1, red_to=5, label_to=label_to, misread=misread)
    actions.Event().run(context, None)
    assert len(button_taps(context)) == 1 and len(corner_taps(context)) >= 4  # on through the fade's 3 lit screens


def test_a_press_that_did_not_take_is_handed_back_to_be_pressed_again(context, clock):
    # The button lit on for EVENT_TAKE s: the press was lost, MirrorHub presses it again. Counted in time, not taps:
    # a label OCR a lit screen (0.2 s here) slows the taps.
    event_text(context, red_from=1)
    inner = context.run_recognition.side_effect
    context.run_recognition.side_effect = lambda *a, **k: actions.time.sleep(0.2) or inner(*a, **k)
    actions.Event().run(context, None)
    assert len(button_taps(context)) == 1 and len(corner_taps(context)) == math.ceil(actions.EVENT_TAKE / 0.2)


def bus_at(context, x, y, linked=()):
    """The map's bus at (x, y); the link nodes in linked hit, nothing else does."""
    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[x, y, 45, 75])
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if name in linked else None
    context.run_recognition.side_effect = run_recognition


def test_a_map_not_readable_yet_is_read_again_before_any_tap(context, monkeypatch):
    # Live (#58): 2 s after a theme pack pull the hub saw a map with no bus or link to read; a fallback slot was entered.
    looks = []

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            looks.append(1)
            return SimpleNamespace(hit=True, box=[446, 248, 45, 75]) if len(looks) > 1 else None
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True  # a node entered before: the bus is not tried first
    actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 + actions.SLOT[0], 248 + actions.SLOT[1])  # the middle row's battle


def test_a_bright_event_its_templates_miss_is_still_an_event(context):
    # Live 2026-10-18, floor 2 "Lake World" (cyan): the top slot's "?" matched no MapNodeEvent template, read
    # unknown (9), and the bot took the middle gift box node (then abno; Focused since #91, 21) over up event > mid battle > mid shop > boss (19).
    # tests/data/map_lake_world.npz: that frame's per-pixel brightness, y 70-614, x 0-1179; bus at 50, 320.
    v = np.zeros((720, 1280), np.uint8)
    v[70:615, :1180] = np.load(Path(__file__).resolve().parent / "data/map_lake_world.npz")["v"]
    image = v[..., None].repeat(3, axis=2)
    seen_live = {(329, 357): {"cost", "gift"}, (584, 357): {"cost"}, (839, 357): {"shop"}, (1094, 357): {"boss", "cost", "gift"}}

    def run_recognition(name, image, override=None):
        if name in ("MapLinkUp", "MapLinkMid"):
            return SimpleNamespace(hit=True)
        if name in actions.MARKS:
            mark, (ox, oy, _, _) = actions.MARKS[name]
            x, y = override[name]["roi"][:2]
            return SimpleNamespace(hit=True, box=[x, y, 26, 24]) if mark in seen_live.get((x - ox, y - oy), ()) else None
        return None
    context.run_recognition.side_effect = run_recognition
    slots = actions.RouteMap.read_slots(context, image, 50, 320)
    ahead = actions.RouteMap.read_ahead(context, image, 50 + actions.SLOT[0], 320 + actions.SLOT[1], slots)
    weights = {"event": 1, "battle": 2, "focused": 4, "shop": 7, "unknown": 9}
    assert slots["up"][0] == "event"
    score, path = actions.map_route.paths(slots, weights, ahead)[actions.map_route.rank(slots, weights, ahead)[0]]
    assert (path, score) == (["up", "mid", "mid", "mid"], 19)


RED = Path(__file__).resolve().parent / "data/map_red_theme.npz"  # live 2026-10-18, floor 3 hard, red theme


def test_a_column_of_lit_events_its_templates_miss_is_read_and_a_dark_one_ends_the_read(context):
    # H1: next to the bus a Focused; then two dim red "?" (no template hit, linked by bright lines); then black.
    v = np.zeros((720, 1280), np.uint8)
    v[70:615, :1180] = np.load(RED)["h1_v"]
    context.run_recognition.return_value = None  # no mark on any node past the first column
    ahead = actions.RouteMap.read_ahead(context, v[..., None].repeat(3, axis=2), 50 + actions.SLOT[0], 320 + actions.SLOT[1], {"mid": ("focused", 2)})
    assert ahead == [{"up": ("event", {"mid"}), "down": ("event", {"mid"})}]


def map_node_boss():
    lines = (Path(actions.__file__).resolve().parent.parent / "assets/resource/base/pipeline/map.json").read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))["MapNodeBoss"]


@pytest.mark.parametrize(("node", "boss"), [
    ("boss_mapboss", True), ("boss_mapshop", True), ("boss_lake_world", True),
    # H2, H3: the red theme's "?" nodes; H2's bottom one read as the boss with a count of 500.
    ("event_h2_up", False), ("event_h2_down", False), ("event_h3_mid", False),
])
def test_only_the_boss_glows_red_enough_for_map_node_boss(node, boss):
    # MapNodeBoss is a ColorMatch (RGB, method 4) over 80 x 80 px around the node: its pixels in range, counted.
    params, rgb = map_node_boss(), np.load(RED)[node]
    hits = ((rgb >= params["lower"]) & (rgb <= params["upper"])).all(axis=2).sum()
    assert (hits >= params["count"]) == boss


def test_a_node_with_its_badges_under_the_resource_bar_is_no_event_for_showing_none(context):
    # At rest (bus at 446, 248) the top row's badges hide under the resource bar: a fight would show no coin.
    image = np.zeros((720, 1280, 3), np.uint8)
    assert actions.node_at(context, image, 725, 72) == "unknown"
    assert actions.node_at(context, image, 329, 144) == "event"  # the top row with the bus at BUS_HOME


def test_after_a_restart_or_recovery_the_bus_is_tapped_first(context, monkeypatch):
    # #88: L3 or Accept results leave the bus on a node not entered yet, whose panel its tap opens.
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    bus_at(context, *actions.BUS_HOME, linked=("MapLinkMid", "MapNodeCost"))
    actions.RouteMap().run(context, None)
    bx, by = actions.BUS_HOME
    assert context.tasker.controller.post_click.call_args_list[0].args == (bx + 22, by + 37)


def test_a_bus_tap_on_a_node_already_entered_gives_up_quickly_for_the_planned_slot(context, clock, monkeypatch):
    # #130 (live 2026-10-18 07:04:47): after an agent restart the first tap, on the bus, showed no panel
    # (its node was entered) and waited the full 2 s before the planned slot; a panel shows within about 0.5 s.
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    bus_at(context, *actions.BUS_HOME, linked=("MapLinkMid", "MapNodeCost"))
    ctl, at = context.tasker.controller, []
    ctl.post_click.side_effect = lambda x, y: at.append(((x, y), actions.time.monotonic())) or DEFAULT
    actions.RouteMap().run(context, None)
    bx, by = actions.BUS_HOME
    (bus, t0), (slot, t1) = at[0], at[1]
    assert bus == (bx + 22, by + 37) and slot == (bx + actions.SLOT[0], by + actions.SLOT[1])  # the bus first, then the slot
    assert t1 - t0 <= 1.3


def test_a_bus_dragged_off_the_screen_is_found_by_dragging_the_map(context, monkeypatch):
    # #61, live 2026-10-16: the map dragged by hand, the bus off the top; three blind rounds, L1, then L2.
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True
    ctl = context.tasker.controller

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[446, 320, 45, 75]) if ctl.post_touch_up.called else None
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    actions.RouteMap().run(context, None)
    assert ctl.post_click.call_args_list[0].args == (446 + actions.SLOT[0], 320 + actions.SLOT[1])
    assert actions.STUCK["flag"] is None or actions.STUCK["flag"][1] == 1  # no node panel in this fake: a miss


def test_a_bus_not_found_even_by_dragging_goes_straight_to_l2(context, monkeypatch):
    # #61: To Window and Resume put the map back; L1 (the back key) does nothing for a map.
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True
    actions.RouteMap().run(context, None)
    assert context.tasker.controller.post_click.called  # the fallback taps still go first
    assert actions.STUCK["flag"][1] == 2


def test_a_bus_at_the_far_left_is_not_dragged(context):
    bus_at(context, *actions.BUS_HOME, linked=("MapLinkMid", "MapLinkDown"))
    _, bus = actions.RouteMap.find_bus(context)
    assert bus == actions.BUS_HOME
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_map_at_rest_is_dragged(context):
    # #111: the bus goes to the far left, where the screen shows it and about four columns.
    bus_at(context, 446, 248, linked=("MapLinkMid",))
    actions.RouteMap.find_bus(context)
    context.tasker.controller.post_touch_down.assert_called()


def map_world(context, nodes, links, bus_x, width=1800):
    """A map wider than the screen, the bus at (bus_x, BUS_HOME's y) on screen; drags move the screen over it.

    nodes: {(column, row): marks}, column 1 next to the bus; links: ((column, row), (column, row)) pairs.
    The bus's chevrons lead to the first column's nodes; a tap on anything but Enter opens a node panel.
    The bus stands on a node already entered (no tap on it first, #88). Returns the screen's offsets after each drag.
    """
    actions.RUN["map_entered"] = True
    bx, by = 446, actions.BUS_HOME[1]  # on the map; the screen starts at 446 - bus_x

    def at(column, row):
        return bx + actions.SLOT[0] + (column - 1) * 255, by + actions.SLOT[1] + {"up": -213, "mid": 0, "down": 213}[row]
    world = np.random.default_rng(2).integers(0, 30, size=(720, width, 3)).astype(np.uint8)
    for a, b in links:
        (x0, y0), (x1, y1) = at(*a), at(*b)
        for t in np.linspace(0, 1, 600):
            x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
            world[y - 2:y + 3, x - 2:x + 3] = 200
    off, start, offsets = [bx - bus_x], [], []  # the screen's left edge on the map; where the touch went down

    def down(x, y):
        start[:] = [x, off[0]]
        return MagicMock()

    def move(x, y):
        off[0] = min(max(0, start[1] + start[0] - x), width - 1280)
        return MagicMock()

    def up():
        offsets.append(off[0])
        return MagicMock()
    ctl = context.tasker.controller
    ctl.post_touch_down.side_effect, ctl.post_touch_move.side_effect, ctl.post_touch_up.side_effect = down, move, up
    ctl.post_screencap.return_value.wait.return_value.get.side_effect = lambda: world[:, off[0]:off[0] + 1280].copy()
    marks = {(at(c, r)[0], at(c, r)[1], m) for (c, r), ms in nodes.items() for m in ms}

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[bx - off[0], by, 45, 75])
        if name in ("MapLinkUp", "MapLinkMid", "MapLinkDown"):
            return SimpleNamespace(hit=True) if (1, name[7:].lower()) in nodes else None
        if name == "MapNodePanel":
            taps = ctl.post_click.call_args_list
            return SimpleNamespace(hit=True) if taps and taps[-1].args != actions.ENTER else None
        if name in actions.MARKS:
            mark, (ox, oy, _, _) = actions.MARKS[name]
            x, y = override[name]["roi"][:2]
            return SimpleNamespace(hit=True, box=[x, y, 26, 24]) if (x - ox + off[0], y - oy, mark) in marks else None
        return None
    context.run_recognition.side_effect = run_recognition
    return offsets


WEIGHTS = {"event": 1, "battle": 2, "focused": 4, "unknown": 9}


def test_the_bus_is_dragged_to_the_far_left_and_the_cheapest_path_over_four_columns_is_taken(context, monkeypatch):
    # The user (#111): event -> battle -> battle -> Focused (9) loses to battle -> battle -> battle -> event (7),
    # which only the fourth column tells apart; with the bus at rest it is off screen.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "down"): {"cost"},
             (3, "up"): {"cost"}, (3, "down"): {"cost"}, (4, "up"): {"cost", "gift"}, (4, "down"): {"event"}}
    links = [((c, r), (c + 1, r)) for c in (1, 2, 3) for r in ("up", "down")]
    offsets = map_world(context, nodes, links, bus_x=446)
    actions.RouteMap().run(context, None)
    # To the far left, then (#202) a drag two columns on that stops at the map's edge, and back.
    assert len(offsets) == 3 and abs(446 - offsets[-1] - actions.BUS_HOME[0]) <= 30
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 - offsets[-1] + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] + 213)  # the bottom row's battle


def test_two_columns_on_a_hard_floor_take_the_cheapest_path(context, monkeypatch):
    # Hard mode shows two columns; nothing past them is lit to read.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost", "gift"}, (2, "down"): {"event"}}
    map_world(context, nodes, [((1, "up"), (2, "up")), ((1, "down"), (2, "down"))], bus_x=actions.BUS_HOME[0])
    actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    bx, by = actions.BUS_HOME
    assert first == (bx + actions.SLOT[0], by + actions.SLOT[1] + 213)  # battle -> event (3), not event -> focused (5)
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_full_read_plans_the_path_and_the_next_step_follows_it_without_a_drag(context, monkeypatch):
    # The user (#111): once the floor's nodes are read, follow the path decided on.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    actions.RUN["floor"] = 1
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "mid"): {"cost"},
             (3, "up"): {"cost", "gift"}, (3, "mid"): {"event"}}
    links = [((1, "up"), (2, "up")), ((1, "down"), (2, "mid")), ((2, "up"), (3, "up")), ((2, "mid"), (3, "mid"))]
    map_world(context, nodes, links, bus_x=actions.BUS_HOME[0])
    actions.RouteMap().run(context, None)  # down battle > mid battle > mid event (5), not up event > battle > focused (7)
    # Steps go from the node before: up from the bottom row to the middle one, then straight on.
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": [("up", "battle"), ("mid", "event")]}

    context.reset_mock()  # on the battle's node now, the map back at rest
    map_world(context, {(1, "up"): {"cost"}, (1, "down"): {"cost"}}, [], bus_x=446)
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_not_called()
    assert context.tasker.controller.post_click.call_args_list[0].args == (446 + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] - 213)
    assert actions.RUN["map_plan"]["steps"] == [("mid", "event")]


def test_a_planned_slot_of_another_type_means_the_map_is_read_again(context, monkeypatch):
    # The bus not where the plan put it, or a node misread from afar: read again rather than follow.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=1, map_plan={"floor": 1, "steps": [("mid", "event")]})
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()  # dragged to the far left for a full read
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": []}


def test_a_planned_slot_not_linked_to_the_bus_means_the_map_is_read_again(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=1, map_plan={"floor": 1, "steps": [("up", "battle")]})
    map_world(context, {(1, "mid"): {"event"}}, [], bus_x=446)
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()  # dragged to the far left for a full read
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": []}  # the new plan: the middle event, nothing after


def test_a_plan_from_the_last_floor_is_not_followed(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=2, map_plan={"floor": 1, "steps": [("mid", "battle")]})
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()
    assert actions.RUN["map_plan"] == {"floor": 2, "steps": []}


def win_rate_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == (984 + 20, 531 + 14)]


def test_a_turn_label_on_a_moving_screen_is_not_played(context):
    # Live (#58): the label matched in the first frames of a turn playing out; Win Rate and START were tapped.
    screens(context, [0, 60, 120, 180, 240, 30, 90, 150, 210, 20, 80, 140])
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    context.tasker.controller.post_click.assert_not_called()


def test_a_turn_over_a_moving_battlefield_is_played(context, monkeypatch):
    # Live 2026-10-21: a swarm of enemies moved over the whole battlefield, the HUD at rest; the screen never
    # read still and turn 3 waited 18 min, twice (BattleTurnSwarm*.png, 3 s apart).
    frames = [np.asarray(Image.open(SCREENS / f"BattleTurnSwarm{s}.png"))[:, :, ::-1] for s in ("", "Next")]
    shots = itertools.cycle(frames)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: next(shots)
    clicks = context.tasker.controller.post_click.call_args_list
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: bool(clicks))  # lit by the Win Rate tap
    actions.PlayTurn().run(context, SimpleNamespace(box=[946, 531, 40, 29]))
    assert [c.args for c in clicks[:2]] == [(946 + 20, 531 + 14), (946 + actions.START_DISC[0], 531 + actions.START_DISC[1])]


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


def touches(context):
    """The controller's touch and tap calls, in order: ("down", (x, y)), ("up", ()), ("click", (x, y))."""
    names = {"post_touch_down": "down", "post_touch_up": "up", "post_click": "click"}
    return [(names[n], a) for n, a, _ in context.tasker.controller.method_calls if n in names]


def hits(context, *shown):
    """The nodes in shown hit on every screen; the others miss."""
    context.run_recognition.side_effect = lambda name, image, override=None: (
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name in shown else None)


@pytest.mark.parametrize("shown", [("BattleTurn",), ("Victory",), ("WipeDialog",), ("RetryPopup",), ("Event",)])
def test_a_held_finger_lifts_once_the_next_turn_or_another_screen_shows(context, clock, shown):
    # #150: held from the turn's start until the next turn waits for input or the battle leaves the screen.
    hits(context, *shown)
    actions.hold_turn(context)
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) < 1


def test_a_held_finger_stays_down_while_the_pause_button_shows(context, clock):
    # In a turn's first frames the Win Rate label can still match: the pause button says the turn plays.
    hits(context, "BattlePause", "BattleTurn")
    actions.hold_turn(context)
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) == pytest.approx(actions.HOLD_LIMIT, abs=actions.HOLD_EVERY)


@pytest.mark.parametrize("shown", actions.BATTLE_POPUPS)
def test_a_held_finger_lifts_on_a_popup_over_the_battle(context, clock, shown):
    # A popup over the battle with the pause button still showing: lift at once, not on it 6 s later.
    hits(context, "BattlePause", shown)
    actions.hold_turn(context)
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) < 1


def test_a_held_finger_reads_no_text_while_the_pause_button_shows(context, clock):
    # #157: no OCR while a turn plays. The screens read by text (Victory, the wipe dialog, an event) hide the
    # pause button (maa-tools test: BattlePause misses on each; it scores 0.34 at most, threshold 0.8).
    hits(context, "BattlePause")
    actions.hold_turn(context)
    looked = {c.args[0] for c in context.run_recognition.call_args_list}
    assert looked == {"BattlePause", *actions.BATTLE_POPUPS}


def test_a_held_finger_lifts_through_a_controller_fetched_after_the_looks(context, clock):
    # Live 2026-10-20: in the agent, a controller kept from before the looks (screen() fetches another) failed
    # its touch up with an access violation, every hold: the finger stayed down until the next tap.
    fresh = []

    def controller(self):
        ctl = MagicMock()
        fresh.append(ctl)
        return ctl
    hits(context, "BattleTurn")
    type(context.tasker).controller = property(controller)
    try:
        actions.hold_turn(context)
    finally:
        del type(context.tasker).controller
    assert [c for c in fresh if c.post_touch_up.called] == [fresh[-1]]


def test_a_held_finger_lifts_when_the_task_is_stopping(context, clock):
    # #145: a finger left down when the bot stopped kept the panel tilted; L1-L3 and a game restart followed.
    hits(context, "BattlePause")
    looks = iter([False, False, True])
    type(context.tasker).stopping = property(lambda self: next(looks))
    try:
        actions.hold_turn(context)
    finally:
        del type(context.tasker).stopping
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]


def test_a_held_finger_lifts_on_an_error(context, clock):
    context.tasker.controller.post_screencap.side_effect = RuntimeError("controller gone")
    with pytest.raises(RuntimeError):
        actions.hold_turn(context)
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]


def test_a_turn_started_by_play_turn_is_held_until_the_next_turn(context, monkeypatch):
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: True)
    monkeypatch.setattr(actions, "turn_started", lambda context, image: True)
    hits(context, "BattleTurn")
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert [t for t, _ in touches(context)] == ["click", "down", "up"]  # START, then the hold


def test_a_turn_that_did_not_start_is_not_held(context, monkeypatch):
    monkeypatch.setattr(actions.battle, "disc_lit", lambda image, x, y: True)
    monkeypatch.setattr(actions, "turn_started", lambda context, image: False)
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert "down" not in [t for t, _ in touches(context)]


def test_the_pause_button_holds_the_turn(context, clock):
    hits(context, "Victory")
    assert actions.HoldTurn().run(context, None)
    assert touches(context) == [("down", actions.HOLD_SPOT), ("up", ())]


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
             tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))],
             tuple(actions.FUSE_LIST): [("E.G.O Gifts Owned", (635, 216, 161, 24))]}  # at its place: nothing over it
SPIDERWEB = {"name": "Spiderweb Entangled in Red", "keyword": "Keywordless", "tier": 3}


def fuse_slots(context, monkeypatch, slots=3, ignored=()):
    """The fuse page's read-back (shop.fuse_slots, placed, picked; test_shop checks them on live captures) as the
    game would show it: a tap on a cell puts its gift in or takes it out, but not on a cell in ignored."""
    def inside():
        taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
        return {c for c in actions.FUSE_CELLS if c not in ignored and taps.count(c) % 2}
    monkeypatch.setattr(actions.shop, "fuse_slots", lambda image: slots)
    monkeypatch.setattr(actions.shop, "placed", lambda image, n: len(inside()))
    monkeypatch.setattr(actions.shop, "picked", lambda image, x, y, bottom=720: (x, y) in inside())


def test_a_fusion_taps_only_the_materials_its_cells_show(context, monkeypatch):
    # #112: one screenshot decides. Spiderweb (observed), Burn (main) and keywordless gifts stay. #161: the badge-less
    # cell 3 matched no vestige icon: a keywordless gift, kept without a tap.
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, ("Keywordless", SPIDERWEB["name"]), ("Bleed", None), ("Burn", None), ("Keywordless", None),
               ("Tremor", None), ("Pierce", None), ("Sinking", None), (None, None))
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": [SPIDERWEB]}}, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [taps.count(c) for c in actions.FUSE_CELLS[:8]] == [0, 1, 0, 0, 1, 1, 0, 0]
    assert actions.PAGE_OK in taps


@pytest.mark.parametrize("tier, vestige", [(1, "Dark Vestige"), (2, "Faint Vestige"), (3, "Twinkling Vestige"),
                                           (4, "Brilliant Vestige")])
def test_vestiges_are_fused_though_keywordless_gifts_are_kept(context, monkeypatch, tier, vestige):
    # #161, the user: vestiges are their own kind, only fusion material; keywordless "keep" (the default) does not keep
    # them. Each is told by its icon: no cell is opened; the vestige goes in, the keywordless gift stays.
    fused, taps, _ = fusion_taps(context, monkeypatch, {}, ("Keywordless", vestige, tier), ("Keywordless", None, 2),
                                 ("Tremor", None), ("Pierce", None))
    assert fused and taps == [1, 0, 1, 1]


@pytest.mark.parametrize("keywordless", ["keep", "fuse_or_sell"])
def test_lunar_vestige_is_never_fused(context, monkeypatch, keywordless):
    # #161: a tier V is never a material (MAX_MATERIAL_TIER).
    fused, taps, _ = fusion_taps(context, monkeypatch, {"keywordless": keywordless}, ("Keywordless", "Lunar Vestige", 5),
                                 ("Tremor", None), ("Pierce", None), ("Sinking", None))
    assert fused and taps == [0, 1, 1, 1]


def test_a_lunar_vestige_that_alone_would_complete_a_group_stays_out(context, monkeypatch):
    # #161: with keywordless gifts let go, the tier V vestige still stays out: no fusion, no cell opened.
    fused, taps, ok = fusion_taps(context, monkeypatch, {"keywordless": "fuse_or_sell"}, ("Keywordless", "Lunar Vestige", 5),
                                  ("Tremor", None), ("Pierce", None))
    assert not fused and not ok and taps == [0, 0, 0]


def test_a_vestige_the_team_keeps_by_name_is_not_fused(context, monkeypatch):
    # #161: the user's per-gift keep list still applies to vestiges.
    team = {"keep_gifts": [{"keyword": "Keywordless", "tier": 1, "name": "Dark Vestige"}]}
    fused, taps, _ = fusion_taps(context, monkeypatch, team, ("Keywordless", "Dark Vestige", 1), ("Tremor", None),
                                 ("Pierce", None), ("Sinking", None))
    assert fused and taps == [0, 1, 1, 1]


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


def sale_taps(context, monkeypatch, team, prices, *readings):
    """Shop.sell with 100 Cost and a 180 wanted, readings (cells_read) priced prices on the grid: the cells it tapped."""
    lines = [(str(p), (x - 3, y + 37, 26, 20)) for p, (x, y) in zip(prices, actions.SELL_CELLS)]
    reads(context, {tuple(actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                    tuple(actions.SELL_COST): [("100", (980, 90, 60, 30))], tuple(actions.SELL_GRID): lines})
    cells_read(monkeypatch, *readings)
    actions.Shop.sell(context, {"keyword": "Burn", "reserve_cost": 0, "gift_search": {"gifts": []}, **team},
                      {"wanted": 180, "sold": False})
    return [c.args for c in context.tasker.controller.post_click.call_args_list if c.args in actions.SELL_CELLS]


def test_a_sale_reads_keywords_and_prices_off_the_grid_and_taps_only_what_it_sells(context, monkeypatch):
    # #112: no gift is tapped to read its panel: the badge-less one matched no vestige icon, a kept keywordless gift
    # (#161). #79: Tremor III + Pierce III + Sinking II fuse into a tier IV; the Bleed I no fusion uses goes, though
    # Tremor's price is higher.
    taps = sale_taps(context, monkeypatch, {}, [90, 300, 200, 120, 60, 80], ("Bleed", None, 1), ("Burn", None),
                     ("Keywordless", None), ("Tremor", None, 3), ("Pierce", None, 3), ("Sinking", None, 2))
    assert taps == [actions.SELL_CELLS[0]]


def test_a_sale_skips_the_teams_kept_gifts(context, monkeypatch):
    # #79: Spiderweb (keep_gifts, by its icon) is the dearest and no fusion would use it once keywordless gifts may go:
    # it stays. Of Bleed, Tremor, Pierce and Sinking, 3 fuse and the one left over goes.
    team = {"keywordless": "fuse_or_sell", "keep_gifts": [SPIDERWEB]}
    taps = sale_taps(context, monkeypatch, team, [400, 90, 60, 70, 80], ("Keywordless", SPIDERWEB["name"], 3),
                     ("Bleed", None), ("Tremor", None), ("Pierce", None), ("Sinking", None))
    assert taps == [actions.SELL_CELLS[4]]


@pytest.mark.parametrize("team, leftover, sold", [
    ({}, 5, False),  # a tier V no fusion takes (pick_fusion never does) is not sold by default
    ({"sell_max_tier": 5}, 5, True),
    ({"sell_max_tier": 2}, 3, False),  # a tier III leftover is over a lower limit
    ({"sell_max_tier": 3}, 3, True),
])
def test_a_sale_stops_at_the_teams_highest_tier(context, monkeypatch, team, leftover, sold):
    # #161: three tier II fuse; the fourth, the leftover, would cover the price.
    taps = sale_taps(context, monkeypatch, team, [90, 60, 70, 300], ("Bleed", None), ("Tremor", None),
                     ("Pierce", None), ("Slash", None, leftover))
    assert taps == ([actions.SELL_CELLS[3]] if sold else [])


@pytest.mark.parametrize("keywordless, sold", [("keep", False), ("fuse", False), ("fuse_or_sell", True)])
def test_a_sale_follows_the_keywordless_setting(context, monkeypatch, keywordless, sold):
    # #161: a keywordless leftover goes only with "fuse_or_sell"; "fuse" keeps it for fusions, and "keep" keeps it
    # everywhere. Its badge-less cell matched no vestige icon: the setting alone decides.
    taps = sale_taps(context, monkeypatch, {"keywordless": keywordless}, [90, 60, 70, 95], ("Bleed", None),
                     ("Tremor", None), ("Pierce", None), ("Keywordless", None, 2))
    assert taps.count(actions.SELL_CELLS[3]) == int(sold)  # the sale's tap only


@pytest.mark.parametrize("keywordless", ["keep", "fuse", "fuse_or_sell"])
@pytest.mark.parametrize("team, sold", [({}, False), ({"sell_vestiges": True}, True),
                                        ({"sell_vestiges": True, "sell_max_tier": 1}, True)])
def test_a_vestige_is_sold_only_when_the_team_allows_it(context, monkeypatch, keywordless, team, sold):
    # #161: sell_vestiges alone decides, whatever the keywordless setting. Dark Vestige is told by its icon: its cell
    # is tapped only to sell it.
    taps = sale_taps(context, monkeypatch, {"keywordless": keywordless, **team}, [90, 60, 70, 95], ("Bleed", None),
                     ("Tremor", None), ("Pierce", None), ("Keywordless", "Dark Vestige", 1))
    assert taps.count(actions.SELL_CELLS[3]) == int(sold)


def test_a_vestige_over_the_highest_tier_sold_stays(context, monkeypatch):
    # #161: sell_max_tier applies to vestiges too; a Twinkling Vestige (III) over a limit of II is not sold.
    taps = sale_taps(context, monkeypatch, {"sell_vestiges": True, "sell_max_tier": 2}, [90, 60, 70, 95],
                     ("Bleed", None), ("Tremor", None), ("Pierce", None), ("Keywordless", "Twinkling Vestige", 3))
    assert taps == []


def test_nothing_is_sold_when_every_material_fuses(context, monkeypatch):
    # #79: 3 materials make a fusion; a sale would only break it.
    assert sale_taps(context, monkeypatch, {}, [90, 60, 70], ("Bleed", None), ("Tremor", None), ("Pierce", None)) == []


@pytest.mark.parametrize("team, gift", [({"keywordless": "fuse"}, None), ({}, "Dark Vestige")])
def test_a_sale_counts_the_fusion_materials_it_may_not_sell(context, monkeypatch, team, gift):
    # #79: a keywordless gift under "fuse", or a vestige the team does not sell, is still fusion material: Bleed and
    # Tremor fuse with it, so neither is sold. Neither is opened (#161).
    taps = sale_taps(context, monkeypatch, team, [90, 95, 60], ("Bleed", None), ("Tremor", None), ("Keywordless", gift, 1))
    assert taps == []


def test_a_sale_does_not_break_a_fusion_by_selling_white_gossypium(context, monkeypatch):
    # #79, #90: White Gossypium is sold first, so the fusion is grouped without it: Tremor, Pierce and Sinking fuse.
    # Its 50 alone does not cover the price: nothing is sold (grouped with it, Sinking would go too, and no fusion).
    taps = sale_taps(context, monkeypatch, {"allow_white_gossypium": False}, [50, 60, 70, 80], ("Bleed", GOSSYPIUM, 1),
                     ("Tremor", None, 1), ("Pierce", None, 1), ("Sinking", None, 1))
    assert taps == []


def live_shop(context, reads_now):
    """A game that reacts to taps: each tap changes the screen, and OCR reads reads_now(taps)[roi]."""
    taps = []

    def click(x, y):
        taps.append((x, y))
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: np.full((720, 1280, 3), len(taps) * 20 % 256, np.uint8)

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in reads_now(taps).get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    return taps


def sell_page(confirmed):
    """The sell page of #174: 51 Cost, cell 0 a Bleed gift for 95; a picked cell previews the Cost as 51146.
    Sell asks to confirm; confirmed(taps) says whether the sale went through."""
    def reads_now(taps):
        sold = confirmed(taps)
        picked = actions.SELL_CELLS[0] in taps and not sold
        asked = taps[-1:] == [actions.PAGE_OK]
        return {tuple(actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                tuple(actions.SELL_COST): [("146" if sold else "51146" if picked else "51", (980, 90, 60, 30))],
                tuple(actions.SELL_GRID): [] if sold else [("95", (680, 295, 26, 20))],
                tuple(actions.DIALOG_TEXT): [("Sell [Today's Expression] for 95 Cost?", (460, 330, 360, 25))] if asked else []}
    return reads_now


SELLER = {"keyword": "Burn", "reserve_cost": 0, "gift_search": {"gifts": []}}


def test_a_sale_confirms_the_sell_dialog(context, monkeypatch):
    # #174 (live 2026-10-19): Sell asked "Sell [Today's Expression] for 95 Cost?" and the bot cancelled it.
    taps = live_shop(context, sell_page(lambda taps: actions.DIALOG_CONFIRM in taps))
    cells_read(monkeypatch, ("Bleed", None))
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    assert actions.Shop.sell(context, SELLER, {"wanted": 145, "sold": False})
    assert taps.index(actions.SELL_CELLS[0]) < taps.index(actions.PAGE_OK) < taps.index(actions.DIALOG_CONFIRM)
    assert "shop: sold cell 0 for 95: 51 -> 146 Cost" in logs


def test_the_cost_preview_of_a_picked_cell_is_not_a_sale(context, monkeypatch):
    # #174: the picked cell's "51 > 146" read as 51146, and the bot took the Cost as changed: sold.
    live_shop(context, sell_page(lambda taps: False))
    cells_read(monkeypatch, ("Bleed", None))
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    actions.Shop.sell(context, SELLER, {"wanted": 145, "sold": False})
    assert any("not sold" in line for line in logs)
    assert not any("sold cell" in line for line in logs)


def test_a_keyword_refresh_waits_for_the_new_cost_not_a_fixed_time(context, clock):
    # Live 2026-10-19: a keyword refresh slept 1.5 + 1 + 2 + 1 s; the screen stops 0.5-0.6 s after OK.
    def reads_now(taps):
        cost = "410" if actions.KEYWORD_REFRESH in taps else "500"
        return {tuple(actions.SHOP_COST): [(cost, (560, 120, 60, 30))],
                tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                tuple(actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))],
                tuple(actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))]}
    taps = live_shop(context, reads_now)
    visit = {"wanted": None, "sold": False, "refreshes": 0}
    assert actions.Shop.buy(context, {"keyword": "Burn", "reserve_cost": 0, "shop_refresh_limit": 1}, visit)
    assert visit["refreshes"] == 1 and taps == [actions.REFRESH["keyword"][0], (330, 360), actions.KEYWORD_REFRESH]
    assert sum(clock) < 1.5


def test_a_keyword_refresh_checks_the_page_before_its_first_tap(context, clock, monkeypatch):
    # #118 (ADR 0007): the shop gone after its Cost was read, the refresh's first tap does not go out.
    def gone(context, home, image=None):
        raise actions.PageGone(home)
    monkeypatch.setattr(actions, "page_guard", gone)
    taps = live_shop(context, lambda taps: {tuple(actions.SHOP_COST): [("500", (560, 120, 60, 30))],
                                            tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                                            tuple(actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))]})
    visit = {"wanted": None, "sold": False, "refreshes": 0}
    with pytest.raises(actions.PageGone):
        actions.Shop.buy(context, {"keyword": "Burn", "reserve_cost": 0, "shop_refresh_limit": 1}, visit)
    assert taps == []


def test_the_leave_dialog_is_read_with_its_spaces_dropped(context, clock, monkeypatch):
    # #160: OCR drops spaces ("LEAVE THESHOP?"); has() compacts both sides, as main's Leave does.
    actions.RUN["team"] = {"heal": "none", "keyword": "Burn", "reserve_cost": 0}
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a: False))
    taps = live_shop(context, lambda taps: {tuple(actions.LEAVE_DIALOG): [("LEAVE THESHOP?", (480, 325, 300, 35))]}
                     if taps else {})
    assert actions.Shop().run(context, argv())
    assert actions.LEAVE_CONFIRM in taps and actions.STUCK["flag"] is None


GOSSYPIUM = "White Gossypium"
NO_GOSSYPIUM = {"keyword": "Bleed", "reserve_cost": 0, "gift_search": {"gifts": []}, "allow_white_gossypium": False}


def test_a_team_without_white_gossypium_fuses_it_first(context, monkeypatch):
    # #90: a Bleed team that does not hold it: its icon makes it material, ahead of the other materials.
    reads(context, {**FUSE_PAGE, tuple(actions.KEYWORD_LABELS): [("Bleed", (300, 400, 60, 20))]})
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, ("Burn", None), ("Tremor", None), ("Pierce", None), ("Bleed", GOSSYPIUM), ("Bleed", None))
    actions.Shop.fuse(context, NO_GOSSYPIUM, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert [taps.count(c) for c in actions.FUSE_CELLS[:5]] == [1, 1, 0, 1, 0]


def test_a_team_without_white_gossypium_does_not_buy_it(context, monkeypatch):
    # #90: White Gossypium is a Bleed gift; the Bleed team buys the other Bleed offer only.
    offers = [("White Gossypium", (570, 333, 90, 17)), ("140", (600, 306, 40, 24)),
              ("Wound Clerid", (725, 333, 90, 17)), ("150", (755, 306, 40, 24))]
    costs, tapped = [500], []

    def click(x, y):
        tapped.append((x, y))
        if (x, y) == actions.PURCHASE:
            costs.append(costs[-1] - 150)
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
    cells_read(monkeypatch, ("Bleed", GOSSYPIUM, 2), ("Bleed", None, 2))
    assert actions.Shop.buy_offers(context, NO_GOSSYPIUM, {"wanted": None, "sold": False}) == 1
    assert [t for t in tapped if t[1] == 268] == [(775, 268)]


def gift_page(context, monkeypatch, names):
    """A gift choice page with a Bleed card per name, Select 0/1."""
    taps = []
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.GIFT_CARDS:
            return [r for i, n in enumerate(names) for r in
                    [("Acquire E.G.O Gift", (200 + 300 * i, 160, 150, 20)), (n, (210 + 300 * i, 250, 150, 20)),
                     ("Inflict Bleed", (210 + 300 * i, 300, 150, 20))]]
        picked = any(y == 300 for _, y in taps)
        selected = actions.GIFT_SELECT in taps
        if roi == actions.GIFT_COUNT:
            return [(f"Select {int(picked)}/1", (1080, 565, 100, 30))]
        if roi == actions.REFUSE_GIFT and not (selected and picked):
            return [("Refuse Gift", (900, 570, 100, 25))]
        return []
    monkeypatch.setattr(actions, "ocr", ocr)
    actions.RUN.update(settings={"trial_risk_overrides": []}, team={**NO_GOSSYPIUM, "trial_risk_weight": "high"})
    return taps


def test_a_team_without_white_gossypium_picks_another_gift(context, monkeypatch):
    taps = gift_page(context, monkeypatch, [GOSSYPIUM, "Wound Clerid"])
    actions.PickGift().run(context, None)
    assert [t for t in taps if t[1] == 300] == [(536, 300)]  # the second card only


def test_a_team_without_white_gossypium_takes_it_when_it_is_the_only_card(context, monkeypatch):
    # #90 (the user, 2026-10-18): taken rather than a random trial for the choice left; the shop then
    # fuses or sells it first (test_a_team_without_white_gossypium_fuses_it_first).
    taps = gift_page(context, monkeypatch, [GOSSYPIUM])
    actions.PickGift().run(context, None)
    assert taps == [(236, 300), actions.GIFT_SELECT]
    assert actions.STUCK["flag"] is None


def fusion_taps(context, monkeypatch, team, *readings, slots=3, ignored=(), confirm=3):
    """Shop.fuse on readings (cells_read) with the read-back of fuse_slots; (its result, how often each cell was tapped,
    whether Fuse was pressed). The confirm dialog reads "confirm/slots"."""
    reads(context, {**FUSE_PAGE, tuple(actions.FUSE_CONFIRM): [(f"Selected E.G.O Gifts {confirm}/{slots}", (330, 175, 320, 30))],
                    tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]})
    fuse_slots(context, monkeypatch, slots, ignored)
    cells_read(monkeypatch, *readings)
    fused = actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}, **team}, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    return fused, [taps.count(c) for c in actions.FUSE_CELLS[:len(readings)]], actions.PAGE_OK in taps


def test_a_fusion_puts_in_the_materials_that_make_the_highest_tier(context, monkeypatch):
    # #77: III + III + II make a tier IV; the three I would make only a tier I.
    fused, taps, ok = fusion_taps(context, monkeypatch, {}, ("Bleed", None, 1), ("Bleed", None, 3), ("Pierce", None, 1),
                                  ("Tremor", None, 2), ("Slash", None, 3), ("Sinking", None, 1))
    assert fused and ok and taps == [0, 1, 0, 1, 1, 0]


def test_the_teams_kept_keywords_and_gifts_stay_out_of_a_fusion(context, monkeypatch):
    # #77: Bleed is kept besides Burn; Spiderweb is kept by its icon (keep_gifts).
    team = {"keep_keywords": ["Bleed"], "keep_gifts": [SPIDERWEB]}
    fused, taps, _ = fusion_taps(context, monkeypatch, team, ("Bleed", None), ("Keywordless", SPIDERWEB["name"], 3),
                                 ("Sinking", None), ("Tremor", None), ("Bleed", None), ("Pierce", None))
    assert fused and taps == [0, 0, 1, 1, 0, 1]


@pytest.mark.parametrize("keywordless", ["fuse", "fuse_or_sell"])
def test_keywordless_gifts_let_go_join_the_highest_tier_pick(context, monkeypatch, keywordless):
    # The user on #161: a keywordless gift that may be fused is a material like any other, not only when the others
    # make no fusion. Tremor III + Pierce III + Sinking I would make a III; with the keywordless III, a IV. Its cell
    # matched no vestige icon: the setting decides.
    fused, taps, _ = fusion_taps(context, monkeypatch, {"keywordless": keywordless}, ("Keywordless", None, 3),
                                 ("Tremor", None, 3), ("Pierce", None, 3), ("Sinking", None, 1))
    assert fused and taps == [1, 1, 1, 0]


def test_a_keywordless_gift_the_team_keeps_stays_out_of_the_pick(context, monkeypatch):
    # The user on #161: keep_gifts still applies, by the gift's icon.
    team = {"keywordless": "fuse", "keep_gifts": [SPIDERWEB]}
    fused, taps, _ = fusion_taps(context, monkeypatch, team, ("Keywordless", SPIDERWEB["name"], 3), ("Tremor", None, 3),
                                 ("Pierce", None, 3), ("Sinking", None, 1))
    assert fused and taps == [0, 1, 1, 1]


def test_a_super_shop_fuses_up_to_5(context, monkeypatch):
    # #77: 5 tier I make a tier III by the Super Shop's thresholds; its confirm dialog reads 5/5.
    fused, taps, _ = fusion_taps(context, monkeypatch, {}, *[("Bleed", None, 1)] * 5, slots=5, confirm=5)
    assert fused and taps == [1] * 5


def test_a_material_that_does_not_show_in_the_fusion_closes_the_page(context, monkeypatch):
    # #77: the second tap put nothing in (or another gift): Close, no Fuse, and not the same scan again.
    visit = {}
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch, ignored=[actions.FUSE_CELLS[1]])
    cells_read(monkeypatch, ("Bleed", None), ("Tremor", None), ("Pierce", None))
    assert not actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, visit)
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert actions.PAGE_OK not in taps and actions.PAGE_CLOSE in taps
    assert [taps.count(c) for c in actions.FUSE_CELLS[:3]] == [1, 1, 0]  # stopped at the second
    assert visit["fuse_scanned"]


def test_a_fusion_is_not_confirmed_when_the_dialog_counts_other_materials(context, monkeypatch):
    fused, _, ok = fusion_taps(context, monkeypatch, {}, *[("Bleed", None)] * 3, confirm=2)
    assert ok and not fused


def test_the_fusion_grid_is_not_scanned_again_while_the_owned_gifts_are_the_same(context, monkeypatch):
    # The fuse page with its keyword dialog, no materials: no fusion this visit.
    reads(context, FUSE_PAGE)
    scans = []
    monkeypatch.setattr(actions, "owned_cells", lambda *a: scans.append(a) or ([], {"page": "fuse", "at": 0}))
    team, visit = {"keyword": "Burn", "gift_search": {"gifts": []}}, {}
    assert not actions.Shop.fuse(context, team, visit)
    taps = context.tasker.controller.post_click.call_count
    assert len(scans) == 1
    assert not actions.Shop.fuse(context, team, visit)  # nothing bought or sold since
    assert context.tasker.controller.post_click.call_count == taps and len(scans) == 1


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


def test_recover_keeps_the_screen_when_the_hub_recognised_nothing(context, clock, monkeypatch, tmp_path):
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    actions.STUCK["flag"] = None
    actions.STUCK["watch"].reset()
    actions.Recover().run(context, None)
    assert len(list((tmp_path / "logs" / "unknown").glob("*.png"))) == 1
    actions.STUCK["ladder"].__init__()


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


CLOSING = {"roi": [600, 440, 80, 35], "expected": "^Continue$"}


def test_tap_until_gone_waits_for_the_text_the_tap_closes_to_go(context, clock):
    # #254: a dialog fades out for a while with its text still readable; the hub would press it again.
    page(context, {(600, 440, 80, 35): lambda clicks, looks: "Continue" if looks < 4 else None})
    param = {"target": [600, 440, 80, 35], "gone": CLOSING}
    assert actions.TapUntil().run(context, argv(param))
    assert taps(context) == [(640, 457)]
    assert context.tasker.controller.post_screencap.call_count == 4  # one before the tap, then until()'s looks
    no_fixed_wait(clock)


def test_tap_until_gone_counts_the_next_popup_in_the_same_place_as_gone(context, clock):
    # ClaimPopup: Rewards Acquired is followed by Pass Level Up in the same roi, both matching the node's expected.
    roi, both = [500, 225, 280, 50], "Rewards Acquired|Pass Level Up"
    page(context, {tuple(roi): lambda clicks, looks: "Rewards Acquired" if looks < 3 else "Pass Level Up"})
    assert actions.TapUntil().run(context, argv({"target": [575, 455, 130, 35], "gone": {"roi": roi, "expected": both}}))
    assert context.tasker.controller.post_screencap.call_count == 3
    no_fixed_wait(clock)


def test_tap_until_gone_has_nothing_to_wait_for_when_the_text_is_already_gone(context, clock):
    page(context, {})
    assert actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING}))
    assert taps(context) == [(640, 457)]
    assert context.tasker.controller.post_screencap.call_count == 2  # the look before the tap, the one after it
    assert sum(clock) == 0


def test_tap_until_gone_gives_up_after_its_timeout(context, clock):
    page(context, {(600, 440, 80, 35): "Continue"})
    assert actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING, "timeout": 2}))
    assert 2 <= sum(clock) < 2.5


def test_tap_until_logs_how_long_the_screen_took(context, clock):
    # #254: the live run reads the wait from the log; the fixed delay it replaces was never measured.
    page(context, {(600, 440, 80, 35): lambda clicks, looks: "Continue" if looks < 4 else None})
    actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING}, node="ProgressPanel"))
    assert "ProgressPanel: screen changed after 0.4 s" in actions.LOG[-1]


def test_plan_run_waits_for_the_enter_dialog_after_pressing_enter(context, clock, monkeypatch):
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 3, "hard_from_floor": 1}
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


@pytest.mark.parametrize(("setting", "expected"), [("auto", "normal"), ("hard", "hard")])
def test_a_planned_run_of_a_team_that_never_switches_to_hard(context, clock, monkeypatch, setting, expected):
    # #137: auto with weekly bonuses left decides hard, but this team's switch to hard is off: the run is NORMAL.
    # Only the global "hard" makes it HARD (every floor, hard_wanted).
    team = {"id": 1, "name": "t", "game_team": 1, "guard_turns": 0, "hard_from_floor": None}
    run = {"runs": None, "stop_when_weekly_bonus_out": False, "difficulty": setting}
    monkeypatch.setattr(actions, "load_settings", lambda root: {"run": run, "teams": [team]})
    monkeypatch.setattr(actions, "pick_team", lambda teams, cursor, difficulty: team)
    monkeypatch.setattr(actions, "read_cursor", lambda root, address: None)
    monkeypatch.setattr(actions.run_start, "run_difficulty", lambda setting, weekly: "hard")
    monkeypatch.setattr(actions.recovery, "read_runs", lambda root: [])
    monkeypatch.setattr(actions.recovery, "floor_limit", lambda runs, team: 1800)
    page(context, {})
    actions.PlanRun().run(context, argv())
    assert actions.RUN["difficulty"] == expected


def team_picker(context, title, after_confirm):
    """The team list shows TEAMS #3 at y 390; title(clicks, looks) is the card's title text, after_confirm(clicks, looks) the next page."""
    page(context, {tuple(actions.TEAM_LIST): [("TEAMS #3", (100, 380, 80, 20))], (220, 112, 210, 26): title,
                   (1160, 522, 60, 34): "63", (400, 230, 480, 90): after_confirm})


def infinity_switch(context, monkeypatch, takes):
    """The entry page's Parallel Superposition Mode reads ON until a tap on INFINITY MIRROR takes (if it does)."""
    taps, stops = [], []
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: stops.append(reason) or False)

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.INFINITY_TITLE:
            # As MaaFramework read EntryNewRun.png and the synthetic EntryParallelOn.png
            return [(f"Alll/Parallel Superposition Mode:{'OFF' if takes and taps else 'ON'}/l", (891, 333, 324, 20))]
        return []
    monkeypatch.setattr(actions, "ocr", ocr)
    return taps, stops, actions.ParallelModeOff().run(context, None)


def test_a_parallel_superposition_switch_left_on_is_switched_off(context, clock, monkeypatch):
    # #94: the bot never plays past floor 5.
    taps, stops, result = infinity_switch(context, monkeypatch, takes=True)
    assert result is True and taps == [actions.INFINITY_BUTTON] and stops == []


def test_a_parallel_superposition_switch_that_stays_on_stops_the_task(context, clock, monkeypatch):
    taps, stops, result = infinity_switch(context, monkeypatch, takes=False)
    assert result is False and taps == [actions.INFINITY_BUTTON] * 2 and len(stops) == 1


def test_select_team_waits_for_the_title_after_the_tap_and_for_the_page_after_confirm(context, clock, monkeypatch):
    monkeypatch.setattr(actions, "scroll", lambda *a: None)  # the drag to the top has its own waits
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


@pytest.mark.parametrize("left_at", [0, 4, 10])
def test_select_team_drags_the_list_to_its_top_before_it_looks_for_the_team(context, clock, monkeypatch, left_at):
    # #226: the list opens wherever it was left; it goes to the top first, then down to the slot.
    actions.RUN["team"] = {"game_team": 8}
    state = {"first": left_at, "tapped": None, "drags": []}  # first: the number of the first row on show
    rows = lambda: {n: 309 + 36 * (n - state["first"]) for n in range(state["first"], state["first"] + 7)}

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.TEAM_LIST:
            return [(f"TEAMS #{n}", (100, y - 10, 80, 20)) for n, y in rows().items()]
        return [(f"TEAMS #{state['tapped']}", tuple(roi))] if roi == actions.TEAM_TITLE and state["tapped"] else []

    def scroll(context, x, y, dx, dy):
        state["drags"].append(dy)
        state["first"] = min(max(state["first"] - 4 * (1 if dy > 0 else -1), 0), 20)  # 140 px = 4 rows

    def click(x, y):
        if x == 130:
            state["tapped"] = next((n for n, ry in rows().items() if abs(ry - y) < 18), None)
        return MagicMock()
    monkeypatch.setattr(actions, "ocr", ocr)
    monkeypatch.setattr(actions, "scroll", scroll)
    context.tasker.controller.post_click.side_effect = click
    assert actions.SelectTeam().run(context, argv())
    assert state["tapped"] == 8
    drags = state["drags"]
    assert drags[0] > 0  # the first drag moves the content down, towards the top, even from the top itself
    top = max(i for i, d in enumerate(drags) if d > 0)
    assert all(d > 0 for d in drags[:top + 1]) and all(d < 0 for d in drags[top + 1:])  # all the way up, then down
    assert (top == 0) == (left_at == 0)  # already at the top: one drag that moves nothing


def test_select_team_makes_a_plan_for_an_abandoned_empty_run_instead_of_backing_out(context, clock, monkeypatch):
    # #128 (live 2026-10-18): Resume on a run paused before team selection reaches the picker with no plan in memory;
    # backing out to the entry page, which only offers Resume, looped every 8 s.
    team = {"id": 1, "name": "t", "game_team": 3, "guard_turns": 0}
    monkeypatch.setattr(actions, "load_settings", lambda root: {"run": {"difficulty": "normal"}, "teams": [team]})
    monkeypatch.setattr(actions, "pick_team", lambda teams, cursor, difficulty: team)
    monkeypatch.setattr(actions, "read_cursor", lambda root, address: None)
    actions.RUN.clear()
    team_picker(context, "TEAMS #3", lambda clicks, looks: "recommended level" if clicks else None)
    assert actions.SelectTeam().run(context, argv())
    assert taps(context) == [(130, 390), (1145, 587)]  # no back arrow (97, 42)
    assert actions.RUN["team"] is team


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


def starlight_page(context, available, owned):
    """The starlight page with Available and the Owned box as texts or f(clicks, looks); card 1's price reads 10."""
    page(context, {tuple(actions.STARLIGHT_AVAILABLE): available, tuple(actions.STARLIGHT_OWNED): owned,
                   (250, 149, 80, 28): "10", (480, 210, 320, 35): "Continue with selected effects?"})


def buy_grace_1(monkeypatch, unaffordable):
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": unaffordable}}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"priority": [1], "levels": ["base"] + ["none"] * 9})


def test_a_configured_grace_is_bought_with_owned_starlight_when_available_falls_short(context, clock, monkeypatch):
    # #96: the user chose the grace, so owned starlight pays the 5 that Available (5 of 10) cannot (live: "0+5").
    buy_grace_1(monkeypatch, "stop")
    starlight_page(context, lambda clicks, looks: "5" if clicks == 0 else "0+5", lambda clicks, looks: "4035" if clicks == 0 else "4035-5")
    assert actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(230, 252), (1195, 672)]
    assert actions.RUN["starlight_unspent"] == 0


def test_graces_beyond_available_and_owned_follow_starlight_unaffordable_skip(context, clock, monkeypatch):
    buy_grace_1(monkeypatch, "skip")
    starlight_page(context, "5", "2")
    assert actions.BuyStarlight().run(context, argv())
    assert taps(context) == [(1195, 672)]  # nothing bought, Enter only


def test_graces_beyond_available_and_owned_follow_starlight_unaffordable_stop(context, clock, monkeypatch):
    stopped = []
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: stopped.append(reason) or False)
    buy_grace_1(monkeypatch, "stop")
    starlight_page(context, "5", "2")
    assert actions.BuyStarlight().run(context, argv()) is False
    assert stopped == ["a planned grace is unaffordable"] and taps(context) == []


def test_the_confirm_dialog_is_confirmed_when_the_graces_spent_owned_starlight(context, clock, monkeypatch):
    # #96: "-60" in the dialog's Owned box is the consented spend, not a reason to cancel.
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"convert_leftover": False})
    page(context, {(870, 165, 85, 25): "-60", (660, 395, 320, 90): "Any unspent Starlight will be added",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks else None})
    assert actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(738, 530)]


def test_convert_starlight_to_cost_is_switched_without_a_fixed_wait(context, clock, monkeypatch):
    # #115: the checkbox tap slept 1 s; the note under it says when it took.
    actions.RUN["settings"] = {}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"convert_leftover": True})
    page(context, {tuple(actions.STARLIGHT_NOTE): lambda clicks, looks: "Coverts any remaining Starlight" if clicks and looks >= 3 else "Any unspent Starlight will be added",
                   (780, 145, 230, 35): lambda clicks, looks: "Selected E.G.O Gift" if clicks >= 2 else None})
    assert actions.ConfirmStarlight().run(context, argv())
    assert taps(context) == [(727, 363), (738, 530)]
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


def search_page(context, rules=None):
    """The search page with Spiderweb picked (Select 1/1, 70 starlight): Select asks to consume, Confirm shows the GET window."""
    page(context, {tuple(actions.SEARCH_COUNT): "Select 1/1", (922, 205, 270, 34): "Spiderweb Entangled in Red",
                   tuple(actions.SEARCH_OWNED[0]): "1542-70", tuple(actions.SEARCH_OWNED[1]): "1472",
                   tuple(actions.SEARCH_DIALOG): lambda clicks, looks: "Consume 70 Starlight to search and obtain these E.G.O Gifts?" if clicks == 1 else None,
                   GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks >= 2 else None, **(rules or {})})
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


REFRESH = (1083, 47)


def pack_page(context, monkeypatch, floor, setting, mode):
    """PickThemePack on a fake floor page of two cards weighing -5 and read as packs the data file lacks (a new pair
    after each of 4 refreshes; a 5th changes nothing: used up). Returns (refresh taps, log lines)."""
    actions.RUN.update(settings={"run": {"theme_pack_refresh": setting}}, team={"hard_from_floor": 0}, difficulty=None)
    plan = {"weights": {}, "threshold": 0, "unlisted": -5, "event_packs": mode}
    art = {"Hello Bus": "S.E.A."}
    monkeypatch.setattr(actions, "theme_pack_plan", lambda settings, team: (plan, [], set(), art))

    def rank_packs(cards, names, plan, title_art):
        assert title_art is art  # every page, a refreshed one too, gets the data file's title art (#246)
        return [(c[0], -5) for c in cards]
    monkeypatch.setattr(actions.run_start, "rank_packs", rank_packs)
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    taps = []
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))

    def ocr(context, image, roi, only_rec=False):
        page = min(taps.count(REFRESH), 4)
        return {
            (480, 100, 320, 40): [(f"FLOOR {floor}", (560, 110, 80, 20))] if not context.tasker.controller.post_swipe.called else [],
            (830, 30, 160, 35): [("NORMAL", (900, 40, 60, 20))],
            tuple(actions.PACK_TITLES): [(f"Pack {page}a", (200, 420, 90, 20)), (f"Pack {page}b", (500, 420, 90, 20))],
        }.get(tuple(roi), [])
    monkeypatch.setattr(actions, "ocr", ocr)

    actions.PickThemePack().run(context, None)
    assert context.tasker.controller.post_swipe.call_count == 1  # one card is pulled whatever the page
    return taps.count(REFRESH), lines


def test_theme_pack_titles_are_read_once_the_cards_stop_swinging(context, monkeypatch):
    # #246, recordings: dealt cards swing for ~2.8 s. Read mid-swing, a card not landed yet was left out and title
    # art was misread. Every read waits for the cards to stop, the refreshed page's too.
    order = []
    monkeypatch.setattr(actions, "still", lambda context, **kw:
                        order.append(("still", tuple(kw.get("roi") or ()), kw.get("runs"), kw.get("timeout"))) or actions.screen(context))
    real = actions.pack_titles
    monkeypatch.setattr(actions, "pack_titles", lambda context, image: order.append("read") or real(context, image))
    pack_page(context, monkeypatch, 2, "once", "weight")
    reads = [i for i, o in enumerate(order) if o == "read"]
    assert len(reads) == 2  # the page and the refreshed page
    assert all(order[i - 1] == ("still", tuple(actions.PACK_CARDS), 2, actions.CARDS_SETTLE) for i in reads)
    assert actions.CARDS_SETTLE >= 3  # the swing's ~2.8 s fits


def test_cards_still_moving_after_the_wait_are_read_anyway_and_logged(context, monkeypatch):
    # #246: a card that never stops (an animated one) costs CARDS_SETTLE, not the floor.
    monkeypatch.setattr(actions, "still", lambda context, **kw: None)
    _, lines = pack_page(context, monkeypatch, 2, "none", "weight")
    assert f"floor 2: the cards still moved after {actions.CARDS_SETTLE:g} s" in lines
    assert lines[-1] == "floor 2: pull 'Pack 0a' (-5, below the threshold)"


@pytest.mark.parametrize(("setting", "refreshes"), [("none", 0), ("once", 1), ("all", 5)])
def test_a_theme_pack_page_below_the_threshold_is_refreshed_as_the_setting_says(context, monkeypatch, setting, refreshes):
    # #41, #240: every page's best pack is below the threshold. The log gives each card's weight, the threshold and the
    # pulled card; floor 2's new packs are plain packs.
    used, lines = pack_page(context, monkeypatch, 2, setting, "prefer")
    assert used == refreshes
    assert "floor 2 packs, threshold 0: Pack 0a (-5), Pack 0b (-5)" in lines
    assert lines[-1] == f"floor 2: pull 'Pack {min(refreshes, 4)}a' (-5, below the threshold)"


def test_floor_5s_leftmost_new_pack_is_taken_when_event_packs_are_preferred(context, monkeypatch):
    # #240: a pack the data file lacks, leftmost on floor 5, is a running event's: "prefer" takes it, no refresh.
    used, lines = pack_page(context, monkeypatch, 5, "all", "prefer")
    assert used == 0
    assert lines[-2:] == ["floor 5 packs, threshold 0: Pack 0a (-5, event), Pack 0b (-5)", "floor 5: pull 'Pack 0a' (-5)"]


def test_a_search_tab_opens_without_fixed_waits(context, clock):
    clicks = context.tasker.controller.post_click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect =         lambda: np.full((720, 1280, 3), 20 * clicks.call_count, np.uint8)  # each tab shows at once
    actions.GiftSearch.open_tab(context, "Bleed")
    assert len(taps(context)) == 2
    no_fixed_wait(clock)
    assert sum(clock) < 1  # was 1.6 s of sleep


def test_a_picked_gift_is_checked_once_the_panel_shows_it(context, clock):
    page(context, {(922, 205, 270, 34): lambda clicks, looks: "Spiderweb Entangled in Red" if clicks else None})
    assert actions.GiftSearch.tap_and_check(context, np.zeros((720, 1280, 3), np.uint8), 300, 300, SPIDERWEB["name"])
    no_fixed_wait(clock)


def test_n_acquired_gift_popups_are_closed_in_one_action(context, clock):
    # #115: n gifts, n popups: the title stays up and the gift's name changes. Each next window is closed once the
    # screen is still, without a pass of MirrorHub in between.
    names = ["Wound Clerid", "Spiderweb", "Ashes to Ashes"]
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks < 3 else None,
                   GIFT_NAME: lambda clicks, looks: names[min(clicks, 2)]})
    assert actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)] * 3
    no_fixed_wait(clock)


def test_a_name_plate_read_mid_fade_out_is_not_taken_for_the_next_window(context, clock):
    # The last window fading out still shows its title, its plate half drawn ("Spiderw"): a tap then lands on the page
    # under it, the search grid, and picks a gift. The next window is tapped only once the screen is still.
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if looks < 4 else None,
                   GIFT_NAME: lambda clicks, looks: "Spiderweb" if looks < 3 else "Spiderw"})
    assert actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]


def test_the_next_gift_popup_is_tapped_once_it_has_stopped_moving(context, clock):
    # The next window slides in (looks 2-4 differ), then holds still (looks 4 and 5 match): its Confirm is tapped after that.
    screens(context, [0, 40, 80, 120, 120])
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get
    tapped_at = []
    context.tasker.controller.post_click.side_effect = lambda x, y: tapped_at.append(shots.call_count) or MagicMock()
    page(context, {GIFT_POPUP: lambda clicks, looks: "E.G.O Gift GET!" if clicks < 2 else None,
                   GIFT_NAME: lambda clicks, looks: "Wound Clerid" if clicks == 0 else "Spiderweb"})
    assert actions.GiftGet().run(context, argv())
    assert len(tapped_at) == 2 and tapped_at[1] >= 5


def test_a_gift_popup_confirm_that_did_not_take_is_left_to_the_hub(context, clock):
    # Same title, same name for the whole wait: the tap was lost; MirrorHub sees the window again.
    page(context, {GIFT_POPUP: "E.G.O Gift GET!", GIFT_NAME: "Wound Clerid"})
    assert actions.GiftGet().run(context, argv())
    assert taps(context) == [(640, 532)]


def test_a_search_tab_tap_waits_for_the_neighbour_tab_to_show_first(context, clock):
    # Live 2026-10-18 (run13): the tapped tab lights up at once but its gifts show a few looks later; the
    # Keywordless tap sent before Blunt's gifts showed was lost, or the grid read still showed Blunt's, and
    # Spiderweb was searched for on the wrong tab ("not on the page").
    tab, pending = ["Poise"], []

    def click(x, y):
        if not pending:  # a tap while a switch is still on its way does nothing
            pending.append([actions.SEARCH_TABS[(x - 113) // 62], 3])
        return MagicMock()

    def shot():
        image = np.zeros((720, 1280, 3), np.uint8)
        if pending:
            pending[0][1] -= 1
            if pending[0][1] < 0:
                tab[0] = pending.pop()[0]
            else:
                image[165:215, 85:775] = 255  # the tap's light on the tab bar, before the gifts change
        image[228:625, 85:775] = 20 * actions.SEARCH_TABS.index(tab[0])
        return image
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = shot
    actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless" and not pending  # the Keywordless gifts show when it returns


def test_a_search_tab_whose_gifts_take_two_seconds_is_waited_for_not_read_early(context, clock):
    # Live 2026-10-20 (#190): Keywordless lit at once but its grid took over 1.6 s; the 1 s wait timed out and
    # the bot read Blunt's gifts: "Spiderweb ... not on the page", and the gift went unbought.
    tab, tapped = ["Poise"], {}

    def click(x, y):
        tapped.update(tab=actions.SEARCH_TABS[(x - 113) // 62], at=actions.time.monotonic())
        return MagicMock()

    def shot():
        if tapped and actions.time.monotonic() - tapped["at"] >= (2.0 if tapped["tab"] == "Keywordless" else 0.5):
            tab[0] = tapped["tab"]
        return np.full((720, 1280, 3), 20 * actions.SEARCH_TABS.index(tab[0]), np.uint8)
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = shot
    actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless"


def test_a_search_tab_tap_that_did_nothing_is_tapped_again(context, clock):
    # #190: the grid not moving for the whole wait means the tap was lost: tap the tab once more, not read on.
    tab, own_taps = ["Poise"], []

    def click(x, y):
        name = actions.SEARCH_TABS[(x - 113) // 62]
        if name == "Keywordless":
            own_taps.append(name)
        if name != "Keywordless" or len(own_taps) > 1:  # the first Keywordless tap is lost
            tab[0] = name
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: np.full((720, 1280, 3), 20 * actions.SEARCH_TABS.index(tab[0]), np.uint8)
    actions.GiftSearch.open_tab(context, "Keywordless")
    assert tab[0] == "Keywordless" and len(own_taps) == 2


def test_a_search_tab_is_not_tapped_again_once_the_page_is_gone(context, clock, guarded):
    # #118 + #190: the second tap comes after the 5 s wait; the search page may have been left by then.
    page_until(context, "GiftSearch", 2)  # the neighbour's tap and the first Keywordless tap went out
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: np.zeros((720, 1280, 3), np.uint8)
    with pytest.raises(actions.PageGone):
        actions.GiftSearch.open_tab(context, "Keywordless")
    assert len(taps(context)) == 2


def test_a_search_tab_is_not_tapped_once_the_page_is_gone_after_the_neighbours_tap(context, guarded):
    # #118: the wait after the neighbour's tap is as long as the retry's; the wanted tab's first tap is guarded too.
    page_until(context, "GiftSearch", 1)
    with pytest.raises(actions.PageGone):
        actions.GiftSearch.open_tab(context, "Keywordless")
    assert len(taps(context)) == 1


def test_a_search_grid_is_not_dragged_once_the_page_is_gone(context, guarded):
    # #118: the drag after open_tab comes behind the tab's tap and fade; a page left meanwhile is not dragged.
    page_until(context, "GiftSearch", 0)
    with pytest.raises(actions.PageGone):
        actions.GiftSearch.scroll(context, 600)
    assert moved(context) == 0


def test_the_second_icon_candidate_is_not_tapped_once_the_page_is_gone(context, guarded, monkeypatch):
    # #118: the first candidate's tap and wait lie between the look and the second tap.
    page_until(context, "GiftSearch", 1)
    entry = next(g for g in actions.gift_data() if g["keyword"] == "Burn")
    gift = {"name": entry["en"], "keyword": "Burn", "tier": entry["tier"]}
    monkeypatch.setattr(actions.GiftSearch, "open_tab", staticmethod(lambda *a: None))
    monkeypatch.setattr(actions.GiftSearch, "scroll", staticmethod(lambda *a: None))
    monkeypatch.setattr(actions.gift_search, "gift_cells", lambda im: [(500, 300, gift["tier"]), (600, 300, gift["tier"])])
    monkeypatch.setattr(actions.GiftSearch, "icon_scores", staticmethod(lambda *a: [(0.9, 500, 300), (0.9, 600, 300)]))
    monkeypatch.setattr(actions.GiftSearch, "tap_and_check", staticmethod(lambda c, im, x, y, n: bool(c.tasker.controller.post_click(x, y)) and False))
    with pytest.raises(actions.PageGone):
        actions.GiftSearch.pick(context, gift)
    assert taps(context) == [(500, 300)]


def test_a_lookalike_pick_is_not_unselected_on_a_page_that_is_gone(context, guarded, monkeypatch):
    # #118: the tap that picked the wrong gift waited up to 1 s; the tap that undoes it is guarded.
    page_until(context, "GiftSearch", 1)
    monkeypatch.setattr(actions.GiftSearch, "chosen", staticmethod(lambda c, im, names: ["Other"] if c.tasker.controller.post_click.called else []))
    with pytest.raises(actions.PageGone):
        actions.GiftSearch.tap_and_check(context, np.zeros((720, 1280, 3), np.uint8), 500, 300, "Wanted")
    assert taps(context) == [(500, 300)]


def test_the_consume_dialog_is_confirmed_once_it_stops_dropping_in(context, clock):
    # Live 2026-10-18 (run13c): Confirm was tapped as soon as "Consume" read, while the dialog still slid down
    # on its chains; the tap did nothing, no GET window came, and every GiftSearch call after it did the same.
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get
    clicks, state = context.tasker.controller.post_click, {"select": None, "bought": False}

    def click(x, y):
        if (x, y) == actions.SEARCH_SELECT:
            state["select"] = shots.call_count
        elif (x, y) == actions.SEARCH_DIALOG_BUTTONS["confirm"] and shots.call_count >= state["select"] + 4:
            state["bought"] = True  # the dialog has stopped: the tap takes
        return MagicMock()

    def shot():
        moving = state["select"] is not None and shots.call_count < state["select"] + 4
        return np.full((720, 1280, 3), 40 * (shots.call_count % 5) if moving else 0, np.uint8)
    search_page(context, {tuple(actions.SEARCH_DIALOG): lambda c, l: "Consume 70 Starlight to search and obtain these E.G.O Gifts?"
                            if state["select"] is not None and not state["bought"] else None,
                          GIFT_POPUP: lambda c, l: "E.G.O Gift GET!" if state["bought"] else None})
    clicks.side_effect = click
    shots.side_effect = shot
    assert actions.GiftSearch().run(context, argv())
    assert state["bought"]


def check_page(context, odds=()):
    """The skill-check page: `Choose a character`, and the odds caption (x -> text) over each portrait."""
    texts = {tuple(actions.CHECK_PROMPT): [("Choose a character", (860, 300, 200, 30))]}
    for x, t in odds:
        texts[(x - 38, 605, 76, 24)] = [(t, (x - 30, 608, 60, 20))]
    reads(context, texts)


def event_portrait_taps(context):
    return [c.args[0] for c in context.tasker.controller.post_click.call_args_list if c.args[1] == actions.EVENT_PORTRAIT_Y]


def test_a_check_with_no_odds_read_tries_the_next_sinner_when_a_tap_did_nothing(context):
    # #92: with no odds read it was always the first sinner; when she cannot be picked it never ended.
    check_page(context)
    for _ in range(3):
        actions.Event().run(context, None)  # the screen never changes: each tap did nothing
    assert event_portrait_taps(context) == actions.EVENT_PORTRAIT_X[:3]


def test_a_check_with_odds_read_takes_the_next_best_when_a_tap_did_nothing(context):
    check_page(context, [(actions.EVENT_PORTRAIT_X[0], "Low"), (actions.EVENT_PORTRAIT_X[2], "Very High"), (actions.EVENT_PORTRAIT_X[4], "High")])
    for _ in range(3):
        actions.Event().run(context, None)
    assert event_portrait_taps(context) == [actions.EVENT_PORTRAIT_X[i] for i in (2, 4, 0)]


def test_a_check_tap_that_took_is_not_held_against_the_sinner(context):
    check_page(context)
    screens(context, [0, 9])  # the first tap changes the screen
    actions.Event().run(context, None)
    actions.Event().run(context, None)
    assert event_portrait_taps(context) == [actions.EVENT_PORTRAIT_X[0]] * 2


def event_for(context, seconds):
    """Run Event once a second on a page it cannot read, for `seconds` or until it hands over to recovery."""
    for _ in range(seconds):
        actions.Event().run(context, None)
        if actions.STUCK["flag"]:
            return
        actions.time.sleep(1)


def test_one_event_that_goes_on_past_its_limit_goes_to_recovery(context):
    event_for(context, actions.EVENT_LIMIT + 60)
    flag = actions.STUCK["flag"]
    assert flag and flag[1] == 1 and "event" in flag[2]
    assert actions.RUN.get("event") is None  # recovery's next look starts a new clock


def test_an_event_after_a_pause_starts_its_own_clock(context):
    # Each event alone stays under the limit (a call taps the text for up to 0.3 s on top of event_for's 1 s);
    # together they would not.
    event_for(context, actions.EVENT_LIMIT // 2 + 30)
    actions.time.sleep(actions.EVENT_LIMIT)  # the event ended; the next one comes later
    event_for(context, actions.EVENT_LIMIT // 2 + 30)
    assert actions.STUCK["flag"] is None


GEAR = (272, 557)  # the left gear of a 7-slot panel (battle.guard_chain)
DISC = (918, 557)  # its START disc
WIN_RATE_XY = (1004, 545)


class Choices:
    """An event's choice page: option cards 130 px tall, 18 apart from y 170, in the list's view y 165-512;
    more than fit show a scrollbar and scroll() moves them. options are (text, hint); OCR reads a line only
    where it shows whole. tapped: the option each tap hit, None when its card was not whole in view.
    The card a drag lifts over lights up (live #196): an orange glow under its bottom edge, 13 px in all."""

    def __init__(self, context, monkeypatch, options, story=(), offset=0, scrollbar=True):
        self.options, self.story, self.offset, self.drags, self.tapped = options, story, offset, [], []
        self.lit = None  # y the last drag lifted at
        self.end = max(0, 170 + 148 * len(options) - 18 - 508)
        self.scrollbar = scrollbar and self.end > 0
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        context.run_recognition.side_effect = self.read
        monkeypatch.setattr(actions, "scroll", self.scroll)

    def scroll(self, context, x, y, dx, dy):
        assert 690 < x < 1165 and 165 < y < 512 and 165 < y + dy < 512  # on the list
        self.drags.append(dy)
        self.offset = min(max(self.offset - dy, 0), self.end)
        self.lit = y + dy

    def tops(self):
        return [170 + 148 * k - self.offset for k in range(len(self.options))]

    def click(self, x, y):
        if 690 < x < 1165:
            whole = [k for k, t in enumerate(self.tops()) if 165 <= t and t + 130 <= 512 and t < y < t + 130]
            self.tapped.append(self.options[whole[0]][0] if whole else None)
        return DEFAULT

    def render(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        for t in self.tops():
            image[max(t, 165):max(min(t + 130, 512), 165), 700:1160] = (20, 30, 60)  # red-brown: open
            glow = 10 if self.lit is not None and t < self.lit < t + 130 else 0
            for y in [*range(t, t + 9), *range(t + 127, t + 130 + glow)]:  # top edge double, bottom edge single
                if 165 <= y < 512:
                    image[y, 690:1165] = 200
        if self.scrollbar:
            image[170:505, 1203:1213] = (26, 41, 60)
        return image

    def read(self, name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = []
        if roi == tuple(actions.CHOICES_HEADER):
            lines = [("Choices", (700, 110, 100, 30))]
        elif roi == tuple(actions.EVENT_STORY):
            lines = [(t, (80, 340 + 30 * i, 400, 20)) for i, t in enumerate(self.story)]
        elif roi == tuple(actions.CHOICE_ROWS):
            for t, (text, hint) in zip(self.tops(), self.options):
                lines += [(s, (733, y, 300, 20)) for s, y in ((text, t + 30), (hint, t + 60)) if s and 165 <= y and y + 20 <= 512]
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None


DOLL = ["In this cramped room, you find a wooden doll, standing.", "Are the talismans filling the room for a wish?",
        "Does this wooden doll wish for anything?"]  # 901013's story, as the box ends it


def test_an_event_in_the_table_takes_a_direct_gift_over_a_check_for_the_main_keyword(context, monkeypatch):
    # 901013 for a Poise team: the hint rules took the check that may give Poise; the table ranks the sure gift first.
    actions.RUN["team"] = {"keyword": "Poise"}
    actions.RUN["settings"] = {"event_overrides": []}
    page = Choices(context, monkeypatch, [
        ("Remove the doll's talismans.", "Select to gain a Rupture E.G.O Gift"),
        ("Remove the wall talismans.", "Sloth & Wrath Advantage check. Then, maybe gain a Poise E.G.O Gift depending on the subsequent choice")],
        DOLL)
    actions.Event().run(context, None)
    assert page.tapped == ["Remove the doll's talismans."]
    assert page.drags == []  # two options fit: no scrolling


SCROLLED = [(f"Option {k}.", "") for k in range(5)]
TABLE = [{"key": "doesthiswoodendollwishforanything",
          "options": [{"text": t, "hint": h, "kind": "other"} for t, h in SCROLLED]}]


@pytest.mark.parametrize("best", [0, 2, 4])
def test_a_list_that_scrolls_is_read_whole_and_the_pick_scrolled_into_view(context, monkeypatch, best):
    # #93: more options than fit: read top to bottom anchored on their texts, the pick tapped whole in view.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = list(SCROLLED)
    options[best] = (f"Option {best}.", "Select to gain a Burn E.G.O Gift")
    table = [{"key": TABLE[0]["key"], "options": [{"text": t, "hint": h, "kind": "direct" if h else "other",
                                                   "gifts": [["Burn", "direct"]] if h else []} for t, h in options]}]
    monkeypatch.setattr(actions, "event_table", lambda: table)
    page = Choices(context, monkeypatch, options, DOLL, offset=100)  # left part way down
    actions.Event().run(context, None)
    assert page.tapped == [f"Option {best}."]


def test_the_card_a_drag_lights_is_read_and_taken(context, monkeypatch):
    # #196: four options, three in view. The drags light East on every screen it shows whole on; it was never read.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = [("North.", ""), ("East.", "Select to gain a Burn E.G.O Gift"), ("West.", ""), ("Turn back.", "")]
    page = Choices(context, monkeypatch, options, ["Unknown story."])
    actions.Event().run(context, None)
    assert page.tapped == ["East."]


def test_into_view_drags_on_past_options_it_did_not_read(context, monkeypatch):
    # #196: the one card whole on screen is an option the read missed; it dragged no further and gave up.
    page = Choices(context, monkeypatch, [(f"Option {k}.", "") for k in range(4)], offset=70)  # only Option 1 whole
    options = [(f"Option {k}.", True, 0) for k in (0, 2, 3)]
    y, _ = actions.Event.into_view(context, page.render(), options, 0)
    assert y is not None and page.tops()[0] < y < page.tops()[0] + 130


def test_into_view_gives_up_at_the_end_the_pick_lies_beyond(context, monkeypatch):
    # The options on screen put the pick above them: the top of the list ends the search, no turn back down.
    page = Choices(context, monkeypatch, [(f"Option {k}.", "") for k in range(4)], offset=236)  # at the bottom
    options = [("Gone.", True, 0)] + [(f"Option {k}.", True, 0) for k in range(4)]
    y, _ = actions.Event.into_view(context, page.render(), options, 0)
    assert y is None and page.drags == [150, 150, 150]  # two to the top, one that does not move


def test_an_option_cut_off_with_no_scrollbar_still_scrolls(context, monkeypatch):
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = [("Option 0.", ""), ("Option 1.", ""), ("Option 2.", "Select to gain a Burn E.G.O Gift")]
    page = Choices(context, monkeypatch, options, ["Unknown story."], scrollbar=False)
    actions.Event().run(context, None)
    assert page.tapped == ["Option 2."]  # the hint rules, on the option read once scrolled


class Panel:
    """A battle's skill panel (7 slots, Win Rate label at x 984): a portrait tap swaps the slot's lower skill
    and its guard skill. A drag from the left gear links the chain, all but drops[k] slots on the k-th drag
    (live #145: under load the finger crosses a slot between two frames and the chain ends there); a drag
    from the gear or a tap on it while a chain is linked clears it. The disc lights once anything is linked,
    the START plaque shows (and START starts the turn) only once every slot is. units[i] is the unit in
    slot i (slots reorder by speed every turn); guard[u] whether unit u shows its guard skill. The plaque swings
    in plaque_after s after the chain is complete (live 2026-10-18, 30 fps recording: upright 0.33-0.47 s after
    the panel levels, ~0.5-0.65 s after the lift; a minimised emulator held it mid-swing for over 2 s)."""

    def __init__(self, context, guard, drops=(), lost_start=0, plaque_after=0.6):
        self.xs = actions.battle.slot_xs(984)
        self.units, self.guard, self.dealt = list(range(7)), list(guard), 0
        self.linked, self.win_rate, self.started, self.at, self.lifted = 0, False, False, None, -1.0
        self.drops, self.lost_start, self.plaque_after, self.complete_at = list(drops), lost_start, plaque_after, None
        self.drags = []  # how long each chain drag took, s
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        ctl.post_touch_down.side_effect = self.down
        ctl.post_touch_up.side_effect = self.lift
        context.run_recognition.side_effect = self.recognise

    def down(self, x, y, *a):
        self.at, self.t0 = (x, y), actions.time.monotonic()
        return DEFAULT

    def lift(self, *a):
        self.lifted = actions.time.monotonic()
        if self.at == GEAR:
            if self.linked:
                self.linked = 0
            else:
                self.linked = 7 - (self.drops.pop(0) if self.drops else 0)
                self.complete_at = self.lifted if self.linked == 7 else None
                self.drags.append(actions.time.monotonic() - self.t0)
        return DEFAULT

    def click(self, x, y):
        if y == actions.SLOT_PORTRAIT_Y:
            u = self.units[min(range(7), key=lambda i: abs(self.xs[i] - x))]
            self.guard[u] = not self.guard[u]
        elif (x, y) == GEAR:
            self.linked = 0
            self.win_rate = False
        elif (x, y) == WIN_RATE_XY:
            self.win_rate = not self.win_rate
            self.linked = 7 if self.win_rate else 0
            self.complete_at = actions.time.monotonic() if self.win_rate else None
        elif (x, y) == DISC and self.linked == 7 and actions.time.monotonic() - self.lifted >= 0.15:
            # live #145: a press while the panel still tilts back from a drag misses the disc
            if self.lost_start:
                self.lost_start -= 1
            else:
                self.started = True
        return DEFAULT

    def recognise(self, name, image, override=None):
        node = (override or {}).get(name, {})
        plaque = self.linked == 7 and actions.time.monotonic() - self.complete_at >= self.plaque_after
        hit = {"BattlePause": self.started, "BattleStart": plaque,
               "BattleTurn": not self.started and actions.time.monotonic() - self.lifted >= 0.15  # live: the panel
               and (self.win_rate or "Pressed" not in node.get("template", ""))}  # tilts back 0.15 s, the label gone
        return SimpleNamespace(hit=True, box=[984, 531, 40, 20]) if hit.get(name) else None

    def next_turn(self, order=None):
        self.linked, self.started, self.win_rate, self.dealt = 0, False, False, self.dealt + 1
        self.units = order or self.units

    def render(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        for i, u in enumerate(self.units):
            x, y = actions.lower_x(self.xs[i]), actions.LOWER_Y
            if self.guard[u]:  # a flat brown icon, its own shape per unit
                image[y - 20:y + 20, x - 20:x + 20] = (50, 100, 150)
                image[y - 15 + u:y - 5 + u, x - 12:x + 2 * u] = (20, 40, 60)
            else:  # line art: a new skill is dealt each turn
                rng = np.random.default_rng(100 * u + self.dealt)
                image[y - 20:y + 20, x - 20:x + 20] = rng.integers(0, 255, (40, 40, 3))
        if self.linked:
            image[547:567, 908:928] = 255  # the START disc at (918, 557)
        return image


def portrait_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args[1] == actions.SLOT_PORTRAIT_Y]


def guard_turn(context, guard_left=3):
    actions.RUN["guard"] = guard_left
    return actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))


def test_a_first_guard_turn_taps_each_portrait_once_when_every_slot_shows_its_skill(context):
    panel = Panel(context, guard=[False] * 7)
    assert actions.PlayTurn.guard(context, 984, DISC)
    assert panel.started and all(panel.guard)
    assert len(portrait_taps(context)) == 7
    assert [c.args for c in context.tasker.controller.post_click.call_args_list].count(DISC) == 1


def test_slots_already_on_guard_are_swapped_off_and_tapped_back(context):
    # Live (2026-10-18): the swap can stay from the last turn; the first taps then take those slots off guard.
    panel = Panel(context, guard=[True, False, True, False, False, False, True])
    assert actions.PlayTurn.guard(context, 984, DISC)
    assert panel.started and all(panel.guard)
    assert len(portrait_taps(context)) == 7 + 3


def test_a_chain_that_misses_its_tail_is_cleared_and_dragged_again_slower_before_the_turn_starts(context):
    # #145 (live 2026-10-18): the chain ended two slots short, the disc lit anyway and START did nothing.
    panel = Panel(context, guard=[False] * 7, drops=[2])
    guard_turn(context)
    assert panel.started and panel.linked == 7 and not panel.win_rate
    assert len(panel.drags) == 2 and panel.drags[1] > panel.drags[0]
    assert actions.RUN["guard"] == 2


def test_a_chain_that_never_links_falls_back_to_win_rate_and_keeps_the_guard_turn(context):
    # Every drag misses (a heavily loaded PC): the chain is cleared so Win Rate picks every slot; the turn does
    # not count as a guard turn.
    panel = Panel(context, guard=[False] * 7, drops=[1, 1, 1])
    guard_turn(context)
    assert panel.started and panel.win_rate
    assert len(panel.drags) == 3
    assert actions.RUN["guard"] == 3


def test_start_is_pressed_again_within_the_call_when_the_first_press_is_lost(context):
    # #145: a START that did not take went back to MirrorHub: 3 more looks, a stuck and recovery, ~23 s a time.
    panel = Panel(context, guard=[False] * 7, lost_start=1)
    guard_turn(context)
    assert panel.started
    assert actions.RUN["guard"] == 2
    assert actions.STUCK["flag"] is None


def test_a_plaque_still_swinging_in_is_waited_for_before_the_chain_is_dragged_again(context):
    # PR #148 follow-up: a minimised emulator held the plaque mid-swing for over 2 s; one look after START did not
    # take read "no plaque", cleared a complete chain and dragged it again. The plaque is waited for instead.
    panel = Panel(context, guard=[False] * 7, lost_start=1, plaque_after=2.5)
    guard_turn(context)
    assert panel.started and len(panel.drags) == 1
    assert actions.RUN["guard"] == 2


def test_a_win_rate_turn_presses_start_at_once_and_counts_no_guard_turn(context):
    panel = Panel(context, guard=[False] * 7)
    guard_turn(context, guard_left=0)
    assert panel.started and panel.win_rate
    assert len(portrait_taps(context)) == 0 and actions.RUN["guard"] == 0


def test_a_guard_turn_on_a_hollow_gear_plays_win_rate_and_keeps_its_guard_turn(context):
    # #127 (live 2026-10-18): in a focused encounter the left gear is a hollow ring and no chain starts from it;
    # each skill has to be dragged onto an enemy's skill slot, which moves with the camera.
    panel = Panel(context, guard=[False] * 7)
    data = (Path(__file__).resolve().parent / "gears" / "hollow_boss.png").read_bytes()  # tests/test_battle.py gear()
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(80, 1 + 80 * 3)
    ring = rows[:, 1:].reshape(80, 80, 3)[:, :, ::-1]

    def render():
        image = panel.render()
        image[536:616, 236:316] = ring  # round the left gear of 7 slots, (276, 576)
        return image
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = render
    actions.RUN["guard"] = 3
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert not portrait_taps(context)
    assert [c.args for c in context.tasker.controller.post_touch_down.call_args_list] == [actions.HOLD_SPOT]  # no drag
    assert win_rate_taps(context)
    assert actions.RUN["guard"] == 3


def gesture(context, clock):
    """Record the touch events with the fake clock's time: [(kind, (x, y), t)]."""
    events = []
    ctl = context.tasker.controller
    for kind in ("down", "move", "up"):
        def record(*a, kind=kind):
            events.append((kind, a[:2], sum(clock)))
            return DEFAULT
        getattr(ctl, f"post_touch_{kind}").side_effect = record
    return events


def test_a_scroll_stops_dead_where_it_was_sent(context, clock):
    # #114 (live 2026-10-18): the game eats the first move (its drag threshold) and flings the content on with
    # what speed the finger still had at the lift, decaying while the finger rests: 0.55 s still after 20 px moves
    # 10 ms apart left at most 1 px over 126 drags; resting after the threshold move keeps the next one whole.
    events = gesture(context, clock)
    actions.scroll(context, 430, 590, 0, -300)
    moves = [(xy, t) for kind, xy, t in events if kind == "move"]
    assert moves[0][0] == (430, 580)  # 10 px: what the threshold eats
    assert moves[-1][0] == (430, 280)  # then the 300 px asked for
    assert moves[1][1] - moves[0][1] >= 0.05
    assert events[-1][0] == "up" and events[-1][2] - moves[-1][1] >= 0.55
    assert events[-1][2] - events[0][2] < 0.9  # live: 0.77 s for 300 px, 1.25 s before


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


def test_a_forfeited_run_gives_up_its_rewards_and_the_same_team_runs_next(context, monkeypatch, tmp_path):
    # #95: after_retries "forfeit" ends the run at Exploration Reward short of floor 5; the rotation
    # cursor does not move on, so the team that lost runs the next run again.
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    teams = [{"id": "a", "name": "A", "enabled": True}, {"id": "b", "name": "B", "enabled": True}]
    actions.RUN.update(settings={"run": {}, "teams": teams}, team=teams[0], planned=True, difficulty="hard")
    taps = []

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.RESULT:
            return [("Floor 3 [HARD] 2/6", (300, 420, 90, 20))]
        if roi == actions.DIALOG_TEXT and taps:
            return [("End expedition without claiming rewards?", (400, 300, 400, 30))]
        return []
    monkeypatch.setattr(actions, "ocr", ocr)
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))

    actions.Settle().run(context, None)
    assert taps == [actions.GIVE_UP, actions.DIALOG_CONFIRM]
    assert not (tmp_path / "state").exists()  # no cursor written
    line = json.loads((tmp_path / "logs" / "runs.jsonl").read_text(encoding="utf-8"))
    assert line["result"] == "giveup" and line["team"] == "a"


# #118: an action checks its page before each tap and hands a changed screen back to MirrorHub.
@pytest.fixture
def guarded(monkeypatch):
    monkeypatch.setattr(actions, "page_guard", REAL_GUARD)


def page_until(context, node, clicks):
    """MirrorHub's node for the page hits until `clicks` taps went out, then the page is gone (left by hand)."""
    inner = context.run_recognition.side_effect

    def run_recognition(name, image, override=None):
        if name == node and override is None:
            return SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if context.tasker.controller.post_click.call_count < clicks else None
        return inner(name, image, override) if inner else None
    context.run_recognition.side_effect = run_recognition


def test_the_guard_passes_the_page_and_waits_out_a_moment_without_its_anchor(context, clock, guarded):
    shown = iter([None, None, True])
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True) if name == "Shop" and next(shown, True) else None
    assert actions.page_guard(context, "Shop") is not None
    assert sum(clock) < 1


def test_the_guard_gives_the_page_up_after_a_second(context, clock, guarded):
    with pytest.raises(actions.PageGone):
        actions.page_guard(context, "Shop")
    assert 1 <= sum(clock) < 1.5


def test_the_guard_takes_a_fresh_screenshot_showing_the_page_without_another(context, guarded):
    page_until(context, "Event", 1)
    image = np.zeros((720, 1280, 3), np.uint8)
    assert actions.page_guard(context, "Event", image=image) is image
    assert context.tasker.controller.post_screencap.call_count == 0


def test_event_text_taps_stop_once_the_event_is_gone(context, guarded):
    # The text tapped on at a dead corner (up to 30 taps); the event page went away after the first. The page is
    # looked at with its text, every EVENT_READ_EVERY taps (#174: one OCR a tap undid the 0.15 s): the taps in
    # between land on the dead corner, which takes none.
    reads(context, {tuple(actions.EVENT_BUTTON_LABEL): [("Continue", (1065, 625, 140, 40))]})
    page_until(context, "Event", 1)
    assert actions.Event().run(context, None)
    assert len(taps(context)) == actions.EVENT_READ_EVERY
    assert actions.STUCK["flag"] is None


def test_a_fusion_taps_no_cell_once_the_shop_is_gone(context, guarded):
    # Live 2026-10-18: the shop left by hand mid-visit; its taps went on onto the map for ~50 s.
    reads(context, FUSE_PAGE)
    owned_gifts(context, actions.FUSE_CELLS[10:12])
    page_until(context, "Shop", 4)  # gone after Fuse, the centre, Burn and its OK
    with pytest.raises(actions.PageGone):
        actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, {})
    assert not set(taps(context)) & set(actions.FUSE_CELLS)


def test_a_shop_visit_left_by_hand_is_handed_back_and_forgotten_at_the_next_node(context, guarded, monkeypatch):
    actions.RUN["team"] = {"heal": "none", "keyword": "Burn", "reserve_cost": 0}
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    monkeypatch.setattr(actions.Shop, "sell", staticmethod(lambda *a: False))
    monkeypatch.setattr(actions.Shop, "buy", staticmethod(lambda *a: actions.page_guard(context, "Shop")))
    assert actions.Shop().run(context, argv())  # the shop is gone: True for MirrorHub, not a stuck
    assert actions.STUCK["flag"] is None and "shop" in actions.RUN
    assert actions.RUN["after_shop"]  # #279: the page handled last, so RouteMap's one node is the boss
    actions.enter_node(context)
    assert "shop" not in actions.RUN and "after_shop" not in actions.RUN


def test_a_formation_left_mid_pick_taps_no_card(context, guarded):
    with pytest.raises(actions.PageGone):
        actions.Formation.pick(context, ["Yi Sang"])
    assert taps(context) == []


def test_a_team_list_gone_is_handed_back_not_stopped_on(context, guarded, monkeypatch):
    actions.RUN["team"] = {"game_team": 3}
    monkeypatch.setattr(actions, "stop", lambda *a, **k: pytest.fail("stopped"))
    team_picker(context, "TEAMS #1", lambda clicks, looks: None)
    assert actions.SelectTeam().run(context, argv())
    assert taps(context) == []


def test_a_battle_gone_before_win_rate_is_handed_back(context, guarded):
    assert actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert taps(context) == []
    assert actions.STUCK["flag"] is None


def test_a_feature_match_hit_comes_back_in_screen_coordinates():
    # #156: the node runs on a cut-out around its roi; its box is put back where it is on the screen.
    ctx, calls = MagicMock(), []

    def recognise(node, image, override):
        calls.append((image.shape, override[node]["roi"]))
        return SimpleNamespace(hit=True, box=Rect(10, 20, 30, 40))
    ctx.run_recognition.side_effect = recognise
    hit = actions.seen(ctx, np.zeros((720, 1280, 3), np.uint8), "MapNodeEvent", [500, 300, 120, 120])
    (h, w, _), roi = calls[0]
    assert w < 1280 and h < 720 and roi[2:] == [120, 120]  # a cut-out, the roi's size kept
    dx, dy = 500 - roi[0], 300 - roi[1]
    assert dx % actions.FEATURE_ALIGN == 0 and dy % actions.FEATURE_ALIGN == 0
    assert tuple(hit.box) == (10 + dx, 20 + dy, 30, 40)


def test_feature_match_lists_every_feature_match_node_of_the_pipeline():
    from test_pipeline import load_nodes, recognition
    assert actions.FEATURE_MATCH == {n for n, spec in load_nodes().items() if recognition(spec)[0] == "FeatureMatch"}


def test_forfeit_reads_its_dialogs_however_ocr_cases_them(context, monkeypatch):
    # #138: the settings panel and the Quit dialog read in capitals still count as shown.
    reads = iter(["DUNGEON PROGRESS", "QUIT EXPLORING THE DUNGEON?", ""])
    monkeypatch.setattr(actions, "text", lambda *a, **k: next(reads))
    monkeypatch.setattr(actions, "tap", lambda *a, **k: None)
    actions.RUN["forfeit"] = True
    assert actions.forfeit(context) is True
    assert actions.STUCK["flag"] is None and "forfeit" not in actions.RUN


def test_the_theme_pack_page_reads_its_floor_in_any_case(context, monkeypatch):
    # #138: "Floor 3" is floor 3, as the page-gone wait after the pull already reads it.
    monkeypatch.setattr(actions, "text", lambda *a, **k: "Floor 3")
    monkeypatch.setattr(actions.PickThemePack, "set_difficulty", lambda *a: False)
    actions.RUN["difficulty"] = None
    actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == 3


def test_a_new_floor_forgets_the_shop_left_before_the_boss(context, monkeypatch):
    # #279: the boss' floor ends with the boss; the next floor's first map is read by its marks again.
    monkeypatch.setattr(actions, "text", lambda *a, **k: "Floor 3")
    monkeypatch.setattr(actions.PickThemePack, "set_difficulty", lambda *a: False)
    actions.RUN.update(difficulty=None, floor=2, after_shop=True)
    actions.PickThemePack().run(context, None)
    assert actions.RUN["floor"] == 3 and "after_shop" not in actions.RUN


def moved(context):
    """Taps, drags and swipes sent to the device."""
    ctl = context.tasker.controller
    return ctl.post_click.call_count + ctl.post_touch_down.call_count + ctl.post_swipe.call_count


def test_a_global_popup_over_the_page_hands_it_back(context, guarded):
    # A popup reads through to the page under it (maatools: the title's nodes hit under RetryCountdown.png);
    # MirrorHub answers the popup before any page, so the guard does too.
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name in ("Shop", "RetryPopup") else None
    with pytest.raises(actions.PageGone):
        actions.page_guard(context, "Shop")


@pytest.mark.parametrize("action, team", [
    (actions.PickStartingGift, {"keyword": "Burn", "gift_search": {"enabled": False, "gifts": []}}),
    (actions.GiftSearch, {"gift_search": {"enabled": True, "gifts": [{"name": "Phlebotomy Pack"}]}}),
])
def test_a_gift_page_gone_is_handed_back_untouched(context, guarded, action, team):
    actions.RUN["team"] = team
    assert action().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_a_theme_pack_page_gone_is_handed_back_untouched(context, guarded, monkeypatch):
    monkeypatch.setattr(actions, "text", lambda *a, **k: "FLOOR 1")
    actions.RUN["difficulty"] = None
    assert actions.PickThemePack().run(context, None)
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def starlight(monkeypatch, available):
    """A starlight page planning graces 1 and 2 at base (10 each), Available reading available in turn, nothing owned."""
    actions.RUN["settings"] = {"run": {"starlight_unaffordable": "stop"}}
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: {"priority": [1, 2], "levels": ["base", "base"] + ["none"] * 8})
    reads = iter(available)
    monkeypatch.setattr(actions, "read_available", lambda context, image: next(reads))
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: pytest.fail(reason))


def test_a_starlight_page_gone_is_handed_back_untouched(context, guarded, monkeypatch):
    starlight(monkeypatch, [20])
    assert actions.BuyStarlight().run(context, argv())
    assert moved(context) == 0


def test_a_starlight_page_handed_back_after_one_grace_still_buys_the_next(context, monkeypatch):
    # #118: back from MirrorHub with grace 1 bought: Available reads 10, grace 1 already selected.
    starlight(monkeypatch, [10, 0])
    monkeypatch.setattr(actions, "grace_selected", lambda image, n: n == 1)
    monkeypatch.setattr(actions.BuyStarlight, "set_level", staticmethod(lambda *a: True))
    assert actions.BuyStarlight().run(context, argv())
    x, y = actions.grace_box(2)
    assert (x + 92, y + 100) in taps(context)


def test_a_gift_choice_gone_is_handed_back_untouched(context, guarded):
    actions.RUN["team"] = {"keyword": "Burn", "trial_risk_weight": "medium"}
    actions.RUN["settings"] = {"trial_risk_overrides": []}
    reads(context, {tuple(actions.GIFT_CARDS): [("Acquire E.G.O Gift", (300, 160, 150, 30)), ("Hellterfly's Dream", (200, 250, 150, 30))]})
    assert actions.PickGift().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_a_map_gone_while_looking_for_its_bus_is_not_dragged(context, guarded):
    actions.RUN["difficulty"] = "normal"
    assert actions.RouteMap().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_an_exploration_reward_gone_is_handed_back_untouched(context, guarded, monkeypatch):
    actions.RUN.update(settings={"run": {"weekly_bonus_use": "none", "weekly_bonus_amount": 0}}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setattr(actions.settlement, "read_result", lambda text: (5, False, 5, 5))
    assert actions.Settle().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_an_event_gone_is_not_scrolled(context, guarded):
    with pytest.raises(actions.PageGone):
        actions.Event.drag(context, np.zeros((720, 1280, 3), np.uint8), actions.CHOICE_STEP)
    assert moved(context) == 0


def test_a_shop_gone_before_leave_is_handed_back_not_stuck(context, guarded, monkeypatch):
    actions.RUN["team"] = {"heal": "none", "keyword": "Burn", "reserve_cost": 0}
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    for step in ("sell", "buy", "fuse"):
        monkeypatch.setattr(actions.Shop, step, staticmethod(lambda *a: False))
    assert actions.Shop().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_a_battle_handed_back_again_and_again_is_no_unchanged_turn(context, guarded):
    # Each hand-back is no submit: the turn count is for turns that START did not move on.
    for _ in range(5):
        assert actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert actions.STUCK["flag"] is None


def test_reward_cards_gone_after_one_card_are_handed_back(context, guarded):
    # A title check alone reads through a popup: the guard takes the page, and the page goes after a card.
    actions.RUN["team"] = {"reward_cards": ["Starlight"]}
    reads(context, {tuple(actions.REWARD_TITLE): [("Encounter Reward", (300, 120, 200, 30))],
                    tuple(actions.SELECTABLE): [("Selectable 0/1", (890, 120, 150, 30))],
                    tuple(actions.CARD_TEXT): [("Gain 8~10 Starlight", (200, 360, 200, 30)), ("Gain 100 Cost", (600, 360, 200, 30))]})
    page_until(context, "RewardCard", 1)
    assert actions.RewardCard().run(context, argv())
    assert len(taps(context)) == 1 and actions.CARD_CONFIRM not in taps(context)
    assert actions.STUCK["flag"] is None


@pytest.mark.parametrize("step, visit", [("sell", {"wanted": 100, "sold": False}), ("fuse", {})])
def test_a_shop_gone_before_the_sell_or_fuse_button_taps_nothing(context, guarded, step, visit):
    with pytest.raises(actions.PageGone):
        getattr(actions.Shop, step)(context, {"keyword": "Burn", "heal": "none", "reserve_cost": 0, "gift_search": {"gifts": []}}, visit)
    assert moved(context) == 0


def test_a_heal_handed_back_mid_way_is_not_paid_again(context, monkeypatch):
    actions.RUN["team"] = {"heal": "full", "keyword": "Burn", "reserve_cost": 0}
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))

    def heal(context, team):
        raise actions.PageGone("Shop")  # the heal page left by hand, or a popup over it
    monkeypatch.setattr(actions.Shop, "heal", staticmethod(heal))
    assert actions.Shop().run(context, argv())
    assert actions.RUN["shop"]["healed"]


def test_a_starlight_page_gone_after_a_grace_tap_is_handed_back_not_stopped(context, guarded, monkeypatch):
    starlight(monkeypatch, [20, None])
    monkeypatch.setattr(actions.BuyStarlight, "set_level", staticmethod(lambda *a: True))
    page_until(context, "StarlightPage", 1)
    assert actions.BuyStarlight().run(context, argv())
    assert len(taps(context)) == 1


def test_a_gift_choice_gone_after_one_card_does_not_press_select(context, guarded):
    actions.RUN["team"] = {"keyword": "Burn", "trial_risk_weight": "medium"}
    actions.RUN["settings"] = {"trial_risk_overrides": []}
    reads(context, {tuple(actions.GIFT_CARDS): [("Acquire E.G.O Gift", (300, 160, 150, 30)), ("Hellterfly's Dream", (200, 250, 150, 30)),
                                                ("Acquire E.G.O Gift", (700, 160, 150, 30)), ("Ashes to Ashes", (600, 250, 150, 30))]})
    page_until(context, "GiftChoice", 1)
    assert actions.PickGift().run(context, argv())
    assert len(taps(context)) == 1 and actions.GIFT_SELECT not in taps(context)


def test_a_formation_gone_after_the_first_card_taps_no_more(context, guarded, monkeypatch):
    ctl = context.tasker.controller
    monkeypatch.setattr(actions, "participants", lambda context, image: (max(0, ctl.post_click.call_count - 1), 5))
    page_until(context, "Formation", 2)  # Clear Selection, then Yi Sang
    with pytest.raises(actions.PageGone):
        actions.Formation.pick(context, ["Yi Sang", "Hong Lu"])
    assert taps(context) == [actions.CLEAR_SELECTION, actions.card_xy(actions.battle.SINNERS.index("Yi Sang"), actions.CARD_TAP_Y)]


def test_a_battle_gone_after_the_portrait_taps_swaps_nothing_back(context, guarded):
    panel = Panel(context, guard=[True, False, True, False, False, False, True])  # 3 slots go off guard and want a tap back
    page_until(context, "BattleTurn", 7)  # gone right after the first round of portrait taps
    with pytest.raises(actions.PageGone):
        actions.PlayTurn.guard(context, 984, DISC)
    assert len(portrait_taps(context)) == 7 and DISC not in taps(context)
    assert context.tasker.controller.post_touch_down.call_count == 0 and not panel.started


def test_an_exploration_reward_gone_after_a_toggle_tap_does_not_claim(context, guarded, monkeypatch):
    actions.RUN.update(settings={"run": {"weekly_bonus_use": "all", "weekly_bonus_amount": 3}}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setattr(actions.settlement, "read_result", lambda text: (5, False, 5, 5))
    monkeypatch.setattr(actions.settlement, "bonus_toggles", lambda *a: 1)
    monkeypatch.setattr(actions, "toggles", lambda context, image: [False, False, False])
    page_until(context, "ExplorationReward", 1)
    assert actions.Settle().run(context, argv())
    assert taps(context) == [(actions.TOGGLE_X[0], 252)]


def test_a_gift_search_gone_after_a_pick_does_not_press_select(context, guarded, monkeypatch):
    gift = {"name": "Phlebotomy Pack", "keyword": "Bleed", "tier": 1}
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [gift]}}
    monkeypatch.setattr(actions.gift_search, "select_count", lambda text: (0, 1))
    monkeypatch.setattr(actions.GiftSearch, "chosen", staticmethod(lambda *a: ["Phlebotomy Pack"]))
    picks = iter([gift])
    monkeypatch.setattr(actions.gift_search, "next_gift", lambda *a: next(picks, None))
    monkeypatch.setattr(actions.GiftSearch, "pick", staticmethod(lambda context, gift: actions.tap(context, 400, 400, wait=0) or True))
    page_until(context, "GiftSearch", 1)
    assert actions.GiftSearch().run(context, argv())
    assert taps(context) == [(400, 400)] and actions.STUCK["flag"] is None


def test_an_exploration_reward_gone_mid_give_up_is_handed_back_not_stuck(context, guarded, monkeypatch):
    monkeypatch.setattr(actions.settlement, "read_result", lambda text: (5, False, 3, 5))  # goal not met: give up
    page_until(context, "ExplorationReward", 1)
    assert actions.Settle().run(context, argv())
    assert taps(context) == [actions.GIVE_UP] and actions.STUCK["flag"] is None


def test_a_gift_search_gone_under_its_consume_dialog_is_not_confirmed(context, guarded, monkeypatch):
    ctl = context.tasker.controller
    actions.RUN["team"] = {"gift_search": {"enabled": True, "gifts": [{"name": "Phlebotomy Pack"}]}}
    monkeypatch.setattr(actions.gift_search, "select_count", lambda text: (1, 1))
    monkeypatch.setattr(actions.GiftSearch, "chosen", staticmethod(lambda *a: ["Phlebotomy Pack"]))
    monkeypatch.setattr(actions.gift_search, "next_gift", lambda *a: None)
    monkeypatch.setattr(actions, "text", lambda context, image, roi, only_rec=False:
                        "Consume 70 Starlight" if roi == actions.SEARCH_DIALOG and ctl.post_click.call_count else "")
    page_until(context, "GiftSearch", 1)  # gone once Select brought its dialog up
    assert actions.GiftSearch().run(context, argv())
    assert taps(context) == [actions.SEARCH_SELECT]


def test_a_starting_gift_page_gone_after_a_gift_tap_does_not_press_select(context, guarded, monkeypatch):
    actions.RUN["team"] = {"keyword": "Burn", "gift_search": {"enabled": False, "gifts": []}}
    monkeypatch.setattr(actions.PickStartingGift, "set_gift_search", staticmethod(lambda *a: None))
    monkeypatch.setattr(actions.PickStartingGift, "full", staticmethod(lambda *a: False))
    monkeypatch.setattr(actions.PickStartingGift, "count", staticmethod(lambda *a: (0, 1)))
    monkeypatch.setattr(actions, "ocr", lambda *a, **k: [("Burn", (200, 200, 60, 20))])
    page_until(context, "StartingGift", 2)  # the cabinet, then its first gift
    assert actions.PickStartingGift().run(context, argv())
    assert taps(context) == [(230, 285), (970, 262)]


def test_a_fusion_gone_after_a_cell_tap_taps_nothing_more(context, guarded, monkeypatch):
    # The first material went in; with the shop gone then, the next material does not go out.
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, ("Bleed", None), ("Tremor", None), ("Pierce", None))
    page_until(context, "Shop", 5)  # gone after Fuse, the centre, Burn, its OK and the first cell
    with pytest.raises(actions.PageGone):
        actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, {})
    assert taps(context)[4] in actions.FUSE_CELLS and not set(taps(context)[5:]) & set(actions.FUSE_CELLS)


def test_hands_back_clears_the_runtime_cache_of_a_long_task():
    """#176: MaaFramework keeps every node's detail until clear_cache, and a dungeon run is one task."""
    class Act:
        @actions.hands_back
        def run(self, context, argv):
            context.tasker.clear_cache.assert_not_called()  # after the action: its own calls still see the detail
            if argv.gone:
                raise actions.PageGone("the map")
            return True

    context = MagicMock()
    def nodes(n, gone=False):
        return SimpleNamespace(task_detail=SimpleNamespace(node_id_list=list(range(n))), gone=gone)

    assert Act().run(context, nodes(actions.CLEAR_CACHE_AFTER_NODES - 1))
    context.tasker.clear_cache.assert_not_called()
    assert Act().run(context, nodes(actions.CLEAR_CACHE_AFTER_NODES))
    context.tasker.clear_cache.assert_called_once()
    context.tasker.clear_cache.reset_mock()
    assert Act().run(context, nodes(actions.CLEAR_CACHE_AFTER_NODES, gone=True))  # PageGone hands back too
    context.tasker.clear_cache.assert_called_once()
