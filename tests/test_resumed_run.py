"""A run under way with no run plan in memory (the agent restarted, or picked up a paused run): its team comes back from
the head of the team queue, so the claim moves that team to the end and runs.jsonl names the team (#436, #501)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import actions
import map_actions
import settle_actions
import settlement
import run_start_actions
import battle_actions
import test_actions
from test_actions import argv, page
from agent_patch import patch_all
from settings import NO_TEAM
from test_task_chain import ENTRY_RUN

clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context


@pytest.fixture
def resumed(context, monkeypatch):
    """settings_cases' valid file under the agent's ROOT: auto difficulty, the queue team a (any) then team b
    (hard_only); the adb address "default"; MirrorDungeon started on it (start), no run plan in memory."""
    data = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    data["run"].update(ENTRY_RUN)
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    context.tasker.controller.info = {}  # address "default"
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # the task started here ends with the test
    start(context)
    actions.RUN.clear()
    return context


def start(context):
    """MirrorDungeon's TaskStart, as a task started after the agent's restart, on the settings file as it is now (its run
    entry_page's, ENTRY_RUN)."""
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))


def on_disk():
    return json.loads((actions.ROOT / "config" / "settings.json").read_text(encoding="utf-8"))


def queue():
    """The team queue on disk; the list's order stays a, b throughout (#803)."""
    data = on_disk()
    assert [t["id"] for t in data["teams"]] == ["a", "b"]
    return data["team_queue"]


