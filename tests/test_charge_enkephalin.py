"""ChargeEnkephalin (#373): the real task on the repo's resource bundle, in MaaFramework and its OCR, on a small model of
the game: a screenshot per screen and the taps that move between them. As test_assemble_modules.py, the task runs in a
child process (this file run as a script): the pytest process holds MaaFramework in AgentServer mode.

No capture of the Use Lunacy tab exists yet (AGENTS.md: no Lunacy is spent without the user's word), so its screens are
EnkephalinPanel.png with the Modules tab's body painted over and a Recharge prompt and a price drawn in; where the real
tab shows them is unverified, so these tests prove the task's decisions, not the reading.
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
sys.path.insert(0, str(ROOT / "tests"))

ENK_BAR, TAB, CONFIRM, CANCEL = (440, 640), (640, 225), (760, 534), (520, 534)
PRICES = (26, 52, 78, 104, 130, 156, 182, 208, 234, 260)


def child():
    """Run ChargeEnkephalin in each scenario; print one JSON line {scenario: {succeeded, nodes, clicks, done}}."""
    from maa.controller import CustomController
    from maa.resource import Resource
    from maa.tasker import Tasker
    from PIL import Image, ImageDraw, ImageFont

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions
    from test_settings import VALID

    def settings(count):
        folder = Path(tempfile.mkdtemp())
        (folder / "config").mkdir()
        (folder / "config" / "settings.json").write_text(json.dumps({**VALID, "charge_enkephalin": {"count": count}}))
        return folder

    def read(png):
        return np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / png).convert("RGB"))[:, :, ::-1])

    def lunacy_tab(price):
        im = Image.open(ROOT / "tests" / "screens" / "EnkephalinPanel.png").convert("RGB")
        draw = ImageDraw.Draw(im)
        draw.rectangle((380, 300, 900, 515), fill=im.getpixel((420, 440)))  # the Modules tab's body
        font = ImageFont.load_default(size=34)
        draw.text((430, 465), "Recharge 20 Enkephalin?", fill=(30, 20, 10), font=font)
        draw.text((590, 370), str(price), fill=(30, 20, 10), font=font)
        return np.ascontiguousarray(np.array(im)[:, :, ::-1])

    images = {"main": read("MainWindowLater.png"), "modules": read("EnkephalinPanel.png"),
              **{f"lunacy{p}": lunacy_tab(p) for p in (*PRICES, 27)}}

    class Game(CustomController):
        def __init__(self):
            super().__init__()

        def set(self, bought=0, price=None, confirm_works=True, tab_works=True, step=1):
            """bought: the day's charges made so far; price: the price shown whatever bought says (a wrong one)."""
            self.screen, self.clicks, self.keys = "main", [], []
            self.bought, self.price, self.confirm_works, self.tab_works, self.step = bought, price, confirm_works, tab_works, step

        def lunacy(self):
            return f"lunacy{self.price or PRICES[min(self.bought, len(PRICES) - 1)]}"

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            if self.screen == "main" and (x, y) == ENK_BAR:
                self.screen = "modules"
            elif self.screen == "modules" and (x, y) == TAB and self.tab_works:
                self.screen = self.lunacy()
            elif self.screen.startswith("lunacy") and (x, y) == CONFIRM and self.confirm_works:
                self.bought += self.step  # 1; 2 is a table that jumped
                self.screen = "main"
            elif self.screen != "main" and (x, y) == CANCEL:
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
            if keycode == 4 and self.screen != "main":
                self.screen = "main"
            return True

        def shell(self, cmd, timeout):
            return "  mCurrentFocus=Window{1a2b u0 com.ProjectMoon.LimbusCompany/com.unity3d.player.UnityPlayerActivity}"

        def __getattr__(self, name):
            return lambda *args: True

    game = Game()
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name, cls in (("StopTask", actions.StopTask), ("DismissShot", actions.DismissShot), ("TaskStart", actions.TaskStart),
                      ("ChargeStart", actions.ChargeStart), ("ChargeMain", actions.ChargeMain),
                      ("ChargePanel", actions.ChargePanel), ("GoHomeRun", actions.GoHomeRun),
                      ("AcceptUpdate", actions.AcceptUpdate), ("AcceptTerms", actions.AcceptTerms),
                      ("ConfirmDownload", actions.ConfirmDownload), ("Halt", actions.Halt)):
        resource.register_custom_action(name, cls())
    resource.register_custom_recognition("GameAway", actions.GameAway())
    resource.register_custom_recognition("HomeText", actions.HomeText())
    resource.register_custom_recognition("DoneFlag", actions.DoneFlag())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    for scenario, (count, state) in {
        "zero": (0, {}),
        "two_from_none": (2, {}),
        "two_one_by_hand": (2, {"bought": 1}),
        "two_already": (2, {"bought": 2}),
        "off_table": (2, {"price": 27}),
        "skips_a_price": (3, {"step": 2}),
        "confirm_does_nothing": (2, {"confirm_works": False}),
        "tab_never_opens": (2, {"tab_works": False}),
    }.items():
        actions.ROOT = settings(count)  # the settings, and the stop procedure's evidence and log
        game.set(**state)
        try:
            detail = tasker.post_task("ChargeEnkephalin", {"ChargeHub": {"timeout": 25000}}).wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "done": actions.TASK["done"]}
        except Exception:
            out["error"] = traceback.format_exc()
    for screen in ("modules", "lunacy26"):  # the prompt: the Modules tab's own line is not it
        game.set()
        game.screen = screen
        node = tasker.post_task("ChargePrompt", {"ChargePrompt": {"next": [], "timeout": 3000}}).wait().get().nodes[0]
        out[f"prompt_{screen}"] = bool(node.recognition and node.recognition.hit)
    print(json.dumps(out))


