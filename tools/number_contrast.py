"""The order numbers' contrast on the settings window's deployment cards (#756; #744 and #754 measured it by hand). Every
card's art is swapped for white, the worst art behind a number, with the card's own filter still on it; then each number's
ink is held against the ring of pixels 1 to 2 CSS px outside its glyphs: the ring's median, and its lighter end (the 90th
percentile of luminance, the worst for an ink lighter than its rim). Large text needs 3:1 on what is right behind it.

Drives the built page over DevTools with tools/gui_devtools.mjs: open the window first (docs/agents/gui-driving.md), with the
grid on the tab it is measured on, then

  uv run python tools/number_contrast.py --port <port> [--sizes 1500x860,1280x720,800x480] [--schemes dark,light]
      [--scale 2] [--grid "[data-section=order] .sinners"] [--prep <js>] [--out <dir>] [--min 3]

Each size is the page laid out at it (`--viewport`), each scheme emulated, at 2 device px a CSS px (`--scale`, as #744 and
#754 measured: the same numbers on any display; 0 takes the window's own, 1.5 on a display at 150 %, where the ring's pixels
fall on a coarser grid and its lighter end reads a little lower). --prep is page code run first (a tab to open, a team to
pick). Prints one line per number, then the lowest median and 90th percentile
per view and kind (deployed, backup) and over all; --out keeps each view's still. Exits 1 when a number's 90th percentile is
under --min, 2 on a command line it cannot use.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
DEVTOOLS = REPO / "tools" / "gui_devtools.mjs"
GRID = "[data-section=order] .sinners"
INK_TOLERANCE = 30  # the sum over R, G, B of a pixel's distance from the ink that still counts as ink, not its soft edge
MIN_INK = 10  # ink pixels a CSS px squared: fewer is no number
PAD = 4  # CSS px round a number's box that the ring may reach
WHITE_ART = ".sinner img { object-position: -9999px 0 !important; background: #fff !important; }"
# The app's CSP refuses an added <style>: the rule goes in a constructed sheet, kept on window to take it off after.
SHEET = "window.__numberContrastWhite"


def luminance(rgb: np.ndarray) -> np.ndarray:
    """WCAG relative luminance of sRGB colours 0-255 (the last axis R, G, B)."""
    c = np.asarray(rgb, dtype=float) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def ratio(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def dilate(mask: np.ndarray, r: float) -> np.ndarray:
    """The mask grown by a disc of radius r px (r need not be whole: 1.5 takes the pixels up to 1.5 px away)."""
    out = mask.copy()
    h, w = mask.shape
    reach = int(r)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            if (dx or dy) and dx * dx + dy * dy <= r * r:
                out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] |= mask[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


def ring(glyph: np.ndarray, scale: float) -> np.ndarray:
    """The pixels more than 1 and at most 2 CSS px from the glyph, at `scale` device px a CSS px."""
    return dilate(glyph, 2 * scale) & ~dilate(glyph, 1 * scale)


def glyph(region: np.ndarray, ink) -> np.ndarray:
    """The pixels of the number's flat ink, not its soft edge."""
    return np.abs(region.astype(int) - np.array(ink)).sum(axis=2) < INK_TOLERANCE


def ring_ratios(ink, pixels: np.ndarray) -> tuple[float, float]:
    """The ink against the ring's median luminance and against its 90th percentile."""
    lum, ink_lum = luminance(pixels), float(luminance(np.array(ink)))
    return ratio(ink_lum, float(np.median(lum))), ratio(ink_lum, float(np.percentile(lum, 90)))


def measure(region: np.ndarray, ink, scale: float) -> dict | None:
    """One number in its region of a still: its ink pixels and the two ratios, or None when the region holds no ink."""
    g = glyph(region, ink)
    if g.sum() < MIN_INK * scale * scale:
        return None
    median, p90 = ring_ratios(ink, region[ring(g, scale)])
    return {"ink_px": int(g.sum()), "median": median, "p90": p90}


def css_rgb(text: str) -> tuple[int, int, int]:
    """A computed CSS colour, rgb() or rgba(), as (R, G, B)."""
    r, g, b = (int(float(v)) for v in re.findall(r"[\d.]+", text)[:3])
    return r, g, b


def summary(rows: list[dict], bar: float) -> tuple[list[str], list[dict]]:
    """The lowest median and 90th percentile per view and kind, and over all per kind; and the rows under `bar`."""
    lines = []

    def low(rs, kind):
        k = [r for r in rs if r["kind"] == kind]
        return f"{kind} n={len(k)} median>={min(r['median'] for r in k):.2f} p90>={min(r['p90'] for r in k):.2f}" if k else None

    for view in dict.fromkeys(r["view"] for r in rows):
        rs = [r for r in rows if r["view"] == view]
        lines.append(f"{view}: " + "; ".join(p for kind in ("deployed", "backup") if (p := low(rs, kind))))
    lines += [f"all {p.replace(' ', ': ', 1)}" for kind in ("deployed", "backup") if (p := low(rows, kind))]
    return lines, [r for r in rows if r["p90"] < bar]


# --- the page --------------------------------------------------------------------------------------------------------

