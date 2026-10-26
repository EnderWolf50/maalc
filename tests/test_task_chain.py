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
    out.update(succeeded=detail.status.succeeded, nodes=[n.name for n in detail.nodes])
    print(json.dumps(out))


def test_a_task_with_nothing_left_to_do_ends_a_success_on_task_done():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["starts"] == 1 and out["done_was"] is None
    assert out["succeeded"] is True
    assert out["nodes"][0] == "MirrorDungeon" and out["nodes"][-1] == "TaskDone"


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
    assert actions.RUN == {} and actions.TASK == {"runs": 0, "done": None} and not actions.SCREENS
    assert (actions.STUCK["flag"], actions.STUCK["kind"]) == (None, None)
    assert actions.STUCK["ladder"].counts == recovery.Ladder().counts
    assert not actions.STUCK["watch"].held(1.0)
    assert (actions.STUCK["l3"], actions.STUCK["updates"]) == (2, 1)


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


def test_plan_run_does_not_open_a_run_the_modules_cannot_claim(context):
    # #369: read 4 on the Drive page (< 5, one Claim): the task is done, Enter is not pressed.
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=4)
    assert actions.PlanRun().run(context, None) is True
    assert "Modules 4 < 5" in actions.TASK["done"]
    context.tasker.controller.post_click.assert_not_called()


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


def test_a_stop_of_one_task_leaves_the_list_running(context):
    actions.RUN["settings"] = {"run": {"webhook_url": ""}}
    assert actions.stop(context, "recovery used up") is False
    context.tasker.post_stop.assert_not_called()


if __name__ == "__main__":
    child()
