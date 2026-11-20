"""Evidence of a live run from the bot's log and the recording: events, captions, frames, clips, the map and pack pages.

    uv run --group probe python tools/live/evidence.py <command> ...

  events LOG [--from T --to T] -o events.json      taps and swipes, for evidence-annotate's --events
  steps  LOG [--from T --to T] [--grep RE] [--hold S] -o steps.json   caption drafts: the log lines in `note`
  frames --video V@START... -o DIR T [T ...]       one PNG per wall time, named HH-MM-SS.fff.png
  clip   --video V@START... --from T --to T -o OUT.mp4   a constant-frame-rate cut
  clips  SPEC.json -o DIR [NAME ...]                annotated clips of a run's checks, one per SPEC entry
  map    LOG --video V@START... --floor N -o DIR [--after T] [--fix FIX.json] [--clip]
  packs  LOG --video V@START... --floor N -o DIR [--clip]
  mask   IMG [IMG ...] [--box X,Y,W,H ...]         black out the identity regions (and each box), in place

LOG is the bot's stdout with a wall time on each line, as `tools/live/bot.py run` writes it
(`HH:MM:SS.fff <line>`; MXU's `YYYY-MM-DD HH:MM:SS [stdout] <line>` reads too). `events` also takes a
maafw.log (through `maafw_events.py`, in game pixels); from LOG it takes the controller's
`x: X, y: Y, width: W, height: H` lines, in device pixels, and a burst under 0.25 s apart is one swipe.
`steps` writes one draft per moment: the `[maalc]` lines less than --hold s (default 3, the shortest a caption
stays up) after the moment's first line go in its `note`, and its `title` stays empty for you to write in
Chinese; `reel.py` refuses a draft left unwritten. Every time T is wall clock, `HH:MM:SS[.fff]`, of the log's day. `--video PATH@START` is a recording and the
wall time of its first frame (screen-record's `started`); give one per piece of a run recorded in pieces.

**map** stitches the floor from the frames before and after each `map: dragged the map N px` and boxes every
node the bot read, at its column and row: green read right, red a wrong type, orange a wrong Cost or a node
the bot did not list (from FIX). Under each box hangs its label, the type and its route weight (map_weights.yaml,
for the difficulty the bot logged for the floor, else told by the Costs read), and a line per note. Reads that took more than the marks have their own
colour and line: violet a type corrected once the map was dragged near (with the first read), magenta a Cost that
read no number or missed, white a boss told by its Cost, cyan a boss told by its red glow or by the shop before it;
a legend under the picture lists the colours it uses. The route is numbered, and the header line has its steps,
their weights summed to its score, and the drags and nodes read. Each shot is the still map the bot read (the still stretch of the footage around
the read, never a motion run: a drag back is not a drag), and the shots are laid side by side by the slide
measured between them on the frames (template match), the log's px where none matches. FIX is what you judged on the frames:
`{"c4/down": ["risky"], "c2/mid": ["cost", "<what it read and what the screen shows>"], "c3/up": ["missed", "<label>"]}`.
`--after T` takes the floor's next reading after T (a restart re-reads the map). Writes stitched.png,
before-1.png, after-N.png, route.json; `--clip` adds drag-clip.mp4 (read, drag, read on, plan, with the touches).

**packs** writes one still per `floor N packs` reading (refreshes included): each card's name and weight, the
pulled card's thick border, and how long the cards took from the deal (card area empty: mean under 8) to standing still
(mean frame difference under 2 for 8 frames at 30 fps), measured on the video. Writes pack-K.png,
pack-K-raw.png, packs.json; `--clip` adds pack-K-clip.mp4.

**clips** writes DIR/NAME.mp4 for each clip of SPEC (all of them without NAMEs), through evidence-annotate:
`{"video": "rec.mp4@14:53:15.595", "color": "#F0A830", "clips": {"c3-stop": {"from": T, "to": T, "log": "run.log",
"idle": 4, "boxes": [[X, Y, W, H]], "steps": [{"from": T, "to": T, "title": "...", "tag": "結果"}]}}}`.
A clip's `video` overrides the spec's (a list for a run recorded in pieces); paths are relative to SPEC. `log` (a
run log of the recording's device) adds its touches, so give it only for the emulator's recording; a clip without one
shows no pointer. `idle` N plays the quiet stretches N times faster. `boxes` are blacked out for the whole clip, in
the 1280x720 space of `frames` (the settings window's local paths: the header, the run log's start line, the MuMu
fields); the identity masks apply as everywhere.

Stills and the clips of map, packs and clips are masked with `--masks` (default `.local/evidence/masks.json`);
those clips go through evidence-annotate's annotate.py (`--annotate`, default its global skill folder).
`clip` is a raw cut for annotate.py, unmasked: it stays in `.local/` until annotate.py has masked it. `mask --box`
also blacks out a box in the image's own pixels (a local path on a still of the settings window).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
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
FONTS = {False: ["C:/Windows/Fonts/msjh.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],  # bold: lists
         True: ["C:/Windows/Fonts/msjhbd.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]}
W, H = 1280, 720  # frames are scaled to the game's own 720p grid
GREEN, RED, ORANGE, YELLOW, GREY, BLUE = (60, 220, 60), (255, 60, 60), (255, 160, 0), (255, 220, 0), (170, 170, 170), (90, 200, 255)
VIOLET, MAGENTA, WHITE, CYAN = (170, 110, 255), (255, 70, 200), (245, 245, 245), (0, 225, 225)


def secs(hms: str) -> float:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


hms = maafw_events.clock  # seconds since midnight -> HH:MM:SS.fff


def parse_log(lines) -> list[tuple[float, str]]:
    """[(wall seconds since midnight, text)] of every stamped line."""
    # ponytail: a run across midnight wraps to 0; add the date when one does
    return [(maafw_events.seconds(m), m[4]) for m in map(STAMP.match, lines) if m]


def read_log(path) -> list[tuple[float, str]]:
    return parse_log(Path(path).read_text(encoding="utf-8", errors="replace").splitlines())


def maalc(log) -> list[tuple[float, str]]:
    return [(t, x[8:]) for t, x in log if x.startswith("[maalc] ")]


def font(size: int, bold: bool = False):
    for f in FONTS[bold]:
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
    """Caption drafts for the `[maalc]` lines in [t0, t1] matching grep: lines less than hold s after a draft's first line
    join it, and a draft lasts until hold s after its last line or the next draft. The lines go in `note`; `title`
    stays empty, for a person to write."""
    groups = []
    for t, x in maalc(log):
        if t0 <= t <= t1 and re.search(grep, x):
            if groups and t - groups[-1][0][0] < hold:
                groups[-1].append((t, x))
            else:
                groups.append([(t, x)])
    starts = [g[0][0] for g in groups[1:]] + [t1]
    return [{"from": hms(g[0][0]), "to": hms(min(nxt, g[-1][0] + hold, t1)), "title": "", "note": "\n".join(x for _, x in g)}
            for g, nxt in zip(groups, starts)]


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


def box_filter(boxes) -> list[str]:
    """ffmpeg's -vf that blacks out each [x, y, w, h] of the 1280x720 frame space, at any frame size; [] for none."""
    if not boxes:
        return []
    return ["-vf", ",".join(f"drawbox=x=iw*{x}/{W}:y=ih*{y}/{H}:w=iw*{w}/{W}:h=ih*{h}/{H}:color=black:t=fill" for x, y, w, h in boxes)]


