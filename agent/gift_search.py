"""E.G.O Gift Search decisions, free of MaaFramework (docs/spec/03-decisions.md section 5).

actions.py taps and reads the page; everything here is plain data or a screenshot array in, plain data out.
"""

import re

import numpy as np

# The gift grid (live 2026-10-16, 1.117.0): 8 columns, rows 80 px apart, sections III, II, I top to bottom.
# Each cell has its tier as 1-3 yellow bars at its top-left; an Owned cell is greyed and shows none.
CELL_X = [130 + round(83.4 * c) for c in range(8)]
GRID_Y = (228, 625)
LAST_Y = 600  # lowest cell centre still inside the grid


def gift_cells(image):
    """Selectable cells [(x, y, tier)] in reading order: a run of 16-22 yellow rows left of each column.

    Section headers carry the same numerals, 14 px tall; an Owned gift has no yellow bars.
    """
    b, g, r = (image[GRID_Y[0]:GRID_Y[1], :, i].astype(int) for i in range(3))
    yellow = (r > 200) & (g > 150) & (b < 80)
    cells = []
    for x in CELL_X:
        strip = yellow[:, x - 34:x - 8]
        rows = np.flatnonzero(strip.any(axis=1))
        for top, run in _runs(rows):
            y = GRID_Y[0] + top + 31
            if 16 <= run <= 22 and y <= LAST_Y:
                bars = len(_runs(np.flatnonzero(strip[top + run // 2])))
                if 1 <= bars <= 3:
                    cells.append((x, y, bars))
    return sorted(cells, key=lambda c: (c[1] // 40, c[0]))


HEADER_Y = 252  # the first section header with the tab scrolled to the top
HEADER_TO_ROW = 61  # header -> its first row, and a section's last row -> the next header
ROW = 78.7


def expected_cell(tab, name):
    """Screen (x, y) of a gift with its tab scrolled to the top, from the observation table's order; y may be
    below the grid. tab: the tab's gifts in table order ({"en", "tier"}). None when name is not in it.

    The table order is the page order (checked cell by cell live). A gift this account lacks shifts every
    later cell of its section by one: the icon match confirms the place.
    """
    y = HEADER_Y
    for tier in (3, 2, 1):
        section = [g["en"] for g in tab if g["tier"] == tier]
        if not section:
            continue
        if name in section:
            row, col = divmod(section.index(name), 8)
            return CELL_X[col], round(y + HEADER_TO_ROW + ROW * row)
        y += 2 * HEADER_TO_ROW + ROW * (-(-len(section) // 8) - 1)
    return None


def next_gift(wanted, chosen, tried, count):
    """The next of the team's gifts to look for, in the user's order, or None.

    chosen: names the Selected E.G.O Gift panel lists; tried: gifts looked for already (found or not);
    count: Select n/m. Nothing more once n == m: the list is a priority order, not a quota.
    """
    n, m = count
    if n >= m:
        return None
    return next((gift for gift in wanted if gift not in tried and gift["name"] not in chosen), None)


def select_count(text):
    """(n, m) of "Select n/m", or None."""
    found = re.search(r"(\d+)\s*/\s*(\d+)", text)
    return (int(found[1]), int(found[2])) if found else None


def owned_starlight(left, right):
    """(owned, price, left over) from the Owned box's "1315-270" and "1045", or None when they do not add up."""
    found = re.search(r"(\d+)\s*-\s*(\d+)", left)
    after = re.sub(r"\D", "", right)
    if not found or not after:
        return None
    owned, price = int(found[1]), int(found[2])
    return (owned, price, int(after)) if owned - price == int(after) else None


def _runs(values):
    """[(start, length)] of the consecutive stretches in a sorted int array."""
    if not len(values):
        return []
    breaks = np.flatnonzero(np.diff(values) != 1)
    starts = np.r_[values[0], values[breaks + 1]]
    ends = np.r_[values[breaks], values[-1]]
    return list(zip(starts.tolist(), (ends - starts + 1).tolist()))
