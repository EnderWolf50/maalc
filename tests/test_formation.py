"""#253: Formation.pick looks at Total Participants right after each tap, instead of sleeping a fixed 1.2 s first."""
from types import SimpleNamespace

import actions
import test_actions
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # its fixtures
ORDER = ["Yi Sang", "Hong Lu", "Rodion"]
OCR = 0.3  # s one look at the count costs (live: ~0.33 s); the screenshot is taken before it


def card(sinner):
    return actions.card_xy(actions.battle.SINNERS.index(sinner), actions.CARD_TAP_Y)


class Game:
    """The formation page's Total Participants. A card tap shows `lag` s later, unless it is eaten (the first `eaten`
    of them); a tap on a card that is picked picks it off again. Clear Selection opens the Reset dialog (`dialog`) that
    Confirm answers by emptying the selection (`clears`); without the dialog it empties the selection itself. `blind`:
    s after a card tap that the count cannot be read (the page moving)."""

    def __init__(self, monkeypatch, start=7, lag=0.3, eaten=0, dialog=True, clears=True, blind=0.0):
        self.count, self.lag, self.eaten, self.dialog, self.clears, self.blind = start, lag, eaten, dialog, clears, blind
        self.open, self.pending, self.taps, self.picked, self.last_card = False, [], [], set(), -99.0
        patch_all(monkeypatch, "tap", self.tap)
        patch_all(monkeypatch, "participants", self.read)
        patch_all(monkeypatch, "text", lambda context, image, roi, only_rec=False: "Reset Deployment Order?" if self.open else "")

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
                self.picked.clear()
                self.pending.append((now + self.lag, lambda: 0))
        elif (x, y) in [actions.card_xy(i, actions.CARD_TAP_Y) for i in range(12)]:
            self.last_card = now
            if self.eaten:
                self.eaten -= 1
            else:
                step = -1 if (x, y) in self.picked else 1
                self.picked ^= {(x, y)}
                self.pending.append((now + self.lag, lambda: self.count + step))
        actions.time.sleep(wait)

    def read(self, context, image):
        shot = actions.time.monotonic()
        actions.time.sleep(OCR)
        for due, value in [p for p in self.pending if p[0] <= shot]:
            self.count = value()
            self.pending.remove((due, value))
        return None if shot < self.last_card + self.blind else (self.count, 12)

    def card_taps(self, sinner):
        return [t for t, xy in self.taps if xy == card(sinner)]


def test_each_card_is_checked_at_once_and_the_next_one_follows_the_count(context, monkeypatch, clock):
    game = Game(monkeypatch)
    assert actions.Formation.pick(context, ORDER)
    assert [xy for _, xy in game.taps] == [actions.CLEAR_SELECTION, actions.RESET_CONFIRM] + [card(s) for s in ORDER]
    assert game.count == 3
    assert sum(clock) < 4.0  # the fixed waits alone were 1.5 + 1.0 + 3 * 1.2 s, plus a look at the count after each


def test_a_card_tap_not_counted_within_a_second_is_tapped_again(context, monkeypatch):
    game = Game(monkeypatch, eaten=1)
    assert actions.Formation.pick(context, ORDER)
    first, again = game.card_taps("Yi Sang")
    assert 1.0 <= again - first < 1.7  # #253: about a second (the looks end after the first one past PICK_RETAP)
    assert [len(game.card_taps(s)) for s in ORDER] == [2, 1, 1] and game.count == 3
    assert "1 taps repeated" in actions.LOG[-1]


def test_a_slow_tap_is_not_tapped_again_before_the_second_is_up(context, monkeypatch):
    # A second tap on a card that took the first one would pick it off again.
    game = Game(monkeypatch, lag=0.8)
    assert actions.Formation.pick(context, ORDER)
    assert [len(game.card_taps(s)) for s in ORDER] == [1, 1, 1] and game.count == 3


def test_a_tap_that_took_late_and_was_repeated_is_tapped_a_third_time_when_the_card_falls_back(context, monkeypatch):
    # The count shows 1.3 s after the first tap: the repeat at 1 s picks the card off again.
    game = Game(monkeypatch, lag=1.3)
    assert actions.Formation.pick(context, ORDER[:1])
    assert len(game.card_taps("Yi Sang")) == 3 and game.count == 1
    assert "2 taps repeated" in actions.LOG[-1]


