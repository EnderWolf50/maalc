"""Pass Missions page (#371): which rows of the Daily or Weekly tab have a reward to claim.

Five rows sit at fixed places (720p). A row is read from its look, not from OCR: a claimed row wears the red CLEAR
stamp, a row under way (3/5) has a short bar, and a row whose icon is lit with a full bar and no stamp waits for a
tap. Live 2026-10-26 only the claimed look (both tabs) and the under-way look (a weekly row) were captured: a row that
waits for a tap is read from them, unverified until one is seen.
"""

import numpy as np
from maa.context import Context
from maa.custom_recognition import CustomRecognition

ROWS_Y = (225, 312, 400, 487, 575)  # the rows' centres
ICON_X = 370  # the coin at the row's left, which a tap claims
# The three thresholds, swept over every 720p image of tests/screens (151, 2026-10-26; test_pass_missions.py): only the
# synthetic claimable row passes all three. On the pass pages a lit coin reads 405 and a grey one 0; the stamp 175-224
# and 0 without it; a full bar 175 and the 3/5 one 105. Other screens light up to 662 coin pixels in a row's square, but
# none of them has a bar over 144 there.
LIT = 100  # orange pixels of the coin's 40 x 40 square: lit; a claimed row's grey coin has none
STAMP = 50  # red pixels of the CLEAR stamp (x 600-700): ~180 where it is, 0 where it is not
BAR = 170  # of the bar's 175 columns bright: full


def claimable(image):
    """Centres (x, y) of the rows to tap, top to bottom; image is a 720p BGR frame."""
    found = []
    for y in ROWS_Y:
        b, g, r = (image[y - 20:y + 20, 350:390, i].astype(int) for i in range(3))
        stamp = image[y - 25:y + 25, 600:700].astype(int)
        red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()
        full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()
        if ((r > 200) & (g > 100) & (b < 80)).sum() > LIT and red < STAMP and full >= BAR:
            found.append((ICON_X, y))
    return found


class PassClaimable(CustomRecognition):
    """The first row to tap, as a 40 x 40 box on its coin; no hit when every row is claimed or under way."""

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        rows = claimable(np.asarray(argv.image))
        return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), detail={"rows": rows}) if rows else None
