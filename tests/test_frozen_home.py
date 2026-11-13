"""A game frozen on the main window (#440, spec 06): the bot knows the screen, and no tap changes it. The real
ClaimPassMissions task in a child process (daily_child.py), on a model of the game whose main window takes no tap until
the game is restarted; and on a live main window, whose picture keeps moving, that takes the banner's tap late or never.
"""

import json
import math
import threading

import numpy as np
from daily_child import GAME, bind, game_class, inside, live_frame, load, result, run_child, run_task, screen
from recovery import L3_PER_TASK
from test_pass_task import BANNER, MISSIONS_TAB, SCREENS as PASS_SCREENS, SEASONAL_TAB, WEEKLY_TAB
from agent_patch import rebind
import recovery

TITLE_TAP = (540, 300, 200, 120)
SCREENS = {**PASS_SCREENS, "title": "Title.png"}
HUB_TIMEOUT = 5000  # PassHub's 60 s, cut short: a pass page that never opens fails the task in 5 s
LIMIT = 60  # s: a scenario still going by then is stopped (GoHome tapping a frozen title for ever, #506)


def child():
    """Run ClaimPassMissions from the main window of each scenario; print one JSON line."""
    actions, resource = load()

    class Game(game_class()):
        images = {**{name: screen(png) for name, png in SCREENS.items()}, "black": np.zeros((720, 1280, 3), np.uint8)}
        images["main_moved"] = live_frame(images["main"])

        def set(self, frozen=False, live=False, ignored=0, ignored_after=0, refreezes=False, screen="main"):
            """frozen: the main window takes no tap and shows the same picture until the game restarts. live: the main
            window's picture moves at every other screenshot. ignored: the banner taps the game lets go by before one opens
            the pass page (math.inf: none does); ignored_after: the same, once the game restarted. screen: where the
            task starts, the main window or the title (frozen there too)."""
            self.screen, self.focus, self.frozen, self.live, self.ignored = screen, GAME, frozen, live, ignored
            self.ignored_after, self.refreezes = ignored_after, refreezes
            self.clicks, self.keys, self.swipes, self.starts, self.stops, self.frames = [], [], [], 0, 0, 0
            self.tapped_frozen = 0

        def screencap(self):
            self.frames += 1
            if self.focus != GAME:
                return self.images["black"]
            if self.screen == "main" and self.live and self.frames % 2:
                return self.images["main_moved"]
            return self.images[self.screen]

        def on_tap(self, x, y):
            if self.frozen:
                self.tapped_frozen += 1
            elif self.screen == "title" and inside(TITLE_TAP, x, y):
                self.screen, self.frozen = "main", self.refreezes
            elif self.screen == "main" and inside(BANNER, x, y):
                if self.ignored > 0:
                    self.ignored -= 1
                else:
                    self.screen = "pass"
            elif self.screen == "pass" and inside(MISSIONS_TAB, x, y):
                self.screen = "daily"
            elif self.screen == "daily" and inside(WEEKLY_TAB, x, y):
                self.screen = "weekly"
            elif self.screen == "weekly" and inside(SEASONAL_TAB, x, y):
                self.screen = "seasonal"
            return True

        def on_swipe(self, down, last):
            self.swipes.append([*down, *last])
            if self.screen == "seasonal" and last[1] < down[1]:
                self.screen = "seasonal_end"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen != "main" and not self.frozen:
                self.screen = "main"
            return True

        def stop_app(self, intent):
            self.stops += 1
            self.focus, self.frozen = "com.android.launcher", False
            return True

        def start_app(self, intent):
            self.starts += 1
            self.focus, self.screen, self.live = GAME, "title", not self.refreezes
            self.ignored = self.ignored_after
            return True

    game = Game()
    game.set()
    # MaaFramework's Linux build (CI) passes no post_shell to a custom controller: read the model's dumpsys directly.
    rebind("foreground", lambda context: recovery.focused_package(game.shell("dumpsys window", 0)))
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (model, restarts_used) in {
        "frozen": ({"frozen": True}, 0),
        # the restarted game lets the banner's first tap go by: its 4th tap in all, past PassBanner's max_hit 3
        "frozen_late": ({"frozen": True, "ignored_after": 1}, 0),
        "frozen_again": ({"frozen": True, "refreezes": True}, 0),
        "frozen_restarts_used": ({"frozen": True}, recovery.L3_FAILED_IN_A_ROW),
        "late": ({"live": True, "ignored": 1}, 0),
        "never": ({"live": True, "ignored": math.inf}, 0),
        "title_frozen": ({"frozen": True, "screen": "title"}, 0),
    }.items():
        game.set(**model)
        actions.STUCK["restarts"] = recovery.Restarts()
        for _ in range(restarts_used):
            actions.STUCK["restarts"].attempt("PassBanner")
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stopped = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        timer = threading.Timer(LIMIT, tasker.post_stop)
        timer.start()
        detail = run_task(tasker, scenario, "ClaimPassMissions", {"PassHub": {"timeout": HUB_TIMEOUT}})
        timer.cancel()
        out[scenario] = {**result(detail, game, actions), "starts": game.starts, "stops": game.stops,
                         "tapped_frozen": game.tapped_frozen, "in_a_row": actions.STUCK["restarts"].in_a_row,
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stopped,
                         "log": list(actions.LOG)[-40:]}
        actions.LOG.clear()
    print(json.dumps(out))


