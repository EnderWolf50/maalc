"""Compare two sets of settings GUI stills (tools/gui_shots.mjs) pixel by pixel: "looks the same" for a refactor (#729).

Usage: uv run python tools/gui_compare.py <before dir> <after dir> [--diff <dir>]
Each dir is a gui_shots.mjs `--out` folder (`<scheme>/<name>.png`, or any tree of PNGs); a still is matched by its path in
it. Prints one line per still: `same`, `size WxH -> WxH`, `N px differ, box (x0, y0)-(x1, y1)` (the box's last pixel
inclusive, in the still's own pixels, device pixels at --scale 2) or `only before` / `only after`; then a summary line.
With --diff, writes `<diff>/<path>` for each still that differs: the after still dimmed, the differing pixels in magenta.
Exits 1 when any still differs or is missing on one side, else 0.

Shoot both sides from the built app, one build per side, at the same window size and scale: two runs of one build gave
the same pixels on 2026-11-14 (28 stills, light and dark, Edge headless), so a difference is the change, not noise.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MARK = (255, 0, 255)


def stills(root: Path) -> dict[str, Path]:
    """Every PNG under root, by its path relative to root with forward slashes."""
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*.png"))}


def compare(before: Path, after: Path) -> tuple[str, np.ndarray | None]:
    """What differs between two stills, and the mask of the differing pixels (None when the sizes differ)."""
    a = np.asarray(Image.open(before).convert("RGBA"))
    b = np.asarray(Image.open(after).convert("RGBA"))
    if a.shape != b.shape:
        return f"size {a.shape[1]}x{a.shape[0]} -> {b.shape[1]}x{b.shape[0]}", None
    mask = (a != b).any(axis=2)
    n = int(mask.sum())
    if not n:
        return "same", mask
    ys, xs = np.nonzero(mask)
    return f"{n} px differ, box ({xs.min()}, {ys.min()})-({xs.max()}, {ys.max()})", mask


def diff_image(after: Path, mask: np.ndarray) -> Image.Image:
    """The after still at a third of its brightness, the differing pixels magenta."""
    im = np.asarray(Image.open(after).convert("RGB")) // 3
    im[mask] = MARK
    return Image.fromarray(im)


def run(before: Path, after: Path, diff: Path | None = None, out=sys.stdout) -> int:
    """Print the comparison; the number of stills that differ or are on one side only."""
    a, b = stills(before), stills(after)
    bad = 0
    for name in sorted(a.keys() | b.keys()):
        if name not in b or name not in a:
            print(f"{name}: only {'before' if name in a else 'after'}", file=out)
            bad += 1
            continue
        what, mask = compare(a[name], b[name])
        print(f"{name}: {what}", file=out)
        if what == "same":
            continue
        bad += 1
        if diff is not None and mask is not None:
            dest = diff / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            diff_image(b[name], mask).save(dest)
    print(f"{len(a.keys() | b.keys()) - bad} same, {bad} differ", file=out)
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--diff", type=Path, help="write the differing stills here, the changed pixels in magenta")
    args = ap.parse_args(argv)
    for d in (args.before, args.after):
        if not d.is_dir():
            raise SystemExit(f"{d}: not a folder")
    return 1 if run(args.before, args.after, args.diff) else 0


if __name__ == "__main__":
    sys.exit(main())
