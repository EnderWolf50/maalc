"""The review reel: annotated clips of live tests strung together by chapter, one chapter per issue.

    uv run --group probe python tools/live/reel.py REEL.json [--check]

REEL.json, paths relative to its folder or absolute, times wall clock `HH:MM:SS[.fff]`:

    {"title": "...", "chapters": [{"issue": "#94", "line": "one line on what to watch", "short"?: "...", "note"?: "...",
      "clips": [{"video": "rec.mp4", "start": "<wall time of its first frame>", "from": T, "to": T,
                 "events": "events.json", "steps": "steps.json",
                 "speed"?: [[T, T, 4]], "freeze"?: [[T, 2.0]]},
                {"image": "gui.png", "caption": "...", "seconds"?: 4}]}]}

A clip is rendered from the uncut recording with evidence-annotate (`evidence.py`'s `annotated_clip`, masks
included) into `clips/` beside REEL.json, again only when one of its inputs changed. `speed` plays a stretch
faster (4) or slower (0.5), `freeze` holds the frame at T for that many seconds; the strip marks each
("快轉 4×", "慢放 0.5×", "停格"). The reel is 1280x776: a 56 px chapter strip above the 1280x720 picture, so
the strip never hides game UI. It shows the chapter (number/total, issue, line) at every moment; the opening
list gives each chapter's start time; the MP4 carries a chapter mark per chapter. Writes reel.mp4 and
chapters.md beside REEL.json.

Before it builds, it checks every chapter against docs/agents/evidence-style.md "Review reel" and refuses, listing
each problem: a caption with no Chinese character or with log text or a code name outside 「」, a caption on screen
shorter than max(3 s, characters / 5), overlapping captions, a box outside its events' grid. A 1920x1080 grid
whose boxes all fit inside 1280x720 gets a warning: the boxes may be in game pixels. `--check` only checks.
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
from live.evidence import hms, secs  # noqa: E402
from local_dir import local_dir  # noqa: E402

W, H, BAND, FPS = 1280, 720, 56, 30
OPENING_S = 10.0  # the opening list is a table of contents to pause on; the chapter marks are for jumping
FONTS = {False: evidence.FONTS, True: ["C:/Windows/Fonts/msjhbd.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]}
AMBER, WHITE, DIM, BG = (255, 196, 64), (245, 245, 245), (190, 194, 204), (17, 19, 26)
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]

HAN = re.compile(r"[\u3400-\u9fff]")
QUOTED = re.compile(r"「[^」]*」")
CODE = re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+"  # snake_case
                  r"|[A-Za-z_][A-Za-z0-9_]*(?:=|\(\))"  # key=value, call()
                  r"|\b[a-z]+\.[a-z_]{2,}\b"  # dotted.name
                  r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){2,}")  # MirrorEntryPaused, GiveUpRewards


def min_seconds(text: str) -> float:
    """How long a caption stays up at least: 3 s, or a second per five characters (spaces not counted)."""
    return max(3.0, len(re.sub(r"\s", "", text)) / 5)


def wording(text: str) -> str | None:
    """Why `text` fails as a caption (no Chinese, or log text / a code name outside 「」), or None."""
    if not HAN.search(text):
        return "has no Chinese character"
    if m := CODE.search(QUOTED.sub("", text)):
        return f"reads like log text or a code name ({m[0]}); a game label goes in 「」"
    return None


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

    def marks(self) -> list[tuple[float, float, str]]:
        """(from, to, text) on the played clip's clock for each stretch not at normal speed."""
        out = [(self.screen(a), self.screen(b), f"快轉 {x:g}×" if x > 1 else f"慢放 {x:g}×") for a, b, x in self.speed]
        out += [(self.screen(at), self.screen(at) + sec, "停格") for at, sec in self.freeze]
        return sorted(out)


@dataclass(frozen=True)
class Step:
    start: float
    end: float
    title: str
    boxes: tuple


