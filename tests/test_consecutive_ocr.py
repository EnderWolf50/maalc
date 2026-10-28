"""The Consecutive Battle box's N (#375), read by actions.consecutive_now on the captures of tests/screens, and the team page
that says Chain To Battle! after a x N battle, which LuxTeamSelect must still know.

Real MaaFramework and its OCR, in a child process (this file run as a script), as test_module_count.py does.
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
# capture -> (the page's box, N): live 2026-10-27, the open row and the closed title read alike; Level Select's yellow 4 only
# reads through the narrow roi on the digit.
READS = {
    "LuxConsecExp1.png": ("exp", 1), "LuxConsecExp1Open.png": ("exp", 1), "LuxConsecExp2Open.png": ("exp", 2),
    "LuxConsecExp10Open.png": ("exp", 10), "LuxConsecExp9Open.png": ("exp", 9),
    "LuxConsecThread1.png": ("thread", 1), "LuxConsecThread2Open.png": ("thread", 2), "LuxConsecThread3Open.png": ("thread", 3),
    "LuxConsecThread10Open.png": ("thread", 10),
    "LuxConsecLevel3.png": ("level", 3), "LuxConsecLevel4Open.png": ("level", 4), "LuxConsecLevel4.png": ("level", 4),
}
# A page with no such box: the Drive page, the team page, a box of another page.
NONE = {"Drive.png": "exp", "LuxTeamSelect.png": "thread", "MainWindow.png": "level", "LuxConsecThread1.png": "level",
        "LuxConsecExp1.png": "level"}
TEAM_PAGES = ["LuxTeamSelect.png", "LuxTeamSelectChain.png"]
NOT_TEAM_PAGES = ["LuxConsecExp1.png", "LuxThreadLevels.png", "TeamSelect.png"]


def child():
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

        def __getattr__(self, name):
            return lambda *args: True

    def load(name):
        return np.asarray(Image.open(SCREENS / name).convert("RGB"))[:, :, ::-1].copy()

    out = {"read": {}, "none": {}, "team": {}}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for name, (box, _) in READS.items():
                    out["read"][name] = actions.consecutive_now(context, load(name), box)
                for name, box in NONE.items():
                    out["none"][f"{name}/{box}"] = actions.consecutive_now(context, load(name), box)
                for name in [*TEAM_PAGES, *NOT_TEAM_PAGES]:
                    out["team"][name] = actions.seen(context, load(name), "LuxTeamSelect") is not None
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


@pytest.mark.parametrize(("name", "n"), [pytest.param(k, v[1], id=k) for k, v in READS.items()])
def test_the_title_reads_as_its_count(read, name, n):
    assert read["read"][name] == n


@pytest.mark.parametrize("key", [f"{n}/{b}" for n, b in NONE.items()])
def test_a_page_without_that_box_reads_none(read, key):
    assert read["none"][key] is None


@pytest.mark.parametrize("name", TEAM_PAGES)
def test_the_team_page_is_known_before_a_battle_and_before_a_chain(read, name):
    assert read["team"][name] is True


@pytest.mark.parametrize("name", NOT_TEAM_PAGES)
def test_other_pages_are_not_the_team_page(read, name):
    assert read["team"][name] is False


if __name__ == "__main__":
    child()