def test_after_a_tap_that_took_late_the_next_cards_wait_for_their_first_tap_longer(context, monkeypatch):
    # The count shows 1.1 s after each tap: without it every card would be repeated, picked off and tapped a third time.
    game = Game(monkeypatch, lag=1.1)
    assert actions.Formation.pick(context, ORDER)
    assert [len(game.card_taps(s)) for s in ORDER] == [3, 1, 1] and game.count == 3


def test_a_count_that_is_never_readable_is_stuck_after_two_taps(context, monkeypatch):
    game = Game(monkeypatch, blind=99)
    assert not actions.Formation.pick(context, ORDER[:1])
    assert len(game.card_taps("Yi Sang")) == 2
    assert actions.STUCK["flag"][2] == "tapping Yi Sang did not pick them"


def test_a_count_that_cannot_be_read_is_waited_for_not_tapped_on(context, monkeypatch):
    # Live (#253 measurement): once the count read as unreadable 1.57 s after a tap that had taken.
    game = Game(monkeypatch, blind=1.4)
    assert actions.Formation.pick(context, ORDER)
    assert [len(game.card_taps(s)) for s in ORDER] == [1, 1, 1] and game.count == 3


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
    assert [xy for _, xy in game.taps].count(actions.CLEAR_SELECTION) == 3
    assert not any(xy == card(s) for _, xy in game.taps for s in ORDER)
    assert actions.STUCK["flag"][2] == "Clear Selection did not clear the formation"


def formation_page(context, monkeypatch, reads, answers):
    """A formation page (MirrorHub's Formation node hits while `"Formation"` reads True) as a TimedGame."""
    game = test_actions.TimedGame(monkeypatch, context, {"Formation": True, **reads}, answers)
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name == "Formation" and game.now()["Formation"] else None
    return game


def test_too_few_alive_backs_out_and_hands_back_once_the_page_goes_not_after_2_s(context, clock, monkeypatch):
    # #258: the back arrow slept 2 s so that MirrorHub would not find the page again and back out twice; the wait now
    # ends when the Formation node no longer hits.
    actions.RUN.update(team={"min_alive": 5, "name": "t"}, settings={"run": {"after_retries": "forfeit"}})
    patch_all(monkeypatch, "participants", lambda context, image: (4, 4))
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: [])
    patch_all(monkeypatch, "dead_sinners", lambda image: set())
    game = formation_page(context, monkeypatch, {tuple(actions.DETAILS_BUTTON): "Details"}, {actions.FORMATION_BACK: [(0.5, {"Formation": False}, 20)]})
    assert actions.Formation().run(context, None)
    assert game.taps == [actions.FORMATION_BACK] and actions.RUN["forfeit"]
    assert not game.now()["Formation"]  # gone before the hub looks again
    assert sum(clock) < 1.5  # still() 0.2 s, then the page's 0.5 s; was 0.2 + 2 s


def test_the_details_view_is_folded_and_read_once_its_button_shows_not_after_1_5_s(context, clock, monkeypatch):
    # #258: the » slept 1.5 s; now the order marks are read on the folded page once Details shows and the page is still.
    actions.RUN.update(team={"min_alive": 0, "name": "t"}, settings={"run": {"after_retries": "stop"}})
    patch_all(monkeypatch, "participants", lambda context, image: (5, 12))
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: [])  # ends the action after the dead are read
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: False)
    read = []
    patch_all(monkeypatch, "dead_sinners", lambda image: read.append(int(image[0, 0, 0])) or set())
    game = formation_page(context, monkeypatch, {tuple(actions.DETAILS_BUTTON): ""},
                          {(826, 125): [(0.4, {tuple(actions.DETAILS_BUTTON): "Details"}, 30)]})
    actions.Formation().run(context, None)
    assert game.taps == [(826, 125)]
    assert read == [30]  # the folded page
    assert sum(clock) < 1.3  # was 0.2 + 1.5 s


