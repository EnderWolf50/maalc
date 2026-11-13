"""The shop's cell taps on the fuse and sell pages (#611): a tap the game did not take (the screen reads back as before
it, read again once it stops) is tapped once more; only a second one gives up. A read-back that is neither as before nor
the one meant gives up at once: the first tap may have been taken."""
import pytest

import actions
import shop_actions
import test_actions
from test_actions import live_shop, sell_page, SELLER, cells_read, with_ids
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # its fixtures
CELLS = [{"i": 10 + k, "x": x, "y": y} for k, (x, y) in enumerate(shop_actions.FUSE_CELLS[:3])]


def placing(context, monkeypatch, reads, out=False):
    """Shop.place of CELLS (into the fusion, or out) on a page whose every read-back (after a tap, and again once the
    screen stops) is the next of reads ((materials in, the tapped cell framed)); (its result, the cells tapped by their
    i, the log lines)."""
    lines, tapped, now = [], [], {"cell": None}
    reads = iter(reads)
    patch_all(monkeypatch, "log", lines.append)
    patch_all(monkeypatch, "cell_at", lambda context, grid, c: now.update(cell=c["i"]) or (c["x"], c["y"]))
    patch_all(monkeypatch, "page_guard", lambda context, home, image=None: None)
    patch_all(monkeypatch, "tap_moved", lambda context, x, y, timeout=0.5: tapped.append(now["cell"]))
    patch_all(monkeypatch, "still", lambda context, timeout=2.0, **k: None)
    patch_all(monkeypatch, "screen", lambda context: (len(CELLS) if out else 0, out))
    patch_all(monkeypatch, "close_tooltip", lambda context, page, force=False: next(reads))
    monkeypatch.setattr(actions.shop, "placed", lambda image, n: image[0])
    monkeypatch.setattr(actions.shop, "picked", lambda image, x, y, bottom=720: image[1])
    done = shop_actions.Shop.place(context, CELLS, 3, {"page": "fuse", "at": 0}, out=out)
    return done, tapped, lines


RETAP = "shop: cell 11 tapped: nothing changed, tapped again"


@pytest.mark.parametrize("out", [False, True])
def test_a_tap_that_changed_nothing_is_made_once_more_and_the_fusion_goes_on(context, monkeypatch, out):
    # #611 (live 2026-11-10): the game showed cell 13 pressed and took nothing in; tapped again, it goes in.
    reads = ([(2, False), (2, True), (2, True), (1, False), (0, False)] if out
             else [(1, True), (1, False), (1, False), (2, True), (3, True)])
    done, tapped, lines = placing(context, monkeypatch, reads, out)
    assert done and tapped == [10, 11, 11, 12]
    assert lines == [RETAP]


@pytest.mark.parametrize("out", [False, True])
def test_two_taps_that_change_nothing_give_up_as_before(context, monkeypatch, out):
    reads = [(2, False), (2, True), (2, True), (2, True)] if out else [(1, True), (1, False), (1, False), (1, False)]
    done, tapped, lines = placing(context, monkeypatch, reads, out)
    assert not done and tapped == [10, 11, 11]
    assert lines == [RETAP, "shop: cell 11 tapped: " + ("2 materials in, framed: not taken out" if out
                                                         else "1 materials in, not framed: no fusion")]


@pytest.mark.parametrize("out", [False, True])
def test_a_tap_taken_late_shows_once_the_screen_stops_and_is_not_made_again(context, monkeypatch, out):
    # The read-back straight after the tap is as before, the one once the screen stops shows it taken: a second tap would
    # undo it.
    reads = [(2, False), (2, True), (1, False), (0, False)] if out else [(1, True), (1, False), (2, True), (3, True)]
    done, tapped, lines = placing(context, monkeypatch, reads, out)
    assert done and tapped == [10, 11, 12] and lines == []


@pytest.mark.parametrize("out", [False, True])
@pytest.mark.parametrize("read", ["count", "frame"])
def test_a_read_back_that_is_not_as_before_gives_up_with_no_second_tap(context, monkeypatch, out, read):
    # Another slot count, or the tapped cell's frame turned with the count unchanged: the tap may have been taken, and a
    # second one would take the material out again (or put it back). (Another cell framed is not seen: shop.picked looks
    # at the tapped cell only, as before #611.)
    wrong = {"count": (0, True) if out else (3, False), "frame": (2, False) if out else (1, True)}[read]
    reads = [(2, False) if out else (1, True), wrong]
    done, tapped, lines = placing(context, monkeypatch, reads, out)
    assert not done and tapped == [10, 11]
    assert len(lines) == 1 and lines[0].startswith("shop: cell 11 tapped: ") and "tapped again" not in lines[0]


def test_a_sell_cell_tap_that_picked_nothing_is_made_once_more(context, monkeypatch):
    # #611: Sell asks nothing and the Cost shows no preview (51, not "51 > 146"): the cell tap was lost, so the cell is
    # tapped once more and Sell again; the sale goes through.
    taps, logs = selling(context, monkeypatch, lost=1)
    assert taps.count(shop_actions.SELL_CELLS[0]) == 2 and SELL_RETAP in logs
    assert "shop: sold cell 0 for 95: 51 -> 146 Cost" in logs


def test_two_sell_cell_taps_that_pick_nothing_sell_nothing_as_before(context, monkeypatch):
    taps, logs = selling(context, monkeypatch, lost=2)
    assert taps.count(shop_actions.SELL_CELLS[0]) == 2 and logs.count(SELL_RETAP) == 1
    assert "shop: sell cell 0 for 95: not sold, 51 -> 51 Cost" in logs


def test_a_sell_cell_picked_whose_sell_tap_was_lost_is_not_tapped_again(context, monkeypatch):
    # The Cost previews the sale ("51 > 146" reads 51146): the cell was picked, and a second tap would unpick it.
    taps, logs = selling(context, monkeypatch, lost=0, sell_lost=True)
    assert taps.count(shop_actions.SELL_CELLS[0]) == 1 and SELL_RETAP not in logs
    assert any("not sold" in line for line in logs)


SELL_RETAP = "shop: sell cell 0 tapped: nothing picked, tapped again"


def selling(context, monkeypatch, lost, sell_lost=False):
    """Shop.sell on sell_page (#174) whose first `lost` taps on the cell the game did not take (and, sell_lost, every
    Sell tap); (the taps, the log lines)."""
    page = sell_page(lambda taps: actions.DIALOG_CONFIRM in taps)

    def reads_now(taps):
        cell = [k for k, t in enumerate(taps) if t == shop_actions.SELL_CELLS[0]]
        taken = [t for k, t in enumerate(taps) if k not in cell[:lost]]
        if sell_lost:
            taken = [t for t in taken if t != shop_actions.PAGE_OK]
        shown = page(taken)
        if shop_actions.SELL_CELLS[0] not in taken:
            shown[tuple(actions.DIALOG_TEXT)] = []  # Sell with nothing picked asks nothing
        return shown
    taps = live_shop(context, reads_now)
    cells_read(monkeypatch, *with_ids([("Bleed",)]))
    patch_all(monkeypatch, "cell_at", lambda context, grid, c: (c["x"], c["y"]))  # this page's screen is no grid
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    shop_actions.Shop.sell(context, SELLER, {"wanted": 145, "sold": False})
    return taps, logs
