"""GoHome (#365, spec 00 daily tasks): back to the main window from wherever the last task left the game.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen, taps and the back key
that move between them, and `dumpsys window` for the front package.
"""

import json

import numpy as np
from daily_child import GAME, ROOT, bind, game_class, inside, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)  # the bottom tab bar's Window tab
MAILBOX_CLOSE = (690, 530, 175, 45)
SETTINGS_RETURN = (500, 370, 280, 45)
TITLE_TAP = (540, 300, 200, 120)

# screen name -> tests/screens image (None: black, the game is not up)
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "sinners": "SinnersTab.png", "mailbox": "Mailbox.png",
           "settings": "SettingsMenu.png", "entry": "EntryNewRun.png", "title": "Title.png", "black": None}
# where a tap moves: (screens it works on, its box, the screen it shows)
TAPS = [(("drive", "sinners"), WINDOW_TAB, "main"), (("mailbox",), MAILBOX_CLOSE, "main"),
        (("settings",), SETTINGS_RETURN, "main"), (("title",), TITLE_TAP, "main")]


def child():
    """Run GoHome from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys, starts}}."""
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) if png else np.zeros((720, 1280, 3), np.uint8) for name, png in SCREENS.items()}

        def set(self, start, focus=GAME):
            self.screen, self.focus, self.clicks, self.keys, self.starts = start, focus, [], [], 0

        def screencap(self):
            return self.images["black" if self.focus != GAME else self.screen]

        def on_tap(self, x, y):
            self.screen = next((to for on, box, to in TAPS if self.screen in on and inside(box, x, y)), self.screen)
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen == "entry":  # the entry page's back: the Drive tab
                self.screen = "drive"
            return True

        def start_app(self, intent):
            self.starts += 1
            self.focus, self.screen = GAME, "title"
            return True

    game = Game()
    game.set("main")
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (start, focus) in {
        "drive": ("drive", GAME), "sinners": ("sinners", GAME), "main": ("main", GAME), "mailbox": ("mailbox", GAME),
        "settings": ("settings", GAME), "entry": ("entry", GAME), "closed": ("black", "com.android.launcher"),
        "stuck": ("entry", GAME),
    }.items():
        game.set(start, focus)
        if scenario == "stuck":  # the back key does nothing: it is pressed up to its limit, then the task fails
            game.on_key = lambda keycode: True
        override = {"GoHome": {"timeout": 4000}} if scenario == "stuck" else {}
        out[scenario] = {**result(tasker.post_task("GoHome", override).wait().get(), game, actions), "starts": game.starts}
    print(json.dumps(out))


def test_go_home_reaches_the_main_window_from_each_start():
    out = run_child(__file__)
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
    o = run_child(__file__)["closed"]
    assert o["succeeded"] and o["starts"] == 1 and o["keys"] == []
    assert "HomeGameAway" in o["nodes"] and "NavTitle" in o["nodes"] and o["nodes"][-1] == "HomeReached"


def test_go_home_fails_after_a_limited_number_of_back_keys_when_the_screen_never_changes():
    o = run_child(__file__)["stuck"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5
    assert o["nodes"][-1] == "GoHomeLost"


def test_go_home_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "GoHome", "label": "$GoHome", "entry": "GoHome"} in interface["task"]


if __name__ == "__main__":
    child()
