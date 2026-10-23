"""Evidence of a live run from the bot's log and the recording: events, captions, frames, clips, the map and pack pages.

    uv run --group probe python tools/live/evidence.py <command> ...

  events LOG [--from T --to T] -o events.json      taps and swipes, for evidence-annotate's --events
  steps  LOG [--from T --to T] [--grep RE] [--hold S] -o steps.json   one caption per `[maalc]` line
  frames --video V@START... -o DIR T [T ...]       one PNG per wall time, named HH-MM-SS.fff.png
  clip   --video V@START... --from T --to T -o OUT.mp4   a constant-frame-rate cut
  map    LOG --video V@START... --floor N -o DIR [--after T] [--fix FIX.json] [--clip]
  packs  LOG --video V@START... --floor N -o DIR [--clip]
  mask   IMG [IMG ...]                             black out the identity regions, in place

LOG is the bot's stdout with a wall time on each line, as `tools/live/bot.py run` writes it
(`HH:MM:SS.fff <line>`; MXU's `YYYY-MM-DD HH:MM:SS [stdout] <line>` reads too). `events` also takes a
maafw.log (through `maafw_events.py`, in game pixels); from LOG it takes the controller's
`x: X, y: Y, width: W, height: H` lines, in device pixels, and a burst under 0.25 s apart is one swipe.
Every time T is wall clock, `HH:MM:SS[.fff]`, of the log's day. `--video PATH@START` is a recording and the
wall time of its first frame (screen-record's `started`); give one per piece of a run recorded in pieces.

**map** stitches the floor from the frames before and after each `map: dragged the map N px` and boxes every
node the bot read, at its column and row: green read right, red a wrong type, orange a wrong Cost or a node
the bot did not list (from FIX), with the Cost it read and the first read when a later one replaced it. Reads
that took more than the marks have their own colour and line: violet a type corrected once the map was dragged
near, magenta a Cost that read no number or missed, white a boss told by its Cost, cyan a boss told by its red
glow or by the shop before it; a legend under the picture says so. The route is numbered and the banner has the
drags, the path and its score. Each shot is the still map the bot read (the still stretch of the footage around
the read, never a motion run: a drag back is not a drag), and the shots are laid side by side by the slide
measured between them on the frames (template match), the log's px where none matches. FIX is what you judged on the frames:
`{"c4/down": ["risky"], "c2/mid": ["cost", "<what it read and what the screen shows>"], "c3/up": ["missed", "<label>"]}`.
`--after T` takes the floor's next reading after T (a restart re-reads the map). Writes stitched.png,
before-1.png, after-N.png, route.json; `--clip` adds drag-clip.mp4 (read, drag, read on, plan, with the touches).

**packs** writes one still per `floor N packs` reading (refreshes included): each card's name and weight, the
pulled card's thick border, and how long the cards took from the deal (card area empty: mean under 8) to standing still
(mean frame difference under 2 for 8 frames at 30 fps), measured on the video. Writes pack-K.png,
pack-K-raw.png, packs.json; `--clip` adds pack-K-clip.mp4.

Stills and the clips of map and packs are masked with `--masks` (default `.local/evidence/masks.json`);
those clips go through evidence-annotate's annotate.py (`--annotate`, default its global skill folder).
`clip` is a raw cut for annotate.py, unmasked: it stays in `.local/` until annotate.py has masked it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from itertools import accumulate
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from live import maafw_events  # noqa: E402
from local_dir import local_dir  # noqa: E402

STAMP = re.compile(r"^(?:\d{4}-\d\d-\d\d )?(\d\d):(\d\d):(\d\d(?:\.\d+)?) (?:\[stdout\] )?(.*)$")
TOUCH = re.compile(r"^x: (\d+), y: (\d+), width: (\d+), height: (\d+)")
ANNOTATE = Path.home() / ".claude/skills/evidence-annotate/scripts/annotate.py"
FONTS = ["C:/Windows/Fonts/msjh.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
W, H = 1280, 720  # frames are scaled to the game's own 720p grid
GREEN, RED, ORANGE, YELLOW, GREY, BLUE = (60, 220, 60), (255, 60, 60), (255, 160, 0), (255, 220, 0), (170, 170, 170), (90, 200, 255)
VIOLET, MAGENTA, WHITE, CYAN = (170, 110, 255), (255, 70, 200), (245, 245, 245), (0, 225, 225)
# a node's notes, in the order they ring its box: tag -> colour
NOTE_COLOUR = {"boss_shop": CYAN, "boss_glow": CYAN, "boss_by_cost": WHITE, "cost_miss": MAGENTA, "cost_none": MAGENTA, "retyped": VIOLET}
LEGEND = [(GREEN, "綠＝讀對"), (RED, "紅＝類型錯"), (ORANGE, "橘＝Cost 錯或漏列"), (VIOLET, "紫＝先讀錯，拖近後改正"),
          (MAGENTA, "洋紅＝Cost 沒讀到或 miss"), (WHITE, "白＝靠 Cost 判成 Boss"), (CYAN, "青＝Boss 紅光或商店判定"), (BLUE, "藍線＝路線")]
SHIFT_MIN = 0.6  # TM_CCOEFF_NORMED of a slide to trust: the real one scored 0.91-0.94 (run 11, floor 1), another place 0.5 at most
COLX = lambda k: 328 + 255 * (k - 1)  # noqa: E731  x of map column k (1-based) before any drag
ROWY = {"up": 144, "mid": 357, "down": 570}
BUS = (110, 357)


def secs(hms: str) -> float:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


hms = maafw_events.clock  # seconds since midnight -> HH:MM:SS.fff


def parse_log(lines) -> list[tuple[float, str]]:
    """[(wall seconds since midnight, text)] of every stamped line."""
    # ponytail: a run across midnight wraps to 0; add the date when one does
    return [(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), m[4]) for m in map(STAMP.match, lines) if m]


def read_log(path) -> list[tuple[float, str]]:
    return parse_log(Path(path).read_text(encoding="utf-8", errors="replace").splitlines())


def maalc(log) -> list[tuple[float, str]]:
    return [(t, x[8:]) for t, x in log if x.startswith("[maalc] ")]


def font(size: int):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


# --- events and captions ---------------------------------------------------------------------------------

def touches(log, t0: float, t1: float) -> dict:
    """events.json of the controller's touch lines in [t0, t1]: a burst under 0.25 s apart and 150 px is one swipe."""
    pts, space = [], [1920, 1080]
    for t, x in log:
        if t0 <= t <= t1 and (m := TOUCH.match(x)):
            pts.append((t, int(m[1]), int(m[2])))
            space = [int(m[3]), int(m[4])]
    events, i = [], 0
    while i < len(pts):
        j = i
        while j + 1 < len(pts) and pts[j + 1][0] - pts[j][0] < 0.25 and abs(pts[j + 1][1] - pts[j][1]) + abs(pts[j + 1][2] - pts[j][2]) < 150:
            j += 1
        a, b = pts[i], pts[j]
        if j == i:
            events.append({"t": hms(a[0]), "kind": "tap", "x": a[1], "y": a[2]})
        else:
            events.append({"t": hms(a[0]), "kind": "swipe", "x": a[1], "y": a[2], "x2": b[1], "y2": b[2], "ms": round((b[0] - a[0]) * 1000)})
        i = j + 1
    return {"space": space, "pointer": "touch", "events": events}


