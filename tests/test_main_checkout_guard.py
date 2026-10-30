"""The PreToolUse hook that keeps the main checkout on its branch."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude/hooks/main-checkout-guard.py"
spec = importlib.util.spec_from_file_location("main_checkout_guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

REFS = {"main", "feat/x", "v1.0", "abc1234"}


def denied(cmd, cwd="repo", main=lambda w: True):
    return guard.check(cmd, cwd, main=main, ref=lambda w, n: n in REFS) is not None


@pytest.mark.parametrize("cmd", [
    "git checkout feat/x",
    "git checkout main",
    "git checkout -b new",
    "git checkout -B new origin/main",
    "git checkout --orphan clean",
    "git checkout --detach abc1234",
    "git checkout v1.0",
    "git switch feat/x",
    "git switch -c new",
    "git switch -",
    "git checkout -",
    "git checkout main --",
    "git -C repo switch main",
    "git -c core.x=1 checkout main",
    "git.exe checkout main",
    "& git checkout main",
    "cd repo && git checkout feat/x",
    "git fetch; git checkout main",
    "git status | cat\ngit switch main",
])
def test_denied_in_the_main_checkout(cmd):
    assert denied(cmd)


@pytest.mark.parametrize("cmd", [
    "git checkout -- agent/x.py",
    "git checkout main -- agent/x.py",
    "git checkout HEAD agent/x.py",
    "git checkout agent/x.py",
    "git checkout .",
    "git checkout",
    "git status",
    "git branch -a",
    "git switch --help",
    "git log --oneline",
    "echo git switch main",
    "git worktree add ../wt -b new origin/main",
    "git commit -m 'git checkout main'",
])
def test_allowed_in_the_main_checkout(cmd):
    assert not denied(cmd)


def test_a_linked_worktree_may_switch():
    assert not denied("git switch -c new", main=lambda w: False)


def test_git_dash_c_checks_the_folder_it_names():
    seen = []
    guard.check("git -C other switch main", "repo", main=lambda w: seen.append(w) or False, ref=lambda w, n: True)
    assert seen == [Path("repo") / "other"]


def test_cd_changes_the_folder_for_later_calls():
    seen = []
    guard.check("cd sub; git switch main", "repo", main=lambda w: seen.append(w) or False, ref=lambda w, n: True)
    assert seen == [Path("repo") / "sub"]


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git("init", "-q", "-b", "main", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "--allow-empty", "-m", "x", cwd=main)
    git("branch", "feat/x", cwd=main)
    git("worktree", "add", "-q", str(tmp_path / "wt"), "-b", "other", cwd=main)
    return main, tmp_path / "wt"


def test_real_repo_main_checkout_denied_worktree_allowed(repo):
    main, wt = repo
    assert guard.check("git checkout feat/x", str(main)) == guard.DENY
    assert guard.check("git switch -c new", str(main)) == guard.DENY
    assert guard.check(f"git -C {main} checkout feat/x", str(wt)) == guard.DENY
    assert guard.check("git checkout feat/x -- .", str(main)) is None
    assert guard.check("git checkout feat/x", str(wt)) is None
    assert guard.check("git checkout main", str(wt.parent)) is None  # not a repo


def run_hook(cmd, cwd, tool="Bash"):
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd)}),
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["hookSpecificOutput"] if out else None


def test_hook_prints_a_deny_decision(repo):
    main, wt = repo
    decision = run_hook("git switch feat/x", main, tool="PowerShell")
    assert decision["permissionDecision"] == "deny" and decision["hookEventName"] == "PreToolUse"
    assert run_hook("git switch feat/x", wt) is None
