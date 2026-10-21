import json
import os
import subprocess
import sys
from pathlib import Path

import slim_mcp


def test_slim_writes_merges_and_is_idempotent(tmp_path):
    f, changed = slim_mcp.slim(tmp_path)
    assert changed
    assert json.loads(f.read_text("utf8")) == {"enabledPlugins": {"tempad-dev@tempad-dev": False}, "deniedMcpServers": slim_mcp.DENIED}
    assert slim_mcp.slim(tmp_path) == (f, False)
    assert not list(f.parent.glob("*.bak-*"))

    f.write_text(json.dumps({"permissions": {"allow": ["x"]}, "deniedMcpServers": [{"serverName": "rea"}, {"serverName": "mine"}]}), "utf8")
    assert slim_mcp.slim(tmp_path)[1]
    got = json.loads(f.read_text("utf8"))
    assert got["permissions"] == {"allow": ["x"]}
    assert got["deniedMcpServers"] == [{"serverName": "rea"}, {"serverName": "mine"}, {"serverName": "playwright"}, {"serverName": "cua-driver"}]
    assert len(list(f.parent.glob("*.bak-*"))) == 1


def test_default_target_is_the_worktree_of_the_current_folder(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "sub").mkdir()
    assert slim_mcp.targets(tmp_path / "sub", False) == [tmp_path.resolve()]


def test_all_sweeps_every_worktree(monkeypatch, tmp_path):
    monkeypatch.setattr(slim_mcp, "worktrees", lambda: [tmp_path, tmp_path / "b"])
    assert slim_mcp.targets(tmp_path, True) == [tmp_path, tmp_path / "b"]


def test_the_command_line_names_a_bad_flag_and_a_non_git_folder(tmp_path):
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)}
    run = lambda *a: subprocess.run([sys.executable, str(Path(slim_mcp.__file__)), *a], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run("--bogus").returncode != 0
    got = run()
    assert got.returncode != 0 and "not inside a git worktree" in got.stderr and "Traceback" not in got.stderr
