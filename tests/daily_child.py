"""What the daily tasks' MaaFramework tests share (#364-#373): each runs the real task on the repo's resource bundle, in
MaaFramework 5.14.3 and its OCR, on a small model of the game (a screenshot per screen, the taps and keys that move
between them). The pytest process holds MaaFramework in AgentServer mode, so the task runs in a child process: the
test file run as a script (run_child), whose child() uses load, game_class and bind.
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


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def screen(png):
    """tests/screens/png as MaaFramework's BGR frame."""
    from PIL import Image

    return np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / png).convert("RGB"))[:, :, ::-1])


def load():
    """(actions, resource): MaaFramework's Resource first, then actions under a stand-in AgentServer that records what
    the agent registers; every custom action and recognition goes on the resource, as the agent serves them. ROOT is a
    new temporary folder (the settings, the stop procedure's evidence and log)."""
    from maa.resource import Resource

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    found = []

    def record(kind):
        return staticmethod(lambda name: lambda cls: found.append((kind, name, cls)) or cls)

    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": record("action"), "custom_recognition": record("recognition")})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    for kind, name, cls in found:
        (resource.register_custom_action if kind == "action" else resource.register_custom_recognition)(name, cls())
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    actions.ROOT = Path(tempfile.mkdtemp())
    return actions, resource


def game_class():
    """The base of a test's game model: screencap shows images[screen], `dumpsys window` reads focus in front. clicks
    and keys record what was pressed; a subclass sets images and moves screen in on_tap(x, y), on_key(keycode) and
    on_swipe(down, last), a drag of 30 px or more."""
    from maa.controller import CustomController

    class Game(CustomController):
        images = {}
        focus = GAME

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return self.images[self.screen]

        def on_tap(self, x, y):
            return True

        def on_key(self, keycode):
            return True

        def on_swipe(self, down, last):
            return True

        def click(self, x, y):
            self.clicks.append((x, y))
            return self.on_tap(x, y)

        def touch_down(self, contact, x, y, pressure):  # MaaFramework taps as touch down and up
            self.down = self.last = (x, y)
            return True

        def touch_move(self, contact, x, y, pressure):
            self.last = (x, y)
            return True

        def touch_up(self, contact):
            if max(abs(self.last[0] - self.down[0]), abs(self.last[1] - self.down[1])) < 30:
                return self.click(*self.down)
            return self.on_swipe(self.down, self.last)

        def key_down(self, keycode):  # a key press is down and up
            return True

        def key_up(self, keycode):
            self.keys.append(keycode)
            return self.on_key(keycode)

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {self.focus}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):  # start_app, scroll ...: nothing moves
            return lambda *args: True

    return Game


def bind(resource, game):
    """A Tasker on the resource and the connected game model."""
    from maa.tasker import Tasker

    game.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, game)
    return tasker


def result(detail, game, actions):
    """A task's outcome for the test: its status, the nodes it went through, what the model was pressed, the done reason."""
    return {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes], "clicks": game.clicks,
            "keys": game.keys, "screen": game.screen, "done": actions.TASK["done"]}


def probe_child(body):
    """The child of a test that calls an agent function on the real OCR: body(context, actions, out) runs inside a custom
    action of a MaaFramework task on a still, black game; whatever it puts in the dict out is printed as the one JSON
    line, and an exception in it as out["error"] (MaaFramework swallows it)."""
    from maa.custom_action import CustomAction

    actions, resource = load()
    out = {"error": None}

    class Still(game_class()):
        images = {"black": np.zeros((720, 1280, 3), np.uint8)}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                body(context, actions, out)
            except Exception:
                out["error"] = traceback.format_exc()
            return True

    game = Still()
    game.screen, game.clicks, game.keys = "black", [], []
    resource.register_custom_action("Probe", Probe())
    bind(resource, game).post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    print(json.dumps(out))


@functools.cache  # one child run for all the tests of a file
def run_child(path, timeout=600):
    """Run the test file at path as a script; its one JSON line, which has no error."""
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out
