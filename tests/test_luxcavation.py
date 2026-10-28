from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import actions
from luxcavation import EXP_COST, FIGHT, FINISH, RETRY, SKIP, STOP, batch, decide, needed, parse_consecutive, presses

if __name__ != "__main__":  # as test_task_chain.py: the fixtures are test_actions's
    from test_actions import Choices, clock, context  # noqa: F401 (the fake Maa context the in-process tests use)

SCREENS = Path(__file__).resolve().parent / "screens"


@pytest.mark.parametrize("count, cost, need", [(1, 3, 3), (2, 3, 6), (5, 3, 15), (3, 2, 6)])
def test_needed(count, cost, need):
    assert needed(cost, count) == need


@pytest.mark.parametrize("modules, count, step", [
    (6, 2, FIGHT),  # exactly enough
    (5, 2, SKIP),  # one short: the log says "5 < 6"
    (0, 1, SKIP),
    (3, 1, FIGHT),
    (2, 1, SKIP),
    (182, 5, FIGHT),
])
def test_the_start_checks_the_modules_once_for_every_battle(modules, count, step):
    assert decide(modules, EXP_COST, count, 0, 0, 0) == step


@pytest.mark.parametrize("count, won, step", [
    (1, 0, FINISH),
    (2, 0, FIGHT),  # the first of two
    (2, 1, FINISH),  # the second of two
    (3, 1, FIGHT),
])
def test_a_win_counts_until_count_are_won(count, won, step):
    assert decide(0, EXP_COST, count, won, 0, 0, "win") == step  # modules no longer matter after the start


@pytest.mark.parametrize("retries, retried, step", [
    (0, 0, STOP),  # no retries: the task fails
    (1, 0, RETRY),
    (1, 1, STOP),  # used up
    (3, 2, RETRY),
    (3, 3, STOP),
])
def test_a_defeat_counts_for_nothing_and_plays_again_within_retries(retries, retried, step):
    assert decide(0, EXP_COST, 2, 1, retried, retries, "lose") == step


def test_a_win_after_retries_still_counts_once():
    assert decide(0, EXP_COST, 1, 0, 1, 1, "win") == FINISH


@pytest.mark.parametrize("count, won, consecutive, size", [
    (1, 0, True, 1), (3, 0, True, 3), (12, 0, True, 10), (12, 10, True, 2), (10, 0, True, 10),  # the rest, up to the game's 10
    (3, 0, False, 1), (12, 10, False, 1),  # off: one battle at a time
])
def test_a_consecutive_battle_takes_the_wins_left_up_to_ten(count, won, consecutive, size):
    assert batch(count, won, consecutive) == size


@pytest.mark.parametrize("count, won, size, step", [
    (3, 0, 3, FINISH),  # one x3 battle wins all three
    (12, 0, 10, FIGHT),  # x10 first, then the 2 left
    (12, 10, 2, FINISH),
])
def test_a_consecutive_win_counts_its_size(count, won, size, step):
    assert decide(0, EXP_COST, count, won, 0, 0, "win", size) == step


@pytest.mark.parametrize("read, n", [
    ("Consecutive Battle ×1", 1), ("Consecutive Battle × 10", 10), ("Consecutive Battle×9▼", 9), ("le×3", 3),
    ("Consecutive Battle X 4", 4), ("Consecutive Battle ×", None), ("Consecutive Battle ", None), ("", None),
    ("×0", None), ("×11", None),  # the game takes 1-10
])
def test_the_title_reads_as_its_count(read, n):
    assert parse_consecutive(read) == n


@pytest.mark.parametrize("now, target, taps", [
    (1, 1, []), (1, 2, ["plus"]), (1, 3, ["plus", "plus"]), (1, 10, ["ten"]), (10, 3, ["one", "plus", "plus"]),
    (9, 10, ["plus"]), (10, 9, ["minus"]), (5, 1, ["one"]), (7, 2, ["one", "plus"]), (4, 10, ["ten"]),
])
def test_the_buttons_to_press_are_the_fewest(now, target, taps):
    assert presses(now, target) == taps


