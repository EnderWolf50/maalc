"""The PreToolUse guard that keeps machine-local paths and personal terms out of public text."""
import json
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


def denied(cmd, cwd):
    out = subprocess.run([sys.executable, str(GUARD)], input=json.dumps({"tool_input": {"command": cmd}, "cwd": str(cwd)}),
                         capture_output=True, text=True, check=True).stdout
    if not out:
        return False
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse" and decision["permissionDecision"] == "deny"
    return True


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
]


@pytest.mark.parametrize("cmd", MUST_HIT)
def test_denies(cmd, repo):
    assert denied(cmd, repo)


@pytest.mark.parametrize("cmd", MUST_PASS)
def test_allows(cmd, repo):
    assert not denied(cmd, repo)


def test_attach_alt_text_is_checked(repo):
    assert denied(f"gh pr create --body ok --attach 'a.png#from {WIN}'", repo)


def test_subagent_preamble_hook_injects_the_preamble_doc():
    hook = GUARD.with_name("subagent-preamble.py")
    out = json.loads(subprocess.run([sys.executable, str(hook)], capture_output=True, text=True, check=True).stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "maalc-live-test" in out["hookSpecificOutput"]["additionalContext"]
