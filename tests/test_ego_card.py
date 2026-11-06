"""#468: an E.G.O card over a battle's planning phase (live 2026-11-07).

The whole battle screen dimmed, one E.G.O card in the middle (Details, To Corrode, the 7 sin costs at its right) and a
bar below it (Resistances, the grade, the E.G.O's name). No battle node knew it, so EXP Luxcavation timed out after
60 s; the back key leaves it up. LuxBattleEgoCard.png is the daily run's EXP battle (a blue card),
BattleEgoCard.png a Mirror Dungeon battle's, opened by a long press on a portrait (a green card). The card's box,
measured on both: x 535-747, y 132-502. A sinner with three E.G.O shows three cards in a row, each with its Details, the
Resistances bar the same (LuxBattleEgoCards.png, the Thread acceptance battle): x 255-1030, y 128-502.
"""
from pathlib import Path

import cv2
from PIL import Image
from test_pause_menus import gray, inside, touches
from test_pipeline import load_nodes, parts, strip, template_first

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "tests/screens"
IMAGES = REPO / "assets/resource/base/image"
SHOTS = ["LuxBattleEgoCard.png", "BattleEgoCard.png", "LuxBattleEgoCards.png"]
CARD_BOX = (535, 132, 212, 370)
CARDS_ROW = (255, 128, 775, 374)  # three cards (LuxBattleEgoCards.png)
# The turn's buttons near the top, measured on BattleTurn.png: WAVE / TURN at the left; the speed, MAX, auto and the
# pause gear at the right, and the box and the red button under them.
TOP_BUTTONS = [(5, 15, 105, 80), (1040, 15, 225, 50), (1080, 70, 185, 55)]


def templates(nodes, spec):
    """(template, roi, threshold) of every TemplateMatch in a node, its And / Or parts included."""
    found = []
    if spec.get("recognition") == "TemplateMatch":
        found.append((spec["template"], spec["roi"], spec["threshold"]))
    for sub in parts(nodes, spec):
        found += templates(nodes, sub)
    return found


def score(image, template, roi):
    """test_pause_menus.best_match's score (grey TM_CCOEFF_NORMED), through OpenCV: the sweep is 200 screens."""
    x, y, w, h = roi
    return float(cv2.matchTemplate(image[y:y + h, x:x + w], gray(IMAGES / template), cv2.TM_CCOEFF_NORMED).max())


def test_the_ego_card_is_found_on_its_capture():
    nodes = load_nodes()
    node = nodes["EgoCard"]
    assert template_first(nodes, node)  # no OCR on a battle round (#157)
    found = templates(nodes, node)
    assert len(found) == 2  # the card's Details and the bar's Resistances: both must show
    for shot in SHOTS:
        image = gray(SCREENS / shot)
        assert all(score(image, t, roi) >= threshold for t, roi, threshold in found), shot


def test_no_other_screen_reads_as_the_ego_card():
    # CODING_STANDARDS: a template ships with a sweep over tests/screens. Sweep (grey, 2026-11-07, 198 other 1280 x 720
    # captures): 1.00 for both parts on all three captures of the card (one card, blue or green; three cards); Details
    # alone 0.70 at most (HelpPager.png), Resistances alone 0.74 (MapNodePanel.png), both together 0.63 at most
    # (SuperShop.png: 0.62 and 0.63). Each part stays under its threshold on its own, and the And's lower part 0.2 under
    # it. The production matcher's own sweep is
    # maa-tools test (maatools.config.mts): EgoCard hits on the three captures of the card and misses every other screen.
    nodes = load_nodes()
    found = templates(nodes, nodes["EgoCard"])
    others = [p for p in sorted(SCREENS.glob("*.png")) if p.name not in SHOTS and Image.open(p).size == (1280, 720)]
    assert len(others) > 100
    for p in others:
        image = gray(p)
        scores = [score(image, t, roi) for t, roi, _ in found]
        assert all(s < threshold for s, (_, _, threshold) in zip(scores, found)), p.name
        assert min(scores) < min(threshold for _, _, threshold in found) - 0.2, p.name


def test_every_battle_hub_closes_the_ego_card_before_the_turn():
    # The battle HUD is dimmed under the card: BattleHUD must know the card itself, and answer it before the turn and
    # the pause it covers. EXP, Thread and the Mirror Dungeon all reach a battle through BattleHUD.
    nodes = load_nodes()
    hud = nodes["BattleHUD"]
    assert "EgoCard" in hud["any_of"]
    listed = strip(hud["next"])
    assert listed.index("EgoCard") < listed.index("BattleTurn") < listed.index("BattlePause")
    for hub in ("MirrorHub", "ExpHub", "ThreadHub"):
        assert "BattleHUD" in strip(nodes[hub]["next"]), hub


def test_a_held_finger_lifts_for_the_ego_card():
    # The daily run's card was up after `turn 1: started` (what opened it is unverified), where hold_turn holds the
    # finger for up to 6 s: it lifts as soon as the card shows, and BattleHUD closes it.
    import actions
    assert "EgoCard" in actions.BATTLE_LEFT


def test_the_tap_lands_off_the_card_and_off_the_turns_buttons():
    # Live 2026-11-07: a tap on the dimmed field, on the bar and on the dim above the card each closed it; the back key
    # did not. The tap (the target's centre) goes above the card, where the turn under it has no button either: a tap
    # that comes when the card has already gone lands on the battlefield's backdrop.
    param = load_nodes()["EgoCard"]["custom_action_param"]
    assert param["left"] is True  # waits for the card to go, no OCR
    x, y, w, h = param["target"]
    tap = (x + w // 2, y + h // 2, 1, 1)
    assert all(inside(tap, (0, 0, 1280, box[1])) and not touches(tap, box) for box in (CARD_BOX, CARDS_ROW))
    assert not any(touches(tap, b) for b in TOP_BUTTONS)
