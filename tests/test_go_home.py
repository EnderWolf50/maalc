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
            self.screen, self.focus, self.clicks, self.keys, self.starts, self.stops = start, focus, [], [], 0, 0

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

        def stop_app(self, intent):
            self.stops += 1
            self.focus = "com.android.launcher"
            return True

    game = Game()
    game.set("main")
    # MaaFramework's Linux build (CI) does not pass post_shell to a custom controller ("Shell is not supported for this
    # controller type"), so foreground() reads None there and GameAway never hits: read the model's dumpsys directly.
    actions.foreground = lambda context: actions.recovery.focused_package(game.shell("dumpsys window", 0))
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (start, focus) in {
        "drive": ("drive", GAME), "sinners": ("sinners", GAME), "main": ("main", GAME), "mailbox": ("mailbox", GAME),
        "settings": ("settings", GAME), "entry": ("entry", GAME), "closed": ("black", "com.android.launcher"),
        "stuck": ("entry", GAME), "restart": ("entry", GAME), "restarts_used": ("entry", GAME),
    }.items():
        game.set(start, focus)
        if scenario in ("stuck", "restart", "restarts_used"):  # the back key does nothing: pressed up to its limit
            game.on_key = lambda keycode: True
        if scenario == "restart":  # the restarted game works again, and its title opens on a page with no tab bar
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "on_key", Game.on_key.__get__(game)))[0]
            game.on_tap = lambda x, y, game=game: (setattr(game, "screen", "entry") if game.screen == "title" else Game.on_tap(game, x, y)) or True
        # stuck: the game restarts that L3 allows were used up before; restart: none were.
        actions.STUCK["l3"] = 0 if scenario == "restart" else actions.recovery.L3_PER_EXECUTION
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stops = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        override = {"GoHome": {"timeout": 4000}, "RecoverL3": {"post_delay": 0}, "RecoverStartApp": {"post_delay": 0}}
        if scenario == "restarts_used":  # one restart left, and the restarted game is as stuck as before
            actions.STUCK["l3"] = actions.recovery.L3_PER_EXECUTION - 1
            game.start_app = lambda intent, game=game: (setattr(game, "focus", GAME), setattr(game, "screen", "entry"), True)[-1]
            override["RecoverStartApp"]["timeout"] = 3000
        out[scenario] = {**result(tasker.post_task("GoHome", override).wait().get(), game, actions), "starts": game.starts,
                         "stops": game.stops, "l3": actions.STUCK["l3"],
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stops}
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


def test_go_home_fails_after_a_limited_number_of_back_keys_when_the_game_restarts_are_used_up():
    o = run_child(__file__)["stuck"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5 and o["stops"] == 0
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1  # the stop procedure ran: evidence and its log


def test_go_home_that_cannot_reach_the_main_window_restarts_the_game_and_goes_again():
    # D4 (#362): L3 within its limit per bot launch, then GoHome from the title. The back key's limit starts over:
    # the restarted game's page with no tab bar takes one more.
    o = run_child(__file__)["restart"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["stopped"] == 0
    assert (o["stops"], o["starts"], o["l3"]) == (1, 1, 1)
    assert o["keys"] == [4] * 6 and "GoHomeLost" in o["nodes"] and "NavTitle" in o["nodes"]


def test_go_home_stops_once_the_last_restart_did_not_help():
    o = run_child(__file__)["restarts_used"]
    assert o["succeeded"] is False and o["stops"] == 1 and o["l3"] == 3 and o["stopped"] == 1
    assert o["nodes"].count("GoHomeLost") == 2


def test_go_home_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "GoHome", "label": "$GoHome", "entry": "GoHome"} in interface["task"]


if __name__ == "__main__":
    child()
