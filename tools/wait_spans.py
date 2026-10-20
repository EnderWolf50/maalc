"""How long MirrorHub saw a waiting screen, and how long the screen sat still in it, from maafw.log (#179).

    uv run python tools/wait_spans.py install/debug/maafw.bak.*.log install/debug/maafw.log [--kinds Loading Connecting]
        [--min 15]

A **pass** starts at each recognition of `Stuck`, MirrorHub's first node; its screen is the first node that hit after
it (not HubText, which only picks the OCR screens to check, #157), and its **scores** every score each node logged
in it, to 6 decimals. A **span** is a run of passes on one screen of `--kinds`. **Still** is the longest stretch of passes with the very same scores: a still game gives the same pixels
every time, so the bot's scores do not move either (live 2026-10-19, checked against the recording of the 105 s
Now Loading of #179). Scores cover only the rois the bot looks at, so still can run longer than the picture did.
Give the logs oldest first; spans under `--min` s are left out.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from maafw_timeline import TS

RESULT = re.compile(r"Recognizer::recognize\] reco \[result=(.*)\] $")


@dataclass
class Pass:
    time: datetime
    screen: str | None = None  # the first node that hit
    scores: dict = field(default_factory=dict)  # node -> every score it logged, to 6 decimals


def all_scores(x):
    """Every "score" in a recognition detail, depth first, to 6 decimals."""
    if isinstance(x, dict):
        own = [round(x["score"], 6)] if isinstance(x.get("score"), (int, float)) else []
        return own + [s for v in x.values() for s in all_scores(v)]
    if isinstance(x, list):
        return [s for v in x for s in all_scores(v)]
    return []


def passes(lines):
    """Every MirrorHub pass in lines, oldest first."""
    found = []
    for line in lines:
        if "Recognizer::recognize] reco [result=" not in line:
            continue
        if not (m := RESULT.search(line.rstrip("\n"))) or not (t := TS.match(line)):
            continue
        try:
            result = json.loads(m[1])
        except ValueError:
            continue
        name = result.get("name")
        if name == "Stuck":
            found.append(Pass(datetime.fromisoformat(t[1])))
        elif found:
            found[-1].scores.setdefault(name, all_scores(result.get("detail")))
            if result.get("box") and found[-1].screen is None and name not in ("NoBatchOCR", "HubText"):
                found[-1].screen = name
    return found


def spans(found, kinds):
    """[(start, screen, seconds, passes, still seconds)] for each run of passes on one screen of kinds."""
    runs, prev = [], None
    for p in found:
        if p.screen in kinds:
            if prev and prev.screen == p.screen:
                runs[-1].append(p)
            else:
                runs.append([p])
        prev = p
    out = []
    for run in runs:
        still, since = 0.0, run[0].time
        for a, b in zip(run, run[1:]):
            if a.scores != b.scores:
                since = b.time
            still = max(still, (b.time - since).total_seconds())
        out.append((run[0].time, run[0].screen, (run[-1].time - run[0].time).total_seconds(), len(run), still))
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
