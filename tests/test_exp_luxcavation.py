"""ExpLuxcavation (#366): from wherever the last task left the game to the main window, Drive, Luxcavation's EXP tab
and the rightmost open stage's Enter; one battle later, back to the main window, a success. ThreadLuxcavation (#368):
the same to the Thread tab's open card, its Level Select and that list's bottom row.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen, taps and the back
key that move between them. Enter opens the team page (LuxTeamSelect.png), its title already TEAMS #3: the team's row is neither tapped
nor dragged to, and the model takes To Battle! there. To Battle! goes straight to the battle (live 2026-10-27: no level warning, no start confirm); the model
plays it as an unknown screen, then the battlefield's VICTORY, then the results page (LuxResultVictory.png, LuxResultThread.png
or LuxResultDefeat.png), which stays until Confirm or the back key and leads back to the EXP or Thread tab.
"""

import json

import numpy as np
from daily_child import ROOT, bind, game_class, inside, interface as interface_json, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)
DRIVE_TAB = (930, 600, 110, 80)
LUXCAVATION = (355, 97, 190, 125)  # Drive's Luxcavation button
EXP_TAB = (68, 234, 154, 60)
THREAD_TAB = (68, 304, 154, 60)
CARD_ENTER = (293, 462, 157, 36)  # the open card's Enter (LuxThread.png: Wrath's, at the left)
LEVEL_ENTERS = [(780, 243 + 101 * i, 100, 40) for i in range(3)]  # Lv40, Lv50, Lv60 of the Level Select; the last is the hardest
ENTERS = {"exp": (1000, 455, 240, 50), "locked": (660, 455, 240, 50)}  # stage 9's Enter: the rightmost, the middle card
TEAM_ROW = (75, 365, 110, 36)  # the TEAMS #3 row of the team page's list (LuxTeamSelect.png), lit and on the title
TO_BATTLE = (1070, 560, 150, 55)
RESULT_CONFIRM = (1045, 540, 165, 60)  # the results page's Confirm (live 2026-10-27: (1125, 570))
# The bot's taps on To Battle! and on the results page's Confirm: each lies inside the other's box, so they are counted
# by the point.
TO_BATTLE_TAP, CONFIRM_TAP = [1145, 588], [1125, 570]
# A battle's event (live 2026-10-28, J1, LuxEvent*.png): the lit button bottom right (SKIP, Commence, Continue), the
# check's card alone at the right, the rightmost sinner of the check prompt (Very High).
EVENT_BUTTON = (1040, 612, 190, 66)
EVENT_CARD = (740, 110, 405, 140)
VERY_HIGH = (530, 620, 70, 70)
EVENT_PORTRAITS = (40, 620, 560, 70)
# The Consecutive Battle box (live 2026-10-27, tests/screens/LuxConsec*.png): a tap on the title opens its row, the row's
# buttons 1<<, -, +, >>10 change N from 1 to 10. Per page: title, row y, button xs.
BOX = {"exp": ((1110, 254), 286, {"one": 1008, "minus": 1038, "plus": 1179, "ten": 1209}),
       "thread": ((370, 226), 259, {"one": 272, "minus": 305, "plus": 436, "ten": 469}),
       "level": ((640, 183), 217, {"one": 530, "minus": 563, "plus": 716, "ten": 749})}
# The box moves with its card: the centre of the Enter under it on each page (LuxExp.png, LuxExpLocked.png, LuxThread.png), where
# BOX's numbers hold for stage 9 at the right and the Thread tab's card.
CARD = {"exp": (1079, 479), "locked": (738, 479), "thread": (372, 481)}
FIGHT_SHOTS = 4  # screenshots the battle takes before its results page: the first of them gray, the rest VICTORY on a win

SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "exp": "LuxExp.png", "locked": "LuxExpLocked.png",
           "thread": "LuxThread.png", "team": "LuxTeamSelect.png", "scrolled": "LuxThreadScrolled.png", "levels": "LuxThreadLevels.png", "fight": None,
           "victory": "Victory.png", "win": "LuxResultVictory.png", "thread_win": "LuxResultThread.png", "lose": "LuxResultDefeat.png",
           "ev_story": "LuxEventStory.png", "ev_card": "LuxEventCard.png", "ev_check": "LuxEventCheck.png",
           "ev_commence": "LuxEventCommence.png", "ev_passed": "LuxEventPassed.png", "ev_text": "LuxEventText.png",
           "ev_continue": "LuxEventContinue.png", "chain_team": "LuxTeamSelectChain.png"}
