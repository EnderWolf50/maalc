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


def test_unknown_last_and_risky_after_shop_on_hard():
    slots = {"up": ("unknown", 3), "mid": ("shop", 1), "down": ("focused", 0)}
    assert mr.rank(slots, NORMAL) == ["down", "mid", "up"]
    assert NORMAL["risky"] < NORMAL["shop"] < HARD["risky"] < HARD["unknown"]
    assert {k: v for k, v in NORMAL.items() if k != "risky"} == {k: v for k, v in HARD.items() if k != "risky"}


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
