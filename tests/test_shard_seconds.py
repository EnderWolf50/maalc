"""tools/shard_seconds.py: the per-file CI seconds tests/conftest.py balances the agent shards with."""

import json
import subprocess
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


def test_a_matching_table_passes(tmp_path, table, monkeypatch):
    table({"test_go_home.py": 200})
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
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


def test_a_shard_with_no_report_fails_the_check(tmp_path, table, capsys):
    table({})
    assert shard_seconds.check([report(tmp_path, "a.xml", [("tests.test_map_cost", "1")])]) == 1
    assert "test_go_home.py has no time in this run's reports" in capsys.readouterr().out


def test_fast_files_never_fail_the_check(tmp_path, table, monkeypatch):
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
    table({"test_map_cost.py": 2})
    assert shard_seconds.check([report(tmp_path, "a.xml", [("tests.test_map_cost", "20"), ("tests.test_x", "29")])]) == 0


def test_update_refuses_a_run_that_lacks_a_test_file(table, monkeypatch, capsys):
    table({"test_go_home.py": 1})

    def download(run, folder):
        report(folder, "junit.xml", [("tests.test_go_home", "380")])
    monkeypatch.setattr(shard_seconds, "download", download)
    monkeypatch.setattr(shard_seconds, "earlier", lambda run: [])
    assert shard_seconds.update(9) == 1
    assert "use a run whose shards all passed" in capsys.readouterr().out
    assert json.loads(shard_seconds.TABLE.read_text(encoding="utf-8")) == {"test_go_home.py": 1}


def test_update_writes_every_file_rounded(table, monkeypatch):
    table({})
    names = [p.stem for p in (shard_seconds.ROOT / "tests").glob("test_*.py")]

    def download(run, folder):
        report(folder, "junit.xml", [(f"tests.{n}", "1.6") for n in names])
    monkeypatch.setattr(shard_seconds, "download", download)
    monkeypatch.setattr(shard_seconds, "earlier", lambda run: [])
    assert shard_seconds.update(9) == 0
    assert json.loads(shard_seconds.TABLE.read_text(encoding="utf-8")) == {f"{n}.py": 2 for n in names}


def ci_runs(monkeypatch, runs, shards=None):
    """CI runs for update(): runs {run id: {test file stem: seconds}} (every other file 1 s), newest first; shards
    {run id: reports} splits a run's cases over that many junit files (default 1), and a run left out of runs has none.
    Returns the list of runs downloaded, in order."""
    names = [p.stem for p in (shard_seconds.ROOT / "tests").glob("test_*.py")]
    downloaded = []

    def download(run, folder):
        downloaded.append(run)
        if run not in runs:
            raise subprocess.CalledProcessError(1, ["gh", "run", "download"])
        cases = [(f"tests.{n}", str(runs[run].get(n, 1))) for n in names]
        count = (shards or {}).get(run, 1)
        for i in range(count):
            report(folder, f"junit-{i}.xml", cases[i::count])
    monkeypatch.setattr(shard_seconds, "download", download)
    monkeypatch.setattr(shard_seconds, "earlier", lambda run: sorted({*runs, *(shards or {})} - {run}, reverse=True))
    return downloaded


def written():
    return json.loads(shard_seconds.TABLE.read_text(encoding="utf-8"))


def test_update_writes_the_median_of_the_run_and_the_four_before_it(table, monkeypatch):
    # #463: the table was written from one run where test_gift_cells took 67 s (103-128 s in most runs), and the next PR's
    # 170 s failed it. A slow run among typical ones writes the typical time.
    table({})
    downloaded = ci_runs(monkeypatch, {9: {"test_gift_cells": 170}, 8: {"test_gift_cells": 126},
                                       7: {"test_gift_cells": 128}, 6: {"test_gift_cells": 125},
                                       5: {"test_gift_cells": 103}, 4: {"test_gift_cells": 1}, 3: {"test_gift_cells": 1}})
    assert shard_seconds.update(9) == 0
    assert written()["test_gift_cells.py"] == 126 and written()["test_go_home.py"] == 1
    assert downloaded == [9, 8, 7, 6, 5]


def test_a_file_off_by_more_than_double_from_the_median_takes_the_runs_own_time(table, monkeypatch):
    # The file changed, not the runner: the table follows the run, so the run passes the check.
    table({})
    ci_runs(monkeypatch, {9: {"test_gift_cells": 380}, **{run: {"test_gift_cells": 126} for run in (8, 7, 6, 5)}})
    assert shard_seconds.update(9) == 0
    assert written()["test_gift_cells.py"] == 380


def test_an_earlier_run_without_a_report_from_every_shard_is_skipped(table, monkeypatch):
    # Run 8's second shard was cut short (one report of the run's two), run 7 has no junit (docs only, or expired).
    table({})
    runs = {9: {"test_gift_cells": 126}, 8: {"test_gift_cells": 10}, **{run: {"test_gift_cells": 130} for run in (6, 5, 4, 3)}}
    downloaded = ci_runs(monkeypatch, runs, shards={9: 2, 8: 1, 7: 2, 6: 2, 5: 2, 4: 2, 3: 2})
    assert shard_seconds.update(9) == 0
    assert written()["test_gift_cells.py"] == 130
    assert downloaded == [9, 8, 7, 6, 5, 4, 3]
