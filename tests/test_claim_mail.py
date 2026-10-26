"""ClaimMail (#372, spec 00 daily tasks): open the Mailbox, press Claim All, end at the main window.

The real task on the repo's resource bundle, in MaaFramework 5.14.3 and its OCR, on a small model of the game: a
screenshot per screen and the taps that move between them. As test_go_home.py, the task runs in a child process
(this file run as a script): the pytest process holds MaaFramework in AgentServer mode.
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
MAIL_ICON = (1085, 95, 70, 60)
MAILBOX_CLOSE = (690, 530, 175, 45)
CLAIM_ALL = (880, 530, 180, 45)

# screen name -> tests/screens image
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "mailbox": "Mailbox.png", "empty": "MailboxEmpty.png"}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run ClaimMail from each start; print one JSON line {scenario: {succeeded, nodes, clicks, screen, done}}."""
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
        """The screen the game shows and what a tap does there; the mailbox holds mail until Claim All."""

        def __init__(self):
            super().__init__()
            self.set("main")

        def set(self, screen, mail=True):
            self.screen, self.mail, self.clicks = screen, mail, []

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            if self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif self.screen == "main" and inside(MAIL_ICON, x, y):
                self.screen = "mailbox" if self.mail else "empty"
            elif self.screen == "mailbox" and inside(CLAIM_ALL, x, y):
                self.screen, self.mail = "empty", False
            elif self.screen in ("mailbox", "empty") and inside(MAILBOX_CLOSE, x, y):
                self.screen = "main"
            return True

        def touch_down(self, contact, x, y, pressure):  # MaaFramework taps as touch down and up
            self.down = (x, y)
            return True

        def touch_move(self, contact, x, y, pressure):
            return True

        def touch_up(self, contact):
            return self.click(*self.down)

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {GAME}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):
            return lambda *args: True

    game = Game()
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name, cls in (("TaskStart", actions.TaskStart), ("StopTask", actions.StopTask), ("GoHomeRun", actions.GoHomeRun), ("MailFinish", actions.MailFinish),
                      ("DismissShot", actions.DismissShot), ("AcceptUpdate", actions.AcceptUpdate),
                      ("AcceptTerms", actions.AcceptTerms), ("ConfirmDownload", actions.ConfirmDownload),
                      ("Halt", actions.Halt)):
        resource.register_custom_action(name, cls())
    for name, cls in (("GameAway", actions.GameAway), ("DoneFlag", actions.DoneFlag), ("HomeText", actions.HomeText),
                      ("MailText", actions.MailText), ("MailPopups", actions.MailPopups)):
        resource.register_custom_recognition(name, cls())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, (screen, mail) in {
        "main": ("main", True), "drive": ("drive", True), "box_open": ("mailbox", True), "no_mail": ("main", False),
    }.items():
        game.set(screen, mail)
        try:
            detail = tasker.post_task("ClaimMail", {"ClaimMailHub": {"timeout": 20000}}).wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "screen": game.screen, "done": actions.TASK["done"]}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def strip(path):
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("//"))


def test_claim_mail_presses_claim_all_once_and_ends_at_the_main_window():
    out = run_child()
    for name in ("main", "drive", "box_open"):
        o = out[name]
        assert o["succeeded"] and o["screen"] == "main" and o["done"] == "no mail to claim", name
        claims = [c for c in o["clicks"] if inside(CLAIM_ALL, *c)]
        assert len(claims) == 1, name  # the one claim; the empty box after it is not pressed again
        assert o["nodes"][-1] == "TaskDone" and "MailClaimAll" in o["nodes"] and "MailFinish" in o["nodes"], name
    # The first step is GoHome (spec 01): from Drive its Window tab, from a stray open box that box's Close.
    assert inside(WINDOW_TAB, *out["drive"]["clicks"][0])
    assert inside(MAILBOX_CLOSE, *out["box_open"]["clicks"][0])


def test_claim_mail_with_no_mail_ends_a_success_without_pressing_claim_all():
    o = run_child()["no_mail"]
    assert o["succeeded"] and o["screen"] == "main" and o["done"] == "no mail to claim"
    assert not any(inside(CLAIM_ALL, *c) for c in o["clicks"])
    assert "MailEmpty" in o["nodes"] and "MailClaimAll" not in o["nodes"]


def test_claim_mail_is_a_task_of_the_interface_and_the_global_mailbox_still_only_closes():
    interface = json.loads(strip(ROOT / "assets/interface.json"))
    assert {"name": "ClaimMail", "label": "$ClaimMail", "entry": "ClaimMail"} in interface["task"]
    mailbox = json.loads(strip(ROOT / "assets/resource/base/pipeline/popups.json"))["Mailbox"]
    assert mailbox["custom_action"] == "DismissShot" and "Claim" not in json.dumps(mailbox)


if __name__ == "__main__":
    child()
