import json
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
from recovery import (GAME, TRANSIT, WAIT_STILL, Ladder, Watchdog, floor_limit, focused_package, over_time, read_runs,
                      run_limit, same_screen, thumb)
from test_pipeline import load_nodes


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
    assert [bool(w.see("MirrorMap", A, t)) for t in range(5)] == [False] * 4 + [True]


def test_watchdog_a_change_starts_over():
    w = Watchdog()
    for t in range(4):
        w.see("MirrorMap", A, t)
    assert not w.see("MirrorMap", B, 4)  # the map moved
    assert not w.see("Event", B, 5)  # same thumbnail, other screen type
    assert [bool(w.see("Event", B, t)) for t in range(6, 10)] == [False, False, False, True]


def dots(n):
    """Loading.png's NOW LOADING... as it animates: n of its 3 dots, a few pixels of one block."""
    image = screen(100)
    for i in range(n % 4):
        image[648:652, 1200 + 6 * i:1204 + 6 * i] = 255
    return thumb(image)


def test_watchdog_a_moving_load_is_no_stuck_until_the_cap():
    # #179: 30 FPS and a loaded CPU took 105 s over a Now Loading that kept moving.
    w = Watchdog()
    assert not any(w.see("Loading", dots(t), t) for t in range(0, 150))
    assert w.see("Loading", dots(3), 151)  # WAIT_CAP: a load moving for ever is stuck too


def test_watchdog_a_still_load_is_stuck_after_wait_still():
    # #179: a load that came through sat still 59 and ~66 s on that host; 2026-10-17 one sat still 89.5 s from its start.
    w = Watchdog()
    assert not any(w.see("Loading", dots(t), t) for t in range(0, 30))  # moving
    assert not any(w.see("Loading", A, t) for t in range(30, 30 + WAIT_STILL))  # still since 30
    assert w.see("Loading", A, 30 + WAIT_STILL)


def test_watchdog_a_load_that_moves_again_starts_the_still_clock_over():
    w = Watchdog()
    assert not any(w.see("Connecting", A, t) for t in range(0, 70))
    assert not w.see("Connecting", dots(1), 70)
    assert not any(w.see("Connecting", dots(1), t) for t in range(71, 70 + WAIT_STILL))
    assert w.see("Connecting", dots(1), 70 + WAIT_STILL)


def test_watchdog_loading_and_connecting_in_turn_share_the_cap():
    w = Watchdog()
    assert not any(w.see("Connecting" if t % 20 < 10 else "Loading", dots(t), t) for t in range(0, 150))
    assert w.see("Loading", dots(1), 151)


def test_watchdog_another_screen_between_two_loads_starts_the_cap_over():
    w = Watchdog()
    assert not any(w.see("Loading", dots(t), t) for t in range(0, 140))
    assert not w.see("Victory", B, 140)
    assert not any(w.see("Loading", dots(t), t) for t in range(141, 290))


def test_watchdog_a_download_waits_as_long_as_it_moves():
    # Live 2026-10-21: 17.77 GB took ~32 min over DOWNLOADING UPDATE, then DOWNLOADING RESOURCES; no cap.
    w = Watchdog()
    assert not any(w.see("Downloading", dots(t), t) for t in range(0, 3600, 5))
    assert not any(w.see("Downloading", A, t) for t in range(3600, 3600 + WAIT_STILL))
    assert w.see("Downloading", A, 3600 + WAIT_STILL)  # a download that stopped moving is stuck


def test_watchdog_a_load_after_a_long_download_has_its_own_cap():
    w = Watchdog()
    assert not any(w.see("Downloading", dots(t), t) for t in range(0, 1800, 5))
    assert not any(w.see("Loading", dots(t), t) for t in range(1800, 1900))


def test_watchdog_a_still_screen_of_another_type_does_not_start_the_wait_still():
    w = Watchdog()
    for t in range(3):
        w.see("Victory", A, t)
    assert not any(w.see("Loading", A, t) for t in range(3, 3 + WAIT_STILL))  # the same picture, Loading since 3
    assert w.see("Loading", A, 3 + WAIT_STILL)


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
    assert ladder.stuck("MirrorMap", 1, 1) == (3, None)  # L3 again: a restart may hang too
    assert ladder.stuck("MirrorMap", 1, 2) == (None, "game restarted 2 times this run")
    assert ladder.counts == {1: 1, 2: 1, 3: 2}


