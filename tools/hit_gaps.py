"""How long the hub sits on each screen: hits, MaaFramework's own sleeps per hit, and the time to the next screen (#254).

    uv run python tools/hit_gaps.py install/debug/maafw.bak.*.log install/debug/maafw.log [--nodes Victory RunVictory]

A **hit** is `recognize_list] reco hit [result.name=X]`, the hub finding screen X (HubText, Stuck and the battle HUD
gate are not screens). **Fixed** is the `TaskBase::sleep] N ms` lines between a hit and the next one: the node's
pre_delay and post_delay (200 ms each unless the node sets them), and any delay its own action sleeps through the
framework. A **span** is a run of hits on one screen; **first -> next** goes from its first hit to the first hit on
another screen, **last -> next** from its last. Give the logs oldest first; the table is markdown.
"""

from __future__ import annotations

import argparse
import re
import statistics
from collections import Counter

from maafw_timeline import TS, stamp

HIT = re.compile(r"recognize_list\] reco hit \[result\.name=(\w+)\]")
SLEEP = re.compile(r"TaskBase::sleep\] (\d+)ms")
NOT_SCREENS = {"HubText", "HubTextLost", "Stuck", "BattleHUD", "BattleHUDLost", "NoBatchOCR"}


def events(lines):
    """[(time, name, sleeps)] of every screen hit in lines, oldest first; sleeps is the seconds slept after it."""
    found = []
    for line in lines:
        if "reco hit [result.name=" in line:
            if (m := HIT.search(line)) and (t := TS.match(line)) and m[1] not in NOT_SCREENS:
                found.append([stamp(t[1]), m[1], 0.0])
        elif "TaskBase::sleep] " in line and found and (m := SLEEP.search(line)):
            found[-1][2] += int(m[1]) / 1000
    return found


def spans(found):
    """[(name, hits, first -> next s, last -> next s)] for each run of hits on one screen that another screen follows."""
    out, i = [], 0
    while i < len(found):
        j = i
        while j + 1 < len(found) and found[j + 1][1] == found[i][1]:
            j += 1
        if j + 1 < len(found):
            out.append((found[i][1], j - i + 1, found[j + 1][0] - found[i][0], found[j + 1][0] - found[j][0]))
        i = j + 1
    return out


def p90(xs):
    return sorted(xs)[max(round(0.9 * len(xs)) - 1, 0)]


def table(found, nodes=None):
    """Markdown rows: screen, hits, fixed s per hit, spans, first -> next median and p90, last -> next median, next screens."""
    rows = ["| screen | hits | fixed s/hit | spans | first -> next s (median, p90) | last -> next s | next screens |", "|---|---:|---:|---:|---:|---:|---|"]
    after = {}
    for name, _, first, last in spans(found):
        after.setdefault(name, []).append((first, last))
    names = Counter(n for _, n, _ in found)
    for name in nodes or [n for n, _ in names.most_common()]:
        if name not in names:
            continue
        fixed = statistics.median(s for _, n, s in found if n == name)
        got = after.get(name, [])
        nxt = Counter(found[k + 1][1] for k in range(len(found) - 1) if found[k][1] == name and found[k + 1][1] != name)
        first = f"{statistics.median(f for f, _ in got):.2f}, {p90([f for f, _ in got]):.2f}" if got else "-"
        last = f"{statistics.median(l for _, l in got):.2f}" if got else "-"
        rows.append(f"| {name} | {names[name]} | {fixed:.1f} | {len(got)} | {first} | {last} | "
                    + ", ".join(f"{n} {c}" for n, c in nxt.most_common(3)) + " |")
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--nodes", nargs="+")
    args = ap.parse_args(argv)
    found = []
    for path in args.logs:
        with open(path, encoding="utf-8", errors="replace") as f:
            found += events(f)
    print(table(found, args.nodes))


if __name__ == "__main__":
    main()
