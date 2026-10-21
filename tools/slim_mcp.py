"""Keep rea, playwright, cua-driver and tempad-dev out of agent sessions in this repo and every worktree.

Claude Code reads `.claude/settings.local.json` from the session's own folder (on Windows a
worktree does not use the main checkout's file), so write it into the worktree of the current
folder, or with `--all` into every worktree. Idempotent; merges into an existing file and keeps
`<file>.bak-<date>` of one it changes.
"""
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

DISABLED_PLUGINS = {"tempad-dev@tempad-dev": False}
DENIED = [{"serverName": "rea"}, {"serverName": "playwright"}, {"serverName": "cua-driver"}]


def worktrees():
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=Path(__file__).parent, capture_output=True, text=True, check=True).stdout
    paths = [Path(line[9:]) for line in out.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p.is_dir()]  # a deleted, unpruned worktree is still listed


def targets(cwd, all_worktrees):
    if all_worktrees:
        return worktrees()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    return [Path(top).resolve()]


def merged(cur):
    denied = cur.get("deniedMcpServers", [])
    return {**cur, "enabledPlugins": {**cur.get("enabledPlugins", {}), **DISABLED_PLUGINS},
            "deniedMcpServers": denied + [s for s in DENIED if s not in denied]}


def slim(wt):
    f = wt / ".claude" / "settings.local.json"
    cur = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
    new = merged(cur)
    if new == cur:
        return f, False
    f.parent.mkdir(exist_ok=True)
    bak = f.with_name(f"{f.name}.bak-{date.today():%Y%m%d}")
    if f.exists() and not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return f, True


if __name__ == "__main__":
    for wt in targets(Path.cwd(), "--all" in sys.argv[1:]):
        try:
            f, changed = slim(wt)
            print("written" if changed else "ok     ", f)
        except (OSError, ValueError, TypeError, AttributeError) as e:
            print("skip   ", wt, e)