def captions(log, t0: float, t1: float, grep: str = "", hold: float = 3.0) -> list[dict]:
    """A step per `[maalc]` line in [t0, t1] matching grep, up to the next one or hold seconds."""
    kept = [(t, x) for t, x in maalc(log) if t0 <= t <= t1 and re.search(grep, x)]
    ends = [t for t, _ in kept[1:]] + [t1]
    return [{"from": hms(t), "to": hms(min(end, t + hold, t1)), "title": x} for (t, x), end in zip(kept, ends)]


# --- footage ---------------------------------------------------------------------------------------------

class Footage:
    """The pieces of a recording, each with the wall time of its first frame."""

    def __init__(self, specs: list[str]):
        self.pieces = sorted((secs(s.rsplit("@", 1)[1]), s.rsplit("@", 1)[0]) for s in specs)

    def locate(self, t: float) -> tuple[str, float]:
        """(file, seconds into it) of the piece that covers wall time t."""
        for start, path in reversed(self.pieces):
            if t >= start:
                return path, round(t - start, 3)
        sys.exit(f"{hms(t)} is before the first frame of every --video")


def decode(path, ss: float, dur: float | None, fps: float | None, gray: bool = False) -> np.ndarray:
    """Frames of path from ss on, at 1280x720: dur seconds at fps, or the one frame at ss when fps is None."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", *(["-t", f"{dur:.3f}"] if dur else []), "-i", str(path),
           "-vf", (f"fps={fps}," if fps else "") + f"scale={W}:{H}", *([] if fps else ["-frames:v", "1"]),
           "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, H, W, *([] if gray else [3]))


def frames(footage: Footage, t0: float, t1: float, fps: float, gray: bool = False):
    """(wall times, frames) of [t0, t1] at fps, from the piece that covers t0."""
    path, off = footage.locate(t0)
    fr = decode(path, off, t1 - t0, fps, gray)
    if not len(fr):
        sys.exit(f"no frames in {path} at {hms(t0)}-{hms(t1)}")
    return [t0 + i / fps for i in range(len(fr))], fr


def grab(footage: Footage, t: float) -> Image.Image:
    path, off = footage.locate(t)
    return Image.fromarray(decode(path, off, None, None)[0])


def cut(footage: Footage, t0: float, t1: float, out) -> None:
    """A constant-frame-rate cut of [t0, t1]: annotate.py turns pieces with uneven timestamps into one frame."""
    path, off = footage.locate(t0)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(path), "-r", "30",
                    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], check=True)


def annotated_clip(footage: Footage, t0: float, t1: float, out: Path, events: dict, steps: list, a) -> None:
    """Cut [t0, t1] and burn events, steps and masks into it with evidence-annotate."""
    stem = out.with_suffix("")
    files = {k: Path(f"{stem}-{k}.json") for k in ("events", "steps")}
    files["events"].write_text(json.dumps(events, indent=1), encoding="utf-8")
    files["steps"].write_text(json.dumps(steps, ensure_ascii=False, indent=1), encoding="utf-8")
    raw = local_dir("scratch") / f"cut-{os.getpid()}-{out.stem}.mp4"  # unmasked: never beside out, which may be shared
    try:
        cut(footage, t0, t1, raw)
        subprocess.run(["uv", "run", str(a.annotate), str(raw), "-o", str(out), "--start", hms(t0), "--events", str(files["events"]),
                        "--steps", str(files["steps"]), "--masks", str(masks_path(a))], check=True)
    finally:
        raw.unlink(missing_ok=True)


# --- masks -----------------------------------------------------------------------------------------------

def masks_path(a) -> Path:
    path = Path(a.masks) if a.masks else local_dir("evidence") / "masks.json"
    if not path.exists():
        sys.exit(f"no {path}: without masks nothing leaves .local/ (docs/agents/local-dev.md)")
    return path


def load_masks(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc["space"], [(np.asarray(Image.open(path.parent / m["template"]).convert("L")), m.get("threshold", 0.8), m["boxes"])
                          for m in doc["masks"]]


def apply_masks(im: Image.Image, masks) -> Image.Image:
    """im with every box blacked out whose template matches it (TM_CCOEFF_NORMED, as annotate.py does)."""
    space, items = masks
    if not items:
        return im
    import cv2  # the probe group's

    g = np.asarray(im.convert("L").resize(tuple(space)))
    sx, sy = im.width / space[0], im.height / space[1]
    d = ImageDraw.Draw(im)
    for tpl, threshold, boxes in items:
        if cv2.matchTemplate(g, tpl, cv2.TM_CCOEFF_NORMED).max() >= threshold:
            for x, y, w, h in boxes:
                d.rectangle([x * sx, y * sy, (x + w) * sx - 1, (y + h) * sy - 1], fill=(0, 0, 0))
    return im


# --- map -------------------------------------------------------------------------------------------------

def floor_block(msgs, floor: int, after: float | None = None) -> list[tuple[float, str]]:
    """The floor's `map:` lines, from its pull (or the first map line after `after`) to its `map: path`."""
    if after is not None:
        start = next(i for i, (t, x) in enumerate(msgs) if t > after and x.startswith("map:"))
    else:
        start = next(i for i, (_, x) in enumerate(msgs) if x.startswith(f"floor {floor}: pull"))
    out = []
    for t, x in msgs[start:]:
        if x.startswith("map:"):
            out.append((t, x))
            if x.startswith("map: path"):
                break
    return out


