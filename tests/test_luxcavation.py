import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
import lux_actions
import luxcavation
from luxcavation import EXP_COST, FIGHT, FINISH, RETRY, SKIP, STOP, batch, decide, needed, parse_consecutive, presses
from agent_patch import patch_all

if __name__ != "__main__":  # as test_task_chain.py: the fixtures are test_actions's
    from test_actions import Choices, clock, context  # noqa: F401 (the fake Maa context the in-process tests use)

SCREENS = Path(__file__).resolve().parent / "screens"


@pytest.mark.parametrize("task, today, fights", [
    ("exp", 0, 1), ("exp", 1, 0),  # the pass's Clear EXP Luxcavation row under way, done
    ("thread", 0, 3), ("thread", 1, 2), ("thread", 3, 0),  # Daily Bonuses 3/3, 2/3, 0/3
    ("exp", 2, 0),  # more won than the day's: nothing, not a negative count
    ("exp", None, None), ("thread", None, None),  # not read: nothing fought (#429)
])
def test_daily_mode_fights_what_the_day_still_needs(task, today, fights):
    assert luxcavation.fights("daily", luxcavation.DAILY[task], today) == fights


@pytest.mark.parametrize("count, today", [(1, None), (3, None), (2, 1), (12, 0)])
def test_count_mode_fights_count_whatever_today_holds(count, today):
    assert luxcavation.fights("count", count, today) == count


@pytest.mark.parametrize("texts, n", [
    (["Daily Bonuses", "0/3"], 0),  # tests/screens/LuxThread.png
    (["Daily Bonuses 2/3"], 2),
    (["3 / 3"], 3),
    (["0/4"], None),  # a cap that is not 3
    (["4/3"], None),  # more than the day has
    (["1/3", "2/3"], None),  # two: refuse
    (["Daily Bonuses"], None),
    ([], None),
])
def test_daily_bonuses_read_as_the_one_n_over_3(texts, n):
    assert luxcavation.read_bonuses(texts) == n


@pytest.mark.parametrize("count, cost, need", [(1, 3, 3), (2, 3, 6), (5, 3, 15), (3, 2, 6)])
def test_needed(count, cost, need):
    assert needed(cost, count) == need


def test_a_thread_battle_takes_2_modules_and_an_exp_battle_3():
    # #640 (luxcavation.py): live 2026-10-26, Thread Lv20-60 all take 2, EXP stages 4-9 take 3; actions.py reads them from here.
    assert (luxcavation.THREAD_COST, luxcavation.EXP_COST) == (2, 3)
    assert [lux_actions.LUX[k][1] for k in ("thread", "exp")] == [2, 3]
    thread = luxcavation.THREAD_COST
    assert decide(6, thread, 3, 0, 0, 0) == FIGHT  # the 3 bonuses of a day on exactly 6 Modules
    assert decide(5, thread, 3, 0, 0, 0) == SKIP


@pytest.mark.parametrize("modules, count, step", [
    (6, 2, FIGHT),  # exactly enough
    (5, 2, SKIP),  # one short: the log says "5 < 6"
    (0, 1, SKIP),
    (3, 1, FIGHT),
    (2, 1, SKIP),
    (182, 5, FIGHT),
])
def test_the_start_checks_the_modules_once_for_every_battle(modules, count, step):
    assert decide(modules, EXP_COST, count, 0, 0, 0) == step


@pytest.mark.parametrize("count, won, step", [
    (1, 0, FINISH),
    (2, 0, FIGHT),  # the first of two
    (2, 1, FINISH),  # the second of two
    (3, 1, FIGHT),
])
def test_a_win_counts_until_count_are_won(count, won, step):
    assert decide(0, EXP_COST, count, won, 0, 0, "win") == step  # modules no longer matter after the start


@pytest.mark.parametrize("retries, retried, step", [
    (0, 0, STOP),  # no retries: the task fails
    (1, 0, RETRY),
    (1, 1, STOP),  # used up
    (3, 2, RETRY),
    (3, 3, STOP),
])
def test_a_defeat_counts_for_nothing_and_plays_again_within_retries(retries, retried, step):
    assert decide(0, EXP_COST, 2, 1, retried, retries, "lose") == step


def test_a_win_after_retries_still_counts_once():
    assert decide(0, EXP_COST, 1, 0, 1, 1, "win") == FINISH


