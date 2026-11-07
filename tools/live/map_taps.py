"""Every touch on the Mirror Dungeon map in a live run: whether the game took it, and how long after the map faded in.

    uv run --group probe python tools/live/map_taps.py LOG --video V@START... -o taps.csv [--offset S]
        [--fade-window S] [--from T --to T]

LOG is the bot's run.log (`tools/live/bot.py run`'s, a wall time per line, as `evidence.py` reads it); `--video
PATH@START` is the recording and the wall time of its first frame (screen-record's `started`), one per piece. Times
are wall clock, `HH:MM:SS[.fff]`, of the log's day.

**The touches.** The controller's `x: X, y: Y, width: W, height: H` lines, in device pixels (shown in the game's
1280x720); a burst of points under 0.25 s and 150 px apart is one touch (a drag), as `evidence.py events` joins them.
Which touches are on the map, and of what kind, comes from the `[maalc] map:` line after them (`RouteMap` in
agent/actions.py):

  follow      the tap before `follow plan`, `planned ... took no tap`, `... moved the map but showed no panel` or
              `no answer to the tap ...; tapping again`
  take        a full read's tap on a slot or the bus: before `map: take ...` or `no node took a tap`; a tap that a
              later one of the same read followed is its `next try`
  find_bus    the drags just before a follow tap or a map read (`node at`, `column 1`, `planned ... not linked`, ...),
              each starting under 2.5 s after the touch before it ended
  read_on     a drag before `dragged the map N px` (or `a drag moved the map ...`)
  drag_back   the drags after the read and before `map: path` (read_on's drags back, and find_bus after them)
  search_bus  a drag before `the bus showed after dragging the map`
  unzoom      the tap after `zoomed in on the bus`

The outcome is that next line, shortened (`follow plan`, `tapping again`, `took no tap`, `no panel`, `map: take`,
`next try`, `read`, `dragged`, `path`, ...).

**The screen.** A touch reaches the screen OFFSET s after its log line (`--offset`, else measured: the median, over
the map's drags that moved it, of the time from the drag's first move after the threshold rest, the first point the map
follows, to the first frame that left the screen of 0.5 s before; the summary prints it, with how many drags and their
quartiles). Taken or ignored is the production judge, `recovery.same_screen` on `recovery.thumb` (3% of the 40x40
blocks moved by more than 8 levels), between the frame PRE s before the touch reached the screen and every frame up
to ANSWER s after it, or up to the next touch reaching the screen when that comes sooner: `taken` with the first frame
that left the screen (`answer_s`, from the touch reaching the screen), `ignored` when none did. `share` is the
largest share of blocks moved in that window. `frozen`: every frame in it is the frame before it, pixel for pixel
(the recorder repeated its last frame), so the screen is not known; `no video` outside the recording.

**The fade.** `since_fade_s` is the time from the last near-black frame (whole-frame mean grey under 8) within
`--fade-window` s before the touch reached the screen, `none in N s` when there is none; `first_after_fade` says no
touch at all (on the map or not) came between that frame and this one. Frames are read at 30 fps, 1280x720, with
ffmpeg, as `evidence.py` reads them.

Writes one CSV row per map touch and prints a summary: the offset used, then per kind and verdict the touches, those
that were the first after a fade, and their range of seconds since it.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "tools", REPO / "agent"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import recovery  # noqa: E402
from live.evidence import TOUCH, Footage, hms, read_log, secs  # noqa: E402

FPS = 30
PRE = 0.2  # s before the touch reaches the screen: the frame the screen is judged against
ANSWER = 2.0  # s a touch has to answer; #473: taken taps answered within 0.23 s, ignored ones not in 2 s
BLACK = 8  # whole-frame mean grey under this is black: the map fades in from it
FADE_WINDOW = 10.0  # s before a touch the fade is looked for
CHAIN = 2.5  # s from a touch's last point to the next touch, at most, for find_bus's drags to be one chain
DWELL = 0.05  # s: a gap this long inside a drag is scroll()'s rest after the threshold move
REACH = 0.5  # s before a drag's first move: the frame its latency is measured against

FOLLOW_END = re.compile(r"map: (follow plan|planned .* (took no tap|moved the map but showed no panel)|no answer to the tap at)")
TAKE_END = re.compile(r"map: (take |no node took a tap)")
READ = re.compile(r"map: (node at|Cost miss|column 1:|the bus stayed|left the shop|planned .* (not linked|reads))")
OUTCOMES = [
    (r"map: follow plan", "follow plan"), (r"map: no answer to the tap", "tapping again"),
    (r"map: planned .* took no tap", "took no tap"), (r"map: planned .* moved the map but", "no panel"),
    (r"map: planned .* not linked", "not linked"), (r"map: planned .* reads", "misread"), (r"map: take ", "map: take"),
    (r"map: no node took a tap", "no node took a tap"), (r"map: (dragged the map|a drag moved)", "dragged"),
    (r"map: (path|the path steps)", "path"), (r"map: the bus showed", "bus showed"), (r"map: ", "read"),
]
DRAGS = ("find_bus", "read_on", "drag_back", "search_bus")


@dataclass
class Stroke:
    """One touch: its first point (wall s, game px), its last point's time, when it first moved after the threshold
    rest (a drag), and its point count."""
    t: float
    x: int
    y: int
    end: float
    moves_at: float
    n: int

    @property
    def drag(self) -> bool:
        return self.n > 1


@dataclass
class Touch:
    t: float
    x: int
    y: int
    kind: str
    outcome: str
    drag: bool
    moves_at: float


@dataclass
class Row(Touch):
    verdict: str  # taken, ignored, frozen, no video
    share: float | None
    answer: float | None  # s from the touch reaching the screen to the first frame that left it
    since_fade: float | None
    first_after_fade: bool


@dataclass
class Offset:
    value: float
    n: int  # drags measured
    lo: float  # their quartiles
    hi: float


def strokes(log) -> list[Stroke]:
    """The touches of the log's controller lines: points under 0.25 s and 150 px apart are one (evidence.touches)."""
    pts = []
    for t, text in log:
        if m := TOUCH.match(text):
            k = 1280 / int(m[3])
            pts.append((t, round(int(m[1]) * k), round(int(m[2]) * k)))
    out, i = [], 0
    while i < len(pts):
        j = i
        while j + 1 < len(pts) and pts[j + 1][0] - pts[j][0] < 0.25 and abs(pts[j + 1][1] - pts[j][1]) + abs(pts[j + 1][2] - pts[j][2]) < 150:
            j += 1
        burst = pts[i:j + 1]
        moves = next((b[0] for a, b in zip(burst, burst[1:]) if b[0] - a[0] > DWELL), burst[0][0])
        out.append(Stroke(burst[0][0], burst[0][1], burst[0][2], burst[-1][0], moves, len(burst)))
        i = j + 1
    return out


