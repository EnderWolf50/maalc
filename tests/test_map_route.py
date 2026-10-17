from pathlib import Path

import numpy as np
import pytest
import yaml

import map_route as mr

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
    ({"gift"}, "unknown"),
    (set(), "unknown"),
])
def test_node_type(marks, expected):
    assert mr.node_type(marks) == expected


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


def test_an_unmarked_node_beyond_the_first_column_scores_as_an_event():
    # MapPanned.png: the "?" two columns out is too dim for its template; fights carry a lit Cost coin.
    ahead = [{"up": ("unknown", {"up"}), "down": ("abno", {"down"})}]
    assert mr.rank({"up": ("battle", 1), "down": ("event", 1)}, HARD, ahead) == ["up", "down"]


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
