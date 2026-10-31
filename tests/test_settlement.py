"""Settlement decisions, and Settle on the acceptance's Exploration Reward capture (#382).

The Settle cases run the real MaaFramework and its OCR in a child process (this file run as a script), as
test_consecutive_ocr.py does.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from daily_child import probe_child, run_child, screen

from settlement import NOT_SEEN, all_hard, append_run, bonus_toggles, claim_dialog, counts_as_run, first_floor_hard, floors_passed, goal_met, new_run_gate, now, read_result, runs_done


@pytest.mark.parametrize("text, expected", [
    ("Floor 5 [NORMAL] 6/6", (5, False, 6, 6)),
    ("Floor 5 [HARD] 5/6", (5, True, 5, 6)),
    ("Floor 3 HARD 2 / 6", (3, True, 2, 6)),  # OCR may drop the brackets
    ("Floor 12 [HARD] 5/7", (12, True, 5, 7)),  # #383: floors run to 15
    ("Floor 15 [NORMAL] 6/6", (15, False, 6, 6)),
    ("Floor 5", None),
    ("", None),
])
def test_read_result(text, expected):
    assert read_result(text) == expected


@pytest.mark.parametrize("result, met, passed", [
    ((5, False, 6, 6), True, 5),
    ((5, True, 5, 6), False, 4),
    ((4, True, 6, 6), False, 4),
    ((1, False, 5, 5), False, 1),
    ((5, True, 7, 7), True, 5),  # live 2026-10-16: a HARD floor 5 may have 7 nodes
    ((5, True, 6, 7), False, 4),
])
def test_goal_and_floors(result, met, passed):
    assert goal_met(result) is met
    assert floors_passed(result) == passed


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
            actions.RUN.update(settings={"run": {"weekly_bonus_use": "hard", "weekly_bonus_amount": "all"}, "teams": [team]},
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
