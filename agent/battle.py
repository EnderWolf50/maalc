"""Battle decisions, free of MaaFramework (docs/spec/03-decisions.md sections 3, 8, 9).

actions.py reads the formation page and the DEFEAT dialog and taps; everything here is plain data.
"""

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


def slot_xs(win_rate_x):
    """x of each skill slot's portrait, from the Win Rate label's x (BattleTurn box, 1280x720).

    Live (2026-10-16): the slots are 81 px apart and centred on x 605; each extra slot moves the
    label half a step right (7 slots: x 984, 8: 1020, 9: 1060). Counted from the label rather than
    the portraits, as a unit's extra slot shows a dark guard icon instead of a portrait.
    """
    n = 7 + round((win_rate_x - 984) / 40.5)
    return [round(605 + 81 * (i - (n - 1) / 2)) for i in range(max(n, 0))]


def guard_chain(xs):
    """The points of the drag that picks every slot's lower skill, left to right (spec 03 section 8).

    Live (2026-10-16): the chain starts only on the left gear, 90 px left of the first slot at y 557.
    Once the finger is down the panel tilts: the upper skills move to y ~600 and the lower skills to
    y ~665, under the slots' x, so the drag runs along y 665 (along the resting lower row, y 577,
    it picks the upper skills).
    """
    return [(xs[0] - 90, 557)] + [(x, 665) for x in xs]


def guard_shown(before, after):
    """Per slot, whether its lower skill shows the guard skill after a portrait tap swapped it.

    before and after hold one (brown, texture) pair per slot, read at the slot's lower skill before
    and after the tap: brown is the share of the guard icons' flat brown, texture the mean brightness
    step between neighbouring pixels (a skill is busy line art, a guard icon flat shapes). The tap swaps
    the lower skill between the slot's skill and its guard skill, and the game keeps that choice from
    turn to turn, so each slot is compared with itself. Texture decides (live: the guard side is 11-65%
    flatter); brown only breaks a tie, as orange and red skill frames read brown too. None when neither tells.
    """
    shown = []
    for (b0, t0), (b1, t1) in zip(before, after):
        if t1 < t0 * 0.93 or t1 > t0 * 1.07:
            shown.append(t1 < t0)
        elif abs(b1 - b0) >= 0.1:
            shown.append(b1 > b0)
        else:
            shown.append(None)
    return shown


def disc_lit(image, x, y):
    """Whether the START disc centred on (x, y) is lit: the brightest channel's mean in a 20 px square.

    Brightness, not the START label (spec 07: the label template fails on snow maps). Unlit reads
    128-142 and lit ~254; live 2026-10-17 (#69) a turn with 6 of 7 slots staggered and its one unit
    picked read ~189 with the START plaque up, so the line sits at 160.
    """
    return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)
