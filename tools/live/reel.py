"""The review reel: annotated clips of live tests strung together by chapter, one chapter per issue.

    uv run --group probe python tools/live/reel.py check REEL.json
    uv run --group probe python tools/live/reel.py build REEL.json
    uv run --group probe python tools/live/reel.py sheet --video V@START --from T --to T [--every S] -o OUT.png

REEL.json, paths relative to its folder or absolute, times wall clock `HH:MM:SS[.fff]`:

    {"title": "...", "chapters": [{"issue": "#94", "line": "one line on what to watch", "short"?: "...", "note"?: "...",
      "clips": [{"video": "rec.mp4", "start": "<wall time of its first frame>", "from": T, "to": T,
                 "events": "events.json", "steps": "steps.json", "box_space"?: [1280, 720],
                 "speed"?: [[T, T, 4]], "freeze"?: [[T, 2.0]]},
                {"image": "gui.png", "caption": "...", "seconds"?: 4}]}]}

`box_space` is the grid the steps' boxes and zoom are written in ([1920, 1080] for a touch log, [1280, 720] for
game pixels); a clip with a box or a zoom must name it, and the boxes are drawn on the events' grid from it.

A clip is rendered from the uncut recording with evidence-annotate (`evidence.py`'s `annotated_clip`, masks
included) into `clips/` beside REEL.json, again only when one of its inputs, the masks or annotate.py changed. `speed` plays a stretch
faster (4) or slower (0.5), `freeze` holds the frame at T for that many seconds; evidence-annotate's bottom-left
corner marks each beside its clock ("快轉 4×", "慢放 0.5×", "停格"). The reel is 1280x776: a 56 px chapter strip above the 1280x720 picture, so
the strip never hides game UI. It shows the chapter (its number, issue, line) at every moment after the opening
list, which fills the whole frame and gives each chapter's start time; the MP4 carries a chapter mark per chapter. Writes reel.mp4,
chapters.md and stills/NN.png (the reel at the middle of each caption) beside REEL.json.

`check`, and `build` before it builds, check every chapter against docs/agents/evidence-style.md ("Clips and stills
in general", "Review reel") and refuse, listing each problem: an unwritten draft (an empty title, as `evidence.py
steps` writes it), a caption or a step `tag` with no Chinese character, a caption on screen shorter than
max(3 s, characters / 5) with the tag's characters counted,
overlapping captions or speed stretches, boxes with no `box_space`, a box outside its `box_space`. They warn about
a caption that reads like log text or a code name outside 「」, and about a title that opens with 改前： or 改後：,
which goes in the step's `tag` instead (evidence-annotate shows the tag in place of the step number).

`sheet` lays out the frames of a recording from T to T, one every S seconds (default 2), each labelled with its wall
time and masked, to find the moments before writing the steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from live import evidence  # noqa: E402
from live.evidence import H, W, hms, secs  # noqa: E402
from local_dir import local_dir  # noqa: E402

BAND, FPS = 56, 30
OPENING_S = 10.0  # the opening list is a table of contents to pause on; the chapter marks are for jumping
FONTS = {False: evidence.FONTS, True: ["C:/Windows/Fonts/msjhbd.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]}
AMBER, WHITE, DIM, BG = (255, 196, 64), (245, 245, 245), (190, 194, 204), (17, 19, 26)
AMBER_HEX = "#ffc440"  # AMBER, as evidence-annotate's own accent (scripts/text.py ACCENT)
CORNER_TEXT = "#e6e6e6e6"  # evidence-annotate's corner text (scripts/text.py CORNER), for the dot before a mark
ANNOTATE_FADE_S = 0.35  # evidence-annotate fades a block in and out over this (scripts/text.py FADE_S)
# A mark's padding, from evidence-annotate's scripts/text.py with style.corner left at its size, 13 px: a block's default
# pad is (0.62, 0.27) x size, so 3.5 px keeps the corner's height; beside the corner (its 8 px right pad, SIDE_GAP 6 px)
# 4 px of left pad makes the gap about as wide as the corner's own "  ·  ".
MARK_PAD = [4, 3.5]
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]

@dataclass
class Report:
    problems: list[str]
    warnings: list[str]


HAN = re.compile(r"[\u3400-\u9fff]")
QUOTED = re.compile(r"「[^」]*」")
CODE = re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+"  # snake_case
                  r"|[A-Za-z_][A-Za-z0-9_]*(?:=|\(\))"  # key=value, call()
                  r"|\b[a-z]+\.[a-z_]{2,}\b"  # dotted.name
                  r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){2,}")  # MirrorEntryPaused, GiveUpRewards


def min_seconds(text: str) -> float:
    """How long a caption stays up at least: 3 s, or a second per five characters (spaces not counted)."""
    return max(3.0, len(re.sub(r"\s", "", text)) / 5)


SIDE = re.compile(r"^\s*(改前|改後)\s*[：:]")  # a before/after side written into the title


def caption_text(text: str, where: str, report: Report) -> None:
    """A caption with no Chinese character is a problem; one that reads like log text outside 「」, a warning."""
    if not HAN.search(text):
        report.problems.append(f"{where}: has no Chinese character")
    if m := CODE.search(QUOTED.sub("", text)):
        report.warnings.append(f"{where}: reads like log text or a code name ({m[0]}); a game label goes in 「」")


# --- the model -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Timeline:
    """A cut [t0, t1] of a recording as the reel plays it: stretches played at another speed, frames held."""
    t0: float
    t1: float
    speed: tuple[tuple[float, float, float], ...] = ()  # (from, to, factor): 4 plays four times faster
    freeze: tuple[tuple[float, float], ...] = ()  # (at, seconds)

    def screen(self, t: float) -> float:
        """Seconds into the played clip at which wall time t shows (a frame held at t shows after its hold)."""
        t = min(max(t, self.t0), self.t1)
        s = t - self.t0
        for a, b, x in self.speed:
            s += max(0.0, min(b, t) - max(a, self.t0)) * (1 / x - 1)
        return s + sum(sec for at, sec in self.freeze if at < t)

    @property
    def length(self) -> float:
        return self.screen(self.t1) + sum(sec for at, sec in self.freeze if at == self.t1)

    def factor(self, t: float) -> float:
        return next((x for a, b, x in self.speed if a <= t < b), 1.0)

    def held(self, at: float) -> float:
        """The recording's time of the frame a freeze at `at` holds: the nearest frame, the cut's last at most."""
        return self.t0 + min(round((at - self.t0) * FPS), round((self.t1 - self.t0) * FPS) - 1) / FPS

    def corner_blocks(self) -> dict:
        """evidence-annotate's blocks.json: each stretch not at normal speed marked beside the clock in its bottom-left
        corner, on the recording's clock. A block fades in and out, and one fading takes its place in the row while
        faint, so every held frame shows its marks fully: the freeze's own centred on it, a speed mark whose edge is
        less than a fade away from it pushed out past it."""
        fade = ANNOTATE_FADE_S + 0.002  # the times are written to the millisecond
        held = [self.held(at) for at, _ in self.freeze]

        def mark(a: float, b: float, text: str) -> dict:
            return {"from": hms(a), "to": hms(b), "at": "bottom-left", "beside": True, "read": False, "sep": "  ", "pad": MARK_PAD,
                    "lines": [[{"text": "·", "color": CORNER_TEXT}, {"text": text, "color": AMBER_HEX}]]}

        def stretch(a: float, b: float, x: float) -> dict:
            a = min([a] + [h - fade for h in held if a <= h < a + fade])
            b = max([b] + [h + fade for h in held if b - fade < h <= b])
            return mark(a, b, f"快轉 {x:g}×" if x > 1 else f"慢放 {x:g}×")

        return {"blocks": [stretch(*s) for s in self.speed] + [mark(h - fade, h + fade, "停格") for h in held]}

    def pieces(self) -> list[tuple]:
        """("play", a, b, factor) and ("hold", at, seconds) in wall order, covering [t0, t1]."""
        cuts = sorted({self.t0, self.t1, *(v for a, b, _ in self.speed for v in (a, b)), *(at for at, _ in self.freeze)})
        cuts = [c for c in cuts if self.t0 <= c <= self.t1]
        out = []
        for p, q in zip(cuts, cuts[1:] + [None]):
            out += [("hold", at, sec) for at, sec in sorted(self.freeze) if at == p]
            if q is not None:
                out.append(("play", p, q, self.factor(p)))
        return out


@dataclass(frozen=True)
class Step:
    start: float
    end: float
    title: str
    boxes: tuple
    zoom: tuple
    note: str
    tag: str = ""  # evidence-annotate shows it in place of the step number: 改前, 改後


@dataclass(frozen=True)
class Clip:
    video: Path
    first_frame: str  # wall time of the recording's first frame
    timeline: Timeline
    events: Path
    steps_file: Path
    space: tuple[int, int]
    steps: tuple[Step, ...]
    raw_steps: tuple[dict, ...]  # as the steps file holds them
    box_space: tuple[int, int] | None

    def annotation_steps(self) -> list[dict]:
        """The steps as evidence-annotate gets them: boxes and zoom moved from `box_space` onto the events' grid."""
        if not self.box_space:
            return [dict(s) for s in self.raw_steps]
        sx, sy = self.space[0] / self.box_space[0], self.space[1] / self.box_space[1]
        scale = lambda x, y, w, h: [x * sx, y * sy, w * sx, h * sy]  # noqa: E731
        out = []
        for s in self.raw_steps:
            s = dict(s)
            if s.get("boxes"):
                s["boxes"] = [scale(*b[:4]) + list(b[4:]) for b in s["boxes"]]
            if s.get("zoom"):
                s["zoom"] = scale(*s["zoom"])
            out.append(s)
        return out


