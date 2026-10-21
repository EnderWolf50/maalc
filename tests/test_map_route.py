from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import yaml

import actions
import map_route as mr
import test_actions
from test_actions import map_world

clock, context = test_actions.clock, test_actions.context  # fixtures of the fake Maa context

WEIGHTS = yaml.safe_load((Path(__file__).resolve().parent.parent / "assets/resource/base/data/map_weights.yaml").read_text(encoding="utf-8"))
NORMAL, HARD = WEIGHTS["normal"], WEIGHTS["hard"]


@pytest.mark.parametrize(("marks", "expected"), [
    ({"boss", "cost", "gift"}, "boss"),
    ({"boss"}, "boss"),  # floor 5 boss: no badges
    ({"focused", "cost", "gift"}, "focused"),
    ({"cost", "gift"}, "abno"),
    ({"cost"}, "battle"),
    ({"event"}, "event"),
    ({"shop"}, "shop"),
    # No Cost coin, no boss, Focused or shop mark: an event, its "?" missed by the templates. Live 2026-10-18,
    # floor 2 "Lake World" (cyan): a bright "?" next to the bus; MapPanned.png: a dim one two columns out.
    ({"gift"}, "event"),
    (set(), "event"),
])
def test_node_type(marks, expected):
    assert mr.node_type(marks) == expected


def test_the_column_before_the_boss_is_the_shop():
    # Live 2026-10-18 (floor 1 orange, floor 2 cyan): bus, one node read as an event, then the boss. Every path ends
    # at the shop, the last column before the boss, whatever the node's mark reads (#146).
    slots, ahead = {"up": ("event", 1)}, [{"up": ("boss", {"up"})}]
    mr.shop_before_boss(slots, ahead)
    assert slots == {"up": ("shop", 1)}
    # Further out: only the column that holds the boss' neighbour changes; the columns before stay as read.
    slots = {"mid": ("battle", 2), "down": ("event", 1)}
    ahead = [{"mid": ("event", {"mid", "down"}), "down": ("battle", {"down"})}, {"mid": ("boss", {"mid", "down"})}]
    mr.shop_before_boss(slots, ahead)
    assert slots == {"mid": ("battle", 2), "down": ("event", 1)}
    assert ahead[0] == {"mid": ("shop", {"mid", "down"}), "down": ("shop", {"down"})}
    # No boss on screen: nothing is a shop by position.
    slots = {"mid": ("event", 1)}
    mr.shop_before_boss(slots, [{"mid": ("event", {"mid"})}])
    assert slots == {"mid": ("event", 1)}


def test_lowest_weight_first():
    slots = {"up": ("battle", 1), "mid": ("abno", 2), "down": ("event", 0)}
    assert mr.rank(slots, NORMAL) == ["down", "up", "mid"]


def test_equal_weight_takes_more_routes_onward():
    # Live 2026-10-15, floor 1: two battles, the middle one leads on to two nodes.
    assert mr.rank({"mid": ("battle", 2), "down": ("battle", 1)}, NORMAL)[0] == "mid"
    assert mr.rank({"up": ("event", 2), "down": ("event", 1)}, NORMAL)[0] == "up"


def test_unread_or_equal_routes_fall_back_to_middle_then_top():
    assert mr.rank({"up": ("battle", None), "mid": ("battle", None), "down": ("battle", None)}, NORMAL) == ["mid", "up", "down"]
    assert mr.rank({"up": ("event", 2), "down": ("event", 2)}, NORMAL) == ["up", "down"]


def test_boss_only_when_alone():
    assert mr.rank({"mid": ("boss", 0), "down": ("unknown", 0)}, NORMAL) == ["down"]
    assert mr.rank({"mid": ("boss", 0)}, NORMAL) == ["mid"]


