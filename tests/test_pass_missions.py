"""Pass Missions rows to claim (#371): which rows of a tab the bot taps."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

import pass_missions

SCREENS = Path(__file__).parent / "screens"


def frame(png):
    return np.asarray(Image.open(SCREENS / png).convert("RGB"))[:, :, ::-1]


def rows(png, dy=0):
    return pass_missions.claimable(frame(png), dy)


CLAIMABLE = [(370, 312), (370, 400), (370, 487), (370, 575)]  # PassMissionsDailyClaimable.png's rows 2-5 (live 2026-10-27)


def band(y):
    """The rows of a row centred at y: its whole box, the coin to the bar's end and the stamp."""
    return slice(y - 43, y + 44)


def seasonal_end_claimable():
    """PassMissionsSeasonalEnd.png (the Seasonal tab swiped to its end, live 2026-10-27: its rows 10 px lower than at the
    top) with its first row replaced by a claimable row of PassMissionsDailyClaimable.png, moved down those 10 px."""
    image, row = frame("PassMissionsSeasonalEnd.png").copy(), frame("PassMissionsDailyClaimable.png")
    image[band(235), 330:705] = row[band(312), 330:705]
    return image


def daily_claimed(k):
    """PassMissionsDailyClaimable.png after k taps: its first k claimable rows wear the claimed look (PassMissionsDaily.png's
    row in the same place: a grey coin, the CLEAR stamp)."""
    image, done = frame("PassMissionsDailyClaimable.png").copy(), frame("PassMissionsDaily.png")
    for _, y in CLAIMABLE[:k]:
        image[band(y), 330:705] = done[band(y), 330:705]
    return image


@pytest.mark.parametrize("png, dy, expected", [
    ("PassMissionsDaily.png", 0, []),  # live 2026-10-26: every row claimed (CLEAR stamp)
    ("PassMissionsDailyUnderway.png", 0, []),  # live 2026-10-27: one claimed, four under way (0/1, 0/2, 0/10)
    ("PassMissionsWeekly.png", 0, []),  # one row under way, 3/5: a short bar, nothing to tap
    # live 2026-10-27 (live-1 F7): rows 2-5 wait for a tap (the whole row framed orange, a red ! at its top right, the bar full)
    ("PassMissionsDailyClaimable.png", 0, CLAIMABLE),
    # live 2026-10-27 (live-2 G2), 0.3 s after the tap on row 1: its coin grey, its stamp not in yet; it is not tapped
    # again, so PassFinish's count of taps is the rows claimed (6 that run: Battle Pass XP 4 -> 18, 5 x 2 daily + 4 weekly)
    ("PassMissionsDailyClaiming.png", 0, CLAIMABLE),
    ("PassMissionsSeasonal.png", 0, []),  # live 2026-10-27, D9: the Seasonal tab's top, all claimed
    ("PassMissionsSeasonalEnd.png", 10, []),  # its end after one swipe, all claimed
])
def test_claimable_rows(png, dy, expected):
    assert rows(png, dy) == expected


@pytest.mark.parametrize("png, dy, done", [
    ("PassMissionsDaily.png", 0, [True] * 5),  # every row claimed (CLEAR)
    ("PassMissionsDailyUnderway.png", 0, [True, False, False, False, False]),  # Clear EXP Luxcavation 0/1 is row 2
    ("PassMissionsDailyClaimable.png", 0, [True] * 5),  # row 1 claimed, rows 2-5 full bars to claim
    ("PassMissionsDailyClaiming.png", 0, [True] * 5),
    ("PassMissionsWeekly.png", 0, [False, True, True, True, True]),  # Clear EXP Luxcavation 5 time(s) 3/5 under way
    ("PassMissionsSeasonal.png", 0, [True] * 5),
    ("PassMissionsSeasonalEnd.png", 10, [True] * 5),
])
def test_a_row_is_done_with_its_bar_full_or_its_stamp_on_and_not_while_under_way(png, dy, done):
    # #429: ExpLuxcavation reads its Clear EXP Luxcavation row as "won today" when it is done, claimed or not
    image = frame(png)
    assert [pass_missions.row_done(image, y + dy) for y in pass_missions.ROWS_Y] == done


def test_the_nearest_row_of_a_rows_text():
    assert [pass_missions.nearest_row(y) for y in (200, 299, 387, 560, 700)] == [225, 312, 400, 575, 575]


def test_the_swiped_seasonal_tab_reads_its_rows_10_px_lower():
    assert pass_missions.claimable(seasonal_end_claimable(), 10) == [(370, 235)]


def analyze(image, param=None):
    """PassClaimable.analyze on a frame, with the param the pipeline passes (None: no param)."""
    argv = SimpleNamespace(image=image, custom_recognition_param=None if param is None else json.dumps(param))
    return pass_missions.PassClaimable().analyze(None, argv)


def test_the_recognition_boxes_the_first_row_to_claim_as_40_by_40_on_its_coin():
    # #640 (pass_missions.py:64): no test ran PassClaimable.analyze; the tap lands in the box's middle, on the coin.
    result = analyze(frame("PassMissionsDailyClaimable.png"))
    assert tuple(result.box) == (350, 292, 40, 40)  # centred on CLAIMABLE[0] = (370, 312)
    assert result.detail == {"rows": CLAIMABLE}
    # the swiped Seasonal tab: the param's dy moves the rows down, and the box with them
    result = analyze(seasonal_end_claimable(), {"dy": 10})
    assert tuple(result.box) == (350, 215, 40, 40) and result.detail == {"rows": [(370, 235)]}


def test_the_recognition_has_no_hit_when_no_row_waits_for_a_tap():
    assert analyze(frame("PassMissionsDaily.png")) is None
    assert analyze(seasonal_end_claimable()) is None  # without dy the swiped tab's rows are 10 px off: none lit
    assert analyze(daily_claimed(3)) is not None and analyze(daily_claimed(4)) is None


def test_each_claimed_row_drops_out():
    assert [pass_missions.claimable(daily_claimed(k)) for k in range(5)] == [CLAIMABLE[k:] for k in range(5)]


def test_no_other_screen_has_a_row_to_claim():
    # Review T2, the thresholds' sweep over every 720p image of tests/screens: only the live capture of rows to claim
    # hits. The margins are in pass_missions.py.
    hits = {png.name: found for png in sorted(SCREENS.glob("*.png"))
            if (image := np.asarray(Image.open(png).convert("RGB"))[:, :, ::-1]).shape[:2] == (720, 1280)
            and (found := pass_missions.claimable(image))}
    assert hits == {"PassMissionsDailyClaimable.png": CLAIMABLE, "PassMissionsDailyClaiming.png": CLAIMABLE}


def test_no_screen_has_a_row_to_claim_10_px_lower():
    # D9: the same sweep for the swiped Seasonal tab's rows.
    hits = {png.name: found for png in sorted(SCREENS.glob("*.png"))
            if (image := np.asarray(Image.open(png).convert("RGB"))[:, :, ::-1]).shape[:2] == (720, 1280)
            and (found := pass_missions.claimable(image, 10))}
    assert hits == {}