@dataclass(frozen=True)
class Clip:
    video: Path
    start: str
    timeline: Timeline
    events: Path
    steps_file: Path
    space: tuple[int, int]
    steps: tuple[Step, ...]


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
    pieces: tuple


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
        pieces = []
        for p in c["clips"]:
            if "image" in p:
                pieces.append(Still(at(p["image"]), p["caption"], float(p.get("seconds", max(4.0, min_seconds(p["caption"]))))))
                continue
            events, steps_file = at(p["events"]), at(p["steps"])
            space = tuple(int(v) for v in read_json(events)["space"])
            steps = tuple(Step(secs(s["from"]), secs(s["to"]), s["title"], tuple(tuple(b) for b in s.get("boxes", ())))
                          for s in read_json(steps_file))
            timeline = Timeline(secs(p["from"]), secs(p["to"]), tuple((secs(a), secs(b), float(x)) for a, b, x in p.get("speed", ())),
                                tuple((secs(t), float(s)) for t, s in p.get("freeze", ())))
            pieces.append(Clip(at(p["video"]), p["start"], timeline, events, steps_file, space, steps))
        chapters.append(Chapter(c["issue"], c["line"], c.get("short", c["line"]), c.get("note", ""), tuple(pieces)))
    return Reel(doc.get("title", "驗收總集"), folder, tuple(chapters))


# --- the check -------------------------------------------------------------------------------------------

@dataclass
class Report:
    problems: list[str]
    warnings: list[str]


def check_clip(clip: Clip, where: str, report: Report) -> None:
    tl, (gw, gh) = clip.timeline, clip.space
    for i, (a, b, x) in enumerate(sorted(tl.speed)):
        if not (tl.t0 <= a < b <= tl.t1) or x <= 0:
            report.problems.append(f"{where}: speed {hms(a)}-{hms(b)} x{x:g} is not a stretch of the cut {hms(tl.t0)}-{hms(tl.t1)}")
        if i and a < sorted(tl.speed)[i - 1][1]:
            report.problems.append(f"{where}: speed {hms(a)}-{hms(b)} overlaps the stretch before it")
    for at, sec in tl.freeze:
        if not tl.t0 <= at <= tl.t1 or sec <= 0:
            report.problems.append(f"{where}: freeze at {hms(at)} for {sec:g} s is outside the cut {hms(tl.t0)}-{hms(tl.t1)}")
    boxes = []
    for i, s in enumerate(clip.steps, 1):
        name = f"{where}, step {i} {s.title!r}"
        if why := wording(s.title):
            report.problems.append(f"{name}: {why}")
        if i > 1 and s.start < clip.steps[i - 2].end:
            report.problems.append(f"{name}: overlaps step {i - 1} (from {hms(s.start)} before its end {hms(clip.steps[i - 2].end)})")
        shown, need = tl.screen(s.end) - tl.screen(s.start), min_seconds(s.title)
        if shown < need - 1e-6:
            report.problems.append(f"{name}: shown {shown:.1f} s, needs {need:.1f} s (3 s or a second per 5 characters)")
        for x, y, w, h, *_ in s.boxes:
            boxes.append((x, y, w, h))
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > gw or y + h > gh:
                report.problems.append(f"{name}: box {[x, y, w, h]} is outside the events grid {gw}x{gh}")
    if (gw, gh) == (1920, 1080) and boxes and all(x + w <= W and y + h <= H for x, y, w, h in boxes):
        report.warnings.append(f"{where}: every box fits inside 1280x720 on a 1920x1080 grid; they may be in game pixels "
                               f"(scale by 1.5 to the touch log's grid)")


def check(path) -> Report:
    reel = load(Path(path))
    report = Report([], [])
    for n, c in enumerate(reel.chapters, 1):
        if why := wording(c.line):
            report.problems.append(f"{reel.label(n)}: line {c.line!r} {why}")
        for k, p in enumerate(c.pieces, 1):
            if isinstance(p, Still):
                where = f"{reel.label(n)}, still {p.image.name} {p.caption!r}"
                if why := wording(p.caption):
                    report.problems.append(f"{where}: {why}")
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