# Each event screen and the tap that leads on from it, live 2026-10-28: SKIP, the card, the Very High sinner, Commence,
# SKIP, a tap on the text once SKIP is grey (live: on the dialog; anywhere off the button here), Continue back to the battle.
EVENT_STEPS = {"ev_story": (EVENT_BUTTON, "ev_card"), "ev_card": (EVENT_CARD, "ev_check"), "ev_check": (VERY_HIGH, "ev_commence"),
               "ev_commence": (EVENT_BUTTON, "ev_passed"), "ev_passed": (EVENT_BUTTON, "ev_text"),
               "ev_continue": (EVENT_BUTTON, "fight")}


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
            self.screen, self.clicks, self.keys, self.shots = start, [], [], 0
            self.stage = "exp" if start != "locked" else "locked"
            self.outcomes = []  # each battle's end, in order: "win", "lose", or None (no results page: straight back to the tab)
            self.outcome = None
            self.lux_tab = lux_tab  # the tab Luxcavation opens on
            self.after = after  # the page a Thread battle ends on: "thread" or "levels"
            self.swipes = []
            self.drags = []  # the team list's
            self.event = False  # an event comes up on the battle's second screenshot
            self.reset_boxes()
            self.unread = False  # the Consecutive Battle title does not read
            self.fights = []  # the N each battle started with
            self.presses = []  # the box's buttons pressed, by name

        def reset_boxes(self):
            """The game's Consecutive Battle goes back to x1 on leaving Luxcavation and after a result (live 2026-10-28)."""
            self.n, self.open, self.fight_box = {"exp": 1, "thread": 1, "level": 1}, False, "exp"

        def box(self):
            """The Consecutive Battle box the page on show has: its key in BOX, None where there is none."""
            return {"exp": "exp", "locked": "exp", "thread": "thread", "levels": "level"}.get(self.screen)

        def shift(self):
            """How far the box on show lies from BOX's numbers: the card it is on is in the middle where stage 10 is locked."""
            card, home = CARD.get(self.screen), CARD.get(self.box())
            return (0, 0) if card is None else (card[0] - home[0], card[1] - home[1])

        def read(self, box, enter=None):
            """What the title reads at the roi LuxEnter hands over: nothing where the box is not, as on the real captures."""
            if self.unread or self.box() != box:
                return None
            card = CARD.get(self.screen)
            if card and (enter is None or abs(enter[0] - card[0]) > 20 or abs(enter[1] - card[1]) > 20):
                return None
            return self.n[box]

        def screencap(self):
            if self.screen == "fight":
                self.shots += 1
                if self.event and self.shots == 2:
                    self.event, self.screen = False, "ev_story"
                    return self.images["ev_story"]
                if self.shots > FIGHT_SHOTS:
                    self.screen = self.stage if self.outcome is None else "result"
                elif self.shots > 1 and self.outcome == "win":
                    return self.images["victory"]
            if self.screen == "team" and self.n[self.fight_box] > 1:
                return self.images["chain_team"]  # live 2026-10-28: Chain To Battle! after a Consecutive Battle x N
            if self.screen == "result":
                return self.images["thread_win" if self.outcome == "win" and self.after == "levels" else self.outcome]
            return self.images[self.screen]

        def on_tap(self, x, y):
            before = self.screen
            box = self.box()
            if box and self.tap_box(box, x, y):
                return True
            self.tap(x, y)
            if self.screen in ("drive", "main") or before == "result":
                self.reset_boxes()
            return True

        def tap_box(self, box, x, y):
            (title_x, title_y), row_y, buttons = BOX[box]
            dx, dy = self.shift()
            title_x, title_y, row_y, buttons = title_x + dx, title_y + dy, row_y + dy, {k: v + dx for k, v in buttons.items()}
            if abs(x - title_x) <= 40 and abs(y - title_y) <= 12:
                self.open = not self.open
                return True
            if not (self.open and abs(y - row_y) <= 12):
                return False
            for name, button_x in buttons.items():
                if abs(x - button_x) <= 14:
                    self.presses.append(name)
                    self.n[box] = {"one": 1, "minus": max(1, self.n[box] - 1), "plus": min(10, self.n[box] + 1), "ten": 10}[name]
                    return True
            return False

        def tap(self, x, y):
            s = self.screen
            if s in EVENT_STEPS and inside(EVENT_STEPS[s][0], x, y):
                self.screen = EVENT_STEPS[s][1]
            elif s == "ev_text" and not inside(EVENT_BUTTON, x, y):
                self.screen = "ev_continue"
            elif s == "drive" and inside(WINDOW_TAB, x, y):
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
                self.n["level"] = self.n["thread"]  # the Level Select starts from the card's N (live 2026-10-27)
            elif s == "levels" and inside(LEVEL_ENTERS[-1], x, y):
                self.screen, self.fight_box = "team", "level"
                self.stage = self.after
            elif s in ENTERS and inside(ENTERS[s], x, y):
                self.screen, self.fight_box = "team", "exp"
            elif s == "team" and inside(TO_BATTLE, x, y):
                self.screen, self.shots = "fight", 0
                self.fights.append(self.n[self.fight_box])
                self.outcome = self.outcomes.pop(0) if self.outcomes else "win"
            elif s == "result" and inside(RESULT_CONFIRM, x, y):
                self.screen = self.stage  # live: the EXP or the Thread tab, not the Level Select
            return True

        def on_swipe(self, down, last):
            if abs(last[1] - down[1]) > abs(last[0] - down[0]):
                self.drags.append((down, last))  # the team list's scroll: a drag up or down, not the Thread tab's swipe
                return True
            self.swipes.append((down, last))
            if self.screen == "scrolled" and last[0] - down[0] > 300:  # the finger to the right: the left cards show
                self.screen = "thread"
            return True

        def on_key(self, keycode):
            before = self.screen
            self.key(keycode)
            if self.screen in ("drive", "main") or before == "result":
                self.reset_boxes()
            return True

        def key(self, keycode):
            if keycode == 4 and self.screen in ("exp", "locked", "thread"):
                self.screen = "drive"
            elif keycode == 4 and self.screen == "levels":  # live 2026-10-26: back closes the Level Select
                self.screen = "thread"
            elif keycode == 4 and self.screen == "result":  # live 2026-10-27: back leaves the results page as Confirm does
                self.screen = self.stage
            return True

    game = Game()
    game.set("main")
    actions.consecutive_now = lambda context, image, box, enter=None: game.read(box, enter)
    tasker = bind(resource, game)
    out = {"error": None}
    # scenario: (task, start screen, team, count, retries, how the battles end, then for the Thread task the tab
    # Luxcavation opens on and the page a battle ends on); the main window shows 182 Modules, an EXP stage takes 3, a
    # Thread level 2. A battle the list does not reach ends in a win.
    win, lose = ["win"], ["lose"]
    scenarios = {"drive": ("ExpLuxcavation", "drive", "b", 1, 0, win), "locked": ("ExpLuxcavation", "locked", "b", 1, 0, win),
                 "no_team": ("ExpLuxcavation", "drive", None, 1, 0, win), "two": ("ExpLuxcavation", "drive", "b", 2, 0, win),
                 "poor": ("ExpLuxcavation", "drive", "b", 61, 0, win), "no_result": ("ExpLuxcavation", "drive", "b", 1, 0, [None]),
                 "lose_retry": ("ExpLuxcavation", "drive", "b", 1, 1, lose + win),
                 "lose_out": ("ExpLuxcavation", "drive", "b", 1, 1, lose + lose),
                 "lose_no_retries": ("ExpLuxcavation", "drive", "b", 1, 0, lose),
                 "thread": ("ThreadLuxcavation", "drive", "b", 1, 0, win, "exp"),
                 "thread_on_thread": ("ThreadLuxcavation", "drive", "b", 1, 0, win, "thread"),
                 "thread_scrolled": ("ThreadLuxcavation", "drive", "b", 1, 0, win, "scrolled"),
                 "thread_two": ("ThreadLuxcavation", "drive", "b", 2, 0, win, "exp"),
                 "thread_two_levels": ("ThreadLuxcavation", "drive", "b", 2, 0, win, "exp", "levels"),
                 "thread_poor": ("ThreadLuxcavation", "drive", "b", 92, 0, win, "exp"),
                 "thread_no_team": ("ThreadLuxcavation", "drive", None, 1, 0, win, "exp"),
                 "thread_no_result": ("ThreadLuxcavation", "drive", "b", 1, 0, [None], "exp"),
                 "thread_lose_retry": ("ThreadLuxcavation", "drive", "b", 1, 1, lose + win, "exp"),
                 "thread_lose_out": ("ThreadLuxcavation", "drive", "b", 1, 0, lose, "exp"),
                 "thread_event": ("ThreadLuxcavation", "drive", "b", 1, 0, win, "exp"),
                 # #375: the wins as Consecutive Battles (the names in `consecutive`), off for the rest
                 "x1": ("ExpLuxcavation", "drive", "b", 1, 0, win), "x3": ("ExpLuxcavation", "drive", "b", 3, 0, win),
                 "x3_off": ("ExpLuxcavation", "drive", "b", 3, 0, win), "x12": ("ExpLuxcavation", "drive", "b", 12, 0, win),
                 "x3_unread": ("ExpLuxcavation", "drive", "b", 3, 0, win),
                 "x3_lose_retry": ("ExpLuxcavation", "drive", "b", 3, 1, lose + win),
                 "thread_x3": ("ThreadLuxcavation", "drive", "b", 3, 0, win, "exp"),
                 "thread_x3_off": ("ThreadLuxcavation", "drive", "b", 3, 0, win, "exp"),
                 "thread_x12": ("ThreadLuxcavation", "drive", "b", 12, 0, win, "exp")}
    consecutive = {"x1", "x3", "x12", "x3_unread", "x3_lose_retry", "thread_x3", "thread_x12"}
    for scenario, (task, start, team, count, retries, outcomes, *rest) in scenarios.items():
        opts = {"count": count, "team": team, "retries": retries, "consecutive": scenario in consecutive}
        (actions.ROOT / "config" / "settings.json").write_text(
            json.dumps({**settings, "luxcavation": {"exp": opts, "thread": opts}}), encoding="utf-8")
        game.set(start, *rest)
        game.outcomes = list(outcomes)
        game.event = scenario == "thread_event"
        game.unread = scenario.endswith("_unread")
        out[scenario] = {**result(tasker.post_task(task).wait().get(), game, actions), "swipes": game.swipes, "drags": game.drags,
                         "fights": game.fights, "presses": game.presses}
    print(json.dumps(out))


