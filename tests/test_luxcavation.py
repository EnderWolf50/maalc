import pytest

from luxcavation import EXP_COST, FIGHT, FINISH, RETRY, SKIP, STOP, batch, decide, needed, parse_consecutive, presses


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
