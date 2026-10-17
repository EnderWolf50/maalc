import zlib
from pathlib import Path

import numpy as np
import pytest

import battle as b

DISCS = Path(__file__).resolve().parent / "discs"

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


@pytest.mark.parametrize(("win_rate_x", "first", "last", "n"), [(984, 362, 848, 7), (1020, 322, 888, 8), (1060, 281, 929, 9)])
def test_slot_xs_follow_the_win_rate_label(win_rate_x, first, last, n):
    # Live 2026-10-16: 7, 8 and 9 slots; the portraits sat at 362-849, 322-887 and 281-929.
    xs = b.slot_xs(win_rate_x)
    assert (xs[0], xs[-1], len(xs)) == (first, last, n)


def test_slot_xs_land_on_the_portraits_of_an_even_count():
    # tests/screens/BattleTurnEven.png: 8 slots, Win Rate box at x 1022; the portrait rings centre on
    # these x (slot 4 is a unit's second slot: a dark guard icon, between 484 and 646).
    portraits = [322, 403, 484, 565, 646, 727, 808, 889]
    xs = b.slot_xs(1022)
    assert len(xs) == 8
    assert all(abs(x - p) <= 2 for x, p in zip(xs, portraits))


def test_guard_chain_starts_on_the_left_gear_and_runs_along_the_lower_row():
    # Live (2026-10-16), 8 slots: the chain starts on the left gear (x ~232, y 557); once the finger is
    # down the panel tilts and the lower skills (the guard skills) sit at y ~665 under the slots' x.
    xs = b.slot_xs(1022)
    assert b.guard_chain(xs) == [(232, 557)] + [(x, 665) for x in xs]


def test_guard_shown_compares_each_slot_before_and_after_the_tap():
    # Live (2026-10-16): slot 6 had been swapped in an earlier turn, so the taps swapped it off guard.
    before = [(0.08, 142), (0.0, 115), (0.01, 135), (0.21, 144), (0.16, 102), (0.28, 45), (0.0, 72), (0.02, 136)]
    after = [(0.53, 71), (0.14, 102), (0.28, 82), (0.44, 72), (0.36, 53), (0.02, 101), (0.05, 51), (0.4, 44)]
    assert b.guard_shown(before, after) == [True] * 5 + [False, True, True]
    # Snow map: an orange skill frame reads browner than the guard icon; the texture still tells.
    assert b.guard_shown([(0.15, 122), (0.01, 131)], [(0.06, 104), (0.03, 113)]) == [True, True]
    assert b.guard_shown([(0.1, 100), (0.2, 100)], [(0.12, 104), (0.05, 100)]) == [None, False]


def test_same_turn_counts_tries_at_one_turn():
    last = None
    for turn, tries in [("1", 1), ("1", 2), ("2", 1), ("2", 2), ("2", 3), ("2", 4), (None, 1), (None, 2), ("3", 1)]:
        last = b.same_turn(last, turn)
        assert last == (turn, tries)


def disc(name):
    """tests/discs/<name>.png as BGR: 40x40 round the START disc centre, cut from the battle screens in
    tests/screens and written by recovery.png (one IDAT, filter 0 on every row)."""
    data = (DISCS / f"{name}.png").read_bytes()
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(40, 1 + 40 * 3)
    return rows[:, 1:].reshape(40, 40, 3)[:, :, ::-1]


@pytest.mark.parametrize(("name", "lit"), [
    ("lit", True),  # BattleTurnLit.png: every slot picked, the disc glows (centre ~254)
    # BattleTurnStagger.png (live 2026-10-17, #69, floor 5 boss turn 6): 6 of 7 slots staggered, Win Rate
    # on, the one unit picked and the START plaque up, but the disc glows only half as much (~189).
    ("stagger", True),
    ("unlit", False),  # BattleTurn.png, BattleTurnEven.png, BattleTurnSolo.png: nothing picked (~128-142)
    ("unlit_even", False),
    ("unlit_solo", False),
])
def test_disc_lit(name, lit):
    assert b.disc_lit(disc(name), 20, 20) is lit