def parse_map(block):
    """(stages [{cols: {k: {row: type}}, costs: [(x, y, cost, type)], misses: [(x, y, why)], boss: {k: tag}, t0, t1}],
    drags [(t, px, from column)], path)."""
    new = lambda t: {"cols": {}, "costs": [], "misses": [], "boss": {}, "t0": t}  # noqa: E731
    stages, drags, path = [new(block[0][0])], [], None
    for t, x in block:
        if m := re.match(r"map: node at (\d+), (\d+) reads Cost (\S+): (\w+)", x):
            stages[-1]["costs"].append((int(m[1]), int(m[2]), m[3], m[4]))  # "None": the bot saw a coin but read no number
        elif m := re.match(r"map: Cost miss at (\d+), (\d+) \(\w+\): (.*?), crop ", x):
            stages[-1]["misses"].append((int(m[1]), int(m[2]), m[3]))
        elif m := re.match(r"map: column (\d+): the boss' glow without", x):
            stages[-1]["boss"][int(m[1])] = "boss_glow"
        elif m := re.match(r"map: column (\d+): after the shop, so the boss|map: left the shop; column (\d+)", x):
            stages[-1]["boss"][int(m[1] or m[2])] = "boss_shop"
        elif m := re.match(r"map: column (\d+): (.*)", x):
            stages[-1]["cols"][int(m[1])] = {c[1]: c[2] for c in re.finditer(r"(up|mid|down) (\w+) \(", m[2])}
            stages[-1]["t1"] = t
        elif m := re.match(r"map: dragged the map (\d+) px; reading on from column (\d+)", x):
            drags.append((t, int(m[1]), int(m[2])))
            stages.append(new(t))
        elif m := re.match(r"map: path (.*), score (-?\d+)", x):
            path = ([tuple(p.split(" ", 1)) for p in m[1].split(" > ")], int(m[2]))
    return stages, drags, path


