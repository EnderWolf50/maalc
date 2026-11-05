"""#378: the fuse page stays open after a fusion: its owned gifts are placed by the fusion (only the gift made is read) or
read again there, and the next fusion made, a wanted one first, until none is left; only then is the page closed."""
import pytest

import actions
import test_actions
import test_shop
import test_shop_scroll
from test_actions import FUSING, after_last, fuse_page, reads, shop_team, taps, wants, with_ids
from test_shop_scroll import KEYWORDS, UNLISTED, by_points, fusion, kept_but

clock, context, grid = test_actions.clock, test_actions.context, test_shop_scroll.grid  # their fixtures
KEPT = "shop: fuse page kept: "
READ_AGAIN = ", owned gifts read again"
PLACED = "shop: fuse page kept: owned gifts placed by the fusion (new gift read at cell "
SOOTHE = 9088  # Burn IV: [9003, 9053, 9157]
EX = 9799  # A Certain Philosophy: the EX gift a 99% fusion gives when it fails (#378, #449)


def read_again(lines):
    """The places in lines of those that say the owned gifts are read again on the page kept open (fused_cells' reason)."""
    return [k for k, m in enumerate(lines) if m.startswith(KEPT) and m.endswith(READ_AGAIN)]


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
    assert len(read_again(lines)) == 2  # the fake shows no gift made: not where the fusion puts it
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert actions.PAGE_CLOSE not in tapped[:tapped.index(actions.FUSE_DIALOG_CONFIRM)]
    assert visit["fuse_scanned"]


def test_the_page_is_closed_once_the_gifts_read_again_make_no_fusion(context, monkeypatch):
    # Five materials: one fusion, then the two left make none. The page is read again, and only then closed: not read
    # again this visit until the owned gifts change (#62).
    fused, visit, tapped, lines, _ = fusing(context, monkeypatch, {}, *with_ids([("Bleed", 2)] * 5))
    assert fused and tapped.count(actions.FUSE_DIALOG_CONFIRM) == 1
    assert read_again(lines)[0] < lines.index("shop: 2 materials on show, a fusion takes 3")
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
    assert recipe < read_again(lines)[0] < ordinary
    assert actions.PAGE_CLOSE in after_last(tapped, actions.FUSE_DIALOG_CONFIRM)
    assert visit["fuse_scanned"]


def test_a_page_closes_after_fusions_per_page_and_leaves_the_rest_to_the_next_round(context, monkeypatch):
    # The bound: FUSIONS_PER_PAGE fusions on one page, then it is closed with a log line; the owned gifts changed, so the next
    # round of Shop.run opens it again (fuse_scanned stays False).
    monkeypatch.setattr(actions, "FUSIONS_PER_PAGE", 2)
    fused, visit, tapped, lines, _ = fusing(context, monkeypatch, {}, *with_ids([("Bleed", 2)] * 9))
    assert fused and tapped.count(actions.FUSE_DIALOG_CONFIRM) == 2 and len(read_again(lines)) == 1
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
    assert read_again(lines) and "shop: no E.G.O Gifts Owned on the fuse page: nothing read" not in lines
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


