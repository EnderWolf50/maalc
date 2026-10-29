from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
import yaml
from PIL import Image

import actions
import map_route as mr
import test_actions
from test_actions import map_world

clock, context = test_actions.clock, test_actions.context  # fixtures of the fake Maa context

SCREENS = Path(__file__).resolve().parent / "screens"

WEIGHTS = yaml.safe_load((Path(__file__).resolve().parent.parent / "assets/resource/base/data/map_weights.yaml").read_text(encoding="utf-8"))
NORMAL, HARD = WEIGHTS["normal"], WEIGHTS["hard"]


@pytest.mark.parametrize(("marks", "expected"), [
    ({"boss", "cost", "gift"}, "boss"),
    ({"boss"}, "boss"),  # floor 5 boss: no badges
    # #91: no Cost read, the marks decide. The WARNING ring is Risky's or Abnormality's: the later, Risky.
    ({"ring", "cost", "gift"}, "risky"),
    ({"ring"}, "risky"),  # its Cost coin under the resource bar
    ({"cost", "gift"}, "focused"),
    ({"cost"}, "battle"),
    ({"event"}, "event"),
    ({"shop"}, "shop"),
    # No Cost coin, no boss, ring or shop mark: an event, its "?" missed by the templates. Live 2026-10-18,
    # floor 2 "Lake World" (cyan): a bright "?" next to the bus; MapPanned.png: a dim one two columns out.
    ({"gift"}, "event"),
    (set(), "event"),
])
def test_node_type(marks, expected):
    assert mr.node_type(marks) == expected


@pytest.mark.parametrize(("marks", "expected"), [
    ({"ring", "cost", "gift"}, "abno"),
    ({"cost"}, "abno"),  # the Cost outranks the marks: ring and gift box are both missed live (#91)
    ({"boss", "cost", "gift"}, "boss"),
    ({"event"}, "event"),
])
def test_node_type_by_cost(marks, expected):
    assert mr.node_type(marks, "abno") == expected


@pytest.mark.parametrize(("hard", "marks", "number", "expected"), [
    (False, {"MapNodeCost"}, "75.", "battle"),
    (False, {"MapNodeCost", "MapNodeGift"}, "100", "focused"),
    (False, {"MapNodeCost", "MapNodeGift"}, "00", "focused"),  # a leading 0 is a part read: the gift box decides
    (False, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "120", "risky"),
    (False, {"MapNodeCost", "MapNodeGift"}, "120", "risky"),  # its ring missed (live logs: 10 of 19)
    # #262: the number is taken as read, not snapped to the table on its last two digits: a 120 read 20 is no
    # Cost and the marks decide (the gift box alone: focused)
    (False, {"MapNodeCost", "MapNodeGift"}, "20", "focused"),
    (False, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "150", "abno"),
    (False, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "50", "risky"),
    (True, {"MapNodeCost"}, "85", "battle"),
    (True, {"MapNodeCost", "MapNodeGift"}, "120", "focused"),
    (True, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedRound"}, "150", "risky"),
    (True, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "180", "abno"),
    (False, {"MapNodeCost"}, "25", "battle"),  # OCR noise: no cost of the table, the marks decide
    (False, {"MapNodeCost"}, "8", "battle"),  # a single digit is a part read
    (False, {"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "", "risky"),  # unread: the ring's later kind
    # the boss' red glow missed: its Cost says boss (live 2026-10-23, hard floor 4, read focused by its gift box)
    (True, {"MapNodeCost", "MapNodeGift"}, "500", "boss"),
    (False, {"MapNodeCost", "MapNodeGift"}, "240", "boss"),
    (True, {"MapNodeCost", "MapNodeGift"}, "240", "focused"),  # a normal floor's boss Cost is none on hard
])
def test_a_node_is_typed_by_its_cost_on_the_floors_difficulty(context, hard, marks, number, expected):
    # #91: a Risky node carries the ring, gift box and Cost coin, and read as Focused (weight 4) by its ring.
    def run_recognition(name, image, override=None):
        if name in marks:
            return SimpleNamespace(hit=True, box=[700, 300, 26, 24])
        if name == "ReadText" and number:
            return SimpleNamespace(all_results=[SimpleNamespace(text=number, box=(0, 0, 20, 20))])
        return None
    context.run_recognition.side_effect = run_recognition
    actions.RUN.update(settings={}, difficulty="normal", floor_hard=hard)
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380) == expected


@pytest.mark.parametrize(("hard", "number", "why"), [
    (False, "", "no digits"),
    (False, ".8", "one digit"),
    (False, "00", "leading 0"),
    (False, "85", "85 is no normal Cost"),
    (True, "20", "20 is no hard Cost"),
])
def test_a_cost_read_as_no_cost_is_logged_with_its_text_and_crop(context, monkeypatch, tmp_path, hard, number, why):
    # #284: each way a Cost misses gets a line with the node, the OCR's own text and the difficulty, and its crop.
    def run_recognition(name, image, override=None):
        if name == "MapNodeCost":
            return SimpleNamespace(hit=True, box=[700, 300, 26, 24])
        if name == "ReadText":
            return SimpleNamespace(all_results=[SimpleNamespace(text=number, box=(0, 0, 20, 20))])
        return None
    context.run_recognition.side_effect = run_recognition
    actions.RUN.update(settings={}, difficulty="normal", floor_hard=hard)
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380) == "battle"
    miss = [line for line in logs if "Cost miss" in line]
    difficulty = "hard" if hard else "normal"
    assert len(miss) == 1 and miss[0].startswith(f"map: Cost miss at 713, 380 ({difficulty}): {why}, OCR {number!r}, crop logs/cost/")
    assert len(list((tmp_path / "logs" / "cost").glob("*_713_380.png"))) == 1


def test_a_cost_of_the_table_logs_no_miss(context, monkeypatch, tmp_path):
    def run_recognition(name, image, override=None):
        if name == "MapNodeCost":
            return SimpleNamespace(hit=True, box=[700, 300, 26, 24])
        return SimpleNamespace(all_results=[SimpleNamespace(text="75", box=(0, 0, 20, 20))]) if name == "ReadText" else None
    context.run_recognition.side_effect = run_recognition
    actions.RUN.update(settings={}, difficulty="normal", floor_hard=False)
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380) == "battle"
    assert not any("Cost miss" in line for line in logs) and not (tmp_path / "logs" / "cost").exists()


