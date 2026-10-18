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
