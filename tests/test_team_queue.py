import json
import os
from types import SimpleNamespace

import pytest

import actions
import run_start_actions
import settings
import test_actions
from team_queue import migrate_cursor, pick_team, requeue, resumed_team
from test_resumed_run import claim
from test_task_chain import entry_page
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context

ADDR = "127.0.0.1:16384"


def t(id, usage="any", enabled=True):
    return {"id": id, "usage": usage, "enabled": enabled}


TEAMS = [t("a"), t("b", "hard_only"), t("c", enabled=False), t("d", "normal_only")]


def settings_of(teams, order):
    """Settings with these teams, the list in the order given, and the queue in order (ids)."""
    return {"teams": teams, "team_queue": list(order)}


# #803: the queue is team_queue; the order of the list is the user's to arrange, and no pick looks at it
REVERSED = TEAMS[::-1]


@pytest.mark.parametrize("order, difficulty, expected", [
    ("abcd", "hard", "a"),
    ("bcda", "hard", "b"),
    ("bcda", "normal", "d"),  # skips hard_only b
    ("cadb", "normal", "a"),  # skips the disabled c
])
def test_a_run_plays_the_first_enabled_team_of_the_queue_that_fits_its_difficulty(order, difficulty, expected):
    assert pick_team(settings_of(REVERSED, order), difficulty)["id"] == expected


def test_no_team_fits():
    assert pick_team(settings_of([t("b", "hard_only"), t("x", enabled=False)], "xb"), "normal") is None
    assert pick_team(settings_of([], ""), "hard") is None


@pytest.mark.parametrize("difficulty, expected", [
    ("hard", ("b", True)),
    ("normal", ("d", True)),
    (None, ("b", False)),  # auto: hard picks b, normal d; the run is counted as hard's b, not known
])
def test_a_resumed_run_is_the_queue_heads_for_its_difficulty(difficulty, expected):
    team, known = resumed_team(settings_of(REVERSED, "bcda"), difficulty)
    assert (team["id"], known) == expected


def test_a_resumed_run_with_no_team_that_fits_is_the_first_enabled_teams():
    team, known = resumed_team(settings_of([t("d", "hard_only"), t("c", enabled=False), t("b", "hard_only")], "cbd"), "normal")
    assert (team["id"], known) == ("b", False)


def settings_file(root, ids, disabled=(), order=None, **extra):
    """A settings file as the GUI writes it: teams in the order ids, the queue in order (ids again when None)."""
    path = root / "config" / "settings.json"
    path.parent.mkdir(exist_ok=True)
    teams = [{"id": i, "name": f"隊 {i}", "enabled": i not in disabled} for i in ids]
    data = {"version": 22, "teams": teams, "team_queue": list(ids if order is None else order), **extra}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def old_settings_file(root, version, ids):
    """A file the GUI has not written back as version 22 yet: its queue is the order of its teams."""
    path = root / "config" / "settings.json"
    path.parent.mkdir(exist_ok=True)
    data = {"version": version, "teams": [{"id": i, "name": f"隊 {i}", "enabled": True} for i in ids]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def on_disk(root):
    return json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))


def queue(root):
    return on_disk(root)["team_queue"]


def listed(root):
    """The order of the team list."""
    return [t["id"] for t in on_disk(root)["teams"]]


def test_a_claim_moves_the_team_to_the_end_of_the_queue_and_keeps_the_rest_of_the_file(tmp_path):
    path = settings_file(tmp_path, ["a", "b", "c"], language="zh_tw")
    before = on_disk(tmp_path)
    requeue(tmp_path, "a")
    assert queue(tmp_path) == ["b", "c", "a"]
    raw = path.read_bytes()
    assert json.loads(raw) == {**before, "team_queue": ["b", "c", "a"]}  # the team list's order too
    # The GUI's own format (App.tsx toText): indent 2, no \u escapes, LF line ends on Windows too.
    assert raw.endswith(b"\n}\n") and b"\r" not in raw and '"name": "隊 a"'.encode() in raw


