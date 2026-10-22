"""#215: the battle pause menu and the Dungeon Progress panel are closed by Resume / Continue, never Give Up / Forfeit.

Button rectangles (x, y, w, h in game pixels) are measured on the live captures tests/screens/BattleMenu.png and
DungeonProgress*.png.
"""
import re
from pathlib import Path

import numpy as np
import pytest
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image
from test_pipeline import load_nodes, strip, template_first

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "tests/screens"
IMAGES = REPO / "assets/resource/base/image"

# The pause menu's four bars, top to bottom: only Resume is pressed; Retry Stage and Give Up end the stage.
BATTLE_BARS = {"Settings": (505, 241, 270, 41), "Resume": (505, 296, 270, 41),
               "Retry Stage": (505, 352, 270, 41), "Give Up": (505, 408, 270, 41)}
# The panel's five buttons, left to right: only Continue is pressed; Forfeit gives the run up, To Window pauses it.
PANEL_BUTTONS = {name: (x, 373, 83, 125) for name, x in
                 [("Progress", 402), ("Forfeit", 500), ("Continue", 598), ("To Window", 696), ("Config", 794)]}
BATTLE_MENU_SHOTS = ["BattleMenu.png", "BattleMenuClosing.png"]


def inside(box, rect):
    x, y, w, h = box
    rx, ry, rw, rh = rect
    return rx <= x and ry <= y and x + w <= rx + rw and y + h <= ry + rh


def touches(box, rect):
    x, y, w, h = box
    rx, ry, rw, rh = rect
    return x < rx + rw and rx < x + w and y < ry + rh and ry < y + h


def gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def best_match(image, template, roi):
    """(score, box) of the best normalised cross-correlation of template inside roi (OpenCV's TM_CCOEFF_NORMED)."""
    x, y, w, h = roi
    th, tw = template.shape
    windows = sliding_window_view(image[y:y + h, x:x + w], (th, tw)).reshape(-1, th * tw)
    windows = windows - windows.mean(axis=1, keepdims=True)
    t = (template - template.mean()).ravel()
    norm = np.sqrt((windows ** 2).sum(axis=1)) * np.sqrt((t ** 2).sum())
    scores = np.divide(windows @ t, norm, out=np.zeros(len(windows), np.float32), where=norm > 0)
    i = int(scores.argmax())
    cols = w - tw + 1
    return float(scores[i]), (x + i % cols, y + i // cols, tw, th)


def battle_menu_match(image):
    node = load_nodes()["BattleMenu"]
    return best_match(image, gray(IMAGES / node["template"]), node["roi"]), node


@pytest.mark.parametrize("shot", BATTLE_MENU_SHOTS)
def test_the_battle_menu_is_found_and_clicked_on_resume_only(shot):
    (score, box), node = battle_menu_match(gray(SCREENS / shot))
    assert node["action"] == "Click" and score >= node["threshold"]
    center = (box[0] + box[2] // 2, box[1] + box[3] // 2, 1, 1)
    assert inside(center, BATTLE_BARS["Resume"])
    assert not any(touches(center, rect) for name, rect in BATTLE_BARS.items() if name != "Resume")


def test_the_battle_menu_roi_holds_the_resume_bar_and_no_other():
    # Whatever the template matches inside the roi, the click cannot reach Give Up or Retry Stage.
    node = load_nodes()["BattleMenu"]
    assert inside(node["roi"], BATTLE_BARS["Resume"])
    assert not any(touches(node["roi"], rect) for name, rect in BATTLE_BARS.items() if name != "Resume")


def test_no_other_screen_reads_as_the_battle_menu():
    # CODING_STANDARDS: a template heuristic ships with a sweep over tests/screens. Live sweep (2026-10-22, 119 images):
    # 1.000 and 0.986 on the two captures of the menu, 0.50 at most on every other screen.
    node = load_nodes()["BattleMenu"]
    template = gray(IMAGES / node["template"])
    others = [p for p in sorted(SCREENS.glob("*.png")) if p.name not in BATTLE_MENU_SHOTS]
    scores = {p.name: best_match(gray(p), template, node["roi"])[0] for p in others
              if Image.open(p).size == (1280, 720)}
    assert len(scores) > 100
    assert {n: s for n, s in scores.items() if s >= node["threshold"] - 0.2} == {}


def test_the_battle_menu_is_answered_before_the_turn_under_it():
    # Live 2026-10-22: the Win Rate label reads through the menu, so PlayTurn tapped it and only closed the menu
    # by chance. BattleHUD tries the menu before BattleTurn and BattlePause, with a template, so a battle round
    # reads no text (#157).
    nodes = load_nodes()
    hud = strip(nodes["BattleHUD"]["next"])
    assert hud.index("BattleMenu") < hud.index("BattleTurn") < hud.index("BattlePause")
    assert nodes["BattleHUD"]["any_of"].index("BattleMenu") < nodes["BattleHUD"]["any_of"].index("BattleTurn")
    assert template_first(nodes, nodes["BattleMenu"])


def test_the_progress_panel_clicks_continue_only():
    node = load_nodes()["ProgressPanel"]
    assert node["action"] == "Click" and re.search(node["expected"], "Continue")
    for other in ["Forfeit", "To Window", "Progress", "Config"]:
        assert not re.search(node["expected"], other)
    # The roi lies within Continue and touches none of the other four buttons: the OCR box clicked is inside it.
    assert inside(node["roi"], PANEL_BUTTONS["Continue"])
    assert not any(touches(node["roi"], rect) for name, rect in PANEL_BUTTONS.items() if name != "Continue")


def test_the_progress_panel_is_answered_before_the_pages_it_opens_over():
    # #215: the back key on an event opens the panel over it; the event's own button (Continue, bottom right) still
    # reads, so its node acted first, and the panel closed by chance. A dialog is answered before the page under it.
    entries = load_nodes()["HubText"]["custom_recognition_param"]["entries"]
    pages = ["Event", "Shop", "GiftGet", "GiftChoice", "RewardCard", "RewardCardForgo", "GiftRefuseDialog", "Victory",
             "WipeDialog", "Formation", "ThemePack"]
    assert all(entries.index("ProgressPanel") < entries.index(p) for p in pages)
    assert entries.index("PopupButton") < entries.index("ProgressPanel")  # the server's popups still come first
