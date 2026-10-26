"""ClaimPassMissions (#371, spec 00 daily tasks): the real task on the repo's resource bundle, in MaaFramework 5.14.3 and
its OCR, on a small model of the game: a screenshot per screen, and the taps and the back key that move between them.
As test_go_home.py, the task runs in a child process (this file run as a script): the pytest process holds
MaaFramework in AgentServer mode.
"""

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

GAME = "com.ProjectMoon.LimbusCompany"
BANNER = (940, 190, 270, 90)  # the Limbus Pass banner on the main window
MISSIONS_TAB = (305, 38, 140, 38)
WEEKLY_TAB = (256, 350, 30, 100)
COIN = (350, 205, 40, 40)  # the weekly tab's first row
SCREENS = {"main": "MainWindow.png", "pass": "PassBattlePass.png", "daily": "PassMissionsDaily.png",
           "weekly": "PassMissionsWeekly.png", "weekly_claimable": "PassMissionsWeeklyClaimable.synthetic.png"}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run ClaimPassMissions from the main window, nothing to claim and a weekly row to claim; print one JSON line."""
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
            self.screen, self.claimable, self.clicks, self.keys = "main", False, [], []

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            if self.screen == "main" and inside(BANNER, x, y):
                self.screen = "pass"
            elif self.screen == "pass" and inside(MISSIONS_TAB, x, y):
                self.screen = "daily"
            elif self.screen == "daily" and inside(WEEKLY_TAB, x, y):
                self.screen = "weekly_claimable" if self.claimable else "weekly"
            elif self.screen == "weekly_claimable" and inside(COIN, x, y):
                self.screen = "weekly"
            return True

        def touch_down(self, contact, x, y, pressure):  # MaaFramework taps as touch down and up
            self.down = (x, y)
            return True

        def touch_move(self, contact, x, y, pressure):
            return True

        def touch_up(self, contact):
            return self.click(*self.down)

        def key_down(self, keycode):  # a key press is down and up
            self.down = keycode
            return True

        def key_up(self, keycode):
            self.keys.append(keycode)
            if keycode == 4 and self.screen != "main":  # the pass pages have no tab bar: back is the main window
                self.screen = "main"
            return True

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {GAME}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):  # swipe, touch_*, scroll ...: nothing moves
            return lambda *args: True

    game = Game()
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name in ("TaskStart", "GoHomeRun", "PassFinish", "StopTask", "DismissShot", "AcceptUpdate", "AcceptTerms",
                 "ConfirmDownload", "Halt"):
        resource.register_custom_action(name, getattr(actions, name)())
    import pass_missions

    for name, cls in (("GameAway", actions.GameAway), ("DoneFlag", actions.DoneFlag), ("HomeText", actions.HomeText),
                      ("PassClaimable", pass_missions.PassClaimable)):
        resource.register_custom_recognition(name, cls())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, claimable in {"nothing": False, "claim": True}.items():
        game.screen, game.claimable, game.clicks, game.keys = "main", claimable, [], []
        try:
            detail = tasker.post_task("ClaimPassMissions").wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "keys": game.keys, "screen": game.screen}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_nothing_to_claim_visits_both_tabs_and_ends_on_the_main_window():
    o = run_child()["nothing"]
    assert o["succeeded"] and o["screen"] == "main"
    assert [inside(BANNER, *o["clicks"][0]), inside(MISSIONS_TAB, *o["clicks"][1]), inside(WEEKLY_TAB, *o["clicks"][2])] == [True] * 3
    assert len(o["clicks"]) == 3 and o["keys"] == [4]  # the back key leaves the pass page
    assert o["nodes"][-1] == "TaskDone"


def test_a_weekly_row_to_claim_is_tapped_once():
    o = run_child()["claim"]
    assert o["succeeded"] and o["screen"] == "main" and o["nodes"][-1] == "TaskDone"
    assert [inside(COIN, *c) for c in o["clicks"]] == [False, False, False, True]


def test_claim_pass_missions_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ClaimPassMissions", "label": "$ClaimPassMissions", "entry": "ClaimPassMissions"} in interface["task"]


if __name__ == "__main__":
    child()
