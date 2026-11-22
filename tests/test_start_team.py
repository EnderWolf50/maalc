"""MirrorDungeon's start team (#805, ADR 0014): run.start_team of the settings file (#813), the team this task starts
from; null, no flag in the team queue (#878), the default. Its first new run picks its team with that team at the head of team_queue and writes it there once the run
opens, as a claim moves one to the end; a run under way at the task's start plays the team of the queue as it was before
the move. A flag on a team disabled or deleted has no effect (#878): the task follows the queue as with no flag, logs
that it ignored the flag, and the flag stays in the file.

Every task here starts on settings_cases' valid file: team a (any) then team b (hard_only), the list and the queue in
that order; gone is a team since deleted.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import actions
import run_start_actions
import test_actions
from agent_patch import patch_all
from team_queue import to_head
# queue(): the team queue of the agent's settings file (actions.ROOT); no move changes the list's order, a then b
from test_resumed_run import claim, queue
from test_task_chain import entry_page, entry_settings
from test_team_queue import old_settings_file, settings_file
from test_team_queue import on_disk as file_at  # file_at(root): the settings file under root as it is now

clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context

IGNORED = "the flag is ignored and the task follows the team queue"


def said():
    return [line.split(" ", 1)[1] for line in actions.LOG]


def start_lines():
    return [line for line in said() if "start team" in line]


def before_new_run(*lines):
    """Whether the log has these lines in a row, the last before the new run's line."""
    log = said()
    i = next(i for i, line in enumerate(log) if line.startswith("new run: ") and " team " in line)
    return log[i - len(lines):i] == list(lines)


def plan_run(context):
    """PlanRun on the entry page, the Modules read on the way in: the run it plans."""
    actions.TASK.update(modules=20)
    assert run_start_actions.PlanRun().run(context, None) is True
    return actions.RUN


def test_the_first_new_run_moves_the_start_team_to_the_head_of_the_queue_and_plays_it(context):
    entry_page(context, difficulty="hard", start_team="b")
    assert queue() == ["a", "b"]  # nothing moves at the task's start: a run under way plays a
    actions.LOG.clear()
    run = plan_run(context)
    assert queue() == ["b", "a"]
    assert run["team"]["id"] == "b" and run["planned"]
    assert before_new_run("team queue: start team 'Team b' (run.start_team) to the head")
    assert [line for line in said() if line.startswith("new run: hard, team 'Team b' (TEAMS #2)")]


def test_a_start_team_already_at_the_head_is_logged_and_the_file_stays(context):
    entry_page(context, difficulty="hard", start_team="a")
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"
    assert path.read_bytes() == before
    assert before_new_run("team queue: start team 'Team a' (run.start_team) is already at the head")


def start(context, monkeypatch, settings=lambda data: None, **run):
    """MirrorDungeon's TaskStart on entry_settings (entry_page's run, its webhook, and these keys; settings edits the
    file): what it returned and the reasons the stop procedure posted to the webhook."""
    entry_settings(settings=settings, **run)
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    ok = actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    return ok, [json.loads(c.args[0].data)["reason"] for c in urlopen.call_args_list]


@pytest.mark.parametrize("team, edit, line", [
    # the settings GUI deleted the team since its flag was set
    ("gone", lambda data: None, f"run/start_team: team 'gone' is no longer listed, {IGNORED}"),
    ("b", lambda data: data["teams"][1].update(enabled=False), f"run/start_team: team 'Team b' (id 'b') is disabled, {IGNORED}"),
])
def test_a_flag_on_a_deleted_or_disabled_team_is_ignored_and_logged_and_the_task_follows_the_queue(context, monkeypatch, team,
                                                                                                   edit, line):
    ok, posted = start(context, monkeypatch, settings=edit, difficulty="hard", start_team=team)
    assert ok is True and posted == []  # no stop procedure, no webhook
    assert said().count(line) == 1 and "start_team" not in actions.TASK
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"  # the queue's first enabled team, as with no flag
    assert path.read_bytes() == before and start_lines() == [] and line not in said()  # no move to the head, logged once
    assert json.loads(before)["run"]["start_team"] == team  # the flag stays, for the team enabled again


def test_a_flag_on_a_team_enabled_again_works_again(context, monkeypatch):
    start(context, monkeypatch, settings=lambda data: data["teams"][1].update(enabled=False), difficulty="hard",
          start_team="b")
    assert "start_team" not in actions.TASK
    entry_page(context, difficulty="hard", start_team="b")  # the next task, b enabled again
    assert plan_run(context)["team"]["id"] == "b" and queue() == ["b", "a"]


def test_a_start_team_disabled_by_a_save_since_the_tasks_start_is_ignored_at_its_first_new_run(context):
    entry_page(context, difficulty="hard", start_team="b")
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["teams"][1]["enabled"] = False  # the settings GUI saved while the task ran
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"
    assert path.read_bytes() == before and "start_team" not in actions.TASK
    assert f"run/start_team: team 'Team b' (id 'b') is disabled, {IGNORED}" in said() and start_lines() == []


