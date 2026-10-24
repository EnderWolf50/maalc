"""#285: the fuse page's Forecasts row is read before Fuse; a tier the gift list's fusion_condition refuses is not fused."""
from types import SimpleNamespace

import numpy as np
import pytest

import actions
import test_actions
from test_shop import screen_with

clock, context = test_actions.clock, test_actions.context  # its fixtures
CHANCE = {tuple(actions.FORECAST_CHANCE): [("90%", (430, 456, 40, 24))]}
THREE_THREE_TWO = [("Bleed", 3), ("Tremor", 3), ("Pierce", 2)]  # 26 points: a IV by the points


def fuse(context, monkeypatch, team, readings, page, chance=True, slots=3, stuck=False, framed=False, visit=None, get=True):
    """Shop.fuse on readings (test_actions.cells_read), the page forecasting page.get(the cells in, as a sorted tuple) (a tier, or
    nothing: the row does not read; page: a dict, or anything with .get). get: the page reads "GET!" after a fusion; stuck: a material tapped in cannot be taken out again, framed: it goes out but its frame stays lit; visit: the shop visit's dict.
    Returns (fused, how often each cell was tapped, whether Fuse was pressed, the log lines)."""
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    reads_ = {**test_actions.FUSE_PAGE, tuple(actions.FUSE_CONFIRM): [(f"Selected E.G.O Gifts 3/{slots}", (330, 175, 320, 30))],
              **({tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]} if get else {}), **(CHANCE if chance else {})}
    test_actions.reads(context, reads_)

    def taps():
        return [c.args for c in context.tasker.controller.post_click.call_args_list]

    def inside():
        n = [taps().count(c) for c in actions.FUSE_CELLS]
        return {i for i, k in enumerate(n) if (k and stuck) or k % 2}
    monkeypatch.setattr(actions.shop, "fuse_slots", lambda image: slots)
    monkeypatch.setattr(actions.shop, "placed", lambda image, n: len(inside()))
    monkeypatch.setattr(actions.shop, "picked", lambda image, x, y, bottom=720: actions.FUSE_CELLS.index((x, y)) in (
        {i for i, c in enumerate(actions.FUSE_CELLS) if taps().count(c)} if framed else inside()))
    monkeypatch.setattr(actions.shop, "forecast_tier", lambda image: page.get(tuple(sorted(inside()))))
    test_actions.cells_read(monkeypatch, *test_actions.with_ids(readings))
    fused = actions.Shop.fuse(context, test_actions.shop_team(team), {} if visit is None else visit)
    return fused, [taps().count(c) for c in actions.FUSE_CELLS[:len(readings)]], actions.PAGE_OK in taps(), lines



def forecast_line(lines):
    return [m for m in lines if "fuse forecast" in m]


def test_a_forecast_the_condition_accepts_is_fused(context, monkeypatch):
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "tier4"}, THREE_THREE_TWO, {(0, 1, 2): 4})
    assert fused and ok and taps == [1, 1, 1]
    assert len(forecast_line(lines)) == 1
    assert forecast_line(lines)[0].endswith("points tier 4, page tier 4, chance 90%, condition tier4: fuse")
    assert any("into a tier 4 Burn gift (condition tier4): done" in m for m in lines)


@pytest.mark.parametrize("condition", ["upgrade", "tier4"])
def test_a_forecast_the_condition_refuses_is_not_fused_and_the_materials_come_out(context, monkeypatch, condition):
    # The points say IV (a III + III + II), the page says III: no upgrade over its III, no IV. Nothing else makes a fusion
    # the condition takes, so the page ends with the materials out and no Fuse pressed.
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": condition}, THREE_THREE_TWO, {(0, 1, 2): 3}, get=False)
    assert not fused and not ok
    assert taps == [2, 2, 2]  # each in, then out
    assert "page tier 3, chance 90%" in forecast_line(lines)[0] and forecast_line(lines)[0].endswith("turned down")
    assert any("1 turned down by the page's forecast" in m for m in lines)


def test_a_refused_group_is_left_out_and_the_next_one_is_tried(context, monkeypatch):
    # upgrade: III + III + II (cells 0, 1, 2) is the best group; the page turns it down. III + III + II with the other II
    # (cells 0, 1, 3) would read the same: not tried. II + II + II (a III over a II) is, and the page takes it.
    cells = [("Bleed", 3), ("Tremor", 3), ("Pierce", 2), ("Slash", 2), ("Sinking", 2)]
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "upgrade"}, cells, {(0, 1, 2): 3, (2, 3, 4): 3})
    assert fused and ok
    assert taps == [2, 2, 3, 1, 1]  # the III in and out; the first II in, out, in; the others in once
    assert [m.rsplit(": ", 1)[1] for m in forecast_line(lines)] == ["turned down", "fuse"]


def test_the_page_turns_down_at_most_fuse_tries_groups_then_closes(context, monkeypatch):
    # Every group the points allow reads as a III on the page: five groups of different tiers are allowed (tier4), only
    # FUSE_TRIES of them are tried, then the page is closed.
    cells = [("Bleed", t) for t in (4, 3, 3, 2, 2, 2, 1, 1, 1)]
    page = SimpleNamespace(get=lambda key: 3)
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "tier4"}, cells, page, get=False)
    assert not fused and not ok
    assert len(forecast_line(lines)) == actions.FUSE_TRIES
    assert actions.PAGE_CLOSE in [c.args for c in context.tasker.controller.post_click.call_args_list]


def test_an_unread_forecast_falls_back_to_the_points_tier_and_says_so(context, monkeypatch):
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "tier4"}, THREE_THREE_TWO, {}, chance=False)
    assert fused and ok and taps == [1, 1, 1]
    assert forecast_line(lines)[0].endswith("points tier 4, page tier unread, chance unread, condition tier4: fuse on the points tier")