def test_a_luxcavation_event_reads_its_choices_without_a_mirror_run_plan(context, monkeypatch):
    # J1: a Luxcavation battle's event has its task's team, no Mirror run plan; one made up from the settings would
    # go to runs.jsonl at the next stop.
    actions.RUN.clear()
    actions.RUN.update(lux={"name": "Thread Luxcavation"}, team={"keyword": "Burn"})
    page = Choices(context, monkeypatch, [("Option 0.", ""), ("Option 1.", "Select to gain a Burn E.G.O Gift")], ["Unknown story."])
    actions.Event().run(context, None)
    assert page.tapped == ["Option 1."] and "settings" not in actions.RUN


LUX_EVENT = {name: np.array(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]
             for name in ("LuxEventStory", "LuxEventCard", "LuxEventCheck", "LuxEventText", "EventStory", "EventCheck",
                          "EventChoices", "EventResult", "EventNotices")}


@pytest.mark.parametrize("name", LUX_EVENT)
def test_a_check_card_alone_is_told_from_every_other_event_page(name):
    # Live 2026-10-28 (J1): after SKIP, a Luxcavation event's check card shows alone at the right, SKIP grey; nothing
    # goes on until the card is tapped. Its prompt below, a result, a Choices list or no card: another page.
    assert actions.card_alone(LUX_EVENT[name]) == (name == "LuxEventCard")


def test_a_check_card_alone_is_tapped_to_open_its_prompt(context, monkeypatch):
    taps = []
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    shots = [LUX_EVENT["LuxEventCard"], LUX_EVENT["LuxEventCheck"]]
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = (
        lambda: shots.pop(0) if len(shots) > 1 else shots[0])
    actions.RUN.clear()
    actions.RUN.update(lux={"name": "Thread Luxcavation"}, team={"keyword": "Burn"})
    assert actions.Event().run(context, None) is True
    assert taps == [actions.EVENT_CARD] and "settings" not in actions.RUN


def run_set_consecutive(context, monkeypatch, reads, target):
    """actions.set_consecutive on the exp page with the title reading `reads` in turn (the last repeats); the taps made."""
    taps, reads = [], list(reads)
    monkeypatch.setattr(actions, "consecutive_now", lambda context, image, box: reads.pop(0) if len(reads) > 1 else reads[0])
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    actions.LOG.clear()
    return actions.set_consecutive(context, "exp", target), taps


def test_the_consecutive_battle_logs_what_it_read_pressed_and_read_back(context, monkeypatch):
    # Acceptance 7 (M1): a run's log did not say what x N the bot found, which keys it pressed, or what it read after.
    got, taps = run_set_consecutive(context, monkeypatch, [1, 4], 4)
    assert got == 4 and len(taps) == 5  # open, + + +, close
    lines = [ln.split(" ", 1)[1] for ln in actions.LOG]
    assert lines == ["Consecutive Battle (exp): shows x1, wants x4",
                     "Consecutive Battle (exp): pressed plus, plus, plus",
                     "Consecutive Battle (exp): shows x4 after closing the row"]


def test_the_consecutive_battle_already_at_its_count_logs_the_read_only(context, monkeypatch):
    got, taps = run_set_consecutive(context, monkeypatch, [3], 3)
    assert got == 3 and taps == []
    assert [ln.split(" ", 1)[1] for ln in actions.LOG] == ["Consecutive Battle (exp): shows x3, wants x3"]


def test_the_consecutive_battle_that_does_not_read_or_set_logs_it(context, monkeypatch):
    got, _ = run_set_consecutive(context, monkeypatch, [None], 4)
    assert got is None and [ln.split(" ", 1)[1] for ln in actions.LOG] == ["Consecutive Battle (exp): does not read, wants x4"]
    got, _ = run_set_consecutive(context, monkeypatch, [1, 2], 4)
    assert got == 2 and actions.LOG[-1].endswith("Consecutive Battle (exp): shows x2 after closing the row, wanted x4")
