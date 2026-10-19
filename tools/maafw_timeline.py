"""Where a run's wall-clock time goes, from maafw.log: per pipeline node, step time, custom-action time and fixed waits.

    uv run python tools/maafw_timeline.py install/debug/debug/maafw.bak.*.log install/debug/debug/maafw.log
        [--range "2026-10-17 14:05:23" "2026-10-17 15:50:30"]...  [--window MirrorEntryNewRun ThemePack]

- A **step** is the time between two `Node.PipelineNode.Succeeded` events, counted for the later node: it holds
  the wait for the node to appear, its action and its `post_delay`.
- The **action** is the node's outermost `CustomAction::run`, enter to leave.
- A **fixed wait** is a gap over 0.2 s inside the action with no agent call (OCR, template match, screencap,
  tap) running: from the action's start or one call's leave to the next call's enter or the action's end. It is
  a `tap(..., wait=)` or a `time.sleep`; a slow call itself is not a wait.

Give the logs oldest first (rotated `maafw.bak.*` files, then `maafw.log`). Each `--range` is one run (local
time, as the log prints it); a step cut by a range edge is left out. `--window START END` keeps only the steps
from START to END of each run, once per time START appears; a window that does not reach END is left out. The
table is the mean per run (or per window), or with `--median` the median.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

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
    calls: list[tuple[float, float]] = field(default_factory=list)  # (enter, leave)

    def seconds(self) -> float:
        return self.end - self.start

    def fixed(self) -> float:
        idle = [(self.start, self.calls[0][0] if self.calls else self.end)]
        idle += [(a[1], b[0]) for a, b in zip(self.calls, self.calls[1:])]
        if self.calls:
            idle.append((self.calls[-1][1], self.end))
        return sum(b - a for a, b in idle if b - a > FIXED_GAP)


class Step(NamedTuple):
    node: str
    start: float
    end: float
    action: float  # seconds in the node's custom action
    fixed: float  # seconds of fixed wait inside it


def parse(lines):
    """(succeeded: [(time, node)], actions: [Action]) from maafw.log lines, in order."""
    succeeded, actions, depth, current, entered = [], [], 0, None, None
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
            ):  # the enter; the [ret=...] line after it is neither
                node = NODE.search(line)
                if depth == 0 and node:
                    current = Action(node[1], stamp(m[1]))
                depth += 1
        elif current and "[AgentClient.cpp]" in line and "::handle_" in line:
            if "| leave" in line:
                if entered is not None:
                    current.calls.append((entered, stamp(m[1])))
                entered = None
            elif "[req=" in line:
                entered = stamp(m[1])
    return succeeded, actions


def steps(succeeded, actions) -> list[Step]:
    """One Step per Succeeded after the first."""
    out, i = [], 0
    for (start, _), (end, node) in zip(succeeded, succeeded[1:]):
        while i < len(actions) and actions[i].start < start:
            i += 1
        act = next((a for a in actions[i:] if a.start <= end and a.node == node), None)
        out.append(
            Step(node, start, end, act.seconds(), act.fixed())
            if act
            else Step(node, start, end, 0.0, 0.0)
        )
    return out


def windows(all_steps: list[Step], ranges, window) -> list[list[Step]]:
    runs = (
        [[s for s in all_steps if a <= s.start and s.end <= b] for a, b in ranges]
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
            if s.node == first:
                cur = []
            if cur is not None:
                cur.append(s)
                if s.node == last:
                    out.append(cur)
                    cur = None
    return out


class Totals(NamedTuple):
    times: float
    step: float
    action: float
    fixed: float


def table(groups: list[list[Step]], stat=statistics.mean) -> str:
    """Per node, the `stat` (mean or median) over the groups of how often it ran and its summed seconds in each group."""
    per: dict[str, list[Totals]] = defaultdict(
        lambda: [Totals(0, 0.0, 0.0, 0.0)] * len(groups)
    )
    for i, g in enumerate(groups):
        for s in g:
            t = per[s.node][i]
            per[s.node][i] = Totals(
                t.times + 1,
                t.step + s.end - s.start,
                t.action + s.action,
                t.fixed + s.fixed,
            )
    total = stat(g[-1].end - g[0].start for g in groups) if groups else 0.0
    lines = [
        f"{len(groups)} run(s), {stat.__name__} {total:.1f} s ({total / 60:.1f} min)",
        f"{'node':24} {'n/run':>6} {'step s':>8} {'action s':>9} {'fixed s':>8}",
    ]
    rows = {
        node: Totals(*(stat(getattr(t, f) for t in ts) for f in Totals._fields))
        for node, ts in per.items()
    }
    for node, r in sorted(rows.items(), key=lambda kv: -kv[1].step):
        # a node that ran in fewer than half the runs has a median of 0 times
        if r.times:
            lines.append(
                f"{node:24} {r.times:6.2f} {r.step:8.2f} {r.action:9.2f} {r.fixed:8.2f}"
            )
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