@pytest.mark.parametrize(("marks", "expected"), [
    ({"MapNodeCost"}, "battle"), ({"MapNodeCost", "MapNodeGift"}, "focused"), ({"MapNodeCost", "MapNodeGift", "MapNodeFocusedHex"}, "risky"),
])
def test_past_the_first_column_no_cost_is_read(context, marks, expected):
    # The badges are dim there (offline: MirrorMap.png's 85 read 8): a ring stands for Risky until read next to the bus.
    def run_recognition(name, image, override=None):
        return SimpleNamespace(hit=True, box=[700, 300, 26, 24]) if name in marks else None
    context.run_recognition.side_effect = run_recognition
    assert actions.node_at(context, np.zeros((720, 1280, 3), np.uint8), 713, 380, costs=False) == expected
    assert all(c.args[0] != "ReadText" for c in context.run_recognition.call_args_list)


@pytest.mark.parametrize(("run", "hard"), [
    ({}, False),  # no difficulty yet: normal, as "auto" (None) is (#257)
    ({"difficulty": "hard"}, True), ({"difficulty": "normal"}, False), ({"difficulty": None}, False),
    ({"difficulty": "hard", "floor_hard": False}, False), ({"difficulty": None, "floor_hard": True}, True),
])
def test_is_hard_takes_the_floors_difficulty_first(context, run, hard):
    actions.RUN.update(settings={}, **run)
    assert actions.is_hard(context) is hard


def test_the_column_after_a_shop_is_the_boss():
    # #279: the shop decides, whatever the next column reads; one that already reads boss stays it.
    after = {"mid": ("event", {"mid"}), "down": ("boss", {"mid"})}
    assert mr.boss_after_shop({"up": ("shop", 1)}, after) == ["mid"]
    assert after == {"mid": ("boss", {"mid"}), "down": ("boss", {"mid"})}
    after = {"mid": ("boss", {"mid"})}
    assert mr.boss_after_shop({"mid": ("shop", 1), "down": ("event", 1)}, after) == []  # nothing changed
    assert after == {"mid": ("boss", {"mid"})}