def devtools(command: str, *args: str, port: int) -> list:
    """A gui_devtools.mjs page command at the port: the JSON values it printed, one a line. A port that did not answer is
    tried again a second later, up to 4 times: the window's DevTools port went quiet for a moment twice in 2026-11-15's
    runs, about once in 60 commands, and answered the next one."""
    for attempt in range(5):
        r = subprocess.run(["node", str(DEVTOOLS), command, *args, "--port", str(port)], capture_output=True, text=True, timeout=120)
        if not r.returncode or not any(m in r.stderr for m in ("cannot connect", "nothing answers")):
            break
        time.sleep(1)
    if r.returncode:
        raise SystemExit(f"gui_devtools {command}: {r.stderr.strip() or r.stdout.strip()}")
    return [None if line == "undefined" else json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def geometry_js(grid: str) -> str:
    """Page code: the grid's box and, per number, its text, kind, ink and the box of its digits (not the span's, which is the
    card's width and reaches the frame's vines) in CSS px from the grid's top left."""
    return f"""(() => {{ const g = document.querySelector({json.dumps(grid)}); if (!g) return null;
  const b = g.getBoundingClientRect();
  return {{ width: b.width, nums: [...g.querySelectorAll(".sinner .num")].map((n) => {{ const range = document.createRange();
    range.selectNodeContents(n); const r = range.getBoundingClientRect();
    return {{ text: n.textContent, kind: n.closest(".sinner").classList.contains("backup") ? "backup" : "deployed",
      ink: getComputedStyle(n).color, x: r.left - b.left, y: r.top - b.top, w: r.width, h: r.height }}; }}) }}; }})()"""


def view_rows(still: Path, geo: dict, view: str) -> list[dict]:
    im = np.asarray(Image.open(still).convert("RGB"))
    scale = im.shape[1] / geo["width"]
    rows = []
    for n in geo["nums"]:
        x0, y0 = (max(0, round((v - PAD) * scale)) for v in (n["x"], n["y"]))
        x1, y1 = round((n["x"] + n["w"] + PAD) * scale), round((n["y"] + n["h"] + PAD) * scale)
        m = measure(im[y0:y1, x0:x1], css_rgb(n["ink"]), scale)
        if m is None:
            raise SystemExit(f"{view}: no ink of number {n['text']} in {still}: is the grid in view?")
        rows.append({"view": view, "kind": n["kind"], "text": n["text"], **m})
    return rows


def run(a: argparse.Namespace) -> int:
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="number-contrast-"))
    out.mkdir(parents=True, exist_ok=True)
    if a.prep:
        devtools("eval", f"(async () => {{ {a.prep}; await new Promise((r) => setTimeout(r, 500)); }})()", port=a.port)
    rows = []
    try:
        white = devtools("eval", f"""(() => {{ const s = new CSSStyleSheet(); s.replaceSync({json.dumps(WHITE_ART)}); {SHEET} = s;
          document.adoptedStyleSheets = [...document.adoptedStyleSheets, s];
          const img = document.querySelector({json.dumps(a.grid)} + " .sinner img");
          return img ? getComputedStyle(img).backgroundColor : null; }})()""", port=a.port)
        if white != ["rgb(255, 255, 255)"]:
            raise SystemExit(f"the art did not turn white ({white}): is {a.grid} on the page?")
        for w, h in a.sizes:
            for scheme in a.schemes:
                view = f"{w}x{h} {scheme}"
                session = ["--viewport", f"{w}x{h}", "--scheme", scheme] + (["--scale", str(a.scale)] if a.scale else [])
                devtools("eval", f"document.querySelector({json.dumps(a.grid)})?.scrollIntoView({{ block: 'center' }})", *session, port=a.port)
                shot = out / f"white-{w}x{h}-{scheme}.png"
                printed = devtools("still", str(shot), "--element", a.grid, *session, "--then", geometry_js(a.grid), port=a.port)
                geo = next((p["then"] for p in printed if isinstance(p, dict) and "then" in p), None)
                if not geo:
                    raise SystemExit(f"{view}: nothing matches {a.grid}")
                for r in view_rows(shot, geo, view):
                    rows.append(r)
                    print(f"{view} {r['kind']} {r['text']}: {r['ink_px']} ink px; ring median {r['median']:.2f}:1, 90th pct {r['p90']:.2f}:1")
    finally:
        devtools("eval", f"document.adoptedStyleSheets = document.adoptedStyleSheets.filter((s) => s !== {SHEET})", port=a.port)
        if not a.out:
            shutil.rmtree(out, ignore_errors=True)
    lines, low = summary(rows, a.min)
    print("\n".join(lines))
    for r in low:
        print(f"under {a.min}:1: {r['view']} {r['kind']} {r['text']} ({r['p90']:.2f}:1)")
    return 1 if low else 0


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="number_contrast.py", description=__doc__.split("\n\n")[0])

    def sizes(text):
        try:
            return [tuple(int(v) for v in re.fullmatch(r"(\d+)x(\d+)", s).groups()) for s in text.split(",")]
        except AttributeError:
            raise argparse.ArgumentTypeError("sizes are WIDTHxHEIGHT, comma-separated, as 1500x860,800x480") from None

    def schemes(text):
        out = text.split(",")
        if not set(out) <= {"dark", "light"}:
            raise argparse.ArgumentTypeError("schemes are dark or light, comma-separated")
        return out

    ap.add_argument("--port", type=int, required=True, help="the window's DevTools port (gui_devtools.mjs open prints it)")
    ap.add_argument("--sizes", type=sizes, default=[(1500, 860), (1280, 720), (800, 480)])
    ap.add_argument("--schemes", type=schemes, default=["dark", "light"])
    ap.add_argument("--scale", type=float, default=2.0, help="device px a CSS px (0: the window's own)")
    ap.add_argument("--grid", default=GRID, help=f"the sinner grid to measure (default {GRID!r})")
    ap.add_argument("--prep", help="page code run first: a tab to open, a team to pick")
    ap.add_argument("--out", help="a folder to keep each view's still in")
    ap.add_argument("--min", type=float, default=3.0, help="the bar a number's 90th percentile is held to (3:1, large text)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    sys.exit(run(parse(sys.argv[1:])))
