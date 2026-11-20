"""One still per floor of the theme pack page and the map from floor 6 on, and one of the settlement window, for a run
whose target is above 5 (#848): actions.keep_floor_still and the three actions that hand it their screen."""

import numpy as np
import pytest

import actions
import map_actions
import recovery
import run_start_actions
import settle_actions
import settlement
from agent_patch import patch_all
import test_actions

clock, context = test_actions.clock, test_actions.context  # its fixtures


@pytest.fixture
def stamps(monkeypatch):
    """settlement.now() moves on a second a call, as a run does."""
    times = iter(f"2026-11-20T03:{m:02}:{s:02}.000Z" for m in range(60) for s in range(60))
    monkeypatch.setattr(settlement, "now", lambda: next(times))


def target(monkeypatch, floors):
    monkeypatch.setitem(actions.TASK, "options", {"target_floor": floors})


def kept(root):
    folder = root / "logs" / "floors"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_each_floor_from_six_keeps_its_first_theme_pack_page_and_map(context, stamps, monkeypatch, tmp_path):
    # A page read again on its floor (fading in, after a refresh, MirrorHub's next look) is not kept again.
    target(monkeypatch, 15)
    image = np.zeros((4, 4, 3), np.uint8)
    for kind, floor in [("pack", 5), ("map", 5), ("pack", 6), ("pack", 6), ("map", 6), ("map", 6), ("pack", 7), ("map", 7),
                        ("map", 7), ("settlement", 7)]:
        actions.keep_floor_still(kind, floor, image)
    assert kept(tmp_path) == ["2026-11-20T03-00-00.000Z-floor06-pack.png", "2026-11-20T03-00-01.000Z-floor06-map.png",
                              "2026-11-20T03-00-02.000Z-floor07-pack.png", "2026-11-20T03-00-03.000Z-floor07-map.png",
                              "2026-11-20T03-00-04.000Z-floor07-settlement.png"]


def test_a_run_ended_before_floor_six_keeps_its_settlement_window(context, stamps, monkeypatch, tmp_path):
    # A 10-floor run wiped out on floor 3: its window is the one a probe run wants to see.
    target(monkeypatch, 10)
    actions.keep_floor_still("settlement", 3, np.zeros((4, 4, 3), np.uint8))
    assert kept(tmp_path) == ["2026-11-20T03-00-00.000Z-floor03-settlement.png"]


@pytest.mark.parametrize("options", [{"target_floor": 5}, {}])  # a 5-floor run; no options read: 5, as option() says
def test_a_five_floor_run_keeps_none(context, stamps, monkeypatch, tmp_path, options):
    monkeypatch.setitem(actions.TASK, "options", options)
    for kind in ("pack", "map", "settlement"):
        actions.keep_floor_still(kind, 6, np.zeros((4, 4, 3), np.uint8))
    assert kept(tmp_path) == []


def test_a_floor_not_known_keeps_none(context, stamps, monkeypatch, tmp_path):
    # The agent restarted mid-run: the map comes before any theme pack page told the floor.
    target(monkeypatch, 15)
    actions.keep_floor_still("map", None, np.zeros((4, 4, 3), np.uint8))
    assert kept(tmp_path) == []


def test_the_folder_keeps_only_the_newest(context, stamps, monkeypatch, tmp_path):
    # Named time first: the next run's floor 6 is newer than the last run's floor 15 and outlives it.
    target(monkeypatch, 15)
    image = np.zeros((4, 4, 3), np.uint8)
    for run in range(4):
        actions.RUN.clear()  # Settle clears the run; a new one starts its floors over
        for floor in range(6, 16):
            actions.keep_floor_still("pack", floor, image)
            actions.keep_floor_still("map", floor, image)
        actions.keep_floor_still("settlement", 15, image)
    names = kept(tmp_path)
    assert len(names) == recovery.FLOOR_KEEP == 63  # three 15-floor runs: 10 floors' two pages and a window each
    assert names[0] == "2026-11-20T03-00-21.000Z-floor06-pack.png"  # the first run's 21 are gone, the newest 63 stay
    assert names[-1] == "2026-11-20T03-01-23.000Z-floor15-settlement.png"