def test_ladder_progress_starts_the_next_stuck_over():
    ladder = Ladder()
    assert ladder.stuck("Event", 1, 0) == (1, None)
    assert ladder.stuck("Event", 1, 0) == (2, None)
    ladder.progress("MirrorMap")  # got past it
    assert ladder.stuck("Event", 1, 0) == (1, None)  # the same screen again: a fresh episode, not a stop
    ladder.progress("Event")  # still the stuck screen: the episode stays open
    assert ladder.stuck("Event", 1, 0) == (2, None)
    assert ladder.counts == {1: 2, 2: 2, 3: 0}


def test_ladder_time_limits_start_at_l2():
    ladder = Ladder()
    assert ladder.stuck("MirrorMap", 2, 0) == (2, None)
    assert ladder.counts == {1: 0, 2: 1, 3: 0}


@pytest.mark.parametrize("kind", ["BattleTurn", "BattlePause", "BattleMenu"])  # BattleMenu: the pause menu (#215)
def test_ladder_skips_l2_in_battle(kind):
    # L2 only goes through on the map: mid-battle it failed after 20 s and the L3 restart followed anyway
    # (live 2026-10-17, #70). A battle climbs from L1 straight to L3; its time limit starts there.
    ladder = Ladder()
    assert ladder.stuck(kind, 1, 0) == (1, None)
    assert ladder.stuck(kind, 1, 0) == (3, None)
    assert Ladder().stuck(kind, 2, 0) == (3, None)
    assert ladder.counts == {1: 1, 2: 0, 3: 1}


def test_ladder_a_level_that_did_not_go_through_is_not_charged_to_the_run():
    # Live 2026-10-17 (#70): `am force-stop` failed once (adb exit 1), then the restart that went through
    # hung on NOW LOADING; the failed one had used up one of the run's 2 restarts, so the bot stopped.
    ladder = Ladder()
    assert ladder.stuck("BattleTurn", 1, 0) == (1, None)
    assert ladder.stuck("BattleTurn", 1, 0) == (3, None)
    ladder.failed(3)
    assert ladder.stuck("BattleTurn", 1, 1) == (3, None)  # the same episode retries the restart
    assert ladder.stuck("Loading", 1, 2) == (3, None)  # the restarted game hangs: one more within the run's 2
    assert ladder.counts == {1: 1, 2: 0, 3: 2}
    assert ladder.stuck("Loading", 1, 2) == (None, "game restarted 2 times this run")


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


def test_floor_limit_45_min_unless_history_says_longer():
    # Live 2026-10-16 (#34): hard runs took 80 and 107 min, floors up to ~25 min, all of it progress.
    assert floor_limit([], "a") == 45 * 60
    assert floor_limit([line("a", 40)] * 10, "a") == 45 * 60  # a fast team keeps the floor's 45 min
    assert floor_limit([line("a", 150)] * 10, "a") == pytest.approx(2 * 150 * 60 / 5)


@pytest.mark.parametrize("kind, now, expected", [
    ("MirrorMap", 999, False),
    ("MirrorMap", 1001, True),  # on the map, where L2 goes through
    ("BattleTurn", 1001, False),  # mid-battle L2 cannot go through: L3 would restart the battle
    ("Event", 1000 + 20 * 60, False),
    ("Event", 1001 + 20 * 60, True),  # not back on the map a battle's limit later: fire anyway
])
def test_over_time_waits_for_the_map(kind, now, expected):
    assert over_time(kind, 1000, now) is expected
    assert over_time(kind, None, now) is False  # no deadline: a resumed run


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


def test_watchdog_a_download_is_no_stuck_while_held():
    # #86: the title's download dialog was confirmed: a big update can sit on one unchanged screen for minutes.
    w = Watchdog()
    w.hold(0, 1800)
    assert not any(w.see("NavTitle", A, t) for t in range(0, 1800, 10))
    assert w.see("NavTitle", A, 1801)  # the hold is over: that is stuck again
    w.hold(2000, 600)
    w.reset()  # a recovery wipes the hold with the rest
    assert not w.held(2001)


def test_ladder_the_downloading_screens_are_on_the_way_back_not_past_the_stuck_one():
    ladder = Ladder()
    assert ladder.stuck("NavTitle", 1, 0) == (1, None)
    for kind in ("DownloadDialog", "PopupButton"):
        ladder.progress(kind)  # an acknowledged dialog on the title does not end the episode
    assert ladder.stuck("NavTitle", 1, 0) == (2, None)


