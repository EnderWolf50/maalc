"""GoHome on the title screen (#495, #506). The real task in a child process (daily_child.py), on a model of the game: a
live title whose picture keeps moving, a tap that brings CONNECTING (or a loading screen) and then the main window, the
title's glitch effect, and a game frozen on the title until it is restarted.

Live 2026-11-08 (a recording and the MaaFramework log of a title tap): CONNECTING showed within 0.6 s of each of 2 taps
and stayed up to 28 s with the title under it, its template still hitting; the glitch warped the whole picture for
0.9-1.1 s three times in 40 s, NavTitle scoring 0.51-0.61 then.
"""

import json
import threading
import time

import numpy as np
from daily_child import GAME, bind, game_class, inside, live_frame, load, result, run_child, screen
from recovery import DEAD_TAPS, L3_FAILED_IN_A_ROW

TITLE_TAP = (540, 300, 200, 120)
SCREENS = {"title": "Title.png", "connecting": "TitleConnecting.png", "loading": "Loading.png", "main": "MainWindow.png"}
LIMIT = 40  # s: a scenario still going by then is stopped (a title tapped for ever)


def glitched(image):
    """The title's glitch effect: the picture blown up 1.1 times wide and 1.2 times tall from its bottom left corner.
    NavTitle scores 0.51 on it (TM_CCOEFF_NORMED offline), the recording's worst."""
    cols = (np.arange(1280) / 1.1).astype(int)
    rows = ((np.arange(720) - 720) / 1.2 + 720).astype(int)
    return np.ascontiguousarray(image[rows][:, cols])


def child():
    """Run GoHome from the title of each scenario; print one JSON line."""
    actions, resource = load()

    class Game(game_class()):
        images = {**{name: screen(png) for name, png in SCREENS.items()}, "black": np.zeros((720, 1280, 3), np.uint8)}
        images["title_moved"] = live_frame(images["title"])
        images["glitch"] = glitched(images["title"])

        def set(self, frozen=False, ignored=0, answer="connecting", answer_for=20, glitch=(), glitch_after_tap=0):
            """frozen: the title takes no tap and shows one picture until the game restarts; a live title's picture moves at
            every other screenshot. ignored: the taps the live title lets go by. answer: the screen a taken tap shows for
            answer_for screenshots before the main window. glitch: the screenshots (counted from 1) that show the glitch;
            glitch_after_tap: that many right after a taken tap, before its answer."""
            self.screen, self.focus, self.frozen, self.ignored = "title", GAME, frozen, ignored
            self.answer, self.answer_for, self.left, self.glitch, self.glitch_after_tap = answer, answer_for, 0, set(glitch), glitch_after_tap
            self.clicks, self.keys, self.starts, self.stops, self.frames = [], [], 0, 0, 0

        def screencap(self):
            self.frames += 1
            if self.focus != GAME:
                return self.images["black"]
            if self.frames in self.glitch:
                return self.images["glitch"]
            if self.screen in ("connecting", "loading"):
                self.left -= 1
                if self.left < 0:
                    self.screen = "main"
            if self.screen == "title" and not self.frozen and self.frames % 2:
                return self.images["title_moved"]
            return self.images[self.screen]

        def on_tap(self, x, y):
            if self.screen != "title" or self.frozen or not inside(TITLE_TAP, x, y):
                return True
            if self.ignored:
                self.ignored -= 1
                return True
            self.glitch |= set(range(self.frames + 1, self.frames + 1 + self.glitch_after_tap))
            self.screen, self.left = self.answer, self.answer_for
            return True

        def stop_app(self, intent):
            self.stops += 1
            self.focus, self.frozen = "com.android.launcher", False
            return True

        def start_app(self, intent):
            self.starts += 1
            self.focus, self.screen = GAME, "title"
            return True

    game = Game()
    game.set()
    # MaaFramework's Linux build (CI) passes no post_shell to a custom controller: read the model's dumpsys directly.
    actions.foreground = lambda context: actions.recovery.focused_package(game.shell("dumpsys window", 0))
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (model, in_a_row) in {
        "connects": ({}, 0),
        "loads": ({"answer": "loading"}, 0),
        "glitch": ({"glitch": (1, 2, 3)}, 0),
        "glitch_after_tap": ({"glitch_after_tap": 3}, 0),
        "ignored_once": ({"ignored": 1}, 0),
        "frozen": ({"frozen": True}, 0),
        "frozen_restarts_used": ({"frozen": True}, L3_FAILED_IN_A_ROW),
    }.items():
        game.set(**model)
        actions.STUCK["restarts"] = actions.recovery.Restarts()
        for _ in range(in_a_row):
            actions.STUCK["restarts"].attempt(None)
        actions.STUCK["watch"].reset()
        actions.STUCK["flag"] = None
        actions.TASK.clear()
        actions.TASK.update(runs=0, done=None)
        actions.LOG.clear()
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stopped = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        began = time.monotonic()
        timer = threading.Timer(LIMIT, tasker.post_stop)
        timer.start()
        job = tasker.post_task("GoHome").wait()
        while not (detail := job.get()).status.done:  # #461: post_stop's queue clear ends wait() before the task does
            time.sleep(0.01)
        timer.cancel()
        out[scenario] = {**result(detail, game, actions), "starts": game.starts, "stops": game.stops,
                         "seconds": time.monotonic() - began, "in_a_row": actions.STUCK["restarts"].in_a_row,
                         "title_taps": sum(inside(TITLE_TAP, *c) for c in game.clicks),
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stopped,
                         "log": list(actions.LOG)}
        actions.STUCK["halted"] = None
    print(json.dumps(out))