@dataclass(frozen=True)
class Still:
    image: Path
    caption: str
    seconds: float


@dataclass(frozen=True)
class Chapter:
    issue: str
    line: str
    short: str
    note: str
    clips: tuple  # of Clip and Still


@dataclass(frozen=True)
class Reel:
    title: str
    folder: Path
    chapters: tuple[Chapter, ...]

    def label(self, n: int) -> str:
        return f"chapter {n} {self.chapters[n - 1].issue}"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load(path: Path) -> Reel:
    path = Path(path)
    folder = path.parent
    at = lambda p: (folder / p).resolve()  # noqa: E731  an absolute p stays as it is
    doc = read_json(path)
    chapters = []
    for c in doc["chapters"]:
        clips = []
        for p in c["clips"]:
            if "image" in p:
                clips.append(Still(at(p["image"]), p["caption"], float(p.get("seconds", max(4.0, min_seconds(p["caption"]))))))
                continue
            events, steps_file = at(p["events"]), at(p["steps"])
            space = tuple(int(v) for v in read_json(events)["space"])
            raw = tuple(read_json(steps_file))
            steps = tuple(Step(secs(s["from"]), secs(s["to"]), s["title"], tuple(tuple(b) for b in s.get("boxes", ())),
                               tuple(s.get("zoom") or ()), s.get("note", ""), s.get("tag", "")) for s in raw)
            box_space = tuple(p["box_space"]) if isinstance(p.get("box_space"), list) else p.get("box_space")
            timeline = Timeline(secs(p["from"]), secs(p["to"]), tuple((secs(a), secs(b), float(x)) for a, b, x in p.get("speed", ())),
                                tuple((secs(t), float(s)) for t, s in p.get("freeze", ())))
            clips.append(Clip(at(p["video"]), p["start"], timeline, events, steps_file, space, steps, raw, box_space))
        chapters.append(Chapter(c["issue"], c["line"], c.get("short", c["line"]), c.get("note", ""), tuple(clips)))
    return Reel(doc.get("title", "驗收總集"), folder, tuple(chapters))