def test_the_column_after_anything_but_a_shop_is_left_as_read():
    # A boss read by its glow after a node that is no shop stays the boss (RouteMap logs the disagreement); no node is made a shop by the boss.
    before, after = {"mid": ("event", 1)}, {"mid": ("boss", {"mid"}), "up": ("battle", {"mid"})}
    assert mr.boss_after_shop(before, after) == []
    assert before == {"mid": ("event", 1)} and after == {"mid": ("boss", {"mid"}), "up": ("battle", {"mid"})}


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


def test_a_path_never_steps_two_rows():
    """#212, live 2026-10-21 floor 4: column 3's lower event went unread, so column 2's lower event had no link
    read onward; the path stepped from it to column 3's upper event, two rows apart, which no link joins."""
    slots = {"mid": ("abno", 2)}
    ahead = [{"up": ("event", {"mid"}), "down": ("event", {"mid"})}, {"up": ("event", {"up"})}, {"mid": ("abno", {"up"})}]
    for _, path in mr.paths(slots, NORMAL, ahead).values():
        assert all(abs(mr.ROW_DY[a] - mr.ROW_DY[b]) <= 213 for a, b in zip(path, path[1:]))
    # The cheapest node of the next column still scores the rest; only rows next to each other are assumed linked.
    down = mr.paths({"down": ("event", None)}, NORMAL, [{"up": ("event", {"mid"}), "mid": ("abno", {"up"})}])["down"]
    assert down == (NORMAL["event"] + NORMAL["abno"], ["down", "mid"])


def test_a_node_with_no_link_read_onward_takes_its_brightest_faint_one():
    # #212: down -> down read 14.4 over a bright nebula; down -> mid -1.6. up's 30 links as before.
    reads = {("down", "down"): 14.4, ("down", "mid"): -1.6, ("up", "up"): 30, ("up", "mid"): 12}
    assert mr.links(reads) == {("down", "down"), ("up", "up")}
    assert mr.links({("down", "down"): 7.9, ("down", "mid"): 0}) == set()
    # A diagonal crossed by a link read the other way (mid -> up) reads its crossing, not a link of its own.
    assert mr.links({("up", "up"): 9, ("up", "mid"): 13, ("mid", "up"): 40, ("mid", "mid"): 30}) == {("mid", "up"), ("mid", "mid"), ("up", "up")}
    # Two faint diagonals crossing: only a link read at LINE_CONTRAST rules a crossing out, so both are taken.
    reads = {("up", "up"): 9, ("up", "mid"): 13, ("mid", "up"): 12, ("mid", "mid"): 10, ("mid", "down"): 0}
    assert mr.links(reads) == {("up", "mid"), ("mid", "up")}


# The map frames of tests/screens and the bus's top-left in each (MapBus matched with cv2, 0.97 and up).
MAP_SCREENS = {"MapBoss": (446, 248), "MapCards": (446, 248), "MapEvent": (446, 248), "MapFocused": (446, 248),
               "MapPanned": (446, 282), "MapRock": (446, 248), "MapShop": (446, 248), "MirrorMap": (446, 248)}


@pytest.mark.parametrize(("name", "bus"), MAP_SCREENS.items())
def test_the_faint_link_fallback_on_the_map_frames_of_tests_screens(name, bus):
    """CODING_STANDARDS' sweep of FAINT_LINK: every slot of every column on screen, node or not, as a node with
    no link read onward. Its one false link: MapBoss, from the empty middle slot behind the bus (a purple pack's
    glow, 11.9); read_ahead only reads on from nodes ahead of the bus. Slot centres: actions.SLOT (279, 37)."""
    v = brightness(name)
    x, y0, extra = (bus[0] + 279) % mr.COLUMN_DX, bus[1] + 37, {}
    while x + mr.COLUMN_DX + 80 <= 1200:
        reads = {(a, b): mr.line_contrast(v, x, y0 + mr.ROW_DY[a], x + mr.COLUMN_DX, y0 + mr.ROW_DY[b]) or 0
                 for a in mr.ROWS for b in mr.ROWS if mr.near(a, b)}
        if added := mr.links(reads) - {pair for pair, c in reads.items() if c >= mr.LINE_CONTRAST}:
            extra[x - bus[0]] = added
        x += mr.COLUMN_DX
    assert extra == ({-231: {("mid", "mid")}} if name == "MapBoss" else {})


