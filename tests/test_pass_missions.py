"""Pass Missions rows to claim (#371): which rows of a tab the bot taps."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import pass_missions

SCREENS = Path(__file__).parent / "screens"


def rows(png):
    return pass_missions.claimable(np.asarray(Image.open(SCREENS / png).convert("RGB"))[:, :, ::-1])


@pytest.mark.parametrize("png, expected", [
    ("PassMissionsDaily.png", []),  # live 2026-10-26: every row claimed (CLEAR stamp)
    ("PassMissionsWeekly.png", []),  # one row under way, 3/5: a short bar, nothing to tap
    # Synthetic: that row with a full bar and no count; no live capture of a row that waits for a tap yet.
    ("PassMissionsWeeklyClaimable.synthetic.png", [(370, 225)]),
])
def test_claimable_rows(png, expected):
    assert rows(png) == expected
