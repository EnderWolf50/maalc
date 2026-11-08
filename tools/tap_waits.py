"""How soon the screen answered each tap a custom action made: a screen recording aligned with maafw.log (#258).

    uv run --group probe python tools/tap_waits.py VIDEO --started 2026-11-08T07:31:35.992 \\
        --log install/debug/maafw.bak.2026.11.08-08.37.11.105.log install/debug/maafw.log \\
        --node MirrorMap image/Map/MirrorMap.png 1195,65,75,130 0.8 [--node ...] \\
        --actions Wipe Settle Shop PickThemePack [--until next-tap] [--from ...] [--to ...] [-o taps.csv]

A **tap** is a `post_click` inside the `CustomAction::run` of one of `--actions` (the innermost action running). Its
**look** is the action's next controller call (screencap, click, swipe, touch) or the action's end: where the bot looked
again, so look minus tap is the wait (a `tap(wait=)` shows as its seconds and about 0.05 s). A wait that polls
(`tap_then`: a screenshot every 0.2 s until the page changes) then measures about 0.05 s every time; `--until next-tap`
skips the screenshots, so the look is the action's next controller call that is no screenshot (a click, swipe, touch,
key or shell command) or its end: where the bot went on, and `settled` is read against the screen it went on from
(#567). The video is aligned with the log as `tools/video_align.py` aligns it, with the same `--started`, `--node` and
fitting options. Every frame from 0.5 s before a tap to its look is scored with the bot's own `recovery.thumb` (32x18,
one block per 40x40 pixels):

- **moved**: the first frame after the tap with any block more than 8 levels off the last frame before it, the test of
  `actions.moved`: the game took the tap. Empty when no frame moved.
- **settled**: the start of the frames, up to the look, that each are `recovery.same_screen` as the frame at the look,
  the screen the bot then read. 0 when that screen was up before the tap.

Both in seconds after the tap. A tap the aligned video does not cover (no frame on both sides, a frame unaligned or
frozen) is left out of the table and counted. The table (markdown, medians and maxima per action, node and tap point)
goes to stdout; `-o` writes one CSV row per tap.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np

import video_align as va
from maafw_timeline import TS, stamp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import recovery  # noqa: E402

ENTER = re.compile(r"CustomAction::run\] \[context\.task_id\(\)=\d+\] \[node_name=(\w+)\].*\[param\.name=(\w+)\].*\| enter")
LEAVE = re.compile(r"CustomAction::run\] \[node_name=\w+\] \[param\.name=\w+\].*\[ret=")
CALL = re.compile(r"handle_controller_post_\w+\] \[req=")
UNTIL = {"next-call": CALL, "next-tap": re.compile(r"handle_controller_post_(?!screencap)\w+\] \[req=")}
CLICK = re.compile(r'handle_controller_post_click\] \[req=\{.*?"x":(\d+),"y":(\d+)')
BEFORE = 0.5  # s of video looked at before a tap
# s around a tap's frames kept while decoding, before the fit knows the offset: a chunk fitted further off has its taps
# outside what was kept, counted as not on the video, and warned of.
MARGIN = 3.0


class Tap(NamedTuple):
    at: float  # log time of the click
    action: str
    node: str
    x: int
    y: int
    look: float  # log time of the action's next controller call (--until next-tap: no screenshot), or of its end


def taps(lines, actions, until="next-call") -> list[Tap]:
    """Every click of `actions` in lines (maafw.log), with its look: the action's next call of UNTIL[until], or its end."""
    ends_wait, found, stack, open_tap = UNTIL[until], [], [], None
    for line in lines:
        if "CustomAction::run]" not in line and "handle_controller_post_" not in line:
            continue
        if not (m := TS.match(line)):
            continue
        t = stamp(m[1])
        if e := ENTER.search(line):
            stack.append((e[1], e[2]))
            continue
        ends = bool(LEAVE.search(line))
        if not ends and not (stack and ends_wait.search(line)):
            continue
        if open_tap is not None:
            found.append(open_tap._replace(look=t))
            open_tap = None
        if ends:
            if stack:
                stack.pop()
        elif (c := CLICK.search(line)) and stack[-1][1] in actions:
            open_tap = Tap(t, stack[-1][1], stack[-1][0], int(c[1]), int(c[2]), 0.0)
    return found


def measure(tap: Tap, lt, thumbs) -> tuple[float | None, float] | None:
    """(moved, settled) s after the tap from frames at log times lt with their thumbnails; None when the video does
    not show the tap: no frame on one side of it, or one of its frames has no log time (unaligned, frozen)."""
    sel = np.flatnonzero((lt >= tap.at - BEFORE) & (lt <= tap.look)) if len(lt) else np.array([], int)
    if not len(sel) or np.isnan(lt[sel[0]:sel[-1] + 1]).any():
        return None
    before, after = [i for i in sel if lt[i] <= tap.at], [i for i in sel if lt[i] > tap.at]
    if not before or not after:
        return None
    base, last = thumbs[before[-1]], thumbs[after[-1]]
    moved = next((lt[i] - tap.at for i in after if (np.abs(thumbs[i] - base) > 8).any()), None)
    differ = [k for k, i in enumerate(after) if not recovery.same_screen(thumbs[i], last)]
    if differ:
        settled = lt[after[differ[-1] + 1]] - tap.at
    else:  # every frame after the tap shows the look's screen: it came with the first, or was up before the tap
        settled = 0.0 if recovery.same_screen(base, last) else lt[after[0]] - tap.at
    return (None if moved is None else float(moved)), float(settled)


