"""AssembleModules (#370): the real task in a child process (daily_child.py), on a model of the game: a screenshot per
screen and the taps that move between them.

A start away from the main window goes through GoHomeRun (spec 01); the task ends from the main window. Confirm leaves
the window open (live 2026-10-27, EnkephalinAssembled.png: the Enkephalin down, "Insufficient Enkephalin." where the prompt
was, Confirm greyed): the bot reads the drop there and closes the window with Cancel.
"""

import itertools
import json

from daily_child import ROOT, bind, game_class, inside, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)
ENK_BAR = (440, 640)
CONFIRM = (760, 534)
CANCEL = (520, 534)
MODULES_TAB = (505, 226)  # D7 (#362), live 720p
SCREENS = {"main": "MainWindowLater.png", "low": "MainWindowLowEnkephalin.synthetic.png", "panel": "EnkephalinPanel.png",
           "drive": "Drive.png", "entry": "EntryNewRun.png", "assembled": "EnkephalinAssembled.png",
           # live 2026-10-27: OCR reads the arrow between the two numbers as "4" (85/136465/136), or not at all (86/13666/136)
           "panel_four": "EnkephalinModulesArrowAsFour.png", "panel_none": "EnkephalinModulesNoArrow.png"}


def child():
    """Run AssembleModules from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
    actions, resource = load()
    from test_charge_enkephalin import lunacy_tab

    class Game(game_class()):
        images = {**{name: screen(png) for name, png in SCREENS.items()}, "lunacy": lunacy_tab(26)}

        def set(self, start, confirm_to="assembled", opens="panel"):
            self.screen, self.confirm_to, self.opens, self.clicks, self.keys = start, confirm_to, opens, [], []
            self.modules = opens if opens.startswith("panel") else "panel"  # the Modules tab this window shows

        def on_tap(self, x, y):
            if self.screen in ("main", "low") and (x, y) == ENK_BAR:
                self.screen = self.opens  # the window opens on the tab it was left on
            elif self.window() and (x, y) == MODULES_TAB:
                self.screen = self.modules
            elif self.window() and inside((650, 500, 220, 60), x, y):  # Confirm
                self.screen = self.confirm_to
            elif self.screen == "assembled" and inside((410, 500, 220, 60), x, y):  # Cancel closes the window
                self.screen = "low"
            elif self.window() and inside((410, 500, 220, 60), x, y):
                self.screen = "main"
            elif self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            return True

        def window(self):  # the Charge Enkephalin window before Confirm, on any tab
            return self.screen.startswith("panel") or self.screen == "lunacy"

        def on_key(self, keycode):
            if keycode == 4 and self.screen == "entry":
                self.screen = "drive"
            elif keycode == 4 and self.screen == "panel":  # closes the window (live: unverified)
                self.screen = "main"
            elif keycode == 4 and self.screen == "assembled":
                self.screen = "low"
            return True

    game = Game()
    game.set("main")
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (start, confirm_to, *opens) in {
        "main": ("main", "assembled"), "low": ("low", "assembled"), "drive": ("drive", "assembled"),
        "entry": ("entry", "assembled"), "panel": ("panel", "assembled"), "no_drop": ("main", "panel"),
        "on_lunacy": ("main", "assembled", "lunacy"), "closes": ("main", "low"),
        "arrow_as_four": ("main", "assembled", "panel_four"), "no_arrow": ("main", "assembled", "panel_none"),
    }.items():
        game.set(start, confirm_to, *opens)
        out[scenario] = result(tasker.post_task("AssembleModules", {"AssembleHub": {"timeout": 15000}}).wait().get(), game, actions)
    print(json.dumps(out))


ASSEMBLE = [list(ENK_BAR), list(MODULES_TAB), list(CONFIRM), list(CANCEL)]  # >> not tapped: the window's own number is under 20


def test_assembles_once_from_the_main_window_closes_the_window_and_ends_there():
    # live-1 F1: the window stays after Confirm; the Enkephalin it shows went down (25 -> 5 live, 22 -> 5 here): Cancel
    o = run_child(__file__)["main"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "AssembleMain" in o["nodes"] and "AssemblePanel" in o["nodes"]
    assert o["clicks"] == ASSEMBLE and o["keys"] == [] and o["screen"] == "low"
    assert "assembled" in o["done"] and "-> 5" in o["done"]


def test_a_window_that_closes_on_confirm_is_judged_from_the_bar():
    o = run_child(__file__)["closes"]  # not seen live: the bar on the main window shows the drop
    assert o["succeeded"] and o["clicks"] == [list(ENK_BAR), list(MODULES_TAB), list(CONFIRM)] and "assembled" in o["done"]


def test_starts_on_gohome_from_another_page():
    out = run_child(__file__)
    for name in ("drive", "entry"):
        o = out[name]
        assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "AssembleHome" in o["nodes"], name
        assert "assembled" in o["done"], name
    assert out["entry"]["keys"] == [4]  # the back key leaves the entry page, as GoHome alone


def test_under_a_module_of_enkephalin_nothing_is_opened_and_the_task_succeeds():
    o = run_child(__file__)["low"]
    assert o["succeeded"] and o["clicks"] == [] and "nothing to assemble" in o["done"]
    assert "AssemblePanel" not in o["nodes"]


def test_a_window_already_open_is_closed_by_gohome_first():
    o = run_child(__file__)["panel"]
    assert o["succeeded"] and o["keys"] == [4] and o["clicks"] == ASSEMBLE
    assert "assembled" in o["done"]


def test_a_window_that_opens_on_the_use_lunacy_tab_is_switched_to_modules_before_confirm():
    # D7 (#362): the window remembers its tab; the Modules tab is tapped first, so Confirm never lands on Use Lunacy.
    o = run_child(__file__)["on_lunacy"]
    assert o["succeeded"] and o["clicks"] == ASSEMBLE and "assembled" in o["done"]


def test_the_window_reads_however_ocr_takes_the_arrow_between_its_numbers():
    # live 2026-10-27 (H1): one OCR over "67/136 > 47/136" read "67/136447/136", a single fraction: no Modules tab, stop
    out = run_child(__file__)
    for name, before in (("arrow_as_four", 85), ("no_arrow", 86)):
        o = out[name]
        assert o["succeeded"] and o["nodes"][-1] == "TaskDone", name
        assert o["clicks"] == [list(ENK_BAR), list(MODULES_TAB), [805, 328], list(CONFIRM), list(CANCEL)], name
        assert f"Enkephalin {before} -> 5" in o["done"], name


def test_a_confirm_that_never_takes_fails_the_task():
    o = run_child(__file__)["no_drop"]  # the prompt stays, the Enkephalin with it: Confirm again, ASSEMBLE_TRIES times
    assert o["succeeded"] is False and o["nodes"][-1] != "TaskDone"
    assert o["clicks"].count(list(CONFIRM)) == 3


def test_fractions_reads_n_over_cap_left_to_right():
    import actions

    assert actions.fractions([("2 / 136", (200, 0, 1, 1)), ("22 / 136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("22/136 > 2/136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("Owned 104", (0, 0, 1, 1))]) == []


def panel(monkeypatch, tmp_path, frames):
    """AssemblePanel on a fake context: frames is what each screenshot shows, (Modules tab prompt read, fractions); a
    run takes one before it taps the Modules tab, the next after."""
    from unittest.mock import MagicMock

    import actions

    shots = iter(frames)
    taps = []
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    monkeypatch.setattr(actions, "screen", lambda context: next(shots))
    monkeypatch.setattr(actions, "too_many", lambda context, image: False)
    monkeypatch.setattr(actions, "on_modules_tab", lambda context, image: image[0])
    monkeypatch.setattr(actions, "read_fractions", lambda context, image, node: image[1])
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    monkeypatch.setattr(actions, "stop", lambda context, reason, **kw: taps.append("stop") or False)
    actions.TASK.clear()
    actions.TASK.update(runs=0, done=None)
    return actions, MagicMock(), taps


def test_a_window_not_on_its_modules_tab_is_cancelled_and_never_confirmed(monkeypatch, tmp_path):
    # S1: the Use Lunacy tab shows the Enkephalin before and after too ("n / cap" twice); Confirm there spends Lunacy.
    actions, context, taps = panel(monkeypatch, tmp_path, itertools.repeat((False, [(22, 136), (48, 136)])))
    results = [actions.AssemblePanel().run(context, None) for _ in range(actions.ASSEMBLE_TRIES)]
    assert results == [True] * (actions.ASSEMBLE_TRIES - 1) + [False]  # the window may still be opening: looked at again
    # the stop procedure's evidence shows the window itself, so it comes before Cancel (live-3 H1)
    assert taps == [actions.MODULES_TAB] * actions.ASSEMBLE_TRIES + ["stop", actions.PANEL_CANCEL]


def test_a_number_that_stops_reading_after_the_most_button_is_cancelled_not_confirmed(monkeypatch, tmp_path):
    # S1: >> tapped, then the tab or its numbers do not read: what Confirm would buy is not known.
    for after in [(True, []), (False, [(42, 136), (2, 136)])]:
        actions, context, taps = panel(monkeypatch, tmp_path, [(False, []), (True, [(42, 136), (42, 136)]), after])
        assert actions.AssemblePanel().run(context, None) is False
        assert taps == [actions.MODULES_TAB, actions.ASSEMBLE_MAX, "stop", actions.PANEL_CANCEL]


def test_the_modules_tab_is_confirmed_once_the_most_button_stops_changing(monkeypatch, tmp_path):
    frames = [(False, []), (True, [(42, 136), (42, 136)]), (True, [(42, 136), (2, 136)])]
    actions, context, taps = panel(monkeypatch, tmp_path, frames)
    assert actions.AssemblePanel().run(context, None) is True
    assert taps == [actions.MODULES_TAB, actions.ASSEMBLE_MAX, actions.PANEL_CONFIRM] and actions.TASK["assemble"]["before"] == 42


def test_assemble_modules_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "AssembleModules", "label": "$AssembleModules", "entry": "AssembleModules"} in interface["task"]



def test_after_confirm_the_drop_in_the_open_window_ends_it_with_cancel(monkeypatch, tmp_path):
    # live-1 F1 (EnkephalinAssembled.png): no prompt ("Insufficient Enkephalin." in its place), 5 / 136 where 25 was
    actions, context, taps = panel(monkeypatch, tmp_path, [(False, [(5, 136), (5, 136)])])
    actions.TASK["assemble"] = {"reads": 0, "confirms": 1, "before": 25}
    assert actions.AssemblePanel().run(context, None) is True
    assert taps == [actions.PANEL_CANCEL] and actions.TASK["assemble"]["end"] == "Enkephalin 25 -> 5, assembled"


def test_after_confirm_a_window_with_nothing_changed_yet_is_looked_at_again(monkeypatch, tmp_path):
    # Neither the prompt nor a drop: the window is still answering the tap; looked at again, then the stop procedure
    frames = itertools.repeat((False, [(25, 136), (5, 136)]))
    actions, context, taps = panel(monkeypatch, tmp_path, frames)
    actions.TASK["assemble"] = {"reads": 0, "confirms": 1, "before": 25}
    results = [actions.AssemblePanel().run(context, None) for _ in range(actions.ASSEMBLE_TRIES)]
    assert results == [True] * (actions.ASSEMBLE_TRIES - 1) + [False]
    assert taps == ["stop", actions.PANEL_CANCEL]


if __name__ == "__main__":
    child()