def test_the_queue_moves_and_the_list_stays_in_the_users_order(tmp_path):
    # #803: the list is c, a, b, the queue a, b, c
    settings_file(tmp_path, ["c", "a", "b"], order="abc")
    requeue(tmp_path, "a")
    assert (queue(tmp_path), listed(tmp_path)) == (["b", "c", "a"], ["c", "a", "b"])


def test_the_claimed_team_moves_wherever_the_gui_put_it_since_the_run_began(tmp_path):
    settings_file(tmp_path, ["a", "b", "c"], order="cab")  # the user dragged c to the top of the queue during a's run
    requeue(tmp_path, "a")
    assert queue(tmp_path) == ["c", "b", "a"]


@pytest.mark.parametrize("version", [20, 21])
def test_a_file_the_gui_has_not_written_back_moves_the_team_in_its_list(tmp_path, version):
    # spec 04 section 2: the agent writes an older file at its version, only the order; that order is its queue, and the
    # migration to 22 makes team_queue of it
    path = old_settings_file(tmp_path, version, ["a", "b", "c"])
    before = json.loads(path.read_text(encoding="utf-8"))
    requeue(tmp_path, "a")
    assert on_disk(tmp_path) == {**before, "teams": [before["teams"][i] for i in (1, 2, 0)]}


@pytest.mark.parametrize("team", ["c", "gone"])
def test_a_team_already_last_or_no_longer_listed_leaves_the_file_alone(tmp_path, team):
    path = settings_file(tmp_path, ["a", "b", "c"])
    before = path.read_bytes()
    assert team in requeue(tmp_path, team)
    assert path.read_bytes() == before


@pytest.mark.parametrize("text", [None, "{", "[]", '{"teams": 3}', '{"teams": [3]}', '{"version": 22, "teams": [{"id": "a"}]}',
                                  '{"version": 22, "teams": [], "team_queue": ["a"]}'])
def test_an_unusable_settings_file_is_logged_not_raised(tmp_path, text):
    if text is not None:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(text, encoding="utf-8")
    assert "not written" in requeue(tmp_path, "a")


def test_a_failed_write_keeps_the_old_file_and_no_temp(tmp_path, monkeypatch):
    path = settings_file(tmp_path, ["a", "b"])
    before = path.read_bytes()

    def boom(*_):
        raise OSError("disk gone")

    monkeypatch.setattr(settings.os, "replace", boom)
    assert "not written" in requeue(tmp_path, "a")
    assert path.read_bytes() == before
    assert os.listdir(path.parent) == ["settings.json"]


def test_a_gui_save_between_the_read_and_the_write_is_kept(tmp_path, monkeypatch):
    path = settings_file(tmp_path, ["a", "b", "c"])
    fsync = settings.os.fsync

    def gui_saves_once(fd):  # the GUI renames b while the agent's temp file is being written
        monkeypatch.setattr(settings.os, "fsync", fsync)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["teams"][1]["name"] = "renamed"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fsync(fd)

    monkeypatch.setattr(settings.os, "fsync", gui_saves_once)
    requeue(tmp_path, "a")
    assert queue(tmp_path) == ["b", "c", "a"]
    assert [(t["id"], t["name"]) for t in on_disk(tmp_path)["teams"]] == [("a", "隊 a"), ("b", "renamed"), ("c", "隊 c")]
    assert os.listdir(path.parent) == ["settings.json"]


def old_state(root, name, cursor):
    """The state file of the rotation cursor before #501: <root>/state/<adb address, ':' as '_'>.json."""
    (root / "state").mkdir(exist_ok=True)
    (root / "state" / name).write_text(json.dumps({"cursor": cursor}), encoding="utf-8")


def test_the_old_cursor_becomes_the_queue_head_and_the_state_files_go(tmp_path):
    settings_file(tmp_path, ["d", "c", "b", "a"], order="abcd")  # the list's order is not the queue's (#803)
    old_state(tmp_path, "127.0.0.1_16384.json", "c")
    old_state(tmp_path, "127.0.0.1_16416.json", "b")  # the other instance's: one queue serves both now
    assert "'c'" in migrate_cursor(tmp_path, ADDR)
    assert queue(tmp_path) == ["c", "d", "a", "b"]  # the order the cursor would have run them in
    assert listed(tmp_path) == ["d", "c", "b", "a"]
    assert not (tmp_path / "state").exists()
    assert migrate_cursor(tmp_path, ADDR) is None  # once
    assert queue(tmp_path) == ["c", "d", "a", "b"]


