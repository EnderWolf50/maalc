from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

import map_route as mr

SCREENS = Path(__file__).resolve().parent / "screens"

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


# The map frames of tests/screens and the bus's top-left in each (MapBus matched with cv2, 0.97 and up).
MAP_SCREENS = {"MapBoss": (446, 248), "MapCards": (446, 248), "MapEvent": (446, 248), "MapFocused": (446, 248),
               "MapPanned": (446, 282), "MapRock": (446, 248), "MapShop": (446, 248), "MirrorMap": (446, 248)}


@pytest.mark.parametrize(("name", "bus"), MAP_SCREENS.items())
def test_the_faint_link_fallback_on_the_map_frames_of_tests_screens(name, bus):
    """CODING_STANDARDS' sweep of FAINT_LINK: every slot of every column on screen, node or not, as a node with
    no link read onward. Its one false link: MapBoss, from the empty middle slot behind the bus (a purple pack's
    glow, 11.9); read_ahead only reads on from nodes ahead of the bus. Slot centres: actions.SLOT (279, 37)."""
    v = np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB")).max(axis=2)
    x, y0, extra = (bus[0] + 279) % mr.COLUMN_DX, bus[1] + 37, {}
    while x + mr.COLUMN_DX + 80 <= 1200:
        reads = {(a, b): mr.line_contrast(v, x, y0 + mr.ROW_DY[a], x + mr.COLUMN_DX, y0 + mr.ROW_DY[b]) or 0
                 for a in mr.ROWS for b in mr.ROWS if mr.near(a, b)}
        if added := mr.links(reads) - {pair for pair, c in reads.items() if c >= mr.LINE_CONTRAST}:
            extra[x - bus[0]] = added
        x += mr.COLUMN_DX
    assert extra == ({-231: {("mid", "mid")}} if name == "MapBoss" else {})


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