def band(n: int, total: int, issue: str, line: str, mark: str = "") -> Image.Image:
    """The chapter strip: 第 n/total 章, the issue, the line; a speed or freeze mark at the right."""
    im = Image.new("RGB", (W, BAND), BG)
    d = ImageDraw.Draw(im)
    x, cy = 20, BAND // 2
    for text, f, colour in ((f"第 {n}/{total} 章" if n else "目錄", font(24, True), AMBER), (issue, font(24, True), WHITE),
                            (line, font(22), DIM)):
        if text:
            d.text((x, cy), text, font=f, fill=colour, anchor="lm")
            x += d.textlength(text, font=f) + 22
    if mark:
        f = font(22, True)
        tw = d.textlength(mark, font=f)
        d.rounded_rectangle([W - tw - 48, cy - 17, W - 16, cy + 17], radius=17, fill=AMBER)
        d.text((W - tw / 2 - 32, cy), mark, font=f, fill=BG, anchor="mm")
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

    def segment(self, picture: list, filters: str, bands: list[tuple[Image.Image, float, float]], out: Path) -> Path:
        """Encode `picture` (ffmpeg input args, 1280x720 after `filters`) under the strip; each band shows from-to (s)."""
        inputs, graph, last = list(picture), [f"[0:v]{filters},pad={W}:{H + BAND}:0:{BAND}[v0]"], "v0"
        for i, (im, a, b) in enumerate(bands, 1):
            png = self.file(".png")
            im.save(png)
            inputs += ["-i", png]
            when = f":enable='between(t,{a:.3f},{b:.3f})'" if b < math.inf else ""
            graph.append(f"[{last}][{i}:v]overlay=0:0{when}[v{i}]")
            last = f"v{i}"
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", *ENC, out])
        return out

    def picture(self, im: Image.Image, seconds: float, n: int, c: Chapter) -> Path:
        png = self.file(".png")
        im.save(png)
        return self.segment(["-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.3f}", "-i", png], "setsar=1,format=yuv420p",
                            [(band(n, self.total, c.issue, c.line), 0, math.inf)], self.file(".mp4"))

    def render(self, clip: Clip, out: Path) -> None:
        """Annotate the cut from the uncut recording, unless the clip and its inputs are what made `out` last time."""
        tl = clip.timeline
        stat = clip.video.stat()
        key = hashlib.sha256(json.dumps([str(clip.video), stat.st_size, stat.st_mtime, clip.start, tl.t0, tl.t1,
                                         clip.events.read_text(encoding="utf-8"), clip.steps_file.read_text(encoding="utf-8")]).encode()).hexdigest()
        stamp = out.with_suffix(".key")
        if out.exists() and stamp.exists() and stamp.read_text() == key:
            return
        events = read_json(clip.events)
        steps = read_json(clip.steps_file)
        footage = evidence.Footage([f"{clip.video}@{clip.start}"])
        evidence.annotated_clip(footage, tl.t0, tl.t1, out, events, steps, SimpleNamespace(annotate=evidence.ANNOTATE, masks=None))
        stamp.write_text(key)

    def timed(self, clip: Clip, src: Path, n: int, c: Chapter) -> Path:
        """The annotated clip played by its timeline, under the strip with its marks."""
        tl, parts, graph = clip.timeline, [], []
        pieces = tl.pieces()
        for i, p in enumerate(pieces):
            if p[0] == "play":
                _, a, b, x = p
                graph.append(f"[s{i}]trim=start={a - tl.t0:.3f}:end={b - tl.t0:.3f},setpts=(PTS-STARTPTS)/{x:g}[p{i}]")
            else:
                _, at, sec = p
                k = min(round((at - tl.t0) * FPS), round((tl.t1 - tl.t0) * FPS) - 1)
                graph.append(f"[s{i}]trim=start_frame={k}:end_frame={k + 1},setpts=PTS-STARTPTS,"
                             f"tpad=stop_mode=clone:stop_duration={sec:.3f}[p{i}]")
            parts.append(f"[p{i}]")
        split = f"split={len(pieces)}" + "".join(f"[s{i}]" for i in range(len(pieces)))
        filters = (f"{split};" + ";".join(graph) + f";{''.join(parts)}concat=n={len(pieces)}:v=1:a=0,fps={FPS},"
                   f"scale={W}:{H},setsar=1,format=yuv420p")
        bands = [(band(n, self.total, c.issue, c.line), 0, math.inf)]
        bands += [(band(n, self.total, c.issue, c.line, text), a, b) for a, b, text in tl.marks()]
        return self.segment(["-i", src], filters, bands, self.file(".mp4"))

    def chapter(self, n: int, c: Chapter) -> list[Path]:
        card = [(f"第 {n}/{self.total} 章", 30, True, AMBER), (c.issue, 60, True, WHITE), (c.line, 40, False, WHITE)]
        segs = [self.picture(still_frame(card), max(3.0, min_seconds(c.line)), n, c)]
        for k, p in enumerate(c.pieces, 1):
            if isinstance(p, Still):
                segs.append(self.picture(still_frame([(p.caption, 30, False, WHITE)], p.image, self.masks), p.seconds, n, c))
            else:
                out = self.clips / f"{n:02d}-{k}.mp4"
                self.render(p, out)
                segs.append(self.timed(p, out, n, c))
        return segs

    def opening(self, starts: list[float]) -> Path:
        im = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(im)
        d.text((W // 2, 50), self.reel.title, font=font(40, True), fill=WHITE, anchor="mm")
        rows = math.ceil(self.total / 2)
        step = min(46, (H - 120) // max(rows, 1))
        f, fb = font(min(24, step - 14)), font(min(24, step - 14), True)
        for i, (c, t) in enumerate(zip(self.reel.chapters, starts)):
            x, y = 60 + (i // rows) * 620, 110 + (i % rows) * step
            d.text((x, y), f"{i + 1:02d}", font=fb, fill=AMBER)
            d.text((x + 44, y), clock(t), font=fb, fill=WHITE)
            d.text((x + 130, y), c.short, font=f, fill=DIM)
        png = self.file(".png")
        im.save(png)
        return self.segment(["-loop", "1", "-framerate", str(FPS), "-t", f"{OPENING_S:.3f}", "-i", png], "setsar=1,format=yuv420p",
                            [(band(0, self.total, "", f"{self.total} 章，章節開始時間如下；播放器也可跳章"), 0, math.inf)], self.file(".mp4"))

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
        marks = [(0.0, OPENING_S, "目錄")] + [(t, t + d, f"{n}/{self.total} {c.issue} {c.line}")
                                             for n, (c, t, d) in enumerate(zip(self.reel.chapters, starts, lengths), 1)]
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
            for p, off in zip(c.pieces, (t + sum(secs_[:k]) for k in range(1, len(secs_)))):
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
                f"reel.mp4 長 {clock(total)}（{total:.1f} s），1280x776：上方 56 px 章節列，下方 1280x720 畫面。開頭目錄 {OPENING_S:g} s；"
                "每章先一張章名卡，MP4 帶章節標記。", "",
                "| 開始 | 章 | Issue | 看什麼 | 來源 | 變速 | 備註 |", "|---|---|---|---|---|---|---|"]
        for n, (c, t) in enumerate(zip(self.reel.chapters, starts), 1):
            srcs, speeds = [], []
            for p in c.pieces:
                if isinstance(p, Still):
                    srcs.append(p.image.name)
                    continue
                srcs.append(f"{p.video.name} {hms(p.timeline.t0)}–{hms(p.timeline.t1)}（{p.steps_file.name}）")
                speeds += [f"{hms(a)}–{hms(b)} {x:g}×" for a, b, x in p.timeline.speed]
                speeds += [f"{hms(at)} 停格 {sec:g} s" for at, sec in p.timeline.freeze]
            rows.append(f"| {clock(t)} | {n} | {c.issue} | {c.line} | {'<br>'.join(srcs)} | {'<br>'.join(speeds)} | {c.note} |")
        (self.reel.folder / "chapters.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reel", type=Path)
    ap.add_argument("--check", action="store_true", help="only check the chapters")
    a = ap.parse_args(argv)
    report = check(a.reel)
    for w in report.warnings:
        print(f"warning: {w}")
    for p in report.problems:
        print(f"problem: {p}")
    if report.problems:
        print(f"refused: {len(report.problems)} problem(s); docs/agents/evidence-style.md \"Review reel\" has the rules")
        sys.exit(1)
    print(f"ok: {len(load(a.reel).chapters)} chapters pass the rules")
    if not a.check:
        Builder(load(a.reel)).build()


if __name__ == "__main__":
    main()
