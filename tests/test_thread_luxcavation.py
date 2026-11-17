"""ThreadLuxcavation (#368): from wherever the last task left the game to the main window, Drive, Luxcavation's
Thread tab, its open card, the Level Select and that list's bottom row; one battle later, back to the main window, a
success. The game model and the child are test_exp_luxcavation.py's, run here for this task alone; the task's
decisions are tested in process in test_luxcavation.py (#641).
"""

from daily_child import inside, interface as interface_json, run_child
from test_exp_luxcavation import (CARD_ENTER, CONFIRM_TAP, DRIVE_TAB, EVENT_CARD, EVENT_PORTRAITS, LEVEL_ENTERS, LUXCAVATION,
                                  TEAM_ROW, THREAD_TAB, TO_BATTLE, VERY_HIGH, WIN, WINDOW_TAB, child, confirms, title_taps)

# test_exp_luxcavation.py's SCENARIOS shape; a Thread level takes 2 Modules.
SCENARIOS = {"thread": ("drive", "b", 1, 0, WIN, "exp"), "thread_two_levels": ("drive", "b", 2, 0, WIN, "exp", "levels"),
             "thread_event": ("drive", "b", 1, 0, WIN, "scrolled"), "thread_x3": ("drive", "b", 3, 0, WIN, "thread"),
             "thread_frozen": ("main", "b", 1, 0, WIN, "exp")}
CONSECUTIVE = {"thread_x3"}
DAILY = {"thread"}
# #429: the Daily Bonuses n/3 (n left; the model's default 3/3, a fresh day): 2/3 one won today, two left; 0/3 all three
# spent, which count mode does not read (#431). #440: the game frozen on the main window until it restarts.
STATES = {"thread": {"bonuses": 2}, "thread_two_levels": {"bonuses": 0}, "thread_frozen": {"frozen": True}}


def test_thread_luxcavation_is_a_task_of_the_interface():
    interface = interface_json()
    assert {"name": "ThreadLuxcavation", "label": "$ThreadLuxcavation", "entry": "ThreadLuxcavation"} in interface["task"]


def level_enters(o):
    return [xy for xy in o["clicks"] if any(inside(box, *xy) for box in LEVEL_ENTERS)]


def test_thread_luxcavation_goes_home_first_taps_thread_the_open_card_and_the_bottom_level_then_ends_home():
    # #368: Luxcavation opened on the EXP tab. Daily mode (#429, #431): Daily Bonuses 2/3, two left, count 1 unused.
    o = run_child(__file__)["thread"]
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # the team page after the Level Select's Enter (#366): the team on the title already, To Battle!
    battle = (CARD_ENTER, LEVEL_ENTERS[-1], TO_BATTLE)
    boxes = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, THREAD_TAB, *battle)
    assert [inside(box, *xy) for box, xy in zip(boxes, taps)] == [True] * 7
    assert not [xy for xy in taps if inside(TEAM_ROW, *xy)] and o["drags"] == []
    assert taps[7] == CONFIRM_TAP  # the results page's Confirm, back on the Thread tab: the second battle from its card
    assert [inside(box, *xy) for box, xy in zip(battle, taps[8:])] == [True] * 3 and taps[11] == CONFIRM_TAP
    assert len(level_enters(o)) == 2 and o["nodes"].count("LuxResult") == 2  # the hardest level only: not Lv40 or Lv50
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 13  # GoHome again: the back key, the Window tab
    assert o["fights"] == [1, 1] and o["presses"] == []  # Consecutive Battle off: one battle at a time
    assert o["nodes"].count("LuxTeamSelect") == 2 and o["done"] == "Thread Luxcavation: 2 won"
    assert o["nodes"][:3] == ["ThreadLuxcavation", "ThreadHome", "ThreadHub"] and o["nodes"][-1] == "TaskDone"


def test_a_thread_task_on_a_frozen_main_window_restarts_the_game_and_fights_its_battle():
    # #440, live 2026-11-05: the Drive tab tapped 5 times, the same picture each time, then ThreadStuck stopped the task.
    o = run_child(__file__)["thread_frozen"]
    assert o["restarts"] == [1, 1] and "ThreadStuck" in o["nodes"], o["nodes"]
    assert o["succeeded"] and o["nodes"][-1] == "TaskDone" and len(level_enters(o)) == 1, o["nodes"]
    assert sum(inside(DRIVE_TAB, *xy) for xy in o["clicks"]) == 3  # 2 frozen, then the restarted game's


def test_thread_luxcavation_counts_a_battle_that_ends_on_the_level_select():
    o = run_child(__file__)["thread_two_levels"]  # the Level Select shows after the battle: counted once, the next battle from it
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 1
    assert o["done"] == "Thread Luxcavation: 2 won"  # count mode, #431: count's 2 with the Daily Bonuses spent (0/3)


def test_a_thread_battles_event_is_played_through_and_the_battle_goes_on():
    # J1 (live 2026-10-28): Glut's second wave showed an event; ThreadHub knew none of its screens and stopped after 60 s.
    out = run_child(__file__)
    o = out["thread_event"]
    assert o["succeeded"], o["nodes"]
    # Luxcavation opened on the Thread tab scrolled away from its open card (LuxThreadScrolled.png, no Enter lit): a swipe
    # to the right brings it back
    assert len(o["swipes"]) == 1 and o["swipes"][0][1][0] - o["swipes"][0][0][0] > 300
    assert "Event" in o["nodes"] and o["screen"] != "ev_text"
    taps = o["clicks"]
    assert len([xy for xy in taps if inside(EVENT_CARD, *xy)]) == 1  # the card alone, tapped once
    picks = [xy for xy in taps if inside(EVENT_PORTRAITS, *xy)]
    assert len(picks) == 1 and inside(VERY_HIGH, *picks[0])  # the best odds, not the Unselectable or a High
    assert len(level_enters(o)) == 1 and len(confirms(o)) == 1 and o["keys"] == out["thread"]["keys"]


def test_thread_consecutive_is_set_on_the_card_and_carries_into_the_level_select():
    o = run_child(__file__)["thread_x3"]  # Luxcavation opened on the Thread tab: it is not tapped
    assert o["succeeded"], o["nodes"]
    assert not any(inside(THREAD_TAB, *xy) for xy in o["clicks"])
    assert o["presses"] == ["plus", "plus"] and len(title_taps(o, "thread")) == 2  # the card's box: opened, + twice, closed
    assert title_taps(o, "level") == []  # the Level Select already shows x3
    assert o["fights"] == [3] and len(level_enters(o)) == 1 and o["done"] == "Thread Luxcavation: 3 won"
    assert o["nodes"].count("LuxTeamSelect") == 1  # Chain To Battle! on the team page


if __name__ == "__main__":
    child("ThreadLuxcavation", SCENARIOS, CONSECUTIVE, STATES, DAILY)
