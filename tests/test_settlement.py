"""Settlement decisions, and Settle on the acceptance's Exploration Reward capture (#382).

The Settle cases run the real MaaFramework and its OCR in a child process (this file run as a script), as
test_consecutive_ocr.py does.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from daily_child import probe_child, run_child, screen

from settlement import NOT_SEEN, Result, all_hard, append_run, bonus_toggles, claim_bonuses, claim_dialog, claim_ok, counts_as_run, first_floor_hard, floors_passed, new_run_gate, now, read_result, runs_done, target_reached

if __name__ != "__main__":  # as test_luxcavation.py: the fixtures are test_actions's
    import actions
    from test_actions import clock, context  # noqa: F401 (the fake Maa context the in-process tests use)


@pytest.mark.parametrize("text, expected", [
    ("Floor 5 [NORMAL] 6/6", (5, "normal", 6, 6)),
    ("Floor 5 [HARD] 5/6", (5, "hard", 5, 6)),
    ("Floor 3 HARD 2 / 6", (3, "hard", 2, 6)),  # OCR may drop the brackets
    ("Floor 12 [HARD] 5/7", (12, "hard", 5, 7)),  # #383: floors run to 15
    ("Floor 15 [NORMAL] 6/6", (15, "normal", 6, 6)),
    ("Floor 12 [HARD] 12/12", (12, "hard", 12, 12)),  # #384: progress takes two digits
    # The INFINITY and EXTREME markers are a guess from the game data (uiConfig.difficultyLabel), no capture shows them.
    ("Floor 8 [INFINITY] 7/7", (8, "infinity", 7, 7)),
    ("Floor 15 [EXTREME] 9/9", (15, "extreme", 9, 9)),
    ("Floor 9 INFINITY 3 / 8", (9, "infinity", 3, 8)),
    ("Floor 8 [!NFINITY] 7/7", (8, None, 7, 7)),  # floor and progress read, the marker did not
    ("Floor 3 7/7", (3, None, 7, 7)),
    ("Floor 5", None),
    ("[HARD] 5/6", None),
    ("", None),
])
def test_read_result(text, expected):
    assert read_result(text) == expected


@pytest.mark.parametrize("difficulty, floor, hard", [
    ("normal", 5, False), ("hard", 3, True), ("infinity", 8, True), ("extreme", 15, True),
    (None, 3, None),  # an unread marker below floor 6 is neither
    (None, 8, True),  # floors 6 and up need every floor HARD
])
def test_hard_follows_the_marker_or_the_floor(difficulty, floor, hard):
    assert Result(floor, difficulty, 1, 1).hard is hard


@pytest.mark.parametrize("result, passed", [
    ((5, "normal", 6, 6), 5),
    ((5, "hard", 5, 6), 4),
    ((4, "hard", 6, 6), 4),
    ((1, "normal", 5, 5), 1),
    ((5, "hard", 7, 7), 5),  # live 2026-10-16: a HARD floor 5 may have 7 nodes
    ((5, "hard", 6, 7), 4),
    ((8, "infinity", 7, 7), 8),
    ((8, "infinity", 3, 7), 7),
    ((15, "extreme", 9, 9), 15),
])
def test_floors_passed(result, passed):
    assert floors_passed(Result(*result)) == passed


# The issue's four windows (target 15 for the first, 5 for the others) and the neighbours of floor 5 and of the target.
@pytest.mark.parametrize("text, target, claim, reached", [
    ("Floor 8 [INFINITY] 7/7", 15, True, False),  # past floor 5, short of the target: Claim
    ("Floor 15 [EXTREME] 9/9", 15, True, True),
    ("Floor 15 [EXTREME] 4/9", 15, True, False),  # died on floor 15: 14 floors passed
    ("Floor 5 [HARD] 6/6", 5, True, True),
    ("Floor 5 [HARD] 6/6", 10, True, False),
    ("Floor 3 [NORMAL] 2/6", 5, False, False),  # short of floor 5: give up
    ("Floor 5 [HARD] 5/7", 5, False, False),
    ("Floor 6 [HARD] 1/7", 5, True, True),  # floor 5 passed, then died on floor 6
    ("Floor 6 [HARD] 1/7", 10, True, False),
    ("Floor 12 [HARD] 12/12", 10, True, True),
    ("Floor 8 7/7", 15, True, False),  # no readable marker: the floors still decide
])
def test_claim_ok_and_target_reached(text, target, claim, reached):
    result = read_result(text)
    assert claim_ok(result) is claim
    assert target_reached(floors_passed(result), target) is reached


@pytest.mark.parametrize("text, target, expected", [
    ("Floor 5 [HARD] 6/6", 5, 3),  # reached: the toggles follow use and amount
    ("Floor 5 [NORMAL] 6/6", 5, 0),  # use is "hard": a NORMAL run takes none
    ("Floor 8 [INFINITY] 7/7", 15, 0),  # claimed short of the target: no toggle
    ("Floor 8 [INFINITY] 7/7", 8, 3),  # INFINITY counts as HARD
    ("Floor 15 [EXTREME] 9/9", 15, 3),
    ("Floor 5 6/6", 5, 0),  # an unread marker is never a guess to spend a bonus on
    ("Floor 8 7/7", 8, 0),
])
def test_claim_bonuses(text, target, expected):
    got = claim_bonuses(read_result(text), target, "hard", "all", 3, {f: True for f in range(1, 16)}, lambda: pytest.fail("the tile was read"))
    assert got == expected


def test_claim_bonuses_reads_the_first_tile_only_when_floors_are_missing():
    tiles = []
    assert claim_bonuses(read_result("Floor 5 [HARD] 6/6"), 5, "hard", "all", 3, {}, lambda: tiles.append(1) or "[HARD] Floor1") == 3
    assert tiles == [1]
    assert claim_bonuses(read_result("Floor 8 [INFINITY] 7/7"), 15, "hard", "all", 3, {}, lambda: tiles.append(2) or "[HARD] Floor1") == 0
    assert tiles == [1]


@pytest.mark.parametrize("use, amount, hard, left, all_hard, expected", [
    ("hard", "all", True, 3, True, 3),
    ("hard", "all", True, 2, True, 2),
    ("hard", "all", True, 3, False, 1),  # partly HARD: the game takes only one at a time
    ("hard", "one", True, 3, True, 1),
    ("hard", "all", False, 3, True, 0),  # a NORMAL run never uses a bonus meant for hard
    ("hard", "one", False, 3, False, 0),
    ("none", "all", True, 3, True, 0),
    ("normal", "all", False, 3, False, 1),
    ("normal", "all", True, 3, True, 0),
    ("hard", "all", True, 0, True, 0),  # used up
])
def test_bonus_toggles(use, amount, hard, left, all_hard, expected):
    assert bonus_toggles(use, amount, hard, left, all_hard) == expected


# The dialogs as OCR read them live (tests/screens: GiveUpDialog, ClaimNoBonusDialog, ClaimBonusDialog).
@pytest.mark.parametrize("text, expected", [
    ("End expedition without claiming rewards?", "giveup"),
    ("You have Weekly Bonus Eligibility remaining. Are you sure you want to claim the current rewards without using the Eligibility?", "no_bonus"),
    ("Spend your 'Weekly Bonuses, to claim the bonus rewards?", "bonus"),  # live 2026-10-16
    ("Spend your 「Weekly Bonuses」 to claim the bonus rewards?", "bonus"),
    ("Claim the rewards? UIEIR", "no_bonus"),  # live 2026-10-17: no weekly bonus left
    ("CLAIM THE REWARDS?", "no_bonus"),  # #138: case and spacing as OCR reads them
    ("End expedition withoutclaiming rewards?", "giveup"),
    ("", None),
    ("Would you like to move to the Window?", None),
])
def test_claim_dialog(text, expected):
    assert claim_dialog(text) == expected


@pytest.mark.parametrize("result, expected", [("clear", True), ("giveup", False), ("stop", False)])
def test_only_claimed_runs_count(result, expected):
    assert counts_as_run(result) is expected


@pytest.mark.parametrize("done, limit, expected", [(0, 1, False), (1, 1, True), (5, None, False), (2, 3, False)])  # None: the switch off, no limit (#137)
def test_runs_done(done, limit, expected):
    assert runs_done(done, limit) is expected


def test_append_run_keeps_reset_markers(tmp_path):
    log = tmp_path / "logs" / "runs.jsonl"
    log.parent.mkdir()
    log.write_text(json.dumps({"reset": "a", "time": "2026-10-15T00:00:00.000Z"}) + "\n", encoding="utf-8")
    append_run(tmp_path, {"team": "a", "team_name": "Ödön", "result": "clear"})
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert lines == [{"reset": "a", "time": "2026-10-15T00:00:00.000Z"}, {"team": "a", "team_name": "Ödön", "result": "clear"}]


def test_now_matches_the_gui_marker_format():
    assert len(now()) == len("2026-10-15T00:00:00.000Z") and now().endswith("Z")


@pytest.mark.parametrize(("seen", "backs", "expected"), [
    (4, 0, "done"), (0, 0, "done"), (5, 0, "go"), (182, 0, "go"), (None, 0, "go"),  # read on the Drive page
    (NOT_SEEN, 0, "back"), (NOT_SEEN, 1, "back"), (NOT_SEEN, 2, "go"),  # no Drive pass: back out twice, then unchecked
])
def test_new_run_gate(seen, backs, expected):
    assert new_run_gate(seen, backs) == expected


@pytest.mark.parametrize(("tile", "expected"), [
    ("[HARD] Floor1", True),  # what the OCR read on tests/screens/ExplorationRewardHard5.png
    ("[HARD] Floor 1", True),
    ("[NORMAL] Floor1", False),
    ("[HARD] Floor2", False),  # not the first tile
    ("[HARD]", False),
    ("", False),
])
def test_first_floor_hard(tile, expected):
    assert first_floor_hard(tile) is expected


@pytest.mark.parametrize(("floors_hard", "floor", "hard", "tile", "expected"), [
    ({f: True for f in range(1, 6)}, 5, True, "", True),  # every floor seen HARD: the tile is not read
    ({1: False, 2: True, 3: True, 4: True, 5: True}, 5, True, "[HARD] Floor1", False),  # seen NORMAL beats the tile
    ({4: True, 5: True}, 5, True, "[HARD] Floor1", True),  # a resumed run: floors 1-3 not seen, the tile says HARD
    ({}, 5, True, "[HARD] Floor1", True),  # no floor seen (the agent restarted)
    ({4: True, 5: True}, 5, True, "[NORMAL] Floor1", False),
    ({4: True, 5: True}, 5, True, "", False),  # unreadable: not all HARD
    ({}, 5, False, "[HARD] Floor1", False),  # the last floor NORMAL: the run is not HARD
    ({1: True, 2: True}, 3, True, "[HARD] Floor1", False),  # floor 3 not seen though floor 1 was
])
def test_all_hard(floors_hard, floor, hard, tile, expected):
    assert all_hard(floors_hard, floor, hard, lambda: tile) is expected


def test_the_floors_not_read_are_not_asked_for_when_all_were_seen():
    assert all_hard({1: True, 2: True}, 2, True, lambda: pytest.fail("the tile was read")) is True


def test_the_difficulty_each_floor_is_played_on_is_remembered(monkeypatch):
    # #382: all_hard comes from what the theme pack page showed per floor, not from the run's plan.
    import actions  # not at the top: the child (this file as a script) loads it under its AgentServer stand-in
    monkeypatch.setattr(actions, "text", lambda *a, **k: "HARD")
    monkeypatch.setattr(actions, "page_guard", lambda context, node, image=None: screen("MainWindow.png"))
    actions.RUN.clear()
    actions.RUN["floor_hard"] = None
    actions.PickThemePack.set_difficulty(MagicMock(), 4, True)
    assert actions.RUN["floors_hard"] == {4: True}
    actions.RUN.clear()


def test_a_new_runs_first_floor_forgets_the_floors_of_the_last_run(monkeypatch):
    # #382: a run that began on an expired session's dialog has no PlanRun to clear RUN; floor 1 does it.
    import actions
    monkeypatch.setattr(actions, "current_run", lambda context: {"difficulty": None, "team": {"hard_from_floor": None}, "settings": {"run": {}}})
    monkeypatch.setattr(actions, "screen", lambda context: None)
    monkeypatch.setattr(actions, "text", lambda *a, **k: "SELECT FLOOR 1 THEME PACK")
    monkeypatch.setattr(actions, "restart_floor_clock", lambda: None)
    monkeypatch.setattr(actions.PickThemePack, "set_difficulty", staticmethod(lambda context, floor, want: False))
    monkeypatch.setattr(actions, "stuck", lambda reason, level=1: True)
    actions.RUN.clear()
    monkeypatch.setattr(actions, "TASK", {"runs": 0, "done": None})  # a fresh task's, the module's own back after the test
    actions.RUN.update(floor=5, floors_hard={f: True for f in range(1, 6)})
    actions.PickThemePack().run(MagicMock(), SimpleNamespace(node_name="PickThemePack"))
    assert "floors_hard" not in actions.RUN and actions.RUN["floor"] == 1
    actions.RUN.clear()


def settle(context, monkeypatch, tmp_path, window, target, floors_hard=None):
    """Settle on a window reading `window` for a run with `target`, weekly bonuses "hard"/"all" with 3 left.

    The toggles are three switches that a tap on one flips. Returns (taps, ON toggles when Claim was tapped, the runs.jsonl line).
    """
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    monkeypatch.setattr(actions, "address", lambda context: "emulator")
    team = {"id": "a", "name": "A", "enabled": True}
    actions.RUN.update(settings={"run": {"weekly_bonus_use": "hard", "weekly_bonus_amount": "all", "target_floor": target}, "teams": [team]},
                       team=team, planned=True, floors_hard=floors_hard or {})
    taps, switches, on_at_claim = [], [False] * 3, []

    def tap(context, x, y, wait=1.0):
        taps.append((x, y))
        if (x, y) == actions.CLAIM:
            on_at_claim.append(sum(switches))
        elif y == 252:
            i = actions.TOGGLE_X.index(x)
            switches[i] = not switches[i]

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.RESULT:
            return [(window, (300, 420, 90, 20))]
        if roi == actions.WEEKLY_LEFT:
            return [("3/3", (440, 230, 40, 20))]
        if roi == actions.DIALOG_TEXT and actions.GIVE_UP in taps:
            return [("End expedition without claiming rewards?", (400, 300, 400, 30))]
        return []
    monkeypatch.setattr(actions, "ocr", ocr)
    monkeypatch.setattr(actions, "tap", tap)
    monkeypatch.setattr(actions, "toggles", lambda context, image: list(switches))
    assert actions.Settle().run(context, None)
    path = tmp_path / "logs" / "runs.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return taps, on_at_claim, lines


@pytest.mark.parametrize("window, target, claimed_on, floors, reached", [
    ("Floor 8 [INFINITY] 7/7", 15, 0, 8, False),  # past floor 5, short of the target: Claim, no toggle
    ("Floor 15 [EXTREME] 9/9", 15, 3, 15, True),  # reached: the toggles follow the settings
    ("Floor 5 [HARD] 6/6", 5, 3, 5, True),  # target 5 acts as it did
    ("Floor 6 [HARD] 1/7", 10, 0, 5, False),  # died on floor 6: floor 5 passed, Claim
    ("Floor 8 7/7", 8, 0, 8, True),  # marker unread: still Claim, never a bonus on a guess
])
def test_settle_claims_a_run_past_floor_5_and_toggles_bonuses_only_at_the_target(context, monkeypatch, tmp_path, window, target, claimed_on, floors, reached):
    taps, on_at_claim, lines = settle(context, monkeypatch, tmp_path, window, target, {f: True for f in range(1, 16)})
    assert actions.GIVE_UP not in taps and actions.CLAIM in taps
    assert on_at_claim == [claimed_on]
    assert [(line["result"], line["floors"], line["target_reached"], line["target"]) for line in lines] == [("clear", floors, reached, target)]


@pytest.mark.parametrize("window, difficulty", [("Floor 8 [INFINITY] 7/7", "hard"), ("Floor 5 [NORMAL] 6/6", "normal"), ("Floor 8 7/7", "hard"), ("Floor 5 6/6", None)])
def test_the_runs_line_keeps_difficulty_hard_normal_or_null(context, monkeypatch, tmp_path, window, difficulty):
    _, _, lines = settle(context, monkeypatch, tmp_path, window, 5)
    assert lines[0]["difficulty"] == difficulty


@pytest.mark.parametrize("window", ["Floor 3 [NORMAL] 2/6", "Floor 5 [HARD] 5/7", "Floor 4 4/4"])
def test_settle_gives_up_a_run_short_of_floor_5_even_with_an_unread_marker(context, monkeypatch, tmp_path, window):
    taps, _, lines = settle(context, monkeypatch, tmp_path, window, 15)
    assert taps == [actions.GIVE_UP, actions.DIALOG_CONFIRM]
    assert [(line["result"], line["target_reached"]) for line in lines] == [("giveup", False)]


def test_a_window_with_floor_and_progress_but_no_marker_is_not_left_fading_in(context, monkeypatch, tmp_path):
    taps, _, lines = settle(context, monkeypatch, tmp_path, "Floor 9 6/6", 15)
    assert taps and lines


def test_a_forfeited_run_past_floor_5_claims_its_floor_5_rewards(context, monkeypatch, tmp_path):
    # forfeit() quits the dungeon and pops the flag; the Exploration Reward window that follows is Settle's, which decides on the result alone.
    taps, on_at_claim, lines = settle(context, monkeypatch, tmp_path, "Floor 7 [HARD] 3/7", 15)
    assert actions.CLAIM in taps and actions.GIVE_UP not in taps
    assert [(line["result"], line["floors"]) for line in lines] == [("clear", 6)]


def test_a_stop_line_of_a_run_with_no_settings_in_memory_is_a_target_5_line(context):
    actions.RUN.clear()
    line = actions.run_line(actions.RUN, "stop", None, 0)
    assert (line["target"], line["target_reached"]) == (5, False)


# The acceptance's claim page (2026-10-29): Floor 5 [HARD] 7/7, five HARD floors, 3 weekly bonuses left, no run plan.
CLAIM = "ExplorationRewardHard5.png"
SEEN = {"all five": {f: True for f in range(1, 6)}, "none": {}, "last two": {4: True, 5: True},
        "floor 1 NORMAL": {1: False, 2: True, 3: True, 4: True, 5: True}}
ASKED = {"all five": 3, "none": 3, "last two": 3, "floor 1 NORMAL": 1}


def child():
    class Asked(Exception):
        pass

    def body(context, actions, out):
        team = {"id": "a", "name": "A", "enabled": True, "hard_from_floor": None}
        asked, real = [], actions.settlement.bonus_toggles

        def bonus(use, amount, hard, left, all_hard):
            asked.append(real(use, amount, hard, left, all_hard))
            raise Asked

        actions.settlement.bonus_toggles = bonus
        out["asked"] = {}
        for name, floors in SEEN.items():
            actions.RUN.clear()
            actions.RUN.update(settings={"run": {"weekly_bonus_use": "hard", "weekly_bonus_amount": "all", "target_floor": 5}, "teams": [team]},
                               team=team, floors_hard=floors)  # no "planned": the run began on the expired session's dialog
            asked.clear()
            try:
                actions.Settle().run(context, SimpleNamespace(node_name="Settle"))
            except Asked:
                pass
            out["asked"][name] = list(asked)

    probe_child(body, image=CLAIM)


def read():
    return run_child(__file__)


@pytest.mark.parametrize("name", list(SEEN))
def test_settle_on_the_acceptance_capture_asks_for_the_bonuses_the_floors_allow(name):
    assert read()["asked"][name] == [ASKED[name]]


if __name__ == "__main__":
    child()
