"""MirrorDungeon's start team (#805, ADR 0014): the client's MirrorStartTeam, the team this task starts from. Its case 0
「照隊伍佇列」 (queue) sends nothing; a team's case sends the team's id as start_team in the entry node's attach, the cases
coming from the team options file the settings GUI writes (tests/team_options.json, as for ExpTeam). The task's start
stops before any tap on a team deleted or disabled; its first new run picks its team with that team at the head of
team_queue and writes it there once the run opens, as a claim moves one to the end; a run under way at the task's
start plays the team of the queue as it was before the move.

Every task here is posted with the override tools/client_override.py builds from interface.json and that file, as MXU
does (client_options), on settings_cases' valid file: team a (any) then team b (hard_only), the list and the queue in
that order; the team options file has a case for each and for gone, a team since deleted.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import actions
import run_start_actions
import test_actions
from client_options import send
from team_queue import to_head
from test_resumed_run import claim
from test_task_chain import ENTRY_OPTIONS, entry_page

clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context

MIRROR_WHERE = "the options of the MirrorDungeon task in the client's task list"
INSTEAD = f"pick another team, or 「照隊伍佇列」 (follow the team queue), in {MIRROR_WHERE}"


def on_disk():
    return json.loads((actions.ROOT / "config" / "settings.json").read_text(encoding="utf-8"))


def queue():
    """The team queue on disk; no start team changes the list's order, a then b (#803)."""
    data = on_disk()
    assert [t["id"] for t in data["teams"]] == ["a", "b"]
    return data["team_queue"]


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
    entry_page(context, "MirrorDifficulty=hard", "MirrorStartTeam=b")
    assert queue() == ["a", "b"]  # nothing moves at the task's start: a run under way plays a
    actions.LOG.clear()
    run = plan_run(context)
    assert queue() == ["b", "a"]
    assert run["team"]["id"] == "b" and run["planned"]
    assert before_new_run("team queue: start team 'Team b' (MirrorStartTeam) to the head")
    assert [line for line in said() if line.startswith("new run: hard, team 'Team b' (TEAMS #2)")]


def test_a_start_team_already_at_the_head_is_logged_and_the_file_stays(context):
    entry_page(context, "MirrorDifficulty=hard", "MirrorStartTeam=a")
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"
    assert path.read_bytes() == before
    assert before_new_run("team queue: start team 'Team a' (MirrorStartTeam) is already at the head")


def start(context, monkeypatch, *options, settings=lambda data: None):
    """MirrorDungeon's TaskStart posted by a client with entry_page's options (its webhook) and these, on settings_cases'
    valid file (settings edits it): what it returned and the reasons the stop procedure posted to the webhook."""
    data = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    settings(data)
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    send(context, "MirrorDungeon", *ENTRY_OPTIONS, *options)
    ok = actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    return ok, [json.loads(c.args[0].data)["reason"] for c in urlopen.call_args_list]


@pytest.mark.parametrize("team, edit, error", [
    # a deleted team keeps its case in the team options file, which still sends its id (#780)
    ("gone", lambda data: None, f"MirrorStartTeam (start_team): team 'gone' was deleted in the settings GUI; {INSTEAD}"),
    ("b", lambda data: data["teams"][1].update(enabled=False),
     f"MirrorStartTeam (start_team): team 'Team b' (id 'b') is disabled; enable it in the settings GUI, or {INSTEAD}"),
])
def test_a_deleted_or_disabled_start_team_stops_the_task_before_any_tap(context, monkeypatch, team, edit, error):
    # the stop procedure (its evidence, the webhook), as a Luxcavation task's deleted team (#780)
    ok, posted = start(context, monkeypatch, f"MirrorStartTeam={team}", settings=edit)
    assert ok is False and posted == [f"Invalid task options:\n- {error}"]
    assert f"stop: Invalid task options:\n- {error}" in said()
    assert queue() == ["a", "b"] and "start_team" not in actions.TASK
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()


@pytest.mark.parametrize("options", [(), ("MirrorStartTeam=b",)])
def test_a_run_under_way_at_the_tasks_start_plays_the_team_of_the_queue_before_the_move(context, monkeypatch, options):
    # #436: an agent restarted mid-run, a paused run picked up, the last run's rewards: the run's team comes back from
    # the queue, a with or without a start team (b, had b moved at the start); the start team waits for the task's
    # first new run.
    ok, _ = start(context, monkeypatch, "MirrorDifficulty=hard", *options)
    assert ok is True
    actions.RUN.clear()  # no run plan in memory
    run = actions.current_run(context)
    assert (run["team"]["id"], run["planned"]) == ("a", True)
    claim(context, monkeypatch, "HARD")
    assert queue() == ["b", "a"]  # a, the run's team, to the end
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "b"
    assert start_lines() == (["team queue: start team 'Team b' (MirrorStartTeam) is already at the head"] if options else [])


def test_a_start_team_whose_usage_does_not_fit_the_run_is_passed_over_and_keeps_the_head(context, monkeypatch):
    entry_page(context, "MirrorDifficulty=normal", "MirrorStartTeam=b")  # b is hard_only
    actions.LOG.clear()
    run = plan_run(context)
    assert run["team"]["id"] == "a" and queue() == ["b", "a"]  # the next team of the queue that fits
    assert before_new_run("team queue: start team 'Team b' (MirrorStartTeam) to the head",
                          "start team 'Team b' (MirrorStartTeam) is hard_only: a normal run passes over it, and it "
                          "keeps its place in the team queue")
    claim(context, monkeypatch)
    assert queue() == ["b", "a"]  # only the team that played goes to the end, and a is last already


