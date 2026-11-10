"""tools/release_draft.py: the release workflow creates a draft only for a tag that has no release yet (#587).

A fake `gh` answers the release listing and records every call; nothing reaches GitHub.
"""
import subprocess
import sys

import pytest
import release_draft as rd


class FakeGh:
    def __init__(self, tags):
        self.tags, self.calls = tags, []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "api":
            return "".join(f"{t}\n" for t in self.tags)
        return ""

    def creates(self):
        return [c for c in self.calls if c[:2] == ["release", "create"]]


@pytest.mark.parametrize("tags", [["v0.1.0"], ["v0.0.9", "v0.1.0", "v0.2.0"]])
def test_a_tag_with_a_release_creates_nothing(tags):
    # v0.1.0 (#587): published by hand, then its tag push ran the workflow again and made a second draft.
    gh, said = FakeGh(tags), []
    rd.draft("v0.1.0", "maalc-v0.1.0.zip", "a14a5d25", gh=gh, say=said.append)
    assert gh.creates() == [] and len(said) == 1 and "already has a release" in said[0]


def test_a_tag_with_no_release_creates_the_draft():
    gh = FakeGh(["v0.0.9", "v0.1.0-rc"])
    rd.draft("v0.1.0", "maalc-v0.1.0.zip", "a14a5d25", gh=gh, say=lambda line: None)
    assert gh.creates() == [["release", "create", "v0.1.0", "maalc-v0.1.0.zip", "--draft", "--target", "a14a5d25",
                             "--title", "v0.1.0", "--generate-notes"]]


def test_the_listing_takes_every_page_drafts_included():
    gh = FakeGh([])
    rd.draft("v0.1.0", "z.zip", "abc", gh=gh, say=lambda line: None)
    assert gh.calls[0] == ["api", "--paginate", "repos/{owner}/{repo}/releases", "--jq", ".[].tag_name"]


def test_a_listing_that_fails_creates_nothing():
    def gh(args):
        if args[0] == "api":
            raise subprocess.CalledProcessError(1, ["gh", *args])
        raise AssertionError(f"called after a failed listing: {args}")

    with pytest.raises(subprocess.CalledProcessError):
        rd.draft("v0.1.0", "z.zip", "abc", gh=gh, say=lambda line: None)


def test_a_failing_gh_leaves_its_error_in_the_log(monkeypatch, capfd):
    # The workflow log is all a failed release run shows: gh's own error (a token scope, a rate limit) must reach it.
    real_run, exit_code = subprocess.run, [1]

    def fake_gh(args, **kwargs):
        script = f"import sys; print('v0.1.0'); sys.stderr.write('HTTP 403: Resource not accessible'); sys.exit({exit_code[0]})"
        return real_run([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(rd.subprocess, "run", fake_gh)
    with pytest.raises(subprocess.CalledProcessError):
        rd.run_gh(["api", "repos/{owner}/{repo}/releases"])
    assert "HTTP 403" in capfd.readouterr().err
    exit_code[0] = 0
    assert rd.run_gh(["api", "repos/{owner}/{repo}/releases"]).strip() == "v0.1.0"  # stdout is still the answer


def test_the_workflow_runs_the_guard_in_place_of_a_bare_create():
    from pathlib import Path

    wf = (Path(__file__).resolve().parent.parent / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "gh release create" not in wf
    assert "tools/release_draft.py $env:TAG $env:ZIP $env:GITHUB_SHA" in wf
    assert "tools/release_draft.py" in wf.split("paths:")[1].splitlines()[0]  # a change to the guard builds on its PR
