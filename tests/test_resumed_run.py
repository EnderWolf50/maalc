"""A run under way with no run plan in memory (the agent restarted, or picked up a paused run): its team comes back from
the rotation cursor, so the claim moves the cursor on and runs.jsonl names the team (#436)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import actions
import test_actions
from test_actions import argv, page

clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context


@pytest.fixture
def resumed(context, monkeypatch):
    """settings_cases' valid file under the agent's ROOT: auto difficulty, team a (any) then team b (hard_only); the
    rotation cursor's address "default", no state file yet; no run plan in memory."""
    data = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    context.tasker.controller.info = {}  # address "default"
    actions.RUN.clear()
    return context


def cursor():
    return actions.read_cursor(actions.ROOT, "default")


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
    page(context, {tuple(actions.RESULT): [(f"Floor 5 [{difficulty}] 6/6", (300, 420, 90, 20))]})
    monkeypatch.setattr(actions, "toggles", lambda context, image: [False, False, False])
    assert actions.Settle().run(context, argv())


def test_a_claim_with_no_run_plan_moves_the_cursor_on_and_names_the_team(resumed, monkeypatch):
    claim(resumed, monkeypatch)
    assert cursor() == "b"  # team a, the cursor's (no state file: the first team), finished; b is next
    line = last_line()
    assert (line["team"], line["team_name"], line["result"]) == ("a", "Team a", "clear")
    assert line["start"] is None  # unknown: the run began before this agent did


def test_a_cursor_that_picks_another_team_on_the_other_difficulty_names_no_team(resumed, monkeypatch):
    # Auto: hard picks b (hard_only), normal skips it for a. Which one the run began on is not known.
    actions.write_cursor(actions.ROOT, "default", "b")
    claim(resumed, monkeypatch)
    assert cursor() == "b"
    assert last_line()["team"] is None


def test_auto_with_a_target_above_floor_5_begins_hard_so_the_cursors_hard_team_is_known(resumed, monkeypatch):
    # #385: auto plays a target above 5 hard (run_start.run_difficulty), so only b (hard_only) can have begun the run.
    def target_10(data):
        data["run"]["target_floor"] = 10
        data["teams"][1]["hard_from_floor"] = 1  # a target above 5 needs the whole run HARD
    edit_settings(target_10)
    actions.write_cursor(actions.ROOT, "default", "b")
    claim(resumed, monkeypatch, "HARD")
    assert cursor() == "a" and last_line()["team"] == "b"


def test_the_team_the_bot_picks_on_the_team_page_is_known(resumed, monkeypatch):
    # A run paused before its team page: the bot picks the slot itself, here b's TEAMS #2, so the run is b's.
    actions.write_cursor(actions.ROOT, "default", "b")
    page(resumed, {tuple(actions.TEAM_TITLE): "TEAMS #2"})
    assert actions.SelectTeam().run(resumed, argv())
    claim(resumed, monkeypatch)
    assert cursor() == "a" and last_line()["team"] == "b"


def stopped_at_once(context, monkeypatch, entry):
    """Stuck at once after the launch: TaskStart of entry, then the stop procedure."""
    monkeypatch.setattr(actions, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(context, SimpleNamespace(node_name=entry))
    assert actions.stop(context, "recovery used up") is False


def test_a_mirror_dungeon_stopped_before_it_touched_the_run_writes_its_stop_line(resumed, monkeypatch):
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert (last_line()["team"], last_line()["result"]) == ("a", "stop")


def test_a_stop_line_is_written_when_no_team_fits_the_set_difficulty(resumed, monkeypatch):
    # NORMAL set, every team hard_only: no new run would start, but the stop procedure still writes its line.
    def normal_set_hard_only_teams(data):
        data["run"]["difficulty"] = "normal"
        for team in data["teams"]:
            team["usage"] = "hard_only"
    edit_settings(normal_set_hard_only_teams)
    stopped_at_once(resumed, monkeypatch, "MirrorDungeon")
    assert (last_line()["team"], last_line()["result"]) == (None, "stop")


def test_a_daily_task_stopped_with_no_run_plan_writes_no_mirror_line(resumed, monkeypatch):
    stopped_at_once(resumed, monkeypatch, "ExpLuxcavation")
    assert not (actions.ROOT / "logs" / "runs.jsonl").exists()


def test_a_stop_after_the_tasks_claim_writes_no_line_for_a_run_not_begun(resumed, monkeypatch):
    # The claim ended the run; the task stops on its way to the next one (Parallel Superposition stays ON, say).
    monkeypatch.setattr(actions, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(resumed, SimpleNamespace(node_name="MirrorDungeon"))
    claim(resumed, monkeypatch)
    actions.stop(resumed, "Parallel Superposition Mode stays ON after tapping INFINITY MIRROR")
    assert last_line()["result"] == "clear"
