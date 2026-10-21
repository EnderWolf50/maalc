import json

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
    assert got["deniedMcpServers"] == [{"serverName": "rea"}, {"serverName": "mine"}, {"serverName": "playwright"}]
    assert len(list(f.parent.glob("*.bak-*"))) == 1