def node_table(stages, drags) -> dict:
    """{(column, row): {type: last read, first: first read, cost: the Cost read there or None, stage: the stage of the
    last read, notes: [(tag, detail)] in NOTE_COLOUR's order}}."""
    offsets = list(accumulate((px for _, px, _ in drags), initial=0))
    nodes, notes = {}, {}
    cell = lambda x, y, off: (round((x + off - COLX(1)) / 255) + 1, min(ROWY, key=lambda r: abs(ROWY[r] - y)))  # noqa: E731
    for s, (st, off) in enumerate(zip(stages, offsets)):
        for k, cells in st["cols"].items():
            for row, typ in cells.items():
                n = nodes.setdefault((k, row), {"type": typ, "first": typ, "cost": None, "stage": s})
                n["type"], n["stage"] = typ, s
        for x, y, cost, kind in st["costs"]:
            if (key := cell(x, y, off)) in nodes:
                nodes[key]["cost"] = cost
                found = notes.setdefault(key, {})
                if cost == "None":
                    found["cost_none"] = None
                if kind == "boss":
                    found["boss_by_cost"] = None
        for x, y, why in st["misses"]:
            if (key := cell(x, y, off)) in nodes:
                notes.setdefault(key, {})["cost_miss"] = why
        for k, tag in st["boss"].items():
            for row in ROWY:
                if (k, row) in nodes:
                    notes.setdefault((k, row), {})[tag] = None
    for key, n in nodes.items():
        found = notes.get(key, {})
        if n["first"] != n["type"]:
            found["retyped"] = None
        if n["type"] != "boss":  # a boss note belongs to a node that ended as the boss
            found = {t: d for t, d in found.items() if not t.startswith("boss")}
        n["notes"] = [(t, found[t]) for t in NOTE_COLOUR if t in found]
    return nodes


def motion(grays) -> list[bool]:
    """Per frame: did the map area (rows 110-620) change from the frame before (mean abs difference over 5)?"""
    out, prev = [], None
    for g in grays:
        im = np.asarray(g[110:620], np.int16)
        out.append(prev is not None and float(np.abs(im - prev).mean()) > 5)
        prev = im
    return out


def runs(mov) -> list[tuple[int, int]]:
    """(first, last) frame of each motion run; a single still frame inside does not end one."""
    out, i, n = [], 0, len(mov)
    while i < n:
        if mov[i]:
            j = i
            while j + 1 < n and (mov[j + 1] or mov[min(j + 2, n - 1)]):
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def still_spans(mov, margin: int = 2) -> list[tuple[int, int]]:
    """(first, last) frame of each stretch between motion runs, a margin of frames off the sides that touch one."""
    spans, lo = [], 0
    for a, b in runs(mov):
        spans.append((lo, a - 1 - margin))
        lo = b + 1 + margin
    spans.append((lo, len(mov) - 1))
    return [(a, b) for a, b in spans if a <= b]


def pick_shots(times, mov, reads) -> list[int]:
    """Frame index of the still map each reading (a wall time) saw: its frame, clipped into the still stretch that
    holds it, or into the nearest one when the footage shows the map moving then (the clocks differ by a fraction of a second).

    Run 11, floor 1 (2026-10-24): the map is dragged twice, then back. The log's `dragged` line comes about a second
    after the drag ended and the drag back starts 0.4 s later: the last motion run within a second of the line is the
    drag back, so a pick by motion runs showed the map of the first drag for the second.
    """
    spans = still_spans(mov) or [(0, len(times) - 1)]
    picks = []
    for t in reads:
        k = min(range(len(times)), key=lambda i: abs(times[i] - t))
        a, b = min(spans, key=lambda s: max(s[0] - k, k - s[1], 0))
        picks.append(min(max(k, a), b))
    return picks


