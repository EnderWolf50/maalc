"""The `read` filter of the CI `changes` job names the non-code files the Python tests read (#684, tests/ci_filter.py)."""
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

import ci_filter as cf
import conftest


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=cf.ROOT, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def test_glob_patterns_cross_folders_only_with_two_stars():
    assert cf.matches(["docs/**"], "docs/spec/04-settings.md") and cf.matches(["docs/**"], "docs/a.md")
    assert cf.matches(["*.md"], "README.md") and not cf.matches(["*.md"], "docs/a.md")
    assert cf.matches(["**/x.py"], "x.py") and cf.matches(["**/x.py"], "a/b/x.py") and not cf.matches(["**/x.py"], "a/xy.py")
    assert not cf.matches(["gui/src/i18n.ts"], "gui/src/i18n.tsx")


def test_docs_spec_alone_still_skips_the_tests_and_gui_i18n_alone_runs_them():
    # #684 acceptance: a PR that changes only gui/src/i18n.ts runs the agent job; one that changes only docs/spec/ skips it.
    outside, listed = cf.not_code(), cf.read_patterns()
    assert cf.matches(outside, "docs/spec/04-settings.md") and not cf.matches(listed, "docs/spec/04-settings.md")
    assert cf.matches(outside, "gui/src/i18n.ts") and cf.matches(listed, "gui/src/i18n.ts")


def test_the_code_output_also_counts_the_read_filter():
    # `code` is the agent job's switch: the files the read filter names switch it on beside the code filter.
    jobs = yaml.safe_load(cf.CI.read_text(encoding="utf-8"))["jobs"]
    assert "steps.readfilter.outputs.read == 'true'" in jobs["changes"]["outputs"]["code"]
    step = cf.changes_steps()["readfilter"]
    assert "predicate-quantifier" not in step["with"]  # `every` would need one file to match all of them


def test_the_read_filter_holds_only_non_code_files_that_exist():
    outside, files = cf.not_code(), tracked()
    patterns = cf.read_patterns()
    assert [p for p in patterns if not cf.matches(outside, p)] == []  # a code file is run anyway: the entry does nothing
    assert [p for p in patterns if not any(cf.matches([p], f) for f in files)] == []  # a renamed or deleted file


def test_a_pattern_with_picomatch_syntax_this_does_not_read_is_refused():
    for pattern in ("docs/{spec,adr}/**", "gui/[ab].ts", "!(docs)/**"):
        with pytest.raises(ValueError):
            cf.glob_regex(pattern)


def test_a_file_a_test_opens_outside_the_read_filter_is_named():
    assert cf.unlisted(["gui/src/i18n.ts", "agent/main.py", "tests/shard_seconds.json"]) == []
    assert cf.unlisted(["docs/spec/04-settings.md", "gui/src/i18n.ts", "README.md", "LICENSE"]) == [
        "LICENSE", "README.md", "docs/spec/04-settings.md"]


def test_record_notes_the_files_of_the_repository_the_way_the_opener_wrote_them(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "OPENED", set())
    cf.record(cf.ROOT / "gui" / "src" / "i18n.ts")
    cf.record(tmp_path / "README.md")  # outside the repository
    cf.record(cf.ROOT / ".venv" / "Lib" / "x.md")
    cf.record(3)  # a file descriptor
    assert cf.OPENED == {"gui/src/i18n.ts"}


def test_the_hook_notes_a_real_open(monkeypatch):
    monkeypatch.setattr(cf, "OPENED", set())
    (cf.ROOT / "docs" / "agents" / "triage-labels.md").read_text(encoding="utf-8")
    assert "docs/agents/triage-labels.md" in cf.OPENED


def test_a_listed_folder_of_docs_is_noted_with_a_closing_slash(monkeypatch):
    monkeypatch.setattr(cf, "OPENED", set())
    cf.record(cf.ROOT / "docs" / "adr", listing=True)
    cf.record(cf.ROOT / "tests", listing=True)  # the code folders are listed all the time
    assert cf.OPENED == {"docs/adr/"} and cf.unlisted(cf.OPENED) == ["docs/adr/"]


def test_a_python_child_reports_what_it_opens():
    # tests/ci_child/sitecustomize.py: a file only a child reads (test_subagent_preamble's hook script) is noted too.
    code = "open(r'%s', encoding='utf-8').close()" % (cf.ROOT / "docs" / "agents" / "watchdog-prompt.md")
    subprocess.run([sys.executable, "-c", code], check=True)
    assert "docs/agents/watchdog-prompt.md" in cf.all_opened()


@pytest.mark.parametrize("opened, status", [({"gui/src/i18n.ts"}, 0), ({"docs/spec/04-settings.md"}, pytest.ExitCode.TESTS_FAILED)])
def test_a_run_that_opened_an_unlisted_file_fails(monkeypatch, capsys, opened, status):
    # conftest.pytest_sessionfinish: the shard fails until the read filter names the file.
    monkeypatch.setattr(cf, "all_opened", lambda: opened)
    monkeypatch.setattr(cf, "forget_log", lambda: None)  # the real log is still collecting the rest of this run
    session = SimpleNamespace(exitstatus=0)
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == status
    assert ("docs/spec/04-settings.md" in capsys.readouterr().out) == (status != 0)