def test_exp_luxcavation_goes_home_first_enters_the_rightmost_open_stage_and_ends_home():
    out = run_child(__file__)
    o = out["drive"]
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # GoHome first (the Window tab), then Drive, Luxcavation, the EXP tab (Thread was open), stage 9's Enter and To
    # Battle!: the team (TEAMS #3) is on the title already, its row neither tapped nor dragged to
    steps = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, EXP_TAB, ENTERS["exp"], TO_BATTLE)
    assert [inside(box, *xy) for box, xy in zip(steps, taps)] == [True] * 6
    assert taps.count(taps[4]) == 1 and taps.count(taps[5]) == 1  # one battle
    assert not [xy for xy in taps if inside(TEAM_ROW, *xy)] and o["drags"] == []
    # Its results page (live-1 F2): Victory read, Confirm, back on the EXP tab: done, and GoHome again (the back key,
    # then the Window tab)
    assert taps[6] == CONFIRM_TAP and o["nodes"].count("LuxResult") == 1
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 8
    assert o["nodes"].count("LuxTeamSelect") == 1
    assert o["nodes"][:3] == ["ExpLuxcavation", "ExpHome", "ExpHub"] and o["nodes"][-1] == "TaskDone"


def enters(o):
    return [xy for xy in o["clicks"] if inside(ENTERS["exp"], *xy)]


