import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
from recovery import (GAME, L2_SCREENS, TRANSIT, WAIT_STILL, Ladder, Restarts, Watchdog, floor_limit, focused_package,
                      over_time, read_runs, run_limit, same_screen, thumb)
from test_pipeline import hub_entries, load_nodes


def screen(level):
    return np.full((720, 1280, 3), level, np.uint8)


A, B = thumb(screen(100)), thumb(screen(200))
WAY_BACK = ("NavTitle", "Connecting", "Loading", "NavMainTabs", "NavDrive", "GoToMirrorEntry", "MirrorEntryPaused",
            "ResumeDialog", "Loading")


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


def test_watchdog_a_tab_tapped_over_and_over_is_stuck_however_the_screen_moves():
    # Acceptance 5 (live 2026-10-28): after an L3 the Drive tab was tapped 2188 times in 45 min, the game showing its tap
    # but never the Drive page; the main window's banners moved all along, so the same-screen count never got to 5.
    w = Watchdog()
    moving = [A, B] * 10
    assert not any(w.see("NavMainTabs", moving[t], t) for t in range(9))
    assert w.see("NavMainTabs", moving[9], 9)
    w = Watchdog()  # a tab that opens its page: another screen comes between two taps
    assert not any(w.see(kind, moving[t % 20], t) for t in range(40) for kind in ("NavMainTabs", "NavDrive"))
    w = Watchdog()  # screens that repeat while the game moves on are not taps
    assert not any(w.see("BattleTurn", moving[t % 20], t) for t in range(40))


def test_a_tab_that_never_opens_after_a_restart_restarts_again_then_stops():
    # Acceptance 5: the battle froze (L1, then L3), and the restarted game would not open Drive. The tab's stuck is the
    # same episode (NavMainTabs is on the way back): L3 again, and once this run's restarts are used up, the stop.
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("BattlePause", 1, restarts) == (1, None)
    assert ladder.stuck("BattlePause", 1, restarts) == (3, None)
    ladder.progress("NavMainTabs")
    assert ladder.stuck("NavMainTabs", 1, restarts) == (3, None)
    ladder.progress("NavMainTabs")
    assert ladder.stuck("NavMainTabs", 1, restarts) == (None, "game restarted 2 times this run")


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


def test_two_dead_taps_of_one_picture_are_a_frozen_game():
    # #440: the main window shown to the byte through two taps' whole waits.
    w = Watchdog()
    assert w.tapped(A) is None
    assert "frozen" in w.tapped(A)


def test_a_dead_tap_streak_starts_over_on_a_live_tap_another_picture_or_a_reset():
    live = Watchdog()
    live.tapped(A)
    assert live.tapped(None) is None and live.tapped(A) is None  # the game took a tap between: alive
    moved = Watchdog()
    moved.tapped(A)
    assert moved.tapped(B) is None  # the picture changed between the two waits: alive
    assert "frozen" in moved.tapped(B)
    reset = Watchdog()
    reset.tapped(A)
    reset.reset()  # forget_game_state, after any recovery
    assert reset.tapped(A) is None


def test_ladder_climbs_until_the_screen_is_past():
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("MirrorMap", 1, restarts) == (1, None)
    ladder.progress("MirrorMap")  # still the same screen
    ladder.progress("Loading")  # on the way back: not past it
    assert ladder.stuck("MirrorMap", 1, restarts) == (2, None)
    assert ladder.stuck("NavDrive", 1, restarts) == (3, None)  # any stuck in an open episode climbs
    assert ladder.stuck("MirrorMap", 1, restarts) == (3, None)  # L3 again: a restart may hang too
    assert ladder.stuck("MirrorMap", 1, restarts) == (None, "game restarted 2 times this run")
    assert ladder.counts == {1: 1, 2: 1, 3: 2}


def test_ladder_progress_starts_the_next_stuck_over():
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("MirrorMap", 1, restarts) == (1, None)
    assert ladder.stuck("MirrorMap", 1, restarts) == (2, None)
    ladder.progress("Event")  # got past it
    assert ladder.stuck("MirrorMap", 1, restarts) == (1, None)  # the same screen again: a fresh episode, not a stop
    ladder.progress("MirrorMap")  # still the stuck screen: the episode stays open
    assert ladder.stuck("MirrorMap", 1, restarts) == (2, None)
    assert ladder.counts == {1: 2, 2: 2, 3: 0}