def test_two_columns_take_the_cheapest_path():
    # Live 2026-10-18, hard floor 1 (user's capture): battle / event / battle, then battle / battle;
    # each battle runs straight on, the event links to both. event -> battle (1 + 2) is cheapest.
    ahead = [{"up": ("battle", {"up", "mid"}), "down": ("battle", {"mid", "down"})}]
    slots = {"up": ("battle", 1), "mid": ("event", 2), "down": ("battle", 1)}
    assert mr.rank(slots, HARD, ahead)[0] == "mid"
    # An event on to an abnormality (1 + 5) loses to a battle on to an event (2 + 1).
    ahead = [{"up": ("abno", {"up"}), "down": ("event", {"down"})}]
    assert mr.rank({"up": ("event", 1), "down": ("battle", 1)}, HARD, ahead) == ["down", "up"]
    assert mr.paths({"up": ("event", 1), "down": ("battle", 1)}, HARD, ahead)["down"] == (3, ["down", "down"])


def test_a_slot_with_no_link_read_onward_goes_on_to_the_cheapest_node():
    # Every node leads on, so an unread link must not make a path look shorter (cheaper) than the others.
    ahead = [{"down": ("event", {"down"})}]
    assert mr.rank({"up": ("battle", None), "down": ("event", None)}, HARD, ahead) == ["down", "up"]


def lit(links, size=(720, 1280)):
    """A dark map with bright 5 px links from (725, 285) into the next column, plus faint noise."""
    v = np.random.default_rng(0).integers(0, 30, size=size).astype(np.uint8)
    for dy in links:
        for t in np.linspace(0, 1, 600):
            x, y = int(725 + 255 * t), int(285 + dy * t)
            v[y - 2:y + 3, x - 2:x + 3] = 200
    return v


@pytest.mark.parametrize("links", [(), (0,), (-213, 213), (-213, 0, 213)])
def test_routes_counts_drawn_links(links):
    assert mr.routes(lit(links), 725, 285) == len(links)


def test_routes_unreadable_off_the_map():
    # A top-row node at rest sits under the resource bar: nothing onward can be read.
    assert mr.routes(lit(()), 725, -200) is None


def test_a_link_along_the_top_row_under_the_resource_bar_edge_still_reads():
    """#129, live 2026-10-18, floor 3 HARD (2 columns, map at rest: it cannot pan): the top row's centres sit at y 72.

    The link from c1 up (726, 72) to c2 up (981, 72) is lit but its upper side sample (y 59) fell above the
    readable area, so it read None and c2 up, whose badges and node the HUD covers, was left out.
    tests/data/map_hard_f3_top.npz is the frame's per-pixel brightness, y 0-299, x 600-1099.
    """
    v = np.zeros((720, 1280), np.uint8)
    v[:300, 600:1100] = np.load(Path(__file__).resolve().parent / "data/map_hard_f3_top.npz")["v"]
    assert mr.line_contrast(v, 726, 72, 981, 72) >= mr.LINE_CONTRAST
    assert mr.line_contrast(v, 726, 285, 981, 72) < mr.LINE_CONTRAST  # mid has no link to it
    assert mr.routes(v, 726, 72) == 2  # c2 up and c2 mid


def test_the_lit_links_from_the_bus_read_at_the_far_left():
    """Live 2026-10-18, bus at 50, 320: the chevron templates missed; the lines did not.

    tests/data/map_far_left.npz is the frame's per-pixel brightness, x 0-399.
    """
    v = np.load(Path(__file__).resolve().parent / "data/map_far_left.npz")["v"]
    bus, slot = (50 + 22, 320 + 37), (50 + 279, 320 + 37)
    lit = {row: mr.line_contrast(v, *bus, slot[0], slot[1] + dy) for row, dy in mr.ROW_DY.items()}
    assert lit["up"] >= 60 and lit["down"] >= 60 and lit["mid"] < 15


# RouteMap on a fresh floor's map, driven offline with test_actions.py's fake Maa context.
AB_WEIGHTS = {"event": 1, "battle": 2, "abno": 5, "unknown": 9}


def title_reads(context, shown, switch_at=0.0, then=None):
    """The map's floor title reads shown, then from the fake clock's switch_at on; everything else as the fake has it."""
    inner = context.run_recognition.side_effect

    def run_recognition(name, image, override=None):
        if name == "ReadText" and override["ReadText"]["roi"] == actions.MAP_TITLE:
            text = then if then and actions.time.monotonic() >= switch_at else shown
            return SimpleNamespace(all_results=[SimpleNamespace(text=text, box=(40, 90, 220, 25))])
        return inner(name, image, override)
    context.run_recognition.side_effect = run_recognition


