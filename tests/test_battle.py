import numpy as np
import pytest

import battle as b

PLAN = ["Ryōshū", "Yi Sang", "Faust", "Hong Lu", "Rodion", "Ishmael",
        "Outis", "Heathcliff", "Sinclair", "Don Quixote", "Meursault", "Gregor"]


def marks_for(order):
    return {s: (order.index(s) + 1 if s in order else None) for s in b.SINNERS}


def test_formation_order_skips_the_dead():
    assert b.formation_order(PLAN, {"Faust", "Gregor"}) == [s for s in PLAN if s not in ("Faust", "Gregor")]
    assert b.formation_order(PLAN, set()) == PLAN
    assert b.formation_order(["Ryōshū"], {"Ryōshū"}) == []  # a solo order with its sinner dead: Formation stops


def test_formation_matches_only_the_exact_order():
    order = b.formation_order(PLAN, {"Faust"})
    assert b.formation_matches(marks_for(order), order)
    # The game keeps the last battle's picks: a dead sinner's old slot shifts every later mark.
    assert not b.formation_matches(marks_for(PLAN), order)
    swapped = order[:]
    swapped[7], swapped[8] = swapped[8], swapped[7]  # backups in the wrong order
    assert not b.formation_matches(marks_for(swapped), order)
    unread = marks_for(order) | {"Outis": None}
    assert not b.formation_matches(unread, order)
    assert not b.formation_matches(marks_for(order[:-1]), order)  # one sinner left out


@pytest.mark.parametrize(("used", "retries", "after", "expected"), [
    (0, 2, "stop", "retry"),
    (1, 2, "forfeit", "retry"),
    (2, 2, "stop", "stop"),
    (2, 2, "forfeit", "forfeit"),
    (0, 0, "forfeit", "forfeit"),
])
def test_after_wipe(used, retries, after, expected):
    assert b.after_wipe(used, retries, after) == expected


def test_guard_turns_count_only_turns_started_on_guard():
    left = 2
    for guarded in (False, True, False, True, True):  # fallbacks to Win Rate keep the count
        left = b.guard_left(left, guarded)
    assert left == 0


def test_slot_centres_merge_ticks_and_drop_sparks():
    row = np.zeros(400, bool)
    row[10:33] = row[35:53] = True  # one top edge cut by a tick: 10-53
    row[100:143] = True
    row[200:204] = True  # a spark
    row[300:390] = True  # too wide for one portrait
    assert b.slot_centres(row) == [31, 121]


def test_same_turn_counts_tries_at_one_turn():
    last = None
    for turn, tries in [("1", 1), ("1", 2), ("2", 1), ("2", 2), ("2", 3), ("2", 4), (None, 1), (None, 2), ("3", 1)]:
        last = b.same_turn(last, turn)
        assert last == (turn, tries)