def test_ladder_on_the_map_climbs_l1_l2_l3():
    # The map is where L2 goes through: its gear opens Dungeon Progress, whose To Window saves the run (spec 06).
    ladder, restarts = Ladder(), Restarts()
    assert [ladder.stuck("MirrorMap", 1, restarts) for _ in range(3)] == [(1, None), (2, None), (3, None)]
    assert ladder.counts == {1: 1, 2: 1, 3: 1}


def test_ladder_l2_on_an_open_dungeon_progress_panel():
    # A panel the hub's Continue does not close: RecoverToWindow taps its To Window, so L2 goes through there too. The
    # panel is on the way back (TRANSIT): a map episode that L1's back key left on it is still that episode.
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("ProgressPanel", 1, restarts) == (1, None)
    assert ladder.stuck("ProgressPanel", 1, restarts) == (2, None)
    episode = Ladder()
    assert episode.stuck("Shop", 1, restarts) == (1, None)
    episode.progress("ProgressPanel")
    assert episode.stuck("ProgressPanel", 1, restarts) == (2, None)


# Every screen but the map and the open panel: RecoverL2 recognises neither its gear (MirrorMap) nor its panel there, and
# waited out its 20 s timeout before L3 (#439). An event's back key opens the panel, but the hub's ProgressPanel closes it
# before the next stuck. MapNodePanel hides the map (maatools.config.mts: MapNodePanel.png reads no MirrorMap); under GiftGet
# the map reads, but its GET! window is what a tap lands on (unverified whether the gear takes it).
@pytest.mark.parametrize("kind", ["BattleTurn", "BattlePause", "BattleMenu",  # BattleMenu: the pause menu (#215)
                                  "Event", "Shop", "ThemePack", "RewardCard", "GiftGet", "MapNodePanel", "Formation",
                                  "Loading", "ResumeDialog", "MirrorMap, then nothing recognised"])
def test_ladder_skips_l2_off_the_map(kind):
    # Live 2026-10-17 (#70): mid-battle L2 failed after 20 s and the L3 restart followed anyway. Off the map a stuck climbs
    # from L1 straight to L3, not charged to L2; a time limit that starts at L2 starts there.
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck(kind, 1, restarts) == (1, None)
    assert ladder.stuck(kind, 1, restarts) == (3, None)
    assert Ladder().stuck(kind, 2, Restarts()) == (3, None)
    assert ladder.counts == {1: 1, 2: 0, 3: 1}


def test_l2_screens_are_what_recover_l2_recognises():
    # RecoverL2 acts on the map its gear node recognises and on the panel RecoverToWindow reads; the hub hands both out.
    nodes = load_nodes()
    assert nodes["RecoverL2"]["next"] == ["RecoverToWindow", "RecoverGear"]
    assert L2_SCREENS == set(nodes["RecoverGear"]["any_of"]) | {"ProgressPanel"}
    hub = hub_entries(nodes, "HubText") + nodes["HubText"]["custom_recognition_param"]["tail"]
    assert L2_SCREENS <= set(hub)


def test_ladder_a_map_episode_on_a_loading_screen_skips_l2():
    # L1 on the map, then the game hangs on the way back (Loading is TRANSIT: the same episode). L2 asks the screen now.
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("MirrorMap", 1, restarts) == (1, None)
    ladder.progress("Loading")
    assert ladder.stuck("Loading", 1, restarts) == (3, None)
    assert ladder.counts == {1: 1, 2: 0, 3: 1}


def test_ladder_time_limits_start_at_l2():
    ladder = Ladder()
    assert ladder.stuck("MirrorMap", 2, Restarts()) == (2, None)
    assert ladder.counts == {1: 0, 2: 1, 3: 0}