def test_the_last_floors_map_leaving_after_a_theme_pack_is_not_read(context, monkeypatch):
    # Live 2026-10-19 (A F2-F5, B F2-F5): after the floor 3 pull the floor 2 map stayed ~3 s, its bus driving off to
    # the exit; RouteMap dragged it, then the new map, and read floor 3 from the bus at rest.
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN["floor"] = 3
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    ctl, gone = context.tasker.controller, actions.time.monotonic() + 3
    title_reads(context, "Exploring Floor 2", switch_at=gone, then="Exploring Floor 3")
    downs = []
    touch_down = ctl.post_touch_down.side_effect
    ctl.post_touch_down.side_effect = lambda x, y: downs.append(actions.time.monotonic()) or touch_down(x, y)
    while not ctl.post_click.called and actions.time.monotonic() < gone + 30:  # MirrorHub calls it again
        actions.RouteMap().run(context, None)
    assert downs and min(downs) >= gone  # no drag on the last floor's map
    assert actions.RUN["floor"] == 3


def test_a_floor_title_that_never_changes_holds_the_map_once(context, clock, monkeypatch):
    # A misread title must not hold the map forever, nor every read of the floor; the floor itself stays.
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN["floor"] = 3
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    title_reads(context, "Exploring Floor 2")
    actions.RouteMap().run(context, None)
    assert actions.RUN["floor"] == 3
    context.tasker.controller.post_click.assert_called()
    waited = sum(clock)
    actions.RouteMap().run(context, None)
    assert sum(clock) - waited < actions.MAP_LEAVING  # not waited out again


def test_a_fresh_floors_map_that_does_not_take_drags_yet_is_dragged_until_the_bus_moves(context, monkeypatch):
    # Live 2026-10-19: a floor's new map ignored drags for its first seconds; after four looks find_bus gave up and
    # the floor was read and tapped with the bus at rest, its top row under the resource bar.
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN.update(floor=3, fresh_floor=True)  # set by the theme pack pull
    nodes = {(1, "up"): {"event"}, (1, "down"): {"cost"}}
    offsets = map_world(context, nodes, [], bus_x=446)
    title_reads(context, "Exploring Floor 3")
    ctl = context.tasker.controller
    move = ctl.post_touch_move.side_effect
    ctl.post_touch_move.side_effect = lambda x, y: MagicMock() if ctl.post_touch_down.call_count <= 4 else move(x, y)
    actions.RouteMap().run(context, None)
    assert abs(446 - offsets[-1] - actions.BUS_HOME[0]) <= 30  # the bus panned home in the end
    first = ctl.post_click.call_args_list[0].args
    assert first == (446 - offsets[-1] + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] - 213)  # the top row's event


def test_a_fresh_map_dragged_to_its_edge_costs_no_extra_drags(context):
    # Live 2026-10-21 NORMAL floor 2: the first drag took the bus from 446 to 196, where the map's left edge stops
    # it; the drags after it left the bus there and were taken for a map that takes no drags yet, for 8 s.
    actions.RUN.update(floor=2, fresh_floor=True)
    offsets = map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    ctl, edge, at = context.tasker.controller, 250, []  # the screen's offset stops at 250: the bus at 196
    down, move = ctl.post_touch_down.side_effect, ctl.post_touch_move.side_effect

    def down_at(x, y):
        at[:] = [x, offsets[-1] if offsets else 0]
        return down(x, y)
    ctl.post_touch_down.side_effect = down_at
    ctl.post_touch_move.side_effect = lambda x, y: move(max(x, at[0] - (edge - at[1])), y)
    image, bus = actions.RouteMap.find_bus(context)
    assert bus == (196, actions.BUS_HOME[1])
    assert ctl.post_touch_down.call_count == 2  # one drag to the edge, one that shows it


@pytest.mark.parametrize(("shown", "floor"), [("Exploring Floor 3", 3), ("Exploring Floar 3", 3), ("Exploring", None), ("", None)])
def test_the_map_title_gives_the_floor(context, shown, floor):
    context.run_recognition.side_effect = lambda name, image, override=None: SimpleNamespace(
        all_results=[SimpleNamespace(text=shown, box=(40, 90, 220, 25))] if shown else [])
    assert actions.map_floor(context, np.zeros((720, 1280, 3), np.uint8)) == floor


