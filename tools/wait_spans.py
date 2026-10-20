"""How long MirrorHub saw a waiting screen, and how long the screen sat still in it, from maafw.log (#179).

    uv run python tools/wait_spans.py install/debug/maafw.bak.*.log install/debug/maafw.log [--kinds Loading Connecting]
        [--min 15]

A **pass** starts at each recognition of `Stuck`, MirrorHub's first node; its screen is the first node that hit after
it, and its **scores** every score each node logged in it, to 6 decimals. A **span** is a run of passes on one screen
of `--kinds`. **Still** is the longest stretch of passes with the very same scores: a still game gives the same pixels
every time, so the bot's scores do not move either (live 2026-10-19, checked against the recording of the 105 s
Now Loading of #179). Scores cover only the rois the bot looks at, so still can run longer than the picture did.
Give the logs oldest first; spans under `--min` s are left out.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime

LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\].*Recognizer::recognize\] reco \[result=(.*)\] $")


def scores(x, out):
    if isinstance(x, dict):
        if isinstance(x.get("score"), (int, float)):
            out.append(round(x["score"], 6))
        for v in x.values():
            scores(v, out)
    elif isinstance(x, list):
        for v in x:
            scores(v, out)
    return out


def passes(lines):
    """[(time, screen or None, {node: scores})] for every MirrorHub pass in lines."""
    found = []
    for line in lines:
        if "Recognizer::recognize] reco [result=" not in line or not (m := LINE.match(line.rstrip("\n"))):
            continue
        try:
            result = json.loads(m[2])
        except ValueError:
            continue
        name = result.get("name")
        if name == "Stuck":
            found.append([datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S.%f"), None, {}])
        elif found:
            found[-1][2].setdefault(name, scores(result.get("detail"), []))
            if result.get("box") and found[-1][1] is None and name != "NoBatchOCR":
                found[-1][1] = name
    return found


def spans(found, kinds):
    """[(start, screen, seconds, passes, still seconds)] for each run of passes on one screen of kinds."""
    runs, prev = [], None
    for p in found:
        if p[1] in kinds:
            if prev and prev[1] == p[1]:
                runs[-1].append(p)
            else:
                runs.append([p])
        prev = p
    out = []
    for run in runs:
        still, since = 0.0, run[0][0]
        for a, b in zip(run, run[1:]):
            if a[2] != b[2]:
                since = b[0]
            still = max(still, (b[0] - since).total_seconds())
        out.append((run[0][0], run[0][1], (run[-1][0] - run[0][0]).total_seconds(), len(run), still))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--kinds", nargs="+", default=["Loading", "Connecting"])
    ap.add_argument("--min", type=float, default=15)
    args = ap.parse_args(argv)
    found = []
    for path in args.logs:
        with open(path, encoding="utf-8", errors="replace") as f:
            found += passes(f)
    for start, kind, seconds, n, still in spans(found, set(args.kinds)):
        if seconds >= args.min:
            print(f"{start:%Y-%m-%d %H:%M:%S}  {kind:<10} {seconds:6.1f} s  {n:4} passes  still {still:5.1f} s")


if __name__ == "__main__":
    main()
