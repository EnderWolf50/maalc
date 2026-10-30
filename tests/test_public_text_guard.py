"""The PreToolUse guard that keeps machine-local paths and personal terms out of public text."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / ".claude/hooks/public-text-guard.py"

# Path-shaped strings are assembled here, so no machine location sits in a repo file as one piece.
WIN = "C" + ":" + "\\Users\\x\\a.png"  # a Windows path with backslashes
WIN_FWD = "D" + ":" + "/work/x"  # the same with forward slashes
HOME = "/" + "home/bob/x"
MNT = "/" + "mnt/c/Users/a"
TILDE = "~" + "/.cache/probe"
FILE_URL = "file" + ":///tmp/x"


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "--local", "--add", "maalc.privateTerm", "secret-folder"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "--local", "user.email", "someone@example.test"], check=True)
    (tmp_path / "clean.md").write_text("Fixed the shop tooltip.")
    (tmp_path / "dirty.md").write_text(f"Evidence is in {WIN}")
    return tmp_path


def reason(cmd, cwd, **env):
    """The deny reason, or None when the guard lets the command through."""
    out = subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd)}),
                         capture_output=True, text=True, check=True, env={**os.environ, "USERNAME": "", "USER": "", **env}).stdout
    if not out:
        return None
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse" and decision["permissionDecision"] == "deny"
    return decision["permissionDecisionReason"]


def denied(cmd, cwd, **env):
    return reason(cmd, cwd, **env) is not None


MUST_HIT = [
    f'gh issue comment 1 --body "see {WIN}"',
    f'gh pr create --title t --body "saved to {WIN_FWD}"',
    f'git commit -m "log in {HOME}"',
    f'git -C {WIN_FWD} commit -m "see {FILE_URL}"',
    f'gh api repos/o/r/issues -f body="{MNT}"',
    f'gh issue create --title t --body "copy {TILDE}"',
    'cd /x && gh pr edit 3 --body "the secret-folder holds it"',  # a personal term from git config
    'git commit -m "mail someone@example.test"',  # user.email
    "gh pr comment 4 --body-file dirty.md",  # the file's contents count
    "gh api repos/o/r/issues -F body=@dirty.md",
    'gh issue close 3 --comment "see ' + WIN + '"',
    'gh pr close 3 --comment "see ' + WIN + '"',
    'gh pr merge 3 --squash --subject "s" --body "see ' + WIN + '"',
    "gh pr merge 3 --squash -F dirty.md",
    'gh release create v1 --notes "see ' + WIN + '"',
    "gh release create v1 --notes-file dirty.md",
    'git merge side -m "see ' + WIN + '"',
    'git tag -a v1 -m "see ' + WIN + '"',
    'git --no-pager commit -m "see ' + WIN + '"',
    "git commit -Fdirty.md",
    "git commit --file=dirty.md",
    f'gh pr create --title t --body ok && gh issue comment 1 --body "see {WIN}"',  # every call in a line is checked
    f'git commit -m ok; git tag -a v1 -m "see {WIN}"',
    # bash's backslash rules: an escaped separator or a line continuation does not end the call
    f"gh issue comment 1 --body a\\;{WIN_FWD}",
    f"gh issue comment 1 --body a\\|{WIN_FWD}",
    f"git commit -m fix\\;{WIN_FWD}",
    f'gh issue comment 1 \\\n  --body "{WIN_FWD}"',
    "gh pr create --title t \\\n  --body-file dirty.md",
    "git commit \\\n  -F dirty.md",
    # quotes as bash reads them: no escape inside '...', an escaped quote outside quotes opens nothing
    f"gh issue comment 1 --body 'a\\''; {WIN_FWD}'",
    f'gh issue comment 1 --body \\""; {WIN_FWD}"',
    # a call inside a quoted command string (bash -c, eval) is checked through to the end of the line
    f'bash -c "gh issue comment 1 --body a\\\\;{WIN_FWD}"',
    # a quote inside a comment or a heredoc body must not flip the inside-quotes reading
    f'true # "\nbash -c "gh issue comment 1 --body \\";{WIN_FWD}\\""',
    f"cat > /dev/null <<'E'\n\"\nE\nbash -c \"gh issue comment 1 --body \\\";{WIN_FWD}\\\"\"",
    f"gh issue comment 1 --body ${{x:-a;{WIN_FWD}}}",  # a separator inside ${...} does not end the call
    # flags named inside a quoted body are text, so they cannot hide what follows
    f'gh issue comment 1 --body "see -C {WIN_FWD}"',
    f'gh issue comment 1 --body "see --attach {WIN_FWD}"',
    'gh issue comment 1 --body "see -R secret-folder"',
]
MUST_PASS = [
    'gh issue comment 1 --body "see https://github.com/EnderWolf50/maalc/pull/2 and tests/screens/Title.png"',
    f"gh pr create --title t --body ok --attach '{WIN}#login error'",
    f'git -C {WIN_FWD} commit -m "fix the shop"',
    f"cd {WIN_FWD} && gh issue view 3",
    f"ls {WIN}",  # not public text
    "gh pr comment 4 --body-file clean.md",
    "gh issue create --repo EnderWolf50/maalc --title t --body 'a/b/c and docs/agents/local-dev.md'",
    'gh issue comment 1 --body "the home screen: https://example.com/home/x"',
    "gh api repos/o/r/issues -F body=@clean.md",
    "gh api repos/o/r/issues -F draft=true -f title=t",
    "gh pr merge 3 --squash",
    "git merge side",
    "git commit -Fclean.md",
    # a substitution in a later command is not this call's text
    'gh pr merge 168 --merge && [ "$(gh pr view 168 --json state -q .state)" = MERGED ] && echo merged',
    'gh pr merge 3 --merge; s=`gh pr view 3 --json state`',
    'git commit -m "fix: tidy" && echo "$(git log -1 --format=%h)"',
    # a flag named inside a quoted message is text, not a flag
    'git commit -m "add EMPTY_FLAG for a --body-file with no value"',
    'git commit -m "use -F to pass a file; deny the --input flag"',
    'gh pr create --title t --body "gh -F is --body-file"',
    "git commit -m \"fix: tidy\" # don't\nls " + WIN_FWD,  # a comment's quote does not swallow the next line
]


@pytest.mark.parametrize("cmd", MUST_HIT)
def test_denies(cmd, repo):
    assert denied(cmd, repo)


@pytest.mark.parametrize("cmd", MUST_PASS)
def test_allows(cmd, repo):
    assert not denied(cmd, repo)


def test_attach_alt_text_is_checked(repo):
    assert denied(f"gh pr create --body ok --attach 'a.png#from {WIN}'", repo)


UNREADABLE_CMDS = [
    "gh pr create --body-file - < clean.md",
    "gh issue comment 1 --body-file=-",
    "git commit -F -",
    "gh api repos/o/r/issues -F body=@-",
    'gh issue comment 1 --body "$(cat clean.md)"',
    'gh api repos/o/r/issues -f body="$(cat clean.md)"',
    'gh issue comment 1 --body "`cat clean.md`"',
    "gh api repos/o/r/issues --input clean.md",
    "git commit -m \"$(cat <<'EOF'\nfix\nEOF\n)\"",
    "gh pr comment 1 --body-file missing.md",  # a file created earlier in the same command does not exist yet
    "echo hi > b.md && gh pr comment 1 --body-file b.md",
    "git commit -Fmissing.md",
    "echo dirty.md | xargs gh issue comment 1 --body-file && echo done",  # xargs supplies the file
    "echo dirty.md | xargs gh issue comment 1 --body-file",
]


@pytest.mark.parametrize("cmd", UNREADABLE_CMDS)
def test_text_it_cannot_read_is_denied_with_the_way_out(cmd, repo):
    assert "pass its absolute Windows path to --body-file" in reason(cmd, repo)


def test_relative_body_file_resolves_after_cd_and_git_C(repo):
    (repo / "sub").mkdir()
    (repo / "sub/ok.md").write_text("fine")
    (repo / "sub/bad.md").write_text(f"see {WIN}")
    assert not denied("cd sub && gh pr comment 1 --body-file ok.md", repo)
    assert denied("cd sub && gh pr comment 1 --body-file bad.md", repo)
    assert not denied("git -C sub commit -F ok.md", repo)
    assert denied("git -C sub commit -F bad.md", repo)


@pytest.mark.skipif(not shutil.which("cygpath"), reason="needs Git Bash's cygpath")
def test_slash_rooted_body_file_is_read_through_cygpath(repo):
    ok, bad = repo / "ok.md", repo / "bad.md"
    ok.write_text("fine")
    bad.write_text(f"see {WIN}")
    posix = lambda p: subprocess.run(["cygpath", "-u", str(p)], capture_output=True, text=True, check=True).stdout.strip()
    assert not denied(f"gh pr comment 1 --body-file {posix(ok)}", "/")
    assert denied(f"gh pr comment 1 --body-file {posix(bad)}", "/")


def test_login_name_counts_only_as_a_path_segment(repo):
    assert not denied('gh issue comment 1 --body "fixed the shop tooltip"', repo, USERNAME="shop")
    assert denied('gh issue comment 1 --body "log in /work/shop/x"', repo, USERNAME="shop")


def test_repo_flag_is_dropped_from_the_command_but_not_from_a_body_file(repo):
    (repo / "flag.md").write_text("run it with -C secret-folder")  # a body that merely mentions the flag
    assert not denied("gh issue create -R secret-folder/x --title t --body ok", repo)
    assert denied("gh issue create --title t --body-file flag.md", repo)


def test_subagent_preamble_hook_injects_the_preamble_doc():
    hook = GUARD.with_name("subagent-preamble.py")
    out = json.loads(subprocess.run([sys.executable, str(hook)], capture_output=True, text=True, check=True).stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "maalc-live-test" in out["hookSpecificOutput"]["additionalContext"]

def test_an_absolute_path_to_a_body_file_is_read_not_judged(repo):
    # The path names the file; only its content is public. Any --<word>-file flag counts as a file flag.
    for flag in ("--body-file", "--comment-file", "-F"):
        assert not denied(f"gh issue comment 1 {flag} '{repo / 'clean.md'}'", repo, USERNAME="")
        assert denied(f"gh issue comment 1 {flag} '{repo / 'dirty.md'}'", repo)
    assert denied(f"gh issue comment 1 --body-file '{repo / 'clean.md'}' --body 'see {WIN}'", repo)


def test_a_local_note_label_is_denied(repo):
    assert denied('gh pr create --title t --body "see questions-1 no. 8"', repo)
    assert denied('git commit -m "answer Questions-12"', repo)
    assert not denied('gh pr create --title t --body "open questions: 1"', repo)


GOOD_BODY = "## Verification\n\n- Tests: `uv run pytest` -> 12 passed, 0 failed\n- Live: not run: the shop path, tracked in #77\n"


def pr_body(repo, text, call="gh pr create --title t --body-file body.md"):
    (repo / "body.md").write_text(text)
    return reason(call, repo)


def test_a_pr_body_needs_the_test_line_and_an_issue_for_each_not_run(repo):
    assert pr_body(repo, GOOD_BODY) is None
    assert pr_body(repo, GOOD_BODY, "gh pr edit 3 --body-file body.md") is None
    assert "N passed, M failed" in pr_body(repo, "- Tests: 1393 collected, 0 failed\n")
    assert "`not run` without the issue" in pr_body(repo, GOOD_BODY + "- Live: not run on the emulator\n")
    assert pr_body(repo, GOOD_BODY + "- Live: not run: none\n") is None


def test_the_test_line_takes_an_optional_skipped_count_and_docs_only_has_its_own_form(repo):
    assert pr_body(repo, "- Tests: `uv run pytest` -> 12 passed, 0 failed, 3 skipped\n") is None
    assert "N passed, M failed" in pr_body(repo, "- Tests: `uv run pytest` -> 12 passed, 3 skipped\n")
    assert pr_body(repo, "## Verification\n\n- Tests: none (docs only)\n") is None
    assert pr_body(repo, "## Verification\n\n- Tests: none (docs only)\n- Live: not run: none\n") is None
    assert "docs only" in pr_body(repo, "## Verification\n\n- Live: not run: none\n")
    assert "docs only" in pr_body(repo, "## Verification\n\n- Tests: none\n")


def test_only_pr_create_and_edit_bodies_are_linted(repo):
    assert pr_body(repo, "short note", "gh pr comment 3 --body-file body.md") is None
    assert pr_body(repo, "short note", "gh issue create --title t --body-file body.md") is None
    assert pr_body(repo, "short note", "gh pr edit 3 --title t") is None


def test_cannot_run_is_not_a_not_run_item(repo):
    assert pr_body(repo, GOOD_BODY + "- Live: cannot run on Linux\n") is None