def test_a_map_that_does_not_pan_costs_no_extra_drags_once_a_node_is_entered(context):
    # Only a floor's fresh map waits out its drags; elsewhere three pans stay the limit.
    actions.RUN["fresh_floor"] = True  # set by the theme pack pull
    nodes = {(1, "mid"): {"cost"}}
    map_world(context, nodes, [], bus_x=446)
    ctl = context.tasker.controller
    ctl.post_click(725, 391)  # a node's tap opens its panel
    assert actions.enter_node(context)
    ctl.post_touch_move.side_effect = lambda x, y: MagicMock()
    actions.RouteMap.find_bus(context)
    assert ctl.post_touch_down.call_count == 3


def test_a_gift_window_over_the_map_after_a_battle_goes_back_to_mirror_hub(context, monkeypatch):
    # Live 2026-10-19 23:34: after an abnormality fight E.G.O Gift GET! slid in over the map (GiftGet 0.73, under its
    # threshold, MirrorMap 0.997); RouteMap read under it, found no bus, dragged the map about and went to L2, then L3.
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    plan = {"floor": 3, "steps": [("mid", "battle")]}
    actions.RUN.update(map_entered=True, floor=3, map_plan=dict(plan))
    context.run_recognition.side_effect = lambda name, image, override=None: SimpleNamespace(hit=True) if name == "GiftGet" else None
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_not_called()
    context.tasker.controller.post_click.assert_not_called()
    assert actions.STUCK["flag"] is None
    assert actions.RUN["map_plan"] == plan  # the floor's plan survives the window


def test_a_gift_window_that_slides_in_over_the_bus_is_not_dragged_under(context, monkeypatch):
    # The window can slide in after RouteMap's first look, with the bus still showing beside it.
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN["floor"] = 3
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    title_reads(context, "Exploring Floor 3")
    recognize, looks = context.run_recognition.side_effect, []

    def window(name, image, override=None):
        if name != "GiftGet":
            return recognize(name, image, override)
        looks.append(name)
        return SimpleNamespace(hit=True) if len(looks) > 1 else None
    context.run_recognition.side_effect = window
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_not_called()
    context.tasker.controller.post_click.assert_not_called()


def gift_window_after(context, looks):
    """MirrorMap's buttons stay readable (the GET! window dims the map under it); GiftGet reads from its looks-th look on."""
    inner, seen = context.run_recognition.side_effect, []

    def run_recognition(name, image, override=None):
        if name == "MirrorMap" and override is None:
            return SimpleNamespace(hit=True, box=[1200, 70, 60, 120])
        if name == "GiftGet":
            seen.append(name)
            return SimpleNamespace(hit=True) if len(seen) >= looks else None
        return inner(name, image, override) if inner else None
    context.run_recognition.side_effect = run_recognition


def test_a_gift_window_that_comes_up_while_the_bus_is_searched_for_is_not_dragged_under(context, monkeypatch):
    # #213, live 2026-10-21 09:20:41: after an abnormality fight the GET! window came up over the map while RouteMap
    # looked for the bus; it dragged the map about under the window ~20 s, "no bus on the map" went to L2, then L3.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN.update(map_entered=True, floor=3)
    gift_window_after(context, actions.MAP_LOOKS + 2)  # read only once the looks for a linked slot are done
    actions.RouteMap().run(context, None)
    context.tasker.controller.post_touch_down.assert_not_called()
    context.tasker.controller.post_click.assert_not_called()
    assert actions.STUCK["flag"] is None


def test_a_gift_window_that_comes_up_between_two_pans_ends_the_pans(context, monkeypatch):
    # #213: the bus far out takes several pans to the far left; the window rose between two of them.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    offsets = map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    monkeypatch.setattr(actions, "scroll", lambda *a, **k: offsets.append(None))  # a drag that moves nothing
    gift_window_after(context, 4)  # RouteMap's first look, the look for a slot, the first pan's guard miss it
    actions.RUN["fresh_floor"] = True  # drags that leave the bus in place are made again
    actions.RouteMap().run(context, None)
    assert len(offsets) == 1
    context.tasker.controller.post_click.assert_not_called()
    assert actions.STUCK["flag"] is None
