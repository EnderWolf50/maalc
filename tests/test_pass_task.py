"""ClaimPassMissions (#371, spec 00 daily tasks): the real task in a child process (daily_child.py), on a model of the
game: a screenshot per screen, and the taps and the back key that move between them.
"""

import json

from daily_child import ROOT, bind, game_class, inside, load, result, run_child, screen

BANNER = (940, 190, 270, 90)  # the Limbus Pass banner on the main window
MISSIONS_TAB = (305, 38, 140, 38)
WEEKLY_TAB = (256, 350, 30, 100)
COIN = (350, 205, 40, 40)  # the weekly tab's first row
SCREENS = {"main": "MainWindow.png", "pass": "PassBattlePass.png", "daily": "PassMissionsDaily.png",
           "weekly": "PassMissionsWeekly.png", "weekly_claimable": "PassMissionsWeeklyClaimable.synthetic.png"}


def child():
    """Run ClaimPassMissions from the main window, nothing to claim and a weekly row to claim; print one JSON line."""
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) for name, png in SCREENS.items()}

        def set(self, claimable):
            self.screen, self.claimable, self.clicks, self.keys = "main", claimable, [], []

        def on_tap(self, x, y):
            if self.screen == "main" and inside(BANNER, x, y):
                self.screen = "pass"
            elif self.screen == "pass" and inside(MISSIONS_TAB, x, y):
                self.screen = "daily"
            elif self.screen == "daily" and inside(WEEKLY_TAB, x, y):
                self.screen = "weekly_claimable" if self.claimable else "weekly"
            elif self.screen == "weekly_claimable" and inside(COIN, x, y):
                self.screen = "weekly"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen != "main":  # the pass pages have no tab bar: back is the main window
                self.screen = "main"
            return True

    game = Game()
    game.set(False)
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, claimable in {"nothing": False, "claim": True}.items():
        game.set(claimable)
        out[scenario] = result(tasker.post_task("ClaimPassMissions").wait().get(), game, actions)
    print(json.dumps(out))


def test_nothing_to_claim_visits_both_tabs_and_ends_on_the_main_window():
    o = run_child(__file__)["nothing"]
    assert o["succeeded"] and o["screen"] == "main"
    assert [inside(BANNER, *o["clicks"][0]), inside(MISSIONS_TAB, *o["clicks"][1]), inside(WEEKLY_TAB, *o["clicks"][2])] == [True] * 3
    assert len(o["clicks"]) == 3 and o["keys"] == [4]  # the back key leaves the pass page
    assert o["nodes"][-1] == "TaskDone"


def test_a_weekly_row_to_claim_is_tapped_once():
    o = run_child(__file__)["claim"]
    assert o["succeeded"] and o["screen"] == "main" and o["nodes"][-1] == "TaskDone"
    assert [inside(COIN, *c) for c in o["clicks"]] == [False, False, False, True]


def test_claim_pass_missions_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ClaimPassMissions", "label": "$ClaimPassMissions", "entry": "ClaimPassMissions"} in interface["task"]


if __name__ == "__main__":
    child()
