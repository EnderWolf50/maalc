"""The task chain (#364, ADR 0010): a task with nothing left to do ends a success, so the client's list goes on.

MaaFramework 5.14.3 ends a task a success when it reaches a node with an empty next off any [JumpBack] (a stack
with nothing to go back to). maa-tools test runs recognitions only, with no task status, so this runs the real
MirrorDungeon task: the repo's resource bundle, a still black controller, the agent's own TaskStart, StuckFlag and
DoneFlag. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a child process: this file
run as a script, as test_map_cost.py does.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

if __name__ != "__main__":  # pytest; the script (child) imports actions itself, under a stand-in AgentServer
    import actions
    import recovery
    from test_actions import clock, context  # noqa: F401 (the fake Maa context the in-process tests use)


def child():
    """Run MirrorDungeon until TaskDone; print its status and nodes."""
    from maa.controller import CustomController
    from maa.custom_recognition import CustomRecognition
    from maa.resource import Resource
    from maa.tasker import Tasker

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # start_app, click, swipe, touch_*, keys, text, scroll: nothing moves
            return lambda *args: True

    out = {"error": None, "starts": 0}

    class HubText(CustomRecognition):
        """MirrorHub's first pass: an action found nothing left to do (PlanRun on the entry page); no screen hits."""

        def analyze(self, context, argv):
            try:
                out["done_was"] = actions.TASK["done"]  # TaskStart cleared the last task's
                actions.done("nothing left to do")
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return None

    class TaskStart(actions.TaskStart):
        def run(self, context, argv):
            out["starts"] += 1
            return super().run(context, argv)

    resource.register_custom_action("TaskStart", TaskStart())
    resource.register_custom_recognition("StuckFlag", actions.StuckFlag())
    resource.register_custom_recognition("DoneFlag", actions.DoneFlag())
    resource.register_custom_recognition("HubText", HubText())
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    actions.TASK["done"] = "left by the last task"
    detail = tasker.post_task("MirrorDungeon").wait().get()
    out.update(succeeded=detail.status.succeeded, nodes=[n.name for n in detail.nodes], first_starts=out["starts"])
    actions.STUCK["halted"] = "maintenance"  # D8: an account-level stop earlier this launch
    detail = tasker.post_task("MirrorDungeon").wait().get()
    out["after_halt"] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes]}
    print(json.dumps(out))


def test_a_task_with_nothing_left_to_do_ends_a_success_on_task_done():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["first_starts"] == 1 and out["done_was"] is None
    assert out["succeeded"] is True
    assert out["nodes"][0] == "MirrorDungeon" and out["nodes"][-1] == "TaskDone"


def test_a_task_after_an_account_level_stop_fails_at_its_entry_node():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["after_halt"] == {"succeeded": False, "nodes": ["MirrorDungeon"]}


def test_each_task_starts_with_a_clean_slate_but_the_game_restarts_count_per_launch(context, monkeypatch):
    # #364, ADR 0010: a task list runs tasks on one agent; what one task left must not reach the next.
    actions.RUN.update(floor=3, guard=2)
    actions.TASK.update(runs=1, done="1 of 1 runs done")
    for key, value in dict(l3=2, updates=1, watch=recovery.Watchdog(), ladder=recovery.Ladder()).items():
        monkeypatch.setitem(actions.STUCK, key, value)  # restored afterwards: the later tests count from 0
    actions.STUCK.update(flag=(None, 1, "x"), kind="MirrorMap")
    actions.STUCK["watch"].hold(0.0, 600)
    actions.STUCK["ladder"].stuck("MirrorMap", 1, 0)
    actions.SCREENS.append(np.zeros((720, 1280, 3), np.uint8))
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert actions.RUN == {} and actions.TASK == {"runs": 0, "done": None, "entry": "MirrorDungeon", "ended": False} and not actions.SCREENS
    assert (actions.STUCK["flag"], actions.STUCK["kind"]) == (None, None)
    assert actions.STUCK["ladder"].counts == recovery.Ladder().counts
    assert not actions.STUCK["watch"].held(1.0)
    assert (actions.STUCK["l3"], actions.STUCK["updates"]) == (2, 1)