def test_count_wins_are_fought_before_it_is_done():
    o = run_child(__file__)["two"]  # #367: a win counts, and the next battle starts from the same tab
    assert o["succeeded"], o["nodes"]
    assert len(enters(o)) == 2 and o["keys"] == [4]  # two Enters, one trip home at the end
    # each battle looks for its team again: on the title already, To Battle! after each Enter
    assert not [xy for xy in o["clicks"] if inside(TEAM_ROW, *xy)] and o["drags"] == []
    assert o["clicks"].count(TO_BATTLE_TAP) == 2


def test_modules_short_of_count_times_the_cost_skip_the_task_a_success_before_any_battle():
    # 61 x 3 = 183 > the 182 the main window shows: no Enter, only the way home
    o = run_child(__file__)["poor"]
    assert o["succeeded"] and enters(o) == [] and o["nodes"][-1] == "TaskDone"


def test_a_battle_with_no_results_page_stops_the_task_instead_of_counting():
    o = run_child(__file__)["no_result"]
    assert o["succeeded"] is False and len(enters(o)) == 1


def confirms(o):
    return [xy for xy in o["clicks"] if xy == CONFIRM_TAP]


def test_a_defeat_counts_nothing_and_the_same_stage_is_played_again_within_the_retries():
    # live-1 F2, F3: the results page's red Defeat is the battle's result; Confirm, then the EXP tab's Enter again
    o = run_child(__file__)["lose_retry"]
    assert o["succeeded"], o["nodes"]
    assert len(enters(o)) == 2 and len(confirms(o)) == 2 and o["nodes"].count("LuxResult") == 2
    assert o["nodes"][-1] == "TaskDone" and "1 won" in o["done"]


