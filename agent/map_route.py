"""Map routing decisions, free of MaaFramework (docs/spec/03-decisions.md section 7).

actions.RouteMap reads the marks with pipeline nodes and taps; everything here is plain data in,
plain data out, plus the link reading, which works on the screenshot array.
"""

import numpy as np

# Rows of the column next to the bus. The order is also the tie-break when links cannot be
# read: middle row first, then the top row (spec 03 section 7).
ROWS = ("mid", "up", "down")
ROW_DY = {"up": -213, "mid": 0, "down": 213}  # node centres, 720p
COLUMN_DX = 255
LINE_CONTRAST = 15  # live: drawn links 22-173, no link -14-4
# A node with no link read onward takes its brightest one from this (#212): faint links over a bright
# background read 13-14.4, the background alone up to 12.5 (a purple pack's grid), so no one bar parts them.
FAINT_LINK = 8


def node_type(marks):
    """The node type for the set of marks seen on a slot.

    boss: red glow; focused: WARNING ring; abno: Cost coin and gift box; battle: Cost coin alone.
    Only the icons count, never the Cost number (spec 03 section 7). Every fight carries a lit Cost coin,
    so a node with none and no shop mark is an event, matched or not: its "?" takes the theme pack's look
    (live 2026-10-18, a bright cyan one missed every template) and dims with distance (MapPanned.png).
    """
    if "boss" in marks:
        return "boss"
    if "focused" in marks:
        return "focused"
    if "cost" in marks:
        return "abno" if "gift" in marks else "battle"
    return "shop" if "shop" in marks else "event"


def shop_before_boss(slots, ahead):
    """Type every node of the column right before the boss's as a shop, in place (#146).

    The map's last column is the shop, then the boss: no node pool holds a shop (mirrordungeon-generatenodepool:
    battle, abnormality, hard battle, event, boss), and in every capture showing the boss with a node before it,
    that node is the shop (spec 03 section 7). Its icon takes the theme pack's colours, so its mark is not trusted.
    slots and ahead are rank's: columns of row -> (node type, ...).
    """
    columns = [slots, *ahead]
    for before, after in zip(columns, columns[1:]):
        if any(node == "boss" for node, _ in after.values()):
            for row, (_, rest) in before.items():
                before[row] = ("shop", rest)


def rank(slots, weights, ahead=()):
    """Rows of the linked slots, best first.

    slots maps row -> (node type, routes onward or None); ahead lists the columns read beyond them,
    each row -> (node type, rows of the column before it linked to that node). A slot scores the
    weights on its cheapest path through those columns, lowest first; a node with no link read
    onward goes on as if linked to the cheapest node of the next column in a row next to its own (paths).
    With no column ahead the score is the slot's own weight. On equal score the node with more routes into the next column;
    then middle, top, bottom. The boss only when it is the only linked node.
    """
    best = paths(slots, weights, ahead)
    rows = [r for r in slots if slots[r][0] != "boss"] or list(slots)
    return sorted(rows, key=lambda r: (best[r][0], -(slots[r][1] or 0), ROWS.index(r)))


def paths(slots, weights, ahead=()):
    """row -> (score, rows of the cheapest path from that slot, one per column) for each slot; see rank.

    Only rows next to each other link (#212): with no link read onward, a node goes on to the cheapest node
    of a row next to its own; with none there, the cheapest of the column still scores but the path ends.
    """
    best = {}  # the same for the nodes of the column after the one being scored
    for column, after in reversed(list(zip((slots, *ahead), (*ahead, {})))):
        nxt, best = best, {}
        for r, (node, _) in column.items():
            linked = [nxt[u] for u in nxt if r in after[u][1]]
            close = [nxt[u] for u in nxt if near(r, u)]
            score, path = min(linked or close or [(s, []) for s, _ in nxt.values()] or [(0, [])])
            best[r] = (weights.get(node, weights["unknown"]) + score, [r, *path])
    return best


def near(a, b):
    """Whether rows a and b are the same or next to each other: only those link (#212)."""
    return abs(ROW_DY[a] - ROW_DY[b]) <= ROW_DY["down"]


def links(reads):
    """The links between two columns, as (row before, row) pairs, from reads: pair -> line_contrast (0 if unread).

    A pair reading LINE_CONTRAST links. Every node leads on (#212), so a row before with none takes its
    brightest pair when it reads FAINT_LINK, but not a diagonal that a link read the other way crosses:
    the crossing alone reads 11.9-14.2 (the bus's links in tests/screens), as high as a faint link. A real faint
    diagonal crossed so is lost too; the path then goes on as paths says. reads covers every row of both columns
    (read_ahead keeps the pairs from its nodes), so a crossing from a node not read still counts.
    """
    read = {pair for pair, c in reads.items() if c >= LINE_CONTRAST}
    found = set(read)
    for src in {src for src, _ in reads} - {src for src, _ in read}:
        c, pair = max((c, (a, b)) for (a, b), c in reads.items() if a == src and (b, a) not in read)
        if c >= FAINT_LINK:
            found.add(pair)
    return found


def steps(path, nodes):
    """The rest of a path as (row seen from the node before, node type): where the bus will stand.

    None when a step joins rows two apart, which no link does (#212): no plan to follow.
    """
    row_at = {dy: r for r, dy in ROW_DY.items()}
    out = [(row_at.get(ROW_DY[b] - ROW_DY[a]), t) for a, b, t in zip(path, path[1:], nodes[1:])]
    return None if any(r is None for r, _ in out) else out


def line_contrast(v, x0, y0, x1, y1, top=56, bottom=615):
    """How much brighter the straight segment between two node centres is than either side of it.

    v is the screenshot's per-pixel brightness (max over channels). Only the middle 40 % is read,
    clear of the nodes and their badges. None when that part is mostly off the readable map area
    (the resource bar above y 56, its lower edge at about 58; the sinner bar below 615).
    """
    n = np.array([y0 - y1, x1 - x0], float)
    n /= np.linalg.norm(n)
    ts = np.linspace(0.3, 0.7, 25)

    def mean(off):
        xs = (x0 + (x1 - x0) * ts + n[0] * off).astype(int)
        ys = (y0 + (y1 - y0) * ts + n[1] * off).astype(int)
        ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)
        return float(v[ys[ok], xs[ok]].mean()) if ok.mean() > 0.6 else None

    on = [mean(o) for o in range(-4, 5, 2)]  # links are ~5 px wide; the centre may be off by a few
    sides = mean(13), mean(-13)
    if None in on or None in sides:
        return None
    return max(on) - max(sides)


def routes(v, cx, cy):
    """Links from the node at (cx, cy) into the next column, or None when none could be read."""
    seen = [line_contrast(v, cx, cy, cx + COLUMN_DX, cy + dy) for dy in ROW_DY.values()]
    seen = [c for c in seen if c is not None]
    return sum(c >= LINE_CONTRAST for c in seen) if seen else None