def table(rows) -> str:
    """Markdown: per action, node and tap point, the taps, the wait, moved and settled (median, max)."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["action"], r["node"], r["x"], r["y"])].append(r)
    out = ["| action | node | tap | taps | wait s | moved s (median, max) | settled s (median, max) | never moved |",
           "|---|---|---|---:|---:|---:|---:|---:|"]
    med = statistics.median
    for (action, node, x, y), rs in sorted(groups.items()):
        moved = [r["moved"] for r in rs if r["moved"] != ""]
        settled = [r["settled"] for r in rs]
        out.append(f"| {action} | {node} | {x},{y} | {len(rs)} | {med(r['wait'] for r in rs):.2f} | "
                   + (f"{med(moved):.2f}, {max(moved):.2f}" if moved else "-")
                   + f" | {med(settled):.2f}, {max(settled):.2f} | {len(rs) - len(moved)} |")
    return "\n".join(out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--started", required=True, help="wall time of the first frame, ISO (screen-record's `started`)")
    ap.add_argument("--log", nargs="+", type=Path, required=True)
    ap.add_argument("--node", nargs=4, action="append", required=True, metavar=("NAME", "TEMPLATE", "ROI", "THRESHOLD"))
    ap.add_argument("--actions", nargs="+", required=True)
    ap.add_argument("--until", choices=list(UNTIL), default="next-call",
                    help="where a tap's wait ends: the action's next controller call, or its next one that is no screenshot")
    ap.add_argument("--hub", default="MirrorHub")
    ap.add_argument("--from", dest="lo", help="log time, ISO")
    ap.add_argument("--to", dest="hi", help="log time, ISO")
    ap.add_argument("--fps", type=float, default=10.0, help="video frames scored a second for the fit")
    ap.add_argument("--chunk", type=float, default=60.0)
    ap.add_argument("--max-lost", type=float, default=7200.0)
    ap.add_argument("--min-corr", type=float, default=0.8)
    ap.add_argument("--drift", type=float, default=2.0)
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args(argv)
    nodes = {n: (va.RESOURCE / f if (va.RESOURCE / f).exists() else Path(f), tuple(map(int, roi.split(","))), float(th))
             for n, f, roi, th in a.node}
    lo, hi = stamp(a.lo) if a.lo else 0.0, stamp(a.hi) if a.hi else float("inf")

    def lines():
        for path in a.log:
            with open(path, encoding="utf-8", errors="replace") as f:
                yield from f

    found = [t for t in taps(lines(), set(a.actions), a.until) if lo <= t.at <= hi]
    _, _, bot = va.parse_log(lines(), list(nodes), a.hub)
    kt, kthumbs = [], []

    def on_frame(t, im):
        kt.append(t)
        kthumbs.append(recovery.thumb(im))
    windows = [(t.at - BEFORE - MARGIN, t.look + MARGIN) for t in found]
    vt, vs, still = va.video_scores(a.video, nodes, stamp(a.started), a.fps, windows, on_frame)
    frozen = va.freezes(vt, still, bot, blip=max(1.0, 3 / a.fps))
    segs = va.fit(vt, vs, bot, a.chunk, a.max_lost, a.min_corr, a.drift, frozen)
    for s in segs:
        print(f"video {va.clock(s.v0)}-{va.clock(s.v1)}  " + (f"offset {s.offset:+.3f} s" if s.offset is not None else "unaligned")
              + f"  corr {s.corr:.3f}", file=sys.stderr)
        if s.offset is not None and abs(s.offset) > MARGIN - BEFORE:
            print(f"warning: offset {s.offset:+.3f} s is past the {MARGIN:g} s kept around each tap: rerun with a --started "
                  "nearer the first frame", file=sys.stderr)
    lt = va.log_times(np.array(kt), segs, frozen)
    rows, missed = [], 0
    for t in found:
        got = measure(t, lt, kthumbs)
        if got is None:
            missed += 1
            continue
        moved, settled = got
        rows.append({"at": va.clock(t.at), "action": t.action, "node": t.node, "x": t.x, "y": t.y, "wait": round(t.look - t.at, 3),
                     "moved": "" if moved is None else round(moved, 3), "settled": round(settled, 3)})
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, ["at", "action", "node", "x", "y", "wait", "moved", "settled"])
            w.writeheader()
            w.writerows(rows)
    print(table(rows))
    print(f"\n{len(rows)} taps on the video, {missed} not (unaligned, frozen or outside it)")


if __name__ == "__main__":
    main()
