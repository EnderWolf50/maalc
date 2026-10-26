"""ExpLuxcavation (#366): from wherever the last task left the game to the main window, Drive, Luxcavation's EXP tab
and the rightmost open stage's Enter; one battle later, back to the main window, a success. ThreadLuxcavation (#368):
the same to the Thread tab's open card, its Level Select and that list's bottom row.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen, taps and the back
key that move between them. Enter opens the team page (LuxTeamSelect.png): the model picks the TEAMS row and To
Battle! there. The pages after To Battle! (level warning, start confirm, battle, results) have no capture yet: the model
plays them as one unknown screen that gives way to the EXP tab again.
"""

import json

import numpy as np
from daily_child import ROOT, bind, game_class, inside, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)
DRIVE_TAB = (930, 600, 110, 80)
LUXCAVATION = (355, 97, 190, 125)  # Drive's Luxcavation button
EXP_TAB = (68, 234, 154, 60)
THREAD_TAB = (68, 304, 154, 60)
CARD_ENTER = (293, 462, 157, 36)  # the open card's Enter (LuxThread.png: Wrath's, at the left)
LEVEL_ENTERS = [(780, 243 + 101 * i, 100, 40) for i in range(3)]  # Lv40, Lv50, Lv60 of the Level Select; the last is the hardest
ENTERS = {"exp": (1000, 455, 240, 50), "locked": (660, 455, 240, 50)}  # stage 9's Enter: the rightmost, the middle card
TEAM_ROW = (75, 365, 110, 36)  # the TEAMS #3 row of the team page's list (LuxTeamSelect.png)
TO_BATTLE = (1070, 560, 150, 55)
FIGHT_SHOTS = 4  # screenshots the pages after Enter take before the EXP tab shows again: the first of them gray, the rest VICTORY

SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "exp": "LuxExp.png", "locked": "LuxExpLocked.png",
           "thread": "LuxThread.png", "team": "LuxTeamSelect.png", "scrolled": "LuxThreadScrolled.png", "levels": "LuxThreadLevels.png", "fight": None,
           "victory": "Victory.png"}


