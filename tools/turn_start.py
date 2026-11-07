"""Each battle turn from the hub seeing it to the bot's first touch, and what came before it, from MaaFramework debug logs (#177).

    uv run python tools/turn_start.py install/debug/debug/maafw.bak.*.log install/debug/debug/maafw.log

A **turn** is one `CustomAction::run ... [param.name=PlayTurn] | enter`, **seen** at the hub's
`recognize_list] reco hit [result.name=BattleTurn]` just before it. Its segments, in ms:

1. seen to the PlayTurn enter: BattleTurn's pre_delay.
2. the enter to PlayTurn's first agent run_recognition of `"entry":"ReadText"`: still(). `caps` counts the
   `handle_controller_post_screencap` calls in it.
3. that ReadText, enter to leave: the turn number OCR. `turn` is what it read, `again` that it is the number of the
   battle's turn before (a second submit of the same turn).
4. its leave to the first touch PlayTurn sends: `handle_controller_post_click`, `post_touch_down` or `post_swipe`.
   `tap` says where that touch landed: `Win Rate` inside the BattleTurn hit box, `other` elsewhere (a guard turn's
   first portrait).

`total` is seen to that touch. What came before the hit, to tell whether BattlePause was seen after the previous action:

- `before`: the custom action that ran last before the hit, by its custom action name (`PlayTurn`: the previous turn's
  own hold ended; `HoldTurn`: the hub saw BattlePause and held again), `-` at the start of a log. `gap`: s from its
  end to the hit.
- `pause_age`: s from the last BattlePause hit to the hit: the hub's `reco hit [result.name=BattlePause]` or an agent
  run_recognition of BattlePause that hit (hold_turn's looks, press_start's).
- `turn_age`: s from the last agent run_recognition of BattleTurn that hit during a hold (hold_turn returning on it)
  to the hit. A hold runs from a `post_touch_down` at (1, 1) (agent/actions.py HOLD_SPOT) to the next
  `post_touch_up`.

Both ages count only looks since the previous turn's first touch, the battle's last Loading hit or the log's start,
whichever is last; `-` when there was none.

An agent run_recognition is the lines from `AgentClient::handle_context_run_recognition] [req={..."entry":"X"...}] |
enter` to its `| leave, N ms`; it hit when the `msg=Node.RecognitionNode.Succeeded` event between them names X, and
missed on `msg=Node.RecognitionNode.Failed`. The hub's own looks are not agent calls: a hub hit is its `reco hit` line.

A battle starts at a log's first turn and at the first turn after a hub hit of Loading (an event inside a Luxcavation
battle shows none). A turn whose PlayTurn ended before its ReadText or its first touch, or whose log ends first, is
left out and counted. Give the logs oldest first: lines of a log stamped no later than the end of the one before it
are skipped (a rotated log can repeat them). The tables are markdown; ages and gaps are in s, segments in ms.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from hit_gaps import HIT
from maafw_timeline import DETAILS, TS, stamp

PARAM = re.compile(r"\[param\.name=(\w+)\]")
RECT = re.compile(r"\[rect=\[(-?\d+),(-?\d+),(\d+),(\d+)\]\]")
HANDLER = re.compile(r"AgentClient::handle_(\w+)\]")
ENTRY = re.compile(r'"entry":"(\w+)"')
XY = re.compile(r'"x":(-?\d+),"y":(-?\d+)')
NAME = re.compile(r'"name":"(\w+)"')
TOUCHES = {"controller_post_click": "click", "controller_post_touch_down": "down", "controller_post_swipe": "swipe"}
HOLD_SPOT = (1, 1)  # a copy of agent/actions.py's: this tool reads logs, not the agent


class Hit(NamedTuple):
    t: float
    name: str


class Enter(NamedTuple):
    t: float
    name: str
    box: tuple[int, int, int, int] | None


class Leave(NamedTuple):
    t: float


class Look(NamedTuple):
    t: float
    end: float
    entry: str
    hit: bool
    text: str


class Cap(NamedTuple):
    t: float


class Touch(NamedTuple):
    t: float
    kind: str
    x: int
    y: int


class Up(NamedTuple):
    t: float


def events(lines):
    """The log lines this tool reads, as Hit, Enter and Leave (top-level custom actions), Look, Cap, Touch and Up."""
    depth, look = 0, None
    for line in lines:
        if "AgentClient::handle_" in line:
            if not (t := TS.match(line)) or not (h := HANDLER.search(line)):
                continue
            name, at = h[1], stamp(t[1])
            if name == "context_run_recognition":
                if "[req=" in line:
                    look = {"t": at, "entry": e[1] if (e := ENTRY.search(line)) else "", "hit": False, "text": ""}
                elif "| leave" in line and look:
                    yield Look(look["t"], at, look["entry"], look["hit"], look["text"])
                    look = None
            elif "[req=" not in line:
                continue
            elif name == "controller_post_screencap":
                yield Cap(at)
            elif name in TOUCHES:
                xy = XY.search(line)
                yield Touch(at, TOUCHES[name], *(map(int, xy.groups()) if xy else (-1, -1)))
            elif name == "controller_post_touch_up":
                yield Up(at)
        elif "msg=Node.RecognitionNode." in line and look:
            if (d := DETAILS.search(line)) and (n := NAME.search(d[1])) and n[1] == look["entry"]:
                look["hit"] = "RecognitionNode.Succeeded" in line
                if look["entry"] == "ReadText":  # text() joins every result, as agent/actions.py ocr() does
                    found = json.loads(d[1]).get("reco_details") or {}
                    look["text"] = " ".join(r.get("text", "") for r in (found.get("detail") or {}).get("all") or [])
        elif "reco hit [result.name=" in line:
            if (m := HIT.search(line)) and (t := TS.match(line)):
                yield Hit(stamp(t[1]), m[1])
        elif "CustomAction::run]" in line and "[CustomAction.cpp]" in line and (t := TS.match(line)):
            if "| leave" in line:
                depth = max(depth - 1, 0)
                if depth == 0:
                    yield Leave(stamp(t[1]))
            elif "[context.task_id()=" in line:  # the enter; the [ret=...] line after it is neither
                if depth == 0 and (p := PARAM.search(line)):
                    r = RECT.search(line)
                    yield Enter(stamp(t[1]), p[1], tuple(map(int, r.groups())) if r else None)
                depth += 1


@dataclass
class Turn:
    seen: float
    enter: float
    box: tuple[int, int, int, int] | None
    battle: float  # its first turn's seen
    before: str = "-"
    gap: float | None = None
    pause_age: float | None = None
    turn_age: float | None = None
    caps: int = 0
    read: float | None = None
    read_end: float | None = None
    number: str | None = None
    touch: float | None = None
    win_rate: bool = False
    again: bool = False

    def segments(self):
        """(total, 1, 2, 3, 4) in ms, unrounded: a median of an even count is then rounded as #177's comment was."""
        return tuple(1000 * (b - a) for a, b in (
            (self.seen, self.touch), (self.seen, self.enter), (self.enter, self.read),
            (self.read, self.read_end), (self.read_end, self.touch)))