def test_ladder_a_level_that_did_not_go_through_is_not_charged_to_the_run():
    # Live 2026-10-17 (#70): `am force-stop` failed once (adb exit 1), then the restart that went through
    # hung on NOW LOADING; the failed one had used up one of the run's 2 restarts, so the bot stopped.
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("BattleTurn", 1, restarts) == (1, None)
    assert ladder.stuck("BattleTurn", 1, restarts) == (3, None)
    ladder.failed(3)
    assert ladder.stuck("BattleTurn", 1, restarts) == (3, None)  # the same episode retries the restart
    assert ladder.stuck("Loading", 1, restarts) == (3, None)  # the restarted game hangs: one more within the run's 2
    assert ladder.counts == {1: 1, 2: 0, 3: 2}
    assert ladder.stuck("Loading", 1, restarts) == (None, "game restarted 2 times this run")


@pytest.mark.parametrize("counts, failed, start, expected", [
    ({1: 0, 2: 3, 3: 0}, 0, 2, (None, "L2 used 3 times this run")),
    ({1: 0, 2: 0, 3: 2}, 0, 3, (None, "game restarted 2 times this run")),
    ({1: 0, 2: 0, 3: 1}, 3, 3, (None, "game restarted 3 times in a row without getting past MirrorMap")),
    ({1: 0, 2: 2, 3: 1}, 2, 2, (2, None)),
])
def test_ladder_limits(counts, failed, start, expected):
    ladder, restarts = Ladder(), Restarts()
    ladder.counts = dict(counts)
    for _ in range(failed):
        restarts.attempt("MirrorMap")
    assert ladder.stuck("MirrorMap", start, restarts) == expected


def restart(ladder, restarts, kind="BattlePause"):
    """One restart (L3) that went through and got past its screen."""
    ladder.progress("MirrorMap")
    restarts.progress("MirrorMap")
    if not ladder.open:
        assert ladder.stuck(kind, 1, restarts) == (1, None)
    return ladder.stuck(kind, 1, restarts)


def test_ladder_a_target_15_run_gets_the_allowance_again_at_floors_6_and_11():
    # #435: each 5-floor stretch of a long run gets what a v1 run gets, 3 L2 and 2 L3; floors 2-5 and 7-10 do not refill.
    ladder, restarts = Ladder(), Restarts()
    for floor in range(1, 6):
        ladder.floor(floor, 15)
    assert [restart(ladder, restarts) for _ in range(3)] == [(3, None), (3, None), (None, "game restarted 2 times this run")]
    for floor in range(6, 11):
        ladder.floor(floor, 15)
    assert [restart(ladder, restarts) for _ in range(3)] == [(3, None), (3, None), (None, "game restarted 2 times since floor 6")]
    ladder.progress("Event")
    for _ in range(3):
        assert ladder.stuck("MirrorMap", 2, restarts) == (2, None)
        ladder.progress("Event")
    assert ladder.stuck("MirrorMap", 2, restarts) == (None, "L2 used 3 times since floor 6")
    ladder.progress("Event")
    ladder.floor(11, 15)
    assert ladder.stuck("MirrorMap", 2, restarts) == (2, None)
    assert restart(ladder, restarts) == (3, None)
    assert ladder.counts == {1: 6, 2: 4, 3: 5}  # runs.jsonl's l1/l2/l3 stay the run's totals


def test_ladder_a_target_15_run_that_restarts_twice_on_floor_3_and_once_on_floor_8_goes_on():
    # The PR's worked example: before #435 the third restart stopped the run, whatever the target.
    ladder, restarts = Ladder(), Restarts()
    ladder.floor(3, 15)
    assert [restart(ladder, restarts) for _ in range(2)] == [(3, None), (3, None)]
    ladder.floor(8, 15)  # floors 6 and 7 not seen (their page did not read): floor 8 starts the stretch all the same
    assert restart(ladder, restarts) == (3, None)


@pytest.mark.parametrize(("first_seen", "after"), [
    (13, [(None, "game restarted 2 times since floor 11")]),
    (7, [(None, "game restarted 2 times since floor 6")]),
    (6, [(3, None), (3, None), (None, "game restarted 2 times since floor 6")]),
    (11, [(3, None), (3, None), (None, "game restarted 2 times since floor 11")]),
])
def test_ladder_a_resumed_run_refills_at_its_first_floor_seen_only_when_that_floor_starts_a_stretch(first_seen, after):
    # A bot launched or a task started mid-run has a fresh Ladder (actions.TaskStart), and PickThemePack tells it the next
    # floor only: its restarts were on the floor before. Floor 12's or 6's are the stretch's of floor 13 or 7; floor 5's
    # or 10's are the last stretch's, and floor 6 or 11 refills as it would without the resume.
    ladder, restarts = Ladder(), Restarts()
    assert [restart(ladder, restarts) for _ in range(2)] == [(3, None), (3, None)]
    ladder.floor(first_seen, 15)
    assert [restart(ladder, restarts) for _ in after] == after


