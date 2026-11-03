"""#378: the fuse page stays open after a fusion: its owned gifts are read again there and the next fusion made, a wanted
one first, until none is left; only then is the page closed."""
import actions
import test_actions
import test_shop_scroll
from test_actions import FUSING, after_last, fuse_page, reads, shop_team, taps, wants, with_ids
from test_shop_scroll import fusion, kept_but

clock, context, grid = test_actions.clock, test_actions.context, test_shop_scroll.grid  # their fixtures
KEPT = "shop: fuse page kept: owned gifts read again"
SOOTHE = 9088  # Burn IV: [9003, 9053, 9157]


def fusing(context, monkeypatch, team, *readings):
    """Shop.fuse on fuse_page's readings, every fusion confirmed; (its result, the visit, the taps, the log lines, how
    often grid_top ran)."""
    lines, tops, visit = [], [], {}
    monkeypatch.setattr(actions, "log", lines.append)
    top = actions.grid_top
    monkeypatch.setattr(actions, "grid_top", lambda *a: tops.append(a) or top(*a))
    reads(context, FUSING)
    fuse_page(context, monkeypatch, *readings)
    fused = actions.Shop.fuse(context, shop_team(team), visit)
    return fused, visit, taps(context), lines, len(tops)


def test_two_fusions_on_show_are_made_on_one_page_opened_once(context, monkeypatch):
    # Six gifts the list drops make two groups of three: Fuse Gifts is tapped once, the list goes to its top once (grid_top),
    # the gifts are read again after each fusion, and the page is closed only after the second.
    fused, visit, tapped, lines, tops = fusing(context, monkeypatch, {}, *with_ids([("Bleed", 2)] * 6))
    assert fused and tops == 1
    assert tapped.count(actions.SHOP_BUTTONS["fuse"]) == 1
    assert tapped.count(actions.FUSE_DIALOG_CONFIRM) == 2
    assert lines.count(KEPT) == 2
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert actions.PAGE_CLOSE not in tapped[:tapped.index(actions.FUSE_DIALOG_CONFIRM)]
    assert visit["fuse_scanned"]


def test_the_page_is_closed_once_the_gifts_read_again_make_no_fusion(context, monkeypatch):
    # Five materials: one fusion, then the two left make none. The page is read again, and only then closed: not read
    # again this visit until the owned gifts change (#62).
    fused, visit, tapped, lines, _ = fusing(context, monkeypatch, {}, *with_ids([("Bleed", 2)] * 5))
    assert fused and tapped.count(actions.FUSE_DIALOG_CONFIRM) == 1
    assert lines.index(KEPT) < lines.index("shop: 2 materials on show, a fusion takes 3")
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert actions.PAGE_CLOSE not in tapped[:tapped.index(actions.FUSE_DIALOG_CONFIRM)]
    assert visit["fuse_scanned"]


def test_a_recipe_and_an_ordinary_fusion_are_made_one_after_the_other_on_one_page(context, monkeypatch):
    # #300's order on the page kept open: Soothe the Dead's three materials (cells 3-5) go in first; with them gone the three
    # gifts the list drops are cells 0-2, read again and fused.
    readings = [*with_ids([("Bleed", 2)] * 3), ("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157)]
    fused, visit, tapped, lines, tops = fusing(context, monkeypatch, {"list": wants(SOOTHE)}, *readings)
    assert fused and tops == 1 and tapped.count(actions.SHOP_BUTTONS["fuse"]) == 1
    cells = [t for t in tapped if t in actions.FUSE_CELLS]
    assert sorted(cells[:3]) == sorted(actions.FUSE_CELLS[3:6]) and sorted(cells[3:]) == sorted(actions.FUSE_CELLS[:3])
    recipe = next(k for k, m in enumerate(lines) if m.startswith(f"shop: recipe fusion {SOOTHE} ") and m.endswith("done"))
    ordinary = next(k for k, m in enumerate(lines) if m.startswith("shop: fuse ") and m.endswith("done"))
    assert recipe < lines.index(KEPT) < ordinary
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert visit["fuse_scanned"]


def test_a_page_closes_after_fusions_per_page_and_leaves_the_rest_to_the_next_round(context, monkeypatch):
    # The bound: FUSIONS_PER_PAGE fusions on one page, then it is closed with a log line; the owned gifts changed, so the next
    # round of Shop.run opens it again (fuse_scanned stays False).
    monkeypatch.setattr(actions, "FUSIONS_PER_PAGE", 2)
    fused, visit, tapped, lines, _ = fusing(context, monkeypatch, {}, *with_ids([("Bleed", 2)] * 9))
    assert fused and tapped.count(actions.FUSE_DIALOG_CONFIRM) == 2 and lines.count(KEPT) == 1
    assert "shop: 2 fusions on one fuse page: it is closed, the next round opens it again" in lines
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert not visit["fuse_scanned"]


def test_a_section_that_goes_with_the_fusion_does_not_lose_the_owned_gifts(context, grid, monkeypatch):
    # Live (#304): a fused recipe's Fusion Available section goes and the list moves up at once. The list read again is
    # dragged back by where it was against its top, not against the owned gifts' first row, so their label shows again
    # (under 7 recipe cells it is 250 px down) and the 20 gifts left are read once more, in order.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 23, recipes=7)
    fused = g.fused
    monkeypatch.setattr(g, "fused", lambda gifts: fused(gifts) or g.drop_section())
    assert fusion(context, monkeypatch, g, kept_but(23, 1, 12, 22))
    assert KEPT in lines and "shop: no E.G.O Gifts Owned on the fuse page: nothing read" not in lines
    assert g.reads == list(range(23)) + [i for i in range(23) if i not in (1, 12, 22)]


def test_a_drag_back_the_game_took_less_of_goes_to_the_lists_top_again(context, grid, monkeypatch):
    # The last row fused, the list springs back a row; the drag back to its top moves 60% of the finger and stops there,
    # the label still over the list's edge. owned_label only looks further up: the list goes to its top (grid_top) and the
    # 20 gifts left are read again.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 23, fling=0, share=0.6)
    assert fusion(context, monkeypatch, g, kept_but(23, 20, 21, 22))
    assert g.reads == list(range(23)) + list(range(20))
    assert "shop: the owned gifts' label is not on show after the drag back: the fuse list goes to its top" in lines
