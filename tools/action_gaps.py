"""What each node's hits cost around its action: MaaFramework's pre_delay and post_delay, the action, the wait for the next hit (#258).

    uv run python tools/action_gaps.py install/debug/maafw.bak.*.log install/debug/maafw.log [--nodes Event MirrorMap]

Per hit of a screen (as tools/hit_gaps.py counts them): **pre** is the sleep between the hit and the action, **action**
the node's `CustomAction::run`, enter to leave, **post** the sleep after it, **to next** the time from the action's end
to the next screen's hit, **short** the actions under 1 s (one that handed back at once, e.g. still() found the screen
moving). Medians in seconds, from the first column's hits. Give the logs oldest first; the table is markdown.
"""

from __future__ import annotations

import argparse
import re
import statistics
from collections import Counter

from hit_gaps import HIT, NOT_SCREENS, SLEEP
from maafw_timeline import TS, stamp

ACTION = re.compile(r'msg=Node\.Action\.Starting\].*"name":"(\w+)"')
RAN = re.compile(r"CustomAction::run\] .*\[node_name=(\w+)\].*\[ret=")


def hits(lines):
    """[{name, at, pre, post, start, end}] of every screen hit in lines; start and end are None for a node with no custom action."""
    found, cur = [], None
    for line in lines:
        if not (t := TS.match(line)):
            continue
        if "reco hit [result.name=" in line:
            m = HIT.search(line)
            cur = None
            if m and m[1] not in NOT_SCREENS:
                cur = {"name": m[1], "at": stamp(t[1]), "pre": 0.0, "post": 0.0, "start": None, "end": None}
                found.append(cur)
        elif cur is None:
            continue
        elif "TaskBase::sleep] " in line:
            cur["post" if cur["end"] else "pre"] += int(SLEEP.search(line)[1]) / 1000
        elif (m := ACTION.search(line)) and m[1] == cur["name"] and cur["start"] is None:
            cur["start"] = stamp(t[1])
        elif cur["start"] and not cur["end"] and (m := RAN.search(line)) and m[1] == cur["name"]:
            cur["end"] = stamp(t[1])
    return found


def table(found, nodes=None):
    rows = ["| screen | hits | pre s | action s | post s | to next s | short | next screens |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    names = Counter(h["name"] for h in found)
    for name in nodes or [n for n, _ in names.most_common()]:
        pairs = [(h, found[i + 1] if i + 1 < len(found) else None) for i, h in enumerate(found) if h["name"] == name and h["end"]]
        if not pairs:
            continue
        med = statistics.median
        acts = [h["end"] - h["start"] for h, _ in pairs]
        nxt = [n["at"] - h["end"] for h, n in pairs if n and n["at"] - h["end"] < 30]
        follow = Counter(n["name"] for _, n in pairs if n)
        rows.append(f"| {name} | {len(pairs)} | {med(h['pre'] for h, _ in pairs):.2f} | {med(acts):.2f} | {med(h['post'] for h, _ in pairs):.2f} | "
                    f"{med(nxt) if nxt else float('nan'):.2f} | {sum(a < 1 for a in acts)} | " + ", ".join(f"{n} {c}" for n, c in follow.most_common(3)) + " |")
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--nodes", nargs="+")
    args = ap.parse_args(argv)
    found = []
    for path in args.logs:
        with open(path, encoding="utf-8", errors="replace") as f:
            found += hits(f)
    print(table(found, args.nodes))


if __name__ == "__main__":
    main()
