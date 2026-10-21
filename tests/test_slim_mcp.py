import json
import subprocess

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