def test_a_defeat_past_the_retries_ends_the_task_failed():
    out = run_child(__file__)
    for name, battles in (("lose_out", 2), ("lose_no_retries", 1)):
        o = out[name]
        assert o["succeeded"] is False and len(enters(o)) == battles and len(confirms(o)) == battles, name
        assert o["done"] is None, name


def test_exp_luxcavation_skips_a_locked_stage_on_the_right():
    o = run_child(__file__)["locked"]
    assert o["succeeded"]
    enters = [xy for xy in o["clicks"] if 440 <= xy[1] < 510]
    assert len(enters) == 1 and inside(ENTERS["locked"], *enters[0])


def test_exp_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child(__file__)["no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ExpLuxcavation"]


def test_exp_luxcavation_is_a_task_of_the_interface():
    interface = interface_json()
    assert {"name": "ExpLuxcavation", "label": "$ExpLuxcavation", "entry": "ExpLuxcavation"} in interface["task"]
    assert {"name": "ThreadLuxcavation", "label": "$ThreadLuxcavation", "entry": "ThreadLuxcavation"} in interface["task"]


def level_enters(o):
    return [xy for xy in o["clicks"] if any(inside(box, *xy) for box in LEVEL_ENTERS)]


def test_thread_luxcavation_goes_home_first_taps_thread_the_open_card_and_the_bottom_level_then_ends_home():
    o = run_child(__file__)["thread"]  # #368: Luxcavation opened on the EXP tab
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # the team page after the Level Select's Enter (#366): the team on the title already, To Battle!
    boxes = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, THREAD_TAB, CARD_ENTER, LEVEL_ENTERS[-1], TO_BATTLE)
    assert [inside(box, *xy) for box, xy in zip(boxes, taps)] == [True] * 7
    assert not [xy for xy in taps if inside(TEAM_ROW, *xy)] and o["drags"] == []
    assert len(level_enters(o)) == 1  # the hardest level only, one battle: not Lv40 or Lv50
    assert taps[7] == CONFIRM_TAP and o["nodes"].count("LuxResult") == 1  # the results page's Confirm
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
    assert not [xy for xy in o["clicks"] if inside(TEAM_ROW, *xy)] and o["drags"] == []  # on the title each battle


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


def test_a_thread_battle_with_no_results_page_stops_the_task_instead_of_counting():
    o = run_child(__file__)["thread_no_result"]
    assert o["succeeded"] is False and len(level_enters(o)) == 1