@pytest.mark.parametrize("floors", [range(1, 6), [5, 6, 11]])  # a target-5 run never sees floor 6; the rule needs the target
def test_ladder_a_target_5_run_keeps_one_allowance(floors):
    ladder, restarts = Ladder(), Restarts()
    for floor in floors:
        ladder.floor(floor, 5)
    assert [restart(ladder, restarts) for _ in range(3)] == [(3, None), (3, None), (None, "game restarted 2 times this run")]
    ladder.progress("Event")
    for _ in range(3):
        assert ladder.stuck("MirrorMap", 2, restarts) == (2, None)
        ladder.progress("Event")
    assert ladder.stuck("MirrorMap", 2, restarts) == (None, "L2 used 3 times this run")


def test_ladder_the_refill_leaves_the_failed_restarts_in_a_row():
    # L3_FAILED_IN_A_ROW is the launch's: a game that never comes back stops at its third failed restart, refill or not.
    ladder, restarts = Ladder(), Restarts()
    ladder.floor(5, 15)
    assert ladder.stuck("Loading", 3, restarts) == (3, None)
    assert ladder.stuck("Loading", 3, restarts) == (3, None)
    ladder.floor(6, 15)
    assert ladder.stuck("Loading", 3, restarts) == (3, None)
    assert ladder.stuck("Loading", 3, restarts) == (None, "game restarted 3 times in a row without getting past Loading")


def test_a_restart_that_needed_another_before_the_bot_got_past_counts_as_failed():
    ladder, restarts = Ladder(), Restarts()
    ladder.stuck("BattlePause", 1, restarts)
    ladder.stuck("BattlePause", 1, restarts)
    for kind in ("NavTitle", "Connecting", "NavMainTabs"):
        ladder.progress(kind)
        restarts.progress(kind)
    assert ladder.stuck("NavMainTabs", 1, restarts) == (3, None)
    for kind in (*WAY_BACK, "BattlePause"):
        ladder.progress(kind)
        restarts.progress(kind)
    assert restarts.in_a_row == 2
    restarts.progress("MirrorMap")
    assert restarts.in_a_row == 0


def line(team, minutes, result="clear", **extra):
    return {"start": "2026-10-16T00:00:00.000Z", "end": f"2026-10-16T{minutes // 60:02}:{minutes % 60:02}:00.000Z",
            "team": team, "result": result, **extra}


def test_run_limit_default_under_10_runs():
    assert run_limit([line("a", 30)] * 9, "a", 5) == 3600


def test_run_limit_twice_p95():
    lines = [line("a", m) for m in range(30, 50)] + [line("b", 300)]  # 30..49 min; b is another team
    assert run_limit(lines, "a", 5) == pytest.approx(2 * 48.05 * 60)


def test_run_limit_only_clears_after_the_latest_reset():
    old = [line("a", 200)] * 20
    new = [line("a", 40)] * 10 + [line("a", 5, "stop"), line("a", 5, "giveup"), {**line("a", 5), "start": None}]
    lines = old + [{"reset": "a", "time": "x"}] + [line("a", 300)] * 5 + [{"reset": "a", "time": "y"}] + new
    assert run_limit(lines, "a", 5) == pytest.approx(2 * 40 * 60)
    assert run_limit(lines + [{"reset": "a", "time": "z"}], "a", 5) == 3600
    assert run_limit(lines, "b", 5) == 3600


def test_floor_limit_45_min_unless_history_says_longer():
    # Live 2026-10-16 (#34): hard runs took 80 and 107 min, floors up to ~25 min, all of it progress.
    assert floor_limit([], "a", 5) == 45 * 60
    assert floor_limit([line("a", 40)] * 10, "a", 5) == 45 * 60  # a fast team keeps the floor's 45 min
    assert floor_limit([line("a", 150)] * 10, "a", 5) == pytest.approx(2 * 150 * 60 / 5)