@pytest.mark.parametrize("count, won, consecutive, size", [
    (1, 0, True, 1), (3, 0, True, 3), (12, 0, True, 10), (12, 10, True, 2), (10, 0, True, 10),  # the rest, up to the game's 10
    (3, 0, False, 1), (12, 10, False, 1),  # off: one battle at a time
])
def test_a_consecutive_battle_takes_the_wins_left_up_to_ten(count, won, consecutive, size):
    assert batch(count, won, consecutive) == size


@pytest.mark.parametrize("count, won, size, step", [
    (3, 0, 3, FINISH),  # one x3 battle wins all three
    (12, 0, 10, FIGHT),  # x10 first, then the 2 left
    (12, 10, 2, FINISH),
])
def test_a_consecutive_win_counts_its_size(count, won, size, step):
    assert decide(0, EXP_COST, count, won, 0, 0, "win", size) == step


@pytest.mark.parametrize("read, n", [
    ("Consecutive Battle ×1", 1), ("Consecutive Battle × 10", 10), ("Consecutive Battle×9▼", 9), ("le×3", 3),
    ("Consecutive Battle X 4", 4), ("Consecutive Battle ×", None), ("Consecutive Battle ", None), ("", None),
    ("×0", None), ("×11", None),  # the game takes 1-10
])
def test_the_title_reads_as_its_count(read, n):
    assert parse_consecutive(read) == n


@pytest.mark.parametrize("now, target, taps", [
    (1, 1, []), (1, 2, ["plus"]), (1, 3, ["plus", "plus"]), (1, 10, ["ten"]), (10, 3, ["one", "plus", "plus"]),
    (9, 10, ["plus"]), (10, 9, ["minus"]), (5, 1, ["one"]), (7, 2, ["one", "plus"]), (4, 10, ["ten"]),
])
def test_the_buttons_to_press_are_the_fewest(now, target, taps):
    assert presses(now, target) == taps


def test_a_luxcavation_event_reads_its_choices_without_a_mirror_run_plan(context, monkeypatch):
    # J1: a Luxcavation battle's event has its task's team, no Mirror run plan; one made up from the settings would
    # go to runs.jsonl at the next stop.
    actions.RUN.clear()
    actions.RUN.update(lux={"name": "Thread Luxcavation"}, team={"keyword": "Burn"})
    page = Choices(context, monkeypatch, [("Option 0.", ""), ("Option 1.", "Select to gain a Burn E.G.O Gift")], ["Unknown story."])
    actions.Event().run(context, None)
    assert page.tapped == ["Option 1."] and "settings" not in actions.RUN


LUX_EVENT = {name: np.array(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]
             for name in ("LuxEventStory", "LuxEventCard", "LuxEventCheck", "LuxEventText", "EventStory", "EventCheck",
                          "EventChoices", "EventResult", "EventNotices")}


@pytest.mark.parametrize("name", LUX_EVENT)
def test_a_check_card_alone_is_told_from_every_other_event_page(name):
    # Live 2026-10-28 (J1): after SKIP, a Luxcavation event's check card shows alone at the right, SKIP grey; nothing
    # goes on until the card is tapped. Its prompt below, a result, a Choices list or no card: another page.
    assert actions.card_alone(LUX_EVENT[name]) == (name == "LuxEventCard")


def test_no_other_screen_is_a_check_card_alone():
    # CODING_STANDARDS, Recognition: the colour thresholds swept over every 720p capture of tests/screens; only the card
    # alone (live 2026-10-28, J1) hits.
    hits = [png.name for png in sorted(SCREENS.glob("*.png"))
            if (image := np.asarray(Image.open(png).convert("RGB"))[:, :, ::-1]).shape[:2] == (720, 1280) and actions.card_alone(image)]
    assert hits == ["LuxEventCard.png"]


def test_a_check_card_alone_is_tapped_to_open_its_prompt(context, monkeypatch):
    taps = []
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = (
        lambda: LUX_EVENT["LuxEventCheck"] if taps else LUX_EVENT["LuxEventCard"])
    actions.RUN.clear()
    actions.RUN.update(lux={"name": "Thread Luxcavation"}, team={"keyword": "Burn"})
    assert actions.Event().run(context, None) is True
    assert taps == [actions.EVENT_CARD] and "settings" not in actions.RUN