@pytest.mark.parametrize("name, cursor", [
    ("127.0.0.1_16384.json", "a"),  # already the head
    ("127.0.0.1_16384.json", "gone"),  # a deleted team: the cursor started from the first enabled team
    ("127.0.0.1_16384.json", "x"),  # a disabled team: the same
    ("127.0.0.1_16416.json", "c"),  # only another instance's cursor
])
def test_a_cursor_that_changes_nothing_leaves_the_order_and_still_removes_the_state(tmp_path, name, cursor):
    path = settings_file(tmp_path, ["a", "x", "b", "c"], disabled={"x"})
    before = path.read_bytes()
    old_state(tmp_path, name, cursor)
    assert migrate_cursor(tmp_path, ADDR)
    assert path.read_bytes() == before
    assert not (tmp_path / "state").exists()


def test_with_no_usable_settings_the_state_file_waits_for_the_next_start(tmp_path):
    old_state(tmp_path, "127.0.0.1_16384.json", "c")
    assert "not migrated" in migrate_cursor(tmp_path, ADDR)
    assert (tmp_path / "state" / "127.0.0.1_16384.json").exists()
    settings_file(tmp_path, ["a", "b", "c"])
    migrate_cursor(tmp_path, ADDR)
    assert queue(tmp_path) == ["c", "a", "b"]


def test_the_cursor_of_a_file_the_gui_has_not_written_back_turns_its_list(tmp_path):
    old_settings_file(tmp_path, 21, ["a", "b", "c"])
    old_state(tmp_path, "127.0.0.1_16384.json", "c")
    migrate_cursor(tmp_path, ADDR)
    assert listed(tmp_path) == ["c", "a", "b"] and "team_queue" not in on_disk(tmp_path)


def test_no_state_file_no_change(tmp_path):
    assert migrate_cursor(tmp_path, ADDR) is None


def test_a_settings_file_with_no_team_still_drops_the_state(tmp_path):
    settings_file(tmp_path, [])
    old_state(tmp_path, "127.0.0.1_16384.json", "c")
    assert migrate_cursor(tmp_path, ADDR)
    assert not (tmp_path / "state").exists()


def test_a_team_the_difficulty_skips_keeps_its_place_and_only_the_claimed_team_goes_last(context, monkeypatch):
    def queue_b_a_c(data):  # b is hard_only, a any; the list c, a, b
        data["teams"].insert(0, {**data["teams"][0], "id": "c", "name": "Team c", "game_team": 3})
        data["team_queue"] = ["b", "a", "c"]
    entry_page(context, settings=queue_b_a_c)  # auto, no weekly bonus left: a normal run
    actions.TASK.update(runs=0, done=None, modules=20)
    assert run_start_actions.PlanRun().run(context, None) is True
    assert (actions.RUN["team"]["id"], actions.RUN["difficulty"]) == ("a", "normal")
    assert queue(actions.ROOT) == ["b", "a", "c"]
    claim(context, monkeypatch)
    assert (queue(actions.ROOT), listed(actions.ROOT)) == (["b", "c", "a"], ["c", "a", "b"])


def test_a_mirror_dungeon_task_turns_the_old_rotation_cursor_into_the_queue_head(context, monkeypatch):
    entry_page(context)
    context.tasker.controller.info = {"adb_serial": ADDR}
    old_state(actions.ROOT, "127.0.0.1_16384.json", "b")
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})
    actions.TaskStart().run(context, SimpleNamespace(node_name="ExpLuxcavation"))
    assert queue(actions.ROOT) == ["a", "b"]  # a daily task leaves it to the mirror
    actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    assert queue(actions.ROOT) == ["b", "a"] and not (actions.ROOT / "state").exists()
    assert listed(actions.ROOT) == ["a", "b"]