def test_floor_limit_follows_the_runs_target_and_history_of_another_target_does_not_count():
    five, fifteen = [line("a", 150, target=5)] * 10, [line("a", 450, target=15)] * 10
    assert floor_limit(five + fifteen, "a", 5) == floor_limit(five, "a", 5) == pytest.approx(2 * 150 * 60 / 5)
    assert floor_limit(five + fifteen, "a", 15) == floor_limit(fifteen, "a", 15) == pytest.approx(2 * 450 * 60 / 15)
    assert run_limit(five, "a", 15) == 3600  # no 15-floor run yet


def test_a_line_without_target_counts_as_target_5():
    old = [line("a", 150)] * 10
    assert run_limit(old, "a", 5) == pytest.approx(2 * 150 * 60)
    assert run_limit(old, "a", 10) == 3600


def test_run_limit_skips_a_clear_that_stopped_short_of_its_target():
    short = [line("a", 20, target=15, target_reached=False)] * 10  # claimed past floor 5, short time
    full = [line("a", 100, target=15, target_reached=True)] * 5 + [line("a", 100, target=15)] * 5  # older lines have no key
    assert run_limit(short, "a", 15) == 3600
    assert run_limit(short + full, "a", 15) == pytest.approx(2 * 100 * 60)


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
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("NavTitle", 1, restarts) == (1, None)
    for kind in ("DownloadDialog", "PopupButton"):
        ladder.progress(kind)  # an acknowledged dialog on the title does not end the episode
    assert ladder.stuck("NavTitle", 1, restarts) == (3, None)  # climbs (a fresh episode is L1); the title skips L2


def test_keep_capture_saves_the_screen_and_keeps_only_the_latest(tmp_path):
    # #85/#87: a screen MirrorHub does not know is the capture the missing popup nodes need.
    from recovery import UNKNOWN_KEEP, keep_capture
    for i in range(UNKNOWN_KEEP + 2):
        keep_capture(tmp_path, "unknown", screen(i), f"2026-10-18T00-00-{i:02}.000Z", UNKNOWN_KEEP)
    saved = sorted(p.name for p in (tmp_path / "logs" / "unknown").iterdir())
    assert len(saved) == UNKNOWN_KEEP
    assert saved[0] == "2026-10-18T00-00-02.000Z.png"  # the two oldest went
    assert (tmp_path / "logs" / "unknown" / saved[-1]).read_bytes().startswith(b"\x89PNG")


def test_notices_at_login_do_not_end_a_stuck_spell():
    # spec 06: screens on the way back to a run (a login may open the notices) are not progress.
    assert "Notices" in TRANSIT


def test_the_daily_hubs_main_window_nodes_are_on_the_way_back_not_past_a_stuck_screen():
    main_window = {name for name, node in load_nodes().items() if "HomeReached" in node.get("all_of", [])}
    assert main_window and main_window <= TRANSIT, sorted(main_window - TRANSIT)


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
    ladder, restarts = Ladder(), Restarts()
    assert ladder.stuck("MirrorMap", 1, restarts) == (1, None)
    assert ladder.stuck("MirrorMap", 3, restarts) == (3, None)  # in an open episode too: L2 cannot help
    assert ladder.counts == {1: 1, 2: 0, 3: 1}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    """A fake Maa context for Recover and DailyRecover: a blank screen, every recovery level goes through and GoHome ends
    on the main window; a fresh ladder and task."""
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    monkeypatch.setattr(actions, "TASK", {"runs": 0, "done": None})  # the module's own back after the test
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    ctx.tasker.get_node_detail.return_value.name = "HomeReached"  # go_home() reads GoHome's last node (#514)
    actions.RUN.clear()
    actions.STUCK["flag"] = None
    actions.STUCK["watch"].reset()
    actions.STUCK["ladder"].__init__()
    actions.STUCK["restarts"].__init__()
    yield ctx
    actions.RUN.clear()
    actions.STUCK["flag"] = None
    actions.STUCK["ladder"].__init__()
    actions.STUCK["restarts"].__init__()


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


