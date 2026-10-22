"""#253: Formation.pick looks at Total Participants right after each tap, instead of sleeping a fixed 1.2 s first."""
import actions
import test_actions

clock, context = test_actions.clock, test_actions.context  # its fixtures
ORDER = ["Yi Sang", "Hong Lu", "Rodion"]
OCR = 0.3  # s one look at the count costs (live: ~0.33 s)


class Game:
    """The formation page's Total Participants. A card tap raises the count `lag` s later, unless it is eaten (the first
    `eaten` of them). Clear Selection opens the Reset dialog (`dialog`) that Confirm answers by emptying the selection
    (`clears`); without the dialog it empties the selection itself."""

    def __init__(self, monkeypatch, start=7, lag=0.3, eaten=0, dialog=True, clears=True):
        self.count, self.lag, self.eaten, self.dialog, self.clears = start, lag, eaten, dialog, clears
        self.open, self.pending, self.taps = False, [], []
        monkeypatch.setattr(actions, "tap", self.tap)
        monkeypatch.setattr(actions, "participants", self.read)
        monkeypatch.setattr(actions, "text", lambda context, image, roi, only_rec=False: "Reset Deployment Order?" if self.open else "")

    def tap(self, context, x, y, wait=1.0):
        now = actions.time.monotonic()
        self.taps.append((now, (x, y)))
        if (x, y) == actions.CLEAR_SELECTION:
            self.open = self.dialog
            if not self.dialog:
                self.pending.append((now + self.lag, lambda: 0))
        elif (x, y) == actions.RESET_CONFIRM and self.open:
            self.open = False
            if self.clears:
                self.pending.append((now + self.lag, lambda: 0))
        elif (x, y) in [actions.card_xy(i, actions.CARD_TAP_Y) for i in range(12)]:
            if self.eaten:
                self.eaten -= 1
            else:
                self.pending.append((now + self.lag, lambda: self.count + 1))
        actions.time.sleep(wait)

    def read(self, context, image):
        actions.time.sleep(OCR)
        now = actions.time.monotonic()
        for due, value in [p for p in self.pending if p[0] <= now]:
            self.count = value()
            self.pending.remove((due, value))
        return self.count, 12

    def cards(self):
        return [t for t, xy in self.taps if xy not in (actions.CLEAR_SELECTION, actions.RESET_CONFIRM)]

    def card_taps(self, sinner):
        return [t for t, xy in self.taps if xy == actions.card_xy(actions.battle.SINNERS.index(sinner), actions.CARD_TAP_Y)]


def test_each_card_is_checked_at_once_and_the_next_one_follows_the_count(context, monkeypatch, clock):
    game = Game(monkeypatch)
    assert actions.Formation.pick(context, ORDER)
    assert [xy for _, xy in game.taps] == [actions.CLEAR_SELECTION, actions.RESET_CONFIRM] + \
        [actions.card_xy(actions.battle.SINNERS.index(s), actions.CARD_TAP_Y) for s in ORDER]
    assert game.count == 3
    assert sum(clock) < 4.0  # the fixed waits alone were 1.5 + 3 * 1.2 s, plus a look at the count after each


def test_a_card_tap_not_counted_within_a_second_is_tapped_again(context, monkeypatch):
    game = Game(monkeypatch, eaten=1)
    assert actions.Formation.pick(context, ORDER)
    first, again = game.card_taps("Yi Sang")
    assert actions.PICK_RETAP <= again - first < actions.PICK_RETAP + 1.0
    assert [len(game.card_taps(s)) for s in ORDER] == [2, 1, 1] and game.count == 3
    assert "1 taps repeated" in actions.LOG[-1]


def test_a_slow_tap_is_not_tapped_again_before_the_second_is_up(context, monkeypatch):
    # A second tap on a card that took the first one would pick it off again.
    game = Game(monkeypatch, lag=0.8)
    assert actions.Formation.pick(context, ORDER)
    assert [len(game.card_taps(s)) for s in ORDER] == [1, 1, 1]


def test_a_card_that_two_taps_do_not_pick_is_stuck_and_no_later_card_is_tapped(context, monkeypatch):
    game = Game(monkeypatch, eaten=2)
    assert not actions.Formation.pick(context, ORDER)
    assert [len(game.card_taps(s)) for s in ORDER] == [2, 0, 0]
    assert actions.STUCK["flag"][2] == "tapping Yi Sang did not pick them"


def test_clear_selection_is_confirmed_when_the_reset_dialog_shows_and_waits_for_a_zero_count(context, monkeypatch):
    game = Game(monkeypatch, lag=0.9)
    assert actions.Formation.pick(context, ORDER[:1])
    assert [xy for _, xy in game.taps[:2]] == [actions.CLEAR_SELECTION, actions.RESET_CONFIRM]
    assert game.taps[2][0] - game.taps[1][0] >= 0.9  # the first card waited for the count to be 0, not for a fixed time


def test_clear_selection_without_the_dialog_goes_on_at_a_zero_count(context, monkeypatch):
    game = Game(monkeypatch, dialog=False)
    assert actions.Formation.pick(context, ORDER[:1])
    assert actions.RESET_CONFIRM not in [xy for _, xy in game.taps]
    assert game.count == 1


def test_a_formation_that_does_not_clear_after_three_tries_is_stuck_and_no_card_is_tapped(context, monkeypatch):
    game = Game(monkeypatch, clears=False)
    assert not actions.Formation.pick(context, ORDER)
    assert [xy for _, xy in game.taps].count(actions.CLEAR_SELECTION) == 3 and game.cards() == []
    assert actions.STUCK["flag"][2] == "Clear Selection did not clear the formation"