def interrupted_run(context, how):
    """MirrorDungeon starts a run, then ends as how says; the next task's TaskStart runs. RUN afterwards."""
    actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    actions.RUN.update(settings={"run": {"webhook_url": ""}}, team={"id": "t1", "name": "A"}, planned=True, floor=3)
    actions.TASK["runs"] = 1
    how()
    return actions.TaskStart().run(context, SimpleNamespace(node_name=next_task)) and dict(actions.RUN)


next_task = "MirrorDungeon"


def test_a_task_the_client_interrupted_leaves_its_run_to_the_same_task(context):
    # D3 (#362): no done(), no stop(): the client stopped the task mid-run, so MirrorDungeon picks the same run up, as
    # before the task chain. Its own state still starts over: the task's runs, the ladder, the screens.
    run = interrupted_run(context, lambda: None)
    assert run["floor"] == 3 and run["team"]["id"] == "t1" and run["planned"]
    assert actions.TASK["runs"] == 0 and actions.STUCK["ladder"].counts == recovery.Ladder().counts


@pytest.mark.parametrize("how", [
    lambda: actions.done("1 of 1 runs done"),
    lambda: actions.stop(MagicMock(), "recovery used up"),
])
def test_a_task_that_ended_by_done_or_the_stop_procedure_leaves_no_run(context, monkeypatch, how):
    monkeypatch.setattr(actions, "screen", lambda context: np.zeros((720, 1280, 3), np.uint8))
    assert interrupted_run(context, how) == {}


def test_an_interrupted_run_does_not_reach_another_task(context, monkeypatch):
    # Not the same task: a daily task's stop would write the Mirror Dungeon run's runs.jsonl line.
    monkeypatch.setattr(sys.modules[__name__], "next_task", "ExpLuxcavation")
    assert interrupted_run(context, lambda: None) == {}


def entry_page(context, edit=lambda run, teams: None):
    """settings.json under the agent's ROOT (settings_cases' valid file, edited); the entry page reads no weekly bonus."""
    data = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    edit(data["run"], data["teams"])
    data["run"]["webhook_url"] = "http://hook.invalid/"
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    actions.RUN.clear()
    context.tasker.controller.info = {}  # the default rotation cursor
    actions.TASK["modules"] = 20  # what OpenDrive read on this trip (#369)


@pytest.mark.parametrize("edit, done", [
    (lambda run, teams: run.update(runs=1), "1 of 1 runs done"),
    (lambda run, teams: run.update(stop_when_weekly_bonus_out=True), "weekly bonuses used up"),
    (lambda run, teams: teams[0].update(usage="hard_only"), "no enabled team may run normal"),
    (lambda run, teams: [t.update(enabled=False) for t in teams], "no enabled team"),  # review S3: no team at all
])
def test_a_mirror_dungeon_that_has_nothing_left_to_do_ends_a_success(context, monkeypatch, edit, done):
    # #364: the run count reached, the weekly bonuses out, no team for the difficulty: the task is done, not failed, so
    # the client's list goes on. No stop procedure: no runs.jsonl line, no webhook, no evidence; Enter is not pressed.
    entry_page(context, edit)
    actions.TASK.update(runs=1, done=None)
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    assert actions.PlanRun().run(context, None) is True
    assert done in actions.TASK["done"]
    assert not (actions.ROOT / "logs").exists() and not urlopen.called
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_called_once_with("GoHome")  # live-2 G4: the main window, not the entry page, for the next task


def test_plan_run_does_not_open_a_run_the_modules_cannot_claim(context):
    # #369: read 4 on the Drive page (< 5, one Claim): the task is done, Enter is not pressed.
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=4)
    assert actions.PlanRun().run(context, None) is True
    assert "Modules 4 < 5" in actions.TASK["done"]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_called_once_with("GoHome")


def test_plan_run_logs_modules_that_cover_a_claim(context, monkeypatch):
    # #369: a run the Modules cover says so too, not only one they do not.
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=118)
    logged = []
    monkeypatch.setattr(actions, "log", logged.append)
    assert actions.PlanRun().run(context, None) is True and actions.RUN["planned"]
    assert "new run: Modules 118 >= 5" in logged


def test_plan_run_starts_when_the_modules_did_not_read(context):
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=None)
    assert actions.PlanRun().run(context, None) is True
    assert actions.TASK["done"] is None and "modules" not in actions.TASK and actions.RUN["planned"]