@pytest.mark.parametrize("team", [None, "b"])
def test_a_run_under_way_at_the_tasks_start_plays_the_team_of_the_queue_before_the_move(context, monkeypatch, team):
    # #436: an agent restarted mid-run, a paused run picked up, the last run's rewards: the run's team comes back from
    # the queue, a with or without a start team (b, had b moved at the start); the start team waits for the task's
    # first new run.
    ok, _ = start(context, monkeypatch, difficulty="hard", start_team=team)
    assert ok is True
    actions.RUN.clear()  # no run plan in memory
    run = actions.current_run(context)
    assert (run["team"]["id"], run["planned"]) == ("a", True)
    claim(context, monkeypatch, "HARD")
    assert queue() == ["b", "a"]  # a, the run's team, to the end
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "b"
    assert start_lines() == (["team queue: start team 'Team b' (run.start_team) is already at the head"] if team else [])


def test_a_start_team_whose_usage_does_not_fit_the_run_is_passed_over_and_keeps_the_head(context, monkeypatch):
    entry_page(context, difficulty="normal", start_team="b")  # b is hard_only
    actions.LOG.clear()
    run = plan_run(context)
    assert run["team"]["id"] == "a" and queue() == ["b", "a"]  # the next team of the queue that fits
    assert before_new_run("team queue: start team 'Team b' (run.start_team) to the head",
                          "start team 'Team b' (run.start_team) is hard_only: a normal run passes over it, and it "
                          "keeps its place in the team queue")
    claim(context, monkeypatch)
    assert queue() == ["b", "a"]  # only the team that played goes to the end, and a is last already


def test_a_task_that_opens_no_run_leaves_the_queue_alone(context):
    # spec #802: the move is the first new run's; a task with nothing left to do opens none
    entry_page(context, difficulty="hard", stop_when_weekly_bonus_out=True, start_team="b")  # none left
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    plan_run(context)
    assert actions.TASK["done"] == "weekly bonuses used up"
    assert path.read_bytes() == before and start_lines() == []


def test_a_back_out_to_read_the_modules_moves_nothing_until_the_run_opens(context):
    # #369: PlanRun goes back to the Drive page when this trip did not read the Modules, and comes back here
    entry_page(context, difficulty="hard", start_team="b")
    del actions.TASK["modules"]
    assert run_start_actions.PlanRun().run(context, None) is True and "settings" not in actions.RUN
    assert queue() == ["a", "b"]
    assert plan_run(context)["team"]["id"] == "b" and queue() == ["b", "a"]


def test_the_start_team_moves_only_before_the_tasks_first_new_run(context, monkeypatch):
    entry_page(context, difficulty="hard", start_team="b")
    assert plan_run(context)["team"]["id"] == "b"
    claim(context, monkeypatch, "HARD")
    assert queue() == ["a", "b"]
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"  # the queue's turn, not b again
    assert queue() == ["a", "b"] and start_lines() == []


def test_follow_the_queue_plays_the_queue_as_before(context):
    # null, no flag, the default
    entry_page(context, difficulty="hard", settings=lambda data: data.update(team_queue=["b", "a"]))
    assert actions.TASK["options"]["start_team"] is None and "start_team" not in actions.TASK
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "b"
    assert path.read_bytes() == before and start_lines() == []


@pytest.mark.parametrize("value", [3, "", ["b"]])
def test_a_start_team_the_schema_refuses_fails_the_task_as_any_bad_settings(context, monkeypatch, value):
    # a file edited by hand: TaskStart reads no options, and PlanRun fails the task on the settings, naming the key;
    # the queue stays
    ok, posted = start(context, monkeypatch, start_team=value)
    assert ok is True and posted == [] and "options" not in actions.TASK
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    actions.TASK.update(modules=20)
    assert run_start_actions.PlanRun().run(context, None) is False
    assert logged[0].startswith("stop: Invalid settings:\n- run/start_team: ") and queue() == ["a", "b"]
    context.tasker.controller.post_click.assert_not_called()


@pytest.mark.parametrize("version", [20, 21])
def test_a_file_the_gui_has_not_written_back_moves_the_start_team_in_its_list(tmp_path, version):
    # as a claim's move (spec 04 section 2): the file stays at its version, only the order of its teams changes, and
    # the migration to 22 makes team_queue of that order
    old_settings_file(tmp_path, version, ["a", "b", "c"])
    before = file_at(tmp_path)
    assert to_head(tmp_path, "c") == "team queue: start team '隊 c' (run.start_team) to the head"
    assert file_at(tmp_path) == {**before, "teams": [before["teams"][i] for i in (2, 0, 1)]}


def test_a_version_22_file_moves_only_its_queue(tmp_path):
    settings_file(tmp_path, ["a", "b", "c"])
    before = file_at(tmp_path)
    to_head(tmp_path, "b")
    assert file_at(tmp_path) == {**before, "team_queue": ["b", "a", "c"]}


@pytest.mark.parametrize("text", [None, "{"])
def test_an_unusable_settings_file_is_logged_not_raised(tmp_path, text):
    if text is not None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(text, encoding="utf-8")
    line = to_head(tmp_path, "a")
    assert line.startswith("team queue not written (") and line.endswith("): start team 'a' (run.start_team) keeps its place")


def test_a_team_deleted_since_the_tasks_start_leaves_the_file_alone(tmp_path):
    path = settings_file(tmp_path, ["a", "b"])
    before = path.read_bytes()
    assert to_head(tmp_path, "gone") == "team queue: start team 'gone' (run.start_team) is no longer listed, the queue stays"
    assert path.read_bytes() == before
