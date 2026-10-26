"""AssembleModules (#370): the real task in a child process (daily_child.py), on a model of the game: a screenshot per
screen and the taps that move between them.

A start away from the main window goes through GoHomeRun (spec 01); the task ends from the main window.
"""

import itertools
import json

from daily_child import ROOT, bind, game_class, inside, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)
ENK_BAR = (440, 640)
CONFIRM = (760, 534)
SCREENS = {"main": "MainWindowLater.png", "low": "MainWindowLowEnkephalin.synthetic.png", "panel": "EnkephalinPanel.png",
           "drive": "Drive.png", "entry": "EntryNewRun.png"}


def child():
    """Run AssembleModules from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) for name, png in SCREENS.items()}

        def set(self, start, confirm_to="low"):
            self.screen, self.confirm_to, self.clicks, self.keys = start, confirm_to, [], []

        def on_tap(self, x, y):
            if self.screen in ("main", "low") and (x, y) == ENK_BAR:
                self.screen = "panel"
            elif self.screen == "panel" and inside((650, 500, 220, 60), x, y):  # Confirm
                self.screen = self.confirm_to
            elif self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen == "entry":
                self.screen = "drive"
            elif keycode == 4 and self.screen == "panel":  # closes the window (live: unverified)
                self.screen = "main"
            return True

    game = Game()
    game.set("main")
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (start, confirm_to) in {
        "main": ("main", "low"), "low": ("low", "low"), "drive": ("drive", "low"), "entry": ("entry", "low"),
        "panel": ("panel", "low"), "no_drop": ("main", "main"),
    }.items():
        game.set(start, confirm_to)
        out[scenario] = result(tasker.post_task("AssembleModules", {"AssembleHub": {"timeout": 15000}}).wait().get(), game, actions)
    print(json.dumps(out))


def test_assembles_once_from_the_main_window_and_ends_there():
    o = run_child(__file__)["main"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "AssembleMain" in o["nodes"] and "AssemblePanel" in o["nodes"]
    assert o["clicks"] == [list(ENK_BAR), list(CONFIRM)] and o["keys"] == []  # >> not tapped: the window's own number is under 20
    assert "assembled" in o["done"]


def test_starts_on_gohome_from_another_page():
    out = run_child(__file__)
    for name in ("drive", "entry"):
        o = out[name]
        assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and "AssembleStart" in o["nodes"], name
        assert "assembled" in o["done"], name
    assert out["entry"]["keys"] == [4]  # the back key leaves the entry page, as GoHome alone


def test_under_a_module_of_enkephalin_nothing_is_opened_and_the_task_succeeds():
    o = run_child(__file__)["low"]
    assert o["succeeded"] and o["clicks"] == [] and "nothing to assemble" in o["done"]
    assert "AssemblePanel" not in o["nodes"]


def test_a_window_already_open_is_closed_by_gohome_first():
    o = run_child(__file__)["panel"]
    assert o["succeeded"] and o["keys"] == [4] and o["clicks"] == [list(ENK_BAR), list(CONFIRM)]
    assert "assembled" in o["done"]


def test_a_bar_that_does_not_drop_after_confirm_fails_the_task():
    o = run_child(__file__)["no_drop"]
    assert o["succeeded"] is False and o["nodes"][-1] != "TaskDone"


def test_fractions_reads_n_over_cap_left_to_right():
    import actions

    assert actions.fractions([("2 / 136", (200, 0, 1, 1)), ("22 / 136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("22/136 > 2/136", (0, 0, 1, 1))]) == [(22, 136), (2, 136)]
    assert actions.fractions([("Owned 104", (0, 0, 1, 1))]) == []


def panel(monkeypatch, tmp_path, frames):
    """AssemblePanel on a fake context: frames is what each screenshot shows, (Modules tab prompt read, fractions)."""
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
    assert taps == [actions.PANEL_CANCEL, "stop"]


def test_a_number_that_stops_reading_after_the_most_button_is_cancelled_not_confirmed(monkeypatch, tmp_path):
    # S1: >> tapped, then the tab or its numbers do not read: what Confirm would buy is not known.
    for after in [(True, []), (False, [(42, 136), (2, 136)])]:
        actions, context, taps = panel(monkeypatch, tmp_path, [(True, [(42, 136), (42, 136)]), after])
        assert actions.AssemblePanel().run(context, None) is False
        assert taps == [actions.ASSEMBLE_MAX, actions.PANEL_CANCEL, "stop"]


def test_the_modules_tab_is_confirmed_once_the_most_button_stops_changing(monkeypatch, tmp_path):
    frames = [(True, [(42, 136), (42, 136)]), (True, [(42, 136), (2, 136)])]
    actions, context, taps = panel(monkeypatch, tmp_path, frames)
    assert actions.AssemblePanel().run(context, None) is True
    assert taps == [actions.ASSEMBLE_MAX, actions.PANEL_CONFIRM] and actions.TASK["assemble"]["before"] == 42


def test_assemble_modules_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "AssembleModules", "label": "$AssembleModules", "entry": "AssembleModules"} in interface["task"]


if __name__ == "__main__":
    child()
