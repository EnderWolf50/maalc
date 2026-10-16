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


def section_headers(image):
    """Section headers on screen as [(y, tier)] top to bottom: y is their numerals' centre.

    A header is a blue band 24-25 px tall across the grid with its tier's 1-3 yellow numerals at its left,
    12 px above its centre line (live 2026-10-16); a band cut by the grid's edge is skipped.
    """
    b, g, r = (image[GRID_Y[0]:GRID_Y[1], :, i].astype(int) for i in range(3))
    band = (b[:, 300:700] - r[:, 300:700]).mean(axis=1) > 40
    yellow = (r > 200) & (g > 150) & (b < 80)
    out = []
    for top, run in _runs(np.flatnonzero(band)):
        bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))
        if 22 <= run <= 27 and 1 <= bars <= 3:
            out.append((GRID_Y[0] + top + 12, bars))
    return out


HEADER_Y = 252  # the first section header with the tab scrolled to the top
HEADER_TO_ROW = 61  # header -> its first row, and a section's last row -> the next header
ROW = 78.7


def expected_cell(tab, name):
    """Screen (x, y) of a gift with its tab scrolled to the top, from the observation table's order; y may be
    below the grid. tab: the tab's gifts in table order ({"en", "tier"}). None when name is not in it.

    The table order is the page order (checked cell by cell live). A gift this account lacks shifts every
    later cell of its section by one: the icon match confirms the place.
    """
    tier = next((g["tier"] for g in tab if g["en"] == name), None)
    if tier is None:
        return None
    row, col = divmod([g["en"] for g in tab if g["tier"] == tier].index(name), 8)
    return CELL_X[col], round(_header_ys(tab)[tier] + HEADER_TO_ROW + ROW * row)


def cell_y(tab, name, headers):
    """Screen y of name's row now, from the section headers on screen (section_headers); None without one.

    Measured from its own section's header when that is on screen, so a gift the account lacks in an
    earlier section does not shift it; else from the first header and the table's section sizes.
    """
    tops = _header_ys(tab)
    headers = [h for h in headers if h[1] in tops]
    if not headers:
        return None
    tier = next(g["tier"] for g in tab if g["en"] == name)
    y, t = next((h for h in headers if h[1] == tier), headers[0])
    return expected_cell(tab, name)[1] - round(tops[t]) + y


def _header_ys(tab):
    """{tier: its header's y} with the tab scrolled to the top, from the table's section sizes."""
    ys, y = {}, HEADER_Y
    for tier in (3, 2, 1):
        n = sum(g["tier"] == tier for g in tab)
        if n:
            ys[tier] = y
            y += 2 * HEADER_TO_ROW + ROW * (-(-n // 8) - 1)
    return ys


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
