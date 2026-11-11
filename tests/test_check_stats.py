"""tools/check_stats.py (#633): the summary of tools/check.py's run log, on fake records."""

import datetime
import json

import check_stats


def rec(n, red=False, branch="b", files=None, tests=(), maa=(), steps=None, test_seconds=None, worktree="w"):
    return {"v": 1, "started": f"2026-11-{n:02d}T10:00:00+08:00", "worktree": worktree, "branch": branch,
            "files": files or {}, "failed_tests": list(tests), "failed_maa": list(maa), "test_seconds": test_seconds or {},
            "steps": steps or [{"name": "ruff", "exit": 1 if red else 0, "seconds": 1.0},
                               {"name": "pytest", "exit": 0, "seconds": 100.0}]}


def kinds(records):
    return [kind for _, _, kind in check_stats.transitions(records)]


def test_a_changed_program_file_between_red_and_green_is_a_stopped_error():
    assert kinds([rec(1, red=True, files={"agent/a.py": "1"}), rec(2, files={"agent/a.py": "2"})]) == ["code"]


def test_a_new_file_or_a_removed_file_counts_as_changed():
    assert kinds([rec(1, red=True), rec(2, files={"tools/x.py": "1"})]) == ["code"]
    assert kinds([rec(1, red=True, files={"tools/x.py": "1"}), rec(2)]) == ["code"]


def test_only_test_files_changed_is_the_tests_own_problem():
    red = rec(1, red=True, files={"agent/a.py": "1", "tests/test_a.py": "1"})
    green = rec(2, files={"agent/a.py": "1", "tests/test_a.py": "2", "tests/conftest.py": "1", "tools/test_x.py": "1"})
    assert kinds([red, green]) == ["test"]


def test_a_test_change_beside_a_program_change_is_a_stopped_error():
    assert kinds([rec(1, red=True), rec(2, files={"tests/test_a.py": "1", "agent/a.py": "1"})]) == ["code"]


def test_nothing_changed_is_flaky():
    same = {"agent/a.py": "1"}
    assert kinds([rec(1, red=True, files=same), rec(2, files=same)]) == ["flaky"]


def test_a_doc_edit_counts_as_code_because_review_lint_reads_docs():
    assert kinds([rec(1, red=True), rec(2, files={"docs/x.md": "1"})]) == ["code"]


def test_a_moved_base_makes_the_pair_not_comparable():
    red, green = rec(1, red=True, files={"agent/a.py": "1"}), rec(2, files={"agent/a.py": "1"})
    red["base"], green["base"] = "aaa", "bbb"
    assert kinds([red, green]) == ["rebased"]


def test_several_reds_in_a_row_compare_the_last_red_with_the_green():
    records = [rec(1, red=True, files={"agent/a.py": "1"}), rec(2, red=True, files={"agent/a.py": "2"}),
               rec(3, files={"agent/a.py": "2"})]
    assert kinds(records) == ["flaky"]


def test_branches_and_worktrees_are_followed_separately():
    records = [rec(1, red=True, branch="a", files={"agent/a.py": "1"}), rec(2, branch="b"), rec(3, red=True, branch="b"),
               rec(4, branch="a", files={"agent/a.py": "1"}), rec(5, branch="b", worktree="other")]
    assert kinds(records) == ["flaky"]  # only a has a red followed by a green


def test_a_green_run_after_green_and_a_red_with_no_green_yet_make_no_transition():
    assert kinds([rec(1), rec(2), rec(3, red=True)]) == []


def test_the_summary_counts_runs_red_tests_classes_and_ranks_time():
    records = [
        rec(1, red=True, tests=["tests/test_a.py::test_x"], maa=["s.png Node: should hit but missed"],
            test_seconds={"test_a.py": 10.0, "test_b.py": 50.0}, files={"agent/a.py": "1"},
            steps=[{"name": "ruff", "exit": 0, "seconds": 2.0}, {"name": "pytest", "exit": 1, "seconds": 300.0}]),
        rec(2, test_seconds={"test_a.py": 20.0, "test_b.py": 70.0}, files={"agent/a.py": "2"},
            steps=[{"name": "ruff", "exit": 0, "seconds": 4.0}, {"name": "pytest", "exit": 0, "seconds": 400.0}]),
        rec(3, red=True, tests=["tests/test_a.py::test_x"], branch="c"),
    ]
    text = check_stats.summary(records)
    assert "runs: 3, red: 2, green: 1" in text
    assert "  2  tests/test_a.py::test_x" in text and "s.png Node: should hit but missed" in text
    assert "steps that went red: pytest 1, ruff 1" in text
    assert "red -> next green on the same branch: 1" in text and "  1  code changed" in text
    assert "1 red branch(es) never ran green" in text
    steps = text.split("slowest steps:")[1].split("slowest test files:")[0]
    assert steps.index("pytest") < steps.index("ruff") and "mean  266.7 s" in steps and "max  400.0 s" in steps
    files = text.split("slowest test files:")[1]
    assert files.index("test_b.py") < files.index("test_a.py") and "max   70.0 s" in files


def test_main_reads_the_period_from_the_log_and_survives_a_missing_or_damaged_log(tmp_path, capsys):
    log = tmp_path / "runs.jsonl"
    assert check_stats.main(["--log", str(log)]) == 0
    assert "no runs in the period" in capsys.readouterr().out
    old, new = rec(1), rec(10, red=True, tests=["tests/test_a.py::t"])
    log.write_text("\n".join([json.dumps(old), "not json", json.dumps(new)]) + "\n", encoding="utf-8")
    now = datetime.datetime.fromisoformat("2026-11-11T12:00:00+08:00")
    assert check_stats.main(["--log", str(log), "--days", "5"], now=now) == 0
    out = capsys.readouterr().out
    assert "runs: 1, red: 1" in out
    assert check_stats.main(["--log", str(log), "--since", "2026-10-01"], now=now) == 0
    assert "runs: 2, red: 1" in capsys.readouterr().out
