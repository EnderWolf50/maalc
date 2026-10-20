"""Align a screen recording with maafw.log: how long each screen was up, and how soon the hub recognized it.

    uv run --group probe python tools/video_align.py VIDEO --started 2026-10-19T19:43:52.123 \\
        --log install/debug/maafw.bak.2026.10.19-21.18.12.223.log install/debug/maafw.log \\
        --node Victory victory.png 415,275,450,150 0.6 [--node Loading loading.png 1055,620,200,50 0.7] \\
        [--hub MirrorHub] \\
        [--from "2026-10-19 19:44"] [--to "2026-10-19 21:13"] [--fps 10] [--chunk 60] [--drift 2] \\
        [--max-lost 7200] [--min-corr 0.8] -o screens.csv

Each `--node NAME TEMPLATE X,Y,W,H THRESHOLD` is a TemplateMatch node the bot ran in that run, with the template,
roi and threshold it had then (TEMPLATE relative to `assets/resource/base/`, or a path): the bot's log has a
`TemplateMatcher::analyze] NAME` score for it on every pass. An OCR node logs no such score and cannot be used.
The tool scores the same template and roi on the video frames (scaled to 1280x720). List every log file, oldest
first (rotated `maafw.bak.*` files, then `maafw.log`); pwsh does not expand a `*` for you.

**Clock.** `--started` is the wall time of the first frame (screen-record's `started`), so a frame's time is
started + pts + offset, and the offset drifts: on 2026-10-19 it went from +0.8 s to +1.3 s over an hour. The
video is cut into `--chunk` seconds. The anchor is the offset (-2 s to `--max-lost` s) at which the video's
scores correlate best with the bot's own scores over two chunks, if no other offset comes within 0.05; then
every chunk from the start is fitted within `--drift` s of the last offset found (the anchor, for the chunks
before it). A chunk with nothing to fit takes the nearest fitted offset; one that shows a screen but correlates
under `--min-corr` stays unaligned and its frames are left out.

**Freezes and holes.** gfxcapture draws nothing while the display sleeps; the recorder then repeats its last frame
(on 2026-10-19: 24 minutes, then the last 18 minutes of the video), so the pts run on but the screen is unknown.
A freeze is `FREEZE` s or more of frames identical to the one before, pixel for pixel in greyscale (a repeated
frame decodes to the same pixels; a refresh of up to 1 s, or 3 frames, inside does not end it), while the bot's
score changes on half its passes or more, or the bot logged under two scores inside it. A screen the game itself left
still (a stuck Now Loading) keeps the bot's score still too, and is no freeze. A freeze's frames are left out
and the tool prints it. A hole in the pts (over `HOLE` s without a frame) is printed too.

**Output.** One CSV row per interval a node was up (score over its threshold, frames under 0.25 s apart, or 1.5
frames at a lower `--fps`):
when it came up (log time), how long it stayed, how many `--hub` passes started while it was up, how many until
the node's first `Node.Recognition.Succeeded`, and how long after it came up that hit was logged. A summary per
node follows. The logs go oldest first, as for `tools/maafw_timeline.py`.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

from maafw_timeline import TS as STAMP, stamp

RESOURCE = Path(__file__).resolve().parents[1] / "assets/resource/base"
GAP = 0.25  # s: frames up closer than this make one interval
MIN_SAMPLES = 10  # bot samples an offset must see in a chunk
HOLE = 1.0  # s: a jump in the pts longer than this is lost frames
FREEZE = 10.0  # s: an unchanged frame this long is a freeze


def parse_log(lines, names, hub: str):
    """(hub pass starts, {name: hit times}, {name: (times, scores)}) of the bot's log, in epoch seconds."""
    starts, hits, bot = [], {n: [] for n in names}, {n: ([], []) for n in names}
    score = {n: re.compile(rf"TemplateMatcher::analyze\] {re.escape(n)} \[all_results_=\[\{{[^}}]*\"score\":([\d.]+)")
             for n in names}
    for line in lines:
        m = STAMP.match(line)
        if not m:
            continue
        t = stamp(m[1])
        if f"recognize_list] [cur_node_={hub}]" in line and line.rstrip().endswith("| enter"):
            starts.append(t)
        elif "[msg=Node.Recognition.Succeeded]" in line:
            for n in names:
                if f'"name":"{n}"' in line[:400]:
                    hits[n].append(t)
        else:
            for n, r in score.items():
                if s := r.search(line):
                    bot[n][0].append(t)
                    bot[n][1].append(float(s[1]))
    for n, (t, s) in bot.items():
        order = np.argsort(t, kind="stable")  # searchsorted needs them in time order
        bot[n] = (np.array(t)[order], np.array(s)[order])
    return starts, hits, bot


