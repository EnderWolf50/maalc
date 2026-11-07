"""tools/live/ego_card.py: opens a sinner's E.G.O card while the bot runs, and times how long it stays (#468).

It reads the card with the EgoCard node's own templates and the planning phase with BattleTurn's, on the live captures
of tests/screens, and long-presses the portrait under a skill slot, as the investigation opened the card (2.5 s).
"""
from pathlib import Path

import cv2

from live import ego_card as ec

SCREENS = Path(__file__).resolve().parent / "screens"
CARDS = ["LuxBattleEgoCard.png", "BattleEgoCard.png", "LuxBattleEgoCards.png"]


def read(name):
    return cv2.imread(str(SCREENS / name))  # BGR, as MaaFramework's screencap


def test_the_card_is_read_with_the_ego_card_nodes_templates():
    assert all(ec.card_up(read(f)) for f in CARDS)
    assert not any(ec.card_up(read(f)) for f in ["BattleTurn.png", "BattlePause.png", "BattleMenu.png", "MainWindow.png"])


def test_the_planning_phase_gives_the_win_rate_labels_x():
    # The pipeline's comment on BattleTurn: x 984 with 7 slots (BattleTurn.png), 1022 with 8 (BattleTurnEven.png).
    assert abs(ec.win_rate_x(read("BattleTurn.png")) - 984) <= 2
    assert abs(ec.win_rate_x(read("BattleTurnEven.png")) - 1022) <= 2
    assert ec.win_rate_x(read("BattlePause.png")) is None


class Bot:
    """The frames the screen shows in turn (the last one stays), a clock the sleeps move, the presses and lines."""

    def __init__(self, frames):
        self.frames, self.now, self.presses, self.said = [read(f) for f in frames], 0.0, [], []

    def grab(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def run(self, slot=0, attempts=2):
        return ec.open_card(self.grab, lambda x, y, s: self.presses.append((x, y, s)), self.said.append, slot=slot,
                            hold=2.5, attempts=attempts, clock=lambda: self.now, sleep=self.sleep)

    def sleep(self, s):
        self.now += s


def test_a_press_on_the_slots_portrait_opens_the_card_and_its_close_is_timed():
    bot = Bot(["BattlePause.png", "BattleTurn.png", "BattleEgoCard.png", "BattleEgoCard.png", "BattleTurn.png"])
    assert bot.run(slot=2) == 0
    assert bot.presses == [(524, 665, 2.5)]  # 7 slots 81 px apart, centred on x 605: the third at 524
    assert any(line.startswith("card open") for line in bot.said)
    assert bot.said[-1].startswith("card gone") and "s after it showed" in bot.said[-1]


def test_a_press_that_opens_no_card_is_tried_again_at_the_next_planning_phase():
    bot = Bot(["BattleTurn.png"])
    assert bot.run(attempts=2) == 2 and len(bot.presses) == 2


def test_a_card_that_stays_is_a_failure():
    bot = Bot(["BattleTurn.png", "BattleEgoCard.png"])
    assert bot.run() == 1 and bot.said[-1].startswith("card still up")
