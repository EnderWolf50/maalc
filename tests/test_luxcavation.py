import pytest

from luxcavation import EXP_COST, FIGHT, FINISH, RETRY, SKIP, STOP, decide, needed


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