def outcome(line: str) -> str:
    return next(label for pattern, label in OUTCOMES if re.match(pattern, line)) if line.startswith("map: ") else line[:40]


def chain(group: list[Stroke]) -> list[Stroke]:
    """The trailing touches of group, each starting under CHAIN s after the one before it ended."""
    k = len(group) - 1
    while k > 0 and group[k].t - group[k - 1].end < CHAIN:
        k -= 1
    return group[k:]


def trailing_drags(group: list[Stroke]) -> list[Stroke]:
    out = []
    for s in reversed(chain(group)):
        if not s.drag:
            break
        out.append(s)
    return out[::-1]


def map_touches(log) -> list[Touch]:
    """The touches on the map, each with its kind and outcome from the `[maalc]` lines around it (module doc)."""
    msgs = [(t, x[8:]) for t, x in log if x.startswith("[maalc] ")]
    stamps = [t for t, _ in msgs]
    groups: dict[int, list[Stroke]] = {}
    for s in strokes(log):
        groups.setdefault(bisect.bisect_right(stamps, s.end), []).append(s)
    out = []
    for i, group in sorted(groups.items()):
        nxt = msgs[i][1] if i < len(msgs) else ""
        prev = msgs[i - 1][1] if i else ""
        if re.match(r"floor \d+: pull", prev) and group[0].drag:
            group = group[1:]  # the theme pack's own drag, before the new floor's map
            if not group:
                continue
        add = lambda s, kind, how=outcome(nxt): out.append(Touch(s.t, s.x, s.y, kind, how, s.drag, s.moves_at))  # noqa: E731
        if prev.startswith("map: zoomed in on the bus") and not group[0].drag:
            add(group[0], "unzoom")
        elif FOLLOW_END.match(nxt) and not group[-1].drag:
            for s in trailing_drags(group[:-1]):
                add(s, "find_bus")
            add(group[-1], "follow")
        elif TAKE_END.match(nxt):
            taps = [s for s in (group if prev.startswith("map: ") else chain(group)) if not s.drag]
            for k, s in enumerate(taps):
                add(s, "take", "map: take" if k == len(taps) - 1 or not nxt.startswith("map: take") else "next try")
        elif re.match(r"map: (dragged the map|a drag moved)", nxt):
            for s in trailing_drags(group):
                add(s, "read_on")
        elif re.match(r"map: (path|the path steps)", nxt) and prev.startswith("map: "):
            for s in trailing_drags(group):
                add(s, "drag_back")
        elif nxt.startswith("map: the bus showed after dragging"):
            for s in trailing_drags(group):
                add(s, "search_bus")
        elif READ.match(nxt):
            if nxt.startswith("map: column 1: no linked slot read") and not group[-1].drag:
                add(group[-1], "take", "map: take")  # tap_bus_first: the bus's tap, then its take line
            else:
                for s in trailing_drags(group):
                    add(s, "find_bus")
    return out