SPIDER_NEST = ["Ryōshū", "Yi Sang", "Faust", "Hong Lu", "Rodion", "Ishmael", "Outis", "Heathcliff", "Sinclair", "Don Quixote"]


def order_page(context, monkeypatch, plan, dead, min_alive, screen_alive, after_retries="forfeit"):
    """A formation page (screen count screen_alive of 12) whose grey cards are `dead`; the stops, taps and log lines (#616)."""
    actions.RUN.update(team={"min_alive": min_alive, "name": "t"}, settings={"run": {"after_retries": after_retries}})
    actions.RUN.pop("forfeit", None)
    stops, taps, lines = [], [], []
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: stops.append(reason) or False)
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    patch_all(monkeypatch, "log", lines.append)
    patch_all(monkeypatch, "participants", lambda context, image: (0, screen_alive))
    patch_all(monkeypatch, "dead_sinners", lambda image: set(dead))
    monkeypatch.setattr(actions.run_start, "resolve_plan", lambda *a: plan)
    patch_all(monkeypatch, "order_marks", lambda context, image: {})
    monkeypatch.setattr(actions.Formation, "pick", staticmethod(lambda context, order: taps.append(("pick", order)) or False))
    test_actions.reads(context, {tuple(actions.DETAILS_BUTTON): [("Details", (0, 0, 10, 10))]})
    result = actions.Formation().run(context, None)
    return result, stops, taps, lines


def test_only_the_deployment_order_counts_toward_min_alive(context, monkeypatch):
    # #616: grey cards Yi Sang to Don Quixote plus Gregor; Ryōshū and Meursault alive: K 1 is met, no forfeit.
    dead = set(actions.battle.SINNERS) - {"Ryōshū", "Meursault"}
    result, stops, taps, lines = order_page(context, monkeypatch, SPIDER_NEST, dead, 1, 2)
    assert "forfeit" not in actions.RUN and stops == []
    assert ("pick", ["Ryōshū"]) in taps
    assert any("1 of the deployment order alive" in line and "2 alive on screen" in line for line in lines)


def test_a_dead_sinner_of_the_order_forfeits_below_k(context, monkeypatch):
    # #616: Ryōshū grey, only Meursault and Gregor alive: nobody of the order is left, K 1 forfeits.
    dead = set(actions.battle.SINNERS) - {"Meursault", "Gregor"}
    result, stops, taps, lines = order_page(context, monkeypatch, SPIDER_NEST, dead, 1, 2)
    assert result is True and actions.RUN["forfeit"] and "0 sinners of" in actions.RUN["forfeit"]
    assert stops == []


def test_the_grey_cards_win_over_the_screen_count(context, monkeypatch):
    # #616: the screen says 4 alive, the grey cards say Yi Sang is dead: the grey cards decide, and the log says so.
    dead = {"Yi Sang"}
    result, stops, taps, lines = order_page(context, monkeypatch, ["Yi Sang"], dead, 1, 4)
    assert actions.RUN["forfeit"]
    assert any("grey cards" in line for line in lines)


def test_the_log_gives_the_screen_count_not_the_grey_card_count(context, monkeypatch):
    result, stops, taps, lines = order_page(context, monkeypatch, ["Yi Sang"], {"Yi Sang"}, 1, 4)
    assert any("0 of the deployment order alive, 4 alive on screen" in line for line in lines)


def test_a_full_order_counts_as_the_screen_count_did(context, monkeypatch):
    # #616: an order of all 12: K 5 with 4 alive forfeits, with 5 alive it does not (as before).
    plan = list(actions.battle.SINNERS)
    dead = set(plan[:8])
    order_page(context, monkeypatch, plan, dead, 5, 4)
    assert actions.RUN["forfeit"]
    order_page(context, monkeypatch, plan, set(plan[:7]), 5, 5)
    assert "forfeit" not in actions.RUN


def test_an_order_shorter_than_k_stops_with_after_retries_stop(context, monkeypatch):
    result, stops, taps, lines = order_page(context, monkeypatch, SPIDER_NEST, set(), 12, 12, "stop")
    assert result is False and len(stops) == 1 and "deployment order" in stops[0]
