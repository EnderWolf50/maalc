"""ChargeEnkephalin (#373): the real task in a child process (daily_child.py), on a model of the game: a screenshot per
screen and the taps that move between them.

No capture of the Use Lunacy tab exists yet (AGENTS.md: no Lunacy is spent without the user's word), so its screens are
EnkephalinPanel.png with the Modules tab's body painted over and a Recharge prompt and a price drawn in; where the real
tab shows them is unverified, so these tests prove the task's decisions, not the reading.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
from daily_child import ROOT, bind, game_class, load, result, run_child, screen

ENK_BAR, TAB, CONFIRM, CANCEL = (440, 640), (640, 225), (760, 534), (520, 534)
PRICES = (26, 52, 78, 104, 130, 156, 182, 208, 234, 260)


def lunacy_tab(price):
    """EnkephalinPanel.png with its Modules tab's body painted over, a Recharge prompt and the price drawn in."""
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(ROOT / "tests" / "screens" / "EnkephalinPanel.png").convert("RGB")
    draw = ImageDraw.Draw(im)
    draw.rectangle((380, 300, 900, 515), fill=im.getpixel((420, 440)))  # the Modules tab's body
    font = ImageFont.load_default(size=34)
    draw.text((430, 465), "Recharge 20 Enkephalin?", fill=(30, 20, 10), font=font)
    draw.text((590, 370), str(price), fill=(30, 20, 10), font=font)
    return np.ascontiguousarray(np.array(im)[:, :, ::-1])


def child():
    """Run ChargeEnkephalin in each scenario; print one JSON line {scenario: {succeeded, nodes, clicks, done}}."""
    actions, resource = load()
    from test_settings import VALID

    def settings(count):
        folder = Path(tempfile.mkdtemp())
        (folder / "config").mkdir()
        (folder / "config" / "settings.json").write_text(json.dumps({**VALID, "charge_enkephalin": {"count": count}}))
        return folder

    class Game(game_class()):
        images = {"main": screen("MainWindowLater.png"), "modules": screen("EnkephalinPanel.png"),
                  **{f"lunacy{p}": lunacy_tab(p) for p in (*PRICES, 27)}}

        def set(self, bought=0, price=None, confirm_works=True, tab_works=True, step=1):
            """bought: the day's charges made so far; price: the price shown whatever bought says (a wrong one)."""
            self.screen, self.clicks, self.keys = "main", [], []
            self.bought, self.price, self.confirm_works, self.tab_works, self.step = bought, price, confirm_works, tab_works, step

        def lunacy(self):
            return f"lunacy{self.price or PRICES[min(self.bought, len(PRICES) - 1)]}"

        def on_tap(self, x, y):
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

        def on_key(self, keycode):
            if keycode == 4 and self.screen != "main":
                self.screen = "main"
            return True

    game = Game()
    game.set()
    tasker = bind(resource, game)
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
        out[scenario] = result(tasker.post_task("ChargeEnkephalin", {"ChargeHub": {"timeout": 25000}}).wait().get(), game, actions)
    for shown in ("modules", "lunacy26"):  # the prompt: the Modules tab's own line is not it
        game.set()
        game.screen = shown
        node = tasker.post_task("ChargePrompt", {"ChargePrompt": {"next": [], "timeout": 3000}}).wait().get().nodes[0]
        out[f"prompt_{shown}"] = bool(node.recognition and node.recognition.hit)
    print(json.dumps(out))


def taps(*points):
    return [list(p) for p in points]


def test_zero_charges_touch_nothing_not_even_the_window():
    o = run_child(__file__)["zero"]
    assert o["succeeded"] and o["clicks"] == [] and "Lunacy left alone" in o["done"]
    assert "ChargeHome" not in o["nodes"] and "ChargePanel" not in o["nodes"]


def test_two_charges_from_a_fresh_day_confirm_26_and_52_and_cancel_at_the_third_price():
    o = run_child(__file__)["two_from_none"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone"
    assert o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "2 charged now" in o["done"]


def test_a_charge_made_by_hand_counts_toward_the_days_total():
    o = run_child(__file__)["two_one_by_hand"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "1 charged now" in o["done"]


def test_a_day_already_charged_confirms_nothing():
    o = run_child(__file__)["two_already"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CANCEL) and "0 charged now" in o["done"]


def test_a_price_off_the_table_is_cancelled_and_fails_the_task():
    o = run_child(__file__)["off_table"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CANCEL)


def test_a_price_that_skips_one_after_a_confirm_is_cancelled_and_fails_the_task():
    o = run_child(__file__)["skips_a_price"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)


def test_a_confirm_that_did_nothing_never_confirms_the_same_price_twice():
    o = run_child(__file__)["confirm_does_nothing"]
    assert o["succeeded"] is False and o["clicks"].count(list(CONFIRM)) == 1


def test_a_tab_that_never_shows_its_price_is_never_confirmed():
    o = run_child(__file__)["tab_never_opens"]
    assert o["succeeded"] is False and list(CONFIRM) not in o["clicks"] and o["clicks"][-1] == list(CANCEL)


def test_the_recharge_prompt_is_read_on_the_lunacy_tab_and_not_on_the_modules_tab():
    out = run_child(__file__)
    assert out["prompt_lunacy26"] is True and out["prompt_modules"] is False


def test_charge_enkephalin_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ChargeEnkephalin", "label": "$ChargeEnkephalin", "entry": "ChargeEnkephalin"} in interface["task"]


if __name__ == "__main__":
    child()