def test_a_thread_defeat_is_played_again_from_the_card_within_the_retries():
    out = run_child(__file__)
    o = out["thread_lose_retry"]
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len(confirms(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 2
    o = out["thread_lose_out"]
    assert o["succeeded"] is False and len(level_enters(o)) == 1 and len(confirms(o)) == 1



def test_a_thread_battles_event_is_played_through_and_the_battle_goes_on():
    # J1 (live 2026-10-28): Glut's second wave showed an event; ThreadHub knew none of its screens and stopped after 60 s.
    out = run_child(__file__)
    o = out["thread_event"]
    assert o["succeeded"], o["nodes"]
    assert "Event" in o["nodes"] and o["screen"] != "ev_text"
    taps = o["clicks"]
    assert len([xy for xy in taps if inside(EVENT_CARD, *xy)]) == 1  # the card alone, tapped once
    picks = [xy for xy in taps if inside(EVENT_PORTRAITS, *xy)]
    assert len(picks) == 1 and inside(VERY_HIGH, *picks[0])  # the best odds, not the Unselectable or a High
    assert len(level_enters(o)) == 1 and len(confirms(o)) == 1 and o["keys"] == out["thread"]["keys"]


def title_taps(o, box):
    (x, y), _, _ = BOX[box]
    return [xy for xy in o["clicks"] if abs(xy[0] - x) <= 40 and abs(xy[1] - y) <= 12]


def test_consecutive_sets_the_stage_to_the_wins_left_and_fights_them_as_one_battle():
    o = run_child(__file__)["x3"]  # #375: count 3 -> x3: the title opened, + twice, closed; one Enter, one battle, 3 won
    assert o["succeeded"], o["nodes"]
    assert o["presses"] == ["plus", "plus"] and len(title_taps(o, "exp")) == 2
    assert o["fights"] == [3] and len(enters(o)) == 1 and "3 won" in o["done"]
    assert o["nodes"].count("LuxTeamSelect") == 1  # the team page of a chain says Chain To Battle! and is known all the same


def test_consecutive_leaves_a_box_that_already_reads_the_wanted_count_alone():
    o = run_child(__file__)["x1"]
    assert o["succeeded"] and o["presses"] == [] and title_taps(o, "exp") == [] and o["fights"] == [1]


def test_consecutive_off_fights_one_battle_at_a_time_and_never_touches_the_box():
    for name, box in (("x3_off", "exp"), ("thread_x3_off", "thread")):
        o = run_child(__file__)[name]
        assert o["succeeded"], o["nodes"]
        assert o["fights"] == [1, 1, 1] and o["presses"] == [] and title_taps(o, box) == [], name


def test_consecutive_splits_more_than_ten_wins_into_ten_and_the_rest():
    o = run_child(__file__)["x12"]  # the game resets to x1 after a result: the second battle sets x2
    assert o["succeeded"], o["nodes"]
    assert o["fights"] == [10, 2] and o["presses"] == ["ten", "plus"] and len(enters(o)) == 2 and "12 won" in o["done"]


def test_consecutive_that_does_not_read_stops_the_task_before_any_battle():
    o = run_child(__file__)["x3_unread"]
    assert o["succeeded"] is False and o["fights"] == [] and enters(o) == [] and o["presses"] == []


def test_a_defeated_consecutive_battle_counts_nothing_and_is_set_and_fought_again():
    o = run_child(__file__)["x3_lose_retry"]
    assert o["succeeded"], o["nodes"]
    assert o["fights"] == [3, 3] and o["presses"] == ["plus", "plus"] * 2 and "3 won" in o["done"]


def test_thread_consecutive_is_set_on_the_card_and_carries_into_the_level_select():
    o = run_child(__file__)["thread_x3"]
    assert o["succeeded"], o["nodes"]
    assert o["presses"] == ["plus", "plus"] and title_taps(o, "level") == []  # the Level Select already shows x3
    assert o["fights"] == [3] and len(level_enters(o)) == 1 and "3 won" in o["done"]


def test_thread_consecutive_splits_more_than_ten_wins_too():
    o = run_child(__file__)["thread_x12"]
    assert o["succeeded"], o["nodes"]
    assert o["fights"] == [10, 2] and o["presses"] == ["ten", "plus"] and len(level_enters(o)) == 2


def test_each_battle_has_its_own_retries_a_win_resets_them():
    # Review S6, as the mirror's wipe retries: retries 1 lets every battle lose once; the task fails only when one battle
    # loses twice.
    from unittest.mock import MagicMock

    import actions

    stops = []
    actions.RUN.clear()
    actions.RUN["team"] = {"guard_turns": 0}
    actions.RUN["lux"] = {"name": "EXP", "cost": 3, "count": 3, "retries": 1, "modules": 99, "won": 0, "retried": 0, "result": None, "size": 1}
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


def test_each_battle_starts_its_guard_turns_afresh():
    # 2026-10-27 decision: the team's guard_turns count per battle, not once for the whole task.
    from unittest.mock import MagicMock

    import actions

    actions.RUN.clear()
    actions.RUN.update(team={"guard_turns": 2}, guard=0, entered=True)
    actions.RUN["lux"] = {"name": "EXP", "cost": 3, "count": 2, "retries": 0, "modules": 99, "won": 0, "retried": 0, "result": "win", "size": 1}
    try:
        assert actions.battle_over(MagicMock()) is None and actions.RUN["guard"] == 2
    finally:
        actions.RUN.clear()


if __name__ == "__main__":
    child()
