"""ChargeEnkephalin (#373; its count the day's target Daily Count, #429): the real task in a child process
(daily_child.py), on a model of the game: a screenshot per screen and the taps that move between them.

The Use Lunacy tab is EnkephalinLunacy.png (live 2026-10-27: price 104 at Daily Count 3/10) with its price and Daily
Count painted over and the model's drawn in. No Confirm was pressed for it (no Lunacy spent), so what the tab shows
after one, and at 10/10, is the model's guess.

The scenarios are the task's paths through its pipeline: a target of 0 (no window opened), the window that closes after
each Confirm, the one that stays open, the Use Boxes tab. Each decision of the panel is tested in process below (#641).
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from daily_child import ROOT, bind, game_class, interface as interface_json, load, result, run_child, screen
from test_settings import VALID
from agent_patch import patch_all, rebind

if __name__ != "__main__":  # as test_luxcavation.py: the fixtures are test_actions's
    import actions
    import daily_actions
    from test_actions import clock, context  # noqa: F401 (the fake Maa context the in-process tests use)

ENK_BAR, TAB, CONFIRM, CANCEL = (440, 640), (639, 226), (760, 534), (520, 534)  # TAB: Use Lunacy (D7, live 720p)
PRICES = (26, 52, 78, 104, 130, 156, 182, 208, 234, 260)


def lunacy_tab(used):
    """EnkephalinLunacy.png at Daily Count used/10 showing the table's price at used."""
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(ROOT / "tests" / "screens" / "EnkephalinLunacy.png").convert("RGB")
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=30)
    for box, at, text in [((582, 274, 645, 316), (590, 278), str(PRICES[min(used, len(PRICES) - 1)])),
                          ((700, 304, 795, 342), (712, 306), f"{used}/10")]:
        draw.rectangle(box, fill=im.getpixel((box[0] - 4, box[1] + 4)))
        draw.text(at, text, fill=(235, 220, 200), font=font)
    return np.ascontiguousarray(np.array(im)[:, :, ::-1])


def child():
    """Run ChargeEnkephalin in each scenario; print one JSON line {scenario: {succeeded, nodes, clicks, done}}."""
    actions, resource = load()

    def settings(count):
        folder = Path(tempfile.mkdtemp())
        (folder / "config").mkdir()
        (folder / "config" / "settings.json").write_text(json.dumps({**VALID, "charge_enkephalin": {"count": count}}))
        return folder

    class Game(game_class()):
        images = {"main": screen("MainWindowLater.png"), "modules": screen("EnkephalinModules.png"),
                  "boxes": screen("EnkephalinBoxes.png"), **{f"lunacy{n}": lunacy_tab(n) for n in range(11)}}

        def set(self, bought=0, tab="lunacy", stays=False):
            """bought: the day's charges made so far (Daily Count); tab: what the Use Lunacy tab's tap shows; stays: the
            window stays open after Confirm (spec 01: live for Modules; unverified for Lunacy)."""
            self.screen, self.clicks, self.keys = "main", [], []
            self.bought, self.tab, self.stays = bought, tab, stays

        def lunacy(self):
            return f"lunacy{self.bought}"

        def on_tap(self, x, y):
            if self.screen == "main" and (x, y) == ENK_BAR:
                self.screen = "modules"  # live 2026-10-27: the window always opens on Modules
            elif self.screen == "modules" and (x, y) == TAB:
                self.screen = self.lunacy() if self.tab == "lunacy" else self.tab
            elif self.screen.startswith("lunacy") and (x, y) == CONFIRM:
                self.bought = min(self.bought + 1, 10)
                self.screen = self.lunacy() if self.stays else "main"
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
        # Confirm leaves the window open: ChargePanel looks at near the same screen 7 times, past the watchdog's SAME_SCREEN
        "window_stays": (10, {"stays": True, "bought": 4}),
        "boxes_tab": (2, {"tab": "boxes"}),  # the same Recharge prompt, no Daily Count
    }.items():
        rebind("ROOT", settings(count))  # the settings, and the stop procedure's evidence and log
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


