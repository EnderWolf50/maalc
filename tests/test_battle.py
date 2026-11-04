import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import battle as b
import recovery

DISCS = Path(__file__).resolve().parent / "discs"
SCREENS = Path(__file__).resolve().parent / "screens"

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


def test_guard_chain_stops_on_no_staggered_slot():
    # #427, BattleTurnStaggerPlus.png: slots 7 and 8 staggered. The chain starts on the same gear and links slots 1-6.
    xs = b.slot_xs(1022)
    assert b.guard_chain(xs, [False] * 6 + [True] * 2) == [(232, 557)] + [(x, 665) for x in xs[:6]]
    # A staggered slot in the middle is no point of the drag; one in front leaves the gear where slot 1 puts it.
    middle = b.guard_chain(xs, [False, False, True] + [False] * 5)
    assert middle == [(232, 557)] + [(x, 665) for x in xs[:2] + xs[3:]]
    assert b.guard_chain(xs, [True] + [False] * 7) == [(232, 557)] + [(x, 665) for x in xs[1:]]


def test_the_hud_band_rests_while_a_swarm_moves_the_battlefield():
    # #229: two turn screens 3 s apart; the swarm moved 6.9% of the band's blocks, the most over 319 such pairs.
    frames = [np.asarray(Image.open(SCREENS / f"BattleTurnSwarm{s}.png"))[:, :, ::-1] for s in ("", "Next")]
    x, y, w, h = b.hud_band([946, 531, 40, 29])
    band = [recovery.thumb(f[y:y + h, x:x + w]) for f in frames]
    assert recovery.same_screen(*band, b.HUD_MOVED)
    assert not recovery.same_screen(*band)  # the whole-screen share
    assert not recovery.same_screen(*map(recovery.thumb, frames), b.HUD_MOVED)


def test_guard_shown_compares_each_slot_before_and_after_the_tap():
    # Live (2026-10-16): slot 6 had been swapped in an earlier turn, so the taps swapped it off guard.
    before = [(0.08, 142), (0.0, 115), (0.01, 135), (0.21, 144), (0.16, 102), (0.28, 45), (0.0, 72), (0.02, 136)]
    after = [(0.53, 71), (0.14, 102), (0.28, 82), (0.44, 72), (0.36, 53), (0.02, 101), (0.05, 51), (0.4, 44)]
    assert b.guard_shown(before, after) == [True] * 5 + [False, True, True]
    # Snow map: an orange skill frame reads browner than the guard icon; the texture still tells.
    assert b.guard_shown([(0.15, 122), (0.01, 131)], [(0.06, 104), (0.03, 113)]) == [True, True]
    assert b.guard_shown([(0.1, 100), (0.2, 100)], [(0.12, 104), (0.05, 100)]) == [None, False]


def screen(png):
    return np.asarray(Image.open(SCREENS / png).convert("RGB"))[:, :, ::-1]


@pytest.mark.parametrize(("png", "win_rate_x", "expected"), [
    # #69 (live 2026-10-17, floor 5 boss turn 6): slots 2-7 STAGGER, a yellow word on each dimmed portrait.
    ("BattleTurnStagger.png", 984, [False] + [True] * 6),
    # #427 (live 2026-11-04, EXP Luxcavation turn 5): slots 7 and 8 STAGGER+ (one unit and its second slot), a white word
    # on red cracks. Slots 2-4 and 6 are the dark guard icons of the other units' second slots.
    ("BattleTurnStaggerPlus.png", 1022, [False] * 6 + [True] * 2),
    # #427 (live 2026-11-05, turn 2, 3 slots): slot 3 STAGGER++, a white word on green cracks (scores 0.04, 0.12, 0.92).
    ("BattleTurnStaggerPlusPlus.png", 984 + 40.5 * (3 - 7), [False, False, True]),
    # Live 2026-10-28, EXP Luxcavation turn 4: slot 9 STAGGER on yellow cracks; slot 7 a dark shield icon.
    ("BattleTurnStaggerLast.png", 1061, [False] * 8 + [True]),
])
def test_staggered_reads_the_stagger_plates(png, win_rate_x, expected):
    assert b.staggered(screen(png), b.slot_xs(win_rate_x)) == expected