def last_line():
    return json.loads((actions.ROOT / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def edit_settings(change):
    """change(data) edits the settings file under the agent's ROOT in place."""
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def claim(context, monkeypatch, difficulty="NORMAL"):
    """Exploration Reward of a cleared run, no weekly bonus left: Settle claims."""
    page(context, {tuple(settle_actions.RESULT): [(f"Floor 5 [{difficulty}] 6/6", (300, 420, 90, 20))]})
    patch_all(monkeypatch, "toggles", lambda context, image: [False, False, False])
    assert settle_actions.Settle().run(context, argv())


def b_first(data):
    data["team_queue"] = ["b", "a"]  # the list stays a, b (#803)


def test_a_claim_with_no_run_plan_moves_the_queue_head_to_the_end_and_names_the_team(resumed, monkeypatch):
    claim(resumed, monkeypatch)
    assert queue() == ["b", "a"]  # team a, the queue head, finished; b is next
    line = last_line()
    assert (line["team"], line["team_name"], line["result"]) == ("a", "Team a", "clear")
    assert line["start"] is None  # unknown: the run began before this agent did


def test_a_queue_that_picks_another_team_on_the_other_difficulty_names_no_team(resumed, monkeypatch):
    # Auto: hard picks b (hard_only), normal skips it for a. Which one the run began on is not known.
    edit_settings(b_first)
    claim(resumed, monkeypatch)
    assert queue() == ["b", "a"]
    assert last_line()["team"] is None


def test_auto_with_a_target_above_floor_5_begins_hard_so_the_queues_hard_team_is_known(resumed, monkeypatch):
    # #385: auto plays a target above 5 hard (run_start.run_difficulty), so only b (hard_only) can have begun the run.
    def target_10(data):
        data["run"]["target_floor"] = 10
        data["teams"][1]["hard_from_floor"] = 1  # a target above 5 needs the whole run HARD
        b_first(data)
    edit_settings(target_10)
    start(resumed)  # a target is the task's option: read at its start
    claim(resumed, monkeypatch, "HARD")
    assert queue() == ["a", "b"] and last_line()["team"] == "b"


def test_the_team_the_bot_picks_on_the_team_page_is_known(resumed, monkeypatch):
    # A run paused before its team page: the bot picks the slot itself, here b's TEAMS #2, so the run is b's.
    edit_settings(b_first)
    page(resumed, {tuple(run_start_actions.TEAM_TITLE): "TEAMS #2"})
    assert run_start_actions.SelectTeam().run(resumed, argv())
    claim(resumed, monkeypatch)
    assert queue() == ["a", "b"] and last_line()["team"] == "b"


def test_a_claim_with_no_run_plan_moves_the_first_place_of_a_team_the_queue_holds_twice(resumed, monkeypatch):
    # #954: the run is the queue's first place, as the pick took it
    edit_settings(lambda data: data.update(team_queue=["a", "b", "a"]))
    claim(resumed, monkeypatch)
    assert queue() == ["b", "a", "a"] and last_line()["team"] == "a"


def empty_queue(data):
    data["team_queue"] = []


def test_a_run_under_way_with_an_empty_queue_goes_through_the_stop_procedure(resumed, monkeypatch):
    # #954: no team to play it with, as with no enabled team before: current_run refuses it (need_team), and the action
    # that asked ends through the stop procedure (hands_back), with no runs.jsonl line and nothing raised.
    edit_settings(empty_queue)
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    page(resumed, {tuple(settle_actions.RESULT): [("Floor 5 [NORMAL] 6/6", (300, 420, 90, 20))]})
    assert settle_actions.Settle().run(resumed, argv()) is False
    reason = f"Invalid settings:\n- {NO_TEAM}"
    assert [line.split(" ", 1)[1] for line in actions.LOG if "stop: " in line] == [f"stop: {reason}"]
    assert [json.loads(c.args[0].data)["reason"] for c in urlopen.call_args_list] == [reason]
    assert not (actions.ROOT / "logs" / "runs.jsonl").exists()
    assert queue() == []
    resumed.tasker.controller.post_click.assert_not_called()


def test_a_queue_emptied_during_a_planned_run_claims_it_and_stays_empty(resumed, monkeypatch):
    # #954: the run plan in memory names the team; the claim has no place to move
    actions.current_run(resumed)
    edit_settings(empty_queue)
    claim(resumed, monkeypatch)
    assert queue() == [] and last_line()["team"] == "a"
    assert "team queue: 'a' is no longer in it, the queue stays" in [line.split(" ", 1)[1] for line in actions.LOG]


def stopped_at_once(context, monkeypatch, entry):
    """Stuck at once after the launch: TaskStart of entry, then the stop procedure."""
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(context, SimpleNamespace(node_name=entry))
    assert actions.stop(context, "recovery used up") is False


def test_a_resumed_run_stopped_on_the_floor_3_map_writes_the_2_floors_it_passed(resumed, monkeypatch):
    # #552: no theme pack page told this agent the floor; the map's title does. floors is the floors passed (the
    # user's decision of 2026-11-25), as for a run the bot began: the title's number less one.
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 3"})
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    line = last_line()
    assert (line["start"], line["floors"], line["target_reached"]) == (None, 2, False)


def test_a_resumed_run_stopped_on_the_floor_1_map_passed_no_floor(resumed, monkeypatch):
    # A real 0, not the null of a floor that did not read.
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 1"})
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    line = last_line()
    assert (line["floors"], line["target_reached"]) == (0, False)


def test_a_resumed_run_stopped_where_no_floor_reads_writes_null(resumed, monkeypatch):
    # #552: not 0, which reads as a run that passed no floor; target_reached is not known either.
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    line = last_line()
    assert (line["result"], line["floors"], line["target_reached"]) == ("stop", None, None)


def test_a_resumed_run_on_the_target_floors_map_has_not_reached_its_target(resumed, monkeypatch):
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 5"})  # target_floor 5: four floors passed
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert (last_line()["floors"], last_line()["target_reached"]) == (4, False)


def test_a_resumed_run_stopped_off_the_map_writes_the_floors_before_the_last_map_it_saw(resumed):
    # RouteMap's title read on floor 3's map; the stop comes in the battle entered from it, where no title shows.
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 3"})
    image = actions.screen(resumed)
    assert map_actions.RouteMap.wait_for_floor(resumed, image)
    page(resumed, {})
    assert actions.stop(resumed, "retries used up") is False
    assert last_line()["floors"] == 2


def test_a_paused_run_stopped_on_the_entry_page_writes_the_floors_before_the_one_it_shows(resumed):
    # Parallel Superposition Mode stays on the wrong side: the Exploring field reads the paused run's floor.
    page(resumed, {tuple(run_start_actions.EXPLORING): "Mirror of Sisyphe - F7"})
    run_start_actions.ParallelSwitch().analyze(
        resumed, SimpleNamespace(image=actions.screen(resumed), custom_recognition_param=json.dumps({"on": False})))
    actions.stop(resumed, "Parallel Superposition Mode stays ON")
    assert last_line()["floors"] == 6


def test_a_resumed_run_stopped_on_the_reward_window_writes_the_floors_it_shows_passed(resumed, monkeypatch):
    # The window reads Floor 5 6/6, a fact the map's title on that floor does not hold: five floors, the target reached.
    actions.RUN["shown_floor"] = 5  # a map's title of floor 5 would give 4
    page(resumed, {tuple(settle_actions.RESULT): [("Floor 5 [NORMAL] 6/6", (300, 420, 90, 20))]})
    monkeypatch.setattr(settlement, "claim_bonuses", lambda *args: 1)
    patch_all(monkeypatch, "toggles", lambda context, image: [False, False, False])  # a tap on one does nothing
    assert settle_actions.Settle().run(resumed, argv()) is False
    assert (last_line()["result"], last_line()["floors"], last_line()["target_reached"]) == ("stop", 5, True)


def test_a_resumed_run_whose_screen_cannot_be_read_still_writes_its_stop_line(resumed, monkeypatch):
    # An emulator gone at the stop: the screenshot fails (maa's RuntimeError), for the evidence after the line as well.
    def gone():
        raise RuntimeError("Failed to get cached image.")
    resumed.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = gone
    with pytest.raises(RuntimeError):
        stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert last_line()["floors"] is None


def test_a_run_the_bot_began_and_stopped_before_its_first_theme_pack_passed_no_floor(resumed):
    # A planned grace is unaffordable, say: no floor was played, so the 0 is real and a title is not read for it.
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 3"})
    actions.current_run(resumed)
    actions.RUN["start"] = "2026-11-25T00:00:00.000Z"
    actions.stop(resumed, "a planned grace is unaffordable")
    assert (last_line()["floors"], last_line()["target_reached"]) == (0, False)


def test_a_resumed_run_that_saw_a_theme_pack_page_writes_the_floors_before_it(resumed):
    page(resumed, {tuple(actions.MAP_TITLE): "Exploring Floor 3"})
    actions.current_run(resumed)
    actions.RUN["floor"] = 3  # PickThemePack's read
    actions.stop(resumed, "recovery used up")
    assert last_line()["floors"] == 2


def test_a_mirror_dungeon_stopped_before_it_touched_the_run_writes_its_stop_line(resumed, monkeypatch):
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert (last_line()["team"], last_line()["result"]) == ("a", "stop")
    assert queue() == ["a", "b"]  # a stop claims nothing: the team keeps its place


def test_a_stop_line_is_written_when_no_team_fits_the_set_difficulty(resumed, monkeypatch):
    # NORMAL set, every team hard_only: no new run would start, but the stop procedure still writes its line.
    def normal_set_hard_only_teams(data):
        data["run"]["difficulty"] = "normal"
        for team in data["teams"]:
            team["usage"] = "hard_only"
    edit_settings(normal_set_hard_only_teams)
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert (last_line()["team"], last_line()["result"]) == (None, "stop")


@pytest.mark.parametrize("action", [run_start_actions.SelectTeam, run_start_actions.ConfirmStarlight, battle_actions.Wipe])
def test_a_restart_mid_run_on_a_broken_settings_file_stops_and_says_why(resumed, monkeypatch, action):
    # #668: the first page action after the restart makes the run plan up from the file, which no longer loads.
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(resumed, SimpleNamespace(node_name="MirrorDungeon"))
    (actions.ROOT / "config" / "settings.json").write_text("{", encoding="utf-8")
    actions.LOG.clear()
    assert action().run(resumed, argv()) is False
    said = [line.split(" ", 1)[1] for line in actions.LOG]
    assert said[0].startswith("stop: Invalid settings:\n- ") and "is not readable JSON" in said[0]
    assert actions.TASK["ended"]


def test_a_daily_task_stopped_with_no_run_plan_writes_no_mirror_line(resumed, monkeypatch):
    stopped_at_once(resumed, monkeypatch, "ExpLuxcavation")
    assert not (actions.ROOT / "logs" / "runs.jsonl").exists()


def test_a_stop_after_the_tasks_claim_writes_no_line_for_a_run_not_begun(resumed, monkeypatch):
    # The claim ended the run; the task stops on its way to the next one (Parallel Superposition stays ON, say).
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(resumed, SimpleNamespace(node_name="MirrorDungeon"))
    claim(resumed, monkeypatch)
    actions.stop(resumed, "Parallel Superposition Mode stays ON after tapping INFINITY MIRROR")
    assert last_line()["result"] == "clear"