GRID = actions.OWNED_GRID["fuse"][:2]
# The fuse page's owned gifts (tier, keyword, id) before a fusion of the live runs of 2026-11-03/04 (#378's logs, the
# "fuse cells" lines), the places of its materials, the tier made, the gift made and the ids after it, in order.
LIVE = {
    "materials of three tiers": (
        [(3, "Keywordless", 9273), (3, "Poise", 9130), (3, "Poise", 9073), (3, "Poise", 9056), (3, "Tremor", 9024),
         (2, "Poise", 9046), (2, "Poise", 9066), (2, "Poise", 9177), (2, "Poise", 9129), (2, "Poise", 9051),
         (2, "Pierce", 9198), (1, "Poise", 9063), (1, "Poise", 9128), (1, "Poise", 9127), (1, "Poise", 9097),
         (1, "Keywordless", 9002), (1, "Bleed", 9192), (1, "Charge", 9069)],
        [15, 10, 4], 3, 9115, [9273, 9130, 9073, 9056, 9115, 9046, 9066, 9177, 9129, 9051, 9063, 9128, 9127, 9097, 9192, 9069]),
    "a tier II made, another keyword": (
        [(3, "Keywordless", 9273), (3, "Poise", 9130), (3, "Poise", 9073), (3, "Poise", 9056), (3, "Tremor", 9115),
         (2, "Poise", 9046), (2, "Poise", 9066), (2, "Poise", 9177), (2, "Poise", 9129), (2, "Poise", 9051),
         (1, "Poise", 9063), (1, "Poise", 9128), (1, "Poise", 9127), (1, "Poise", 9097), (1, "Bleed", 9192),
         (1, "Charge", 9069)],
        [15, 14, 4], 2, 9001, [9273, 9130, 9073, 9056, 9046, 9066, 9177, 9129, 9051, 9001, 9063, 9128, 9127, 9097]),
    "materials of one tier": (
        [(3, "Keywordless", 9273), (2, "Poise", 9046), (2, "Keywordless", 9025), (2, "Poise", 9066), (2, "Rupture", 9047),
         (2, "Charge", 9057), (1, "Burn", 9003), (1, "Keywordless", 9010), (1, "Poise", 9063), (1, "Poise", 9128),
         (1, "Poise", 9127)],
        [5, 2, 4], 3, 9130, [9273, 9130, 9046, 9066, 9003, 9010, 9063, 9128, 9127]),
    "the only tier IV a material": (
        [(4, "Poise", 9070), (3, "Keywordless", 9273), (3, "Poise", 9130), (2, "Poise", 9046), (2, "Poise", 9066),
         (2, "Keywordless", 9006), (2, "Poise", 9177), (2, "Poise", 9129), (1, "Burn", 9003), (1, "Keywordless", 9010),
         (1, "Poise", 9063), (1, "Poise", 9128), (1, "Poise", 9127)],
        [8, 9, 0], 3, 9073, [9273, 9130, 9073, 9046, 9066, 9006, 9177, 9129, 9063, 9128, 9127]),
    "a tier the list did not hold": (
        [(3, "Poise", 9056), (3, "Keywordless", 9076), (2, "Slash", 9032), (2, "Rupture", 9047), (2, "Keywordless", 9037),
         (2, "Sinking", 9054), (1, "Keywordless", 9004), (1, "Poise", 9063)],
        [0, 1, 2], 4, 9131, [9131, 9047, 9037, 9054, 9004, 9063]),
    # The vestiges go first whatever their tier (the client's SortByTierPieceFirst), the gift made after them: the IV made
    # lands third, after the Dark Vestige (I) and the IV left (2026-11-04 F5, read again as "no order by tier", 6.83 s).
    "a Dark Vestige ahead of a tier IV": (
        [(1, "Keywordless", 9991), (4, "Poise", 9131), (3, "Keywordless", 9273), (3, "Poise", 9073), (3, "Poise", 9130),
         (3, "Poise", 9056), (3, "Keywordless", 9067), (3, "Keywordless", 9038), (3, "Keywordless", 9190), (3, "Slash", 9821),
         (2, "Poise", 9046), (2, "Poise", 9177), (2, "Poise", 9178), (2, "Poise", 9066), (2, "Poise", 9129), (2, "Poise", 9051),
         (2, "Tremor", 9820), (1, "Poise", 9063), (1, "Poise", 9128), (1, "Poise", 9127), (1, "Poise", 9097)],
        [16, 6, 7], 4, 9070, [9991, 9131, 9070, 9273, 9073, 9130, 9056, 9190, 9821, 9046, 9177, 9178, 9066, 9129, 9051, 9063,
                              9128, 9127, 9097]),
    # A Twinkling Vestige (III) first, then A Certain Philosophy (EX, tier V in the data: the 2026-11-04 recording shows it at
    # place 1, the log's read skipped it as no gift), then the III run; the vestige fused, the III made goes last of the IIIs.
    "a vestige and an EX gift ahead of a tier III": (
        [(3, "Keywordless", 9993), (5, "Keywordless", 9799), (3, "Keywordless", 9273), (3, "Poise", 9130), (3, "Poise", 9073),
         (2, "Poise", 9046), (2, "Poise", 9066), (2, "Poise", 9129), (2, "Poise", 9178), (2, "Sinking", 9061),
         (2, "Poise", 9051), (1, "Poise", 9063), (1, "Rupture", 9013), (1, "Poise", 9128)],
        [12, 9, 0], 3, 9056, [9799, 9273, 9130, 9073, 9056, 9046, 9066, 9129, 9178, 9051, 9063, 9128]),
}


def listed(gifts):
    """Cells as owned_cells reads them, of (tier, keyword, id)."""
    return [{"i": i, "tier": t, "keyword": k, "id": g} for i, (t, k, g) in enumerate(gifts)]


