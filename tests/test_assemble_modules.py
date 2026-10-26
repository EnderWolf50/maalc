"""AssembleModules (#370): the real task on the repo's resource bundle, in MaaFramework 5.14.3 and its OCR, on a small model
of the game: a screenshot per screen and the taps that move between them. As test_go_home.py, the task runs in a child
process (this file run as a script): the pytest process holds MaaFramework in AgentServer mode.

It also settles how a daily task starts and ends on GoHome: the hub's last next entry is [JumpBack]GoHome, so it runs
only when no screen the task knows is up, and the task ends from the main window.
"""

import functools
import json
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

WINDOW_TAB = (790, 608, 70, 64)
ENK_BAR = (440, 640)
CONFIRM = (760, 534)
SCREENS = {"main": "MainWindowLater.png", "low": "MainWindowLowEnkephalin.synthetic.png", "panel": "EnkephalinPanel.png",
           "drive": "Drive.png", "entry": "EntryNewRun.png"}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run AssembleModules from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
    from maa.controller import CustomController
    from maa.resource import Resource
    from maa.tasker import Tasker
    from PIL import Image

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    actions.ROOT = Path(tempfile.mkdtemp())  # the stop procedure's evidence and log
    images = {name: np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / png).convert("RGB"))[:, :, ::-1])
              for name, png in SCREENS.items()}

    class Game(CustomController):
        def __init__(self):
            super().__init__()
            self.set("main")

        def set(self, screen, confirm_to="low"):
            self.screen, self.confirm_to, self.clicks, self.keys = screen, confirm_to, [], []

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            if self.screen in ("main", "low") and (x, y) == ENK_BAR:
                self.screen = "panel"
            elif self.screen == "panel" and inside((650, 500, 220, 60), x, y):  # Confirm
                self.screen = self.confirm_to
            elif self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            return True

        def touch_down(self, contact, x, y, pressure):
            self.down = (x, y)
            return True

        def touch_move(self, contact, x, y, pressure):
            return True

        def touch_up(self, contact):
            return self.click(*self.down)

        def key_down(self, keycode):
            self.down = keycode
            return True

        def key_up(self, keycode):
            self.keys.append(keycode)
            if keycode == 4 and self.screen == "entry":
                self.screen = "drive"
            return True

        def shell(self, cmd, timeout):
            return "  mCurrentFocus=Window{1a2b u0 com.ProjectMoon.LimbusCompany/com.unity3d.player.UnityPlayerActivity}"

        def __getattr__(self, name):
            return lambda *args: True

    game = Game()
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name, cls in (("StopTask", actions.StopTask), ("DismissShot", actions.DismissShot), ("TaskStart", actions.TaskStart),
                      ("AssembleMain", actions.AssembleMain), ("AssemblePanel", actions.AssemblePanel),
                      ("AcceptUpdate", actions.AcceptUpdate), ("AcceptTerms", actions.AcceptTerms),
                      ("ConfirmDownload", actions.ConfirmDownload), ("Halt", actions.Halt)):
        resource.register_custom_action(name, cls())
    resource.register_custom_recognition("GameAway", actions.GameAway())
    resource.register_custom_recognition("HomeText", actions.HomeText())
    resource.register_custom_recognition("DoneFlag", actions.DoneFlag())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, (screen, confirm_to) in {
        "main": ("main", "low"), "low": ("low", "low"), "drive": ("drive", "low"), "entry": ("entry", "low"),
        "panel": ("panel", "low"), "no_drop": ("main", "main"),
    }.items():
        game.set(screen, confirm_to)
        try:
            detail = tasker.post_task("AssembleModules", {"AssembleHub": {"timeout": 15000}}).wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "keys": game.keys, "done": actions.TASK["done"]}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


@functools.cache
def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_assembles_once_from_the_main_window_and_ends_there():
    o = run_child()["main"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "AssembleMain" in o["nodes"] and "AssemblePanel" in o["nodes"]
    assert o["clicks"] == [list(ENK_BAR), list(CONFIRM)] and o["keys"] == []  # >> not tapped: the window's own number is under 20
    assert "assembled" in o["done"]


def test_starts_on_gohome_from_another_page():
    out = run_child()
    for name in ("drive", "entry"):
        o = out[name]
        assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "HomeWindowTab" in o["nodes"], name
        assert "assembled" in o["done"], name
    assert out["entry"]["keys"] == [4]  # the back key leaves the entry page, as GoHome alone


def test_under_a_module_of_enkephalin_nothing_is_opened_and_the_task_succeeds():
    o = run_child()["low"]
    assert o["succeeded"] and o["clicks"] == [] and "nothing to assemble" in o["done"]
    assert "AssemblePanel" not in o["nodes"]


def test_a_window_already_open_is_confirmed():
    o = run_child()["panel"]
    assert o["succeeded"] and o["clicks"] == [list(CONFIRM)] and "assembled" in o["done"]


def test_a_bar_that_does_not_drop_after_confirm_fails_the_task():
    o = run_child()["no_drop"]
    assert o["succeeded"] is False and o["nodes"][-1] != "TaskDone"


def test_fractions_reads_n_over_cap_left_to_right():
    import actions

    assert actions.fractions([("2 / 136", (200, 0, 1, 1)), ("22 / 136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("22/136 > 2/136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("Owned 104", (0, 0, 1, 1))]) == []


def test_assemble_modules_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "AssembleModules", "label": "$AssembleModules", "entry": "AssembleModules"} in interface["task"]


if __name__ == "__main__":
    child()