def test_the_faint_links_between_events_of_a_diamond_read(context):
    # #212, live 2026-10-21 floor 4 (Full-Stopped by a Bullet): bus, a gift box node (maalc's abno then,
    # Focused by #91), two events above and two below, another. Column 2's lower event links on to column 3's along a faint line over a bright nebula (14.4);
    # it went unread, and the path stepped from it to column 3's upper event, two rows apart.
    # tests/data/map_f4_diamond.npz: that frame's per-pixel brightness, y 70-614, x 0-1179; bus at 48, 320.
    v = np.zeros((720, 1280), np.uint8)
    v[70:615, :1180] = np.load(Path(__file__).resolve().parent / "data/map_f4_diamond.npz")["v"]
    focused = {(327, 357), (1092, 357)}

    def run_recognition(name, image, override=None):
        if name in actions.MARKS:
            mark, (ox, oy, _, _) = actions.MARKS[name]
            x, y = override[name]["roi"][:2]
            return SimpleNamespace(hit=True, box=[x, y, 26, 24]) if mark in ("cost", "gift") and (x - ox, y - oy) in focused else None
        return None
    context.run_recognition.side_effect = run_recognition
    ahead = actions.RouteMap.read_ahead(context, v[..., None].repeat(3, axis=2), 48 + 279, 320 + 37, {"mid": ("focused", 2)})
    assert ahead == [{"up": ("event", {"mid"}), "down": ("event", {"mid"})}, {"up": ("event", {"up"}), "down": ("event", {"down"})},
                     {"mid": ("focused", {"up", "down"})}]
    score, path = mr.paths({"mid": ("focused", 2)}, NORMAL, ahead)["mid"]
    assert score == 10 and path[1] == path[2] and path[3] == "mid"  # focused, two events in one row, focused


def test_nothing_is_read_past_the_boss(context):
    # #279, live 2026-10-22 HARD floor 1 (campaign1): the boss in column 1, the bus beside it. Its red glow reads 12.4
    # towards the empty slot behind it (FAINT_LINK 8 to LINE_CONTRAST 15) and p90 38 there: a phantom event was read past the boss.
    # tests/data/map_boss_glow.npz: that frame's per-pixel brightness, y 56-614, x 250-699; the boss's centre at 327, 357.
    v = np.zeros((720, 1280), np.uint8)
    v[56:615, 250:700] = np.load(Path(__file__).resolve().parent / "data/map_boss_glow.npz")["v"]
    x, y = 327, 357
    assert mr.links({("mid", r): mr.line_contrast(v, x, y, x + mr.COLUMN_DX, y + dy) or 0 for r, dy in mr.ROW_DY.items()}) == {("mid", "mid")}  # the glow reads as a link
    context.run_recognition.side_effect = lambda name, image, override=None: None
    assert actions.RouteMap.read_ahead(context, v[..., None].repeat(3, axis=2), x, y, {"mid": ("boss", None)}) == []


def test_steps_are_rows_seen_from_the_node_before():
    assert mr.steps(["down", "mid", "mid"], ["battle", "battle", "event"]) == [("up", "battle"), ("mid", "event")]
    assert mr.steps(["mid"], ["abno"]) == []
    assert mr.steps(["mid", "down", "up"], ["abno", "event", "event"]) is None  # #212: no link joins two rows apart


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


@pytest.mark.parametrize(("shown", "floor"), [("Exploring Floor 3", 3), ("Exploring Floar 3", 3), ("Exploring Floor 10", 10), ("Exploring Floor 15", 15), ("Exploring Floor12", 12), ("Exploring Floar12", 12), ("Exploring Floor3", 3), ("Exploring", None), ("", None)])
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


def test_a_fresh_hard_map_that_cannot_pan_costs_no_extra_drags(context, clock):
    # A HARD floor's map shows two columns and does not pan (#129): its drags are not waited out.
    actions.RUN.update(fresh_floor=True, floor_hard=True)
    map_world(context, {(1, "mid"): {"cost"}}, [], bus_x=446)
    ctl = context.tasker.controller
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


def test_a_gift_window_that_comes_up_after_the_last_tap_is_not_taken_for_a_map_with_no_bus(context, monkeypatch):
    # #213 review: the window can rise while the last fallback tap waits for a node panel; "no bus on the map" went to L2.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    monkeypatch.setattr(actions, "map_weights", lambda context: AB_WEIGHTS)
    actions.RUN.update(map_entered=True, floor=3)
    # Missed by RouteMap's first look, the looks for a slot, search_bus's 5 drags and the 4 fallback taps' guards.
    gift_window_after(context, 1 + actions.MAP_LOOKS + 5 + 4 + 1)
    actions.RouteMap().run(context, None)
    assert context.tasker.controller.post_click.call_count == 4
    assert actions.STUCK["flag"] is None


