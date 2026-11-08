"""Memory of a live run's process tree, sampled until its root ends: the memory half of a performance fix's
before/after (CODING_STANDARDS.md "Fixes"). Windows only: private bytes are Windows' commit charge.

    uv run --group probe python tools/live/memwatch.py --pid ROOT --csv mem.csv [--every 5]

ROOT is the bot's pid (the one `queue.py detach` prints for `bot.py run`) or a client's (MXU, MFAAvalonia). Each
sample lists the tree again, so the tasker and the agent, which start after the root, are counted. The CSV has one
row per process per sample: time, pid, role, name, working set and private bytes in MB. The role comes from the
command line: `tasker` (`bot.py tasker`, where MaaFramework recognises), `agent` (`agent/main.py`), `client` (MXU,
MFAAvalonia), `other`. A venv's python.exe is a launcher that starts the real interpreter under it with the same
command line, so a role counts both; the launcher is about 12 MB of working set and 3 MB private. When the root ends
it prints the peak and the last sample of the whole tree and of each role.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import NamedTuple

FIELDS = ["time", "pid", "role", "name", "working_set_mb", "private_mb"]


class Mem(NamedTuple):
    working_set: float
    private: float


def role(name: str, cmdline: list[str]) -> str:
    args = [a.replace("\\", "/") for a in cmdline]
    if any(a.endswith("agent/main.py") for a in args):
        return "agent"
    if any(a.endswith("bot.py") for a in args) and "tasker" in args:
        return "tasker"
    if name.lower().startswith(("mxu", "mfaavalonia")):
        return "client"
    return "other"


def sample(root, now: str) -> list[dict]:
    """A row per process of root's tree; none once root has ended."""
    import psutil

    try:
        procs = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []
    rows = []
    for p in procs:
        try:
            with p.oneshot():
                m = p.memory_info()
                name = p.name()
                try:
                    cmdline = p.cmdline()
                except psutil.AccessDenied:
                    cmdline = []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        rows.append({"time": now, "pid": p.pid, "role": role(name, cmdline), "name": name,
                     "working_set_mb": round(m.rss / 2**20, 1), "private_mb": round(m.private / 2**20, 1)})
    return rows


def summary(rows: list[dict]) -> list[str]:
    """Peak and last of the tree's sum and of each role's sum, over the samples in the order they were taken."""
    sums: dict[str, dict[str, Mem]] = defaultdict(dict)
    for r in rows:
        for group in ("tree", r["role"]):
            had = sums[group].get(r["time"], Mem(0.0, 0.0))
            sums[group][r["time"]] = Mem(had.working_set + float(r["working_set_mb"]), had.private + float(r["private_mb"]))
    lines = []
    for group in ["tree", *sorted(g for g in sums if g != "tree")]:
        series = sums[group]
        ws_at = max(series, key=lambda t: series[t].working_set)
        private_at = max(series, key=lambda t: series[t].private)
        last_at = list(series)[-1]
        lines.append(f"{group}: peak working set {series[ws_at].working_set:.1f} MB at {ws_at}, peak private "
                     f"{series[private_at].private:.1f} MB at {private_at}; last {last_at}: working set "
                     f"{series[last_at].working_set:.1f} MB, private {series[last_at].private:.1f} MB")
    return lines


def main(argv=None) -> int:
    import psutil

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--every", type=float, default=5, help="seconds between samples")
    args = ap.parse_args(argv)
    root = psutil.Process(args.pid)
    rows: list[dict] = []
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        while sampled := sample(root, datetime.now().strftime("%H:%M:%S.%f")[:-3]):
            writer.writerows(sampled)
            f.flush()
            rows += sampled
            time.sleep(args.every)
    print("\n".join(summary(rows)) or "no sample")
    return 0


if __name__ == "__main__":
    sys.exit(main())