# --- the screen ------------------------------------------------------------------------------------------

@dataclass
class Frames:
    """A stretch of the recording: each frame's wall time, recovery.thumb and whole-frame mean grey."""
    times: np.ndarray
    thumbs: np.ndarray
    means: np.ndarray

    @classmethod
    def of(cls, times, images) -> Frames:
        thumbs = np.array([recovery.thumb(im) for im in images], np.float32)
        return cls(np.asarray(times, float), thumbs, thumbs.mean(axis=(1, 2)))

    def covers(self, t: float) -> bool:
        return len(self.times) > 0 and self.times[0] <= t <= self.times[-1]


def stretch(spans: list[Frames], t: float) -> Frames | None:
    return next((f for f in spans if f.covers(t)), None)


def answer(f: Frames, at: float, until: float):
    """(verdict, share, answer s) of the screen from PRE s before at to until (module doc)."""
    ref = int(np.searchsorted(f.times, at - PRE, "right")) - 1
    end = int(np.searchsorted(f.times, until, "left"))
    if ref < 0 or end <= ref + 1:
        return "no video", None, None
    before, window = f.thumbs[ref], f.thumbs[ref + 1:end]
    if not np.any(window != before):
        return "frozen", None, None
    moved = (np.abs(window - before) > 8).mean(axis=(1, 2))
    share = float(moved.max())
    k = next((k for k, th in enumerate(window) if not recovery.same_screen(before, th)), None)
    return ("ignored", share, None) if k is None else ("taken", share, round(float(f.times[ref + 1 + k] - at), 3))


def last_black(f: Frames, at: float, window: float) -> float | None:
    sel = np.flatnonzero((f.times >= at - window) & (f.times <= at) & (f.means < BLACK))
    return float(f.times[sel[-1]]) if len(sel) else None


def judge(spans: list[Frames], touches: list[Touch], every: list[Stroke], offset: float,
          fade_window: float = FADE_WINDOW) -> list[Row]:
    """A Row per touch: its verdict on the frames and the time since the fade (module doc). every: all the log's
    touches, on the map or not, which end each touch's window and say whether it was the first after the fade."""
    starts = [s.t for s in every]
    rows = []
    for tc in touches:
        at = tc.t + offset
        k = bisect.bisect_right(starts, tc.t)
        until = min(at + ANSWER, starts[k] + offset) if k < len(starts) else at + ANSWER
        f = stretch(spans, at)
        verdict, share, ans = answer(f, at, until) if f else ("no video", None, None)
        black = last_black(f, at, fade_window) if f else None
        prev = starts[k - 2] + offset if k >= 2 else None  # the touch before this one (starts[k - 1] is this one)
        first = black is not None and (prev is None or prev < black)
        rows.append(Row(tc.t, tc.x, tc.y, tc.kind, tc.outcome, tc.drag, tc.moves_at, verdict, share, ans,
                        None if black is None else round(at - black, 3), first))
    return rows


def measure_offset(spans: list[Frames], touches: list[Touch]) -> Offset | None:
    """The median, over the map's drags, of the time from the drag's first move to the first frame that left the frame
    REACH s before it; drags that left none (ignored ones) or whose screen moved before (still fading in) do not count."""
    lat = []
    for tc in touches:
        if tc.kind in DRAGS and (f := stretch(spans, tc.moves_at - REACH)):
            ref = int(np.searchsorted(f.times, tc.moves_at - REACH, "right")) - 1
            end = int(np.searchsorted(f.times, tc.moves_at + 1.0, "right"))
            k = next((k for k in range(ref + 1, end) if not recovery.same_screen(f.thumbs[ref], f.thumbs[k])), None)
            if k is not None and (d := float(f.times[k] - tc.moves_at)) > -REACH + 2 / FPS:
                lat.append(d)
    if not lat:
        return None
    q = statistics.quantiles(lat, n=4) if len(lat) > 1 else [lat[0]] * 3
    return Offset(round(statistics.median(lat), 3), len(lat), round(q[0], 3), round(q[2], 3))