def measure_shift(prev, cur, expect: int, reach: int = 100, rows=(150, 560), cols=(40, 440)):
    """(shift, score): how far the map slid from the gray frame prev to cur (cur's x is prev's x minus shift), by the
    best match of cur's left part within reach px of expect; None when it scores under SHIFT_MIN or cur is flat.

    Rows 150-560 leave the HUD and the party bar out. The columns repeat every 255 px, so the search stays near expect.
    """
    import cv2  # the probe group's

    (y0, y1), (x0, x1) = rows, cols
    tpl = np.ascontiguousarray(cur[y0:y1, x0:x1])
    if tpl.std() < 3:
        return None
    lo, hi = max(0, x0 + expect - reach), min(prev.shape[1], x1 + expect + reach)
    score = cv2.matchTemplate(np.ascontiguousarray(prev[y0:y1, lo:hi]), tpl, cv2.TM_CCOEFF_NORMED)[0]
    best = int(score.argmax())
    return (lo + best - x0, float(score[best])) if score[best] >= SHIFT_MIN else None


def label(d, x, y, lines, colours, f):
    for j, (line, col) in enumerate(zip(lines, colours)):
        w = d.textlength(line, font=f)
        d.rectangle([x, y + j * 26, x + w + 8, y + 26 + j * 26], fill=(0, 0, 0, 215))
        d.text((x + 4, y + j * 26), line, font=f, fill=col)


def note_text(tag: str, detail, n) -> str:
    return {"retyped": f"先讀成 {n['first']}，拖近後改正", "cost_none": "Cost 沒讀到", "cost_miss": f"Cost miss：{detail}",
            "boss_by_cost": f"靠 Cost {n['cost']} 判成 boss", "boss_glow": "Boss 紅光判斷，前面沒有商店",
            "boss_shop": "商店後面，判成 boss"}[tag]


def legend_layout(d, f, width: int):
    """([(x, y, colour, text)], height): the legend's entries, flowing over rows of the picture's width."""
    x, y, items = 8, 6, []
    for col, text in LEGEND:
        w = 34 + d.textlength(text, font=f) + 24
        if x + w > width and x > 8:
            x, y = 8, y + 32
        items.append((x, y, col, text))
        x += w
    return items, y + 38


def drag_banner(drags, offsets, measured) -> str:
    """`512px(從第 3 欄接)` per drag, with the slide the frames show where it differs from the log's or was not measured."""
    parts = []
    for n, (_, px, col) in enumerate(drags):
        step = offsets[n + 1] - offsets[n]
        extra = f"，畫面量得 {step}px" if abs(step - px) > 2 else "，位移沒量到" if measured and measured[n] is None else ""
        parts.append(f"{px}px(從第 {col} 欄接{extra})")
    return " + ".join(parts) or "無"


def draw_map(shots, offsets, drags, nodes, path, fix, floor: int, measured=()) -> Image.Image:
    """offsets: the x of each shot on the picture (the slides measured, or the log's px); drags: the log's."""
    logged = list(accumulate((px for _, px, _ in drags), initial=0))
    f, fb = font(22), font(26)
    items, legend_h = legend_layout(ImageDraw.Draw(Image.new("RGB", (1, 1))), f, W + int(offsets[-1]))
    canvas = Image.new("RGB", (W + int(offsets[-1]), H + legend_h))
    for im, off in zip(shots, offsets):
        canvas.paste(im.convert("RGB"), (int(off), 0))
    d = ImageDraw.Draw(canvas, "RGBA")

    def where(k, row):
        """A node sits where the shot it was last read in shows it: the log's column grid, moved by what that shot's
        offset differs from the log's px."""
        s = nodes[k, row]["stage"] if (k, row) in nodes else 0
        return COLX(k) + offsets[s] - logged[s], ROWY[row]

    for (k, row), n in sorted(nodes.items()):
        (x, y), real = where(k, row), fix.get(f"c{k}/{row}")
        notes = [(t, det) for t, det in n["notes"] if not (t == "cost_none" and any(u == "cost_miss" for u, _ in n["notes"]))]
        rings = ([ORANGE if real[0] == "cost" else RED] if real else []) + list(dict.fromkeys(NOTE_COLOUR[t] for t, _ in notes)) or [GREEN]
        for i, col in enumerate(rings):
            e = 52 - 5 * i
            d.rectangle([x - e, y - e, x + e, y + e], outline=col + (255,), width=4)
        cost = n["cost"] if n["cost"] not in (None, "None") else ""
        lines, colours = [n["type"] + (f" {cost}" if cost else "")], [rings[0]]
        for tag, detail in notes:
            lines.append(note_text(tag, detail, n))
            colours.append(NOTE_COLOUR[tag])
        if real and real[0] == "cost":
            lines.append(f"Cost 讀錯：{real[1]}，類型讀對")
            colours.append(ORANGE)
        elif real:
            lines.append(f"讀錯：實為 {real[0]}")
            colours.append(RED)
        label(d, x - 52, y + 54, lines, colours, f)
    for key, real in fix.items():
        if real[0] == "missed":
            k, row = int(key[1:].split("/")[0]), key.split("/")[1]
            x, y = COLX(k), ROWY[row]
            d.rectangle([x - 52, y - 52, x + 52, y + 52], outline=ORANGE + (255,), width=4)
            label(d, x - 52, y + 54, [real[1]], [ORANGE], f)
    for x, y, col, text in items:
        d.rectangle([x, H + y + 3, x + 24, H + y + 27], fill=col)
        d.text((x + 32, H + y), text, font=f, fill=(255, 255, 255))
    banner = f"第 {floor} 層  拖曳 " + drag_banner(drags, offsets, measured)
    if path:
        pts = [BUS] + [where(k, row) for k, (row, _) in enumerate(path[0], 1)]
        d.line(pts, fill=BLUE + (255,), width=8)
        for n, (x, y) in enumerate(pts[1:], 1):
            d.ellipse([x - 66, y - 66, x - 38, y - 38], fill=BLUE + (255,))
            d.text((x - 59, y - 67), str(n), font=fb, fill=(0, 0, 0))
        banner += "  路線：" + " > ".join(f"{r} {t}" for r, t in path[0]) + f"  分數 {path[1]}"
    d.rectangle([0, 0, canvas.width, 34], fill=(0, 0, 0, 200))
    d.text((8, 3), banner, font=f, fill=(255, 255, 255))
    return canvas