def test_the_condition_any_fuses_whatever_the_page_forecasts(context, monkeypatch):
    # any never refuses: a lower tier than the points give is logged, and fused.
    fused, taps, ok, lines = fuse(context, monkeypatch, {}, THREE_THREE_TWO, {(0, 1, 2): 2})
    assert fused and ok and taps == [1, 1, 1]
    assert "points tier 4, page tier 2" in forecast_line(lines)[0]


def test_materials_that_will_not_come_out_close_the_page(context, monkeypatch):
    # A refused group whose gifts stay in: nothing more is tapped but the Close, and the grid is not read again.
    visit = {}
    cells = [("Bleed", 3), ("Tremor", 3), ("Pierce", 2), ("Slash", 2), ("Sinking", 2)]
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "upgrade"}, cells, {(0, 1, 2): 3}, stuck=True, visit=visit, get=False)
    assert not fused and not ok
    assert taps == [2, 1, 1, 0, 0]  # the first tap out did not show: the rest stay, the next group is not tried
    assert any("not taken out" in m for m in lines)
    assert actions.PAGE_CLOSE in [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert visit["fuse_scanned"]


def test_a_taken_out_material_whose_frame_stays_lit_closes_the_page(context, monkeypatch):
    cells = [("Bleed", 3), ("Tremor", 3), ("Pierce", 2), ("Slash", 2), ("Sinking", 2)]
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "upgrade"}, cells, {(0, 1, 2): 3}, framed=True, get=False)
    assert not fused and not ok and taps == [2, 1, 1, 0, 0]
    assert any("cell 0 tapped: 2 materials in, framed: not taken out" in m for m in lines)


def test_a_group_is_judged_by_its_highest_material_not_its_first(context, monkeypatch):
    # A Super Shop's II + II + III (22 points, a IV by the points) forecast as a III: no upgrade over the III, though over a II.
    fused, taps, ok, lines = fuse(context, monkeypatch, {"fusion_condition": "upgrade"},
                                  [("Bleed", 2), ("Tremor", 2), ("Pierce", 3)], {(0, 1, 2): 3}, slots=5, get=False)
    assert not fused and not ok and taps == [2, 2, 2]


def test_the_forecast_is_read_off_a_live_capture(context, monkeypatch):
    # Live 2026-10-23: a Super Shop's II + II + III: "IV Guaranteed 90%".
    image = screen_with("forecast_super_iv")
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
    test_actions.reads(context, CHANCE)
    assert actions.read_forecast(context) == (4, 90)


def test_the_forecast_waits_for_its_row_but_not_for_long(context, clock):
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = iter(
        [np.zeros((720, 1280, 3), np.uint8)] + [screen_with("forecast_super_iv")] * 3)
    test_actions.reads(context, CHANCE)
    assert actions.read_forecast(context) == (4, 90)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = None
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    assert actions.read_forecast(context) == (None, None)
    assert 1.0 <= sum(clock) < 2.0


CASK_SPIRITS = 9180  # Poise, tier IV


def real_read_cells(monkeypatch, tiers, ids):
    """actions.read_cells itself over the first cells of any grid, whose numerals read `tiers` and whose icons cell_id names
    `ids`: only the pixel reading is replaced."""
    spots = actions.FUSE_CELLS[:len(tiers)]
    named = iter(ids)
    monkeypatch.setattr(actions.shop, "filled", lambda image, x, y: (x, y) in spots)
    monkeypatch.setattr(actions.shop, "cell_crop", lambda image, x, y, scale: (x, y))
    monkeypatch.setattr(actions.shop, "rescale", lambda image, factor: image)
    monkeypatch.setattr(actions.shop, "tier", lambda crop: tiers[spots.index(crop)])
    monkeypatch.setattr(actions, "template_hits", lambda *args: [])
    monkeypatch.setattr(actions, "cell_id", lambda context, grid, at, keyword, tier: (next(named), 0.9))


def test_a_cell_named_by_a_gift_of_another_tier_takes_that_gifts_tier(context, monkeypatch):
    # #330: the numeral read II, the icon is Cask Spirits (IV): the cell is a IV, not what the numeral said.
    real_read_cells(monkeypatch, [2, 3, 3], [CASK_SPIRITS, 9071, 9053])
    cells = actions.read_cells(context, np.zeros((720, 1280, 3), np.uint8), actions.FUSE_CELLS[:3], "fuse")
    assert [(c["id"], c["tier"]) for c in cells] == [(CASK_SPIRITS, 4), (9071, 3), (9053, 3)]


def test_a_misread_tier_does_not_make_a_fusion_the_condition_refuses(context, monkeypatch):
    # #330 with #285: Cask Spirits (IV) read as II, with two III: by the points II + III + III is a IV, an upgrade, and the page
    # forecasts IV, so it would be fused. It is IV + III + III: a IV again, no upgrade over its IV. Nothing is tapped in.
    real_read_cells(monkeypatch, [2, 3, 3], [CASK_SPIRITS, 9071, 9053])
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    test_actions.reads(context, {**test_actions.FUSE_PAGE, tuple(actions.FUSE_CONFIRM): [("Selected E.G.O Gifts 3/3", (330, 175, 320, 30))],
                                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))], **CHANCE})
    test_actions.fuse_slots(context, monkeypatch)
    monkeypatch.setattr(actions.shop, "forecast_tier", lambda image: 4)
    fused = actions.Shop.fuse(context, test_actions.shop_team({"fusion_condition": "upgrade"}), {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    assert not fused and not set(taps[4:]) & set(actions.FUSE_CELLS)
    assert actions.PAGE_OK not in taps
