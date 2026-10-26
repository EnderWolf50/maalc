"""The Enkephalin Modules number in the bottom-left panel (#367): read by actions.module_count on the captures in
tests/screens that show the panel, and None where it does not (a page without it, a screen where the icon is not there).

The same function gives #369's Mirror Dungeon threshold. It runs inside a real MaaFramework task (resource bundle loaded,
a still controller), so the OCR is the agent's on the device; the pytest process holds MaaFramework in AgentServer
mode, so the task runs in a child process: this file run as a script, as test_map_cost.py does.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

SCREENS = ROOT / "tests" / "screens"
# Labelled by eye (2026-10-26 live; the panel moves between the main window's x 393 and the Luxcavation pages' x 242).
MODULES = {
    "MainWindow.png": 182, "MainWindowFadeIn.png": 182, "MainWindowLater.png": 104, "Drive.png": 182,
    "LuxExp.png": 104, "LuxExpLocked.png": 104, "LuxThread.png": 104,
}
# No panel, or none this function can read: the title screen, the Mirror Dungeon map, a shop, the Mirror Dungeon entry page (#369: PlanRun's read gives None there).
NONE = ["Title.png", "MirrorMap.png", "Shop.png", "Loading.png", "EntryNewRun.png", "EntryPaused.png", "EntryParallelOn.png"]


def child():
    """Read every capture through actions.module_count in a MaaFramework task; print {image: number read}."""
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
                for name in [*MODULES, *NONE]:
                    image = np.asarray(Image.open(SCREENS / name).convert("RGB"))[:, :, ::-1].copy()
                    out[name] = actions.module_count(context, image)
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


@pytest.mark.parametrize(("name", "modules"), [pytest.param(n, m, id=n) for n, m in MODULES.items()])
def test_the_panel_reads_as_its_number(read, name, modules):
    assert read[name] == modules


@pytest.mark.parametrize("name", NONE)
def test_a_screen_without_the_panel_reads_as_none(read, name):
    assert read[name] is None


if __name__ == "__main__":
    child()
