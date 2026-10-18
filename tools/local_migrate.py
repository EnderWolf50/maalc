"""Bring data that lives outside the repo into `<main checkout>/.local/` (docs/agents/local-dev.md).

  uv run python tools/local_migrate.py [--probe <old probe folder>] [--unpack <unpacked game data>] [--apply] [--move]

Dry run unless `--apply`. Nothing is moved by default: a directory junction (a symlink off Windows) points
`.local/` at the existing folder, so a task still using it keeps working. `--move` moves the folders instead.
Existing targets are left alone.

  --probe   its `archive/` becomes `.local/archive/` (with INDEX.md); its `tools/templates/` (full screens
            of the main window and the title screen) yield the privacy-mask templates and
            `.local/evidence/masks.json`, which the `evidence-annotate` skill reads (`--masks`).
  --unpack  becomes `.local/unpack/`: the game data, with `raw/Localize/<lang>/` in it.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from local_dir import main_checkout

# Where the account shows, in 1280x720 game space. The template is a button next to it that stays put.
MASKS = [
    # (template file, screen it is cut from, crop box x0 y0 x1 y1, boxes to black out)
    ("main-copy.png", "MainWindow.png", (255, 130, 335, 158), [[55, 126, 200, 36], [30, 620, 125, 34]]),  # UID plate
    ("title-change-account.png", "Title.png", (45, 638, 172, 672), [[1000, 652, 200, 38]]),  # account e-mail
]


def link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], check=True, capture_output=True)
    else:
        dst.symlink_to(src, target_is_directory=True)


def write_masks(templates: Path, evidence: Path) -> None:
    (evidence / "templates").mkdir(parents=True, exist_ok=True)
    masks = []
    for name, screen, crop, boxes in MASKS:
        Image.open(templates / screen).convert("RGB").crop(crop).save(evidence / "templates" / name)
        masks.append({"template": f"templates/{name}", "threshold": 0.8, "boxes": boxes})
    (evidence / "masks.json").write_text(json.dumps({"space": [1280, 720], "masks": masks}, indent=1), encoding="utf-8")


def plan(local: Path, probe: Path | None, unpack: Path | None) -> list[tuple[str, Path, Path]]:
    items = []
    if probe:
        items += [("folder", probe / "archive", local / "archive"), ("masks", probe / "tools/templates", local / "evidence")]
    if unpack:
        items.append(("folder", unpack, local / "unpack"))
    return items


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", type=Path)
    ap.add_argument("--unpack", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--move", action="store_true")
    a = ap.parse_args(argv)
    local = main_checkout() / ".local"
    for kind, src, dst in plan(local, a.probe, a.unpack):
        verb = {"masks": "write masks from", "folder": "move" if a.move else "junction to"}[kind]
        if not src.exists():
            print(f"skip   {dst}: {src} does not exist")
        elif dst.exists() and (kind == "folder" or (dst / "masks.json").exists()):
            print(f"skip   {dst}: exists")
        else:
            print(f"{'do   ' if a.apply else 'would'}  {dst}: {verb} {src}")
            if a.apply and kind == "masks":
                write_masks(src, dst)
            elif a.apply and a.move:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(src, dst)
            elif a.apply:
                link(src, dst)
    if not a.apply:
        print("dry run: add --apply to do it")


if __name__ == "__main__":
    main()
