"""Committed screenshots carry no account identity: the regions that show it are blacked out.

Two things on a 1280x720 capture show the account: the e-mail next to "GOOGLE" at the foot of the title
screen (and every dialog drawn over it), and the player-number plate on the main window. The rectangles
below were measured on the committed fixtures (the pure-black boxes in them), in game pixels.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SCREENS = Path(__file__).parent / "screens"

TITLE_EMAIL = (1055, 658, 136, 31)  # title-screen dialogs: TryAgain, RetryCountdown, MaintenanceNotice, ...
TITLE_EMAIL_SMALL = (1060, 662, 120, 22)  # the plain title screens
UID_PLATE = (110, 130, 135, 28)  # main window, next to its Copy button

IDENTITY = {
    "TryAgain": TITLE_EMAIL, "RetryCountdown": TITLE_EMAIL, "MaintenanceNotice": TITLE_EMAIL,
    "TitleDownload": TITLE_EMAIL, "TitleErrorConfirm": TITLE_EMAIL,
    "Title": TITLE_EMAIL_SMALL, "TitleConnecting": TITLE_EMAIL_SMALL, "TitleFading": TITLE_EMAIL_SMALL,
    "MainWindow": UID_PLATE, "MainWindowFadeIn": UID_PLATE,
}

# A new fixture is found by a button that stays put on the screen it belongs to: it must match Title.png's
# "Change Account" or MainWindow.png's "Copy" button, and then needs the matching mask.
BUTTONS = [("Title.png", (45, 638, 127, 34), 20, TITLE_EMAIL_SMALL), ("MainWindow.png", (255, 130, 80, 28), 5, UID_PLATE)]


def crop(img, box):
    x, y, w, h = box
    return np.asarray(img.convert("L").crop((x, y, x + w, y + h)), dtype=float)


def required_boxes(png: Path) -> list[tuple]:
    img = Image.open(png)
    boxes = [IDENTITY[png.stem]] if png.stem in IDENTITY else []
    if img.size == (1280, 720):
        for ref, button, tolerance, mask in BUTTONS:
            if np.abs(crop(img, button) - crop(Image.open(SCREENS / ref), button)).mean() < tolerance and mask not in boxes:
                boxes.append(mask)
    return boxes


def unmasked(png: Path) -> list[tuple]:
    img = Image.open(png)
    return [b for b in required_boxes(png) if crop(img, b).max() > 2]


@pytest.mark.parametrize("png", sorted(SCREENS.rglob("*.png")), ids=lambda p: p.name)
def test_identity_regions_are_masked(png):
    assert unmasked(png) == [], f"{png.name}: identity region not blacked out"


def test_every_listed_fixture_exists():
    assert [n for n in IDENTITY if not (SCREENS / f"{n}.png").is_file()] == []


def test_an_unmasked_copy_of_a_fixture_fails(tmp_path):
    shot = Image.open(SCREENS / "TryAgain.png").convert("RGB")
    x, y, w, h = TITLE_EMAIL
    shot.paste(Image.new("RGB", (w, h), (200, 200, 200)), (x, y))  # what an unmasked e-mail looks like to the check
    copy = tmp_path / "TryAgain.png"
    shot.save(copy)
    assert TITLE_EMAIL in unmasked(copy)
