"""Where a run's wall-clock time goes, from maafw.log: per pipeline node, step time, custom-action time and fixed waits.

    uv run python tools/maafw_timeline.py install/debug/debug/maafw.bak.*.log install/debug/debug/maafw.log
        [--range "2026-10-17 14:05:23" "2026-10-17 15:50:30"]...  [--window MirrorEntryNewRun ThemePack]

- A **step** is the time between two `Node.PipelineNode.Succeeded` events, counted for the later node: it holds
  the wait for the node to appear, its action and its `post_delay`.
- The **action** is the node's outermost `CustomAction::run`, enter to leave.
- A **fixed wait** is a gap over 0.2 s between two agent calls (OCR, template match, screencap, tap) inside the
  action: a `tap(..., wait=)` or a `time.sleep`.

Give the logs oldest first (rotated `maafw.bak.*` files, then `maafw.log`). Each `--range` is one run (local
time, as the log prints it); `--window START END` keeps only the steps from START to END of each run, once per
time START appears. The table is the mean per run (or per window), or with `--median` the median.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

TS = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\]")
DETAILS = re.compile(r"\[details=(\{.*\})\]\s*$")
NODE = re.compile(r"\[node_name=(\w+)\]")
FIXED_GAP = 0.2


def stamp(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


@dataclass
class Action:
    node: str
    start: float
    end: float = 0.0
    calls: list[float] = field(
        default_factory=list
    )  # every agent call's enter and leave time

    def fixed(self) -> float:
        points = [self.start, *self.calls, self.end]
        return sum(b - a for a, b in zip(points, points[1:]) if b - a > FIXED_GAP)


def parse(lines):
    """(succeeded: [(time, node)], actions: [Action]) from maafw.log lines, in order."""
    succeeded, actions, depth, current = [], [], 0, None
    for line in lines:
        m = TS.match(line)
        if not m:
            continue
        if "msg=Node.PipelineNode.Succeeded" in line:
            d = DETAILS.search(line)
            if d:  # the top-level name is the task's entry; node_details names the node that ran
                details = json.loads(d[1])
                node = (details.get("node_details") or {}).get("name") or details[
                    "name"
                ]
                succeeded.append((stamp(m[1]), node))
        elif "[CustomAction.cpp]" in line and "CustomAction::run]" in line:
            if "| leave" in line:
                depth = max(depth - 1, 0)
                if depth == 0 and current:
                    current.end = stamp(m[1])
                    actions.append(current)
                    current = None
            elif (
                "[context.task_id()=" in line
            ):  # the enter line; the [ret=...] line after the call is neither
                node = NODE.search(line)
                if depth == 0 and node:
                    current = Action(node[1], stamp(m[1]))
                depth += 1
        elif current and "[AgentClient.cpp]" in line and "::handle_" in line:
            current.calls.append(stamp(m[1]))
    return succeeded, actions


def steps(succeeded, actions):
    """[(node, start, end, action seconds, fixed seconds)]: one per Succeeded after the first."""
    out, i = [], 0
    for (start, _), (end, node) in zip(succeeded, succeeded[1:]):
        while i < len(actions) and actions[i].start < start:
            i += 1
        act = next((a for a in actions[i:] if a.start <= end and a.node == node), None)
        out.append(
            (
                node,
                start,
                end,
                act.end - act.start if act else 0.0,
                act.fixed() if act else 0.0,
            )
        )
    return out


def windows(all_steps, ranges, window):
    runs = (
        [[s for s in all_steps if a <= s[1] and s[2] <= b] for a, b in ranges]
        if ranges
        else [all_steps]
    )
    if not window:
        return runs
    first, last = window
    out = []
    for run in runs:
        cur = None
        for s in run:
            if s[0] == first:
                cur = []
            if cur is not None:
                cur.append(s)
                if s[0] == last:
                    out.append(cur)
                    cur = None
    return out


def table(groups, stat=statistics.mean) -> str:
    """Per node, the `stat` (mean or median) over the groups of its count and summed seconds in each group."""
    per = defaultdict(lambda: [[0, 0.0, 0.0, 0.0] for _ in groups])
    for i, g in enumerate(groups):
        for node, a, b, act, fixed in g:
            row = per[node][i]
            row[0] += 1
            row[1] += b - a
            row[2] += act
            row[3] += fixed
    total = stat(g[-1][2] - g[0][1] for g in groups) if groups else 0.0
    lines = [
        f"{len(groups)} run(s), {stat.__name__} {total:.1f} s ({total / 60:.1f} min)",
        f"{'node':24} {'n/run':>6} {'step s':>8} {'action s':>9} {'fixed s':>8}",
    ]
    rows = {
        node: [stat(r[k] for r in rs) for k in range(4)] for node, rs in per.items()
    }
    for node, (c, step, act, fixed) in sorted(rows.items(), key=lambda kv: -kv[1][1]):
        lines.append(f"{node:24} {c:6.2f} {step:8.2f} {act:9.2f} {fixed:8.2f}")
    return "\n".join(lines)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("logs", nargs="+", help="maafw.log files, oldest first")
    p.add_argument(
        "--range",
        nargs=2,
        action="append",
        metavar=("FROM", "TO"),
        help="one run, local time",
    )
    p.add_argument(
        "--window",
        nargs=2,
        metavar=("START", "END"),
        help="keep the steps from START to END",
    )
    p.add_argument(
        "--median", action="store_true", help="the median per run instead of the mean"
    )
    a = p.parse_args(argv)

    def lines():
        for path in a.logs:
            with open(path, encoding="utf-8", errors="replace") as f:
                yield from f

    succeeded, actions = parse(lines())
    ranges = [(stamp(x), stamp(y)) for x, y in a.range or []]
    groups = [g for g in windows(steps(succeeded, actions), ranges, a.window) if g]
    stat = statistics.median if a.median else statistics.mean
    print(table(groups, stat) if groups else "no steps in the given range or window")


if __name__ == "__main__":
    main()
