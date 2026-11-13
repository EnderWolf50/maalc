"""GoHome on the title screen (#495, #506, #540). The real task in a child process (daily_child.py), on a model of the
game: a live title whose picture keeps moving, a tap that brings CONNECTING (or a loading screen) and then the main window,
the title's glitch effect, a login that shows the title alone between two CONNECTINGs, and a game frozen on the title,
with or without CONNECTING up, until it is restarted.

Live 2026-11-08 (a recording and the MaaFramework log of a title tap): CONNECTING showed within 0.6 s of each of 2 taps
and stayed up to 28 s with the title under it, its template still hitting; the glitch warped the whole picture for
0.9-1.3 s three times in 40 s, NavTitle scoring 0.51-0.61 then. Live 2026-11-12 (a recording of one tap by hand):
CONNECTING went for 2.8 s with the title alone up, then came back by itself before the main window (#58).
"""

import json
import threading
import time

import numpy as np
from daily_child import GAME, bind, game_class, inside, live_frame, load, result, run_child, run_task, screen
from recovery import DEAD_TAPS, L3_FAILED_IN_A_ROW
from agent_patch import rebind
import recovery

TITLE_TAP = (540, 300, 200, 120)
GLITCH = 1.3  # s: the recording's longest glitch
GAP = 2.8  # s: the title alone between two CONNECTINGs of one login, 2026-11-12's recording
SCREENS = {"title": "Title.png", "connecting": "TitleConnecting.png", "loading": "Loading.png", "main": "MainWindow.png"}
LIMIT = 40  # s: a scenario still going by then is stopped (a title tapped for ever)
CONNECTING_WAIT = 5  # s: GoHome's wait on CONNECTING in the frozen_connecting scenarios, for the pipeline's 60; their
# restarted game's CONNECTING (5 screenshots) ends well within it


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

        def set(self, frozen=False, ignored=0, answer=("connecting",), then=None, answer_for=20, glitch=0.0,
                glitch_after_tap=0.0, screen="title"):
            """frozen: the game takes no tap and shows one picture, the screen it starts on, until it restarts; a live
            title's picture moves at every other screenshot. ignored: the taps the live title lets go by. answer: the
            screens a taken tap shows in turn, each for answer_for screenshots ("gap": the title, taking no tap, for GAP
            s), before the main window; then: the answer of the taps after the first taken one. glitch: the seconds
            from the start that show the glitch; glitch_after_tap: the seconds right after a taken tap, before its
            answer. screen: the one at the start."""
            self.screen, self.focus, self.frozen, self.ignored = screen, GAME, frozen, ignored
            self.answer, self.then, self.answer_for, self.left = answer, then or answer, answer_for, 0
            self.glitch_after_tap, self.gap_until = glitch_after_tap, 0.0
            self.coming = []
            self.glitch_until = time.monotonic() + glitch
            self.clicks, self.keys, self.starts, self.stops, self.frames = [], [], 0, 0, 0

        def screencap(self):
            self.frames += 1
            if self.focus != GAME:
                return self.images["black"]
            if time.monotonic() < self.glitch_until:
                return self.images["glitch"]
            if self.screen in ("connecting", "loading") and not self.frozen:
                self.left -= 1
                if self.left < 0:
                    self.screen, self.left = (self.coming.pop(0), self.answer_for) if self.coming else ("main", 0)
                    self.gap_until = time.monotonic() + GAP
            if self.screen == "gap" and time.monotonic() >= self.gap_until:
                self.screen, self.left = (self.coming.pop(0), self.answer_for) if self.coming else ("main", 0)
            if self.screen in ("title", "gap") and not self.frozen and self.frames % 2:
                return self.images["title_moved"]
            return self.images["title" if self.screen == "gap" else self.screen]

        def on_tap(self, x, y):
            if self.screen != "title" or self.frozen or not inside(TITLE_TAP, x, y):
                return True
            if self.ignored:
                self.ignored -= 1
                return True
            self.glitch_until = time.monotonic() + self.glitch_after_tap
            self.screen, *self.coming = self.answer
            self.answer, self.left = self.then, self.answer_for
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
    rebind("foreground", lambda context: recovery.focused_package(game.shell("dumpsys window", 0)))
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (model, in_a_row) in {
        "connects": ({}, 0),
        "loads": ({"answer": ("loading",)}, 0),
        "connects_then_loads": ({"answer": ("connecting", "loading")}, 0),
        "glitch": ({"glitch": GLITCH}, 0),
        "glitch_after_tap": ({"glitch_after_tap": GLITCH}, 0),
        # a picture no node reads (the glitch frame), then the main window within HomeBack's wait: a page that comes late
        "late_main": ({"screen": "main", "glitch": 0.5}, 0),
        "ignored_once": ({"ignored": 1}, 0),
        "login_gap": ({"answer": ("connecting", "gap", "connecting")}, 0),
        "back_to_title": ({"answer": ("connecting", "title"), "then": ("connecting",)}, 0),
        "taken_long_ago": ({}, 0),  # NavTitle's last taken tap SETTLE_WITHIN s and more before
        "taken_just_now": ({}, 0),  # ... and just before the scenario
        "frozen": ({"frozen": True}, 0),
        "frozen_restarts_used": ({"frozen": True}, L3_FAILED_IN_A_ROW),
        "frozen_connecting": ({"frozen": True, "screen": "connecting", "answer_for": 5}, 0),
        "frozen_connecting_restarts_used": ({"frozen": True, "screen": "connecting"}, L3_FAILED_IN_A_ROW),
    }.items():
        game.set(**model)
        actions.STUCK["restarts"] = recovery.Restarts()
        for _ in range(in_a_row):
            actions.STUCK["restarts"].attempt(None)
        actions.STUCK["watch"].reset()
        actions.STUCK["flag"] = None
        actions.STUCK["taken"].clear()  # a scenario's own taps only
        if scenario.startswith("taken_"):
            ago = actions.SETTLE_WITHIN + 1 if scenario == "taken_long_ago" else 0
            actions.STUCK["taken"]["NavTitle"] = time.monotonic() - ago
        actions.TASK.clear()
        actions.TASK.update(runs=0, done=None)
        actions.LOG.clear()
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stopped = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        began = time.monotonic()
        timer = threading.Timer(LIMIT, tasker.post_stop)
        timer.start()
        # The model's CONNECTING lasts answer_for screenshots, not seconds: HomeConnecting's 300 ms between looks would only
        # stretch each scenario, as the node delays did (#480).
        override = {"HomeConnecting": {"rate_limit": 0}}
        if scenario.startswith("frozen_connecting"):
            override["HomeConnecting"]["timeout"] = CONNECTING_WAIT * 1000
        detail = run_task(tasker, scenario, "GoHome", override)
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
    # #495: for up to 1.3 s (GLITCH, the recording's longest) the glitch hides the title from every template, and GoHome
    # pressed back on it.
    o = run_child(__file__)["glitch"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["keys"] == [] and o["title_taps"] == 1, json.dumps(o)


def test_a_screen_go_home_knows_showing_during_the_back_keys_wait_gets_no_back_key():
    # Review of #495's fix: the back key waited for the title only, then went to whatever had come in the meantime.
    o = run_child(__file__)["late_main"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["keys"] == [] and o["clicks"] == [], json.dumps(o)


def test_a_glitch_right_after_the_tap_is_not_the_title_leaving():
    # #495: a glitch frame read as the title gone, then GoHome knew nothing, pressed back and tapped the title again.
    o = run_child(__file__)["glitch_after_tap"]
    assert o["succeeded"] and o["keys"] == [] and o["title_taps"] == 1, json.dumps(o)
    assert len(title_lines(o)) == 1 and "screen changed" in title_lines(o)[0], json.dumps(o)


def test_a_live_title_that_lets_a_tap_go_by_is_tapped_again_not_restarted():
    o = run_child(__file__)["ignored_once"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 2, json.dumps(o)
    assert (o["stops"], o["starts"]) == (0, 0), json.dumps(o)


def test_the_title_between_two_connectings_of_one_login_is_not_tapped_again():
    # #58: CONNECTING goes for a moment with the title alone up (2.8 s on 2026-11-12's recording), then comes back by
    # itself; the bot tapped the title in that gap every morning of 2026-11-09 to 11-12.
    o = run_child(__file__)["login_gap"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["keys"] == [], json.dumps(o)
    assert o["title_taps"] == 1, json.dumps(o)
    assert any("not tapped again, the screen moved on by itself" in line for line in title_lines(o)), json.dumps(o)


def test_a_title_long_after_a_taken_tap_is_tapped_at_once_and_one_just_after_waits_the_settle():
    # Review of #58: the settle held for the whole launch, so a title met long after the login (a session expired)
    # waited 5 s too. It holds SETTLE_WITHIN s after a taken tap now.
    late, soon = run_child(__file__)["taken_long_ago"], run_child(__file__)["taken_just_now"]
    for o in (late, soon):
        assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 1, json.dumps(o)
    assert not any("still up" in line for line in title_lines(late)) and late["seconds"] < 5, json.dumps(late)
    assert any("still up" in line for line in title_lines(soon)), json.dumps(soon)


def test_a_title_still_up_once_the_settle_is_over_is_tapped_again():
    # #58's settle: a title that stays with no CONNECTING for 5 s after a taken tap wants another one.
    from test_pipeline import load_nodes

    settle = load_nodes("navigation.json")["NavTitle"]["custom_action_param"]["settle"]
    o = run_child(__file__)["back_to_title"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 2, json.dumps(o)
    assert any(f"still up {settle} s after its last tap was taken" in line for line in title_lines(o)), json.dumps(o)
    assert settle <= o["seconds"] < LIMIT, json.dumps(o)


def test_a_title_frozen_through_its_taps_restarts_the_game_and_go_home_reaches_the_main_window():
    # #506: the title is known on every look, so GoHome never timed out into its restart: it tapped the title for ever.
    o = run_child(__file__)["frozen"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["stopped"] == 0, json.dumps(o)
    assert (o["stops"], o["starts"]) == (1, 1), json.dumps(o)
    assert o["title_taps"] == DEAD_TAPS + 1, json.dumps(o)  # the frozen game's, then the restarted title's one


def test_a_normal_login_through_connecting_and_loading_is_not_restarted():
    o = run_child(__file__)["connects_then_loads"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["title_taps"] == 1 and o["keys"] == [], json.dumps(o)
    assert (o["stops"], o["starts"]) == (0, 0) and not any("recovery L3" in line for line in o["log"]), json.dumps(o)


def test_a_title_frozen_under_connecting_restarts_the_game_once_the_wait_is_up_and_reaches_the_main_window():
    # #540: each look at CONNECTING went back to GoHome with a new 60 s timeout, so a game frozen on it was never
    # restarted (the model: 5181 looks in 40 s). The wait is the pipeline's 60 s here cut to CONNECTING_WAIT; the
    # restart is the task's first of its 2, and the restarted game's CONNECTING, shorter than the wait, is let through.
    o = run_child(__file__)["frozen_connecting"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["stopped"] == 0, json.dumps(o)
    assert (o["stops"], o["starts"]) == (1, 1) and o["title_taps"] == 1, json.dumps(o)
    assert CONNECTING_WAIT <= o["seconds"] < LIMIT, json.dumps(o)
    assert [line for line in o["log"] if "recovery L3: CONNECTING" in line and "1 of 2 this task" in line], json.dumps(o)


def test_go_home_waits_on_connecting_up_to_60_s():
    # #540: the user's pick of 2026-11-08 for GoHome alone; spec 01 "回主畫面" says what it costs.
    from test_pipeline import load_nodes

    nodes = load_nodes("navigation.json")
    timeout = nodes["HomeConnecting"]["timeout"]
    assert timeout == 60_000
    assert f"after {timeout // 1000} s" in nodes["HomeConnectingLost"]["custom_action_param"]


def test_a_frozen_title_with_the_restarts_used_up_ends_through_the_stop_procedure():
    o = run_child(__file__)["frozen_restarts_used"]
    assert o["succeeded"] is False and (o["stops"], o["starts"]) == (0, 0) and o["stopped"] == 1, json.dumps(o)
    assert o["title_taps"] == DEAD_TAPS, json.dumps(o)


def test_connecting_frozen_with_the_restarts_used_up_ends_through_the_stop_procedure():
    # Review of #540: the restart is the wait's on_error, inside a JumpBack from GoHome; it must end the task, not go back.
    o = run_child(__file__)["frozen_connecting_restarts_used"]
    assert o["succeeded"] is False and (o["stops"], o["starts"]) == (0, 0) and o["stopped"] == 1, json.dumps(o)
    assert o["title_taps"] == 0 and CONNECTING_WAIT <= o["seconds"] < LIMIT, json.dumps(o)


if __name__ == "__main__":
    child()