def test_a_full_disk_logs_and_the_run_goes_on(context, stamps, monkeypatch, tmp_path):
    target(monkeypatch, 15)
    lines = []
    patch_all(monkeypatch, "log", lines.append)

    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(recovery, "keep_capture", fail)
    actions.keep_floor_still("map", 6, np.zeros((4, 4, 3), np.uint8))
    actions.keep_floor_still("map", 6, np.zeros((4, 4, 3), np.uint8))
    assert lines == ["floor 6 map: screen not saved: disk full"]  # once a floor and page, as a saved one


def test_the_theme_pack_page_hands_its_screen_and_floor(context, stamps, monkeypatch, tmp_path):
    target(monkeypatch, 15)
    patch_all(monkeypatch, "text", lambda *a, **k: "Floor 6")
    monkeypatch.setattr(run_start_actions.PickThemePack, "set_difficulty", lambda *a: False)  # stops after the floor read
    actions.RUN.update(difficulty=None, floor=5)
    run_start_actions.PickThemePack().run(context, None)
    run_start_actions.PickThemePack().run(context, None)
    assert kept(tmp_path) == ["2026-11-20T03-00-01.000Z-floor06-pack.png"]  # the first stamp went to the memory line


def test_the_map_of_this_floor_hands_its_screen(context, stamps, monkeypatch, tmp_path):
    target(monkeypatch, 10)
    actions.RUN.update(floor=8)
    patch_all(monkeypatch, "still", lambda context, timeout=None: np.zeros((720, 1280, 3), np.uint8))
    monkeypatch.setattr(map_actions.RouteMap, "wait_for_floor", staticmethod(lambda context, image: True))
    monkeypatch.setattr(map_actions.RouteMap, "unzoom", staticmethod(lambda context: False))  # stops after the still
    map_actions.RouteMap().run(context, None)
    assert kept(tmp_path) == ["2026-11-20T03-00-00.000Z-floor08-map.png"]


def test_a_map_still_the_last_floors_is_not_kept_as_this_ones(context, stamps, monkeypatch, tmp_path):
    target(monkeypatch, 10)
    actions.RUN.update(floor=8)
    patch_all(monkeypatch, "still", lambda context, timeout=None: np.zeros((720, 1280, 3), np.uint8))
    monkeypatch.setattr(map_actions.RouteMap, "wait_for_floor", staticmethod(lambda context, image: False))
    map_actions.RouteMap().run(context, None)
    assert kept(tmp_path) == []


def test_the_settlement_window_hands_its_screen_and_floor(context, stamps, monkeypatch, tmp_path):
    target(monkeypatch, 10)
    actions.RUN.update(settings={}, team={"hard_from_floor": None}, difficulty="hard")
    monkeypatch.setattr(settlement, "read_result", lambda text: settlement.Result(10, "hard", 6, 6))
    monkeypatch.setattr(settlement, "claim_ok", lambda result: False)
    monkeypatch.setattr(settle_actions.Settle, "give_up", lambda self, context, run, result: True)
    settle_actions.Settle().run(context, None)
    settle_actions.Settle().run(context, None)  # read again under its dialog
    assert kept(tmp_path) == ["2026-11-20T03-00-00.000Z-floor10-settlement.png"]


def test_an_unknown_screen_logs_the_floor_it_was_on(context, stamps, monkeypatch, tmp_path):
    lines = []
    patch_all(monkeypatch, "log", lines.append)
    actions.RUN.update(floor=12)
    actions.keep_unknown(np.zeros((4, 4, 3), np.uint8))
    actions.RUN.pop("floor")
    actions.keep_unknown(np.zeros((4, 4, 3), np.uint8))
    assert lines == ["unknown screen kept in logs/unknown/2026-11-20T03-00-00.000Z.png (floor 12)",
                     "unknown screen kept in logs/unknown/2026-11-20T03-00-01.000Z.png (floor ?)"]
