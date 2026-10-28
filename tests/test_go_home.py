"""GoHome (#365, spec 00 daily tasks): back to the main window from wherever the last task left the game.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen, taps and the back key
that move between them, and `dumpsys window` for the front package.
"""

import json
import time

import numpy as np
from daily_child import GAME, bind, game_class, inside, interface as interface_json, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)  # the bottom tab bar's Window tab
MAILBOX_CLOSE = (690, 530, 175, 45)
SETTINGS_RETURN = (500, 370, 280, 45)
TITLE_TAP = (540, 300, 200, 120)

# screen name -> tests/screens image (None: black, the game is not up)
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "sinners": "SinnersTab.png", "mailbox": "Mailbox.png",
           "settings": "SettingsMenu.png", "entry": "EntryNewRun.png", "title": "Title.png", "black": None,
           "battle": "LuxBattleTurn.png", "event": "LuxEventStory.png"}
# where a tap moves: (screens it works on, its box, the screen it shows)
TAPS = [(("drive", "sinners"), WINDOW_TAB, "main"), (("mailbox",), MAILBOX_CLOSE, "main"),
        (("settings",), SETTINGS_RETURN, "main"), (("title",), TITLE_TAP, "main")]


def child():
    """Run GoHome from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys, starts}}."""
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) if png else np.zeros((720, 1280, 3), np.uint8) for name, png in SCREENS.items()}

        def set(self, start, focus=GAME, lag=0, splash=0):
            self.screen, self.focus, self.clicks, self.keys, self.starts, self.stops = start, focus, [], [], 0, 0
            self.lag, self.splash, self.pending = lag, splash, None  # lag: screenshots a tap's screen takes to show

        def screencap(self):
            if self.pending:
                self.pending[1] -= 1
                if self.pending[1] < 0:
                    self.screen, self.pending = self.pending[0], None
            if self.focus == GAME and self.screen == "title" and self.splash > 0:  # the game's start, before its title
                self.splash -= 1
                return self.images["black"]
            return self.images["black" if self.focus != GAME else self.screen]

        def on_tap(self, x, y):
            to = next((to for on, box, to in TAPS if self.screen in on and inside(box, x, y)), self.screen)
            if self.lag and to != self.screen:
                self.pending = [to, self.lag]
            else:
                self.screen = to
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
    for scenario, (start, focus, *model) in {
        "drive": ("drive", GAME), "sinners": ("sinners", GAME), "main": ("main", GAME), "mailbox": ("mailbox", GAME),
        "settings": ("settings", GAME), "entry": ("entry", GAME), "closed": ("black", "com.android.launcher"),
        # the Window tab's page shows 4 screenshots after the tap; the game shows black for 15 before its title
        "drive_late": ("drive", GAME, 4), "closed_slow": ("black", "com.android.launcher", 0, 15),
        # these last: they change the model's methods
        "stuck": ("entry", GAME), "restart": ("entry", GAME), "restarts_used": ("entry", GAME), "event": ("event", GAME),
        # the Window tab shows its tap but the page never changes: tapped up to its limit (the taps stay ignored after it)
        "tab_stuck": ("drive", GAME),
        # the same, with a game restart left: the restarted game opens on the Drive page and takes the Window tab's tap again
        "tab_restart": ("drive", GAME),
        # J2 (live 2026-10-28): the last task stopped mid-battle; it ends the task list (post_stop): last
        "battle": ("battle", GAME),
    }.items():
        game.set(start, focus, *model)
        if scenario in ("stuck", "restart", "restarts_used"):  # the back key does nothing: pressed up to its limit
            game.on_key = lambda keycode: True
        if scenario == "restart":  # the restarted game works again, and its title opens on a page with no tab bar
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "on_key", Game.on_key.__get__(game)))[0]
            game.on_tap = lambda x, y, game=game: (setattr(game, "screen", "entry") if game.screen == "title" else Game.on_tap(game, x, y)) or True
        # stuck: the game restarts that L3 allows were used up before; restart: none were.
        actions.STUCK["l3"] = 0 if scenario in ("restart", "tab_restart") else actions.recovery.L3_PER_EXECUTION
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stops = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        override = {"GoHome": {"timeout": 4000}, "RecoverL3": {"post_delay": 0}, "RecoverStartApp": {"post_delay": 0}}
        if scenario == "tab_stuck":
            game.on_tap = lambda x, y: True
            override["GoHome"]["timeout"] = 8000
            override["HomeWindowTab"] = {"custom_action_param": {"left": True, "timeout": 0.1}}
        if scenario == "tab_restart":
            game.on_tap = lambda x, y: True
            override["GoHome"]["timeout"] = 8000
            override["HomeWindowTab"] = {"custom_action_param": {"left": True, "timeout": 0.1}}
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "screen", "drive"),
                                                        setattr(game, "on_tap", Game.on_tap.__get__(game)))[0]
        if scenario == "restarts_used":  # one restart left, and the restarted game is as stuck as before
            actions.STUCK["l3"] = actions.recovery.L3_PER_EXECUTION - 1
            game.start_app = lambda intent, game=game: (setattr(game, "focus", GAME), setattr(game, "screen", "entry"), True)[-1]
            override["RecoverStartApp"]["timeout"] = 3000
        began = time.monotonic()
        out[scenario] = {**result(tasker.post_task("GoHome", override).wait().get(), game, actions), "starts": game.starts,
                         "seconds": time.monotonic() - began,
                         "stops": game.stops, "l3": actions.STUCK["l3"],
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stops,
                         "halted": actions.STUCK["halted"]}
        actions.STUCK["halted"] = None
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