def test_staggered_holds_for_a_plate_of_another_colour_and_a_longer_word():
    # #427: the plates come in yellow, red and green (STAGGER++ is real, BattleTurnStaggerPlusPlus.png). A plate of a
    # colour no capture has: slot 8's STAGGER+ plate with its colour channels swapped (the red cracks blue) and
    # moved 6 px left, as a centred STAGGER++ moves its first seven letters, still reads staggered.
    image = screen("BattleTurnStaggerPlus.png").copy()
    x = b.slot_xs(1022)[7]
    image[630:680, x - 40:x + 40] = np.roll(image[630:680, x - 40:x + 40, ::-1], -6, axis=1)
    assert b.staggered(image, b.slot_xs(1022)) == [False] * 6 + [True] * 2


def test_the_stagger_word_is_cut_from_the_69_screen():
    word = recovery.unpng(b.STAGGER_WORD_PNG.read_bytes())
    assert np.array_equal(word, screen("BattleTurnStagger.png")[649:663, 582:630])  # slot 4's word, 2 px round it


def test_no_other_slot_of_tests_screens_reads_staggered():
    # CODING_STANDARDS' sweep: every slot position of 1 to 12 slots on every 1280x720 screen of tests/screens. Only the
    # plates above read staggered: 0.86-1.00 on them, 0.42 at most anywhere else (STAGGER_MATCH 0.6).
    xs = sorted({x for n in range(1, 13) for x in b.slot_xs(984 + 40.5 * (n - 7))})
    hits = {}
    for png in sorted(SCREENS.glob("*.png")):
        image = screen(png.name)
        if image.shape[:2] == (720, 1280) and (found := [x for x, s in zip(xs, b.staggered(image, xs)) if s]):
            hits[png.name] = found
    assert hits == {"BattleTurnStagger.png": b.slot_xs(984)[1:], "BattleTurnStaggerPlus.png": b.slot_xs(1022)[6:],
                    "BattleTurnStaggerPlusPlus.png": b.slot_xs(984 - 162)[2:],
                    "BattleTurnStaggerLast.png": b.slot_xs(1061)[8:]}


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


def gear(name):
    """tests/gears/<name>.png as BGR: 80x80 round the left gear (first slot's x - 86, y 576), written by recovery.png."""
    data = (Path(__file__).resolve().parent / "gears" / f"{name}.png").read_bytes()
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(80, 1 + 80 * 3)
    return rows[:, 1:].reshape(80, 80, 3)[:, :, ::-1]


@pytest.mark.parametrize(("name", "hollow"), [
    # #127 (live 2026-10-18): focused encounters show a hollow ring from the turn's start, nothing picked;
    # floor 3 boss on a dark ground, a floor 4 battle on a blue one, the floor 2 boss on an orange one.
    ("hollow_boss", True),
    ("hollow_floor4", True),
    ("hollow_floor2_boss", True),
    # Picks made by Win Rate show the ring too (BattleTurnLit.png, a normal battle; BattleTurnStagger.png).
    ("hollow_win_rate", True),
    ("hollow_stagger", True),
    # The chain's gear: a toothed wheel round a glass swirl (BattleTurn, -Even, -Solo), glowing once chained.
    ("gear_unlit", False),
    ("gear_unlit_even", False),
    ("gear_unlit_solo", False),
    ("gear_chained", False),
])
def test_gear_hollow(name, hollow):
    assert b.gear_hollow(gear(name), 40, 40) is hollow


@pytest.mark.parametrize(("png", "hollow"), [
    # live-1 F5 (2026-10-27): EXP Luxcavation's stage 9, a battle with the chain's gear: its 5 guard turns were played.
    ("LuxBattleTurn.png", False),
    # Thread Luxcavation's Faelantern (TETH), an Abnormality: a focused encounter, its skill slots over the enemy. The
    # guard chain cannot start there, so its turns are Win Rate and the guard turns wait (#127).
    ("LuxBattleTurnFocused.png", True),
])
def test_gear_hollow_on_the_luxcavation_battles(png, hollow):
    image = np.asarray(Image.open(SCREENS / png).convert("RGB"))[:, :, ::-1]
    assert b.gear_hollow(image, b.slot_xs(984)[0] - 86, 576) is hollow  # 7 slots: Win Rate at x 984