def check_clip(clip: Clip, where: str, report: Report) -> None:
    tl = clip.timeline
    before = len(report.problems)
    for i, (a, b, x) in enumerate(sorted(tl.speed)):
        if not (tl.t0 <= a < b <= tl.t1) or x <= 0:
            report.problems.append(f"{where}: speed {hms(a)}-{hms(b)} x{x:g} is not a stretch of the cut {hms(tl.t0)}-{hms(tl.t1)}")
        if i and a < sorted(tl.speed)[i - 1][1]:
            report.problems.append(f"{where}: speed {hms(a)}-{hms(b)} overlaps the stretch before it")
    for at, sec in tl.freeze:
        if not tl.t0 <= at <= tl.t1 or sec <= 0:
            report.problems.append(f"{where}: freeze at {hms(at)} for {sec:g} s is outside the cut {hms(tl.t0)}-{hms(tl.t1)}")
    timed = len(report.problems) == before  # a broken timeline gives no screen times
    grid = clip.box_space
    if grid is not None and not (isinstance(grid, tuple) and len(grid) == 2 and all(isinstance(v, int) and v > 0 for v in grid)):
        report.problems.append(f"{where}: box_space {grid!r} is not [width, height] in pixels")
        grid = None
    elif not grid and any(s.boxes or s.zoom for s in clip.steps):
        report.problems.append(f"{where}: has boxes but no box_space: name the grid they are written in, "
                               f"[1920, 1080] for a touch log or [1280, 720] for game pixels")
    for i, s in enumerate(clip.steps, 1):
        name = f"{where}, step {i} {s.title!r}"
        if s.title.strip():
            caption_text(s.title, name, report)
            if m := SIDE.match(s.title):
                report.warnings.append(f"{name}: opens with {m[1]}; put it in the step's tag (\"tag\": \"{m[1]}\")")
        else:
            report.problems.append(f"{where}, step {i}: an unwritten draft (the log lines evidence.py steps put in its note: "
                                   f"{s.note!r}); write the caption")
        if s.tag:
            caption_text(s.tag, f"{name}, tag {s.tag!r}", report)
        if i > 1 and s.start < clip.steps[i - 2].end:
            report.problems.append(f"{name}: overlaps step {i - 1} (from {hms(s.start)} before its end {hms(clip.steps[i - 2].end)})")
        shown, need = (tl.screen(s.end) - tl.screen(s.start), min_seconds(s.tag + s.title)) if timed else (math.inf, 0)
        if shown < need - 1e-6:
            report.problems.append(f"{name}: shown {shown:.1f} s, needs {need:.1f} s (3 s or a second per 5 characters)")
        if grid:
            gw, gh = grid
            for x, y, w, h, *_ in s.boxes + ((s.zoom,) if s.zoom else ()):
                if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > gw or y + h > gh:
                    report.problems.append(f"{name}: box {[x, y, w, h]} is outside its box_space {gw}x{gh}")


