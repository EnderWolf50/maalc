import numpy as np

import gift_search as g

YELLOW = (0, 195, 249)  # BGR of a tier bar (live 2026-10-16)


def grid(*marks, height=19):
    """A dark 1280x720 screen with tier bars: (column, bar top y, tier) per gift."""
    image = np.full((720, 1280, 3), (40, 30, 160), np.uint8)
    for col, top, tier in marks:
        x = g.CELL_X[col] - 30
        for k in range(tier):
            image[top:top + height, x + 6 * k:x + 6 * k + 3] = YELLOW
    return image


def test_gift_cells_from_tier_bars_in_reading_order():
    image = grid((1, 281, 3), (0, 281, 3), (0, 481, 2), (7, 560, 1))
    assert g.gift_cells(image) == [(g.CELL_X[0], 312, 3), (g.CELL_X[1], 312, 3), (g.CELL_X[0], 512, 2), (g.CELL_X[7], 591, 1)]


def test_gift_cells_skip_section_headers_and_cut_cells():
    # A section header's numeral is shorter (14 px); a cell scrolled half under the grid's edge has no full bars.
    image = grid((0, 245, 3), height=14)
    image[600:620, g.CELL_X[2] - 30:g.CELL_X[2] - 27] = YELLOW  # bars running into the grid's bottom edge
    assert g.gift_cells(image) == []


SMOKES = {"keyword": "Bleed", "tier": 3, "name": "Smokes and Wires"}
BASS = {"keyword": "Bleed", "tier": 2, "name": "Walking Bass"}
STAKE = {"keyword": "Bleed", "tier": 1, "name": "Grimy Iron Stake"}


def test_next_gift_follows_the_users_order():
    assert g.next_gift([SMOKES, BASS, STAKE], chosen=[], tried=[], count=(0, 3)) == SMOKES
    assert g.next_gift([SMOKES, BASS, STAKE], chosen=["Smokes and Wires"], tried=[SMOKES], count=(1, 3)) == BASS


def test_next_gift_skips_what_is_already_selected_or_was_not_found():
    # Selected before (an action run again on the same page): the panel lists it.
    assert g.next_gift([SMOKES, BASS], chosen=["Smokes and Wires"], tried=[], count=(1, 3)) == BASS
    # Not on the page or not affordable: tried once, never again.
    assert g.next_gift([SMOKES, BASS, STAKE], chosen=[], tried=[SMOKES, BASS], count=(0, 3)) == STAKE
    assert g.next_gift([SMOKES], chosen=[], tried=[SMOKES], count=(0, 3)) is None


def test_next_gift_stops_when_select_is_full():
    # Select 1/1: the rest of the list is left.
    assert g.next_gift([SMOKES, BASS], chosen=["Smokes and Wires"], tried=[SMOKES], count=(1, 1)) is None
    assert g.next_gift([SMOKES, BASS], chosen=[], tried=[], count=(3, 3)) is None


def test_select_count():
    assert g.select_count("Select 0/3") == (0, 3)
    assert g.select_count("Select 2 / 3") == (2, 3)
    assert g.select_count("Select") is None


def test_owned_starlight_before_and_after():
    # The Owned box reads "1315 -270 > 1045": owned, the selection's price, what is left.
    assert g.owned_starlight("1315-270", "1045") == (1315, 270, 1045)
    assert g.owned_starlight("1315-0", "1315") == (1315, 0, 1315)
    assert g.owned_starlight("1315-270", "1046") is None  # misread: the numbers must add up
    assert g.owned_starlight("", "1315") is None
