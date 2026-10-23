"""#334: the reward page's cards are read and tapped once they have stopped moving; a tap the game ignored is not a card taken."""
import numpy as np

import actions
import test_actions

clock, context = test_actions.clock, test_actions.context  # its fixtures
ORDER = ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"]
CARDS = [(400, "Gain 100~150 Cost"), (660, "Gain a random Tier 1~2 E.G.O Gift"), (860, "E.G.O Resource +6 for 2 of the least-owned")]


class RewardPage:
    """The reward page of a floor 3+: three cards that slide in for `deal` s (moving pixels; the third card reads as
    nothing, as live) and take no tap meanwhile; Selectable n/1. ignore: how many taps after the deal the game drops
    anyway (#334: the live log shows taps swallowed up to 0.08 s after the last motion)."""

    def __init__(self, context, monkeypatch, deal=0.6, ignore=0):
        self.start, self.deal, self.ignore = actions.time.monotonic(), deal, ignore
        self.taps, self.reads, self.picked, self.shots = [], [], [], 0
        context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = self.screen
        monkeypatch.setattr(actions, "ocr", self.ocr)
        monkeypatch.setattr(actions, "tap", self.tap)
        actions.RUN["team"] = {"reward_cards": ORDER}

    def dealing(self):
        return actions.time.monotonic() - self.start < self.deal

    def screen(self):
        self.shots += 1
        image = np.full((720, 1280, 3), 40, np.uint8)
        if self.dealing():  # a card sliding across: a bright block somewhere else in each screenshot
            x = 130 + self.shots * 211 % 800
            image[200:450, x:x + 200] = 250
        return image

    def ocr(self, context, image, roi, only_rec=False):
        if roi == actions.REWARD_TITLE:
            return [("Select Encounter Reward Card", (300, 120, 200, 30))]
        if roi == actions.SELECTABLE:
            return [(f"Selectable {len(self.picked)}/1", (890, 120, 150, 30))]
        if roi == actions.CARD_TEXT:
            shown = [(x, "a" if self.dealing() and x == 860 else t) for x, t in CARDS]
            self.reads.append([t for _, t in shown])
            return [(t, (x - 60, 380, 120, 30)) for x, t in shown]
        return []

    def tap(self, context, x, y, wait=1.0):
        self.taps.append((x, y))
        actions.time.sleep(wait)
        if x == actions.CARD_CONFIRM[0] or self.dealing():
            return
        if self.ignore:
            self.ignore -= 1
            return
        self.picked = [c for c, _ in CARDS if abs(c - x) < 80]  # a tap on a lit card would drop it; none is tapped twice here


def test_the_cards_are_read_and_tapped_after_they_stop_moving(context, monkeypatch):
    page = RewardPage(context, monkeypatch)
    assert actions.RewardCard().run(context, None)
    assert page.reads[0] == [t for _, t in CARDS]  # no card still moving when read
    assert page.taps[0] == (660, 300)  # Random E.G.O Gift: the team's first of the three, in the first tap
    assert page.taps[1:] == [actions.CARD_CONFIRM]
    assert actions.STUCK["flag"] is None


def test_a_tap_the_game_ignored_is_taken_again_not_counted_as_a_card_taken(context, monkeypatch):
    page = RewardPage(context, monkeypatch, deal=0, ignore=1)
    assert actions.RewardCard().run(context, None)
    assert page.taps == [(660, 300), (660, 300), actions.CARD_CONFIRM]  # the second round took the best card again, not the next
    assert actions.STUCK["flag"] is None


def test_a_card_that_reads_as_nothing_is_read_again(context, monkeypatch):
    # The page's cards still swinging when the screenshots look alike: the third card unread; the next look has it.
    page = RewardPage(context, monkeypatch, deal=0)
    reads = iter([[CARDS[0][1], CARDS[1][1], "a"]])
    ocr = page.ocr

    def read_once_wrong(context, image, roi, only_rec=False):
        wrong = next(reads, None) if roi == actions.CARD_TEXT else None
        if wrong is None:
            return ocr(context, image, roi, only_rec)
        page.reads.append(wrong)
        return [(t, (x - 60, 380, 120, 30)) for (x, _), t in zip(CARDS, wrong)]
    monkeypatch.setattr(actions, "ocr", read_once_wrong)
    assert actions.RewardCard().run(context, None)
    assert page.reads[0][2] == "a" and page.reads[1] == [t for _, t in CARDS]
    assert page.taps == [(660, 300), actions.CARD_CONFIRM]