def brightness(name):
    return np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB")).max(axis=2)


def test_a_drag_of_the_map_is_measured_on_the_frames_before_and_after_it():
    """#202, live 2026-10-22 NORMAL floor 4: the bus at the far left (48, 320), then two columns on (49, 320).

    Column 3 of MapFloor4.png (x 837) is column 1 of MapFloor4Panned.png (x 328): the map moved 509 px, give or
    take the bus match. The bus and the nodes behind it changed in between; the HUD stayed put."""
    assert abs(mr.shift(brightness("MapFloor4"), brightness("MapFloor4Panned"), 530) - 509) <= 3
    assert mr.shift(brightness("MapFloor4"), brightness("MapFloor4"), 530) == 0  # the map's edge: it did not move


def test_a_drag_that_cannot_be_measured_is_none():
    # Another map altogether (a pack's art over the whole screen changed): no shift stands out.
    assert mr.shift(brightness("MapFloor4"), brightness("MirrorMap"), 530) is None


def test_two_different_map_frames_never_measure_a_drag():
    """CODING_STANDARDS' sweep of SHIFT_CLEAR over every ordered pair of map frames in tests/screens.

    Only the live drag measures one. Four pairs of one theme pack's map at rest (MapBoss and MapFocused,
    MirrorMap and MapEvent, both ways; 0.2-0.54 of the median) read 0: the map did not move, so read_on stops."""
    names = [*MAP_SCREENS, "MapFloor4", "MapFloor4Panned", "GiftGetOverMap", "MapZoomed"]
    frames = {n: brightness(n) for n in names}
    moved = {(a, b): s for a in names for b in names if a != b and (s := mr.shift(frames[a], frames[b], 530))}
    assert moved.keys() == {("MapFloor4", "MapFloor4Panned")}


# #202: a NORMAL floor wider than the screen, read two columns per drag. Two rows run straight on: the first
# screen (columns 1-4) favours the top one (events), columns 5-6 the bottom one; then the shop and the boss.
WIDE = {**{(c, "up"): {"event"} for c in (1, 2, 3, 4)}, (5, "up"): {"cost", "gift"}, (6, "up"): {"cost", "gift"},
        **{(c, "down"): {"cost"} for c in (1, 2, 3, 4)}, (5, "down"): {"event"}, (6, "down"): {"event"},
        (7, "mid"): {"shop"}, (8, "mid"): {"boss"}}
WIDE_LINKS = [((c, r), (c + 1, r)) for c in range(1, 6) for r in ("up", "down")] + [((6, "up"), (7, "mid")), ((6, "down"), (7, "mid")),
                                                                                   ((7, "mid"), (8, "mid"))]
WIDE_WEIGHTS = {"event": 1, "battle": 2, "focused": 4, "shop": 0, "boss": 0, "unknown": 9}


def test_a_floor_wider_than_the_screen_is_read_two_columns_a_drag_and_planned_whole(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    actions.RUN["floor"] = 1
    offsets = map_world(context, WIDE, WIDE_LINKS, bus_x=446, width=2900)
    actions.RouteMap().run(context, None)
    # The bus to the far left, two drags of two columns on to the boss, then back to the bus. The fake map takes
    # each drag's 10 px threshold move too (actions.scroll): 520 px a drag, and back a little past where it was.
    assert [o - offsets[0] for o in offsets[:3]] == [0, 520, 1040] and abs(446 - offsets[-1] - actions.BUS_HOME[0]) <= 30
    # up: 4 events, 2 focused (12); down: 4 battles, 2 events (10). The first screen alone took the top row.
    assert context.tasker.controller.post_click.call_args_list[0].args == (446 - offsets[-1] + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] + 213)
    assert actions.RUN["map_plan"]["steps"] == [("mid", "battle")] * 3 + [("mid", "event")] * 2 + [("up", "shop"), ("mid", "boss")]
    assert "map: path down battle > down battle > down battle > down battle > down event > down event > mid shop > mid boss, score 10" in logs
    assert [line for line in logs if line.startswith("map: dragged")] == ["map: dragged the map 520 px; reading on from column 3", "map: dragged the map 520 px; reading on from column 5"]