@pytest.fixture
def stops(monkeypatch):
    """The reasons actions.stop was called with; the stop procedure itself does not run."""
    reasons = []
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: reasons.append(reason) or False)
    return reasons


def test_ten_runs_with_a_restart_each_never_stop(hub, stops):
    # #520, for #34's 10 HARD runs in one launch.
    for _ in range(10):
        actions.STUCK["ladder"] = Ladder()
        for _ in range(2):
            actions.STUCK["flag"] = ("BattlePause", 1, "BattlePause: the screen did not change")
            actions.Recover().run(hub, None)
        for kind in (*WAY_BACK, "MirrorMap"):
            actions.StuckFlag.see(kind, screen(0))
    assert stops == []
    assert [c.args for c in hub.run_task.call_args_list] == [("RecoverL1",), ("RecoverL3",)] * 10
    assert actions.STUCK["restarts"].in_a_row == 0


def test_a_force_stop_that_fails_three_times_in_a_row_stops(hub, stops):
    hub.run_task.return_value.status.succeeded = False
    actions.STUCK["flag"] = ("MirrorMap", 3, "the game is frozen")
    assert actions.Recover().run(hub, None) is False
    assert [c.args for c in hub.run_task.call_args_list] == [("RecoverL3",)] * 3
    assert len(stops) == 1 and "3 times in a row" in stops[0], stops
    assert actions.STUCK["ladder"].counts[3] == 0


FROZEN = ("PassBanner", 3, "PassBanner: the main window took none of 2 taps, the same picture after each: the game is frozen")
PASS_STUCK = SimpleNamespace(node_name="PassStuck", custom_action_param=None)


def daily_restarts(ctx, times):
    """PassStuck's DailyRecover on a game frozen on the main window, times; after each, the hub gets past it to a pass page."""
    results = []
    for _ in range(times):
        actions.STUCK["flag"] = FROZEN
        results.append(actions.DailyRecover().run(ctx, PASS_STUCK))
        actions.StuckFlag.see("PassMissionsTab", screen(0))
    return results


def restarts_run(ctx):
    return [c.args for c in ctx.run_task.call_args_list].count(("RecoverL3",))


def test_a_daily_task_stops_at_its_third_restart_though_each_got_past(hub, stops):
    # #520: each restart got the bot past the main window, so the launch's streak never grows; the task's 2 end it.
    assert daily_restarts(hub, 3) == [True, True, False]
    assert restarts_run(hub) == 2
    assert len(stops) == 1 and "2 times this task" in stops[0], stops


def test_the_next_task_has_its_own_two_restarts(hub, stops):
    daily_restarts(hub, 2)
    assert actions.TaskStart().run(hub, SimpleNamespace(node_name="ClaimPassMissions")) is True
    assert daily_restarts(hub, 3) == [True, True, False]
    assert restarts_run(hub) == 4 and len(stops) == 1, stops


def test_a_restart_that_did_not_go_through_is_not_one_of_the_tasks_two(hub, stops):
    # The failed force-stop stays in the launch's streak only, as Ladder.failed uncharges the run: two more restarts run.
    hub.run_task.side_effect = lambda name: MagicMock(**{"status.succeeded": name != "RecoverL3"})
    actions.STUCK["flag"] = FROZEN
    assert actions.DailyRecover().run(hub, PASS_STUCK) is True
    hub.run_task.side_effect = None
    assert daily_restarts(hub, 3) == [True, True, False]
    assert restarts_run(hub) == 3
    assert len(stops) == 1 and "2 times this task" in stops[0], stops


def test_the_opening_go_homes_restart_is_one_of_the_tasks_two(hub, stops):
    # GoHome did not reach the main window: restart 1
    assert actions.HomeLost().run(hub, SimpleNamespace(custom_action_param=None)) is True
    actions.StuckFlag.see("PassBanner", screen(0))
    actions.StuckFlag.see("PassMissionsTab", screen(0))
    assert daily_restarts(hub, 2) == [True, False]
    assert restarts_run(hub) == 2
    assert len(stops) == 1 and "2 times this task" in stops[0], stops
