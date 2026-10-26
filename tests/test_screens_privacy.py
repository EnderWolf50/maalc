"""Committed screenshots carry no account identity: the regions that show it are blacked out.

Three things on a 1280x720 capture show the account: the e-mail next to "GOOGLE" at the foot of the title
screen (and every dialog drawn over it), the player-number plate on the main window, and the player name
under the LV/inventory panel at the bottom left of the main window, the Drive and the Sinners tab. The
rectangles below were measured on the committed fixtures (the pure-black boxes in them), in game pixels.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SCREENS = Path(__file__).parent / "screens"

TITLE_EMAIL = (1055, 658, 136, 31)  # title-screen dialogs: TryAgain, RetryCountdown, MaintenanceNotice, ...
TITLE_EMAIL_SMALL = (1060, 662, 120, 22)  # the plain title screens
UID_PLATE = (110, 130, 135, 28)  # main window, next to its Copy button
NAME_PLATE = (36, 626, 98, 20)  # the player name above "LV", on every screen that shows the LV panel

IDENTITY = {
    "TryAgain": [TITLE_EMAIL], "RetryCountdown": [TITLE_EMAIL], "MaintenanceNotice": [TITLE_EMAIL],
    "TitleDownload": [TITLE_EMAIL], "TitleClientOutdated": [TITLE_EMAIL], "TitleErrorConfirm": [TITLE_EMAIL],
    "UserAgreement": [TITLE_EMAIL], "UserAgreementTicked": [TITLE_EMAIL], "UpdateDialog.synthetic": [TITLE_EMAIL],
    "Title": [TITLE_EMAIL_SMALL], "TitleConnecting": [TITLE_EMAIL_SMALL], "TitleFading": [TITLE_EMAIL_SMALL],
    "MainWindow": [UID_PLATE, NAME_PLATE], "MainWindowFadeIn": [UID_PLATE, NAME_PLATE],
    "Drive": [NAME_PLATE], "SinnersTab": [NAME_PLATE],
    # Luxcavation's narrower LV panel: the LV label sits elsewhere (#366)
    "LuxExp": [NAME_PLATE], "LuxExpLocked": [NAME_PLATE], "LuxThread": [NAME_PLATE],
    # the main window dimmed under the Mailbox and the popup: the Copy button and LV label do not match
    "ServerErrorRetry": [UID_PLATE, NAME_PLATE], "ServerErrorRetryCountdown": [UID_PLATE, NAME_PLATE],
    "NetworkUnstable": [UID_PLATE, NAME_PLATE],
    "EventNotices": [UID_PLATE, NAME_PLATE], "SystemNotices": [UID_PLATE, NAME_PLATE],
    "Mailbox": [UID_PLATE, NAME_PLATE], "SettingsMenu": [UID_PLATE, NAME_PLATE],
}

# A new fixture is found by a part of the screen that stays put: it must match Title.png's "Change Account"
# button, MainWindow.png's "Copy" button or its "LV" label (mean grey difference below the tolerance), and
# then needs the matching mask. Over the committed fixtures the LV label is exact (0) on the four screens
# that show it undimmed and 55+ on every other one. A main window dimmed under a popup reads like any other
# screen, so it is listed in IDENTITY by hand.
BUTTONS = [("Title.png", (45, 638, 127, 34), 20, TITLE_EMAIL_SMALL), ("MainWindow.png", (255, 130, 80, 28), 5, UID_PLATE),
           ("MainWindow.png", (36, 647, 18, 14), 5, NAME_PLATE)]


def crop(img, box):
    x, y, w, h = box
    return np.asarray(img.convert("L").crop((x, y, x + w, y + h)), dtype=float)


def required_boxes(png: Path) -> list[tuple]:
    img = Image.open(png)
    boxes = list(IDENTITY.get(png.stem, []))
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


def test_the_name_plate_detector_finds_every_screen_that_shows_the_lv_panel():
    shown = {p.stem for p in SCREENS.glob("*.png") if NAME_PLATE in required_boxes(p)}
    assert shown == {"MainWindow", "MainWindowFadeIn", "Drive", "SinnersTab", "ServerErrorRetry", "ServerErrorRetryCountdown",
                     "NetworkUnstable", "EventNotices", "SystemNotices", "Mailbox", "SettingsMenu",
                     "LuxExp", "LuxExpLocked", "LuxThread"}


def test_an_unmasked_copy_of_a_fixture_fails(tmp_path):
    shot = Image.open(SCREENS / "TryAgain.png").convert("RGB")
    x, y, w, h = TITLE_EMAIL
    shot.paste(Image.new("RGB", (w, h), (200, 200, 200)), (x, y))  # what an unmasked e-mail looks like to the check
    copy = tmp_path / "TryAgain.png"
    shot.save(copy)
    assert TITLE_EMAIL in unmasked(copy)


def test_an_unmasked_player_name_fails_on_a_screen_the_detector_finds_by_itself(tmp_path):
    shot = Image.open(SCREENS / "Drive.png").convert("RGB")
    x, y, w, h = NAME_PLATE
    shot.paste(Image.new("RGB", (w, h), (200, 200, 200)), (x, y))
    copy = tmp_path / "SomeNewMainScreen.png"  # not in IDENTITY: only the LV panel gives it away
    shot.save(copy)
    assert NAME_PLATE in unmasked(copy)
