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
SHIFT_CLEAR = 0.6  # shift: the best shift's difference, at most this share of the median (a drag 0.46, other maps 0.77+)


def node_type(marks, by_cost=None):
    """The node type for the set of marks seen on a slot, and the fight's kind its Cost number gives, if read.

    boss: red glow. A fight (Cost coin or WARNING ring) is by_cost when given (#91): the ring and the gift box
    are often missed live. Else by its marks: the ring is Risky's or Abnormality's, taken for the later, risky;
    a gift box with no ring is Focused's; the Cost coin alone a battle. Every fight carries a lit Cost coin,
    so a node with none and no shop mark is an event, matched or not: its "?" takes the theme pack's look
    (live 2026-10-18, a bright cyan one missed every template) and dims with distance (MapPanned.png).
    """
    if "boss" in marks:
        return "boss"
    if "cost" in marks or "ring" in marks:
        if by_cost:
            return by_cost
        if "ring" in marks:
            return "risky"
        return "focused" if "gift" in marks else "battle"
    return "shop" if "shop" in marks else "event"


def boss_after_shop(before, column):
    """Type every node of column, the one right after before's, as the boss when before holds a shop, in place (#279).

    The map's last two columns are the shop, then the boss, one node each (22 floors read; the game data's
    fixedEncounters target sector -2). The shop is told by its shape (actions.shop_icon: 0.47-1.0 on the shops
    it finds, 0.32 at most on any other slot of 111 captures); the boss' red glow is not: 722-850 red pixels on a
    dark one against 842 on a node that is not the boss.
    So the shop decides and the glow only helps (a node reading as the boss stays one). Both columns are rank's:
    row -> (node type, ...). Returns the rows whose type it changed.
    """
    if not any(node == "shop" for node, _ in before.values()):
        return []
    changed = [row for row, (node, _) in column.items() if node != "boss"]
    for row, (_, rest) in column.items():
        column[row] = ("boss", rest)
    return changed


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


def shift(before, after, most, top=230, bottom=600, right=1200):
    """How many px (0 to most) a drag moved the map leftward between two frames' brightness, or None when unclear (#202).

    The shift where the map band (below the floor's title, above the sinner bar, left of the buttons) differs least,
    every 4th row. Live 2026-10-22 (MapFloor4*.png, a drag of two columns): 0.46 of the median over all shifts; two
    different maps of tests/screens 0.77-0.88. A still HUD part only adds a little to every shift.
    """
    a, b = (f[top:bottom:4, :right].astype(np.int16) for f in (before, after))
    errs = np.array([np.abs(a[:, s:] - b[:, :right - s]).mean() for s in range(most + 1)])
    s = int(errs.argmin())
    return s if errs[s] < SHIFT_CLEAR * np.median(errs) else None


def routes(v, cx, cy):
    """Links from the node at (cx, cy) into the next column, or None when none could be read."""
    seen = [line_contrast(v, cx, cy, cx + COLUMN_DX, cy + dy) for dy in ROW_DY.values()]
    seen = [c for c in seen if c is not None]
    return sum(c >= LINE_CONTRAST for c in seen) if seen else None