def test_keep_unknown_saves_the_screen_and_keeps_only_the_latest(tmp_path):
    # #85/#87: a screen MirrorHub does not know is the capture the missing popup nodes need.
    from recovery import UNKNOWN_KEEP, keep_unknown
    for i in range(UNKNOWN_KEEP + 2):
        keep_unknown(tmp_path, screen(i), f"2026-10-18T00-00-{i:02}.000Z")
    saved = sorted(p.name for p in (tmp_path / "logs" / "unknown").iterdir())
    assert len(saved) == UNKNOWN_KEEP
    assert saved[0] == "2026-10-18T00-00-02.000Z.png"  # the two oldest went
    assert (tmp_path / "logs" / "unknown" / saved[-1]).read_bytes().startswith(b"\x89PNG")


def test_notices_at_login_do_not_end_a_stuck_spell():
    # spec 06: screens on the way back to a run (a login may open the notices) are not progress.
    assert "Notices" in TRANSIT


GAME_FOCUS = "  mCurrentFocus=Window{1d4e2f0 u0 com.ProjectMoon.LimbusCompany/com.unity3d.player.UnityPlayerActivity}\n"


@pytest.mark.parametrize("dumpsys, expected", [
    (GAME_FOCUS, GAME),
    ("  mCurrentFocus=Window{9a1b u0 com.android.vending/com.google.android.finsky.activities.MainActivity}\n",
     "com.android.vending"),
    ("  mCurrentFocus=null\n", ""),  # live 2026-10-22: the game's first launch after an update, black for 5 min
    ("  mCurrentFocus=null\n" + GAME_FOCUS, GAME),  # one line per display: the game on any of them is in front
    ("", None),  # not read (no adb, or no such line): unknown
])
def test_focused_package(dumpsys, expected):
    assert focused_package(dumpsys) == expected


def test_the_game_package_is_the_one_l3_restarts():
    nodes = load_nodes()
    assert nodes["RecoverL3"]["package"] == nodes["RecoverStartApp"]["package"] == GAME


def test_ladder_a_game_not_in_front_goes_straight_to_l3():
    ladder = Ladder()
    assert ladder.stuck("MirrorMap", 1, 0) == (1, None)
    assert ladder.stuck("MirrorMap", 3, 0) == (3, None)  # in an open episode too: L2 cannot help
    assert ladder.counts == {1: 1, 2: 0, 3: 1}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    """A fake Maa context for Recover: a blank screen, every recovery level goes through; a fresh ladder."""
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    actions.RUN.clear()
    actions.STUCK["flag"] = None
    actions.STUCK["watch"].reset()
    actions.STUCK["ladder"].__init__()
    yield ctx
    actions.RUN.clear()
    actions.STUCK["flag"] = None
    actions.STUCK["ladder"].__init__()


@pytest.mark.parametrize("focus, flag, first", [
    ("com.android.vending/x", None, "RecoverL3"),  # #86: the Play Store in front; the back key would only work it
    ("null", None, "RecoverL3"),  # #86 live: the game alive, black, no window focused for 5 min
    ("com.ProjectMoon.LimbusCompany/x", None, "RecoverL1"),
    ("com.android.vending/x", ("MirrorMap", 1, "the map did not change"), "RecoverL1"),  # a screen of the game was read
])
def test_recover_restarts_the_game_when_it_is_not_in_front(hub, focus, flag, first):
    actions.STUCK["flag"] = flag  # None: MirrorHub recognised nothing
    shell = hub.tasker.controller.post_shell
    window = "null" if focus == "null" else "Window{1 u0 " + focus + "}"
    shell.return_value.wait.return_value.get.return_value = f"  mCurrentFocus={window}\n"
    actions.Recover().run(hub, None)
    assert hub.run_task.call_args_list[0].args == (first,)
    assert shell.called == (flag is None)


@pytest.mark.parametrize("failed", ["raises", "not succeeded"])
def test_recover_climbs_as_before_when_the_focus_cannot_be_read(hub, failed):
    job = hub.tasker.controller.post_shell.return_value.wait.return_value
    if failed == "raises":  # not an adb controller
        job.get.side_effect = RuntimeError("no adb")
    else:  # adb failed: the output may be the last command's
        job.succeeded = False
        job.get.return_value = "  mCurrentFocus=Window{1 u0 com.android.vending/x}\n"
    actions.Recover().run(hub, None)
    assert hub.run_task.call_args_list[0].args == ("RecoverL1",)
