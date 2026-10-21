"""#205: the fuse and sell pages' owned grids are scrolled to read their cut-off rows; no cell is opened to read it."""
from types import SimpleNamespace

import numpy as np
import pytest

import actions
import test_actions
from test_shop import screen_with

clock, context = test_actions.clock, test_actions.context  # its fixtures
DONE = SimpleNamespace(wait=lambda: None)
# Live 2026-10-21: a sell grid of 13 gifts scrolls 31 px, its last row's price just inside; the fuse page's end is a guess.
END = {"fuse": 56, "sell": 495 + 31 - 472}
TOP = {"fuse": 200, "sell": 215}  # the lists' upper edge (live: the fuse page's label at 216-240, sell rows cut at 215)
KEYWORDS = ["Bleed", "Tremor", "Pierce", "Sinking", "Slash", "Blunt", "Poise", "Rupture", "Charge"]


class Grid:
    """The owned grid of page as the game shows it: n gifts, 5 a row, each a unique icon in the same frame. A drag
    moves it by the finger's travel after the drag threshold's first move (1 px more every other drag: the fling
    left, or fling px more each drag; or only share of it), stopped at its ends; a tap lands on the gift under it. The
    grid ends END px under its last row's centre. On the fuse page OCR reads the "E.G.O Gifts Owned" label over the gifts
    where it shows; recipes: a section of that many cells over it (a fixed recipe's Fusion Available), each a gift
    of its own, its label as tall as the owned gifts'."""

    def __init__(self, context, page, n, fling=None, share=1.0, recipes=0):
        (self.x0, self.y0), (self.dx, self.dy), _ = actions.OWNED_GRID[page]
        self.page, self.above = page, (1 + (recipes - 1) // 5) * self.dy + actions.OWNED_LABEL if recipes else 0
        self.recipes = [(self.x0 + self.dx * (k % 5), self.y0 + self.dy * (k // 5)) for k in range(recipes)]
        self.top, self.bottom = TOP[page], actions.CELL_PAGES[page][1]
        self.max_at = max(0, self.y0 + self.above + self.dy * ((n - 1) // 5) + END[page] - self.bottom)
        self.at, self.drags, self.taps, self.reads, self.fling, self.share = 0, 0, [], [], fling, share
        rng = np.random.default_rng(1)
        self.icons = [np.kron(rng.integers(40, 255, (19, 19, 3), np.uint8), np.ones((4, 4, 1), np.uint8))
                      for _ in range(n + recipes)]
        for icon in self.icons:
            icon[:5], icon[-5:], icon[:, :5], icon[:, -5:] = (0, 200, 230), (0, 200, 230), (0, 200, 230), (0, 200, 230)
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.screen
        ctl.post_touch_down.side_effect = self.down
        ctl.post_touch_move.side_effect = self.move
        ctl.post_touch_up.side_effect = self.up
        ctl.post_click.side_effect = self.click

    def place(self, i):
        """Gift i's centre with the grid at its top (the recipe cells' after the owned gifts')."""
        n = len(self.icons) - len(self.recipes)
        return self.recipes[i - n] if i >= n else (self.x0 + self.dx * (i % 5), self.y0 + self.above + self.dy * (i // 5))

    def recognition(self, name, image, override=None):
        """OCR of FUSE_LIST: the owned gifts' label, where it shows whole on the fuse page; None for anything else."""
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        y = self.y0 + self.above - actions.OWNED_LABEL - self.at
        if self.page != "fuse" or roi != tuple(actions.FUSE_LIST) or not self.top <= y - 12 <= y + 12 <= self.bottom:
            return None
        return SimpleNamespace(all_results=[SimpleNamespace(text="E.G.O Gifts Owned", box=(635, y - 12, 161, 24))])

    def at_screen(self, x, y):
        """The gift whose cell is under (x, y) on screen now, or None."""
        return next((i for i in range(len(self.icons)) if abs(self.place(i)[0] - x) < 38
                     and abs(self.place(i)[1] - self.at - y) < 38 and self.top <= y < self.bottom), None)

    def screen(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        for i, icon in enumerate(self.icons):
            x, y = self.place(i)
            y -= self.at
            lo, hi = max(y - 38, self.top), min(y + 38, self.bottom)
            if lo < hi:
                image[lo:hi, x - 38:x + 38] = icon[lo - y + 38:hi - y + 38]
        return image

    def down(self, x, y):
        assert self.top <= y <= self.bottom, "a drag starts inside the grid"
        self.moves = []
        return DONE

    def move(self, x, y):
        self.moves.append(y)
        return DONE

    def up(self):
        self.drags += 1
        fling = self.drags % 2 if self.fling is None else self.fling
        self.at = min(max(self.at + round((self.moves[0] - self.moves[-1]) * self.share) + fling, 0), self.max_at)
        return DONE

    def click(self, x, y):
        i = self.at_screen(x, y)
        self.taps.append((x, y) if i is None else i)
        return DONE

    def read_cells(self, context, image, cells, page, gifts=()):
        """actions.read_cells as the badge and icon matching would: each gift's keyword, by the gift on screen there.
        Only cells shown whole are asked for (test_shop_cells checks the matching itself)."""
        out = []
        for k, (x, y) in enumerate(cells):
            assert actions.whole(page, y) and y - 38 >= self.top, (x, y)  # its frame shows whole
            i = self.at_screen(x, y)
            assert i is None or i < len(self.icons) - len(self.recipes), f"a recipe cell read as an owned gift at {x, y}"
            if i is not None:
                self.reads.append(i)
                out.append({"i": k, "x": x, "y": y, "tier": 1, "keyword": KEYWORDS[i % len(KEYWORDS)], "gift": None})
        return out


@pytest.fixture
def grid(context, monkeypatch):
    def make(page, n, fling=None, share=1.0, recipes=0):
        g = Grid(context, page, n, fling, share, recipes)
        monkeypatch.setattr(actions, "read_cells", g.read_cells)
        context.run_recognition.side_effect = g.recognition
        return g
    return make


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("n", [3, 10, 13, 20, 23, 31])
def test_every_gift_is_read_once_whatever_the_grid_holds(context, grid, monkeypatch, page, n):
    # Two rows a drag, the first cut-off one to the first's place; the last drag stops at the grid's end. A last row
    # full at the end takes one drag more: it might be a drag the game took less of. The sell page is first dragged to
    # its top (a drag that does not move it here).
    g = grid(page, n)
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    cells, _ = actions.owned_cells(context, g.screen(), page, [])
    assert g.reads == list(range(n))  # each gift once, in the grid's order
    assert (f"shop: the {page} grid does not move: at its end" in logs) == (n == 20)
    assert [c["i"] for c in cells] == list(range(n))
    assert [c["keyword"] for c in cells] == [KEYWORDS[i % len(KEYWORDS)] for i in range(n)]
    assert g.drags == (0 if n <= 10 else -(-(n - 10) // 10)) + (n == 20) + (page == "sell")  # rows 3-4, 5-6: a drag each


def test_a_cell_read_further_down_is_found_again_after_the_grid_moved(context, grid):
    # cell_at drags the grid back to bring a cell read before the last drag whole into view; its tap hits that gift.
    g = grid("fuse", 23)
    cells, at = actions.owned_cells(context, g.screen(), "fuse", [])
    for i in (22, 0, 12, 4, 21):
        g.click(*actions.cell_at(context, at, cells[i]))
    assert g.taps == [22, 0, 12, 4, 21]


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("recipes", [0, 7])
def test_a_page_opened_where_its_list_was_left_is_read_from_its_top(context, grid, page, recipes):
    # Live 2026-10-21 (F4): the fuse page opened again after a fusion with its list still scrolled, its owned gifts'
    # label above the edge: the scan dragged on down and found no label. The list goes back to its top first.
    g = grid(page, 23, recipes=recipes if page == "fuse" else 0)
    g.at = g.max_at
    actions.owned_cells(context, g.screen(), page, [])
    assert g.reads == list(range(23))


@pytest.mark.parametrize("fling", [-8, 8])
def test_a_drag_a_few_px_off_still_reads_every_gift_once(context, grid, fling):
    # A drag stops GRID_MARGIN px short of the first row's place: a row that lands a few px higher is still whole.
    g = grid("fuse", 31, fling)
    actions.owned_cells(context, g.screen(), "fuse", [])
    assert g.reads == list(range(31))


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("share", [0.25, 0.6])
def test_a_drag_the_game_took_less_of_still_reads_on(context, grid, page, share):
    # A short drag (a quarter: 44-52 px) can leave a full row over the edge and the next one all under it: nothing cut
    # off shows, yet the grid goes on (review of #221).
    g = grid(page, 31, 0, share)
    actions.owned_cells(context, g.screen(), page, [])
    assert g.reads == list(range(31))


def test_the_same_gift_check_holds_on_live_captures():
    # GRID_SAME's sweep: each filled cell of tests/shop's captures against itself 0-3 px off and moved a fraction of a
    # px (resampled), and against every other cell of its capture. The closest two gifts are Faint and Dark Vestige.
    grids = {"fuse": "FUSE_CELLS", "fuse_one_in": "FUSE_CELLS", "fuse_two_in": "FUSE_CELLS", "fuse_spiderweb": "FUSE_CELLS",
             "sell": "SELL_CELLS"}
    same, other = [], []
    for name, cells in grids.items():
        image = screen_with(name)
        cells = [(x, y) for x, y in getattr(actions, cells)[:10] if actions.shop.filled(image, x, y)]
        for x, y in cells:
            look = actions.centre(image, x, y)
            for f in (0.33, 0.5, 0.67):
                moved = (image * (1 - f) + np.roll(image, -1, axis=0) * f).astype(np.uint8)
                same += [actions.matched(moved, x, y + e, look)[0] for e in range(4)]
            other += [actions.matched(image, x2, y2, look)[0] for x2, y2 in cells if (x2, y2) != (x, y)]
    assert len(same) == 348 and len(other) == 204
    assert max(same) < actions.GRID_SAME < min(other)


@pytest.mark.parametrize("s", [0, 1, 46, 91, 92, 183, 184, -92, -184])
def test_the_grid_shift_is_measured_on_a_live_capture(s):
    # The fuse page of tests/shop/fuse.png moved up by s px (down when negative): the frames repeat every row, the
    # icons do not.
    before = screen_with("fuse")
    after = np.zeros_like(before)
    top, bottom = actions.OWNED_GRID["fuse"][0][1] - 48, actions.CELL_PAGES["fuse"][1]
    src = np.zeros_like(before)
    src[top:bottom] = before[top:bottom]
    if s >= 0:
        after[top:bottom - s] = src[top + s:bottom]
    else:
        after[top - s:bottom] = src[top:bottom + s]
    most = 184 if s >= 0 else -184
    assert actions.grid_shift(src, after, "fuse", most) == s


def fusion(context, monkeypatch, g):
    """Shop.fuse on g with the fuse page's read-back as the game would show it (a tap puts a gift in or takes it out)."""
    def inside():
        return {i for i in g.taps if isinstance(i, int) and g.taps.count(i) % 2}
    page = {**test_actions.FUSE_PAGE, tuple(actions.FUSE_CONFIRM): [("Selected E.G.O Gifts 3/3", (330, 175, 320, 30))],
            tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}
    del page[tuple(actions.FUSE_LIST)]  # the grid's own label
    test_actions.reads(context, page)
    inner = context.run_recognition.side_effect
    context.run_recognition.side_effect = lambda *a, **k: g.recognition(*a, **k) or inner(*a, **k)
    monkeypatch.setattr(actions.shop, "fuse_slots", lambda image: 3)
    monkeypatch.setattr(actions.shop, "placed", lambda image, n: len(inside()))
    monkeypatch.setattr(actions.shop, "picked", lambda image, x, y, bottom=720: g.at_screen(x, y) in inside())
    return actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, {})


def test_a_fusion_puts_in_gifts_from_both_ends_of_the_grid(context, grid, monkeypatch):
    # 23 gifts: all Burn (kept) but 1, 12 and 22. They fuse; each is dragged into view and tapped once, no other cell.
    g = grid("fuse", 23)
    reader = g.read_cells

    def read_cells(context, image, cells, page, gifts=()):
        return [{**c, "keyword": c["keyword"] if g.at_screen(c["x"], c["y"]) in (1, 12, 22) else "Burn"}
                for c in reader(context, image, cells, page, gifts)]
    monkeypatch.setattr(actions, "read_cells", read_cells)
    assert fusion(context, monkeypatch, g)
    assert sorted(i for i in g.taps if isinstance(i, int)) == [1, 12, 22]
    assert actions.PAGE_OK in g.taps


@pytest.mark.parametrize("recipes", [1, 7, 15])
def test_a_fusion_reads_the_owned_gifts_under_a_fixed_recipes_section(context, grid, monkeypatch, recipes):
    # Live 2026-10-21 (F4, F5): a fixed recipe's Fusion Available section over the owned gifts closed the fuse page
    # unread (#103). The owned gifts are found by their label under 1, 2 or 3 rows of recipe cells (3: the label is
    # under the list's edge when it opens); no recipe cell is read or tapped (#78 is the recipes' own issue).
    g = grid("fuse", 23, recipes=recipes)
    reader = g.read_cells

    def read_cells(context, image, cells, page, gifts=()):
        return [{**c, "keyword": c["keyword"] if g.at_screen(c["x"], c["y"]) in (1, 12, 22) else "Burn"}
                for c in reader(context, image, cells, page, gifts)]
    monkeypatch.setattr(actions, "read_cells", read_cells)
    assert fusion(context, monkeypatch, g)
    assert g.reads == list(range(23))
    assert sorted(i for i in g.taps if isinstance(i, int)) == [1, 12, 22]


def test_a_fuse_page_without_its_owned_gifts_label_is_not_read(context, grid, monkeypatch):
    # The label never shows (OCR misses it, or a list it does not know): no gift is read or tapped.
    g = grid("fuse", 13)
    monkeypatch.setattr(g, "recognition", lambda *a, **k: None)
    assert not fusion(context, monkeypatch, g)
    assert not g.reads and not [i for i in g.taps if isinstance(i, int)]


def sell_page(context, g, prices, cost=100):
    """The sell page over g: Cost, each whole cell's price under it, the sale's dialog naming the price of the gift last
    tapped, and Confirm adding it to the Cost."""
    state = {"cost": cost, "asked": None}
    click = g.click

    def tap(x, y):
        click(x, y)
        if (x, y) == actions.PAGE_OK:
            state["asked"] = next(i for i in reversed(g.taps) if isinstance(i, int))
        elif (x, y) == actions.DIALOG_CONFIRM and state["asked"] is not None:
            state["cost"] += prices[state["asked"]]
            state["asked"] = None
        return DONE
    context.tasker.controller.post_click.side_effect = tap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                 tuple(actions.SELL_COST): [(str(state["cost"]), (980, 90, 60, 30))]}.get(roi, [])
        if roi == tuple(actions.SELL_GRID):
            spots = [(i, *g.place(i)) for i in range(len(g.icons))]
            lines = [(str(prices[i]), (x - 13, y - g.at + 38, 26, 16)) for i, x, y in spots  # digits 38-53 px under (live)
                     if y - g.at + 53 <= actions.CELL_PAGES["sell"][1] and y - g.at - 38 >= g.top]
        if roi == tuple(actions.DIALOG_TEXT) and state["asked"] is not None:
            lines = [(f"Sell [Gift] for {prices[state['asked']]} Cost?", (460, 330, 360, 25))]
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    return state


def test_a_sale_taps_the_gift_it_picked_far_down_the_grid(context, grid, monkeypatch):
    # 18 gifts, all Burn (kept) but the last: no fusion takes it, and its 90 makes the wanted 180 with 100 Cost. Its
    # price shows only once the grid is dragged; it is tapped there and sold, nothing else tapped.
    g = grid("sell", 18)
    reader = g.read_cells
    monkeypatch.setattr(actions, "read_cells", lambda *a, **k: [
        {**c, "keyword": "Bleed" if g.at_screen(c["x"], c["y"]) == 17 else "Burn"} for c in reader(*a, **k)])
    state = sell_page(context, g, [50 + i for i in range(17)] + [90])
    assert actions.Shop.sell(context, {"keyword": "Burn", "reserve_cost": 0, "gift_search": {"gifts": []}},
                             {"wanted": 180, "sold": False})
    assert [i for i in g.taps if isinstance(i, int)] == [17] and state["cost"] == 190


def test_a_sale_whose_dialog_names_another_price_is_cancelled(context, grid, monkeypatch):
    # The tap picked another gift than the one meant (the grid moved under it): the dialog's price says so.
    g = grid("sell", 4)
    monkeypatch.setattr(actions, "read_cells", lambda *a, **k: [{**c, "keyword": "Bleed"} for c in g.read_cells(*a, **k)])
    state = sell_page(context, g, [10, 20, 30, 90])
    monkeypatch.setattr(actions, "cell_at", lambda context, grid, cell: g.place(0))
    actions.Shop.sell(context, {"keyword": "Burn", "reserve_cost": 0, "gift_search": {"gifts": []}},
                      {"wanted": 180, "sold": False})
    assert actions.DIALOG_CANCEL in g.taps and actions.DIALOG_CONFIRM not in g.taps and state["cost"] == 100


def test_a_fusion_taps_nothing_when_the_grid_is_not_where_it_was_measured(context, grid, monkeypatch):
    # The grid moved a row more than measured (a drag the game took more of): the cell where gift 22 should be shows
    # another gift, so nothing is tapped and the page is closed unfused.
    g = grid("fuse", 23)
    reader = g.read_cells

    def read_cells(context, image, cells, page, gifts=()):
        return [{**c, "keyword": c["keyword"] if g.at_screen(c["x"], c["y"]) in (1, 12, 22) else "Burn"}
                for c in reader(context, image, cells, page, gifts)]
    monkeypatch.setattr(actions, "read_cells", read_cells)
    scan = actions.owned_cells

    def owned_cells(*args):
        out = scan(*args)
        g.at -= g.dy  # unseen by the shift measured
        return out
    monkeypatch.setattr(actions, "owned_cells", owned_cells)
    assert not fusion(context, monkeypatch, g)
    assert not [i for i in g.taps if isinstance(i, int)] and actions.PAGE_OK not in g.taps


def test_a_sale_never_taps_a_gift_whose_badge_is_unread(context, monkeypatch):
    # #205: the first cell's badge is unread: neither sold nor opened, though as a tier I it is the one the fusion of
    # the 3 others leaves over.
    assert test_actions.sale_taps(context, monkeypatch, {}, [500, 90, 60, 70], (None, None, 1), ("Bleed", None),
                                  ("Tremor", None), ("Pierce", None)) == []


def test_a_material_whose_price_is_unread_is_not_sold_but_still_fused(context, monkeypatch):
    # #205: Bleed's price is unread (no panel is opened for it): it is not sold, and still counts for the fusion, so
    # Tremor and Pierce make a group with it and none is sold.
    assert test_actions.sale_taps(context, monkeypatch, {}, [], ("Bleed", None), ("Tremor", None), ("Pierce", None)) == []


def test_a_gift_whose_badge_is_unread_stays_out_of_a_fusion_untapped(context, monkeypatch):
    # #205: no cell is opened to read it; with the others it would make a fusion, without them none is made.
    fused, taps, ok = test_actions.fusion_taps(context, monkeypatch, {}, (None, None), ("Tremor", None), ("Pierce", None))
    assert not fused and not ok and taps == [0, 0, 0]


def test_no_cell_of_the_fusion_grid_is_tapped_to_read_it(context, monkeypatch):
    # Live 2026-10-18: 5 gifts owned, 10 empty cells tapped at 3.4 s each. #205: two gifts in the third row, whose
    # badges the grid's edge cuts off: the grid is dragged for them (this screen does not move), never tapped.
    test_actions.reads(context, test_actions.FUSE_PAGE)
    test_actions.owned_gifts(context, actions.FUSE_CELLS[10:12])
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    assert not actions.Shop.fuse(context, {"keyword": "Burn", "gift_search": {"gifts": []}}, {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert not set(taps) & set(actions.FUSE_CELLS) and context.tasker.controller.post_touch_down.called
    assert "shop: the fuse grid does not move: its cut-off cells stay unread" in logs


def test_a_fuse_page_with_no_keyword_picked_is_closed_with_one_tap(context, clock):
    # #214 (live 2026-10-21): on "Select a Keyword" a line in the old tooltip check's roi ended in "E.G.O Gift", its
    # neutral tap on the grid opened Keyword Selection, and Close then hit its Cancel: 12 rounds, 31 s. Close alone.
    def reads_now(taps):
        if actions.PAGE_CLOSE in taps:  # the main shop: its Refresh fee
            return {tuple(actions.REFRESH["normal"][1]): [("30", (970, 145, 40, 20))]}
        return {tuple(actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 90, 200, 40))],
                (600, 180, 680, 440): [("Select a Keyword to fuse an E.G.O Gift", (700, 330, 400, 25))]}
    taps = test_actions.live_shop(context, reads_now)
    assert actions.Shop.to_main(context)
    assert taps == [actions.PAGE_CLOSE]