def after(lines, last):
    """lines from the first one stamped later than last["stamp"] (a timestamp's text), which becomes the last line's
    stamp; last["skipped"] counts the lines left out."""
    fresh = not last["stamp"]
    for line in lines:
        if t := TS.match(line):
            if not fresh and t[1] <= last["stamp"]:
                last["skipped"] += 1
                continue
            fresh = True
            last["stamp"] = t[1]
        if fresh:
            yield line


def turns(logs):
    """(the complete turns, Counter of the turns left out by reason, the lines skipped per log) of logs, each an
    iterable of lines, oldest first."""
    done, out, last, skipped = [], Counter(), {"stamp": ""}, []
    for lines in logs:
        hit = action = prior = cur = prev = battle = None
        pause = turn_seen = mark = float("-inf")
        holding, loading = False, True
        last["skipped"] = 0
        for ev in events(after(lines, last)):
            match ev:
                case Hit(t, name):
                    hit = ev
                    if name == "BattlePause":
                        pause = t
                    elif name == "Loading":
                        loading, mark = True, t
                case Enter(t, name, box):
                    action = name
                    if name != "PlayTurn":
                        continue
                    if not hit or hit.name != "BattleTurn":
                        out["no BattleTurn hit before it"] += 1
                        continue
                    if loading:
                        battle, prev, loading = hit.t, None, False
                    cur = Turn(hit.t, t, box, battle)
                    if prior:
                        cur.before, cur.gap = prior[0], hit.t - prior[1]
                    cur.pause_age = hit.t - pause if pause > mark else None
                    cur.turn_age = hit.t - turn_seen if turn_seen > mark else None
                case Look(t, end, entry, found, text):
                    if entry == "BattlePause" and found:
                        pause = t
                    elif entry == "BattleTurn" and found and holding:
                        turn_seen = t
                    elif entry == "ReadText" and cur and cur.read is None:
                        cur.read, cur.read_end, cur.number = t, end, text.strip() or None
                case Cap(t):
                    if cur and cur.read is None:
                        cur.caps += 1
                case Touch(t, kind, x, y):
                    if kind == "down" and (x, y) == HOLD_SPOT:
                        holding = True
                    if cur and cur.touch is None:
                        cur.touch, mark = t, t
                        bx, by, bw, bh = cur.box or (0, 0, -1, -1)
                        cur.win_rate = bx <= x <= bx + bw and by <= y <= by + bh
                case Up(t):
                    holding = False
                case Leave(t):
                    if action:
                        prior, action = (action, t), None
                    if cur:
                        if cur.read is None or cur.touch is None:
                            out["PlayTurn ended before its ReadText or touch"] += 1
                        else:
                            cur.again = bool(prev and cur.number and prev.number == cur.number)
                            done.append(cur)
                            prev = cur
                        cur = None
        if cur:
            out["log ended in it"] += 1
        skipped.append(last["skipped"])
    return done, out, skipped