def run_set_consecutive(context, monkeypatch, reads, target, enter=None):
    """lux_actions.set_consecutive on the exp page with the title reading `reads` in turn (the last repeats); the taps made."""
    taps, reads = [], list(reads)
    patch_all(monkeypatch, "consecutive_now", lambda context, image, box, enter=None: reads.pop(0) if len(reads) > 1 else reads[0])
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    actions.LOG.clear()
    return lux_actions.set_consecutive(context, "exp", target, enter), taps


def test_the_consecutive_battle_logs_what_it_read_pressed_and_read_back(context, monkeypatch):
    # Acceptance 7 (M1): a run's log did not say what x N the bot found, which keys it pressed, or what it read after.
    got, taps = run_set_consecutive(context, monkeypatch, [1, 4], 4)
    assert got == 4 and len(taps) == 5  # open, + + +, close
    lines = [ln.split(" ", 1)[1] for ln in actions.LOG]
    assert lines == ["Consecutive Battle (exp): shows x1, wants x4",
                     "Consecutive Battle (exp): pressed plus, plus, plus",
                     "Consecutive Battle (exp): shows x4 after closing the row"]


def test_the_consecutive_battle_is_tapped_on_the_card_of_the_enter_in_use(context, monkeypatch):
    # Stage 9 in the middle (the 10th locked, LuxExpLocked.png): its Enter is 341 px left of the rightmost card's, and so is
    # the title to tap, the row and its buttons.
    _, right = run_set_consecutive(context, monkeypatch, [1, 2], 2, lux_actions.ENTER_AT["exp"])
    _, middle = run_set_consecutive(context, monkeypatch, [1, 2], 2, (lux_actions.ENTER_AT["exp"][0] - 341, lux_actions.ENTER_AT["exp"][1]))
    assert right == [(1110, 254), (1179, 286), (1110, 254)]
    assert middle == [(1110 - 341, 254), (1179 - 341, 286), (1110 - 341, 254)]


def test_the_consecutive_battle_already_at_its_count_logs_the_read_only(context, monkeypatch):
    got, taps = run_set_consecutive(context, monkeypatch, [3], 3)
    assert got == 3 and taps == []
    assert [ln.split(" ", 1)[1] for ln in actions.LOG] == ["Consecutive Battle (exp): shows x3, wants x3"]


def test_the_consecutive_battle_that_does_not_read_or_set_logs_it(context, monkeypatch):
    got, _ = run_set_consecutive(context, monkeypatch, [None], 4)
    assert got is None and [ln.split(" ", 1)[1] for ln in actions.LOG] == ["Consecutive Battle (exp): does not read, wants x4"]
    got, _ = run_set_consecutive(context, monkeypatch, [1, 2], 4)
    assert got == 2 and actions.LOG[-1].endswith("Consecutive Battle (exp): shows x2 after closing the row, wanted x4")


# The task's steps in actions.py, in process (#641): the branches the integration scenarios of test_exp_luxcavation.py
# and test_thread_luxcavation.py once ran in MaaFramework, test_actions.py's fake context around them.