def title_lines(o):
    return [line for line in o["log"] if "NavTitle:" in line]


def test_a_title_tap_that_brings_connecting_is_taken_at_once():
    # #495: the title stays under CONNECTING, so waiting for it to leave timed out (`no change after 3.2 s`) on a tap the
    # game had taken.
    o = run_child(__file__)["connects"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 1 and o["keys"] == [], json.dumps(o)
    assert len(title_lines(o)) == 1 and "screen changed" in title_lines(o)[0], json.dumps(o)
    assert o["starts"] == 0, json.dumps(o)


def test_a_title_tap_that_goes_to_the_loading_screen_is_not_a_frozen_game():
    o = run_child(__file__)["loads"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 1 and o["keys"] == [], json.dumps(o)
    assert o["starts"] == 0, json.dumps(o)


def test_the_titles_glitch_gets_no_back_key():
    # #495: for about 1 s the glitch hides the title from every template, and GoHome pressed back on it.
    o = run_child(__file__)["glitch"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["keys"] == [] and o["title_taps"] == 1, json.dumps(o)


def test_a_glitch_right_after_the_tap_is_not_the_title_leaving():
    # #495: a glitch frame read as the title gone, then GoHome knew nothing, pressed back and tapped the title again.
    o = run_child(__file__)["glitch_after_tap"]
    assert o["succeeded"] and o["keys"] == [] and o["title_taps"] == 1, json.dumps(o)
    assert len(title_lines(o)) == 1 and "screen changed" in title_lines(o)[0], json.dumps(o)


def test_a_live_title_that_lets_a_tap_go_by_is_tapped_again_not_restarted():
    o = run_child(__file__)["ignored_once"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 2, json.dumps(o)
    assert (o["stops"], o["starts"]) == (0, 0), json.dumps(o)


def test_a_title_frozen_through_its_taps_restarts_the_game_and_go_home_reaches_the_main_window():
    # #506: the title is known on every look, so GoHome never timed out into its restart: it tapped the title for ever.
    o = run_child(__file__)["frozen"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["stopped"] == 0, json.dumps(o)
    assert (o["stops"], o["starts"]) == (1, 1), json.dumps(o)
    assert o["title_taps"] == DEAD_TAPS + 1, json.dumps(o)  # the frozen game's, then the restarted title's one


def test_a_frozen_title_with_the_restarts_used_up_ends_through_the_stop_procedure():
    o = run_child(__file__)["frozen_restarts_used"]
    assert o["succeeded"] is False and (o["stops"], o["starts"]) == (0, 0) and o["stopped"] == 1, json.dumps(o)
    assert o["title_taps"] == DEAD_TAPS, json.dumps(o)


if __name__ == "__main__":
    child()
