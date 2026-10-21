"""Keep rea, playwright and tempad-dev out of agent sessions in this repo and every worktree.

Claude Code reads `.claude/settings.local.json` from the session's own folder (on Windows a
worktree does not use the main checkout's file), so write it into each worktree. Idempotent;
merges into an existing file and keeps `<file>.bak-<date>` of one it changes.
"""
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

PLUGINS = {"tempad-dev@tempad-dev": False}
DENIED = [{"serverName": "rea"}, {"serverName": "playwright"}]


def worktrees(cwd=None):
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=True).stdout
    return [Path(line[9:]) for line in out.splitlines() if line.startswith("worktree ")]


def merged(cur):
    denied = cur.get("deniedMcpServers", [])
    return {**cur, "enabledPlugins": {**cur.get("enabledPlugins", {}), **PLUGINS},
            "deniedMcpServers": denied + [s for s in DENIED if s not in denied]}


def slim(wt):
    f = wt / ".claude" / "settings.local.json"
    cur = json.loads(f.read_text(encoding="utf8")) if f.exists() else {}
    new = merged(cur)
    if new == cur:
        return f, False
    f.parent.mkdir(exist_ok=True)
    if f.exists():
        shutil.copy2(f, f.with_name(f"{f.name}.bak-{date.today():%Y%m%d}"))
    f.write_text(json.dumps(new, indent=2) + "\n", encoding="utf8")
    return f, True


if __name__ == "__main__":
    for wt in worktrees():
        f, changed = slim(wt)
        print("written" if changed else "ok     ", f)