def decode(path, ss: float, dur: float, start: float) -> Frames:
    """Frames of path from ss s on, dur s at FPS and 1280x720, timed by the wall clock (start: its first frame's)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-t", f"{dur:.3f}", "-i", str(path), "-vf", f"fps={FPS},scale=1280:720",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    size, thumbs = 1280 * 720 * 3, []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as p:
        while len(buf := p.stdout.read(size)) == size:
            thumbs.append(recovery.thumb(np.frombuffer(buf, np.uint8).reshape(720, 1280, 3)))
    th = np.array(thumbs, np.float32).reshape(-1, 18, 32)
    return Frames(start + ss + np.arange(len(th)) / FPS, th, th.mean(axis=(1, 2)))


def read_frames(footage: Footage, touches: list[Touch], fade_window: float) -> list[Frames]:
    """The stretches of the recording the touches need, overlapping windows joined, one ffmpeg run each."""
    wins = sorted((tc.t - fade_window - 1.0, tc.t + ANSWER + 1.0) for tc in touches)
    merged: list[list[float]] = []
    for a, b in wins:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    spans = []
    for a, b in merged:
        piece = next(((start, path) for start, path in reversed(footage.pieces) if start <= b), None)
        if piece is None:
            continue
        start, path = piece
        a = max(a, start)
        spans.append(decode(path, a - start, b - a, start))
    return spans


# --- report ----------------------------------------------------------------------------------------------

FIELDS = ["time", "x", "y", "kind", "outcome", "verdict", "share", "answer_s", "since_fade_s", "first_after_fade"]


def csv_row(r: Row, fade_window: float = FADE_WINDOW) -> dict:
    fmt = lambda v: "" if v is None else f"{v:.3f}"  # noqa: E731
    return {"time": hms(r.t), "x": r.x, "y": r.y, "kind": r.kind, "outcome": r.outcome, "verdict": r.verdict,
            "share": fmt(r.share), "answer_s": fmt(r.answer),
            "since_fade_s": f"none in {fade_window:g} s" if r.since_fade is None else f"{r.since_fade:.2f}",
            "first_after_fade": "yes" if r.first_after_fade else ""}


def summary(rows: list[Row], off: Offset | None, given: float | None = None) -> str:
    if given is not None:
        lines = [f"offset {given:+.3f} s (given)"]
    elif off:
        lines = [f"offset {off.value:+.3f} s (median of {off.n} map drags the map followed, quartiles {off.lo:+.3f} to {off.hi:+.3f} s)"]
    else:
        lines = ["offset: no map drag to measure it on"]
    lines.append(f"{'kind':<9} {'verdict':<8} {'touches':>7} {'first after a fade':>7}  since the fade (first touches)")
    for kind, verdict in sorted({(r.kind, r.verdict) for r in rows}):
        sel = [r for r in rows if (r.kind, r.verdict) == (kind, verdict)]
        first = sorted(r.since_fade for r in sel if r.first_after_fade)
        span = f"{first[0]:.2f}-{first[-1]:.2f} s" if first else "-"
        lines.append(f"{kind:<9} {verdict:<8} {len(sel):>7} {len(first):>7}  {span}")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--video", action="append", required=True, help="PATH@START, the wall time of its first frame")
    ap.add_argument("-o", "--out", required=True, help="the CSV to write")
    ap.add_argument("--offset", type=float, help="s from a touch's log line to the screen; measured when left out")
    ap.add_argument("--fade-window", type=float, default=FADE_WINDOW)
    ap.add_argument("--from", dest="t0", default="00:00:00")
    ap.add_argument("--to", dest="t1", default="23:59:59.999")
    a = ap.parse_args(argv)
    log = read_log(a.log)
    every = strokes(log)
    touches = [tc for tc in map_touches(log) if secs(a.t0) <= tc.t <= secs(a.t1)]
    spans = read_frames(Footage(a.video), touches, a.fade_window)
    off = None if a.offset is not None else measure_offset(spans, touches)
    rows = judge(spans, touches, every, a.offset if a.offset is not None else (off.value if off else 0.0), a.fade_window)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(csv_row(r, a.fade_window) for r in rows)
    print(summary(rows, off, a.offset))
    print(f"{len(rows)} map touches -> {a.out}")


if __name__ == "__main__":
    main()
