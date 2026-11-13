"""The mirror map's actions (agent/map_actions.py): entering a node, routing the floor, and forfeiting.

Split out of tests/test_actions.py (#713); the fake Maa context and the helpers other files share stay there."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT

import numpy as np
import pytest

import actions
import map_actions
import map_route
from agent_patch import patch_all
import test_actions

from test_actions import TimedGame, argv, map_world, moved

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


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
    patch_all(monkeypatch, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True  # a node entered before: the bus is not tried first
    map_actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 + map_actions.SLOT[0], 248 + map_actions.SLOT[1])  # the middle row's battle


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
        if name in map_actions.MARKS:
            mark, (ox, oy, _, _) = map_actions.MARKS[name]
            x, y = override[name]["roi"][:2]
            return SimpleNamespace(hit=True, box=[x, y, 26, 24]) if mark in seen_live.get((x - ox, y - oy), ()) else None
        return None
    context.run_recognition.side_effect = run_recognition
    slots = map_actions.RouteMap.read_slots(context, image, 50, 320)
    ahead = map_actions.RouteMap.read_ahead(context, image, 50 + map_actions.SLOT[0], 320 + map_actions.SLOT[1], slots)
    weights = {"event": 1, "battle": 2, "focused": 4, "shop": 7, "unknown": 9}
    assert slots["up"][0] == "event"
    score, path = map_route.paths(slots, weights, ahead)[map_route.rank(slots, weights, ahead)[0]]
    assert (path, score) == (["up", "mid", "mid", "mid"], 19)


RED = Path(__file__).resolve().parent / "data/map_red_theme.npz"  # live 2026-10-18, floor 3 hard, red theme


def test_a_column_of_lit_events_its_templates_miss_is_read_and_a_dark_one_ends_the_read(context):
    # H1: next to the bus a Focused; then two dim red "?" (no template hit, linked by bright lines); then black.
    v = np.zeros((720, 1280), np.uint8)
    v[70:615, :1180] = np.load(RED)["h1_v"]
    context.run_recognition.return_value = None  # no mark on any node past the first column
    ahead = map_actions.RouteMap.read_ahead(context, v[..., None].repeat(3, axis=2), 50 + map_actions.SLOT[0], 320 + map_actions.SLOT[1], {"mid": ("focused", 2)})
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
    assert map_actions.node_at(context, image, 725, 72) == "unknown"
    assert map_actions.node_at(context, image, 329, 144) == "event"  # the top row with the bus at BUS_HOME


def test_after_a_restart_or_recovery_the_bus_is_tapped_first(context, monkeypatch):
    # #88: L3 or Accept results leave the bus on a node not entered yet, whose panel its tap opens.
    patch_all(monkeypatch, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    bus_at(context, *map_actions.BUS_HOME, linked=("MapLinkMid", "MapNodeCost"))
    map_actions.RouteMap().run(context, None)
    bx, by = map_actions.BUS_HOME
    assert context.tasker.controller.post_click.call_args_list[0].args == (bx + 22, by + 37)


def test_a_bus_tap_on_a_node_already_entered_gives_up_quickly_for_the_planned_slot(context, clock, monkeypatch):
    # #130 (live 2026-10-18 07:04:47): after an agent restart the first tap, on the bus, showed no panel
    # (its node was entered) and waited the full 2 s before the planned slot; a panel shows within about 0.5 s.
    patch_all(monkeypatch, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    bus_at(context, *map_actions.BUS_HOME, linked=("MapLinkMid", "MapNodeCost"))
    ctl, at = context.tasker.controller, []
    ctl.post_click.side_effect = lambda x, y: at.append(((x, y), actions.time.monotonic())) or DEFAULT
    map_actions.RouteMap().run(context, None)
    bx, by = map_actions.BUS_HOME
    (bus, t0), (slot, t1) = at[0], at[1]
    assert bus == (bx + 22, by + 37) and slot == (bx + map_actions.SLOT[0], by + map_actions.SLOT[1])  # the bus first, then the slot
    assert t1 - t0 <= 1.3


def test_a_bus_dragged_off_the_screen_is_found_by_dragging_the_map(context, monkeypatch):
    # #61, live 2026-10-16: the map dragged by hand, the bus off the top; three blind rounds, L1, then L2.
    patch_all(monkeypatch, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True
    ctl = context.tasker.controller

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[446, 320, 45, 75]) if ctl.post_touch_up.called else None
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    map_actions.RouteMap().run(context, None)
    assert ctl.post_click.call_args_list[0].args == (446 + map_actions.SLOT[0], 320 + map_actions.SLOT[1])
    assert actions.STUCK["flag"] is None or actions.STUCK["flag"][1] == 1  # no node panel in this fake: a miss


def test_a_bus_not_found_even_by_dragging_goes_straight_to_l2(context, monkeypatch):
    # #61: To Window and Resume put the map back; L1 (the back key) does nothing for a map.
    patch_all(monkeypatch, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True
    map_actions.RouteMap().run(context, None)
    assert context.tasker.controller.post_click.called  # the fallback taps still go first
    assert actions.STUCK["flag"][1] == 2


def test_a_bus_at_the_far_left_is_not_dragged(context):
    bus_at(context, *map_actions.BUS_HOME, linked=("MapLinkMid", "MapLinkDown"))
    _, bus = map_actions.RouteMap.find_bus(context)
    assert bus == map_actions.BUS_HOME
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_map_at_rest_is_dragged(context):
    # #111: the bus goes to the far left, where the screen shows it and about four columns.
    bus_at(context, 446, 248, linked=("MapLinkMid",))
    map_actions.RouteMap.find_bus(context)
    context.tasker.controller.post_touch_down.assert_called()


WEIGHTS = {"event": 1, "battle": 2, "focused": 4, "unknown": 9}


def test_the_bus_is_dragged_to_the_far_left_and_the_cheapest_path_over_four_columns_is_taken(context, monkeypatch):
    # The user (#111): event -> battle -> battle -> Focused (9) loses to battle -> battle -> battle -> event (7),
    # which only the fourth column tells apart; with the bus at rest it is off screen.
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "down"): {"cost"},
             (3, "up"): {"cost"}, (3, "down"): {"cost"}, (4, "up"): {"cost", "gift"}, (4, "down"): {"event"}}
    links = [((c, r), (c + 1, r)) for c in (1, 2, 3) for r in ("up", "down")]
    offsets = map_world(context, nodes, links, bus_x=446)
    map_actions.RouteMap().run(context, None)
    # To the far left, then (#202) a drag two columns on that stops at the map's edge, and back.
    assert len(offsets) == 3 and abs(446 - offsets[-1] - map_actions.BUS_HOME[0]) <= 30
    first = context.tasker.controller.post_click.call_args_list[0].args
    assert first == (446 - offsets[-1] + map_actions.SLOT[0], map_actions.BUS_HOME[1] + map_actions.SLOT[1] + 213)  # the bottom row's battle


def test_two_columns_on_a_hard_floor_take_the_cheapest_path(context, monkeypatch):
    # Hard mode shows two columns; nothing past them is lit to read.
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost", "gift"}, (2, "down"): {"event"}}
    map_world(context, nodes, [((1, "up"), (2, "up")), ((1, "down"), (2, "down"))], bus_x=map_actions.BUS_HOME[0])
    map_actions.RouteMap().run(context, None)
    first = context.tasker.controller.post_click.call_args_list[0].args
    bx, by = map_actions.BUS_HOME
    assert first == (bx + map_actions.SLOT[0], by + map_actions.SLOT[1] + 213)  # battle -> event (3), not event -> focused (5)
    context.tasker.controller.post_touch_down.assert_not_called()


def test_a_full_read_plans_the_path_and_the_next_step_follows_it_without_a_drag(context, monkeypatch):
    # The user (#111): once the floor's nodes are read, follow the path decided on.
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    actions.RUN["floor"] = 1
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}, (2, "up"): {"cost"}, (2, "mid"): {"cost"},
             (3, "up"): {"cost", "gift"}, (3, "mid"): {"event"}}
    links = [((1, "up"), (2, "up")), ((1, "down"), (2, "mid")), ((2, "up"), (3, "up")), ((2, "mid"), (3, "mid"))]
    map_world(context, nodes, links, bus_x=map_actions.BUS_HOME[0])
    map_actions.RouteMap().run(context, None)  # down battle > mid battle > mid event (5), not up event > battle > focused (7)
    # Steps go from the node before: up from the bottom row to the middle one, then straight on.
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": [("up", "battle"), ("mid", "event")]}

    context.reset_mock()  # on the battle's node now, the map back at rest
    map_world(context, {(1, "up"): {"cost"}, (1, "down"): {"cost"}}, [], bus_x=446)
    map_actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_not_called()
    assert context.tasker.controller.post_click.call_args_list[0].args == (446 + map_actions.SLOT[0], map_actions.BUS_HOME[1] + map_actions.SLOT[1] - 213)
    assert actions.RUN["map_plan"]["steps"] == [("mid", "event")]


def test_a_planned_slot_of_another_type_means_the_map_is_read_again(context, monkeypatch):
    # The bus not where the plan put it, or a node misread from afar: read again rather than follow.
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=1, map_plan={"floor": 1, "steps": [("mid", "event")]})
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    map_actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()  # dragged to the far left for a full read
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": []}


def test_a_planned_slot_not_linked_to_the_bus_means_the_map_is_read_again(context, monkeypatch):
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=1, map_plan={"floor": 1, "steps": [("up", "battle")]})
    map_world(context, {(1, "mid"): {"event"}}, [], bus_x=446)
    map_actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()  # dragged to the far left for a full read
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": []}  # the new plan: the middle event, nothing after


def test_a_plan_from_the_last_floor_is_not_followed(context, monkeypatch):
    patch_all(monkeypatch, "map_weights", lambda context: WEIGHTS)
    actions.RUN.update(floor=2, map_plan={"floor": 1, "steps": [("mid", "battle")]})
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    map_actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_called()
    assert actions.RUN["map_plan"] == {"floor": 2, "steps": []}


def test_forfeit_reads_its_dialogs_however_ocr_cases_them(context, monkeypatch):
    # #138: the settings panel and the Quit dialog read in capitals still count as shown.
    reads = iter(["DUNGEON PROGRESS", "QUIT EXPLORING THE DUNGEON?", ""])
    patch_all(monkeypatch, "text", lambda *a, **k: next(reads))
    patch_all(monkeypatch, "tap", lambda *a, **k: None)
    actions.RUN["forfeit"] = True
    assert map_actions.forfeit(context) is True
    assert actions.STUCK["flag"] is None and "forfeit" not in actions.RUN


PROGRESS_TITLE, QUIT_DIALOG = (520, 212, 240, 30), tuple(map_actions.FORFEIT_DIALOG)


def forfeit_game(context, monkeypatch, gear=((0.5, {PROGRESS_TITLE: "Dungeon Progress"}, 30),)):
    return TimedGame(monkeypatch, context, {}, {
        map_actions.GEAR: list(gear),
        map_actions.FORFEIT: [(0.5, {QUIT_DIALOG: "Quit exploring the dungeon?"}, 40)],
        map_actions.FORFEIT_CONFIRM: [(0.5, {QUIT_DIALOG: ""}, 50)]})


def test_forfeit_taps_each_step_once_its_panel_shows_not_after_2_s(context, clock, monkeypatch):
    # #258: the gear, Forfeit and Confirm slept 2 s each; each now goes on once the panel or dialog it brings is still,
    # and Confirm hands back once the dialog goes.
    game = forfeit_game(context, monkeypatch)
    actions.RUN["forfeit"] = True
    assert map_actions.forfeit(context) is True
    assert game.taps == [map_actions.GEAR, map_actions.FORFEIT, map_actions.FORFEIT_CONFIRM]
    assert "forfeit" not in actions.RUN and actions.STUCK["flag"] is None
    assert sum(clock) < 3  # was 6 s


def test_forfeit_hands_back_once_the_map_is_gone_after_quit(context, clock, monkeypatch):
    # The map stays up a moment after Quit: handed back on it, RouteMap (forfeit flag gone) would pick a node.
    game = forfeit_game(context, monkeypatch)
    game.answers[map_actions.FORFEIT_CONFIRM] = [[(0.4, {QUIT_DIALOG: ""}, 50), (1.0, {"map": False}, 70)]]
    game.reads["map"] = True
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name == "MirrorMap" and game.now()["map"] else None
    actions.RUN["forfeit"] = True
    assert map_actions.forfeit(context) is True
    assert not game.now()["map"] and game.taps.count(map_actions.FORFEIT_CONFIRM) == 1


def test_forfeit_taps_the_gear_again_when_the_panel_does_not_show_in_2_s(context, clock, monkeypatch):
    game = forfeit_game(context, monkeypatch, gear=[None, (0.5, {PROGRESS_TITLE: "Dungeon Progress"}, 30)])
    actions.RUN["forfeit"] = True
    assert map_actions.forfeit(context) is True
    assert game.taps == [map_actions.GEAR, map_actions.GEAR, map_actions.FORFEIT, map_actions.FORFEIT_CONFIRM]
    assert sum(clock) >= 2  # the lost tap's old wait


def test_a_map_gone_while_looking_for_its_bus_is_not_dragged(context, guarded):
    actions.RUN["difficulty"] = "normal"
    assert map_actions.RouteMap().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None