def test_go_home_waits_for_the_screens_not_for_fixed_delays():
    # #362: the Window tab's tap waits until the tab reads unlit no more, so a page that comes late is not tapped twice;
    # the game's start waits for its title, not 10 s.
    o = run_child(__file__)["drive_late"]
    assert o["succeeded"] and len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]) and o["keys"] == []
    o = run_child(__file__)["closed_slow"]
    assert o["succeeded"] and o["starts"] == 1 and "GoHomeLost" not in o["nodes"] and "HomeGameUp" in o["nodes"]
    assert "NavTitle" in o["nodes"] and o["nodes"][-1] == "HomeReached"
    assert run_child(__file__)["closed"]["seconds"] < 10  # HomeGameAway's post_delay was 10 s


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


def test_go_home_in_a_battle_ends_the_task_list_without_a_back_key():
    # J2 (live 2026-10-28): in a battle the back key opens the pause menu, Give Up one tap away. Nothing is pressed: the
    # stop procedure, and the rest of the list goes, as after an account-level stop, for the user to end it by hand.
    o = run_child(__file__)["battle"]
    assert o["succeeded"] is False and o["keys"] == [] and o["clicks"] == []
    assert o["stopped"] == 1 and o["halted"].startswith("HomeInBattle: "), o["halted"]


def test_go_home_on_an_event_page_presses_back_then_restarts_the_game():
    # The user (2026-10-28): the event screens of Luxcavation and the mirror look the same, so no screen reading tells
    # them apart; an event page gets the old way, the back key (5 times, live: the story page did not change), then L3.
    # The restarts are used up here: L3 runs the stop procedure, and the list is not ended.
    o = run_child(__file__)["event"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5 and o["clicks"] == []
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1 and o["halted"] is None, o


def test_go_home_taps_a_window_tab_that_does_not_open_its_page_only_a_limited_number_of_times():
    # Review of #375: HomeWindowTab had no limit, so a tab that showed its tap but never changed the page was tapped
    # until the end of time (a JumpBack gives GoHome a fresh timeout each time). 10 taps, then GoHomeLost's L3.
    o = run_child(__file__)["tab_stuck"]
    assert o["succeeded"] is False and len(o["clicks"]) == 10 and all(inside(WINDOW_TAB, *c) for c in o["clicks"]), o
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1, o


def test_go_home_taps_the_window_tab_again_after_the_game_restarted():
    # Review of #375: L3 cleared HomeBack's and HomeGameAway's hit counts but not HomeWindowTab's, so a task that used its
    # 10 taps could not tap the restarted game's Window tab at all.
    o = run_child(__file__)["tab_restart"]
    assert o["succeeded"] and o["l3"] == 1 and "GoHomeLost" in o["nodes"], o
    assert len(o["clicks"]) == 11 and all(inside(WINDOW_TAB, *c) for c in o["clicks"]), o


def test_go_home_is_not_a_task_of_the_interface():  # the daily tasks run it themselves (#365); no PI entry of its own
    interface = interface_json()
    assert "GoHome" not in [t["name"] for t in interface["task"]]


if __name__ == "__main__":
    child()
