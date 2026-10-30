"""A theme pack card told by its cover art, for the cards whose title OCR cannot name (#274).

Plain data in, plain data out: numpy only. data/theme_pack_signatures.json holds one small colour thumbnail per pack, made
from the cover images of #242 by tools/theme_pack_signatures.py with the same signature() the page's cards go through:
the picture and the title, so covers with the same picture (The Outcast and The Dream Ending) still differ.
"""

import base64
import json
from functools import lru_cache

import numpy as np

from settings import data_dir

SIGNATURES = data_dir() / "theme_pack_signatures.json"  # (#323)
ART = (0.05, 0.18, 0.95, 0.62)  # the part of a card that is its picture (left, top, right, bottom as shares): below the
# search button and warning mark, above the logo and the title
BANDS = ((ART[1], ART[3], 16), (0.74, 0.90, 6))  # top, bottom (shares, ART's left and right) and rows of each part of a
# signature: the picture, then the title; cells about 9 px tall in both
COLUMNS = 12
CARD = (182, 335)  # a card on the 720p page: width, height; its top edge is at y = CARD_TOP
CARD_TOP = 185
PITCH = 210.5  # card centre to card centre; a page of n cards is centred on x = 640
MIN_SCORE = 0.5  # the best cover's correlation with the card, and its lead over the runner-up, that count as a read
MIN_LEAD = 0.1


def signature(image):
    """The BANDS of a card (BGR, any size) as thumbnails of area averages stacked in one, COLUMNS wide, uint8."""
    h, w = image.shape[:2]
    out = []
    for top, bottom, rows in BANDS:
        part = image[int(top * h):int(bottom * h), int(ART[0] * w):int(ART[2] * w)].astype(np.float32)
        for axis, n in ((0, rows), (1, COLUMNS)):
            edges = np.linspace(0, part.shape[axis], n + 1).astype(int)
            part = np.add.reduceat(part, edges[:-1], axis=axis) / np.diff(edges).reshape((-1, 1, 1) if axis == 0 else (1, -1, 1))
        out.append(part)
    return np.rint(np.concatenate(out)).astype(np.uint8)


def encode(sig):
    return base64.b64encode(sig.tobytes()).decode()


@lru_cache(maxsize=1)
def covers():
    """{pack name: signature}"""
    data = json.loads(SIGNATURES.read_text(encoding="utf-8"))
    return {name: np.frombuffer(base64.b64decode(b), np.uint8).reshape(-1, COLUMNS, 3) for name, b in data.items()}


def correlation(a, b):
    a = a.astype(np.float32).ravel() - a.mean()
    b = b.astype(np.float32).ravel() - b.mean()
    return float(a @ b / (np.sqrt((a @ a) * (b @ b)) + 1e-6))


def card_image(page, x):
    """The card whose title is centred on x of a 720p page, BGR. Cards stand on a half-pitch grid around x = 640."""
    centre = 640 + round((x - 640) / (PITCH / 2)) * PITCH / 2
    w, h = CARD
    left = int(centre - w / 2)
    return page[CARD_TOP:CARD_TOP + h, max(0, left):left + w]


def read_cover(page, x, allowed=None):
    """(pack name, correlation) of the cover the card at x looks most like, or None when none stands clear of the next.

    allowed: the names the title already narrowed it to ("Line" reads Line 1 to 5). The lead is taken over all covers
    of that set, so a pack outside it cannot take the card.
    """
    sig = signature(card_image(page, x))
    scores = sorted(((correlation(sig, c), n) for n, c in covers().items() if allowed is None or n in allowed), reverse=True)
    if not scores or scores[0][0] < MIN_SCORE:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < MIN_LEAD:
        return None
    return scores[0][1], scores[0][0]