def drag_steps(block, stages, drags, path, floor: int, t0: float, t1: float) -> list[dict]:
    t_plan, first = block[-1][0] - 0.3, stages[0].get("t1", block[0][0])
    steps, prev = [{"from": t0, "to": first, "title": f"第 {floor} 層：先讀巴士加 {len(stages[0]['cols'])} 欄"}], first
    for n, (t, px, col) in enumerate(drags):
        nxt = drags[n + 1][0] if n + 1 < len(drags) else t_plan
        steps += [{"from": prev, "to": t, "title": f"拖曳地圖，位移 {px} px"},
                  {"from": t, "to": nxt, "title": f"從第 {col} 欄接著讀，拼成整層"}]
        prev = nxt
    if path:
        steps.append({"from": t_plan, "to": t1, "title": f"規劃路線，分數 {path[1]}：" + " > ".join(f"{r} {t}" for r, t in path[0])})
    return [{**s, "from": hms(s["from"]), "to": hms(s["to"])} for s in steps if s["from"] < s["to"]]


def map_cmd(a) -> None:
    log, out = read_log(a.log), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    block = floor_block(maalc(log), a.floor, secs(a.after) if a.after else None)
    stages, drags, path = parse_map(block)
    nodes, fix = node_table(stages, drags), json.loads(Path(a.fix).read_text(encoding="utf-8")) if a.fix else {}
    footage, masks = Footage(a.video), load_masks(masks_path(a))
    # The floor's first reading (a floor's block opens at `floor N's map is up, floor N+1 next; waiting`, while the
    # last floor's map still shows), then the first after each `dragged` line.
    reads = [next(t for t, x in block if x.startswith(("map: node at", "map: column")))] + [t + 0.1 for t, _, _ in drags]
    times, grays = frames(footage, reads[0] - 0.5, block[-1][0] + 0.5, 10, gray=True)
    idx = pick_shots(times, motion(grays), reads)
    shots = [apply_masks(grab(footage, times[i]), masks) for i in idx]
    for n, im in enumerate(shots):
        im.save(out / ("before-1.png" if n == 0 else f"after-{n}.png"))
    gray = [np.asarray(im.convert("L")) for im in shots]
    slides = [measure_shift(gray[n], gray[n + 1], px) for n, (_, px, _) in enumerate(drags)]
    offsets = list(accumulate((s[0] if s else px for s, (_, px, _) in zip(slides, drags)), initial=0))
    measured = [s and s[0] for s in slides]
    draw_map(shots, offsets, drags, nodes, path, fix, a.floor, measured).save(out / "stitched.png")
    (out / "route.json").write_text(json.dumps({
        "floor": a.floor, "drags": [{"t": hms(t), "px": px, "from_column": c, "measured": m, "score": s and round(s[1], 3)}
                                    for (t, px, c), m, s in zip(drags, measured, slides)],
        "path": path and {"nodes": [" ".join(p) for p in path[0]], "score": path[1]},
        "nodes": [{"column": k, "row": row, **n, "fix": fix.get(f"c{k}/{row}")} for (k, row), n in sorted(nodes.items())],
        "shots": [hms(times[i]) for i in idx]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"floor {a.floor}: {len(nodes)} nodes, {len(drags)} drags -> {out / 'stitched.png'}")
    if a.clip:
        t0, t1 = block[0][0] - 0.5, block[-1][0] + 2.0
        annotated_clip(footage, t0, t1, out / "drag-clip.mp4", touches(log, t0, t1),
                       drag_steps(block, stages, drags, path, a.floor, t0, t1), a)


# --- packs -----------------------------------------------------------------------------------------------

def pack_readings(msgs, floor: int) -> list[dict]:
    """Each `floor N packs` line: its time, threshold, cards [(name, weight, event)] and the pulled card's name."""
    out = []
    for i, (t, x) in enumerate(msgs):
        if m := re.match(rf"floor {floor} packs, threshold (-?\d+): (.*)", x):
            cards = [(c[1], int(c[2]), bool(c[3])) for c in re.finditer(r"(?:^|, )(.+?) \((-?\d+)(, event)?\)(?=,|$)", m[2])]
            pull = next((p for _, y in msgs[i + 1:i + 3] if (p := re.match(rf"floor {floor}: pull (.+) \((-?\d+)", y))), None)
            out.append({"t": t, "threshold": int(m[1]), "cards": cards, "pull": pull and pull[1].strip("'\"")})
    return out


def card_rows(grays) -> list[tuple[float, float]]:
    """(mean brightness, mean abs difference from the frame before) of the card area, rows 150-600."""
    out, prev = [], None
    for g in grays:
        im = np.asarray(g[150:600], np.int16)
        out.append((float(im.mean()), 0.0 if prev is None else float(np.abs(im - prev).mean())))
        prev = im
    return out


EMPTY = 8  # mean brightness of an empty card area: black is 0, the starfield behind the cards 6.7 (floor 1, 2026-10-22)


def settle(rows, k_log: int):
    """(deal frame, settle frame or None, deal before the footage): the deal follows the last empty card area
    before the log line; the cards stand still from the first of 8 frames each under 2 apart."""
    empties = [i for i in range(min(k_log, len(rows) - 1) + 1) if rows[i][0] < EMPTY]
    deal = empties[-1] + 1 if empties else 0
    still = next((i for i in range(deal, len(rows) - 7) if rows[i][0] > 20 and all(rows[j][1] < 2 for j in range(i, i + 8))), None)
    return deal, still, not empties


def centres(n: int) -> list[float]:
    return [640 + (i - (n - 1) / 2) * 210.5 for i in range(n)]


def draw_packs(raw: Image.Image, r: dict, banner: str) -> Image.Image:
    im = raw.copy()
    d, small = ImageDraw.Draw(im, "RGBA"), font(20)
    for x, (name, weight, event) in zip(centres(len(r["cards"])), r["cards"]):
        sel = name == r["pull"]
        col = GREEN if sel else YELLOW
        d.rectangle([x - 105, 180, x + 105, 525], outline=col + (255,), width=8 if sel else 4)
        lines, cur = [], ""
        for word in name.split():
            if cur and d.textlength(f"{cur} {word}", font=small) > 200:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
        lines.append(("★ 選中  " if sel else "") + f"權重 {weight}" + (" (活動)" if event else ""))
        for j, line in enumerate(lines):
            w = d.textlength(line, font=small)
            d.rectangle([x - w / 2 - 3, 596 + j * 26, x + w / 2 + 3, 620 + j * 26], fill=(0, 0, 0, 230))
            d.text((x - w / 2, 596 + j * 26), line, font=small, fill=col)
    d.rectangle([0, 686, W, H], fill=(0, 0, 0, 230))
    d.text((8, 688), banner, font=font(24), fill=(255, 255, 255))
    return im


def packs_cmd(a, fps: int = 30) -> None:
    out, msgs = Path(a.out), maalc(read_log(a.log))
    out.mkdir(parents=True, exist_ok=True)
    footage, masks, res = Footage(a.video), load_masks(masks_path(a)), []
    for k, r in enumerate(pack_readings(msgs, a.floor), 1):
        _, off = footage.locate(r["t"])
        times, grays = frames(footage, max(r["t"] - 10.0, r["t"] - off + 0.2), r["t"] + 3.0, fps, gray=True)
        k_log = min(len(times) - 1, round((r["t"] - times[0]) * fps))
        deal, still, partial = settle(card_rows(grays), k_log)
        raw = apply_masks(grab(footage, times[min(len(times) - 1, (still if still is not None else k_log) + 3)]), masks)
        raw.save(out / f"pack-{k}-raw.png")
        n, dur = len(r["cards"]), None if still is None else round(times[still] - times[deal], 2)
        msg = f"{n} 張卡，影片內沒有量到停住" if dur is None else f"{n} 張卡，發牌到停住 {dur:.1f} 秒" + ("，發牌起點在片段之前" if partial else "")
        draw_packs(raw, r, f"第 {a.floor} 層  第 {k} 次讀取  {msg}  log {hms(r['t'])}").save(out / f"pack-{k}.png")
        res.append({"k": k, "t_log": hms(r["t"]), "threshold": r["threshold"], "cards": r["cards"], "pull": r["pull"],
                    "settle_s": dur, "partial": partial, "log_after_settle_s": None if still is None else round(r["t"] - times[still], 2)})
        print(res[-1])
        if a.clip and still is not None:
            t_deal, t_still = times[deal], times[still]
            t0, t1 = t_deal - 0.8, t_still + 2.2
            steps = [{"from": hms(t0), "to": hms(t_deal), "title": f"第 {a.floor} 層選包頁"},
                     {"from": hms(t_deal), "to": hms(t_still), "title": f"發牌、搖擺：{t_still - t_deal:.1f} 秒"},
                     {"from": hms(t_still), "to": hms(t1), "title": f"卡片停住，log 讀出 {n} 張：選 {r['pull']}"}]
            annotated_clip(footage, t0, t1, out / f"pack-{k}-clip.mp4", {"space": [W, H], "pointer": "none", "events": []}, steps, a)
    (out / "packs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# --- command line ----------------------------------------------------------------------------------------

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    video, masks, annotate = (argparse.ArgumentParser(add_help=False) for _ in range(3))
    video.add_argument("--video", action="append", default=[], help="PATH@START, the wall time of its first frame")
    masks.add_argument("--masks", help="masks.json (default .local/evidence/masks.json)")
    annotate.add_argument("--annotate", type=Path, default=ANNOTATE, help="evidence-annotate's annotate.py")
    for name in ("events", "steps"):
        p = sub.add_parser(name)
        p.add_argument("log")
        p.add_argument("--from", dest="t0", default="00:00:00")
        p.add_argument("--to", dest="t1", default="23:59:59.999")
        p.add_argument("-o", "--out", required=True)
        if name == "steps":
            p.add_argument("--grep", default="")
            p.add_argument("--hold", type=float, default=3.0)
    p = sub.add_parser("frames", parents=[video, masks])
    p.add_argument("times", nargs="+")
    p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("clip", parents=[video])
    p.add_argument("--from", dest="t0", required=True)
    p.add_argument("--to", dest="t1", required=True)
    p.add_argument("-o", "--out", required=True)
    for name in ("map", "packs"):
        p = sub.add_parser(name, parents=[video, masks, annotate])
        p.add_argument("log")
        p.add_argument("--floor", type=int, required=True)
        p.add_argument("-o", "--out", required=True)
        p.add_argument("--clip", action="store_true")
        if name == "map":
            p.add_argument("--after", help="the floor's next reading after this time")
            p.add_argument("--fix", help="FIX.json: misreads judged on the frames")
    p = sub.add_parser("mask", parents=[masks])
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)

    if a.cmd == "events":
        text = Path(a.log).read_text(encoding="utf-8", errors="replace").splitlines()
        if any(line.startswith("[20") for line in text[:50]):
            doc = maafw_events.parse(text)
            doc["events"] = [e for e in doc["events"] if secs(a.t0) <= secs(e["t"]) <= secs(a.t1)]
        else:
            doc = touches(parse_log(text), secs(a.t0), secs(a.t1))
        Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"{len(doc['events'])} events -> {a.out}")
    elif a.cmd == "steps":
        steps = captions(read_log(a.log), secs(a.t0), secs(a.t1), a.grep, a.hold)
        Path(a.out).write_text(json.dumps(steps, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(steps)} steps -> {a.out}")
    elif a.cmd == "frames":
        Path(a.out).mkdir(parents=True, exist_ok=True)
        footage, found = Footage(a.video), load_masks(masks_path(a))
        for t in a.times:
            f = Path(a.out) / f"{hms(secs(t)).replace(':', '-')}.png"
            apply_masks(grab(footage, secs(t)), found).save(f)
            print(f)
    elif a.cmd == "clip":
        if local_dir().resolve() not in Path(a.out).resolve().parents:
            sys.exit(f"{a.out}: a cut is unmasked, so it goes under .local/ (annotate.py masks it on the way out)")
        cut(Footage(a.video), secs(a.t0), secs(a.t1), a.out)
    elif a.cmd == "map":
        map_cmd(a)
    elif a.cmd == "packs":
        packs_cmd(a)
    elif a.cmd == "mask":
        masks = load_masks(masks_path(a))
        for f in a.images:
            apply_masks(Image.open(f).convert("RGB"), masks).save(f)
            print("masked", f)


if __name__ == "__main__":
    main()