def cut(footage: Footage, t0: float, t1: float, out, boxes=()) -> None:
    """A constant-frame-rate cut of [t0, t1] with each box blacked out: annotate.py turns pieces with uneven timestamps into one frame."""
    path, off = footage.locate(t0)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(path), *box_filter(boxes),
                    "-r", "30", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], check=True)


def annotated_clip(footage: Footage, t0: float, t1: float, out: Path, events: dict, steps: list, a, blocks: dict | None = None,
                   boxes=(), extra=()) -> None:
    """Cut [t0, t1] with each box blacked out, and burn events, steps, masks and any blocks (evidence-annotate's blocks.json)
    into it with evidence-annotate; extra: more of annotate.py's options."""
    stem = out.with_suffix("")
    files = {k: Path(f"{stem}-{k}.json") for k in ("events", "steps", "blocks")}
    files["events"].write_text(json.dumps(events, indent=1), encoding="utf-8")
    files["steps"].write_text(json.dumps(steps, ensure_ascii=False, indent=1), encoding="utf-8")
    if blocks:
        files["blocks"].write_text(json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8")
    raw = local_dir("scratch") / f"cut-{os.getpid()}-{out.stem}.mp4"  # unmasked: never beside out, which may be shared
    try:
        cut(footage, t0, t1, raw, boxes)
        subprocess.run(["uv", "run", str(a.annotate), str(raw), "-o", str(out), "--start", hms(t0), "--events", str(files["events"]),
                        "--steps", str(files["steps"]), "--masks", str(masks_path(a)),
                        *(["--blocks", str(files["blocks"])] if blocks else []), *extra], check=True)
    finally:
        raw.unlink(missing_ok=True)


# --- the clips of a run's checks -------------------------------------------------------------------------

CLIP_KEYS = {"from", "to", "log", "idle", "boxes", "steps", "video"}


def read_spec(path: Path) -> dict:
    """clips' SPEC, checked, its paths made absolute: {name: {footage, t0, t1, log, idle, boxes, steps, color}}."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    def videos(v, name):
        specs = [v] if isinstance(v, str) else v
        if not specs or not isinstance(specs, list) or not all(isinstance(x, str) and "@" in x for x in specs):
            sys.exit(f"{path}: clip {name}: video takes PATH@START or a list of them")
        return [f"{base / x.rsplit('@', 1)[0]}@{x.rsplit('@', 1)[1]}" for x in specs]

    if not isinstance(doc.get("clips"), dict) or not doc["clips"]:
        sys.exit(f"{path}: no clips")
    out = {}
    for name, c in doc["clips"].items():
        if not re.fullmatch(r"[\w.-]+", name):
            sys.exit(f"{path}: clip name {name!r}: letters, digits, _ . - only (it names the file)")
        if unknown := set(c) - CLIP_KEYS:
            sys.exit(f"{path}: clip {name}: unknown keys {sorted(unknown)}")
        if not ("from" in c and "to" in c and secs(c["from"]) < secs(c["to"])):
            sys.exit(f"{path}: clip {name}: needs from and to, from first")
        for b in c.get("boxes", []):
            if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
                sys.exit(f"{path}: clip {name}: a box is [x, y, w, h], not {b!r}")
        steps = [dict(s) for s in c.get("steps", [])]
        for s in steps:
            if not (s.get("title") and "from" in s and "to" in s):
                sys.exit(f"{path}: clip {name}: each step needs from, to and a title")
        out[name] = {"footage": videos(c.get("video", doc.get("video")), name), "t0": secs(c["from"]), "t1": secs(c["to"]),
                     "log": base / c["log"] if c.get("log") else None, "idle": int(c.get("idle", 0)),
                     "boxes": c.get("boxes", []), "steps": steps, "color": doc.get("color")}
    return out


def clip_events(clip: dict) -> dict:
    """A clip's events.json: its log's touches, or none (no pointer), in the spec's colour when it names one."""
    events = touches(read_log(clip["log"]), clip["t0"], clip["t1"]) if clip["log"] else {"space": [W, H], "pointer": "none", "events": []}
    if clip["color"]:
        events["style"] = {**events.get("style", {}), "color": clip["color"]}
    return events


def clips_cmd(a) -> int:
    spec = read_spec(Path(a.spec))
    if missing := [n for n in a.names if n not in spec]:
        sys.exit(f"no clip {', '.join(missing)} in {a.spec}: {', '.join(spec)}")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in a.names or list(spec):
        c = spec[name]
        extra = ["--idle-speed", str(c["idle"]), "--idle-after", "6"] if c["idle"] > 1 else []
        out = Path(a.out) / f"{name}.mp4"
        try:
            annotated_clip(Footage(c["footage"]), c["t0"], c["t1"], out, clip_events(c), c["steps"], a, boxes=c["boxes"], extra=extra)
            print(f"{name} -> {out}")
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"{name}: failed ({e})", file=sys.stderr)
    return 1 if failed else 0


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


