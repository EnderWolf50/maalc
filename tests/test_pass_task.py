"""ClaimPassMissions (#371, spec 00 daily tasks): the real task in a child process (daily_child.py), on a model of the
game: a screenshot per screen, and the taps and the back key that move between them.
"""

import json

from daily_child import bind, game_class, inside, interface as interface_json, load, result, run_child, screen

BANNER = (940, 190, 270, 90)  # the Limbus Pass banner on the main window
MISSIONS_TAB = (305, 38, 140, 38)
WEEKLY_TAB = (256, 350, 30, 100)
SEASONAL_TAB = (256, 490, 30, 100)  # live 2026-10-27, (270, 540)
COINS = [(350, y - 20, 40, 40) for y in (312, 400, 487, 575)]  # PassMissionsDailyClaimable.png's rows to claim, top to bottom
END_COIN = (350, 215, 40, 40)  # the swiped Seasonal tab's first row, 10 px lower
SCREENS = {"main": "MainWindow.png", "pass": "PassBattlePass.png", "daily": "PassMissionsDaily.png",
           "weekly": "PassMissionsWeekly.png",
           "seasonal": "PassMissionsSeasonal.png", "seasonal_end": "PassMissionsSeasonalEnd.png"}


def child():
    """Run ClaimPassMissions from the main window: nothing to claim, four daily rows (live 2026-10-27), a row at the
    Seasonal tab's end; print one JSON line."""
    actions, resource = load()
    from test_pass_missions import daily_claimed, seasonal_end_claimable

    class Game(game_class()):
        images = {**{name: screen(png) for name, png in SCREENS.items()}, "seasonal_end_claimable": seasonal_end_claimable(),
                  **{f"daily_{k}": daily_claimed(k) for k in range(4)}}

        def set(self, claimable):
            self.screen, self.claimable, self.clicks, self.keys, self.swipes = "main", claimable, [], [], []

        def on_tap(self, x, y):
            if self.screen == "main" and inside(BANNER, x, y):
                self.screen = "pass"
            elif self.screen == "pass" and inside(MISSIONS_TAB, x, y):
                self.screen = "daily_0" if self.claimable == "daily" else "daily"
            elif self.screen.startswith("daily_") and inside(COINS[k := int(self.screen[-1])], x, y):
                self.screen = f"daily_{k + 1}" if k < 3 else "daily"  # each tap claims its row
            elif self.screen == "daily" and inside(WEEKLY_TAB, x, y):
                self.screen = "weekly"
            elif self.screen == "weekly" and inside(SEASONAL_TAB, x, y):
                self.screen = "seasonal"
            elif self.screen == "seasonal_end_claimable" and inside(END_COIN, x, y):
                self.screen = "seasonal_end"
            return True

        def on_swipe(self, down, last):
            self.swipes.append([*down, *last])
            if self.screen == "seasonal" and last[1] < down[1]:  # up: the list's end
                self.screen = "seasonal_end_claimable" if self.claimable == "seasonal" else "seasonal_end"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen != "main":  # the pass pages have no tab bar: back is the main window
                self.screen = "main"
            return True

    game = Game()
    game.set(False)
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, claimable in {"nothing": None, "claim": "daily", "seasonal": "seasonal"}.items():
        game.set(claimable)
        out[scenario] = {**result(tasker.post_task("ClaimPassMissions").wait().get(), game, actions), "swipes": game.swipes}
    print(json.dumps(out))


def test_nothing_to_claim_visits_the_three_tabs_swipes_the_seasonal_once_and_ends_on_the_main_window():
    o = run_child(__file__)["nothing"]
    assert o["succeeded"] and o["screen"] == "main"
    assert [inside(box, *c) for box, c in zip((BANNER, MISSIONS_TAB, WEEKLY_TAB, SEASONAL_TAB), o["clicks"])] == [True] * 4
    assert len(o["clicks"]) == 4 and o["keys"] == [4]  # the back key leaves the pass page
    assert len(o["swipes"]) == 1 and o["nodes"].count("PassSeasonalSwipe") == 1  # D9: one swipe, never a run of them
    assert o["nodes"][-1] == "TaskDone"
    assert o["done"] == "pass missions: nothing to claim"  # live-1 F6: not "claimed" when nothing was


def test_each_daily_row_to_claim_is_tapped_once_top_to_bottom():
    o = run_child(__file__)["claim"]
    assert o["succeeded"] and o["screen"] == "main" and o["nodes"][-1] == "TaskDone"
    assert [inside(box, *c) for box, c in zip(COINS, o["clicks"][2:6])] == [True] * 4 and len(o["clicks"]) == 8
    assert o["done"] == "pass missions: 4 row(s) claimed"


def test_a_seasonal_row_below_the_first_five_is_tapped_after_the_swipe():
    o = run_child(__file__)["seasonal"]
    assert o["succeeded"] and o["screen"] == "main" and o["nodes"][-1] == "TaskDone"
    assert inside(END_COIN, *o["clicks"][-1]) and len(o["clicks"]) == 5 and len(o["swipes"]) == 1
    assert "PassSeasonalEndClaim" in o["nodes"] and o["done"] == "pass missions: 1 row(s) claimed"


def test_claim_pass_missions_is_a_task_of_the_interface():
    interface = interface_json()
    assert {"name": "ClaimPassMissions", "label": "$ClaimPassMissions", "entry": "ClaimPassMissions"} in interface["task"]


if __name__ == "__main__":
    child()