def test_plan_run_backs_out_to_read_the_modules_when_the_trip_skipped_drive(context):
    # #369: the last run's Claim took 5, so an old value is none: the back key, twice at most, then the run starts.
    entry_page(context)
    actions.TASK.clear()
    actions.TASK.update(runs=0, done=None)
    for n in (1, 2):
        assert actions.PlanRun().run(context, None) is True
        context.tasker.controller.post_click_key.assert_called_with(actions.BACK_KEY)
        assert context.tasker.controller.post_click_key.call_count == n and not actions.RUN
    assert actions.PlanRun().run(context, None) is True and actions.RUN["planned"]
    assert context.tasker.controller.post_click_key.call_count == 2


@pytest.mark.parametrize("action, run", [
    ("Halt", {}),  # MaintenanceNotice, ClientOutdated
    ("ConfirmDownload", {"auto_download": False}),
    ("AcceptUpdate", {"auto_download": False}),
    ("AcceptTerms", {"auto_accept_terms": False}),
])
def test_an_account_level_stop_ends_the_whole_task_list(context, action, run):
    # #364: every task after this one would meet the same screen: after the stop procedure, post_stop empties the
    # client's queue.
    actions.RUN["settings"] = {"run": {"webhook_url": "", **run}}
    argv = SimpleNamespace(node_name="MaintenanceNotice", custom_action_param='"maintenance"', box=[0, 0, 10, 10])
    assert getattr(actions, action)().run(context, argv) is False
    context.tasker.post_stop.assert_called_once()
    assert list((actions.ROOT / "logs" / "evidence").iterdir())  # the stop procedure ran first


def test_an_update_that_keeps_coming_back_ends_the_whole_task_list(context, monkeypatch):
    # D1 (#362): the game asks for an update past its restarts with auto_download on: every later task would meet it.
    monkeypatch.setitem(actions.STUCK, "updates", actions.UPDATE_RESTARTS)
    actions.RUN["settings"] = {"run": {"webhook_url": "", "auto_download": True}}
    argv = SimpleNamespace(node_name="UpdateDialog", custom_action_param=None, box=[0, 0, 10, 10])
    assert actions.AcceptUpdate().run(context, argv) is False
    context.tasker.post_stop.assert_called_once()
    context.tasker.controller.post_click.assert_not_called()


def test_every_task_after_an_account_level_stop_fails_at_its_entry_without_a_tap_or_a_webhook(context, monkeypatch):
    # D8 (#362): MFAAvalonia hands the tasker one task at a time, so post_stop does not reach the next: the agent
    # remembers the stop for this launch, and each later entry fails before anything (no evidence, no webhook).
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    actions.RUN["settings"] = {"run": {"webhook_url": "http://hook.invalid/"}}
    argv = SimpleNamespace(node_name="MaintenanceNotice", custom_action_param='"maintenance"', box=[0, 0, 10, 10])
    assert actions.Halt().run(context, argv) is False and urlopen.call_count == 1
    evidence = list((actions.ROOT / "logs" / "evidence").iterdir())
    context.reset_mock()
    for start, node, param in [(actions.TaskStart, "ClaimMail", None), (actions.LuxStart, "ExpLuxcavation", '"exp"'),
                               (actions.ChargeStart, "ChargeEnkephalin", None)]:
        assert start().run(context, SimpleNamespace(node_name=node, custom_action_param=param)) is False, node
    assert urlopen.call_count == 1 and list((actions.ROOT / "logs" / "evidence").iterdir()) == evidence
    assert not context.method_calls and not context.tasker.controller.method_calls  # no tap, no key, no screenshot
    assert any("skip: account-level stop earlier this launch" in line for line in actions.LOG)


def test_the_account_level_stop_is_remembered_for_the_whole_launch(context):
    actions.RUN["settings"] = {"run": {"webhook_url": ""}}
    actions.stop(context, "recovery used up")
    assert actions.STUCK["halted"] is None  # one task's stop: the next task runs
    actions.stop(context, "maintenance", whole_list=True)
    assert actions.STUCK["halted"] == "maintenance"


def test_a_stop_of_one_task_leaves_the_list_running(context):
    actions.RUN["settings"] = {"run": {"webhook_url": ""}}
    assert actions.stop(context, "recovery used up") is False
    context.tasker.post_stop.assert_not_called()


if __name__ == "__main__":
    child()
