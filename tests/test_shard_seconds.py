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


# The agent shards run these tests under a pull request's GITHUB_EVENT_NAME too.
@pytest.fixture(autouse=True)
def no_ci_event(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)


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


LISTED = [100, 80, 60, 50, 40]
USUAL_OVER_LISTED = [0.7, 0.85, 1, 1.2, 1.4]


def shard(prefix, pace):
    return ([(f"tests.test_{prefix}{i}", str(listed * usual * pace))
             for i, (listed, usual) in enumerate(zip(LISTED, USUAL_OVER_LISTED))],
            {f"test_{prefix}{i}.py": listed for i, listed in enumerate(LISTED)})


@pytest.mark.parametrize("pace", [0.5, 2])
def test_one_shard_on_a_runner_at_half_or_double_the_tables_pace_beside_usual_ones_fails_no_file(
        tmp_path, table, capsys, monkeypatch, pace):
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
    (fast, fast_table), (usual_a, table_a), (usual_b, table_b) = shard("a", pace), shard("b", 1), shard("c", 1)
    table(fast_table | table_a | table_b)
    reports = [report(tmp_path, f"{i}.xml", cases) for i, cases in enumerate([fast, usual_a, usual_b])]
    assert shard_seconds.check(reports) == 0, capsys.readouterr().out


@pytest.mark.parametrize("pace", [1, 0.5])
def test_one_file_down_to_a_third_fails_alone_even_when_it_is_most_of_its_shard(tmp_path, table, capsys, monkeypatch,
                                                                                 pace):
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
    listed = {"test_thread_luxcavation.py": 216, "test_assemble_modules.py": 49, "test_live_evidence.py": 22,
              "test_pause_menus.py": 18, "test_live_giveup.py": 15}
    table(listed)
    took = {name: seconds * pace for name, seconds in listed.items()} | {"test_thread_luxcavation.py": 72 * pace}
    assert shard_seconds.check([report(tmp_path, "a.xml", [(f"tests.{n[:-3]}", str(t)) for n, t in took.items()])]) == 1
    errors = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::error")]
    assert len(errors) == 1 and f"test_thread_luxcavation.py took {72 * pace:.0f} s, the table says 216" in errors[0]


@pytest.fixture
def new_file_check(tmp_path, table, monkeypatch):
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])

    def check(event, pace, took):
        monkeypatch.setenv("GITHUB_EVENT_NAME", event)
        cases, listed = shard("a", pace)
        table(listed)
        return shard_seconds.check([report(tmp_path, "a.xml", cases + [("tests.test_new", str(took))])])
    return check


def test_542s_new_file_fails_its_pull_request_and_passes_main_on_a_slower_runner(new_file_check, capsys):
    verdicts = {"pull_request": new_file_check("pull_request", 1, 29), "push": new_file_check("push", 1.26, 31)}
    assert verdicts == {"pull_request": 1, "push": 0}, capsys.readouterr().out


def test_no_new_file_passes_a_pull_request_and_fails_main_at_half_to_double_the_pace(new_file_check):
    paces = [0.5, 1, 2]

    def passes(event, pace, usual, scales):
        return new_file_check(event, pace, usual * pace if scales else usual) == 0

    for scales in [True, False]:
        through = [(usual, pr) for usual in range(1, 61) for pr in paces if passes("pull_request", pr, usual, scales)]
        assert through and len(through) < 60 * len(paces)
        red = [(usual, pr, main) for usual, pr in through for main in paces if not passes("push", main, usual, scales)]
        assert red == [], f"scales with the runner: {scales}"


def test_a_file_whose_time_ignores_the_runner_passes_too(tmp_path, table, capsys, monkeypatch):
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
    fast, listed = shard("a", 0.5)
    table(listed | {"test_charge_enkephalin.py": 77})
    xml = report(tmp_path, "a.xml", fast + [("tests.test_charge_enkephalin", "90")])
    assert shard_seconds.check([xml]) == 0, capsys.readouterr().out


def test_update_refuses_a_run_that_lacks_a_test_file(table, monkeypatch, capsys):
    table({"test_go_home.py": 1})

    def download(run, folder):
        report(folder, "junit.xml", [("tests.test_go_home", "380")])
    monkeypatch.setattr(shard_seconds, "download", download)
    monkeypatch.setattr(shard_seconds, "agents_passed", lambda run: True)
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
    monkeypatch.setattr(shard_seconds, "agents_passed", lambda run: True)
    assert shard_seconds.update(9) == 0
    assert json.loads(shard_seconds.TABLE.read_text(encoding="utf-8")) == {f"{n}.py": 2 for n in names}


def test_update_refuses_a_run_whose_agent_shards_did_not_all_pass_on_the_ci_runner(table, monkeypatch, capsys):
    # #636: a run from before the move to Windows would write a table of Linux times.
    table({"test_go_home.py": 1})
    downloaded = ci_runs(monkeypatch, {9: {}}, failed={9})
    assert shard_seconds.update(9) == 1
    assert "windows-latest" in capsys.readouterr().out
    assert downloaded == [] and written() == {"test_go_home.py": 1}