# --- command line ----------------------------------------------------------------------------------------

def box_arg(text: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4 or not all(p.isdigit() for p in parts) or int(parts[2]) < 1 or int(parts[3]) < 1:
        raise argparse.ArgumentTypeError(f"{text!r}: a box is X,Y,W,H in whole pixels, W and H at least 1")
    x, y, w, h = map(int, parts)
    return x, y, w, h


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
            p.add_argument("--hold", type=float, default=3.0, help="lines this many s after a draft's first line join it, "
                           "and a draft lasts this long after its last line")
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
    p = sub.add_parser("clips", parents=[masks, annotate])
    p.add_argument("spec")
    p.add_argument("names", nargs="*")
    p.add_argument("-o", "--out", required=True)
    p = sub.add_parser("mask", parents=[masks])
    p.add_argument("images", nargs="+")
    p.add_argument("--box", action="append", default=[], type=box_arg, help="X,Y,W,H in the image's pixels; again for more")
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
        from live import evidence_map  # here, not at the top: it imports this module

        evidence_map.map_cmd(a)
    elif a.cmd == "packs":
        from live import evidence_packs  # as evidence_map

        evidence_packs.packs_cmd(a)
    elif a.cmd == "clips":
        sys.exit(clips_cmd(a))
    elif a.cmd == "mask":
        masks = load_masks(masks_path(a))
        for f in a.images:
            im = apply_masks(Image.open(f).convert("RGB"), masks)
            for x, y, w, h in a.box:
                ImageDraw.Draw(im).rectangle([x, y, x + w - 1, y + h - 1], fill=(0, 0, 0))
            im.save(f)
            print("masked", f, *(f"box {x},{y},{w},{h}" for x, y, w, h in a.box))


if __name__ == "__main__":
    main()