@pytest.mark.parametrize("before, gone, tier, made, after", LIVE.values(), ids=list(LIVE))
def test_the_gift_made_goes_last_of_its_tier_as_on_the_live_fuse_pages(before, gone, tier, made, after):
    # The list goes by tier, highest first, the vestiges ahead; the materials go out, the rest keep their order, and the
    # gift made goes after the vestiges, last of its tier's run (29 of the 30 fusions read again in the live logs; the 30th
    # failed and gave an EX gift). Its id is unknown until read; the places run on.
    new, k = actions.shop.fusion_places(listed(before), gone, tier, GRID)
    assert [c["id"] for c in new] == [None if g == made else g for g in after]
    assert k == after.index(made) and new[k]["tier"] == tier and new[k]["keyword"] is None
    assert [(c["i"], c["x"], c["y"]) for c in new] == [(i, 678 + 96 * (i % 5), 294 + 92 * (i // 5)) for i in range(len(after))]


def test_a_super_shops_five_materials_go_out_at_once():
    # II + II + II + I + I (24 points, a Super Shop's IV): the IV goes first, the gifts left keep their order.
    gifts = [(3, "Poise", 1), (3, "Poise", 2), (2, "Bleed", 3), (2, "Bleed", 4), (2, "Bleed", 5), (1, "Burn", 6),
             (1, "Burn", 7), (1, "Burn", 8), (1, "Burn", 9)]
    new, k = actions.shop.fusion_places(listed(gifts), [2, 3, 4, 7, 8], 4, GRID)
    assert k == 0 and [c["id"] for c in new] == [None, 1, 2, 6, 7]


@pytest.mark.parametrize("gifts, gone, tier", [
    ([(2, "Burn", 1), (2, "Burn", 2), (1, "Burn", 3)], [0], None),  # the tier made unknown
    ([(2, "Burn", 1), (None, "Burn", 2), (1, "Burn", 3)], [0], 2),  # a tier unread
    ([(1, "Burn", 1), (2, "Burn", 2), (1, "Burn", 3)], [0], 2),  # not by tier
    ([(2, "Burn", 1), (2, "Burn", 2), (1, "Burn", 3)], [5], 2),  # a material not among the places read
    ([(2, "Burn", 1), (1, "Keywordless", 9991), (1, "Burn", 3)], [0], 2),  # a vestige after another gift
    ([(1, "Keywordless", 9991), (3, "Keywordless", 9993), (2, "Burn", 3)], [2], 2),  # the vestiges not by tier
])
def test_no_order_is_made_up_from_a_read_that_does_not_give_it(gifts, gone, tier):
    assert actions.shop.fusion_places(listed(gifts), gone, tier, GRID) is None
    cells = listed(gifts[:1] + gifts[2:])
    cells[1]["i"] = 2  # place 1 not read
    assert actions.shop.fusion_places(cells, [0], 2, GRID) is None


def placed_lines(lines):
    return [m for m in lines if m.startswith(PLACED)]


def three_tiers(grid, **gifts):
    """A grid of 16 gifts by tier (III x5, II x6, I x5) whose list keeps all but III 4, II 10 and I 13-15 (#378's F5): a
    fusion of 4, 10 and 15 (19 points: III), then of the III made with 13 and 14 (16 points: II)."""
    return grid("fuse", 16, tiers=[3] * 5 + [2] * 6 + [1] * 5, makes=by_points(), **gifts), kept_but(16, 4, 10, 13, 14, 15)


def test_after_a_fusion_only_the_gift_made_is_read(context, grid, monkeypatch):
    # The page kept open: the gifts left and the gift made are placed by the fusion, only the gift made's cell is read
    # (cell 4, last of the tier III run), and the next fusion takes it in. No gift the list keeps is tapped.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g, team = three_tiers(grid)
    assert fusion(context, monkeypatch, g, team)
    assert placed_lines(lines) == [PLACED + "4)", PLACED + "9)"] and not read_again(lines)  # the II made: last of 5 II
    assert g.reads == list(range(16)) + [1001, 1002]
    assert sorted(g.tapped) == [4, 10, 13, 14, 15, 1001] and 1001 in g.tapped[3:]
    second = [m for m in lines if m.startswith("shop: fuse cells")][1]
    assert f"; 4 III {KEYWORDS[1001 % len(KEYWORDS)]} unknown (best 0.90): material, drop; " in second  # the III made, as read


def test_a_super_shops_gift_made_is_placed_too(context, grid, monkeypatch):
    # A Super Shop's 5 slots: five I (15 points, a III by its thresholds) go out, the III made goes first.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 12, tiers=[2] * 6 + [1] * 6, makes=by_points(5))
    assert fusion(context, monkeypatch, g, kept_but(12, 6, 7, 8, 9, 10, 11), slots=5)
    assert placed_lines(lines) == [PLACED + "0)"] and g.reads == list(range(12)) + [1001]
    assert len(g.tapped) == 5 and set(g.tapped) <= {6, 7, 8, 9, 10, 11}


def test_a_gift_made_not_where_the_fusion_puts_it_has_the_owned_gifts_read_again(context, grid, monkeypatch):
    # No gift shows at cell 5, last of the tier I run: placed by their label once more, the same; read again.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 8)  # the gift made left out
    assert fusion(context, monkeypatch, g, kept_but(8, 0, 1, 2))
    assert KEPT + "the gift made reads no gift at cell 5, the owned gifts are placed by their label" in lines
    assert KEPT + "the gift made reads no gift at cell 5" + READ_AGAIN in lines
    assert g.reads == list(range(8)) + list(range(3, 8)) and not placed_lines(lines)


@pytest.mark.parametrize("same_id", [False, True])
def test_a_gift_made_that_looks_like_a_gift_listed_is_its_twin_only_by_the_same_id(context, grid, monkeypatch, same_id):
    # Live 2026-11-04 (F3): Old Wooden Doll (II), the gift made, showed at its place, but its centre was within GRID_SAME of
    # Finifugality's (III, cell 2): "cell 9, the gift made, looks like cell 2", twice, then read again (6.76 s). Its id read
    # is another gift's: it is placed. A look-alike that reads the same id may be that gift still: read again.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g, team = three_tiers(grid)
    made = g.fused

    def fused(gifts):
        made(gifts)
        if g.made == 1:  # the III made (cell 4) shows cell 2's icon
            g.icons[g.ids.index(1001)] = g.icons[g.ids.index(2)].copy()
            if same_id:
                g.names[1001] = UNLISTED + 2
    monkeypatch.setattr(g, "fused", fused)
    assert fusion(context, monkeypatch, g, team)
    twin = KEPT + "cell 4, the gift made, looks like cell 2"
    if same_id:
        assert twin + ", the owned gifts are placed by their label" in lines and twin + READ_AGAIN in lines
    else:
        assert placed_lines(lines) == [PLACED + "4)", PLACED + "9)"] and not read_again(lines)
        assert g.reads == list(range(16)) + [1001, 1002]


def test_a_fusion_whose_get_popup_shows_ex_places_the_ex_gift_as_tier_v(context, grid, monkeypatch):
    # #449, live 2026-11-04 (F2's second fusion): forecast IV at 99%, the fusion gave A Certain Philosophy (EX, tier V in the
    # data); read as tier V where the forecast's tier was made, the owned gifts were read again. Its GET! popup (the
    # recording's frame, over the page left of the grid from the fusion's Confirm until its own) shows the green "EX": the
    # gift made is tier V, placed ahead of the IIIs and read there alone. The fusion: III 4, II 10 and I 15 (a III by points).
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 16, tiers=[3] * 5 + [2] * 6 + [1] * 5, makes=lambda tiers, ids: (5, EX))
    popup = test_shop.screen_with("get_ex")

    def screen():
        image = g.screen()
        if actions.FUSE_DIALOG_CONFIRM in g.taps and actions.GET_CONFIRM not in after_last(g.taps, actions.FUSE_DIALOG_CONFIRM):
            image[160:500, 300:640] = popup[160:500, 300:640]
        return image
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = screen
    assert fusion(context, monkeypatch, g, kept_but(16, 4, 10, 13, 14, 15))
    assert "shop: the GET! popup shows an EX gift (green EX): the gift made is placed as tier V" in lines
    assert placed_lines(lines) == [PLACED + "0)"] and not read_again(lines)
    assert g.reads == list(range(16)) + [1001]


def test_an_unselectable_cell_is_kept_whatever_the_list_says():
    # #378: the fuse page tags A Certain Philosophy (EX, the gift a 99% fusion gives when it fails) Unselectable: the page
    # takes it in no fusion, so it is no material even when the list drops it.
    team = shop_team({"list": wants()})
    cell = {"i": 0, "tier": 5, "keyword": "Keywordless", "id": 9799, "unselectable": True}
    assert actions.cell_state(cell, team["list"]) == "drop"
    assert actions.cell_role(cell, team, "fuse", ()) == "keep"
    assert actions.cell_role(cell, team, "fuse", (9799,)) == "keep"  # nor as a gift the team avoids
    assert actions.cell_line({**cell, "score": 0.78}, "keep") == "0 V Keywordless 9799 A Certain Philosophy (0.78) unselectable: keep"


def test_a_cell_placed_by_the_fusion_that_is_not_there_has_the_page_opened_again(context, grid, monkeypatch):
    # The gifts placed by the first fusion are not where they were put (each shows another gift than the one read there):
    # the next fusion's first cell does not match its look, so nothing is tapped; the page is closed and opened again,
    # its gifts read from the top, and the fusion made then.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g, team = three_tiers(grid)
    place, placed = actions.fused_cells, []

    def fused_cells(*args):
        out = place(*args)
        if out and not placed:
            placed.append(out)
            for c in out:
                c["look"] = 255 - c["look"]
        return out
    monkeypatch.setattr(actions, "fused_cells", fused_cells)
    assert fusion(context, monkeypatch, g, team)
    assert "shop: a cell placed by the fusion is not where it was put: the fuse page is opened again" in lines
    assert g.taps.count(actions.SHOP_BUTTONS["fuse"]) == 2 and g.taps.count(actions.FUSE_DIALOG_CONFIRM) == 2
    assert sorted(g.tapped) == [4, 10, 13, 14, 15, 1001]  # each material once, nothing else


def test_a_recipe_gift_is_placed_after_its_section_goes(context, grid, monkeypatch):
    # Soothe the Dead's materials (III 9053, III 9157, I 9003) under a Fusion Available section of 7 cells that goes with the
    # fusion (#304): the owned gifts are placed by their label, Soothe the Dead (IV) read at cell 0, nothing else read.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    recipe = {1: 9053, 2: 9157, 7: 9003}
    g = grid("fuse", 10, recipes=7, tiers=[3, 3, 3, 2, 2, 2, 1, 1, 1, 1], names=recipe,
             makes=lambda tiers, ids: (4, SOOTHE) if sorted(ids) == sorted(recipe.values()) else None)
    made = g.fused
    monkeypatch.setattr(g, "fused", lambda gifts: made(gifts) or g.drop_section())
    team = shop_team({"list": wants(SOOTHE, keep=[UNLISTED + i for i in range(10)])})
    assert fusion(context, monkeypatch, g, team)
    assert placed_lines(lines) == [PLACED + "0)"] and not read_again(lines)
    assert g.reads == list(range(10)) + [1001] and sorted(g.tapped) == [1, 2, 7]
    second = [m for m in lines if m.startswith("shop: fuse cells")][1]
    assert f") 0 IV {KEYWORDS[1001 % len(KEYWORDS)]} {SOOTHE} Soothe the Dead (0.90): keep, want; " in second


def test_a_section_that_comes_with_the_fusion_has_the_owned_gifts_placed_by_their_label(context, grid, monkeypatch):
    # The III made completes a fixed recipe's materials: a Fusion Available section of 2 cells comes over the owned gifts,
    # which move down a row and the label (#304). The cells on show are not where the fusion put them; placed by their
    # label, they are, and only the gift made is read.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    g = grid("fuse", 16, tiers=[3] * 5 + [2] * 6 + [1] * 5, makes=by_points())
    made = g.fused
    monkeypatch.setattr(g, "fused", lambda gifts: made(gifts) or g.add_section(2))
    assert fusion(context, monkeypatch, g, kept_but(16, 4, 10, 15))
    assert [m for m in lines if m.startswith(KEPT + "cell ") and m.endswith(", the owned gifts are placed by their label")]
    assert placed_lines(lines) == [PLACED + "4)"] and g.reads == list(range(16)) + [1001]


def test_a_recipe_whose_cell_is_not_where_the_fusion_put_it_is_not_counted_failed(context, monkeypatch):
    # A cell placed by the last fusion that did not show where it was put (cell_at) is no fault of the recipe: the page is
    # opened again and the recipe tried there. A cell read and not there still counts it failed for the visit (#300).
    def place(context, cells, slots, grid, out=False):
        grid["missed"] = True
        return False
    monkeypatch.setattr(actions.Shop, "place", staticmethod(place))
    cells = [{"i": k, "x": 678 + 96 * k, "y": 294, "tier": t, "keyword": "Burn", "id": g, "score": 0.9}
             for k, (t, g) in enumerate([(1, 9003), (3, 9053), (3, 9157)])]
    for placed, failed in ((True, []), (False, [SOOTHE])):
        visit = {}
        grid = {"page": "fuse", "at": 0, "placed": placed, "missed": False}
        assert actions.Shop.fuse_recipe(context, shop_team({"list": wants(SOOTHE)}), cells, grid, 3, visit) is False
        assert visit["recipes_failed"] == failed