def video_scores(video: Path, nodes: dict, started: float, fps: float = 10.0):
    """(wall time of each scored frame by its pts, {name: score per frame}, whether the frame is the one before
    it, unchanged); `fps` frames a second are scored."""
    import cv2  # the probe group's; the rest of the tool runs without it

    tpl = {n: cv2.imread(str(f)) for n, (f, _, _) in nodes.items()}
    for n, img in tpl.items():
        if img is None:
            sys.exit(f"cannot read the template of {n}: {nodes[n][0]}")
    vt, vs, still, prev = [], {n: [] for n in nodes}, [], None
    cap, due = cv2.VideoCapture(str(video)), 0.0
    while cap.grab():
        pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if pts < due:
            continue
        due = pts + 1 / fps - 1e-3
        ok, im = cap.retrieve()
        if not ok:
            break
        vt.append(started + pts)
        if len(vt) % round(600 * fps) == 0:
            print(f"{pts / 60:.0f} min of video scored", file=sys.stderr, flush=True)
        if im.shape[:2] != (720, 1280):
            im = cv2.resize(im, (1280, 720))
        grey = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        still.append(prev is not None and not cv2.countNonZero(cv2.absdiff(grey, prev)))
        prev = grey
        for n, (_, (x, y, w, h), _) in nodes.items():
            vs[n].append(float(cv2.matchTemplate(im[y:y + h, x:x + w], tpl[n], cv2.TM_CCOEFF_NORMED).max()))
    return np.array(vt), {n: np.array(s) for n, s in vs.items()}, np.array(still)


class Segment(NamedTuple):
    v0: float  # wall time of its first frame by pts
    v1: float
    offset: float | None  # log time = frame time + offset; None: unaligned
    corr: float


def pearson(cnt, sx, sxx, sy, syy, sxy):
    vx, vy = cnt * sxx - sx * sx, cnt * syy - sy * sy
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (cnt * sxy - sx * sy) / np.sqrt(vx * vy)
    return np.where((vx > 1e-9) & (vy > 1e-9), np.nan_to_num(r, nan=-1.0), -1.0)  # a flat side tells nothing


def scan(vt, vs, bot, v0, v1, lo, hi, step):
    """(offsets, Pearson correlation per offset, bot samples each offset sees) of the video's scores over
    [v0, v1) against the bot's samples at frame time + offset, on a grid of `step` s; a grid point without a bot
    sample within step/2 is left out, and an offset that sees under MIN_SAMPLES samples scores -1. All nodes pool."""
    grid = np.arange(v0, v1, step)
    m = len(grid)
    span = np.arange(v0 + lo, v1 + hi + step, step)
    n = len(span) - m + 1
    if m < 2 or n < 1:
        return np.array([]), np.array([]), np.array([])
    sums = np.zeros((6, n))
    ones = np.ones(m)
    for name, (bt, bs) in bot.items():
        if not len(bt):
            continue
        v = vs[name][np.clip(np.searchsorted(vt, grid), 0, len(vt) - 1)]
        i = np.clip(np.searchsorted(bt, span), 1, max(len(bt) - 1, 1))
        i -= (np.abs(bt[i - 1] - span) < np.abs(bt[np.minimum(i, len(bt) - 1)] - span)).astype(int)
        i = np.minimum(i, len(bt) - 1)  # the nearest sample
        mask = (np.abs(bt[i] - span) <= step / 2).astype(float)
        b = bs[i] * mask
        for k, (x, y) in enumerate([(mask, ones), (mask, v), (mask, v * v), (b, ones), (b * b, ones), (b, v)]):
            sums[k] += np.correlate(x, y, "valid")
    corr = pearson(*sums)
    return lo + np.arange(n) * step, np.where(sums[0] >= MIN_SAMPLES, corr, -1.0), sums[0]


