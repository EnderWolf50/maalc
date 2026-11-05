"""tools/shard_seconds.py: the per-file CI seconds tests/conftest.py balances the agent shards with."""

import json
from pathlib import Path

import pytest

import shard_seconds


def report(folder, name, cases):
    body = "".join(f'<testcase classname="{c}" name="t{i}" time="{t}" />' for i, (c, t) in enumerate(cases))
    path = Path(folder) / name
    path.write_text(f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>', encoding="utf-8")
    return path


@pytest.fixture
def table(tmp_path, monkeypatch):
    path = tmp_path / "shard_seconds.json"
    monkeypatch.setattr(shard_seconds, "TABLE", path)

    def write(entries):
        path.write_text(json.dumps(entries), encoding="utf-8")
    return write


def test_seconds_add_up_per_file_across_shards_and_classes(tmp_path):
    a = report(tmp_path, "a.xml", [("tests.test_go_home", "100.5"), ("tests.test_go_home.TestBack", "20")])
    b = report(tmp_path, "b.xml", [("tests.test_map_cost", "0.25")])
    assert shard_seconds.measured([a, b]) == {"test_go_home.py": 120.5, "test_map_cost.py": 0.25}


def test_a_matching_table_passes(tmp_path, table, capsys):
    table({"test_go_home.py": 200})
    assert shard_seconds.check([report(tmp_path, "a.xml", [("tests.test_go_home", "380")])]) == 0


def test_a_slow_file_missing_from_the_table_fails_with_the_update_command(tmp_path, table, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    table({})
    assert shard_seconds.check([report(tmp_path, "a.xml", [("tests.test_new_child", "45")])]) == 1
    out = capsys.readouterr().out
    assert "test_new_child.py took 45 s and is not in the table" in out
    assert "tools/shard_seconds.py update --run 123" in out


def test_a_number_off_by_more_than_double_fails_either_way(tmp_path, table, capsys):
    table({"test_go_home.py": 181, "test_pass_task.py": 300})
    xml = report(tmp_path, "a.xml", [("tests.test_go_home", "380"), ("tests.test_pass_task", "100")])
    assert shard_seconds.check([xml]) == 1
    out = capsys.readouterr().out
    assert "test_go_home.py took 380 s, the table says 181" in out
    assert "test_pass_task.py took 100 s, the table says 300" in out


def test_fast_files_never_fail_the_check(tmp_path, table):
    table({"test_map_cost.py": 2})
    assert shard_seconds.check([report(tmp_path, "a.xml", [("tests.test_map_cost", "20"), ("tests.test_x", "29")])]) == 0


def test_update_refuses_a_run_that_lacks_a_test_file(tmp_path, table, monkeypatch, capsys):
    table({"test_go_home.py": 1})

    def download(args, check):
        report(args[args.index("--dir") + 1], "junit.xml", [("tests.test_go_home", "380")])
    monkeypatch.setattr(shard_seconds.subprocess, "run", download)
    assert shard_seconds.update(9) == 1
    assert "use a green run" in capsys.readouterr().out
    assert json.loads(shard_seconds.TABLE.read_text(encoding="utf-8")) == {"test_go_home.py": 1}


def test_update_writes_every_file_rounded(tmp_path, table, monkeypatch):
    table({})
    names = [p.stem for p in (shard_seconds.ROOT / "tests").glob("test_*.py")]

    def download(args, check):
        report(args[args.index("--dir") + 1], "junit.xml", [(f"tests.{n}", "1.6") for n in names])
    monkeypatch.setattr(shard_seconds.subprocess, "run", download)
    assert shard_seconds.update(9) == 0
    assert json.loads(shard_seconds.TABLE.read_text(encoding="utf-8")) == {f"{n}.py": 2 for n in names}