def lux_start(context, monkeypatch, key, **opts):
    """LuxStart on the settings luxcavation.<key> = opts over a daily task of count 2 and team "b"; its return, the stops."""
    settings = json.loads((SCREENS.parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    settings["luxcavation"][key] = {"mode": "daily", "count": 2, "team": "b", "retries": 0, "consecutive": False, **opts}
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    stops = []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    # TaskStart starts a task afresh: its TASK and STUCK are put back after the test
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # as at launch: no task before it
    patch_all(monkeypatch, "STUCK", dict(actions.STUCK))
    entry = {"exp": "ExpLuxcavation", "thread": "ThreadLuxcavation"}[key]
    return lux_actions.LuxStart().run(context, SimpleNamespace(node_name=entry, custom_action_param=json.dumps(key))), stops


@pytest.mark.parametrize("key, mode, target, cost", [
    ("exp", "daily", 1, 3), ("thread", "daily", 3, 2),  # #431: daily mode fights to the day's battles, count 2 unused
    ("exp", "count", 2, 3), ("thread", "count", 2, 2),
])
def test_a_luxcavation_task_aims_at_the_days_battles_in_daily_mode_and_at_count_in_count_mode(context, monkeypatch, key, mode, target, cost):
    ok, stops = lux_start(context, monkeypatch, key, mode=mode)
    lux = actions.RUN["lux"]
    assert ok is True and stops == [] and (lux["mode"], lux["target"], lux["cost"], lux["fights"]) == (mode, target, cost, None)


@pytest.mark.parametrize("key, name", [("exp", "EXP Luxcavation"), ("thread", "Thread Luxcavation")])
def test_a_luxcavation_task_with_no_team_picked_stops_before_any_tap(context, monkeypatch, key, name):
    ok, stops = lux_start(context, monkeypatch, key, team=None)
    assert ok is False and stops == [f"{name} has no team: pick one in the settings GUI's Daily tab"]


def run_plan(monkeypatch, today, seen, **lux):
    """lux_actions.plan on RUN["lux"] = lux over an EXP task in daily mode with 182 Modules; its return, the finish reasons.
    The tests take the context fixture for its RUN cleared after them."""
    ends = []
    patch_all(monkeypatch, "finish", lambda context, reason: ends.append(reason) or True)
    actions.RUN.clear()
    actions.RUN["lux"] = {"name": "EXP Luxcavation", "cost": 3, "mode": "daily", "target": 1, "today": None, "seen": None,
                          "fights": None, "retries": 0, "modules": 182, **lux}
    return lux_actions.plan(MagicMock(), today, seen), ends


def test_the_modules_are_checked_against_this_runs_battles(context, monkeypatch):
    # #429: one won today leaves 2 of the day's 3, 4 Modules at 2 each: fought, where 3 x 2 = 6 would skip. #431: count
    # mode checks count's battles.
    thread = {"name": "Thread Luxcavation", "cost": 2, "target": 3}
    over, ends = run_plan(monkeypatch, 1, "Daily Bonuses 2/3", **thread, modules=4)
    assert over is None and actions.RUN["lux"]["fights"] == 2 and ends == []
    over, ends = run_plan(monkeypatch, 1, "Daily Bonuses 2/3", **thread, modules=3)
    assert over is True and ends == ["Thread Luxcavation: Daily Bonuses 2/3 (1 won today), 3 a day: Modules 3 < 4 needed for 2, skipped"]
    over, ends = run_plan(monkeypatch, None, None, **{**thread, "target": 91}, mode="count")
    assert over is None and actions.RUN["lux"]["fights"] == 91
    over, ends = run_plan(monkeypatch, None, None, **{**thread, "target": 91}, mode="count", modules=181)
    assert over is True and ends == ["Thread Luxcavation: count mode, 91 this run: Modules 181 < 182 needed for 91, skipped"]
    # EXP in count mode, 61 x 3 = 183 > the 182 the main window shows: skipped before any battle
    over, ends = run_plan(monkeypatch, None, None, mode="count", target=61)
    assert over is True and ends == ["EXP Luxcavation: count mode, 61 this run: Modules 182 < 183 needed for 61, skipped"]


@pytest.mark.parametrize("today, seen, end", [
    (1, "the pass's Clear EXP Luxcavation row done",  # #429: the day's one won: nothing fought
     "EXP Luxcavation: the pass's Clear EXP Luxcavation row done (1 won today), 1 a day: nothing to fight"),
    (None, "the pass's Clear EXP Luxcavation row did not read",  # #429 item 4: a day not read is a day not fought
     "EXP Luxcavation: the pass's Clear EXP Luxcavation row did not read: nothing fought"),
    (None, "the pass page was not reached in 60 s", "EXP Luxcavation: the pass page was not reached in 60 s: nothing fought"),
])
def test_daily_mode_with_nothing_left_or_nothing_read_ends_at_the_main_window_unfought(context, monkeypatch, today, seen, end):
    over, ends = run_plan(monkeypatch, today, seen)
    assert over is True and ends == [end] and actions.RUN["lux"]["fights"] is None


@pytest.mark.parametrize("png, found, param, today, seen", [
    ("PassMissionsDailyUnderway.png", True, None, 0, "the pass's Clear EXP Luxcavation row under way"),
    ("PassMissionsDaily.png", True, None, 1, "the pass's Clear EXP Luxcavation row done"),
    ("PassMissionsDailyUnderway.png", False, None, None, "the pass's Clear EXP Luxcavation row did not read"),
    ("PassMissionsDailyUnderway.png", False, '{"lost": true}', None, "the pass page was not reached in 60 s"),  # ExpPassLost
])
def test_the_pass_row_reads_as_the_battles_won_today(context, png, found, param, today, seen):
    # #429: ExpPassRead finds the row by its text (PassExpRow: row 2 of the Daily tab) and reads it by its look.
    image = np.array(Image.open(SCREENS / png).convert("RGB"))[:, :, ::-1]
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
    row = SimpleNamespace(hit=True, best_result=SimpleNamespace(box=(405, 285, 280, 27)))
    context.run_recognition.side_effect = lambda name, image: row if found and name == "PassExpRow" else None
    actions.RUN.clear()
    actions.RUN["lux"] = {"name": "EXP Luxcavation", "today": None, "seen": None}
    assert lux_actions.ExpPassRead().run(context, SimpleNamespace(custom_action_param=param)) is True
    assert (actions.RUN["lux"]["today"], actions.RUN["lux"]["seen"]) == (today, seen)
    assert context.tasker.controller.post_click.call_count == 0  # nothing tapped


def over_after(monkeypatch, results, **lux):
    """lux_actions.battle_over after each battle of results in turn (a result, or (result, its Consecutive Battle size)), from
    a fresh EXP task (lux over its defaults); the steps, the stop reasons and the finish reasons."""
    stops, ends, steps = [], [], []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    patch_all(monkeypatch, "finish", lambda context, reason: ends.append(reason) or True)
    actions.RUN.clear()
    actions.RUN["team"] = {"guard_turns": 0}
    actions.RUN["lux"] = {"name": "EXP", "cost": 3, "fights": 3, "retries": 1, "modules": 99, "won": 0, "retried": 0,
                          "result": None, "size": 1, **lux}
    for result in results:
        result, size = result if isinstance(result, tuple) else (result, 1)
        actions.RUN.update(entered=True)
        actions.RUN["lux"].update(result=result, size=size)
        steps.append(lux_actions.battle_over(MagicMock()))
    return steps, stops, ends


def test_each_battle_has_its_own_retries_a_win_resets_them(context, monkeypatch):
    # Review S6, as the mirror's wipe retries: retries 1 lets every battle lose once; the task fails only when one battle
    # loses twice.
    steps, stops, ends = over_after(monkeypatch, ("lose", "win", "lose", "win", "lose", "lose"))
    assert steps == [None] * 5 + [False] and stops == ["EXP: defeated with the 1 retries used up"] and ends == []


@pytest.mark.parametrize("retries, results", [(1, ("lose", "lose")), (0, ("lose",))])
def test_a_defeat_past_the_retries_stops_the_task(context, monkeypatch, retries, results):
    steps, stops, ends = over_after(monkeypatch, results, fights=1, retries=retries)
    assert steps == [None] * (len(results) - 1) + [False] and len(stops) == 1 and ends == []


def test_a_defeat_within_the_retries_counts_nothing_and_a_win_after_it_finishes(context, monkeypatch):
    # live-1 F2, F3: a red Defeat, Confirm, the same stage again. A Consecutive Battle x3 lost counts none of its three.
    steps, stops, ends = over_after(monkeypatch, ("lose", "win"), fights=1)
    assert steps == [None, True] and ends == ["EXP: 1 won"] and stops == []
    steps, stops, ends = over_after(monkeypatch, [("lose", 3)], fights=3)
    assert steps == [None] and (actions.RUN["lux"]["won"], actions.RUN["lux"]["retried"]) == (0, 1) and stops == ends == []


def test_a_consecutive_win_counts_all_its_battles(context, monkeypatch):
    steps, stops, ends = over_after(monkeypatch, [("win", 10), ("win", 2)], fights=12, retries=0)  # #375: x10, then x2
    assert steps == [None, True] and ends == ["EXP: 12 won"] and stops == []


def test_a_battle_with_no_results_page_stops_the_task_instead_of_counting(context, monkeypatch):
    steps, stops, ends = over_after(monkeypatch, [None])
    assert steps == [False] and stops == ["EXP: back on the page with no results page seen"] and ends == []
    assert actions.RUN["lux"]["won"] == 0


def test_each_battle_starts_its_guard_turns_afresh():
    # 2026-10-27 decision: the team's guard_turns count per battle, not once for the whole task.
    actions.RUN.clear()
    actions.RUN.update(team={"guard_turns": 2}, guard=0, entered=True)
    actions.RUN["lux"] = {"name": "EXP", "cost": 3, "fights": 2, "retries": 0, "modules": 99, "won": 0, "retried": 0, "result": "win", "size": 1}
    try:
        assert lux_actions.battle_over(MagicMock()) is None and actions.RUN["guard"] == 2
    finally:
        actions.RUN.clear()


CARD_ENTER = (293, 462, 157, 36)  # LuxThreadEnter's box on tests/screens/LuxThread.png
CARD_TAP = (293 + 157 // 2, 462 + 36 // 2)


def enter_card(context, monkeypatch, bonuses=(), box_shows=None, **lux):
    """LuxEnter on the Thread tab's card, its Daily Bonuses box reading `bonuses` (texts) and its Consecutive Battle box
    left at `box_shows`; its return, the taps of the Enter, the stops, the finish reasons and the OCR nodes read."""
    taps, stops, ends, reads = [], [], [], []
    patch_all(monkeypatch, "ocr_texts", lambda context, image, node: reads.append(node) or list(bonuses))
    patch_all(monkeypatch, "tap_then", lambda context, x, y, done, timeout=2.0: taps.append((x, y)) or "page")
    patch_all(monkeypatch, "set_consecutive", lambda context, box, target, enter=None: box_shows)
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    patch_all(monkeypatch, "finish", lambda context, reason: ends.append(reason) or True)
    actions.RUN.clear()
    actions.RUN["lux"] = {"name": "Thread Luxcavation", "cost": 2, "mode": "daily", "target": 3, "today": None, "seen": None,
                          "fights": None, "retries": 0, "modules": 182, "won": 0, "retried": 0, "result": None,
                          "consecutive": False, "size": 1, **lux}
    argv = SimpleNamespace(box=CARD_ENTER, node_name="LuxThreadEnter", custom_action_param=json.dumps({"opens_battle": False, "box": "thread"}))
    return lux_actions.LuxEnter().run(context, argv), taps, stops, ends, reads


@pytest.mark.parametrize("bonuses, fights, end", [
    (["Daily Bonuses", "3/3"], 3, None),  # a fresh day: all three
    (["Daily Bonuses", "1/3"], 1, None),
    (["Daily Bonuses", "0/3"], None, "Thread Luxcavation: Daily Bonuses 0/3 (3 won today), 3 a day: nothing to fight"),
    (["Daily Bonuses"], None, "Thread Luxcavation: Daily Bonuses did not read: nothing fought"),  # #429 item 4
])
def test_thread_in_daily_mode_plans_from_the_daily_bonuses_on_the_card(context, monkeypatch, bonuses, fights, end):
    ok, taps, stops, ends, reads = enter_card(context, monkeypatch, bonuses)
    assert ok is True and stops == [] and reads == ["ThreadBonuses"] and actions.RUN["lux"]["fights"] == fights
    assert (ends, taps) == (([], [CARD_TAP]) if end is None else ([end], []))  # nothing to fight: the card not entered


def test_a_task_planned_already_never_reads_the_daily_bonuses(context, monkeypatch):
    # #431: count mode plans in LuxHome; 0/3 (the bonuses spent) is not read, count's 2 battles go on
    ok, taps, stops, ends, reads = enter_card(context, monkeypatch, ["0/3"], mode="count", target=2, fights=2)
    assert ok is True and reads == [] and taps == [CARD_TAP] and stops == ends == []


@pytest.mark.parametrize("box_shows, why", [(None, "did not read"), (2, "shows x2")])
def test_a_consecutive_battle_that_does_not_read_or_set_stops_the_task_before_the_enter(context, monkeypatch, box_shows, why):
    ok, taps, stops, ends, _ = enter_card(context, monkeypatch, box_shows=box_shows, mode="count", target=3, fights=3, consecutive=True)
    assert ok is False and taps == [] and ends == []
    assert stops == [f"Thread Luxcavation: Consecutive Battle {why}, wanted x3"]