def fine(vt, vs, bot, v0, v1, around):
    """(offset within 0.5 s of `around` to the frame, its correlation): the video's score at each bot sample of
    [v0 + around, v1 + around] against the sample. The middle of a plateau of equal scores wins."""
    offs = around + np.arange(-15, 16) / 30
    sums = np.zeros((6, len(offs)))
    for name, (bt, bs) in bot.items():
        bt, bs = bt[(bt >= v0 + around) & (bt < v1 + around)], bs[(bt >= v0 + around) & (bt < v1 + around)]
        x = vs[name][np.clip(np.searchsorted(vt, bt[None, :] - offs[:, None]), 0, len(vt) - 1)]
        sums += [np.full(len(offs), len(bt)), x.sum(1), (x * x).sum(1), np.full(len(offs), bs.sum()),
                 np.full(len(offs), (bs * bs).sum()), (x * bs).sum(1)]
    corr = pearson(*sums)
    top = np.flatnonzero(corr >= corr.max() - 1e-6)
    i = top[len(top) // 2]
    return round(float(offs[i]), 3), float(corr[i])


def chunk_offset(vt, vs, bot, v0, v1, max_lost, min_corr) -> Segment:
    """The chunk's offset in [-2 s, max_lost]: the best correlation, unless under min_corr or a second peak
    (2 s or more away) comes within 0.05 of it, which a chunk with only one event on screen gives. An offset that
    sees under half the median sample count is left out: a window that runs off the end of the log holds one
    event or two, which correlate perfectly anywhere."""
    offs, corr, cnt = scan(vt, vs, bot, v0, v1, -2.0, max_lost, 0.25)
    if not len(corr) or not (cnt > 0).any():
        return Segment(v0, v1, None, -1.0)
    corr = np.where(cnt >= np.median(cnt[cnt > 0]) / 2, corr, -1.0)
    i = int(corr.argmax())
    rival = corr[np.abs(offs - offs[i]) >= 2].max(initial=-1.0)
    if corr[i] < min_corr or rival > corr[i] - 0.05:
        return Segment(v0, v1, None, float(corr[i]))
    off, c = fine(vt, vs, bot, v0, v1, offs[i])
    return Segment(v0, v1, off if c >= min_corr else None, c)


def local(vt, vs, bot, v0, v1, around, drift, min_corr) -> Segment:
    """The chunk's offset within `drift` of `around`; None when its best correlation is under min_corr
    (-1: nothing to correlate, a flat video or bot side, or too few samples)."""
    offs, corr, _ = scan(vt, vs, bot, v0, v1, around - drift, around + drift, 0.25)
    if not len(corr) or corr.max() < min_corr:
        return Segment(v0, v1, None, float(corr.max()) if len(corr) else -1.0)
    off, c = fine(vt, vs, bot, v0, v1, offs[int(corr.argmax())])
    return Segment(v0, v1, off if c >= min_corr else None, c)


def freezes(vt, still, bot=None, min_s=FREEZE, blip=1.0) -> list[tuple[float, float]]:
    """Stretches of at least `min_s` where the frame does not change while the bot's own score keeps changing (on
    half its passes or more) or the bot logged none; a changed frame within `blip` s of the still frames on both
    sides does not end one (the recorder repeated its last frame, refreshing it now and then). A screen the game
    itself left still (a stuck Now Loading) keeps the bot's score still too, and is no freeze."""
    out = []
    for t, s in zip(vt, still):
        if not s:
            continue
        if out and t - out[-1][1] <= blip:
            out[-1][1] = t
        else:
            out.append([t, t])

    def bot_moved(a, b):  # 2 s in from each end: the edges still show the screen fading in or out
        inner = [x for bt, bs in (bot or {}).values() if len(x := bs[(bt >= a + 2) & (bt <= b - 2)]) > 1]
        # 2026-10-19: the bot's score moved between 71 % and 80 % of its passes through the two freezes, and
        # 0 % to 25 % through still screens of the game. A bot that logged nothing cannot tell: the screen is unknown.
        return not inner or any((np.abs(np.diff(x)) > 0.01).mean() >= 0.5 for x in inner)

    return [(a, b) for a, b in out if b - a >= min_s and bot_moved(a, b)]


def holes(vt, min_s=HOLE) -> list[tuple[float, float]]:
    """(last frame before, first frame after) wherever the pts jump by more than `min_s`: frames the recorder lost."""
    i = np.flatnonzero(np.diff(vt) > min_s)
    return [(float(vt[k]), float(vt[k + 1])) for k in i]


def fit(vt, vs, bot, chunk=60.0, max_lost=7200.0, min_corr=0.8, drift=2.0, frozen=()) -> list[Segment]:
    """Segments of the video, `chunk` seconds each, with their offsets.

    The anchor comes from a wide search (`chunk_offset`, -2 s to `max_lost`) over two chunks, sliding on until
    one is found; then every chunk from the start is fitted within `drift` s of the last offset found (the
    anchor, for the chunks before it), which follows the slow drift between the recorder's clock and the log's.
    A chunk mostly inside a freeze stays unaligned (corr -1), and so does one that shows a screen but fits no
    offset near the last (corr under min_corr). A chunk with nothing to fit (corr -1 from the fit: no screen
    change, too few bot samples) takes the nearest fitted offset, since the clock runs on through it."""
    edges = list(np.arange(vt[0], vt[-1], chunk)) + [vt[-1] + 1e-6]
    chunks = list(zip(edges, edges[1:]))

    def frozen_chunk(a, b):
        return sum(min(b, y) - max(a, x) for x, y in frozen if x < b and y > a) >= 0.9 * (b - a)

    off = None
    for a, _ in chunks:
        if not frozen_chunk(a, a + chunk):
            off = chunk_offset(vt, vs, bot, a, min(a + 2 * chunk, edges[-1]), max_lost, min_corr).offset
            if off is not None:
                break
    if off is None:
        return [Segment(a, b, None, -1.0) for a, b in chunks]
    segs, carry = [], []
    for a, b in chunks:  # from the start: the chunks before the anchor are fitted around it too
        if frozen_chunk(a, b):
            segs.append(Segment(a, b, None, -1.0))
            continue
        s = local(vt, vs, bot, a, b, off, drift, min_corr)
        if s.offset is not None:
            off = s.offset
        elif s.corr == -1.0:
            carry.append(len(segs))
        segs.append(s)
    fitted = [k for k, s in enumerate(segs) if s.offset is not None]
    for k in carry:
        if fitted:
            j = min(fitted, key=lambda j: (abs(j - k), j))
            segs[k] = segs[k]._replace(offset=segs[j].offset)
    # ponytail: a recorder that drops frames and closes up the pts (no hole) moves the offset past `drift`; the
    # chunks after it then stay unaligned (shown as such) instead of being re-fitted with a second wide search.
    return segs


def log_times(vt, segs, frozen=()) -> np.ndarray:
    """Each frame's log time; NaN for a frame of an unaligned segment or inside a freeze (its screen is unknown)."""
    lt = np.full(len(vt), np.nan)
    for s in segs:
        if s.offset is not None:
            sel = (vt >= s.v0) & (vt < s.v1)
            lt[sel] = vt[sel] + s.offset
    for x, y in frozen:
        lt[(vt >= x) & (vt <= y)] = np.nan
    return lt


def intervals(lt, scores, threshold, hub, hits, gap=GAP) -> list[dict]:
    """The intervals the screen was up, in log time; an unaligned frame ends one."""
    spans = []
    for t, s in zip(lt, scores):
        if np.isnan(t) or s < threshold:
            if np.isnan(t) and spans:
                spans[-1][2] = True  # closed
            continue
        if spans and not spans[-1][2] and t - spans[-1][1] <= gap:
            spans[-1][1] = t
        else:
            spans.append([t, t, False])
    rows = []
    for a, b, _ in spans:
        passes = [h for h in hub if a <= h <= b]
        hit = [h for h in hits if a <= h <= b + 0.5]  # a hit is logged after its screenshot
        first = min(hit) if hit else None
        rows.append({"up_at": round(float(a), 3), "up_s": round(float(b - a), 3), "hub_passes_while_up": len(passes),
                     "passes_until_hit": len([h for h in passes if first is None or h <= first]),
                     "recognized": bool(hit), "hit_after_s": round(float(first - a), 3) if hit else ""})
    return rows


def clock(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--started", required=True, help="wall time of the first frame, ISO (screen-record's `started`)")
    ap.add_argument("--log", nargs="+", type=Path, required=True)
    ap.add_argument("--node", nargs=4, action="append", required=True, metavar=("NAME", "TEMPLATE", "ROI", "THRESHOLD"))
    ap.add_argument("--hub", default="MirrorHub")
    ap.add_argument("--from", dest="lo", help="log time, ISO")
    ap.add_argument("--to", dest="hi", help="log time, ISO")
    ap.add_argument("--fps", type=float, default=10.0, help="video frames scored a second")
    ap.add_argument("--chunk", type=float, default=60.0)
    ap.add_argument("--max-lost", type=float, default=7200.0)
    ap.add_argument("--min-corr", type=float, default=0.8)
    ap.add_argument("--drift", type=float, default=2.0, help="s a chunk's offset may move from the last one")
    ap.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args(argv)
    nodes = {n: (RESOURCE / f if (RESOURCE / f).exists() else Path(f), tuple(map(int, roi.split(","))), float(th))
             for n, f, roi, th in a.node}
    lo, hi = stamp(a.lo) if a.lo else 0.0, stamp(a.hi) if a.hi else float("inf")

    def lines():
        for path in a.log:
            with open(path, encoding="utf-8", errors="replace") as f:
                yield from f

    hub, hits, bot = parse_log(lines(), list(nodes), a.hub)
    vt, vs, still = video_scores(a.video, nodes, stamp(a.started), a.fps)
    frozen = freezes(vt, still, bot, blip=max(1.0, 3 / a.fps))
    segs = fit(vt, vs, bot, a.chunk, a.max_lost, a.min_corr, a.drift, frozen)
    for s in segs:
        print(f"video {clock(s.v0)}-{clock(s.v1)}  " + (f"offset {s.offset:+.3f} s" if s.offset is not None else "unaligned")
              + f"  corr {s.corr:.3f}")
    for x, y in frozen:
        print(f"freeze: the video shows one frame from {clock(x)} to {clock(y)} ({y - x:.0f} s)")
    for x, y in holes(vt):
        print(f"hole: no frames from {clock(x)} to {clock(y)} ({y - x:.1f} s)")
    lt = log_times(vt, segs, frozen)
    rows = [{"screen": n, **r} for n in nodes for r in intervals(lt, vs[n], nodes[n][2], hub, hits[n], max(GAP, 1.5 / a.fps)) if lo <= r["up_at"] <= hi]
    rows.sort(key=lambda r: r["up_at"])
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["screen", "up_at", "up_s", "hub_passes_while_up", "passes_until_hit", "recognized", "hit_after_s"])
        w.writeheader()
        w.writerows({**r, "up_at": clock(r["up_at"])} for r in rows)
    for n in nodes:
        r = [x for x in rows if x["screen"] == n]
        if r:
            up = sorted(x["up_s"] for x in r)
            after = sorted(x["hit_after_s"] for x in r if x["hit_after_s"] != "")
            print(f"{n}: {len(r)} intervals, {sum(x['recognized'] for x in r)} recognized, up {up[0]}-{up[-1]} s"
                  f" (median {up[len(up) // 2]}), hit after median {after[len(after) // 2] if after else '-'} s")


if __name__ == "__main__":
    main()
