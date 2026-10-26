"""ExpLuxcavation (#366): from wherever the last task left the game to the main window, Drive, Luxcavation's EXP tab
and the rightmost open stage's Enter; one battle later, back to the main window, a success.

The real task on the repo's resource bundle in MaaFramework 5.14.3, as test_go_home.py: a screenshot per screen, taps
and the back key that move between them. Enter opens the team page (ExpTeamSelect.png): the model picks the
TEAMS row and To Battle! there. The pages after To Battle! (level warning, start confirm, battle, results) have no capture
yet: the model plays them as one unknown screen that gives way to the EXP tab again. The task runs in a child process
(this file run as a script): the pytest process holds MaaFramework in AgentServer mode.
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

GAME = "com.ProjectMoon.LimbusCompany"
WINDOW_TAB = (790, 608, 70, 64)
DRIVE_TAB = (930, 600, 110, 80)
LUXCAVATION = (355, 97, 190, 125)  # Drive's Luxcavation button
EXP_TAB = (68, 234, 154, 60)
ENTERS = {"exp": (1000, 455, 240, 50), "locked": (660, 455, 240, 50)}  # stage 9's Enter: the rightmost, the middle card
TEAM_ROW = (75, 365, 110, 36)  # the TEAMS #3 row of the team page's list (ExpTeamSelect.png)
TO_BATTLE = (1070, 560, 150, 55)
FIGHT_SHOTS = 3  # screenshots the pages after Enter take before the EXP tab shows again

SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "exp": "LuxExp.png", "locked": "LuxExpLocked.png",
           "thread": "LuxThread.png", "team": "ExpTeamSelect.png", "fight": None}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run ExpLuxcavation from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
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

    actions.ROOT = Path(tempfile.mkdtemp())
    (actions.ROOT / "config").mkdir()
    settings = json.loads((ROOT / "tests" / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    settings["teams"][1]["game_team"] = 3  # the row ExpTeamSelect.png has lit
    images = {name: np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / png).convert("RGB"))[:, :, ::-1])
              if png else np.full((720, 1280, 3), 40, np.uint8) for name, png in SCREENS.items()}

    class Game(CustomController):
        """The screen the game shows and what a tap or the back key does there."""

        def set(self, screen):
            self.screen, self.clicks, self.keys, self.shots, self.picked = screen, [], [], 0, False
            self.stage = "exp" if screen != "locked" else "locked"

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            if self.screen == "fight":
                self.shots += 1
                if self.shots > FIGHT_SHOTS:
                    self.screen = self.stage
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            s = self.screen
            if s == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif s == "main" and inside(DRIVE_TAB, x, y):
                self.screen = "drive"
            elif s == "drive" and inside(LUXCAVATION, x, y):
                self.screen = "thread"  # the tab last left open
            elif s == "thread" and inside(EXP_TAB, x, y):
                self.screen = self.stage
            elif s in ENTERS and inside(ENTERS[s], x, y):
                self.screen = "team"
            elif s == "team" and inside(TEAM_ROW, x, y):
                self.picked = True
            elif s == "team" and self.picked and inside(TO_BATTLE, x, y):
                self.screen, self.shots = "fight", 0
            return True

        def touch_down(self, contact, x, y, pressure):
            self.down, self.dragged = (x, y), False
            return True

        def touch_move(self, contact, x, y, pressure):
            self.dragged = True  # the team list's scroll: a drag, not a tap
            return True

        def touch_up(self, contact):
            return True if self.dragged else self.click(*self.down)

        def key_down(self, keycode):
            return True

        def key_up(self, keycode):
            self.keys.append(keycode)
            if keycode == 4 and self.screen in ("exp", "locked", "thread"):
                self.screen = "drive"
            return True

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {GAME}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):
            return lambda *args: True

    game = Game()
    game.set("main")
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name in ("ExpStart", "ExpEnter", "ExpSelectTeam", "GoHomeRun", "StopTask", "DismissShot", "AcceptUpdate", "AcceptTerms", "ConfirmDownload",
                 "Halt", "TapUntil", "PlayTurn", "HoldTurn", "Victory"):
        resource.register_custom_action(name, getattr(actions, name)())
    for name in ("GameAway", "HomeText", "ExpText", "StuckFlag", "DoneFlag"):
        resource.register_custom_recognition(name, getattr(actions, name)())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, (screen, team) in {"drive": ("drive", "b"), "locked": ("locked", "b"), "no_team": ("drive", None)}.items():
        (actions.ROOT / "config" / "settings.json").write_text(
            json.dumps({**settings, "luxcavation": {"exp": {"count": 1, "team": team, "retries": 0}}}), encoding="utf-8")
        game.set(screen)
        try:
            detail = tasker.post_task("ExpLuxcavation").wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "keys": game.keys}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


@functools.cache  # one child run (~40 s) for every test
def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_exp_luxcavation_goes_home_first_enters_the_rightmost_open_stage_and_ends_home():
    out = run_child()
    o = out["drive"]
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # GoHome first (the Window tab), then Drive, Luxcavation, the EXP tab (Thread was open), stage 9's Enter, the team's
    # row (TEAMS #3) and To Battle!
    steps = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, EXP_TAB, ENTERS["exp"], TEAM_ROW, TO_BATTLE)
    assert [inside(box, *xy) for box, xy in zip(steps, taps)] == [True] * 7
    assert taps.count(taps[4]) == 1 and taps.count(taps[6]) == 1  # one battle
    # Back on the EXP tab after it: done, and GoHome again (the back key, then the Window tab)
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 8
    assert o["nodes"].count("ExpTeamSelect") == 1
    assert o["nodes"][:3] == ["ExpLuxcavation", "ExpHome", "ExpHub"] and o["nodes"][-1] == "TaskDone"


def test_exp_luxcavation_skips_a_locked_stage_on_the_right():
    o = run_child()["locked"]
    assert o["succeeded"]
    enters = [xy for xy in o["clicks"] if 440 <= xy[1] < 510]
    assert len(enters) == 1 and inside(ENTERS["locked"], *enters[0])


def test_exp_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child()["no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ExpLuxcavation"]


def test_exp_luxcavation_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ExpLuxcavation", "label": "$ExpLuxcavation", "entry": "ExpLuxcavation"} in interface["task"]


if __name__ == "__main__":
    child()