@functools.cache
def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=900, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def taps(*points):
    return [list(p) for p in points]


def test_zero_charges_touch_nothing_not_even_the_window():
    o = run_child()["zero"]
    assert o["succeeded"] and o["clicks"] == [] and "Lunacy left alone" in o["done"]
    assert "ChargeHome" not in o["nodes"] and "ChargePanel" not in o["nodes"]


def test_two_charges_from_a_fresh_day_confirm_26_and_52_and_cancel_at_the_third_price():
    o = run_child()["two_from_none"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone"
    assert o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "2 charged now" in o["done"]


def test_a_charge_made_by_hand_counts_toward_the_days_total():
    o = run_child()["two_one_by_hand"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "1 charged now" in o["done"]


def test_a_day_already_charged_confirms_nothing():
    o = run_child()["two_already"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CANCEL) and "0 charged now" in o["done"]


def test_a_price_off_the_table_is_cancelled_and_fails_the_task():
    o = run_child()["off_table"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CANCEL)


def test_a_price_that_skips_one_after_a_confirm_is_cancelled_and_fails_the_task():
    o = run_child()["skips_a_price"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)


def test_a_confirm_that_did_nothing_never_confirms_the_same_price_twice():
    o = run_child()["confirm_does_nothing"]
    assert o["succeeded"] is False and o["clicks"].count(list(CONFIRM)) == 1


def test_a_tab_that_never_shows_its_price_is_never_confirmed():
    o = run_child()["tab_never_opens"]
    assert o["succeeded"] is False and list(CONFIRM) not in o["clicks"] and o["clicks"][-1] == list(CANCEL)


def test_the_recharge_prompt_is_read_on_the_lunacy_tab_and_not_on_the_modules_tab():
    out = run_child()
    assert out["prompt_lunacy26"] is True and out["prompt_modules"] is False


def test_charge_enkephalin_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ChargeEnkephalin", "label": "$ChargeEnkephalin", "entry": "ChargeEnkephalin"} in interface["task"]


if __name__ == "__main__":
    child()