def check(path) -> Report:
    return audit(load(Path(path)))


def audit(reel: Reel) -> Report:
    report = Report([], [])
    for n, c in enumerate(reel.chapters, 1):
        caption_text(c.line, f"{reel.label(n)}: line {c.line!r}", report)
        for p in c.clips:
            if isinstance(p, Still):
                where = f"{reel.label(n)}, still {p.image.name} {p.caption!r}"
                caption_text(p.caption, where, report)
                if p.seconds < min_seconds(p.caption):
                    report.problems.append(f"{where}: shown {p.seconds:.1f} s, needs {min_seconds(p.caption):.1f} s")
            else:
                check_clip(p, f"{reel.label(n)}, {p.steps_file.name}", report)
    return report


# --- the build -------------------------------------------------------------------------------------------

def font(size: int, bold: bool = False):
    for f in FONTS[bold]:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def run(cmd: list) -> None:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))[:400]}\n{r.stderr[-2000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def clock(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def chapter_label(n: int) -> str:
    """A chapter as the strip, its card, the opening list and the chapter marks name it: `08`."""
    return f"{n:02d}"


def fit(d, text: str, f, width: float) -> str:
    """text, cut with an ellipsis to `width` px."""
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text + "…"


def band(n: int, issue: str, line: str) -> Image.Image:
    """The chapter strip: the chapter's number in amber, the issue, the line."""
    im = Image.new("RGB", (W, BAND), BG)
    d = ImageDraw.Draw(im)
    x, cy = 20, BAND // 2
    for text, f, colour in ((chapter_label(n), font(26, True), AMBER), (issue, font(24, True), WHITE), (line, font(22), DIM)):
        text = fit(d, text, f, W - 20 - x)
        d.text((x, cy), text, font=f, fill=colour, anchor="lm")
        x += d.textlength(text, font=f) + 22
    d.line([(0, BAND - 1), (W, BAND - 1)], fill=(60, 64, 76))
    return im


def wrap(d, text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) > width:
            lines.append(cur)
            cur = ""
        cur += ch
    return lines + [cur]


def still_frame(lines: list[tuple[str, int, bool, tuple]], image: Path | None = None, masks=None) -> Image.Image:
    """A 1280x720 frame: an image fitted above, or nothing, and centred lines of (text, size, bold, colour) below."""
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    top = 0
    if image:
        shot = evidence.apply_masks(Image.open(image).convert("RGB"), masks) if masks else Image.open(image).convert("RGB")
        shot.thumbnail((W, H - 90))
        im.paste(shot, ((W - shot.width) // 2, (H - 90 - shot.height) // 2))
        top = H - 80
    rows = [(r, f, c) for text, size, bold, c in lines for f in [font(size, bold)] for r in wrap(d, text, f, W - 120)]
    y = top or (H - sum(f.size + 18 for _, f, _ in rows)) // 2
    for r, f, c in rows:
        d.text((W // 2, y + f.size // 2), r, font=f, fill=c, anchor="mm")
        y += f.size + 18
    return im


def opening_frame(title: str, chapters: tuple[Chapter, ...], starts: list[float]) -> Image.Image:
    """The opening list over the whole 1280x776 frame, no strip above it: each chapter's number, start time and name."""
    im = Image.new("RGB", (W, H + BAND), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((W // 2, 56), title, font=font(40, True), fill=WHITE, anchor="mm")
    d.text((W // 2, 104), f"{len(chapters)} 章，每章的開始時間如下；播放器也可跳章", font=font(22), fill=DIM, anchor="mm")
    rows = math.ceil(len(chapters) / 2)
    step = min(48, (H + BAND - 170) // max(rows, 1))
    f, fb = font(min(24, step - 14)), font(min(24, step - 14), True)
    for i, (c, t) in enumerate(zip(chapters, starts)):
        x, y = 60 + (i // rows) * 620, 150 + (i % rows) * step
        d.text((x, y), chapter_label(i + 1), font=fb, fill=AMBER)
        d.text((x + 44, y), clock(t), font=fb, fill=WHITE)
        d.text((x + 130, y), c.short, font=f, fill=DIM)
    return im


def chapter_marks(chapters: tuple[Chapter, ...], starts: list[float], lengths: list[float]) -> list[tuple[float, float, str]]:
    """The MP4's chapter marks, (from, to, title) in seconds: the opening list, then each chapter by its number."""
    return [(0.0, OPENING_S, "目錄")] + [(t, t + d, f"{chapter_label(n)} {c.issue} {c.line}")
                                         for n, (c, t, d) in enumerate(zip(chapters, starts, lengths), 1)]


class Builder:
    def __init__(self, reel: Reel):
        self.reel, self.total = reel, len(reel.chapters)
        self.work = local_dir("scratch", "reel", reel.folder.name)
        self.clips = reel.folder / "clips"
        self.clips.mkdir(exist_ok=True)
        self.masks = evidence.load_masks(evidence.masks_path(SimpleNamespace(masks=None)))
        self.n = 0

    def file(self, suffix: str) -> Path:
        self.n += 1
        return self.work / f"{self.n:03d}{suffix}"

    def segment(self, picture: list, filters: str, strip: Image.Image | None, out: Path) -> Path:
        """Encode `picture` (ffmpeg input args, 1280x720 or the whole 1280x776 after `filters`) at the bottom of the
        frame, the strip, if any, over the top."""
        inputs, graph, last = list(picture), [f"[0:v]{filters},pad={W}:{H + BAND}:0:oh-ih[v0]"], "v0"
        if strip:
            png = self.file(".png")
            strip.save(png)
            inputs += ["-i", png]
            graph.append("[v0][1:v]overlay=0:0[v1]")
            last = "v1"
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", *ENC, out])
        return out

    def picture(self, im: Image.Image, seconds: float, strip: Image.Image | None) -> Path:
        png = self.file(".png")
        im.save(png)
        return self.segment(["-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.3f}", "-i", png], "setsar=1,format=yuv420p",
                            strip, self.file(".mp4"))

    def render(self, clip: Clip, out: Path) -> None:
        """Annotate the cut from the uncut recording, unless the clip, its inputs, the masks and annotate.py are what
        made `out` last time."""
        tl = clip.timeline
        masks = evidence.masks_path(SimpleNamespace(masks=None))
        files = [clip.video, evidence.ANNOTATE, *sorted(masks.parent.glob("*.png"))]
        steps, blocks = clip.annotation_steps(), tl.corner_blocks()
        key = hashlib.sha256(json.dumps([[str(f), f.stat().st_size, f.stat().st_mtime] for f in files] + [
            clip.first_frame, tl.t0, tl.t1, masks.read_text(encoding="utf-8"), clip.events.read_text(encoding="utf-8"),
            steps, blocks], ensure_ascii=False).encode()).hexdigest()
        stamp = out.with_suffix(".key")
        if out.exists() and stamp.exists() and stamp.read_text() == key:
            return
        events = read_json(clip.events)
        footage = evidence.Footage([f"{clip.video}@{clip.first_frame}"])
        evidence.annotated_clip(footage, tl.t0, tl.t1, out, events, steps, SimpleNamespace(annotate=evidence.ANNOTATE, masks=None),
                                blocks)
        stamp.write_text(key)

    def timed(self, clip: Clip, src: Path, n: int, c: Chapter) -> Path:
        """The annotated clip played by its timeline, under the strip."""
        tl, parts, graph = clip.timeline, [], []
        pieces = tl.pieces()
        for i, p in enumerate(pieces):
            if p[0] == "play":
                _, a, b, x = p
                graph.append(f"[s{i}]trim=start={a - tl.t0:.3f}:end={b - tl.t0:.3f},setpts=(PTS-STARTPTS)/{x:g}[p{i}]")
            else:
                _, at, sec = p
                k = round((tl.held(at) - tl.t0) * FPS)
                graph.append(f"[s{i}]trim=start_frame={k}:end_frame={k + 1},setpts=PTS-STARTPTS,"
                             f"tpad=stop_mode=clone:stop_duration={sec:.3f}[p{i}]")
            parts.append(f"[p{i}]")
        split = f"split={len(pieces)}" + "".join(f"[s{i}]" for i in range(len(pieces)))
        filters = (f"{split};" + ";".join(graph) + f";{''.join(parts)}concat=n={len(pieces)}:v=1:a=0,fps={FPS},"
                   f"scale={W}:{H},setsar=1,format=yuv420p")
        return self.segment(["-i", src], filters, band(n, c.issue, c.line), self.file(".mp4"))

    def chapter(self, n: int, c: Chapter) -> list[Path]:
        card = [(chapter_label(n), 44, True, AMBER), (c.issue, 60, True, WHITE), (c.line, 40, False, WHITE)]
        strip = band(n, c.issue, c.line)
        segs = [self.picture(still_frame(card), max(3.0, min_seconds(c.line)), strip)]
        for k, p in enumerate(c.clips, 1):
            if isinstance(p, Still):
                segs.append(self.picture(still_frame([(p.caption, 30, False, WHITE)], p.image, self.masks), p.seconds, strip))
            else:
                out = self.clips / f"{n:02d}-{k}.mp4"
                self.render(p, out)
                segs.append(self.timed(p, out, n, c))
        return segs

    def opening(self, starts: list[float]) -> Path:
        return self.picture(opening_frame(self.reel.title, self.reel.chapters, starts), OPENING_S, None)

    def build(self) -> None:
        chapters = [self.chapter(n, c) for n, c in enumerate(self.reel.chapters, 1)]
        seconds = [[duration(s) for s in segs] for segs in chapters]
        lengths = [sum(d) for d in seconds]
        starts = [OPENING_S + sum(lengths[:i]) for i in range(self.total)]
        opening = self.opening(starts)
        listing = self.work / "list.txt"
        listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in [opening, *(s for segs in chapters for s in segs)]), encoding="utf-8")
        meta = self.work / "chapters.txt"
        esc = lambda s: re.sub(r"([=;#\\\n])", r"\\\1", s)  # noqa: E731
        marks = chapter_marks(self.reel.chapters, starts, lengths)
        meta.write_text(";FFMETADATA1\ntitle=" + esc(self.reel.title) + "\n" + "".join(
            f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(a * 1000)}\nEND={round(b * 1000)}\ntitle={esc(t)}\n" for a, b, t in marks), encoding="utf-8")
        out = self.reel.folder / "reel.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-i", meta, "-map", "0:v",
             "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", out])
        self.write_chapters(starts, lengths, duration(out))
        self.stills(out, starts, seconds)
        print(f"wrote {out} ({clock(duration(out))}), chapters.md and stills/")

    def stills(self, reel: Path, starts: list[float], seconds: list[list[float]]) -> None:
        """stills/NN.png per chapter: the finished reel at the middle of its card, of each still and of each caption."""
        folder = self.reel.folder / "stills"
        folder.mkdir(exist_ok=True)
        for n, (c, t, secs_) in enumerate(zip(self.reel.chapters, starts, seconds), 1):
            shots = [("章名卡", t + secs_[0] / 2)]
            for p, off in zip(c.clips, (t + sum(secs_[:k]) for k in range(1, len(secs_)))):
                if isinstance(p, Still):
                    shots.append((p.image.name, off + p.seconds / 2))
                    continue
                tl = p.timeline
                for i, st in enumerate(p.steps, 1):
                    a, b = tl.screen(st.start), tl.screen(st.end)
                    shots.append((f"步驟 {i}/{len(p.steps)}", off + (a + b) / 2))
            cols, w, h = 3, W // 2, (H + BAND) // 2
            sheet = Image.new("RGB", (cols * w, math.ceil(len(shots) / cols) * (h + 28)), (0, 0, 0))
            d = ImageDraw.Draw(sheet)
            for i, (label, at) in enumerate(shots):
                png = self.work / "still.png"
                run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", reel, "-frames:v", "1", "-vf", f"scale={w}:{h}", png])
                x, y = i % cols * w, i // cols * (h + 28)
                sheet.paste(Image.open(png).convert("RGB"), (x, y + 28))
                d.text((x + 6, y + 4), f"{label}　{clock(at)}（{at:.1f} s）", font=font(18), fill=AMBER)
            sheet.save(folder / f"{n:02d}.png")

    def write_chapters(self, starts: list[float], lengths: list[float], total: float) -> None:
        rows = ["# " + self.reel.title, "",
                f"reel.mp4 長 {clock(total)}（{total:.1f} s），1280x776：上方 56 px 章節列（章號、issue、一句話），下方 1280x720 畫面。"
                f"開頭目錄 {OPENING_S:g} s，占滿整個畫面、沒有章節列；"
                "每章先一張章名卡，MP4 帶章節標記。", "",
                "| 開始 | 章 | Issue | 看什麼 | 來源 | 變速 | 備註 |", "|---|---|---|---|---|---|---|"]
        for n, (c, t) in enumerate(zip(self.reel.chapters, starts), 1):
            srcs, speeds = [], []
            for p in c.clips:
                if isinstance(p, Still):
                    srcs.append(p.image.name)
                    continue
                srcs.append(f"{p.video.name} {hms(p.timeline.t0)}–{hms(p.timeline.t1)}（{p.steps_file.name}）")
                speeds += [f"{hms(a)}–{hms(b)} {x:g}×" for a, b, x in p.timeline.speed]
                speeds += [f"{hms(at)} 停格 {sec:g} s" for at, sec in p.timeline.freeze]
            rows.append(f"| {clock(t)} | {chapter_label(n)} | {c.issue} | {c.line} | {'<br>'.join(srcs)} | {'<br>'.join(speeds)} | {c.note} |")
        (self.reel.folder / "chapters.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def sheet_frames(footage, t0: float, t1: float, every: float):
    """(wall time, 1280x720 frame) from t0 to t1, one every `every` s, decoded one at a time from the piece covering t0."""
    path, off = footage.locate(t0)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{off:.3f}", "-t", f"{t1 - t0 + every / 2:.3f}", "-i", str(path), "-vf",
                            f"fps=1/{every:g},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    i = 0
    while len(buf := dec.stdout.read(W * H * 3)) == W * H * 3:
        yield t0 + i * every, Image.frombytes("RGB", (W, H), buf)
        i += 1
    dec.wait()


def sheet(footage, t0: float, t1: float, every: float, out: Path, masks=None, cols: int = 6) -> None:
    """The recording's frames from t0 to t1, one every `every` s, masked at full size, laid out at a quarter size, each
    labelled with its wall time."""
    w, h, label = W // 4, H // 4, 22
    shots = []
    for t, frame in sheet_frames(footage, t0, t1, every):
        shots.append((t, (evidence.apply_masks(frame, masks) if masks else frame).resize((w, h))))
    if not shots or shots[-1][0] < t1 - every:
        print(f"sheet: the recording that covers {hms(t0)} ends before {hms(t1)}; {len(shots)} frames")
    im = Image.new("RGB", (cols * w, max(1, math.ceil(len(shots) / cols)) * (h + label)), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, (t, shot) in enumerate(shots):
        x, y = i % cols * w, i // cols * (h + label)
        im.paste(shot, (x, y + label))
        d.text((x + 4, y + 2), hms(t), font=font(15), fill=AMBER)
    im.save(out)
    print(f"{len(shots)} frames -> {out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "build"):
        sub.add_parser(name).add_argument("reel", type=Path)
    p = sub.add_parser("sheet")
    p.add_argument("--video", action="append", required=True, help="PATH@START, the wall time of its first frame")
    p.add_argument("--from", dest="t0", required=True)
    p.add_argument("--to", dest="t1", required=True)
    p.add_argument("--every", type=float, default=2.0, help="seconds between frames")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--masks", help="masks.json (default .local/evidence/masks.json)")
    p.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "sheet" and (a.every <= 0 or a.cols <= 0):
        ap.error("--every and --cols must be above 0")
    if a.cmd == "sheet":
        sheet(evidence.Footage(a.video), secs(a.t0), secs(a.t1), a.every, a.out, evidence.load_masks(evidence.masks_path(a)), a.cols)
        return
    reel = load(a.reel)
    report = audit(reel)
    for w in report.warnings:
        print(f"warning: {w}")
    for p in report.problems:
        print(f"problem: {p}")
    if report.problems:
        print(f"refused: {len(report.problems)} problem(s); the rules are in docs/agents/evidence-style.md")
        sys.exit(1)
    print(f"ok: {len(reel.chapters)} chapters pass the rules", flush=True)
    if a.cmd == "build":
        Builder(reel).build()


if __name__ == "__main__":
    main()
