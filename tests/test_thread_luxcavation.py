"""ThreadLuxcavation (#368): from wherever the last task left the game to the main window, Drive, Luxcavation's
Thread tab, its open card, the Level Select and that list's bottom row; one battle later, back to the main window, a
success. The game model and the child are test_exp_luxcavation.py's, run here for this task alone.
"""

from daily_child import inside, interface as interface_json, run_child
from test_exp_luxcavation import (CARD_ENTER, CONFIRM_TAP, DRIVE_TAB, EVENT_CARD, EVENT_PORTRAITS, LEVEL_ENTERS, LOSE,
                                  LUXCAVATION, TEAM_ROW, THREAD_TAB, TO_BATTLE, VERY_HIGH, WIN, WINDOW_TAB, child,
                                  confirms, title_taps)

# test_exp_luxcavation.py's SCENARIOS shape; a Thread level takes 2 Modules.
SCENARIOS = {"thread": ("drive", "b", 1, 0, WIN, "exp"), "thread_on_thread": ("drive", "b", 1, 0, WIN, "thread"),
             "thread_scrolled": ("drive", "b", 1, 0, WIN, "scrolled"), "thread_two": ("drive", "b", 2, 0, WIN, "exp"),
             "thread_two_levels": ("drive", "b", 2, 0, WIN, "exp", "levels"),
             "thread_poor": ("drive", "b", 92, 0, WIN, "exp"), "thread_no_team": ("drive", None, 1, 0, WIN, "exp"),
             "thread_no_result": ("drive", "b", 1, 0, [None], "exp"),
             "thread_lose_retry": ("drive", "b", 1, 1, LOSE + WIN, "exp"), "thread_lose_out": ("drive", "b", 1, 0, LOSE, "exp"),
             "thread_event": ("drive", "b", 1, 0, WIN, "exp"),
             "thread_x3": ("drive", "b", 3, 0, WIN, "exp"), "thread_x3_off": ("drive", "b", 3, 0, WIN, "exp"),
             "thread_x12": ("drive", "b", 12, 0, WIN, "exp"),
             "thread_done_today": ("drive", "b", 3, 0, WIN, "exp"), "thread_one_today": ("drive", "b", 1, 0, WIN, "exp"),
             "thread_bonuses_unread": ("drive", "b", 3, 0, WIN, "exp"), "thread_daily": ("drive", "b", 1, 0, WIN, "exp"),
             "thread_count_spent": ("drive", "b", 2, 0, WIN, "exp")}
CONSECUTIVE = {"thread_x3", "thread_x12"}
DAILY = {"thread_done_today", "thread_one_today", "thread_bonuses_unread", "thread_daily"}
# #429: the Daily Bonuses n/3 (n left; the model's default 3/3, a fresh day): 0/3 three won today, 2/3 one, blank.
STATES = {"thread_done_today": {"bonuses": 0}, "thread_one_today": {"bonuses": 2}, "thread_bonuses_unread": {"bonuses": None},
          "thread_count_spent": {"bonuses": 0}}


def test_thread_luxcavation_is_a_task_of_the_interface():
    interface = interface_json()
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


def test_thread_consecutive_off_fights_one_battle_at_a_time_and_never_touches_the_box():
    o = run_child(__file__)["thread_x3_off"]
    assert o["succeeded"], o["nodes"]
    assert o["fights"] == [1, 1, 1] and o["presses"] == [] and title_taps(o, "thread") == []


def test_thread_consecutive_is_set_on_the_card_and_carries_into_the_level_select():
    o = run_child(__file__)["thread_x3"]
    assert o["succeeded"], o["nodes"]
    assert o["presses"] == ["plus", "plus"] and title_taps(o, "level") == []  # the Level Select already shows x3
    assert o["fights"] == [3] and len(level_enters(o)) == 1 and "3 won" in o["done"]


def test_thread_consecutive_splits_more_than_ten_wins_too():
    o = run_child(__file__)["thread_x12"]
    assert o["succeeded"], o["nodes"]
    assert o["fights"] == [10, 2] and o["presses"] == ["ten", "plus"] and len(level_enters(o)) == 2


def test_daily_mode_fights_the_daily_bonuses_left_whatever_count_says():
    out = run_child(__file__)
    o = out["thread_done_today"]  # #429: Daily Bonuses 0/3, three won today: nothing fought
    assert o["succeeded"] and level_enters(o) == [] and not any(inside(CARD_ENTER, *xy) for xy in o["clicks"])
    assert o["done"] == "Thread Luxcavation: Daily Bonuses 0/3 (3 won today), 3 a day: nothing to fight"
    assert o["screen"] == "main" and o["nodes"][-1] == "TaskDone"
    o = out["thread_one_today"]  # 2/3: two left, count 1 unused (#431)
    assert o["succeeded"] and len(level_enters(o)) == 2 and o["done"] == "Thread Luxcavation: 2 won"
    o = out["thread_daily"]  # 3/3, a fresh day: three
    assert o["succeeded"] and len(level_enters(o)) == 3 and o["done"] == "Thread Luxcavation: 3 won"


def test_count_mode_fights_count_with_the_daily_bonuses_spent():
    o = run_child(__file__)["thread_count_spent"]  # #431: 0/3, count 2: two battles, the bonuses not read
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and o["done"] == "Thread Luxcavation: 2 won"


def test_thread_daily_bonuses_that_do_not_read_fight_nothing_and_end_a_success():
    o = run_child(__file__)["thread_bonuses_unread"]
    assert o["succeeded"] and level_enters(o) == [] and not any(inside(CARD_ENTER, *xy) for xy in o["clicks"])
    assert o["done"] == "Thread Luxcavation: Daily Bonuses did not read: nothing fought" and o["screen"] == "main"


def test_the_modules_are_checked_against_this_runs_battles():
    # #429: one won today leaves 2 of the day's 3, 4 Modules at 2 each: fought, where 3 x 2 = 6 would skip. #431: count
    # mode checks count's battles.
    from unittest.mock import MagicMock

    import actions

    ends = []
    saved = actions.finish
    actions.finish = lambda context, reason: ends.append(reason) or True
    actions.RUN.clear()
    actions.RUN["lux"] = {"name": "Thread Luxcavation", "cost": 2, "mode": "daily", "target": 3, "today": None, "seen": None,
                          "fights": None, "retries": 0, "modules": 4}
    try:
        assert actions.plan(MagicMock(), 1, "Daily Bonuses 2/3") is None and actions.RUN["lux"]["fights"] == 2 and ends == []
        actions.RUN["lux"].update(modules=3, fights=None)
        assert actions.plan(MagicMock(), 1, "Daily Bonuses 2/3") is True
        assert ends == ["Thread Luxcavation: Daily Bonuses 2/3 (1 won today), 3 a day: Modules 3 < 4 needed for 2, skipped"]
        actions.RUN["lux"].update(mode="count", target=91, modules=182, fights=None)
        assert actions.plan(MagicMock(), None, None) is None and actions.RUN["lux"]["fights"] == 91
        actions.RUN["lux"].update(modules=181, fights=None)
        assert actions.plan(MagicMock(), None, None) is True
        assert ends[-1] == "Thread Luxcavation: count mode, 91 this run: Modules 181 < 182 needed for 91, skipped"
    finally:
        actions.finish = saved
        actions.RUN.clear()


if __name__ == "__main__":
    child("ThreadLuxcavation", SCENARIOS, CONSECUTIVE, STATES, DAILY)