def test_a_target_of_two_on_a_fresh_day_confirms_26_and_52_and_cancels_at_2_of_10():
    o = run_child(__file__)["two_from_none"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone"
    assert o["clicks"] == taps(ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CONFIRM, ENK_BAR, TAB, CANCEL)
    assert o["done"] == "Daily Count 2/10, target 2: 2 charged"


def test_charges_in_a_window_that_stays_open_are_not_a_stuck_screen_and_end_at_10_of_10():
    # The same picture over and over, only its price and Daily Count moving: the watchdog's same-screen count must not take
    # it (ChargePanel is in actions.PASS_NODES). Six charges from 4/10, then 10/10 shows: the day is done, a success.
    o = run_child(__file__)["window_stays"]
    assert o["succeeded"] and o["clicks"].count(list(CONFIRM)) == 6 and o["clicks"].count(list(CANCEL)) == 1
    assert o["done"] == "Daily Count 10/10, target 10: 6 charged" and o["nodes"].count("ChargePanel") > 5


def test_the_use_boxes_tab_has_the_same_prompt_but_no_daily_count_and_is_never_confirmed():
    o = run_child(__file__)["boxes_tab"]
    assert o["succeeded"] and list(CONFIRM) not in o["clicks"] and o["clicks"][-1] == list(CANCEL)
    assert "nothing charged" in o["done"]


def test_the_recharge_prompt_is_read_on_the_lunacy_tab_and_not_on_the_modules_tab():
    out = run_child(__file__)
    assert out["prompt_lunacy0"] is True and out["prompt_modules"] is False


def test_charge_enkephalin_is_a_task_of_the_interface():
    interface = interface_json()
    assert {"name": "ChargeEnkephalin", "label": "$ChargeEnkephalin", "entry": "ChargeEnkephalin"} in interface["task"]


# ChargePanel in process (#641): the branches the scenarios above once ran in MaaFramework, test_actions.py's
# fake context around them. A Tab is the Use Lunacy tab as the panel reads it: its price and Daily Count, the Recharge prompt.

class Tab:
    """The Use Lunacy tab at Daily Count `used`/10, showing `price` (the table's at used when None). confirm_works: a
    Confirm moves the count on by `step`; readable: the prompt and the Daily Count read (False: the tab never showed)."""

    def __init__(self, context, monkeypatch, used=0, price=None, confirm_works=True, step=1, readable=True):
        self.used, self.price, self.confirm_works, self.step, self.readable = used, price, confirm_works, step, readable
        self.taps, self.stops = [], []
        patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # the panel's state, gone after the test
        patch_all(monkeypatch, "tap", self.tap)
        patch_all(monkeypatch, "ocr_texts", self.ocr)
        patch_all(monkeypatch, "stop", lambda context, reason, **kw: self.stops.append(reason) or False)
        context.run_recognition.side_effect = lambda node, image: SimpleNamespace(hit=self.readable) if node == "ChargePrompt" else None

    def tap(self, context, x, y, wait=1.0):
        self.taps.append((x, y))
        if (x, y) == CONFIRM and self.confirm_works:
            self.used = min(self.used + self.step, 10)

    def ocr(self, context, image, node):
        price = self.price or PRICES[min(self.used, len(PRICES) - 1)]
        return {"ChargePrice": [str(price)], "ChargeCount": [f"{self.used}/10"]}.get(node, [])


def panel(context, count, passes):
    """ChargePanel `passes` times on a task of target `count`, as the hub hands the open window over; the returns."""
    actions.TASK["charge"] = {"count": count, "reads": 0, "opened": 0, "charged": 0}
    return [daily_actions.ChargePanel().run(context, None) for _ in range(passes)]


@pytest.mark.parametrize("state, count, passes, steps, clicks, end", [
    # #429: one charged by hand at 26; a target of three charges two more, 52 and 78, not 52, 78 and 104
    ({"used": 1}, 3, 3, [True] * 3, [TAB, CONFIRM, TAB, CONFIRM, TAB, CANCEL], "Daily Count 3/10, target 3: 2 charged"),
    ({"used": 3}, 3, 1, [True], [TAB, CANCEL], "Daily Count 3/10, target 3: nothing to charge"),  # met by hand
    ({"used": 5}, 2, 1, [True], [TAB, CANCEL], "Daily Count 5/10, target 2: nothing to charge"),
    ({"used": 9}, 10, 2, [True] * 2, [TAB, CONFIRM, TAB, CANCEL], "Daily Count 10/10, target 10: 1 charged"),  # the day's last
    # #429 item 4: the tab never read, so the day's charges are not known: none made, a success; three reads, then Cancel
    ({"readable": False}, 2, 3, [True] * 3, [TAB, TAB, TAB, CANCEL],
     "the Use Lunacy tab's prompt and Daily Count did not read, target 2: nothing charged"),
])
def test_the_panel_charges_up_to_the_target_and_ends_the_task_a_success(context, monkeypatch, state, count, passes, steps, clicks, end):
    tab = Tab(context, monkeypatch, **state)
    assert panel(context, count, passes) == steps and tab.taps == clicks and tab.stops == []
    assert actions.TASK["charge"]["end"] == end


@pytest.mark.parametrize("state, count, passes, clicks, why", [
    ({"price": 27}, 2, 1, [TAB, CANCEL], "the price 27 is not the table's 26 at Daily Count 0/10"),  # off the table
    ({"step": 2}, 3, 2, [TAB, CONFIRM, TAB, CANCEL],  # the count jumped a price
     "the Daily Count is 2/10 after the last Confirm, expected 1/10"),
    ({"confirm_works": False}, 2, 2, [TAB, CONFIRM, TAB, CANCEL],  # never the same price confirmed twice
     "the Daily Count is 0/10 after the last Confirm, expected 1/10"),
])
def test_a_tab_that_is_not_what_the_task_expects_is_cancelled_and_fails_the_task(context, monkeypatch, state, count, passes, clicks, why):
    tab = Tab(context, monkeypatch, **state)
    assert panel(context, count, passes)[-1] is False and tab.taps == clicks and tab.stops == [why]


def test_a_tab_that_stops_reading_after_a_confirm_fails_the_task(context, monkeypatch):
    tab = Tab(context, monkeypatch)
    steps = panel(context, 2, 1)
    tab.readable = False  # after the Confirm the prompt and the Daily Count read no more
    steps += [daily_actions.ChargePanel().run(context, None) for _ in range(3)]
    assert steps == [True] * 3 + [False] and tab.taps == [TAB, CONFIRM, TAB, TAB, TAB, CANCEL]
    assert tab.stops == ["the Use Lunacy tab's prompt and Daily Count could not be read after a Confirm"]


def test_a_cancel_that_never_closes_the_window_stops_the_task_after_a_few_taps(context, monkeypatch):
    # Done at the third price, the window stays: ChargePanel is exempt from the same-screen watchdog, so it bounds itself.
    tab = Tab(context, monkeypatch, used=2)
    assert panel(context, 2, 1 + daily_actions.CHARGE_TRIES + 1) == [True] * (1 + daily_actions.CHARGE_TRIES) + [False]
    assert tab.taps.count(CANCEL) == 1 + daily_actions.CHARGE_TRIES  # the deciding one, then CHARGE_TRIES more
    assert tab.stops == [f"the Charge Enkephalin window stayed open after {daily_actions.CHARGE_TRIES} more Cancels"]


if __name__ == "__main__":
    child()
