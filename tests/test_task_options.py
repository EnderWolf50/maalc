"""A task's options (#777, agent/task_options.py): its entry action (TaskStart, LuxStart, ChargeStart) reads them once,
before any tap, and every reader takes them from there; the two rules that cross them with the teams stop the task at
its start, in the words the settings' load gave them.

In process on test_actions' fake Maa context, then the real tasks on MaaFramework in a child process (daily_child.py):
this file run as a script, as test_task_chain.py does.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from daily_child import bind, game_class, load, result, run_child, run_task, screen
from test_settings import VALID, apply_edits

CASES = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))
LUX_KEYS = {"ExpLuxcavation": "exp", "ThreadLuxcavation": "thread"}

if __name__ != "__main__":  # pytest; the child imports the agent itself, under a stand-in AgentServer (daily_child.load)
    import actions
    import daily_actions
    import lux_actions
    import run_start_actions
    import test_actions
    from agent_patch import patch_all
    from settings import NO_TEAM
    from test_task_chain import entry_page

    clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context


def write(data):
    """data as settings.json under the agent's ROOT."""
    (actions.ROOT / "config").mkdir(exist_ok=True)
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def start(context, monkeypatch, task):
    """task's entry action on the settings file under ROOT, as at launch (no task before it): what it returned, the
    stop procedure's reasons (the procedure itself left out), and the log."""
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # TaskStart starts afresh: TASK and STUCK come back after
    patch_all(monkeypatch, "STUCK", dict(actions.STUCK))
    stops = []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    actions.LOG.clear()
    if task in LUX_KEYS:
        ok = lux_actions.LuxStart().run(context, SimpleNamespace(node_name=task, custom_action_param=json.dumps(LUX_KEYS[task])))
    elif task == "ChargeEnkephalin":
        ok = daily_actions.ChargeStart().run(context, SimpleNamespace(node_name=task, custom_action_param=None))
    else:
        ok = actions.TaskStart().run(context, SimpleNamespace(node_name=task))
    return ok, stops, [line.split(" ", 1)[1] for line in actions.LOG]


def invalid(errors):
    """The words of a SettingsError of errors."""
    return "Invalid settings:\n- " + "\n- ".join(errors)


@pytest.mark.parametrize("case", CASES["task_start"], ids=lambda c: c["name"])
def test_a_rule_that_crosses_a_tasks_options_with_the_teams_stops_it_at_its_start(context, monkeypatch, case):
    # #777: the target floor's rule (#385) and a Luxcavation task's team (#366) moved from the settings' load to the
    # task's start, the same words; the GUI's save check refuses the same files (gui/src/validate.test.ts).
    write(apply_edits(CASES["valid"], case["edits"]))
    ok, stops, said = start(context, monkeypatch, case["task"])
    if not case["cross"]:
        assert ok is True and stops == [] and not [line for line in said if line.startswith("stop:")]
    elif case["task"] == "MirrorDungeon":  # a failure, as PlanRun's on bad settings: no stop procedure
        assert ok is False and stops == [] and said[-1] == f"stop: {invalid(case['cross'])}"
    else:  # a Luxcavation task: the stop procedure, as for any settings it cannot run on
        assert ok is False and stops == [invalid(case["cross"])]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()  # not even GoHome


@pytest.mark.parametrize("target", [10, 15])
def test_a_disabled_team_does_not_hide_a_normal_only_team_behind_it_from_a_target_past_floor_5(context, monkeypatch, target):
    # #640 (once in settings.py): the check passed over a disabled team with `break`, so teams after it went unchecked.
    data = copy.deepcopy(VALID)
    data["run"]["target_floor"] = target
    data["teams"][0]["enabled"] = False
    data["teams"][1]["usage"] = "normal_only"
    write(data)
    ok, _, said = start(context, monkeypatch, "MirrorDungeon")
    got = said[-1].removeprefix("stop: Invalid settings:\n- ").split("\n- ")
    assert ok is False and [e for e in got if "teams/1/usage" in e and "normal_only" in e], got
    assert not [e for e in got if "teams/0/" in e]  # the disabled team itself is not asked


def test_a_rule_a_task_does_not_play_by_leaves_it_alone(context, monkeypatch):
    # Each task checks its own: a gone EXP team and a target its teams cannot play stop neither the mail nor the
    # Thread task, as the settings' load stopped them all before #777.
    write(apply_edits(CASES["valid"], [{"set": "luxcavation/exp/team", "value": "gone"}, {"set": "run/target_floor", "value": 15},
                                       {"set": "luxcavation/thread/team", "value": "a"}]))
    assert start(context, monkeypatch, "ClaimMail")[:2] == (True, [])
    assert start(context, monkeypatch, "ThreadLuxcavation")[:2] == (True, [])


