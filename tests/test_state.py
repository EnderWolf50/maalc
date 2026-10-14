import os

import pytest

import state
from state import next_cursor, pick_team, read_cursor, state_path, write_cursor

ADDR = "127.0.0.1:16384"


def t(id, usage="any", enabled=True):
    return {"id": id, "usage": usage, "enabled": enabled}


def test_state_path_uses_adb_address(tmp_path):
    assert state_path(tmp_path, ADDR) == tmp_path / "state" / "127.0.0.1_16384.json"


def test_cursor_round_trip(tmp_path):
    assert read_cursor(tmp_path, ADDR) is None
    write_cursor(tmp_path, ADDR, "b")
    write_cursor(tmp_path, ADDR, "c")
    assert read_cursor(tmp_path, ADDR) == "c"
    assert os.listdir(tmp_path / "state") == ["127.0.0.1_16384.json"]


@pytest.mark.parametrize("text", ["{", "[]", '{"cursor": 3}', ""])
def test_unusable_state_file_means_no_cursor(tmp_path, text):
    path = state_path(tmp_path, ADDR)
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    assert read_cursor(tmp_path, ADDR) is None


def test_failed_write_keeps_old_file_and_no_temp(tmp_path, monkeypatch):
    write_cursor(tmp_path, ADDR, "a")

    def boom(*_):
        raise OSError("disk gone")

    monkeypatch.setattr(state.os, "replace", boom)
    with pytest.raises(OSError):
        write_cursor(tmp_path, ADDR, "b")
    assert read_cursor(tmp_path, ADDR) == "a"
    assert os.listdir(tmp_path / "state") == ["127.0.0.1_16384.json"]


TEAMS = [t("a"), t("b", "hard_only"), t("c", enabled=False), t("d", "normal_only")]


@pytest.mark.parametrize("cursor, difficulty, expected", [
    ("a", "hard", "a"),
    ("b", "hard", "b"),
    ("b", "normal", "d"),  # skips hard_only b
    ("d", "hard", "a"),  # wraps around
    ("c", "normal", "a"),  # cursor on a disabled team -> first enabled team
    ("gone", "hard", "a"),  # cursor on a deleted team
    (None, "normal", "a"),  # no state file
])
def test_pick_team(cursor, difficulty, expected):
    assert pick_team(TEAMS, cursor, difficulty)["id"] == expected


def test_pick_team_none_fits():
    assert pick_team([t("b", "hard_only"), t("x", enabled=False)], "b", "normal") is None
    assert pick_team([], None, "hard") is None


@pytest.mark.parametrize("finished, expected", [
    ("a", "b"),
    ("b", "d"),  # skips disabled c, not usage-mismatched teams
    ("d", "a"),  # wraps around
    ("c", None),  # disabled team: leave cursor alone
    ("gone", None),
])
def test_next_cursor(finished, expected):
    assert next_cursor(TEAMS, finished) == expected


def test_next_cursor_single_team():
    assert next_cursor([t("a")], "a") == "a"