SEGMENTS = "| total | 1 | 2 | 3 | 4 |"


def when(t):
    return datetime.fromtimestamp(t).strftime("%m-%d %H:%M:%S.%f")[:-3]


def secs(x):
    return "-" if x is None else f"{x:.2f}"


def p90(xs):
    """Interpolated between the values around it, as #177's comment's p90s were (hit_gaps.p90 takes one value)."""
    return statistics.quantiles(xs, n=10, method="inclusive")[-1] if len(xs) > 1 else xs[0]


def spread(xs):
    """n: min / median / p90 / max, in s; - for none."""
    xs = [x for x in xs if x is not None]
    return f"{len(xs)}: {min(xs):.2f} / {statistics.median(xs):.2f} / {p90(xs):.2f} / {max(xs):.2f}" if xs else "-"


def cap_counts(found):
    return ", ".join(f"{n}: {c}" for n, c in sorted(Counter(t.caps for t in found).items()))


def medians(found, with_p90=False):
    cols = zip(*(t.segments() for t in found))
    return " | ".join(f"{statistics.median(c):.0f}" + (f" ({p90(c):.0f})" if with_p90 else "") for c in map(list, cols))


def rows(found):
    """One markdown row per turn."""
    out = ["| seen | turn | again | before | gap s | pause_age s | turn_age s | caps | tap " + SEGMENTS,
           "|---|---:|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"]
    for t in found:
        out.append(f"| {when(t.seen)} | {t.number or '-'} | {'again' if t.again else ''} | {t.before} | {secs(t.gap)} | "
                   f"{secs(t.pause_age)} | {secs(t.turn_age)} | {t.caps} | {'Win Rate' if t.win_rate else 'other'} | "
                   + " | ".join(f"{x:.0f}" for x in t.segments()) + " |")
    return out


def summary(found, title, key):
    """Per class of key(turn): turns, segment medians in ms, still() screenshots, repeats, the ages and the gap."""
    out = [f"| {title} | turns " + SEGMENTS + " caps: turns | again | pause_age s (n: min / median / p90 / max) | "
           "turn_age s (n: min / median / p90 / max) | gap s (median) |", "|---|---:" + "|---:" * 5 + "|---|---:|---|---|---:|"]
    groups = {}
    for t in found:
        groups.setdefault(key(t), []).append(t)
    for name, ts in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        gaps = [t.gap for t in ts if t.gap is not None]
        out.append(f"| {name} | {len(ts)} | {medians(ts)} | {cap_counts(ts)} | {sum(t.again for t in ts)} | "
                   f"{spread(t.pause_age for t in ts)} | {spread(t.turn_age for t in ts)} | "
                   f"{secs(statistics.median(gaps)) if gaps else '-'} |")
    return out


def battles(found):
    """Per battle: its first turn's seen, turns, Win Rate taps, segment medians in ms."""
    out = ["| battle | turns | Win Rate | " + SEGMENTS[2:], "|---|---:|---:" + "|---:" * 5 + "|"]
    groups = {}
    for t in found:
        groups.setdefault(t.battle, []).append(t)
    for start, ts in groups.items():
        out.append(f"| {when(start)[:-4]} | {len(ts)} | {sum(t.win_rate for t in ts)} | {medians(ts)} |")
    return out


def report(found, left, skipped):
    """The markdown the tool prints."""
    head = (f"{len(found)} turns; left out: " + (", ".join(f"{why} {n}" for why, n in left.items()) or "none")
            + "".join(f"; log {i} skipped {n} lines stamped before the log before it ended" for i, n in enumerate(skipped, 1) if n))
    if not found:
        return head
    out = [head, "",
           "Median (p90) ms:", "", "| turns " + SEGMENTS + " caps: turns | again |", "|---:" * 6 + "|---|---:|",
           f"| {len(found)} | {medians(found, with_p90=True)} | {cap_counts(found)} | {sum(t.again for t in found)} |", ""]
    out += summary(found, "before", lambda t: t.before) + [""]
    out += summary(found, "pause_age", lambda t: "set" if t.pause_age is not None else "unset") + [""]
    out += summary(found, "tap", lambda t: "Win Rate" if t.win_rate else "other") + [""]
    out += battles(found) + [""]
    return "\n".join(out + rows(found))


def lines_of(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        yield from f


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="+", help="maafw.log files, oldest first")
    args = ap.parse_args(argv)
    print(report(*turns(lines_of(p) for p in args.logs)))


if __name__ == "__main__":
    main()
