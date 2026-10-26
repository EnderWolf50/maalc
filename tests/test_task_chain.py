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

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it


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


if __name__ == "__main__":
    child()
