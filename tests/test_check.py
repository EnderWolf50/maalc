"""tools/check.py (#484): pytest runs as SHARDS processes at once, SHARD=i of SHARDS each, so tests/conftest.py splits the
files as CI's agent job does; the step fails when any shard fails, and its output names that shard."""

import json
import subprocess
import types
from pathlib import Path

import pytest

# A check.py that runs at import (before #484) would start the whole check from inside pytest, which collects this file
# again and recurses without end; fail at collection instead.
assert 'if __name__ == "__main__":' in (Path(__file__).parents[1] / "tools" / "check.py").read_text(encoding="utf-8")

import check  # noqa: E402

PYTEST = ["uv", "run", "pytest", "-q"]


class Popen:
    """subprocess.Popen as check.run_step calls it: each process writes one line naming its shard to the stdout it is
    given and ends with codes[shard]; the start of shard `fails` raises. events lists the starts and waits in order."""

    def __init__(self, codes, fails=None):
        self.codes, self.fails, self.envs, self.events, self.started, self.cmds = codes, fails, [], [], [], []

    def __call__(self, cmd, stdout, stderr, env=None):
        shard = int(env["SHARD"]) if env and "SHARD" in env else 0
        if shard == self.fails:
            raise FileNotFoundError(cmd[0])
        self.envs.append(env)
        self.cmds.append(cmd)
        self.events.append(("start", shard))
        stdout.write(f"output of shard {shard}\n")
        stdout.flush()
        process = types.SimpleNamespace(shard=shard, done=False)
        process.wait = lambda: self.events.append(("wait", shard)) or setattr(process, "done", True) or self.codes[shard]
        process.poll = lambda: self.codes[shard] if process.done else None
        self.started.append(process)
        return process


def test_pytest_runs_as_four_shards_at_once():
    popen = Popen([0, 0, 0, 0])
    code, shown = check.run_step(PYTEST, 4, popen)
    assert code == 0 and shown == ""
    assert [(e["SHARDS"], e["SHARD"]) for e in popen.envs] == [("4", "0"), ("4", "1"), ("4", "2"), ("4", "3")]
    assert [kind for kind, _ in popen.events] == ["start"] * 4 + ["wait"] * 4  # every shard starts before any wait


def test_a_failing_shard_fails_the_step_and_shows_its_output():
    code, shown = check.run_step(PYTEST, 4, Popen([0, 0, 1, 0]))
    assert code == 1
    assert "shard 2 of 4" in shown and "output of shard 2" in shown
    assert "output of shard 0" not in shown and "output of shard 3" not in shown


def test_another_step_runs_once_without_a_shard():
    popen = Popen([1])
    code, shown = check.run_step(["uv", "run", "ruff", "check"], 1, popen)
    assert code == 1 and "output of shard 0" in shown and "shard 0 of" not in shown
    assert popen.envs == [None]


def test_a_shard_that_cannot_start_ends_the_ones_already_running():
    popen, stopped = Popen([0, 0, 0, 0], fails=2), []
    with pytest.raises(FileNotFoundError):
        check.run_step(PYTEST, 4, popen, stop=stopped.append)
    assert [p.shard for p in stopped] == [0, 1]


def test_only_pytest_runs_as_shards_and_every_line_has_its_seconds(capsys):
    calls = []
    assert check.main(run=lambda cmd, shards: calls.append((cmd[2], shards)) or (0, ""), has_base=lambda base: True, log=None) == 0
    assert calls == [("ruff", 1), ("python", 1), ("pytest", check.SHARDS), ("maa-tools", 1), ("maa-tools", 1)]
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 5 and all(line.startswith("== ") and line.endswith(" s") and ": exit 0, " in line for line in lines)


def test_review_lint_compares_with_origin_main_and_a_failure_counts(capsys):
    calls = []
    assert check.main(run=lambda cmd, shards: calls.append(cmd) or (1 if "tools/review_lint.py" in cmd else 0, "term"),
                      has_base=lambda base: True, log=None) == 1
    assert ["uv", "run", "python", "tools/review_lint.py", "origin/main"] in calls
    assert "term" in capsys.readouterr().out


def test_review_lint_is_skipped_with_its_reason_when_there_is_no_base_to_compare_with(capsys):
    calls = []
    assert check.main(run=lambda cmd, shards: calls.append(cmd[2]) or (0, ""), has_base=lambda base: False, log=None) == 0
    assert "python" not in calls and len(calls) == 4
    out = capsys.readouterr().out
    assert "skipped" in out and "origin/main" in out and "git fetch" in out


def test_has_base_asks_git_whether_the_ref_exists():
    assert check.has_base("HEAD") and not check.has_base("origin/no-such-branch-628")


@pytest.mark.parametrize(("cores", "shards"), [(32, 4), (16, 4), (8, 2), (4, 1), (2, 1), (1, 1)])
def test_one_shard_per_four_cores_as_on_ci(cores, shards):
    assert check.pytest_shards(cores) == shards


