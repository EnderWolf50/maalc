"""The shop node on the map, read by MaaFramework's own template matching (#146), on live captures.

actions.node_at runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the
MapNodeShop templates and their scores are the agent's on the device. The pytest process holds MaaFramework in
AgentServer mode, so the task runs in a child process: this file run as a script, as test_shop_cells.py does.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it
from test_shop import screen_with  # noqa: E402

# case: node centre. The crops sit where the live frames had them: the pre-boss shop at the left of a map panned
# toward the boss, a bus 260 px behind it.
CASES = {
    "map_shop_cyan": (330, 145),  # live 2026-10-18 floor 2, cyan theme: read as an event (#146)
    "map_shop_orange": (330, 145),  # floor 1, orange theme: read as an event too
    "map_event_orange": (326, 144),  # a "?" in the same theme and place must stay an event
}


def child():
    """Run every case through actions.node_at in a MaaFramework task; print {case: node type}."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
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

    out = {}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for case, (cx, cy) in CASES.items():
                    out[case] = actions.node_at(context, screen_with(case), cx, cy, costs=False)
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return True

    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    resource.register_custom_action("Probe", Probe())
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    tasker.post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    print(json.dumps(out))


@pytest.fixture(scope="module")
def read():
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


@pytest.mark.parametrize("case, kind", [
    ("map_shop_cyan", "shop"),
    ("map_shop_orange", "shop"),
    ("map_event_orange", "event"),
])
def test_the_shop_node_is_a_shop_in_every_theme_pack_colour_and_a_question_mark_stays_an_event(read, case, kind):
    assert read[case] == kind


if __name__ == "__main__":
    child()
