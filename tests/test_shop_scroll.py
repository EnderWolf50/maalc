"""#205: the fuse and sell pages' owned grids are scrolled to read their cut-off rows; no cell is opened to read it."""
from types import SimpleNamespace

import numpy as np
import pytest

import actions
import shop_actions
import shop
import test_actions
from test_shop import screen_with
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # its fixtures
DONE = SimpleNamespace(wait=lambda: None)
# Live 2026-10-21: a sell grid of 13 gifts scrolls 31 px, its last row's price just inside; the fuse page's end is a guess.
END = {"fuse": 56, "sell": 495 + 31 - 472}
TOP = {"fuse": 200, "sell": 215}  # the lists' upper edge (live: the fuse page's label at 216-240, sell rows cut at 215)
UNLISTED = test_actions.UNLISTED  # gift i of a grid reads as id UNLISTED + i, which no gift list mentions
KEYWORDS = ["Bleed", "Tremor", "Pierce", "Sinking", "Slash", "Blunt", "Poise", "Rupture", "Charge"]


def icon(rng):
    """A gift's cell, 76 px square: an icon of rng's, in the frame every gift has."""
    out = np.kron(rng.integers(40, 255, (19, 19, 3), np.uint8), np.ones((4, 4, 1), np.uint8))
    out[:5], out[-5:], out[:, :5], out[:, -5:] = (0, 200, 230), (0, 200, 230), (0, 200, 230), (0, 200, 230)
    return out


