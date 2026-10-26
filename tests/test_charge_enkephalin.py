"""ChargeEnkephalin (#373): the real task in a child process (daily_child.py), on a model of the game: a screenshot per
screen and the taps that move between them.

The Use Lunacy tab is EnkephalinLunacy.png (live 2026-10-27: price 104 at Daily Count 3/10) with its price and Daily
Count painted over and the model's drawn in. No Confirm was pressed for it (no Lunacy spent), so what the tab shows
after one, and at 10/10, is the model's guess.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
from daily_child import ROOT, bind, game_class, load, result, run_child, screen

ENK_BAR, TAB, CONFIRM, CANCEL = (440, 640), (639, 226), (760, 534), (520, 534)  # TAB: Use Lunacy (D7, live 720p)
PRICES = (26, 52, 78, 104, 130, 156, 182, 208, 234, 260)


def lunacy_tab(used, price=None):
    """EnkephalinLunacy.png at Daily Count used/10 showing price (the table's at used when None)."""
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(ROOT / "tests" / "screens" / "EnkephalinLunacy.png").convert("RGB")
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=30)
    for box, at, text in [((582, 274, 645, 316), (590, 278), str(price or PRICES[min(used, len(PRICES) - 1)])),
                          ((700, 304, 795, 342), (712, 306), f"{used}/10")]:
        draw.rectangle(box, fill=im.getpixel((box[0] - 4, box[1] + 4)))
        draw.text(at, text, fill=(235, 220, 200), font=font)
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
        images = {"main": screen("MainWindowLater.png"), "modules": screen("EnkephalinModules.png"),
                  "boxes": screen("EnkephalinBoxes.png"), **{f"lunacy{n}": lunacy_tab(n) for n in range(11)},
                  "lunacy0_27": lunacy_tab(0, 27)}

        def set(self, bought=0, price=None, confirm_works=True, tab="lunacy", step=1):
            """bought: the day's charges made so far (Daily Count); price: the price shown whatever bought says (a wrong
            one); tab: what the Use Lunacy tab's tap shows ("modules": the tap did nothing)."""
            self.screen, self.clicks, self.keys = "main", [], []
            self.bought, self.price, self.confirm_works, self.tab, self.step = bought, price, confirm_works, tab, step

        def lunacy(self):
            return f"lunacy{self.bought}" + (f"_{self.price}" if self.price else "")

        def on_tap(self, x, y):
            if self.screen == "main" and (x, y) == ENK_BAR:
                self.screen = "modules"  # live 2026-10-27: the window always opens on Modules
            elif self.screen == "modules" and (x, y) == TAB:
                self.screen = self.lunacy() if self.tab == "lunacy" else self.tab
            elif self.screen.startswith("lunacy") and (x, y) == CONFIRM and self.confirm_works:
                self.bought = min(self.bought + self.step, 10)  # step 1; 2 is a count that jumped
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
        "two_after_nine": (2, {"bought": 9}),
        "off_table": (2, {"price": 27}),
        "skips_a_price": (3, {"step": 2}),
        "confirm_does_nothing": (2, {"confirm_works": False}),
        "tab_never_opens": (2, {"tab": "modules"}),
        "boxes_tab": (2, {"tab": "boxes"}),  # the same Recharge prompt, no Daily Count
    }.items():
        actions.ROOT = settings(count)  # the settings, and the stop procedure's evidence and log
        game.set(**state)
        out[scenario] = result(tasker.post_task("ChargeEnkephalin", {"ChargeHub": {"timeout": 25000}}).wait().get(), game, actions)
    for shown in ("modules", "lunacy0"):  # the prompt: the Modules tab's own line is not it
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


def test_the_count_is_this_runs_whatever_was_charged_earlier_today():
    # D5 (#362): one charged by hand at 26; this run charges two more, 52 and 78, and checks 104 follows.
    o = run_child(__file__)["two_one_by_hand"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "2 charged now" in o["done"]


def test_the_tenth_charge_of_the_day_ends_the_task_at_10_of_10():
    # D5 (#362): 9/10 is charged, then 10/10 shows: the day is done, a success.
    o = run_child(__file__)["two_after_nine"]
    assert o["succeeded"] and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert "1 charged now" in o["done"] and "10 charges are done" in o["done"]


def test_a_price_off_the_table_is_cancelled_and_fails_the_task():
    o = run_child(__file__)["off_table"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CANCEL)


def test_a_daily_count_that_skips_one_after_a_confirm_is_cancelled_and_fails_the_task():
    o = run_child(__file__)["skips_a_price"]
    assert o["succeeded"] is False and o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)


def test_a_confirm_that_did_nothing_never_confirms_the_same_price_twice():
    o = run_child(__file__)["confirm_does_nothing"]
    assert o["succeeded"] is False and o["clicks"].count(list(CONFIRM)) == 1


def test_a_tab_that_never_shows_its_price_is_never_confirmed():
    o = run_child(__file__)["tab_never_opens"]
    assert o["succeeded"] is False and list(CONFIRM) not in o["clicks"] and o["clicks"][-1] == list(CANCEL)


def test_the_use_boxes_tab_has_the_same_prompt_but_no_daily_count_and_is_never_confirmed():
    o = run_child(__file__)["boxes_tab"]
    assert o["succeeded"] is False and list(CONFIRM) not in o["clicks"] and o["clicks"][-1] == list(CANCEL)


def test_the_recharge_prompt_is_read_on_the_lunacy_tab_and_not_on_the_modules_tab():
    out = run_child(__file__)
    assert out["prompt_lunacy0"] is True and out["prompt_modules"] is False


def test_charge_enkephalin_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ChargeEnkephalin", "label": "$ChargeEnkephalin", "entry": "ChargeEnkephalin"} in interface["task"]


if __name__ == "__main__":
    child()