def test_a_settings_file_saved_mid_task_changes_nothing_the_task_reads(context, monkeypatch):
    # #777: the options are read once, at the task's start: a GUI save mid-task reaches the next task, not this one.
    # Before, PlanRun read the run count from the file, the title's dialogs and the stop procedure too.
    entry_page(context, lambda run, teams: run.update(runs=1, auto_download=False))  # MirrorDungeon starts on it
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["run"].update(runs=5, auto_download=True, webhook_url="")
    path.write_text(json.dumps(data), encoding="utf-8")
    actions.TASK.update(runs=1, done=None)
    assert run_start_actions.PlanRun().run(context, None) is True and actions.TASK["done"] == "1 of 1 runs done"
    assert actions.allowed("auto_download") is False
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    actions.stop(context, "recovery used up")
    assert urlopen.call_args.args[0].full_url == "http://hook.invalid/"  # entry_page's, which the start read


@pytest.mark.parametrize("task, stopped", [("MirrorDungeon", False), ("ClaimMail", False), ("ExpLuxcavation", True),
                                           ("ThreadLuxcavation", True), ("ChargeEnkephalin", True)])
def test_a_task_whose_settings_do_not_load_at_its_start_goes_on_or_stops_as_before(context, monkeypatch, task, stopped):
    # No settings file: MirrorDungeon goes on to PlanRun, which fails it and says why (test_settings.py); a task with no
    # options of its own goes on and reads the defaults; a Luxcavation task and ChargeEnkephalin stop, before any tap.
    ok, stops, _ = start(context, monkeypatch, task)
    assert ok is not stopped
    assert stops == ([f"Invalid settings:\n- {actions.ROOT / 'config' / 'settings.json'} not found. {NO_TEAM}"]
                     if stopped else [])
    context.tasker.controller.post_click.assert_not_called()
    if not stopped:
        assert [actions.allowed(k) for k in ("auto_accept_terms", "auto_download", "keep_dismissed_screens")] == [True] * 3


def test_charge_enkephalin_reads_its_count_at_its_start(context, monkeypatch):
    # #429, #777: count 0 ends the task a success before any tap; another count goes on to the window.
    write(apply_edits(CASES["valid"], [{"set": "charge_enkephalin/count", "value": 0}]))
    assert start(context, monkeypatch, "ChargeEnkephalin")[0] is True and actions.TASK["done"] == "charge_enkephalin.count is 0: Lunacy left alone"
    write(apply_edits(CASES["valid"], [{"set": "charge_enkephalin/count", "value": 3}]))
    assert start(context, monkeypatch, "ChargeEnkephalin")[0] is True and actions.TASK["done"] is None
    assert actions.TASK["charge"]["count"] == 3


# The real tasks on MaaFramework (#777): a rule broken at the start ends the task at its entry node, before any tap.
RULE_STOPS = {
    "target": ("MirrorDungeon", [{"set": "run/target_floor", "value": 15}]),
    "exp_team": ("ExpLuxcavation", [{"set": "luxcavation/exp/team", "value": "gone"}]),
}


def child():
    actions, resource = load()

    class Still(game_class()):
        images = {"main": screen("MainWindow.png")}

    game = Still()
    game.screen = "main"
    tasker = bind(resource, game)
    out = {"error": None}
    for name, (task, edits) in RULE_STOPS.items():
        (actions.ROOT / "config").mkdir(exist_ok=True)
        (actions.ROOT / "config" / "settings.json").write_text(json.dumps(apply_edits(CASES["valid"], edits)), encoding="utf-8")
        game.clicks, game.keys = [], []
        evidence = actions.ROOT / "logs" / "evidence"
        before = len(list(evidence.iterdir())) if evidence.exists() else 0
        actions.LOG.clear()
        out[name] = {**result(run_task(tasker, name, task), game, actions),
                     "stops": [line.split(" ", 1)[1] for line in actions.LOG if " stop: " in line],
                     "evidence": (len(list(evidence.iterdir())) if evidence.exists() else 0) - before}
    print(json.dumps(out))


@pytest.mark.parametrize("name, procedure", [("target", False), ("exp_team", True)])
def test_a_broken_rule_ends_the_real_task_at_its_entry_node_before_any_tap(name, procedure):
    task, edits = RULE_STOPS[name]
    case = next(c for c in CASES["task_start"] if c["task"] == task and c["edits"] == edits)
    o = run_child(__file__)[name]
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, [task], [], [])
    assert o["stops"] == [f"stop: {invalid(case['cross'])}"]
    assert o["evidence"] == (1 if procedure else 0)  # MirrorDungeon fails; the Luxcavation task runs the stop procedure


if __name__ == "__main__":
    child()
