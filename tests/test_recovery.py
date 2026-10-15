import json

import numpy as np
import pytest

from recovery import Ladder, Watchdog, read_runs, run_limit, same_screen, thumb


def screen(level):
    return np.full((720, 1280, 3), level, np.uint8)


A, B = thumb(screen(100)), thumb(screen(200))


def test_same_screen_ignores_flicker_not_change():
    flicker = screen(100)
    flicker[300:380, 300:380] = 255  # 4 of 576 blocks: the map's bus flame
    changed = screen(100)
    changed[:360] = 200
    assert same_screen(A, thumb(flicker))
    assert not same_screen(A, thumb(changed))
    assert not same_screen(A, None)


def test_watchdog_same_screen_five_times():
    w = Watchdog()
    assert [w.see("MirrorMap", A, t) for t in range(5)] == [False] * 4 + [True]


def test_watchdog_a_change_starts_over():
    w = Watchdog()
    for t in range(4):
        w.see("MirrorMap", A, t)
    assert not w.see("MirrorMap", B, 4)  # the map moved
    assert not w.see("Event", B, 5)  # same thumbnail, other screen type
    assert [w.see("Event", B, t) for t in range(6, 10)] == [False, False, False, True]


def test_watchdog_waits_go_by_time():
    w = Watchdog()
    assert not any(w.see("Loading", A, t) for t in range(0, 91, 10))  # 90 s is allowed, even unchanged
    assert w.see("Loading", B, 91)  # whatever it shows


def test_watchdog_battle_pause_needs_30_s_too():
    w = Watchdog()
    assert not any(w.see("BattlePause", A, t * 2) for t in range(10))  # 10 times in 18 s
    assert w.see("BattlePause", A, 30)


def test_watchdog_reset():
    w = Watchdog()
    for t in range(4):
        w.see("MirrorMap", A, t)
    w.reset()
    assert not w.see("MirrorMap", A, 4)


def test_ladder_climbs_until_the_screen_is_past():
    ladder = Ladder()
    assert ladder.stuck("MirrorMap", 1, 0) == (1, None)
    ladder.progress("MirrorMap")  # still the same screen
    ladder.progress("Loading")  # on the way back: not past it
    assert ladder.stuck("MirrorMap", 1, 0) == (2, None)
    assert ladder.stuck("NavDrive", 1, 0) == (3, None)  # any stuck in an open episode climbs
    assert ladder.stuck("MirrorMap", 1, 0) == (None, "L3 did not get past it")
    assert ladder.counts == {1: 1, 2: 1, 3: 1}


def test_ladder_same_screen_twice_in_a_run_stops():
    ladder = Ladder()
    assert ladder.stuck("Event", 1, 0) == (1, None)
    ladder.progress("MirrorMap")
    assert ladder.stuck("Shop", 1, 0) == (1, None)  # another screen: a fresh episode
    ladder.progress("MirrorMap")
    assert ladder.stuck("Event", 1, 0) == (None, "stuck on Event a second time this run")


def test_ladder_time_limits_start_at_l2():
    ladder = Ladder()
    assert ladder.stuck("BattleTurn", 2, 0) == (2, None)
    assert ladder.counts == {1: 0, 2: 1, 3: 0}


@pytest.mark.parametrize("counts, l3_execution, start, expected", [
    ({1: 0, 2: 3, 3: 0}, 0, 2, (None, "L2 used 3 times this run")),
    ({1: 0, 2: 0, 3: 2}, 0, 3, (None, "game restarted 2 times this run")),
    ({1: 0, 2: 0, 3: 1}, 3, 3, (None, "game restarted 3 times since the bot started")),
    ({1: 0, 2: 2, 3: 1}, 2, 2, (2, None)),
])
def test_ladder_limits(counts, l3_execution, start, expected):
    ladder = Ladder()
    ladder.counts = dict(counts)
    assert ladder.stuck("MirrorMap", start, l3_execution) == expected


def line(team, minutes, result="clear"):
    return {"start": "2026-10-16T00:00:00.000Z", "end": f"2026-10-16T{minutes // 60:02}:{minutes % 60:02}:00.000Z",
            "team": team, "result": result}


def test_run_limit_default_under_10_runs():
    assert run_limit([line("a", 30)] * 9, "a") == 3600


def test_run_limit_twice_p95():
    lines = [line("a", m) for m in range(30, 50)] + [line("b", 300)]  # 30..49 min; b is another team
    assert run_limit(lines, "a") == pytest.approx(2 * 48.05 * 60)


def test_run_limit_only_clears_after_the_latest_reset():
    old = [line("a", 200)] * 20
    new = [line("a", 40)] * 10 + [line("a", 5, "stop"), line("a", 5, "giveup"), {**line("a", 5), "start": None}]
    lines = old + [{"reset": "a", "time": "x"}] + [line("a", 300)] * 5 + [{"reset": "a", "time": "y"}] + new
    assert run_limit(lines, "a") == pytest.approx(2 * 40 * 60)
    assert run_limit(lines + [{"reset": "a", "time": "z"}], "a") == 3600
    assert run_limit(lines, "b") == 3600


def test_read_runs_skips_bad_lines(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "runs.jsonl").write_text(json.dumps(line("a", 1)) + "\nnot json\n[1]\n" + json.dumps({"reset": "a", "time": "t"}) + "\n", encoding="utf-8")
    assert read_runs(tmp_path) == [line("a", 1), {"reset": "a", "time": "t"}]
    assert read_runs(tmp_path / "missing") == []


def test_png_round_trip():
    import struct
    import zlib

    from recovery import png

    image = np.zeros((2, 3, 3), np.uint8)
    image[0, 1] = (255, 0, 0)  # blue in BGR
    data = png(image)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (3, 2)  # IHDR width, height
    idat = data.index(b"IDAT")
    size = struct.unpack(">I", data[idat - 4:idat])[0]
    rows = zlib.decompress(data[idat + 4:idat + 4 + size])
    assert rows == b"\0" + bytes([0, 0, 0, 0, 0, 255, 0, 0, 0]) + b"\0" + bytes(9)  # filter byte, then RGB
