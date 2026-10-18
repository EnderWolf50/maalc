from pathlib import Path

import pytest
import yaml

import run_start as rs

LEVELS = ["plus2", "base", "plus", "base", "none", "none", "none", "none", "none", "base"]
PRIORITY = [3, 1, 10, 4, 2, 5, 6, 7, 8, 9]


@pytest.mark.parametrize(("setting", "weekly", "expected"), [
    ("auto", 3, "hard"), ("auto", 0, "normal"), ("hard", 0, "hard"), ("normal", 3, "normal"),
])
def test_run_difficulty(setting, weekly, expected):
    assert rs.run_difficulty(setting, weekly) == expected


def test_resolve_plan():
    settings = {"starlight_plans": [{"id": "a", "levels": LEVELS}]}
    assert rs.resolve_plan(settings, {"starlight": {"plan": "a"}}, "starlight")["levels"] == LEVELS
    assert rs.resolve_plan(settings, {"starlight": {"custom": {"x": 1}}}, "starlight") == {"x": 1}


def test_starlight_skip_buys_past_an_unaffordable_grace():
    # The live run of 2026-10-14: 120 available, grace 10 (60) no longer fits after 3+ and 1++.
    buys, missed = rs.starlight_purchases({"levels": LEVELS, "priority": PRIORITY}, 120, "skip")
    assert buys == [(3, "plus", 40), (1, "plus2", 30), (4, "base", 20), (2, "base", 10)]
    assert missed == [(10, "base", 60)]


def test_starlight_stop_buys_nothing_after_an_unaffordable_grace():
    buys, missed = rs.starlight_purchases({"levels": LEVELS, "priority": PRIORITY}, 120, "stop")
    assert buys == [(3, "plus", 40), (1, "plus2", 30)]
    assert missed == [(10, "base", 60)]


def test_starlight_never_buys_more_than_available():
    plan = {"levels": ["plus2"] * 10, "priority": list(range(1, 11))}
    for available in range(0, 400, 7):
        buys, _ = rs.starlight_purchases(plan, available, "skip")
        assert sum(p for _, _, p in buys) <= available


@pytest.mark.parametrize(("floor", "run_hard", "from_floor", "expected"), [
    (1, True, 1, True), (5, True, 1, True), (2, True, 3, False), (3, True, 3, True), (1, False, 1, False),
    (1, True, None, False), (5, True, None, False),  # the switch off: this team plays the whole run NORMAL (#137)
])
def test_hard_wanted(floor, run_hard, from_floor, expected):
    assert rs.hard_wanted(floor, run_hard, from_floor) is expected


@pytest.mark.parametrize(("floor", "shown_hard", "want_hard", "expected"), [
    (1, False, True, "hard"),
    (1, True, False, "normal"),  # floor 1, nothing chosen yet: the game's remembered HARD may go
    (2, True, False, None),  # HARD once chosen is kept
    (3, False, True, "hard"),
    (2, True, True, None),
    (1, True, None, None),  # run difficulty unknown: keep what the game shows
])
def test_difficulty_move(floor, shown_hard, want_hard, expected):
    assert rs.difficulty_move(floor, shown_hard, want_hard) == expected


NAMES = ["To be Crushed", "To be Cleaved", "To be Pierced", "Nagel und Hammer",
         "Walpurgis Night: Hatred and Despair", "Charm, Wander, Doubt"]


@pytest.mark.parametrize(("lines", "expected"), [
    (["bimus", "To be Crushed"], "To be Crushed"),  # logo fragment above the title
    (["Walpurgis g Hatred and 'Despair"], "Walpurgis Night: Hatred and Despair"),
    (["Charm, Wander Doubt"], "Charm, Wander, Doubt"),
    (["Lake World"], None),
])
def test_match_card(lines, expected):
    assert rs.match_card(lines, NAMES)[0] == expected


def test_close_names_need_a_margin():
    assert rs.match_pack("To be Cxxxxed", NAMES) is None


def test_rank_and_pick():
    marks = {"To be Crushed": "avoid", "Nagel und Hammer": "prefer"}
    ranked = rs.rank_packs([["To be Crushed"], ["Lake World"], ["Nagel und Hammer"]], NAMES, marks)
    assert ranked == [("To be Crushed", "avoid"), ("Lake World", "neutral"), ("Nagel und Hammer", "prefer")]
    assert rs.pick_pack([r for _, r in ranked]) == 2
    assert rs.pick_pack(["neutral", "avoid", "neutral"]) == 0
    assert rs.pick_pack(["avoid", "avoid"]) == 0



@pytest.mark.parametrize(("setting", "used", "expected"), [
    ("all", 0, True), ("all", 3, True),  # every free refresh (#25's rule, the default)
    ("once", 0, True), ("once", 1, False),
    ("none", 0, False),
])
def test_an_all_avoid_page_is_refreshed_as_often_as_the_setting_allows(setting, used, expected):
    # #41: none / once / all; "all" stops only when a refresh changes nothing (the caller sees that).
    assert rs.refresh_wanted(["avoid", "avoid", "avoid"], setting, used) is expected


@pytest.mark.parametrize("setting", ["none", "once", "all"])
def test_a_page_with_anything_but_avoid_is_never_refreshed(setting):
    assert rs.refresh_wanted(["avoid", "neutral", "avoid"], setting, 0) is False


@pytest.mark.parametrize(("visible", "target", "expected"), [
    ({1: 309, 2: 345}, 2, ("tap", 345)),
    ({1: 309, 7: 527}, 13, "down"),
    ({8: 303, 14: 523}, 2, "up"),
    ({}, 3, "down"),
])
def test_team_list_move(visible, target, expected):
    assert rs.team_list_move(visible, target) == expected


def test_theme_pack_data_file():
    path = Path(__file__).resolve().parent.parent / "assets/resource/base/data/theme_packs.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["packs"] and all(isinstance(p, str) for p in data["packs"])  # unquoted "a: b" parses as a dict
    assert all(p in data["packs"] and m in rs.PACK_RANK for p, m in data["default_plan"].items())