def child():
    """Run ExpLuxcavation from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
    actions, resource = load()
    (actions.ROOT / "config").mkdir()
    settings = json.loads((ROOT / "tests" / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    settings["teams"][1]["game_team"] = 3  # the row LuxTeamSelect.png has lit

    class Game(game_class()):
        """The screen the game shows and what a tap or the back key does there."""

        images = {name: screen(png) if png else np.full((720, 1280, 3), 40, np.uint8) for name, png in SCREENS.items()}

        def set(self, start, lux_tab="thread", after="thread"):
            self.screen, self.clicks, self.keys, self.shots, self.picked = start, [], [], 0, False
            self.stage = "exp" if start != "locked" else "locked"
            self.wins = True  # the battles end in VICTORY; False: they end with no victory screen
            self.lux_tab = lux_tab  # the tab Luxcavation opens on
            self.after = after  # the page a Thread battle ends on: "thread" or "levels"
            self.swipes = []

        def screencap(self):
            if self.screen == "fight":
                self.shots += 1
                if self.shots > FIGHT_SHOTS:
                    self.screen = self.stage
                elif self.shots > 1 and self.wins:
                    return self.images["victory"]
            return self.images[self.screen]

        def on_tap(self, x, y):
            s = self.screen
            if s == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif s == "main" and inside(DRIVE_TAB, x, y):
                self.screen = "drive"
            elif s == "drive" and inside(LUXCAVATION, x, y):
                self.screen = self.lux_tab  # the tab last left open
            elif s in ("thread", "scrolled") and inside(EXP_TAB, x, y):
                self.screen = self.stage
            elif s in ("exp", "locked") and inside(THREAD_TAB, x, y):
                self.screen = "thread"
            elif s == "thread" and inside(CARD_ENTER, x, y):
                self.screen = "levels"
            elif s == "levels" and inside(LEVEL_ENTERS[-1], x, y):
                self.screen, self.picked = "team", False
                self.stage = self.after
            elif s in ENTERS and inside(ENTERS[s], x, y):
                self.screen, self.picked = "team", False
            elif s == "team" and inside(TEAM_ROW, x, y):
                self.picked = True
            elif s == "team" and self.picked and inside(TO_BATTLE, x, y):
                self.screen, self.shots = "fight", 0
            return True

        def on_swipe(self, down, last):
            if abs(last[1] - down[1]) > abs(last[0] - down[0]):
                return True  # the team list's scroll: a drag up or down, not the Thread tab's swipe
            self.swipes.append((down, last))
            if self.screen == "scrolled" and last[0] - down[0] > 300:  # the finger to the right: the left cards show
                self.screen = "thread"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen in ("exp", "locked", "thread"):
                self.screen = "drive"
            elif keycode == 4 and self.screen == "levels":  # live 2026-10-26: back closes the Level Select
                self.screen = "thread"
            return True

    game = Game()
    game.set("main")
    tasker = bind(resource, game)
    out = {"error": None}
    # scenario: (task, start screen, team, count, battles that end in VICTORY, then for the Thread task the tab Luxcavation
    # opens on and the page a battle ends on); the main window shows 182 Modules, an EXP stage takes 3, a Thread level 2
    scenarios = {"drive": ("ExpLuxcavation", "drive", "b", 1, True), "locked": ("ExpLuxcavation", "locked", "b", 1, True),
                 "no_team": ("ExpLuxcavation", "drive", None, 1, True), "two": ("ExpLuxcavation", "drive", "b", 2, True),
                 "poor": ("ExpLuxcavation", "drive", "b", 61, True), "no_victory": ("ExpLuxcavation", "drive", "b", 1, False),
                 "thread": ("ThreadLuxcavation", "drive", "b", 1, True, "exp"),
                 "thread_on_thread": ("ThreadLuxcavation", "drive", "b", 1, True, "thread"),
                 "thread_scrolled": ("ThreadLuxcavation", "drive", "b", 1, True, "scrolled"),
                 "thread_two": ("ThreadLuxcavation", "drive", "b", 2, True, "exp"),
                 "thread_two_levels": ("ThreadLuxcavation", "drive", "b", 2, True, "exp", "levels"),
                 "thread_poor": ("ThreadLuxcavation", "drive", "b", 92, True, "exp"),
                 "thread_no_team": ("ThreadLuxcavation", "drive", None, 1, True, "exp"),
                 "thread_no_victory": ("ThreadLuxcavation", "drive", "b", 1, False, "exp")}
    for scenario, (task, start, team, count, wins, *rest) in scenarios.items():
        opts = {"count": count, "team": team, "retries": 0}
        (actions.ROOT / "config" / "settings.json").write_text(
            json.dumps({**settings, "luxcavation": {"exp": opts, "thread": opts}}), encoding="utf-8")
        game.set(start, *rest)
        game.wins = wins
        out[scenario] = {**result(tasker.post_task(task).wait().get(), game, actions), "swipes": game.swipes}
    print(json.dumps(out))


def test_exp_luxcavation_goes_home_first_enters_the_rightmost_open_stage_and_ends_home():
    out = run_child(__file__)
    o = out["drive"]
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # GoHome first (the Window tab), then Drive, Luxcavation, the EXP tab (Thread was open), stage 9's Enter, the team's
    # row (TEAMS #3) and To Battle!
    steps = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, EXP_TAB, ENTERS["exp"], TEAM_ROW, TO_BATTLE)
    assert [inside(box, *xy) for box, xy in zip(steps, taps)] == [True] * 7
    assert taps.count(taps[4]) == 1 and taps.count(taps[6]) == 1  # one battle
    # Back on the EXP tab after it: done, and GoHome again (the back key, then the Window tab)
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 8
    assert o["nodes"].count("LuxTeamSelect") == 1
    assert o["nodes"][:3] == ["ExpLuxcavation", "ExpHome", "ExpHub"] and o["nodes"][-1] == "TaskDone"


def enters(o):
    return [xy for xy in o["clicks"] if inside(ENTERS["exp"], *xy)]


def test_count_wins_are_fought_before_it_is_done():
    o = run_child(__file__)["two"]  # #367: a win counts, and the next battle starts from the same tab
    assert o["succeeded"], o["nodes"]
    assert len(enters(o)) == 2 and o["keys"] == [4]  # two Enters, one trip home at the end
    # each battle picks its team again: the row and To Battle! after each Enter
    assert len([xy for xy in o["clicks"] if inside(TEAM_ROW, *xy)]) == 2
    assert len([xy for xy in o["clicks"] if inside(TO_BATTLE, *xy)]) == 2


def test_modules_short_of_count_times_the_cost_skip_the_task_a_success_before_any_battle():
    # 61 x 3 = 183 > the 182 the main window shows: no Enter, only the way home
    o = run_child(__file__)["poor"]
    assert o["succeeded"] and enters(o) == [] and o["nodes"][-1] == "TaskDone"


def test_a_battle_with_no_victory_stops_the_task_instead_of_counting():
    # TODO(#367): a defeat sets no result yet (no capture of its screen)
    o = run_child(__file__)["no_victory"]
    assert o["succeeded"] is False and len(enters(o)) == 1


def test_exp_luxcavation_skips_a_locked_stage_on_the_right():
    o = run_child(__file__)["locked"]
    assert o["succeeded"]
    enters = [xy for xy in o["clicks"] if 440 <= xy[1] < 510]
    assert len(enters) == 1 and inside(ENTERS["locked"], *enters[0])


def test_exp_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child(__file__)["no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ExpLuxcavation"]


def test_exp_luxcavation_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ExpLuxcavation", "label": "$ExpLuxcavation", "entry": "ExpLuxcavation"} in interface["task"]
    assert {"name": "ThreadLuxcavation", "label": "$ThreadLuxcavation", "entry": "ThreadLuxcavation"} in interface["task"]


def level_enters(o):
    return [xy for xy in o["clicks"] if any(inside(box, *xy) for box in LEVEL_ENTERS)]


def test_thread_luxcavation_goes_home_first_taps_thread_the_open_card_and_the_bottom_level_then_ends_home():
    o = run_child(__file__)["thread"]  # #368: Luxcavation opened on the EXP tab
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # the team page after the Level Select's Enter (#366): the team's row, To Battle!
    boxes = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, THREAD_TAB, CARD_ENTER, LEVEL_ENTERS[-1], TEAM_ROW, TO_BATTLE)
    assert [inside(box, *xy) for box, xy in zip(boxes, taps)] == [True] * 8
    assert len(level_enters(o)) == 1  # the hardest level only, one battle: not Lv40 or Lv50
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 9  # GoHome again: the back key, the Window tab
    assert o["nodes"].count("LuxTeamSelect") == 1
    assert o["nodes"][:3] == ["ThreadLuxcavation", "ThreadHome", "ThreadHub"] and o["nodes"][-1] == "TaskDone"


def test_thread_luxcavation_on_the_thread_tab_does_not_tap_it():
    o = run_child(__file__)["thread_on_thread"]
    assert o["succeeded"], o["nodes"]
    assert not any(inside(THREAD_TAB, *xy) for xy in o["clicks"]) and len(level_enters(o)) == 1


def test_thread_luxcavation_swipes_a_tab_scrolled_away_from_its_open_card():
    o = run_child(__file__)["thread_scrolled"]  # LuxThreadScrolled.png: no Enter lit on show
    assert o["succeeded"], o["nodes"]
    assert len(o["swipes"]) == 1 and o["swipes"][0][1][0] - o["swipes"][0][0][0] > 300 and len(level_enters(o)) == 1


def test_thread_luxcavation_fights_count_wins_from_the_card_each_time():
    o = run_child(__file__)["thread_two"]
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 2 and o["keys"] == [4]
    assert len([xy for xy in o["clicks"] if inside(TEAM_ROW, *xy)]) == 2  # the team is picked again for each battle


def test_thread_luxcavation_counts_a_battle_that_ends_on_the_level_select():
    o = run_child(__file__)["thread_two_levels"]  # the Level Select shows after the battle: counted once, the next battle from it
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 1


def test_thread_luxcavation_skips_when_the_modules_do_not_cover_count_levels_at_2_each():
    o = run_child(__file__)["thread_poor"]  # 92 x 2 = 184 > the 182 the main window shows
    assert o["succeeded"] and level_enters(o) == [] and not any(inside(CARD_ENTER, *xy) for xy in o["clicks"])
    assert o["nodes"][-1] == "TaskDone"


def test_thread_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child(__file__)["thread_no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ThreadLuxcavation"]


def test_a_thread_battle_with_no_victory_stops_the_task_instead_of_counting():
    o = run_child(__file__)["thread_no_victory"]
    assert o["succeeded"] is False and len(level_enters(o)) == 1



def test_the_watchdog_counts_screens_not_the_luxcavation_hubs():
    # Review M5: StuckFlag skipped MirrorHub by name; ExpHub and ThreadHub reached the watchdog as if they were screens.
    # A hub is now the node whose next list names the Stuck node.
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import actions
    from test_pipeline import load_nodes

    nodes = load_nodes()
    context = MagicMock()
    context.get_node_data = lambda name: {"next": [{"name": n.split("]")[-1]} for n in nodes[name].get("next", [])]}
    seen = []
    see = actions.StuckFlag.see
    actions.StuckFlag.see = staticmethod(lambda kind, image: seen.append(kind))
    try:
        for stuck, hub in (("ExpStuck", "ExpHub"), ("ThreadStuck", "ThreadHub"), ("Stuck", "MirrorHub")):
            for k, name in enumerate((hub, "LuxExpEnter", "ExpText", stuck)):
                actions.STUCK.update(node=None, flag=None)
                context.tasker.get_node_detail.return_value = SimpleNamespace(name=name)
                argv = SimpleNamespace(node_name=stuck, image=None, task_detail=SimpleNamespace(node_id_list=[k + 1]))
                actions.StuckFlag().analyze(context, argv)
    finally:
        actions.StuckFlag.see = see
    assert seen == ["LuxExpEnter"] * 3


def test_each_battle_has_its_own_retries_a_win_resets_them():
    # Review S6, as the mirror's wipe retries: retries 1 lets every battle lose once; the task fails only when one battle
    # loses twice.
    from unittest.mock import MagicMock

    import actions

    stops = []
    actions.RUN.clear()
    actions.RUN["lux"] = {"name": "EXP", "cost": 3, "count": 3, "retries": 1, "modules": 99, "won": 0, "retried": 0, "result": None}
    saved = actions.stop
    actions.stop = lambda context, reason, **kw: stops.append(reason) or False
    try:
        steps = []
        for result in ("lose", "win", "lose", "win", "lose", "lose"):
            actions.RUN.update(entered=True)
            actions.RUN["lux"]["result"] = result
            steps.append(actions.battle_over(MagicMock()))
    finally:
        actions.stop = saved
        actions.RUN.clear()
    assert steps == [None] * 5 + [False] and len(stops) == 1

if __name__ == "__main__":
    child()
