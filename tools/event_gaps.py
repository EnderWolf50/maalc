"""How long a lit event button waits for its press after an option is taken or the text runs out (#557).

    uv run python tools/event_gaps.py install/debug/maafw.bak.*.log install/debug/maafw.log [--list]

Reads the taps the agent sent (game pixels) and the Event action's calls. Each press of the event button (1130,645) in
an Event call goes in one group, measured from:

- **option**: the option's tap (x 925, in an Event call), when it is the last tap other than the dead corner (5,5) and at
  most MAX_GAP s before; split by whether a recognition of `Connecting` hit in between (MirrorHub's or page_guard's);
- **corner**: else the corner tap just before it.

A press with the action handed back in between splits into **action** (the tap to the action's end), **hub** (to the
next Event call's start) and **next** (that start to the press); their medians are over the handed-back presses. Medians
and ranges in seconds, from the logs given oldest first; the table is markdown. Under it, the presses that came under
TAKE s after the press before (`--list` marks them `soon`): SKIP then Continue, or one button pressed twice, which only
the recording tells apart.
"""

from __future__ import annotations

import argparse
import re
import statistics
from dataclasses import dataclass
from datetime import datetime

from maafw_timeline import TS, stamp

CLICK = re.compile(r'handle_controller_post_click\] \[req=\{.*"x":(\d+),"y":(\d+)\}\].*\| enter')
START = re.compile(r"CustomAction::run\] \[context\.task_id\(\)=\d+\] \[node_name=Event\]")
END = re.compile(r"CustomAction::run\] \[node_name=Event\].*\[ret=")
CONNECTING = re.compile(r'Recognizer::recognize\] reco \[result=\{"algorithm":"\w+","box":\[.*"name":"Connecting"')
MAX_GAP = 10.0
# agent/actions.py's EVENT_NEUTRAL, EVENT_BUTTON, CHOICE_X and EVENT_TAKE (tests/test_event_gaps.py holds them equal).
CORNER, BUTTON, OPTION_X, TAKE = (5, 5), (1130, 645), 925, 1.5


def kind(x, y):
    if (x, y) == CORNER:
        return "corner"
    if (x, y) == BUTTON:
        return "button"
    return "option" if x == OPTION_X else "other"


@dataclass
class Log:
    taps: list  # [(time, kind, in an Event call)]
    starts: list
    ends: list
    connecting: list
    corners: list  # corner taps of each Event call


def read(lines):
    log, inside = Log([], [], [], [], []), False
    for line in lines:
        if not (t := TS.match(line)):
            continue
        at = stamp(t[1])
        if m := CLICK.search(line):
            k = kind(int(m[1]), int(m[2]))
            log.taps.append((at, k, inside))
            if inside and k == "corner":
                log.corners[-1] += 1
        elif START.search(line):
            log.starts.append(at)
            log.corners.append(0)
            inside = True
        elif END.search(line):
            log.ends.append(at)
            inside = False
        elif CONNECTING.search(line):
            log.connecting.append(at)
    return log


def presses(log):
    """[{group, at, total, connecting, action, hub, next}] of every button press in an Event call that a group takes."""
    found = []
    for i, (at, k, inside) in enumerate(log.taps):
        if k != "button" or not inside or i == 0:
            continue
        j = i - 1
        while j > 0 and log.taps[j][1] == "corner":
            j -= 1
        if log.taps[j][1] == "option" and log.taps[j][2] and at - log.taps[j][0] <= MAX_GAP:
            group, since = "option", log.taps[j][0]
        elif log.taps[i - 1][1] == "corner" and log.taps[i - 1][2] and at - log.taps[i - 1][0] <= MAX_GAP:
            group, since = "corner", log.taps[i - 1][0]
        else:
            continue
        ends = [e for e in log.ends if since < e < at]
        starts = [s for s in log.starts if since < s < at]
        row = {"group": group, "at": since, "total": at - since, "connecting": any(since < c < at for c in log.connecting),
               "action": None, "hub": None, "next": None}
        if ends and starts:
            row.update(action=ends[0] - since, hub=starts[-1] - ends[0], next=at - starts[-1])
        found.append(row)
    return found


def table(found, log):
    groups = [("option", lambda r: r["group"] == "option"),
              ("option, CONNECTING seen", lambda r: r["group"] == "option" and r["connecting"]),
              ("option, no CONNECTING", lambda r: r["group"] == "option" and not r["connecting"]),
              ("corner", lambda r: r["group"] == "corner")]
    rows = ["| press after | n | median s | range s | handed back | action s | hub s | next s |",
            "|---|---:|---:|---|---:|---:|---:|---:|"]
    for name, keep in groups:
        picked = [r for r in found if keep(r)]
        if not picked:
            continue
        totals = [r["total"] for r in picked]
        back = [r for r in picked if r["action"] is not None]

        def med(key):
            return f"{statistics.median(r[key] for r in back):.2f}" if back else "-"
        rows.append(f"| {name} | {len(picked)} | {statistics.median(totals):.2f} | {min(totals):.2f}-{max(totals):.2f} | "
                    f"{len(back)} | {med('action')} | {med('hub')} | {med('next')} |")
    rows.append("")
    rows.append(f"Event calls: {len(log.starts)}; most corner taps in one call: {max(log.corners, default=0)}")
    rows.append(f"presses under {TAKE} s after the press before: {len(soon(log))}")
    return "\n".join(rows)


def soon(log):
    """The times of the button presses that came under TAKE s after the press before."""
    pressed = [at for at, k, _ in log.taps if k == "button"]
    return [at for before, at in zip(pressed, pressed[1:]) if at - before < TAKE]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--list", action="store_true", help="also print each press")
    args = ap.parse_args(argv)
    lines = []
    for path in args.logs:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines += [line for line in f if "post_click] [req=" in line or "node_name=Event]" in line or '"name":"Connecting"' in line]
    log = read(lines)
    found = presses(log)
    print(table(found, log))
    if args.list:
        for r in found:
            split = "" if r["action"] is None else f" = action {r['action']:.3f} + hub {r['hub']:.3f} + next {r['next']:.3f}"
            print(f"{clock(r['at'])} {r['group']}{' CONNECTING' if r['connecting'] else ''} {r['total']:.3f}{split}")
        for at in soon(log):
            print(f"{clock(at)} soon")


def clock(at):
    return datetime.fromtimestamp(at).strftime("%H:%M:%S.%f")[:-3]


if __name__ == "__main__":
    main()