def test_a_main_window_that_takes_no_tap_restarts_the_game_and_the_task_goes_on():
    o = run_child(__file__)["frozen"]
    assert (o["stops"], o["starts"]) == (1, 1), json.dumps(o)
    assert o["in_a_row"] == 0, json.dumps(o)
    # Within the banner's own 3 taps (PassBanner's max_hit): after them the hub has nothing left to tap.
    assert 1 <= o["tapped_frozen"] <= 3, json.dumps(o)
    assert o["succeeded"] and o["screen"] == "main" and o["nodes"][-1] == "TaskDone", json.dumps(o)
    assert o["done"] == "pass missions: nothing to claim" and o["stopped"] == 0, json.dumps(o)


def test_after_the_restart_the_hub_taps_the_banner_afresh():
    # The dead taps used up PassBanner's hits before the restart; the restarted game's taps count anew.
    o = run_child(__file__)["frozen_late"]
    assert (o["stops"], o["starts"]) == (1, 1), json.dumps(o)
    assert o["succeeded"] and o["done"] == "pass missions: nothing to claim", json.dumps(o)
    assert sum(inside(BANNER, *c) for c in o["clicks"]) == 4, json.dumps(o)


def test_a_main_window_frozen_again_after_each_restart_stops_after_two():
    # Each restart went through (the title came), so the task's 2 stop it before the launch's 3 in a row (#520).
    o = run_child(__file__)["frozen_again"]
    assert (o["stops"], o["starts"], o["in_a_row"]) == (L3_PER_TASK,) * 3, json.dumps(o)
    assert o["succeeded"] is False and o["stopped"] == 1, json.dumps(o)
    assert any(f"game restarted {L3_PER_TASK} times this task" in line for line in o["log"]), json.dumps(o)


def test_a_frozen_main_window_with_the_restarts_used_up_ends_the_task_through_the_stop_procedure():
    o = run_child(__file__)["frozen_restarts_used"]
    assert o["succeeded"] is False and (o["stops"], o["starts"]) == (0, 0) and o["stopped"] == 1, json.dumps(o)


def test_a_task_started_on_a_frozen_title_restarts_the_game_and_is_done():
    # #506: the task's first step, GoHome, tapped a title that took no tap for ever; the title is known on every look, so
    # GoHome never timed out into its restart.
    o = run_child(__file__)["title_frozen"]
    assert (o["stops"], o["starts"]) == (1, 1), json.dumps(o)
    assert o["succeeded"] and o["done"] == "pass missions: nothing to claim" and o["stopped"] == 0, json.dumps(o)


def test_a_live_main_window_that_takes_the_banner_late_is_not_restarted():
    o = run_child(__file__)["late"]
    assert (o["stops"], o["starts"]) == (0, 0), json.dumps(o)
    assert o["succeeded"] and o["done"] == "pass missions: nothing to claim", json.dumps(o)
    assert [inside(BANNER, *c) for c in o["clicks"][:2]] == [True, True], json.dumps(o)


def test_a_live_main_window_whose_banner_never_opens_the_pass_is_not_restarted():
    # The screen moves after each tap: the game is up, so a restart would not help; the task fails as it did before.
    o = run_child(__file__)["never"]
    assert (o["stops"], o["starts"]) == (0, 0), json.dumps(o)
    assert o["succeeded"] is False and o["stopped"] == 1 and "PassLost" in o["nodes"], json.dumps(o)


def test_every_stuck_node_goes_back_to_its_hub_the_daily_ones_through_daily_recover():
    # The daily pages have L3 only (spec 06): a hub left on StopTask would stop a frozen game's task instead of restarting it.
    from test_pipeline import load_nodes

    nodes = load_nodes()
    stucks = {name for name, node in nodes.items() if node.get("custom_recognition") == "StuckFlag"}
    hubs = {name: node["next"][0].split("]")[-1] for name, node in nodes.items() if node.get("next")}
    heads = {first: hub for hub, first in hubs.items() if first in stucks}
    assert set(heads) == stucks and len(stucks) == 8, sorted(stucks)
    for stuck, hub in heads.items():
        assert nodes[stuck]["next"] == [hub], stuck
        assert nodes[stuck]["custom_action"] == ("Recover" if hub == "MirrorHub" else "DailyRecover"), stuck


def test_a_main_window_tap_node_lasts_the_dead_taps():
    # A main-window tap with fewer hits than DEAD_TAPS would leave its hub nothing to tap before the game is restarted.
    from recovery import DEAD_TAPS
    from test_pipeline import load_nodes

    taps = {name: node.get("max_hit") for name, node in load_nodes().items()
            if node.get("custom_action") == "TapUntil" and "HomeReached" in node.get("all_of", [])}
    assert {"PassBanner", "MailOpen"} <= set(taps), taps
    assert all(hits is None or hits >= DEAD_TAPS for hits in taps.values()), taps


if __name__ == "__main__":
    child()