def test_a_drag_that_moves_too_little_leaves_the_first_screens_read(context, monkeypatch):
    # The map's right edge two columns on: the first screen showed all there was to read; the plan is as before #202.
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    actions.RUN["floor"] = 1
    offsets = map_world(context, WIDE, WIDE_LINKS, bus_x=446, width=1800)
    actions.RouteMap().run(context, None)
    assert len(offsets) == 3 and abs(446 - offsets[-1] - actions.BUS_HOME[0]) <= 30  # to the far left, on to the edge, back
    assert context.tasker.controller.post_click.call_args_list[0].args == (446 - offsets[-1] + actions.SLOT[0], actions.BUS_HOME[1] + actions.SLOT[1] - 213)
    assert actions.RUN["map_plan"]["steps"] == [("mid", "event")] * 3


def test_a_drag_that_cannot_be_measured_leaves_the_first_screens_read(context, monkeypatch):
    # A drag whose frames match nowhere (a window over the map, a fade): what was read stands; the map goes back.
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    monkeypatch.setattr(mr, "shift", lambda *args: None)
    actions.RUN["floor"] = 1
    offsets = map_world(context, WIDE, WIDE_LINKS, bus_x=446, width=2900)
    actions.RouteMap().run(context, None)
    assert [o - offsets[0] for o in offsets] == [0, 520, 0]
    assert actions.RUN["map_plan"]["steps"] == [("mid", "event")] * 3


def test_the_cost_is_read_on_the_two_columns_next_to_the_bus_and_only_marks_beyond(context):
    """#238, live 2026-10-22 floor 4: column 3's Risky (Cost 120) and Abnormality (150) read from their marks as
    Focused; their WARNING rings were missed. Read near, as a drag brings them, their Cost types them."""
    def run_recognition(name, image, override=None):
        if name in ("MapNodeCost", "MapNodeGift"):
            return SimpleNamespace(hit=True, box=[*override[name]["roi"][:2], 26, 24])
        if name == "ReadText":
            return SimpleNamespace(all_results=[SimpleNamespace(text="120", box=(0, 0, 20, 20))])
        return None
    context.run_recognition.side_effect = run_recognition
    actions.RUN.update(settings={}, difficulty="normal", floor_hard=False)
    x, y = 50 + actions.SLOT[0], 320 + actions.SLOT[1]  # column 1 with the bus at the far left
    image = np.zeros((720, 1280, 3), np.uint8)
    for c in range(3):  # each row runs straight on through columns 2-4
        for dy in mr.ROW_DY.values():
            image[y + dy - 2:y + dy + 3, x + c * mr.COLUMN_DX:x + (c + 1) * mr.COLUMN_DX] = 200
    ahead = actions.RouteMap.read_ahead(context, image, x, y, {r: ("risky", 1) for r in mr.ROWS})
    assert [{r: t for r, (t, _) in c.items()} for c in ahead] == [dict.fromkeys(mr.ROWS, "risky")] + [dict.fromkeys(mr.ROWS, "focused")] * 2


def test_a_hard_floor_that_cannot_pan_is_not_dragged_on(context, monkeypatch):
    # #129: a HARD map stays at rest, its two columns ending at the screen's edge (980); read_on makes no drag.
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    actions.RUN.update(floor=1, floor_hard=True)
    map_world(context, {(1, "up"): {"event"}, (2, "up"): {"cost"}}, [((1, "up"), (2, "up"))], bus_x=446, width=1280)
    actions.RouteMap().run(context, None)
    assert "map: column 2: up battle (from up)" in logs
    assert not [line for line in logs if line.startswith(("map: a drag", "map: dragged"))]