def ci_runs(monkeypatch, runs, failed=(), expired=()):
    """CI runs for update(): runs {run id: {test file stem: seconds}} (every other file 1 s); failed: runs where an agent
    shard did not pass; expired: runs whose agent shards passed but whose junit is gone. A larger id is a later run.
    Returns the list of runs downloaded, in order."""
    names = [p.stem for p in (shard_seconds.ROOT / "tests").glob("test_*.py")]
    downloaded = []

    def download(run, folder):
        downloaded.append(run)
        if run not in runs:
            raise subprocess.CalledProcessError(1, ["gh", "run", "download"])
        report(folder, "junit.xml", [(f"tests.{n}", str(runs[run].get(n, 1))) for n in names])
    monkeypatch.setattr(shard_seconds, "download", download)
    monkeypatch.setattr(shard_seconds, "earlier",
                        lambda run: sorted({r for r in (*runs, *failed, *expired) if r < run}, reverse=True))
    monkeypatch.setattr(shard_seconds, "agents_passed", lambda run: run not in failed)
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


def test_a_file_a_fast_runner_ran_at_under_half_its_median_keeps_the_median(table, monkeypatch):
    # Shard 3 of run 42440944197 and of the four runs before it (#536).
    table({})
    names = ["test_shop_skill_screens", "test_go_home", "test_pass_task", "test_shop", "test_frozen_home"]
    seconds = {9: [41, 83, 23, 24, 55], 8: [86, 102, 40, 33, 65], 7: [85, 100, 41, 34, 65], 6: [85, 102, 41, 34, 65],
               5: [94, 107, 44, 37, 67]}
    ci_runs(monkeypatch, {run: dict(zip(names, times)) for run, times in seconds.items()})
    assert shard_seconds.update(9) == 0
    assert written()["test_shop_skill_screens.py"] == 85


def test_the_table_update_writes_passes_its_own_runs_check_when_changed_files_pull_the_pace(tmp_path, table,
                                                                                             monkeypatch, capsys):
    table({})
    took = {"test_gift_cells": 90, "test_shop": 100, "test_go_home": 220, "test_pass_task": 500, "test_frozen_home": 600}
    ci_runs(monkeypatch, {9: took, **{run: dict.fromkeys(took, 100) for run in (8, 7, 6, 5)}})
    assert shard_seconds.update(9) == 0
    monkeypatch.setattr(shard_seconds, "unmeasured", lambda seconds: [])
    xml = report(tmp_path, "a.xml", [(f"tests.{name}", str(seconds)) for name, seconds in took.items()])
    assert shard_seconds.check([xml]) == 0, capsys.readouterr().out
    assert written()["test_go_home.py"] == 220


def test_an_earlier_run_whose_agent_shards_did_not_all_pass_or_whose_junit_expired_is_skipped(table, monkeypatch, capsys):
    # Run 8 had a shard fail or cut short (its times are not a runner's), run 7's junit is gone: neither counts, and run 8
    # is not even downloaded. Only three runs are left: update says so.
    table({})
    runs = {9: {"test_gift_cells": 126}, 8: {"test_gift_cells": 10}, **{run: {"test_gift_cells": 130} for run in (6, 5, 4)}}
    downloaded = ci_runs(monkeypatch, runs, failed={8}, expired={7})
    assert shard_seconds.update(9) == 0
    assert written()["test_gift_cells.py"] == 130
    assert downloaded == [9, 7, 6, 5, 4]
    assert "only 3 earlier CI runs" in capsys.readouterr().out


def test_earlier_lists_the_completed_ci_runs_before_the_run_newest_first(monkeypatch):
    calls = []

    def gh_json(*args):
        calls.append(args)
        return [{"databaseId": 12}, {"databaseId": 10}, {"databaseId": 9}, {"databaseId": 7}]
    monkeypatch.setattr(shard_seconds, "gh_json", gh_json)
    assert shard_seconds.earlier("10") == [9, 7]  # argparse hands the run id over as text
    assert {"ci.yml", "completed"} <= set(calls[0])


def test_only_a_run_whose_agent_shards_all_passed_on_the_ci_runner_counts(monkeypatch):
    win, linux = ["windows-latest"], ["ubuntu-latest"]
    jobs = {1: [("agent (0)", "success", win), ("agent (1)", "success", win), ("shard-balance", "failure", linux)],
            2: [("agent (0)", "success", win), ("agent (1)", "failure", win)],
            3: [("agent (0)", "success", win), ("agent (1)", "cancelled", win)],
            4: [("changes", "success", linux), ("agent", "skipped", [])],  # docs only: the matrix never ran
            5: [("agent (0)", "success", linux), ("agent (1)", "success", linux)]}  # before #636: not a Windows runner's
    calls = []

    def gh_json(*args):
        calls.append(args)
        run = int(args[1].split("/runs/")[1].split("/")[0])
        return {"jobs": [{"name": n, "conclusion": c, "labels": labels} for n, c, labels in jobs[run]]}
    monkeypatch.setattr(shard_seconds, "gh_json", gh_json)
    assert [run for run in jobs if shard_seconds.agents_passed(run)] == [1]
    assert calls[0][0] == "api"
