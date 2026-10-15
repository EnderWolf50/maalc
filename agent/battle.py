"""Battle decisions, free of MaaFramework (docs/spec/03-decisions.md sections 3, 8, 9).

actions.py reads the formation page and the DEFEAT dialog and taps; everything here is plain data.
"""

import numpy as np

# The 12 cards on the formation page, left to right, top row first.
SINNERS = ("Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu",
           "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor")


def formation_order(plan, dead):
    """The sinners to tap, in order: the deployment order minus the dead (spec 03 section 3)."""
    return [s for s in plan if s not in dead]


def formation_matches(marks, order):
    """Whether the cards' order marks ({sinner: number or None}) are exactly order's 1, 2, 3, ..."""
    want = {s: i + 1 for i, s in enumerate(order)}
    return all(marks.get(s) == want.get(s) for s in SINNERS)


def after_wipe(retries_used, wipe_retries, after_retries):
    """"retry", "forfeit" or "stop" on the DEFEAT dialog (spec 03 section 9).

    Retry Stage up to wipe_retries times per encounter; then the after_retries setting.
    """
    return "retry" if retries_used < wipe_retries else after_retries


def same_turn(last, turn):
    """(turn, tries) after one more try at turn, as read off the screen (None when unread).

    Spec 03 section 8: three submits that leave the turn unchanged mean the battle is stuck,
    so the caller stops when the count passes 3. An unread turn counts as a turn of its own.
    """
    if last and last[0] == turn:
        return turn, last[1] + 1
    return turn, 1


def guard_left(left, guarded):
    """Guard turns left in the run after a turn started (spec 03 section 8).

    Only a turn that started with every unit on guard counts; a fallback to Win Rate keeps the count.
    """
    return left - 1 if guarded and left > 0 else left


def slot_centres(columns):
    """x centres of the skill slots, from one bool per x: is the portraits' orange hexagon top there.

    A top edge is one run of about 43 px, cut by white ticks (gaps under 10 px); other runs are sparks.
    """
    edges = np.flatnonzero(np.diff(np.concatenate(([0], columns.astype(np.int8), [0]))))
    runs = []
    for a, b in edges.reshape(-1, 2).tolist():
        if runs and a - runs[-1][1] <= 10:
            runs[-1][1] = b
        else:
            runs.append([a, b])
    return [(a + b) // 2 for a, b in runs if 25 <= b - a <= 60]