class Grid:
    """The owned grid of page as the game shows it: n gifts, 5 a row, each a unique icon in the same frame. A drag
    moves it by the finger's travel after the drag threshold's first move (1 px more every other drag: the fling
    left, or fling px more each drag; or only share of it), stopped at its ends; a tap lands on the gift under it. The
    grid ends END px under its last row's centre. On the fuse page OCR reads the "E.G.O Gifts Owned" label over the gifts
    where it shows; recipes: a section of that many cells over it (a fixed recipe's Fusion Available), each a gift
    of its own, its label as tall as the owned gifts'. tiers: each owned gift's (I by default), highest first; names: the
    data's id a gift reads as (UNLISTED + its number by default); makes: what a fusion makes, (tier, id or None) of the
    tiers and ids fused (None: nothing shows, the gift made left out)."""

    def __init__(self, context, page, n, fling=None, share=1.0, recipes=0, tiers=None, names=None, makes=None):
        (self.x0, self.y0), (self.dx, self.dy), _ = shop_actions.OWNED_GRID[page]
        self.page, self.above = page, (1 + (recipes - 1) // 5) * self.dy + shop_actions.OWNED_LABEL if recipes else 0
        self.recipes = [(self.x0 + self.dx * (k % 5), self.y0 + self.dy * (k // 5)) for k in range(recipes)]
        self.top, self.bottom = TOP[page], shop_actions.CELL_PAGES[page][1]
        self.end = END[page]
        self.at, self.drags, self.taps, self.reads, self.fling, self.share = 0, 0, [], [], fling, share
        # a gift's tooltip over the cells, its red head drawn (head: shop.tooltip sees it); taps on the neutral spot that do not close it
        self.tooltip, self.head, self.stuck = False, True, 0
        rng = np.random.default_rng(1)
        self.icons = [icon(rng) for _ in range(n + recipes)]
        self.ids = list(range(n + recipes))  # each icon's gift: its place when the grid was made
        self.tiers = list(tiers or [1] * n) + [1] * recipes
        self.names, self.makes, self.made, self.tapped = dict(names or {}), makes, 0, []  # tapped: the gifts tapped, in turn
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.screen
        ctl.post_touch_down.side_effect = self.down
        ctl.post_touch_move.side_effect = self.move
        ctl.post_touch_up.side_effect = self.up
        ctl.post_click.side_effect = self.click

    @property
    def max_at(self):
        """How far the grid scrolls: its last row's END under the list's edge."""
        n = len(self.icons) - len(self.recipes)
        return max(0, self.y0 + self.above + self.dy * ((n - 1) // 5) + self.end - self.bottom)

    def sold(self, i):
        """Gift i sold: the gifts after it move up a cell, and a grid scrolled past its new end springs back."""
        del self.icons[i], self.ids[i], self.tiers[i]
        self.at = min(self.at, self.max_at)

    def fused(self, gifts):
        """The gifts in `gifts` (places) fused: they leave the grid as a sale does, and the gift made (makes) goes last of
        its tier's run, the others keeping their order (live, #378); then a grid scrolled past its new end springs back."""
        made = self.makes and self.makes([self.tiers[i] for i in gifts], [self.gift_id(self.ids[i]) for i in gifts])
        at = self.at
        for i in sorted(gifts, reverse=True):
            self.sold(i)
        if made:
            tier, gift_id = made
            self.made += 1
            gift = 1000 + self.made  # a number no gift of the grid has
            k = sum(t >= tier for t in self.tiers[:len(self.icons) - len(self.recipes)])
            self.icons.insert(k, icon(np.random.default_rng(gift)))
            self.ids.insert(k, gift)
            self.tiers.insert(k, tier)
            if gift_id is not None:
                self.names[gift] = gift_id
        self.at = min(at, self.max_at)

    def gift_id(self, gift):
        """The data's id gift reads as."""
        return self.names.get(gift, UNLISTED + gift)

    def add_section(self, recipes):
        """A Fusion Available section of `recipes` cells comes over the owned gifts (a gift made completes a fixed recipe's
        materials): the owned gifts move down under it."""
        self.above = (1 + (recipes - 1) // 5) * self.dy + shop_actions.OWNED_LABEL
        self.recipes = [(self.x0 + self.dx * (k % 5), self.y0 + self.dy * (k // 5)) for k in range(recipes)]
        self.icons += [icon(np.random.default_rng(2000 + k)) for k in range(recipes)]
        self.ids += [2000 + k for k in range(recipes)]
        self.tiers += [1] * recipes

    def drop_section(self):
        """The recipe section over the owned gifts goes (live, #304: its recipe fused, the list moves up at once)."""
        n = len(self.icons) - len(self.recipes)
        del self.icons[n:], self.ids[n:], self.tiers[n:]
        self.recipes, self.above = [], 0
        self.at = min(self.at, self.max_at)

    def place(self, i):
        """Gift i's centre with the grid at its top (the recipe cells' after the owned gifts')."""
        n = len(self.icons) - len(self.recipes)
        return self.recipes[i - n] if i >= n else (self.x0 + self.dx * (i % 5), self.y0 + self.above + self.dy * (i // 5))

    def recognition(self, name, image, override=None):
        """OCR of FUSE_LIST: the owned gifts' label, where it shows whole on the fuse page; None for anything else."""
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        y = self.y0 + self.above - shop_actions.OWNED_LABEL - self.at
        if self.page != "fuse" or roi != tuple(shop_actions.FUSE_LIST) or not self.top <= y - 12 <= y + 12 <= self.bottom:
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
        if self.tooltip and self.head:  # its head under the grid's edge, where no drag measures it
            image[500:526, 700:990] = (0, 0, 155)
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
        if i is not None:
            self.tapped.append(self.ids[i])
        if (x, y) == shop_actions.FUSE_NEUTRAL:
            self.stuck, self.tooltip = max(0, self.stuck - 1), self.tooltip and self.stuck > 0
        return DONE

    def read_cells(self, context, image, cells, page):
        """shop_actions.read_cells as the badge and icon matching would: each gift's keyword, by the gift on screen there.
        Only cells shown whole are asked for (test_shop_cells checks the matching itself)."""
        out = []
        for k, (x, y) in enumerate(cells):
            assert shop_actions.whole(page, y) and y - 38 >= self.top, (x, y)  # its frame shows whole
            i = self.at_screen(x, y)
            assert i is None or i < len(self.icons) - len(self.recipes), f"a recipe cell read as an owned gift at {x, y}"
            if i is not None:
                gift = self.ids[i]
                self.reads.append(gift)
                out.append({"i": k, "x": x, "y": y, "tier": self.tiers[i], "keyword": KEYWORDS[gift % len(KEYWORDS)],
                            "id": None if self.tooltip and gift % 2 else self.gift_id(gift), "score": 0.9})
        return out


@pytest.fixture
def grid(context, monkeypatch):
    def make(page, n, fling=None, share=1.0, recipes=0, **gifts):
        g = Grid(context, page, n, fling, share, recipes, **gifts)
        patch_all(monkeypatch, "read_cells", g.read_cells)
        context.run_recognition.side_effect = g.recognition
        return g
    return make


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("n", [3, 10, 13, 20, 23, 31])
def test_every_gift_is_read_once_whatever_the_grid_holds(context, grid, monkeypatch, page, n):
    # Two rows a drag, the first cut-off one to the first's place; the last drag stops at the grid's end. A last row
    # full at the end takes one drag more: it might be a drag the game took less of. Every page is first dragged to
    # its top (a drag that does not move it here).
    g = grid(page, n)
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    cells, _ = shop_actions.owned_cells(context, page)
    assert g.reads == list(range(n))  # each gift once, in the grid's order
    assert (f"shop: the {page} grid does not move: at its end" in logs) == (n == 20)
    assert [c["i"] for c in cells] == list(range(n))
    assert [c["keyword"] for c in cells] == [KEYWORDS[i % len(KEYWORDS)] for i in range(n)]
    assert g.drags == (0 if n <= 10 else -(-(n - 10) // 10)) + (n == 20) + 1  # rows 3-4, 5-6: a drag each


@pytest.mark.parametrize("stuck", [0, 1, 2])
def test_a_fuse_pages_tooltip_is_closed_before_its_cells_are_read(context, grid, stuck):
    # #331: a gift's tooltip hides some of the cells (10 of 217 live): they read as unknown. The neutral spot is
    # tapped first; when taps did not close it (stuck of them) and a cell still reads unknown, it is read again after
    # one more. Only the neutral spot is tapped.
    g = grid("fuse", 13)
    g.tooltip, g.stuck = True, stuck
    cells, _ = shop_actions.owned_cells(context, "fuse")
    assert [c["id"] for c in cells] == [UNLISTED + i for i in range(13)]
    assert g.taps and set(g.taps) == {shop_actions.FUSE_NEUTRAL}


def test_a_fuse_page_with_no_tooltip_is_read_without_a_tap(context, grid):
    # #378: the neutral spot was tapped before every read and the screen waited on to move, 1.5 s a read with nothing
    # to close (live 2026-11-04: 4 of them in one read of 16 gifts). No tooltip on show: no tap, no wait for one.
    g = grid("fuse", 23)
    cells, _ = shop_actions.owned_cells(context, "fuse")
    assert [c["id"] for c in cells] == [UNLISTED + i for i in range(23)]
    assert shop_actions.FUSE_NEUTRAL not in g.taps


def test_a_tooltip_the_check_misses_is_closed_for_the_cells_it_hid(context, grid):
    # A tooltip whose head shop.tooltip does not see: the cells under it read unknown, so the neutral spot is tapped once
    # and they are read again (#331's second read), every gift known.
    g = grid("fuse", 13)
    g.tooltip, g.head = True, False
    cells, _ = shop_actions.owned_cells(context, "fuse")
    assert [c["id"] for c in cells] == [UNLISTED + i for i in range(13)]
    assert g.taps == [shop_actions.FUSE_NEUTRAL]


def test_a_page_the_guard_does_not_find_untapped_is_tapped_as_before(context, clock, monkeypatch):
    # A tooltip that hides Leave (the Shop node's anchor) and that shop.tooltip misses: the guard on the untapped screenshot
    # fails, so the neutral spot is tapped and the page checked again, as close_tooltip always did (ADR 0007).
    patch_all(monkeypatch, "page_guard", test_actions.REAL_GUARD)
    ctl = context.tasker.controller
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name == "Shop" and ctl.post_click.called else None
    assert shop_actions.close_tooltip(context, "fuse") is not None
    assert [c.args for c in ctl.post_click.call_args_list] == [shop_actions.FUSE_NEUTRAL]


def test_the_tap_that_closes_a_materials_tooltip_is_followed_by_the_page_guard(context, monkeypatch):
    # ADR 0007, #331: the neutral spot is tapped through close_tooltip (the tap, then the guard: a tooltip over the fuse page
    # hides Leave, so the page node reads nothing until it is closed), after each material tapped in.
    events = []
    patch_all(monkeypatch, "cell_at", lambda context, grid, c: (c["x"], c["y"]))
    patch_all(monkeypatch, "tap_moved", lambda context, x, y, timeout=0.5: events.append("cell"))
    patch_all(monkeypatch, "tap_settled", lambda context, x, y, timeout=1.0: events.append((x, y)))
    patch_all(monkeypatch, "page_guard", lambda context, home, image=None: events.append("guard") or np.zeros((720, 1280, 3), np.uint8))
    patch_all(monkeypatch, "screen", lambda context: np.zeros((720, 1280, 3), np.uint8))
    monkeypatch.setattr(shop, "placed", lambda image, n: events.count("cell"))
    monkeypatch.setattr(shop, "picked", lambda image, x, y, bottom=720: True)
    cells = [{"i": i, "x": x, "y": y} for i, (x, y) in enumerate(shop_actions.FUSE_CELLS[:3])]
    assert shop_actions.Shop.place(context, cells, 3, {"page": "fuse", "at": 0})
    assert events == ["guard", "cell", shop_actions.FUSE_NEUTRAL, "guard"] * 3


def test_a_cell_read_further_down_is_found_again_after_the_grid_moved(context, grid):
    # cell_at drags the grid back to bring a cell read before the last drag whole into view; its tap hits that gift.
    g = grid("fuse", 23)
    cells, at = shop_actions.owned_cells(context, "fuse")
    for i in (22, 0, 12, 4, 21):
        g.click(*shop_actions.cell_at(context, at, cells[i]))
    assert [t for t in g.taps if t != shop_actions.FUSE_NEUTRAL] == [22, 0, 12, 4, 21]


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("recipes", [0, 7])
def test_a_page_opened_where_its_list_was_left_is_read_from_its_top(context, grid, page, recipes):
    # Live 2026-10-21 (F4): the fuse page opened again after a fusion with its list still scrolled, its owned gifts'
    # label above the edge: the scan dragged on down and found no label. The list goes back to its top first.
    g = grid(page, 23, recipes=recipes if page == "fuse" else 0)
    g.at = g.max_at
    shop_actions.owned_cells(context, page)
    assert g.reads == list(range(23))


@pytest.mark.parametrize("fling", [-8, 8])
def test_a_drag_a_few_px_off_still_reads_every_gift_once(context, grid, fling):
    # A drag stops GRID_MARGIN px short of the first row's place: a row that lands a few px higher is still whole.
    g = grid("fuse", 31, fling)
    shop_actions.owned_cells(context, "fuse")
    assert g.reads == list(range(31))


@pytest.mark.parametrize("page", ["fuse", "sell"])
@pytest.mark.parametrize("share", [0.25, 0.6])
def test_a_drag_the_game_took_less_of_still_reads_on(context, grid, page, share):
    # A short drag (a quarter: 44-52 px) can leave a full row over the edge and the next one all under it: nothing cut
    # off shows, yet the grid goes on (review of #221).
    g = grid(page, 31, 0, share)
    shop_actions.owned_cells(context, page)
    assert g.reads == list(range(31))


def test_the_same_gift_check_holds_on_live_captures():
    # GRID_SAME's sweep: each filled cell of tests/shop's captures against itself 0-3 px off and moved a fraction of a
    # px (resampled), and against every other cell of its capture. The closest two gifts are Faint and Dark Vestige.
    grids = {"fuse": "FUSE_CELLS", "fuse_one_in": "FUSE_CELLS", "fuse_two_in": "FUSE_CELLS", "fuse_spiderweb": "FUSE_CELLS",
             "sell": "SELL_CELLS"}
    same, other = [], []
    for name, cells in grids.items():
        image = screen_with(name)
        cells = [(x, y) for x, y in getattr(shop_actions, cells)[:10] if shop.filled(image, x, y)]
        for x, y in cells:
            look = shop_actions.centre(image, x, y)
            for f in (0.33, 0.5, 0.67):
                moved = (image * (1 - f) + np.roll(image, -1, axis=0) * f).astype(np.uint8)
                same += [shop_actions.matched(moved, x, y + e, look)[0] for e in range(4)]
            other += [shop_actions.matched(image, x2, y2, look)[0] for x2, y2 in cells if (x2, y2) != (x, y)]
    assert len(same) == 348 and len(other) == 204
    assert max(same) < shop_actions.GRID_SAME < min(other)


@pytest.mark.parametrize("s", [0, 1, 46, 91, 92, 183, 184, -92, -184])
def test_the_grid_shift_is_measured_on_a_live_capture(s):
    # The fuse page of tests/shop/fuse.png moved up by s px (down when negative): the frames repeat every row, the
    # icons do not.
    before = screen_with("fuse")
    after = np.zeros_like(before)
    top, bottom = shop_actions.OWNED_GRID["fuse"][0][1] - 48, shop_actions.CELL_PAGES["fuse"][1]
    src = np.zeros_like(before)
    src[top:bottom] = before[top:bottom]
    if s >= 0:
        after[top:bottom - s] = src[top + s:bottom]
    else:
        after[top - s:bottom] = src[top:bottom + s]
    most = 184 if s >= 0 else -184
    assert shop_actions.grid_shift(src, after, "fuse", most) == s


def kept_but(n, *free):
    """The team of a grid of n gifts whose list keeps every gift but the free ones (they drop)."""
    return test_actions.shop_team({"list": test_actions.wants(keep=[UNLISTED + i for i in range(n) if i not in free])})


def by_points(slots=3):
    """A Grid's makes: the gift made is of the tier the materials' points give (shop.yaml, a shop's or a Super Shop's
    thresholds), an id no list mentions."""
    d = actions.data("shop.yaml")
    thresholds = d["fusion_tiers"]["super_shop" if slots == 5 else "shop"]
    return lambda tiers, ids: (shop.fusion_tier(sum(d["fusion_points"][t] for t in tiers), thresholds), None)


def fusion(context, monkeypatch, g, team, slots=3, visit=None):
    """Shop.fuse on g with the fuse page's read-back as the game would show it: a tap puts a gift in or takes it out, the
    dialog counts the gifts in, and its Confirm takes them out of the grid (g.fused) and empties the slots, as Close does."""
    def inside():
        since = test_actions.after_last(test_actions.after_last(g.taps, shop_actions.FUSE_DIALOG_CONFIRM), shop_actions.PAGE_CLOSE)
        return {i for i in since if isinstance(i, int) and since.count(i) % 2}
    click = g.click

    def tap(x, y):
        if (x, y) == shop_actions.FUSE_DIALOG_CONFIRM:
            g.fused(inside())
        return click(x, y)
    context.tasker.controller.post_click.side_effect = tap
    page = dict(test_actions.FUSING)
    del page[tuple(shop_actions.FUSE_LIST)]  # the grid's own label
    test_actions.reads(context, page)
    inner = context.run_recognition.side_effect

    def recognition(name, image, override=None):
        if tuple((override or {}).get(name, {}).get("roi", ())) == tuple(shop_actions.FUSE_CONFIRM):
            return SimpleNamespace(all_results=[SimpleNamespace(text=f"Selected E.G.O Gifts {len(inside())}/{slots}",
                                                                box=(330, 175, 320, 30))], hit=True, best_result=None)
        return g.recognition(name, image, override) or inner(name, image, override)
    context.run_recognition.side_effect = recognition
    monkeypatch.setattr(shop, "fuse_slots", lambda image: slots)
    monkeypatch.setattr(shop, "placed", lambda image, n: len(inside()))
    monkeypatch.setattr(shop, "picked", lambda image, x, y, bottom=720: g.at_screen(x, y) in inside())
    return shop_actions.Shop.fuse(context, team, {} if visit is None else visit)


def test_a_fusion_puts_in_gifts_from_both_ends_of_the_grid(context, grid, monkeypatch):
    # 23 gifts: all kept by the list but 1, 12 and 22. They fuse; each is dragged into view and tapped once, no other cell.
    g = grid("fuse", 23)
    assert fusion(context, monkeypatch, g, kept_but(23, 1, 12, 22))
    assert sorted(i for i in g.taps if isinstance(i, int)) == [1, 12, 22]
    assert shop_actions.PAGE_OK in g.taps


@pytest.mark.parametrize("recipes", [1, 7, 15])
def test_a_fusion_reads_the_owned_gifts_under_a_fixed_recipes_section(context, grid, monkeypatch, recipes):
    # Live 2026-10-21 (F4, F5): a fixed recipe's Fusion Available section over the owned gifts closed the fuse page
    # unread (#103). The owned gifts are found by their label under 1, 2 or 3 rows of recipe cells (3: the label is
    # under the list's edge when it opens); no recipe cell is read or tapped (#78 is the recipes' own issue). After the
    # fusion the 20 gifts left are read again under the section on the page still open (#378).
    g = grid("fuse", 23, recipes=recipes)
    assert fusion(context, monkeypatch, g, kept_but(23, 1, 12, 22))
    assert g.reads == list(range(23)) + [i for i in range(23) if i not in (1, 12, 22)]
    assert sorted(i for i in g.taps if isinstance(i, int)) == [1, 12, 22]


def test_a_fuse_page_without_its_owned_gifts_label_is_not_read(context, grid, monkeypatch):
    # The label never shows (OCR misses it, or a list it does not know): no gift is read or tapped.
    g = grid("fuse", 13)
    monkeypatch.setattr(g, "recognition", lambda *a, **k: None)
    assert not fusion(context, monkeypatch, g, kept_but(13))
    assert not g.reads and not [i for i in g.taps if isinstance(i, int)]


def sell_page(context, g, prices, cost=100):
    """The sell page over g: Cost, each whole cell's price under it, the sale's dialog naming the price of the gift last
    tapped, and Confirm adding it to the Cost."""
    state = {"cost": cost, "asked": None}
    click = g.click

    def tap(x, y):
        click(x, y)
        if (x, y) == shop_actions.PAGE_OK:
            state["asked"] = next(i for i in reversed(g.taps) if isinstance(i, int))
        elif (x, y) == actions.DIALOG_CONFIRM and state["asked"] is not None:
            state["cost"] += prices.pop(state["asked"])
            g.sold(state["asked"])
            state["asked"] = None
        return DONE
    context.tasker.controller.post_click.side_effect = tap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = {tuple(shop_actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                 tuple(shop_actions.SELL_COST): [(str(state["cost"]), (980, 90, 60, 30))]}.get(roi, [])
        if roi == tuple(shop_actions.SELL_GRID):
            spots = [(i, *g.place(i)) for i in range(len(g.icons))]
            lines = [(str(prices[i]), (x - 13, y - g.at + 38, 26, 16)) for i, x, y in spots  # digits 38-53 px under (live)
                     if y - g.at + 53 <= shop_actions.CELL_PAGES["sell"][1] and y - g.at - 38 >= g.top]
        if roi == tuple(actions.DIALOG_TEXT) and state["asked"] is not None:
            lines = [(f"Sell [Gift] for {prices[state['asked']]} Cost?", (460, 330, 360, 25))]
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    return state


def test_a_sale_taps_the_gift_it_picked_far_down_the_grid(context, grid, monkeypatch):
    # 18 gifts, all kept by the list but the last: no fusion takes it, and its 90 makes the wanted 180 with 100 Cost. Its
    # price shows only once the grid is dragged; it is tapped there and sold, nothing else tapped.
    g = grid("sell", 18)
    state = sell_page(context, g, [50 + i for i in range(17)] + [90])
    assert shop_actions.Shop.sell(context, kept_but(18, 17), {"wanted": 180, "sold": False})
    assert [i for i in g.taps if isinstance(i, int)] == [17] and state["cost"] == 190


def test_two_sales_far_down_the_grid_go_back_to_its_top_between_them(context, grid, monkeypatch):
    # 16 gifts, the last two the list lets go (no fusion takes 2): the 180 wanted with 100 Cost needs both. Sold, the last one
    # empties its row and the grid springs back from its end; the grid goes back to its top (grid_top) and the second
    # is dragged into view again: each tapped once, sold.
    g = grid("sell", 16)
    state = sell_page(context, g, [50 + i for i in range(14)] + [45, 40])
    assert shop_actions.Shop.sell(context, kept_but(16, 14, 15), {"wanted": 180, "sold": False})
    assert [i for i in g.taps if isinstance(i, int)] == [15, 14] and state["cost"] == 185


def test_a_sale_whose_dialog_names_another_price_is_cancelled(context, grid, monkeypatch):
    # The tap picked another gift than the one meant (the grid moved under it): the dialog's price says so.
    g = grid("sell", 4)
    state = sell_page(context, g, [10, 20, 30, 90])
    patch_all(monkeypatch, "cell_at", lambda context, grid, cell: g.place(0))
    shop_actions.Shop.sell(context, test_actions.shop_team({}),
                      {"wanted": 180, "sold": False})
    assert actions.DIALOG_CANCEL in g.taps and actions.DIALOG_CONFIRM not in g.taps and state["cost"] == 100


def test_a_fusion_taps_nothing_when_the_grid_is_not_where_it_was_measured(context, grid, monkeypatch):
    # The grid moved a row more than measured (a drag the game took more of): the cell where gift 22 should be shows
    # another gift, so nothing is tapped and the page is closed unfused.
    g = grid("fuse", 23)
    scan = shop_actions.owned_cells

    def owned_cells(*args):
        out = scan(*args)
        g.at -= g.dy  # unseen by the shift measured
        return out
    patch_all(monkeypatch, "owned_cells", owned_cells)
    assert not fusion(context, monkeypatch, g, kept_but(23, 1, 12, 22))
    assert not [i for i in g.taps if isinstance(i, int)] and shop_actions.PAGE_OK not in g.taps


def test_a_sale_never_taps_a_gift_whose_badge_is_unread(context, monkeypatch):
    # #205: the first cell's badge is unread: neither sold nor opened, though as a tier I it is the one the fusion of
    # the 3 others leaves over.
    assert test_actions.sale_taps(context, monkeypatch, {}, [500, 90, 60, 70], (None, 1), ("Bleed",),
                                  ("Tremor",), ("Pierce",)) == []


def test_a_material_whose_price_is_unread_is_not_sold_but_still_fused(context, monkeypatch):
    # #205: Bleed's price is unread (no panel is opened for it): it is not sold, and still counts for the fusion, so
    # Tremor and Pierce make a group with it and none is sold.
    assert test_actions.sale_taps(context, monkeypatch, {}, [], ("Bleed",), ("Tremor",), ("Pierce",)) == []


def test_a_gift_whose_badge_is_unread_stays_out_of_a_fusion_untapped(context, monkeypatch):
    # #205: no cell is opened to read it; with the others it would make a fusion, without them none is made.
    fused, taps, ok = test_actions.fusion_taps(context, monkeypatch, {}, (None,), ("Tremor",), ("Pierce",))
    assert not fused and not ok and taps == [0, 0, 0]


def test_no_cell_of_the_fusion_grid_is_tapped_to_read_it(context, monkeypatch):
    # Live 2026-10-18: 5 gifts owned, 10 empty cells tapped at 3.4 s each. #205: two gifts in the third row, whose
    # badges the grid's edge cuts off: the grid is dragged for them (this screen does not move), never tapped.
    test_actions.reads(context, test_actions.FUSE_PAGE)
    test_actions.owned_gifts(context, shop_actions.FUSE_CELLS[10:12])
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    assert not shop_actions.Shop.fuse(context, test_actions.shop_team({}), {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert not set(taps) & set(shop_actions.FUSE_CELLS) and context.tasker.controller.post_touch_down.called
    assert "shop: the fuse grid does not move: its cut-off cells stay unread" in logs


def test_a_fuse_page_with_no_keyword_picked_is_closed_with_one_tap(context, clock):
    # #214 (live 2026-10-21): on "Select a Keyword" a line in the old tooltip check's roi ended in "E.G.O Gift", its
    # neutral tap on the grid opened Keyword Selection, and Close then hit its Cancel: 12 rounds, 31 s. Close alone.
    def reads_now(taps):
        if shop_actions.PAGE_CLOSE in taps:  # the main shop: its Refresh fee
            return {tuple(shop_actions.REFRESH["normal"][1]): [("30", (970, 145, 40, 20))]}
        return {tuple(shop_actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 90, 200, 40))],
                (600, 180, 680, 440): [("Select a Keyword to fuse an E.G.O Gift", (700, 330, 400, 25))]}
    taps = test_actions.live_shop(context, reads_now)
    assert shop_actions.Shop.to_main(context)
    assert taps == [shop_actions.PAGE_CLOSE]