def cost_reads(monkeypatch, offsets):
    """The map_world columns node_at reads, as (column, costs) pairs, the screen's offset on the map taken at each read."""
    node_at, reads = actions.node_at, []

    def read(context, image, cx, cy, marks=None, costs=True):
        reads.append(((cx + (offsets[-1] if offsets else 0) - 446 - actions.SLOT[0]) // mr.COLUMN_DX + 1, costs))
        return node_at(context, image, cx, cy, marks, costs)
    monkeypatch.setattr(actions, "node_at", read)
    return reads


@pytest.mark.parametrize("eaten", [(138, 0), (90, -10)], ids=["382 then 520 px", "430 then 530 px"])
def test_a_short_drag_still_brings_every_column_near_before_it_is_joined_on(context, monkeypatch, eaten):
    # Review of #239: a first drag that moves 382 px (the game ate part of it) left column 4 at x 712, read from its
    # marks; the next drag put it at 202, where it was joined on from, not read again. One of 430 px left it at 664,
    # and one of 530 px after it at 134. Every column reads its Cost.
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    actions.RUN["floor"] = 1
    offsets = map_world(context, WIDE, WIDE_LINKS, bus_x=446, width=3200)
    drags, scroll, reads = [], actions.scroll, cost_reads(monkeypatch, offsets)

    def short_first(context, x, y, dx, dy):
        drags.append(dx)
        scroll(context, x, y, dx + eaten[0] if len(drags) == 2 else dx + eaten[1] if len(drags) == 3 else dx, dy)
    monkeypatch.setattr(actions, "scroll", short_first)
    actions.RouteMap().run(context, None)
    assert {c for c, costs in reads if costs} >= set(range(1, 7))
    assert actions.RUN["map_plan"]["steps"][-2:] == [("up", "shop"), ("mid", "boss")]


@pytest.mark.parametrize("dark_from", [mr.COLUMN_DX + 60, 60], ids=["after column 3", "after column 2"])
def test_a_near_read_that_ends_short_keeps_the_columns_read_before(context, monkeypatch, dark_from):
    # #202's "never worse": a link unread up close ends the near read at its first column, or before it; the columns
    # the first screen read past it stay, and the floor is read on from them. Those kept near the bus read their Cost
    # there (review of #239: one was joined on from, its Cost never read; with no column read near, none was).
    monkeypatch.setattr(actions, "map_weights", lambda context: WIDE_WEIGHTS)
    actions.RUN["floor"] = 1
    offsets = map_world(context, WIDE, WIDE_LINKS, bus_x=446, width=2900)
    reads = cost_reads(monkeypatch, offsets)
    read_ahead = actions.RouteMap.read_ahead

    def near_read(context, image, x, y, before, first=2):
        if first == 3:  # the frame dark past the node: no link onward reads
            image = image.copy()
            image[:, x + dark_from:] = 0
        return read_ahead(context, image, x, y, before, first)
    monkeypatch.setattr(actions.RouteMap, "read_ahead", staticmethod(near_read))
    actions.RouteMap().run(context, None)
    assert actions.RUN["map_plan"]["steps"] == [("mid", "battle")] * 3 + [("mid", "event")] * 2 + [("up", "shop"), ("mid", "boss")]
    assert {c for c, costs in reads if costs} >= set(range(1, 7))


def shop_world(context, monkeypatch, nodes, links=(((1, "mid"), (2, "mid")),), **run):
    """A fresh floor 1 map, the bus at the far left, run once; the log lines it wrote. run: more of RUN's keys."""
    monkeypatch.setattr(actions, "map_weights", lambda context: {**NORMAL, "shop": 0, "boss": 0})
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    actions.RUN.update(floor=1, **run)
    map_world(context, nodes, list(links), bus_x=actions.BUS_HOME[0])
    actions.RouteMap().run(context, None)
    return logs


def test_a_dark_boss_after_the_shop_is_the_boss_by_position(context, monkeypatch):
    # #279: 722-850 red pixels on a dark boss, 842 on a node that is none; the shop (a shape, #146) says where it is.
    logs = shop_world(context, monkeypatch, {(1, "mid"): {"shop"}, (2, "mid"): set()})
    assert "map: column 2: after the shop, so the boss; mid read as something else" in logs
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": [("mid", "boss")]}
    assert any(line.startswith("map: path mid shop > mid boss") for line in logs)


def test_a_boss_read_by_its_glow_after_the_shop_needs_no_log(context, monkeypatch):
    logs = shop_world(context, monkeypatch, {(1, "mid"): {"shop"}, (2, "mid"): {"boss"}})
    assert not [line for line in logs if "after the shop" in line or "glow" in line]
    assert actions.RUN["map_plan"] == {"floor": 1, "steps": [("mid", "boss")]}


def test_the_boss_reads_alone_when_no_shop_stands_before_it(context, monkeypatch):
    # The glow still counts (#279), the node before it is not made a shop; the two readings disagree: one line.
    logs = shop_world(context, monkeypatch, {(1, "mid"): set(), (2, "mid"): {"boss"}})
    assert "map: column 2: the boss' glow without a shop before it" in logs
    assert any(line.startswith("map: path mid event > mid boss") for line in logs)


def test_nothing_is_read_past_the_column_after_the_shop(context, monkeypatch):
    # The boss column is the last: a column read past it (its glow makes a faint link, see above) is never read.
    logs = shop_world(context, monkeypatch, {(1, "mid"): {"shop"}, (2, "mid"): set(), (3, "mid"): {"cost"}},
                      links=(((1, "mid"), (2, "mid")), ((2, "mid"), (3, "mid"))))
    assert not [line for line in logs if line.startswith("map: column 3")]


def test_left_the_shop_the_only_node_is_the_boss(context, monkeypatch):
    # #279: HARD, the page handled last was the shop: the bus's one slot is the boss, however dark it reads.
    # ADR 0003: the fact comes from the screen handled (Shop.run), memory only; a restarted agent reads the colour.
    logs = shop_world(context, monkeypatch, {(1, "mid"): set()}, links=(), after_shop=True, floor_hard=True)
    assert "map: left the shop; column 1 mid read as something else than the boss" in logs
    assert any(line.startswith("map: path mid boss") for line in logs)
    assert "after_shop" not in actions.RUN  # entering the node ends it


def test_left_the_shop_a_boss_read_by_its_glow_is_logged_as_agreeing(context, monkeypatch):
    logs = shop_world(context, monkeypatch, {(1, "mid"): {"boss"}}, links=(), after_shop=True, floor_hard=True)
    assert "map: left the shop; column 1 is the boss" in logs


def test_without_the_shop_behind_it_a_dark_boss_in_the_first_column_reads_as_it_looks(context, monkeypatch):
    # No page memory (a restart, ADR 0003): the colour alone decides, the old behaviour.
    logs = shop_world(context, monkeypatch, {(1, "mid"): set()}, links=(), floor_hard=True)
    assert any(line.startswith("map: path mid event") for line in logs)


def test_a_planned_boss_after_the_shop_is_followed_whatever_it_reads(context, monkeypatch):
    # follow() types the planned node again; the dark boss reads as an event, so the plan was dropped and the map read again.
    monkeypatch.setattr(actions, "map_weights", lambda context: {**NORMAL, "boss": 0})
    actions.RUN.update(floor=1, after_shop=True, map_plan={"floor": 1, "steps": [("mid", "boss")]})
    map_world(context, {(1, "mid"): set()}, [], bus_x=446)
    assert actions.RouteMap.follow(context)
    context.tasker.controller.post_touch_down.assert_not_called()  # followed: no drag for a full read
    assert actions.RUN["map_plan"]["steps"] == []


def test_a_boss_told_by_the_shop_is_not_typed_again_by_its_cost(context):
    # #279: read_on types the columns now near again (retype); a dark boss reads as an event on its own.
    context.run_recognition.side_effect = lambda name, image, override=None: None
    column = {"mid": ("boss", {"mid"}), "up": ("abno", {"mid"})}
    actions.RouteMap.retype(context, np.zeros((720, 1280, 3), np.uint8), column, 400, 357, 3)
    assert column == {"mid": ("boss", {"mid"}), "up": ("event", {"mid"})}


@pytest.mark.parametrize(("before", "expected"), [
    ({"mid": ("shop", 1)}, [{"mid": ("boss", {"mid"})}]),  # a boss as dark as hard mode's dark columns: still the boss
    ({"mid": ("event", 1)}, []),  # no shop before it: a dark column ends the read as ever
])
def test_a_dark_column_after_a_shop_is_still_the_boss(context, before, expected):
    # #279: no mark and no light (p90 under 20) around it, only the link into it: `lit` alone would end the read there.
    context.run_recognition.side_effect = lambda name, image, override=None: None
    x, y = 50 + actions.SLOT[0], 320 + actions.SLOT[1]
    image = np.zeros((720, 1280, 3), np.uint8)
    image[y - 2:y + 3, x:x + mr.COLUMN_DX] = 200  # the link, 5 px wide
    assert actions.RouteMap.read_ahead(context, image, x, y, before) == expected
