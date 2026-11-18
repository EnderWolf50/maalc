"""The run log: one file a start under <root>/logs/runner/, every line the runner sends as a log event, in
tools/live/bot.py's stamped format (`HH:MM:SS.fff <line>`, which tools/live/evidence.py reads). The newest KEEP stay."""
from __future__ import annotations

import datetime
from pathlib import Path

KEEP = 30
FOLDER = Path("logs") / "runner"


def clock() -> str:
    return f"{datetime.datetime.now():%H:%M:%S.%f}"[:-3]


def stamp(t: str, line: str) -> str:
    return f"{t} {line}\n"


def prune(folder: Path, keep: int = KEEP) -> None:
    """Delete all but the newest keep run logs (by modification time, then name); one another process holds stays."""
    logs = sorted(folder.glob("run-*.log"), key=lambda p: (p.stat().st_mtime_ns, p.name))
    for old in logs[:max(len(logs) - keep, 0)]:
        try:
            old.unlink()
        except OSError:
            pass


def open_new(root: Path, now=datetime.datetime.now):
    """A new run log under root, opened for appending a line at a time, the older ones pruned to KEEP with it."""
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    base = f"run-{now():%Y%m%d-%H%M%S}"
    path, n = folder / f"{base}.log", 1
    while path.exists():
        n += 1
        path = folder / f"{base}-{n}.log"
    f = open(path, "x", encoding="utf-8", buffering=1)
    prune(folder)
    return f
