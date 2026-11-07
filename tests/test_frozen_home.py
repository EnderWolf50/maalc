"""A game frozen on the main window (#440, spec 06): the bot knows the screen, and no tap changes it. The real
ClaimPassMissions task in a child process (daily_child.py), on a model of the game whose main window takes no tap until
the game is restarted; and on a live main window, whose picture keeps moving, that takes the banner's tap late or never.
"""

import json

import numpy as np
from daily_child import GAME, bind, game_class, inside, live_frame, load, result, run_child, screen
from test_pass_task import BANNER, MISSIONS_TAB, SEASONAL_TAB, WEEKLY_TAB

TITLE_TAP = (540, 300, 200, 120)
SCREENS = {"main": "MainWindow.png", "title": "Title.png", "pass": "PassBattlePass.png", "daily": "PassMissionsDaily.png",
           "weekly": "PassMissionsWeekly.png", "seasonal": "PassMissionsSeasonal.png",
           "seasonal_end": "PassMissionsSeasonalEnd.png"}
HUB_TIMEOUT = 5000  # PassHub's 60 s, cut short: a pass page that never opens fails the task in 5 s


def child():
    """Run ClaimPassMissions from the main window of each scenario; print one JSON line."""
    actions, resource = load()

    class Game(game_class()):
        images = {**{name: screen(png) for name, png in SCREENS.items()}, "black": np.zeros((720, 1280, 3), np.uint8)}
        images["main_moved"] = live_frame(images["main"])

        def set(self, frozen=False, live=False, ignored=0, ignored_after=0):
            """frozen: the main window takes no tap and shows the same picture until the game restarts. live: the main
            window's picture moves at every screenshot. ignored: the banner taps the game lets go by before one opens the
            pass page (None: none does); ignored_after: the same, once the game restarted."""
            self.screen, self.focus, self.frozen, self.live, self.ignored = "main", GAME, frozen, live, ignored
            self.ignored_after = ignored_after
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
                self.screen = "main"
            elif self.screen == "main" and inside(BANNER, x, y):
                if self.ignored is None or self.ignored > 0:
                    self.ignored = self.ignored and self.ignored - 1
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
            self.focus, self.screen, self.live = GAME, "title", True  # the restarted game is live again
            self.ignored = self.ignored_after
            return True

    game = Game()
    game.set()
    # MaaFramework's Linux build (CI) passes no post_shell to a custom controller: read the model's dumpsys directly.
    actions.foreground = lambda context: actions.recovery.focused_package(game.shell("dumpsys window", 0))
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (model, restarts_used) in {
        "frozen": ({"frozen": True}, 0),
        # the restarted game lets the banner's first tap go by: its 4th tap in all, past PassBanner's max_hit 3
        "frozen_late": ({"frozen": True, "ignored_after": 1}, 0),
        "frozen_restarts_used": ({"frozen": True}, actions.recovery.L3_PER_EXECUTION),
        "late": ({"live": True, "ignored": 1}, 0),
        "never": ({"live": True, "ignored": None}, 0),
    }.items():
        game.set(**model)
        actions.STUCK["l3"] = restarts_used
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stopped = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        detail = tasker.post_task("ClaimPassMissions", {"PassHub": {"timeout": HUB_TIMEOUT}}).wait().get()
        out[scenario] = {**result(detail, game, actions), "starts": game.starts, "stops": game.stops,
                         "tapped_frozen": game.tapped_frozen, "l3": actions.STUCK["l3"],
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stopped,
                         "log": list(actions.LOG)[-40:]}
        actions.LOG.clear()
    print(json.dumps(out))


def test_a_main_window_that_takes_no_tap_restarts_the_game_and_the_task_goes_on():
    o = run_child(__file__)["frozen"]
    assert (o["stops"], o["starts"], o["l3"]) == (1, 1, 1), json.dumps(o)
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


def test_a_frozen_main_window_with_the_restarts_used_up_ends_the_task_through_the_stop_procedure():
    o = run_child(__file__)["frozen_restarts_used"]
    assert o["succeeded"] is False and (o["stops"], o["starts"]) == (0, 0) and o["stopped"] == 1, json.dumps(o)


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
