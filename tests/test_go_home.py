"""GoHome (#365, spec 00 daily tasks): back to the main window from wherever the last task left the game.

The real task on the repo's resource bundle, in MaaFramework 5.14.3 and its OCR, on a small model of the game: a
screenshot per screen, taps and the back key that move between them, and `dumpsys window` for the front package. As
test_task_chain.py, the task runs in a child process (this file run as a script): the pytest process holds
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
WINDOW_TAB = (790, 608, 70, 64)  # the bottom tab bar's Window tab
MAILBOX_CLOSE = (690, 530, 175, 45)
SETTINGS_RETURN = (500, 370, 280, 45)
TITLE_TAP = (540, 300, 200, 120)

# screen name -> tests/screens image (None: black, the game is not up)
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "sinners": "SinnersTab.png", "mailbox": "Mailbox.png",
           "settings": "SettingsMenu.png", "entry": "EntryNewRun.png", "title": "Title.png", "black": None}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run GoHome from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys, starts}}."""
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
              if png else np.zeros((720, 1280, 3), np.uint8) for name, png in SCREENS.items()}

    class Game(CustomController):
        """The screen the game shows and what a tap or the back key does there."""

        def __init__(self):
            super().__init__()
            self.set("main")

        def set(self, screen, focus=GAME):
            self.screen, self.focus, self.clicks, self.keys, self.starts = screen, focus, [], [], 0

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return images["black" if self.focus != GAME else self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            if self.screen in ("drive", "sinners") and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif self.screen == "mailbox" and inside(MAILBOX_CLOSE, x, y):
                self.screen = "main"
            elif self.screen == "settings" and inside(SETTINGS_RETURN, x, y):
                self.screen = "main"
            elif self.screen == "title" and inside(TITLE_TAP, x, y):
                self.screen = "main"
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
            return self.click_key(keycode)

        def click_key(self, keycode):
            self.keys.append(keycode)
            if keycode == 4 and self.screen == "entry":  # the entry page's back: the Drive tab
                self.screen = "drive"
            return True

        def start_app(self, intent):
            self.starts += 1
            self.focus, self.screen = GAME, "title"
            return True

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {self.focus}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):  # swipe, touch_*, scroll ...: nothing moves
            return lambda *args: True

    game = Game()
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name, cls in (("GameAway", actions.GameAway), ("StopTask", actions.StopTask), ("DismissShot", actions.DismissShot),
                      ("AcceptUpdate", actions.AcceptUpdate), ("AcceptTerms", actions.AcceptTerms),
                      ("ConfirmDownload", actions.ConfirmDownload), ("Halt", actions.Halt)):
        (resource.register_custom_recognition if name == "GameAway" else resource.register_custom_action)(name, cls())
    resource.register_custom_recognition("HomeText", actions.HomeText())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, (screen, focus) in {
        "drive": ("drive", GAME), "sinners": ("sinners", GAME), "main": ("main", GAME), "mailbox": ("mailbox", GAME),
        "settings": ("settings", GAME), "entry": ("entry", GAME), "closed": ("black", "com.android.launcher"),
        "stuck": ("entry", GAME),
    }.items():
        game.set(screen, focus)
        if scenario == "stuck":  # the back key does nothing: it is pressed up to its limit, then the task fails
            game.click_key = lambda keycode: game.keys.append(keycode) or True  # an instance attribute: key_up finds it
        override = {"GoHome": {"timeout": 4000}} if scenario == "stuck" else {}
        try:
            detail = tasker.post_task("GoHome", override).wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "keys": game.keys, "starts": game.starts}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_go_home_reaches_the_main_window_from_each_start():
    out = run_child()
    for name in ("drive", "sinners"):  # the tab bar is up with another tab open: tap Window, no back key
        o = out[name]
        assert o["succeeded"] and o["keys"] == [] and o["nodes"][-1] == "HomeReached", name
        assert len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]), name
    # Already home: nothing is pressed.
    assert out["main"]["succeeded"] and out["main"]["clicks"] == [] and out["main"]["keys"] == []
    # A popup over the main window comes first, even though the Window tab still shows lit under the settings menu.
    assert out["mailbox"]["succeeded"] and len(out["mailbox"]["clicks"]) == 1
    assert inside(MAILBOX_CLOSE, *out["mailbox"]["clicks"][0]) and out["mailbox"]["nodes"][-1] == "HomeReached"
    assert out["settings"]["succeeded"] and "SettingsMenu" in out["settings"]["nodes"]
    # A page with no tab bar: the back key, then the tab.
    assert out["entry"]["succeeded"] and out["entry"]["keys"] == [4] and len(out["entry"]["clicks"]) == 1


def test_go_home_starts_the_game_when_it_is_not_in_front_and_taps_through_the_title():
    o = run_child()["closed"]
    assert o["succeeded"] and o["starts"] == 1 and o["keys"] == []
    assert "HomeGameAway" in o["nodes"] and "NavTitle" in o["nodes"] and o["nodes"][-1] == "HomeReached"


def test_go_home_fails_after_a_limited_number_of_back_keys_when_the_screen_never_changes():
    o = run_child()["stuck"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5
    assert o["nodes"][-1] == "GoHomeLost"


def test_go_home_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "GoHome", "label": "$GoHome", "entry": "GoHome"} in interface["task"]


if __name__ == "__main__":
    child()
