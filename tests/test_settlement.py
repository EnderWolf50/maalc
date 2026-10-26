import json

import pytest

from settlement import append_run, bonus_toggles, can_claim, claim_dialog, counts_as_run, floors_passed, goal_met, now, read_result, runs_done


@pytest.mark.parametrize("text, expected", [
    ("Floor 5 [NORMAL] 6/6", (5, False, 6, 6)),
    ("Floor 5 [HARD] 5/6", (5, True, 5, 6)),
    ("Floor 3 HARD 2 / 6", (3, True, 2, 6)),  # OCR may drop the brackets
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


@pytest.mark.parametrize(("modules", "expected"), [(4, False), (0, False), (5, True), (182, True), (None, True)])
def test_can_claim(modules, expected):
    assert can_claim(modules) is expected