def test_a_task_that_opens_no_run_leaves_the_queue_alone(context):
    # spec #802: the move is the first new run's; a task with nothing left to do opens none
    entry_page(context, "MirrorDifficulty=hard", "MirrorStopWhenBonusOut=Yes", "MirrorStartTeam=b")  # none left
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    plan_run(context)
    assert actions.TASK["done"] == "weekly bonuses used up"
    assert path.read_bytes() == before and start_lines() == []


def test_a_back_out_to_read_the_modules_moves_nothing_until_the_run_opens(context):
    # #369: PlanRun goes back to the Drive page when this trip did not read the Modules, and comes back here
    entry_page(context, "MirrorDifficulty=hard", "MirrorStartTeam=b")
    del actions.TASK["modules"]
    assert run_start_actions.PlanRun().run(context, None) is True and "settings" not in actions.RUN
    assert queue() == ["a", "b"]
    assert plan_run(context)["team"]["id"] == "b" and queue() == ["b", "a"]


def test_the_start_team_moves_only_before_the_tasks_first_new_run(context, monkeypatch):
    entry_page(context, "MirrorDifficulty=hard", "MirrorStartTeam=b")
    assert plan_run(context)["team"]["id"] == "b"
    claim(context, monkeypatch, "HARD")
    assert queue() == ["a", "b"]
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "a"  # the queue's turn, not b again
    assert queue() == ["a", "b"] and start_lines() == []


@pytest.mark.parametrize("sent", [
    ("MirrorStartTeam=queue",),  # 「照隊伍佇列」, the default: nothing sent
    (),
])
def test_follow_the_queue_or_no_value_plays_the_queue_as_before(context, sent):
    entry_page(context, "MirrorDifficulty=hard", *sent, settings=lambda data: data.update(team_queue=["b", "a"]))
    assert "start_team" not in actions.TASK["options"]
    path = actions.ROOT / "config" / "settings.json"
    before = path.read_bytes()
    actions.LOG.clear()
    assert plan_run(context)["team"]["id"] == "b"
    assert path.read_bytes() == before and start_lines() == []


@pytest.mark.parametrize("value", [3, "", None, ["b"]])
def test_a_start_team_the_agent_cannot_read_is_follow_the_queue(context, value):
    # spec #802: only a hand-made attach sends one; the options line shows what came
    entry_page(context)
    send(context, "MirrorDungeon", *ENTRY_OPTIONS, "MirrorDifficulty=hard")
    nodes = {name: dict(context.get_node_data(name)["attach"]) for name in ("MirrorDungeon", "GlobalOptions")}
    nodes["MirrorDungeon"]["start_team"] = value
    context.get_node_data.side_effect = lambda name: {"attach": nodes[name]}
    actions.LOG.clear()
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    shown = value if isinstance(value, str) else json.dumps(value)
    assert [line for line in said() if line.startswith("options: ")][0].endswith(f", start_team={shown}")
    assert "start_team" not in actions.TASK["options"]
    actions.RUN.clear()
    assert plan_run(context)["team"]["id"] == "a" and queue() == ["a", "b"] and start_lines() == []


def settings_file(root, version, ids):
    """A settings file of ids' teams: at version 22 with its queue in the order ids, older (20, 21: the GUI has not
    written it back) with none, its queue the order of its teams. Returns what it holds."""
    path = root / "config" / "settings.json"
    path.parent.mkdir(exist_ok=True)
    data = {"version": version, "teams": [{"id": i, "name": f"隊 {i}", "enabled": True} for i in ids]}
    if version >= 22:
        data["team_queue"] = list(ids)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def file_now(root):
    return json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("version", [20, 21])
def test_a_file_the_gui_has_not_written_back_moves_the_start_team_in_its_list(tmp_path, version):
    # as a claim's move (spec 04 section 2): the file stays at its version, only the order of its teams changes, and
    # the migration to 22 makes team_queue of that order
    before = settings_file(tmp_path, version, ["a", "b", "c"])
    assert to_head(tmp_path, "c") == "team queue: start team '隊 c' (MirrorStartTeam) to the head"
    assert file_now(tmp_path) == {**before, "teams": [before["teams"][i] for i in (2, 0, 1)]}


def test_a_version_22_file_moves_only_its_queue(tmp_path):
    before = settings_file(tmp_path, 22, ["a", "b", "c"])
    to_head(tmp_path, "b")
    assert file_now(tmp_path) == {**before, "team_queue": ["b", "a", "c"]}


@pytest.mark.parametrize("text", [None, "{"])
def test_an_unusable_settings_file_is_logged_not_raised(tmp_path, text):
    if text is not None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(text, encoding="utf-8")
    line = to_head(tmp_path, "a")
    assert line.startswith("team queue not written (") and line.endswith("): start team 'a' (MirrorStartTeam) keeps its place")


def test_a_team_deleted_since_the_tasks_start_leaves_the_file_alone(tmp_path):
    settings_file(tmp_path, 22, ["a", "b"])
    path = tmp_path / "config" / "settings.json"
    before = path.read_bytes()
    assert to_head(tmp_path, "gone") == "team queue: start team 'gone' (MirrorStartTeam) is no longer listed, the queue stays"
    assert path.read_bytes() == before
