"""Memory of a live run's process tree, sampled until its root ends: the memory half of a performance fix's
before/after (CODING_STANDARDS.md "Fixes").

    uv run --group probe python tools/live/memwatch.py --pid ROOT --csv mem.csv [--every 5]

ROOT is the bot's pid (the one `queue.py detach` prints for `bot.py run`) or a client's (MXU, MFAAvalonia). Each
sample lists the tree again, so the tasker and the agent, which start after the root, are counted. The CSV has one
row per process per sample: time, pid, role, name, working set and private bytes in MB. The role comes from the
command line: `tasker` (`bot.py tasker`, where MaaFramework recognises), `agent` (`agent/main.py`), `client` (MXU,
MFAAvalonia), `other`. When the root ends it prints the peak and the last sample of the whole tree and of each role.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from datetime import datetime

import psutil

FIELDS = ["time", "pid", "role", "name", "working_set_mb", "private_mb"]


def role(name: str, cmdline: list[str]) -> str:
    args = [a.replace("\\", "/") for a in cmdline]
    if any(a.endswith("agent/main.py") for a in args):
        return "agent"
    if any(a.endswith("bot.py") for a in args) and "tasker" in args:
        return "tasker"
    if name.lower().startswith(("mxu", "mfaavalonia")):
        return "client"
    return "other"


def sample(root: psutil.Process, now: str) -> list[dict]:
    try:
        procs = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []
    rows = []
    for p in procs:
        try:
            with p.oneshot():
                m = p.memory_info()
                rows.append({"time": now, "pid": p.pid, "role": role(p.name(), p.cmdline()), "name": p.name(),
                             "working_set_mb": round(m.rss / 2**20, 1),
                             "private_mb": round(getattr(m, "private", getattr(m, "vms", 0)) / 2**20, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return rows


def summary(rows: list[dict]) -> list[str]:
    """Peak and last of the tree's sum and of each role's sum, over the samples."""
    totals: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in rows:
        for group in ("tree", r["role"]):
            pair = totals[group][r["time"]]
            pair[0] += float(r["working_set_mb"])
            pair[1] += float(r["private_mb"])
    lines = []
    for group in ["tree", *sorted(g for g in totals if g != "tree")]:
        series = totals[group]
        if not series:
            continue
        peak_ws = max(series.items(), key=lambda kv: kv[1][0])
        peak_pv = max(series.items(), key=lambda kv: kv[1][1])
        last = series[max(series)]
        lines.append(f"{group}: peak working set {peak_ws[1][0]:.1f} MB at {peak_ws[0]}, peak private {peak_pv[1][1]:.1f} MB "
                     f"at {peak_pv[0]}; last {max(series)}: working set {last[0]:.1f} MB, private {last[1]:.1f} MB")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--every", type=float, default=5, help="seconds between samples")
    a = ap.parse_args(argv)
    root = psutil.Process(a.pid)
    rows: list[dict] = []
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        while root.is_running() and root.status() != psutil.STATUS_ZOMBIE:
            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            got = sample(root, now)
            if not got:
                break
            w.writerows(got)
            f.flush()
            rows += got
            time.sleep(a.every)
    print("\n".join(summary(rows)) or "no sample")
    return 0


if __name__ == "__main__":
    sys.exit(main())
