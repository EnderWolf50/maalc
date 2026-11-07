import numpy as np
import pytest

from live import evidence as ev
from live import map_taps as mt

W, H = 1280, 720


def touch(stamp, x, y):
    """A controller touch line at game pixel (x, y), in the device's 1920x1080 as run.log has it."""
    return f"{stamp} x: {round(x * 1.5)}, y: {round(y * 1.5)}, width: 1920, height: 1080, rotation: 90.000000, product_major: 0"


def drag(start, x, y, dx, step=0.011):
    """scroll()'s points: down, the 10 px threshold move, a 0.11 s rest, then 20 px moves `step` s apart."""
    t = ev.secs(start)
    sign = 1 if dx > 0 else -1
    pts = [(t, x), (t + 0.001, x + 10 * sign)] + [(t + 0.112 + k * step, x + 10 * sign + 20 * sign * (k + 1)) for k in range(abs(dx) // 20)]
    return [touch(ev.hms(u), px, y) for u, px in pts]


# One map visit after a fight: a reward tap off the map, find_bus's drag, the full read, the take; then a follow that
# the map ignores once and takes on the tap after.
RUN = [
    "10:00:00.000 [maalc] victory",
    "10:00:01.000 [maalc] reward cards: Cost Gift Chance: take 'Cost Gift Chance'",
    touch("10:00:01.001", 554, 300),
    *drag("10:00:04.000", 852, 391, -406),
    "10:00:05.500 [maalc] map: node at 328, 357 reads Cost 85: battle",
    "10:00:05.600 [maalc] map: column 1: mid battle (1 onward)",
    "10:00:05.700 [maalc] map: path mid battle > down shop, score 18",
    touch("10:00:05.800", 328, 357),
    "10:00:06.200 [maalc] map: take mid battle",
    "10:00:06.300 [maalc] entered the node",
    "10:00:20.000 [maalc] victory",
    touch("10:00:25.000", 725, 285),
    "10:00:25.700 [maalc] map: no answer to the tap at 725, 285; tapping again",
    touch("10:00:25.900", 725, 285),
    "10:00:26.300 [maalc] map: follow plan mid battle",
]


def kinds(rows):
    return [(ev.hms(r.t), r.kind, (r.x, r.y), r.outcome) for r in rows]


def test_map_touches_take_the_kind_from_the_log_lines_and_leave_other_pages_out():
    rows = mt.map_touches(ev.parse_log(RUN))
    assert kinds(rows) == [
        ("10:00:04.000", "find_bus", (852, 391), "read"),
        ("10:00:05.800", "take", (328, 357), "map: take"),
        ("10:00:25.000", "follow", (725, 285), "tapping again"),
        ("10:00:25.900", "follow", (725, 285), "follow plan"),
    ]


def test_a_drag_is_one_touch_that_moves_after_the_threshold_rest():
    rows = mt.map_touches(ev.parse_log(RUN))
    bus = rows[0]
    assert bus.drag and bus.moves_at == pytest.approx(ev.secs("10:00:04.112"))
    assert [r.drag for r in rows[1:]] == [False, False, False]


def test_a_full_read_tap_before_the_one_that_took_is_its_next_try():
    log = ev.parse_log([
        "11:00:00.000 [maalc] map: path up event > mid risky, score 22",
        touch("11:00:00.100", 1077, 144),
        touch("11:00:02.400", 1077, 357),
        "11:00:02.900 [maalc] map: take mid risky",
    ])
    assert [(r.kind, r.outcome) for r in mt.map_touches(log)] == [("take", "next try"), ("take", "map: take")]


def test_a_full_read_no_slot_took_ends_on_its_own_outcome():
    log = ev.parse_log([
        "11:00:00.000 [maalc] map: path up event > mid risky, score 22",
        touch("11:00:00.100", 1077, 144),
        touch("11:00:02.400", 1077, 357),
        "11:00:04.500 [maalc] map: no node took a tap; MirrorHub looks again",
    ])
    assert [(r.kind, r.outcome) for r in mt.map_touches(log)] == [("take", "next try"), ("take", "no node took a tap")]


def test_the_touches_after_the_unzoom_tap_still_count():
    log = ev.parse_log([
        "11:00:00.000 [maalc] map: zoomed in on the bus; opening and closing its node panel",
        touch("11:00:00.100", 500, 400),
        *drag("11:00:01.500", 852, 391, -406),
        "11:00:03.000 [maalc] map: column 1: mid battle (1 onward)",
    ])
    assert [(r.kind, r.outcome) for r in mt.map_touches(log)] == [("unzoom", "read"), ("find_bus", "read")]


def test_the_theme_pack_drag_before_the_new_floor_is_no_map_touch():
    log = ev.parse_log([
        "12:00:00.000 [maalc] floor 2: pull 'Emotional Seduction' (0)",
        *drag("12:00:00.010", 429, 330, 320),
        *drag("12:00:01.500", 852, 391, -406),
        "12:00:03.000 [maalc] map: node at 328, 357 reads Cost 85: battle",
    ])
    assert [(ev.hms(r.t), r.kind) for r in mt.map_touches(log)] == [("12:00:01.500", "find_bus")]


# --- the screen ------------------------------------------------------------------------------------------

FPS = 10
MAP = np.random.default_rng(7).integers(40, 200, (H // 40, W // 40, 1), dtype=np.uint8).repeat(40, 0).repeat(40, 1).repeat(3, 2)  # every 40x40 block its own grey
PANEL = MAP.copy()
PANEL[:, 320:] = 250  # a node panel over three quarters of the screen
BLACK = np.zeros((H, W, 3), np.uint8)


def screen(t0, scenes, t1, flicker=True):
    """Frames at FPS from t0 to t1: scenes is [(from, image)], each shown from its time on. The top-left block flickers
    every other frame, as the map's bus flame does (one block of 576, under same_screen's 3%); flicker=False repeats
    each scene's frame pixel for pixel, as a recorder that lost its frames does."""
    times = [t0 + k / FPS for k in range(round((t1 - t0) * FPS))]
    out = []
    for k, t in enumerate(times):
        im = next(im for u, im in reversed(scenes) if u <= t + 1e-9)
        if flicker and k % 2:
            im = im.copy()
            im[:40, :40] = 255 - im[:40, :40]
        out.append(im)
    return mt.Frames.of(times, out)


def test_a_taken_tap_answers_and_an_ignored_one_does_not_until_the_tap_after_it():
    t = ev.secs("10:00:25.000")
    # black until the fade, the map from t - 1.3, still through the first tap; the second tap opens the panel
    frames = screen(t - 3, [(t - 3, BLACK), (t - 1.3, MAP), (t + 0.9 + 0.1, PANEL)], t + 3)
    log = ev.parse_log(RUN)
    rows = mt.judge([frames], mt.map_touches(log)[2:], mt.strokes(log), offset=0.1)
    first, second = rows
    assert (first.verdict, first.answer) == ("ignored", None) and first.share < 0.03
    # the last black frame is one frame before the map; the touch reaches the screen offset s after its log line
    assert first.since_fade == pytest.approx(1.3 + 1 / FPS + 0.1) and first.first_after_fade
    assert second.verdict == "taken" and second.share == pytest.approx(0.75, abs=0.01)
    assert second.answer == pytest.approx(0.0, abs=1 / FPS) and not second.first_after_fade


def test_a_touch_that_ended_after_the_black_frame_makes_the_next_one_not_the_first():
    # the event page's taps at (5, 5), three within 0.25 s, the last one while the screen is black
    log = ev.parse_log([
        touch("10:00:21.000", 5, 5), touch("10:00:21.150", 5, 5), touch("10:00:21.300", 5, 5),
        "10:00:22.000 [maalc] Event: Event is gone: back to MirrorHub",
        *drag("10:00:24.000", 852, 391, -406),
        "10:00:25.500 [maalc] map: node at 328, 357 reads Cost 85: battle",
    ])
    t = ev.secs("10:00:24.000")
    frames = screen(t - 4, [(t - 4, BLACK), (ev.secs("10:00:21.250"), MAP)], t + 2)
    row = mt.judge([frames], mt.map_touches(log), mt.strokes(log), offset=0.1)[0]
    assert row.since_fade is not None and not row.first_after_fade


def test_a_touch_with_no_black_frame_in_the_window_has_no_fade():
    t = ev.secs("10:00:25.000")
    frames = screen(t - 12, [(t - 12, MAP), (t + 0.2, PANEL)], t + 1)
    log = ev.parse_log(RUN)
    row = mt.judge([frames], mt.map_touches(log)[2:3], mt.strokes(log), offset=0.1, fade_window=10)[0]
    assert row.verdict == "taken" and row.since_fade is None
    assert mt.csv_row(row, fade_window=10)["since_fade_s"] == "none in 10 s"


def test_a_fade_window_the_recording_does_not_cover_says_how_far_it_looked():
    t = ev.secs("10:00:25.000")
    frames = screen(t - 2, [(t - 2, MAP), (t + 0.2, PANEL)], t + 1)  # the recording starts 2 s before the tap
    log = ev.parse_log(RUN)
    row = mt.judge([frames], mt.map_touches(log)[2:3], mt.strokes(log), offset=0.1, fade_window=10)[0]
    assert mt.csv_row(row, fade_window=10)["since_fade_s"] == "none in 2.1 s of video"


def test_a_window_the_recorder_froze_on_is_frozen_not_ignored():
    t = ev.secs("10:00:25.000")
    frames = screen(t - 3, [(t - 3, MAP)], t + 3, flicker=False)
    log = ev.parse_log(RUN)
    assert mt.judge([frames], mt.map_touches(log)[2:3], mt.strokes(log), offset=0.1)[0].verdict == "frozen"


def test_the_offset_is_measured_from_the_drags_the_map_followed():
    log = ev.parse_log([
        *drag("10:00:04.000", 852, 391, -406),
        "10:00:05.500 [maalc] map: node at 328, 357 reads Cost 85: battle",
        *drag("10:00:10.000", 852, 391, -406),
        "10:00:11.500 [maalc] map: node at 328, 357 reads Cost 85: battle",
    ])
    moved = np.roll(MAP, -200, axis=1)
    a, b = ev.secs("10:00:04.112"), ev.secs("10:00:10.112")
    frames = screen(a - 2, [(a - 2, MAP), (a + 0.3, moved), (b - 1, MAP), (b + 0.3, moved)], b + 2)
    off = mt.measure_offset([frames], mt.map_touches(log))
    assert off.value == pytest.approx(0.3, abs=1e-6) and off.n == 2


def test_the_summary_counts_each_kind_and_verdict_and_the_range_after_a_fade():
    row = lambda kind, verdict, since, first: mt.Row(0, 0, 0, kind, "follow plan", False, 0, verdict, 0.5, 0.1, since, first)  # noqa: E731
    text = mt.summary([row("follow", "ignored", 1.16, True), row("follow", "ignored", 1.46, True),
                       row("follow", "taken", 1.32, True), row("follow", "taken", 8.0, False)],
                      mt.Offset(0.067, 9, 0.033, 0.1))
    assert "offset +0.067 s" in text
    assert "follow    ignored        2     2  1.16-1.46 s   1.16-1.46 s" in text
    assert "follow    taken          2     1  1.32-1.32 s   1.32-8.00 s" in text


def test_the_summary_prints_the_offset_it_used_when_none_was_measured():
    assert mt.summary([], None).startswith("offset +0.000 s (no map drag to measure it on)")