# The run log (#633): one JSON line per run, in the main checkout's .local/.
JUNIT_XML = """<testsuites><testsuite>
<testcase classname="tests.test_a" name="test_ok" time="1.25"/>
<testcase classname="tests.test_a" name="test_red" time="0.5"><failure message="x"/></testcase>
<testcase classname="tests.test_b.TestK" name="test_err" time="2"><error message="y"/></testcase>
</testsuite></testsuites>"""
MAA_OUT = "\x1b[31mgroup\x1b[0m\n  tests/screens/a.png NodeA should hit but missed\n  tests/screens/b.png NodeB should missed but hit\n"


def fake_run(codes, maa_text=""):
    """A check.run_step stand-in: pytest writes a junit file where --junitxml says, maa-tools test shows `maa_text`."""
    def run(cmd, shards):
        name = check.step_name(cmd)
        if name == "pytest":
            path = next(arg for arg in cmd if arg.startswith("--junitxml=")).split("=", 1)[1].replace("{shard}", "0")
            Path(path).write_text(JUNIT_XML, encoding="utf-8")
        shown = check.Shown(maa_text if name == "maa-tools test" else "")
        shown.texts = (maa_text,) if name == "maa-tools test" else ()
        return codes.get(name, 0), shown
    return run


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_passing_run_leaves_one_full_record(tmp_path):
    log = tmp_path / "sub" / "runs.jsonl"
    assert check.main(run=fake_run({}), has_base=lambda base: False, log=lambda: log) == 0
    (rec,) = records(log)
    assert rec["v"] == 1 and rec["started"] and rec["seconds"] >= 0
    assert rec["branch"] and len(rec["head"]) == 40 and isinstance(rec["dirty"], bool) and isinstance(rec["files"], dict)
    assert [(s["name"], s["exit"]) for s in rec["steps"]] == [("ruff", 0), ("pytest", 0), ("maa-tools check", 0), ("maa-tools test", 0)]
    assert all(s["seconds"] >= 0 for s in rec["steps"])
    assert rec["test_seconds"] == {"test_a.py": 1.8, "test_b.py": 2.0}  # the file of the junit report, summed
    assert rec["failed_maa"] == []


def test_a_failing_run_records_the_red_tests_and_maa_cases_and_review_lint_when_it_ran(tmp_path):
    log = tmp_path / "runs.jsonl"
    codes = {"pytest": 1, "maa-tools test": 1}
    assert check.main(run=fake_run(codes, MAA_OUT), has_base=lambda base: True, log=lambda: log) == 2
    (rec,) = records(log)
    assert [(s["name"], s["exit"]) for s in rec["steps"]] == [("ruff", 0), ("review_lint", 0), ("pytest", 1), ("maa-tools check", 0),
                                                              ("maa-tools test", 1)]
    assert rec["failed_tests"] == ["tests/test_a.py::test_red", "tests/test_b.py::TestK::test_err"]
    assert rec["failed_maa"] == ["tests/screens/a.png NodeA: should hit but missed", "tests/screens/b.png NodeB: should missed but hit"]


def test_runs_append_lines(tmp_path):
    log = tmp_path / "runs.jsonl"
    for _ in range(2):
        check.main(run=fake_run({}), has_base=lambda base: False, log=lambda: log)
    assert len(records(log)) == 2


def test_a_log_that_cannot_be_written_warns_and_the_run_goes_on(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert check.main(run=fake_run({"ruff": 1}), has_base=lambda base: False, log=lambda: blocker / "runs.jsonl") == 1
    out = capsys.readouterr().out
    assert "check log not written" in out and "== uv run ruff check: exit 1" in out


def test_the_files_of_a_record_follow_the_working_tree_not_the_commits(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "a@b"], ["config", "user.name", "n"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    (repo / "a.py").write_text("1", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    (repo / "a.py").write_text("2", encoding="utf-8")  # unstaged edit
    (repo / "new.py").write_text("3", encoding="utf-8")  # untracked
    monkeypatch.setattr(check, "ROOT", repo)
    files = check.work_tree_files(base)
    assert set(files) == {"a.py", "new.py"}
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "two"], cwd=repo, check=True)
    assert check.work_tree_files(base) == files  # committing the same change gives the same blobs


def test_each_shard_gets_its_own_number_in_the_arguments():
    popen = Popen([0, 0])
    check.run_step(["x", "--junitxml=/j/{shard}.xml"], 2, popen)
    assert [cmd[1] for cmd in popen.cmds] == ["--junitxml=/j/0.xml", "--junitxml=/j/1.xml"]


def test_a_checkout_that_has_no_origin_main_to_compare_with_records_no_base(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "a@b"], ["config", "user.name", "n"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    monkeypatch.setattr(check, "ROOT", repo)
    state = check.checkout_state(True)  # has_base said yes, but this repo has no origin/main to compare with
    assert state["base"] is None and state["files"] == {} and len(state["head"]) == 40
