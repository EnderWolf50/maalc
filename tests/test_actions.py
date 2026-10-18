"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import json
import time
from pathlib import Path
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
    # unknown (9), and the bot took the middle abnormality (22) over up event > mid battle > mid shop > boss (19).
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
    ahead = actions.RouteMap.read_ahead(context, image, 50, 320, slots)
    weights = {"event": 1, "battle": 2, "abno": 5, "shop": 7, "unknown": 9}
    assert slots["up"][0] == "event"
    score, path = actions.map_route.paths(slots, weights, ahead)[actions.map_route.rank(slots, weights, ahead)[0]]
    assert (path, score) == (["up", "mid", "mid", "mid"], 19)


RED = Path(__file__).resolve().parent / "data/map_red_theme.npz"  # live 2026-10-18, floor 3 hard, red theme


def test_a_column_of_lit_events_its_templates_miss_is_read_and_a_dark_one_ends_the_read(context):
    # H1: next to the bus a Focused; then two dim red "?" (no template hit, linked by bright lines); then black.
    v = np.zeros((720, 1280), np.uint8)
    v[70:615, :1180] = np.load(RED)["h1_v"]
    context.run_recognition.return_value = None  # no mark on any node past the first column
    ahead = actions.RouteMap.read_ahead(context, v[..., None].repeat(3, axis=2), 50, 320, {"mid": ("focused", 2)})
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


@pytest.mark.parametrize(("number", "expected"), [("85", "battle"), ("75.", "battle"), ("120", "risky"), ("50", "risky"), ("8", "battle"), ("", "battle")])
def test_a_cost_coin_whose_number_is_no_battle_cost_is_not_a_battle(context, number, expected):
    # #91: no Risky capture yet; a Cost coin alone read as a battle (weight 2) whatever it was.
    def run_recognition(name, image, override=None):
        if name == "MapNodeCost":
            return SimpleNamespace(hit=True, box=[700, 300, 26, 24])
        if name == "ReadText" and number:
            return SimpleNamespace(all_results=[SimpleNamespace(text=number, box=(0, 0, 20, 20))])
        return None
    context.run_recognition.side_effect = run_recognition
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380) == expected
    # Past the first column the badges are dim (offline: MirrorMap.png's 85 read 8): no Cost read there.
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380, costs=False) == "battle"


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


def map_world(context, nodes, links, bus_x):
    """A map wider than the screen, the bus at (bus_x, BUS_HOME's y) on screen; drags move the screen over it.

    nodes: {(column, row): marks}, column 1 next to the bus; links: ((column, row), (column, row)) pairs.
    The bus's chevrons lead to the first column's nodes; a tap on anything but Enter opens a node panel.
    The bus stands on a node already entered (no tap on it first, #88). Returns the screen's offsets after each drag.
    """
    actions.RUN["map_entered"] = True
    bx, by = 446, actions.BUS_HOME[1]  # on the map; the screen starts at 446 - bus_x

    def at(column, row):
        return bx + actions.SLOT[0] + (column - 1) * 255, by + actions.SLOT[1] + {"up": -213, "mid": 0, "down": 213}[row]
    world = np.random.default_rng(2).integers(0, 30, size=(720, 1800, 3)).astype(np.uint8)
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
        off[0] = min(max(0, start[1] + start[0] - x), 1800 - 1280)
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


WEIGHTS = {"event": 1, "battle": 2, "abno": 5, "unknown": 9}


def test_the_bus_is_dragged_to_the_far_left_and_the_cheapest_path_over_four_columns_is_taken(context, monkeypatch):
    # The user (#111): event -> battle -> battle -> abnormality (10) loses to battle -> battle -> battle -> event (7),
    # which only the fourth column tells apart; with the bus at rest it is off screen.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "down"): {"cost"},
             (3, "up"): {"cost"}, (3, "down"): {"cost"}, (4, "up"): {"cost", "gift"}, (4, "down"): {"event"}}
    links = [((c, r), (c + 1, r)) for c in (1, 2, 3) for r in ("up", "down")]
    offsets = map_world(context, nodes, links, bus_x=446)
    actions.RouteMap().run(context, None)
    assert len(offsets) == 1 and abs(446 - offsets[0] - actions.BUS_HOME[0]) <= 30  # one drag, none back
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 - offsets[0] + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] + 213)  # the bottom row's battle


def test_two_columns_on_a_hard_floor_take_the_cheapest_path(context, monkeypatch):
    # Hard mode shows two columns; nothing past them is lit to read.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost", "gift"}, (2, "down"): {"event"}}
    map_world(context, nodes, [((1, "up"), (2, "up")), ((1, "down"), (2, "down"))], bus_x=actions.BUS_HOME[0])
    actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    bx, by = actions.BUS_HOME
    assert first == (bx + actions.SLOT[0], by + actions.SLOT[1] + 213)  # battle -> event (3), not event -> abno (6)
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_full_read_plans_the_path_and_the_next_step_follows_it_without_a_drag(context, monkeypatch):
    # The user (#111): once the floor's nodes are read, follow the path decided on.
    monkeypatch.setattr(actions, "map_weights", lambda context: WEIGHTS)
    actions.RUN["floor"] = 1
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "mid"): {"cost"},
             (3, "up"): {"cost", "gift"}, (3, "mid"): {"event"}}
    links = [((1, "up"), (2, "up")), ((1, "down"), (2, "mid")), ((2, "up"), (3, "up")), ((2, "mid"), (3, "mid"))]
    map_world(context, nodes, links, bus_x=actions.BUS_HOME[0])
    actions.RouteMap().run(context, None)  # down battle > mid battle > mid event (5), not up event > battle > abno (8)
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
