"""Move data that lives outside the repo into `<main checkout>/.local/`, leaving a link at the old place
(docs/agents/local-dev.md).

  uv run python tools/local_migrate.py [--probe <old probe folder>] [--unpack <unpacked game data>] [--apply]
  uv run python tools/local_migrate.py --remove-links [--apply]

Dry run unless `--apply`. Each folder is copied into `.local/`, the copy is checked (the same files with the
same sizes), the original is renamed aside, a directory junction (a symlink off Windows) takes its place
pointing at the `.local/` copy, and the renamed original is deleted. A task still using the old path keeps
working through the link. When the rename fails (a file in use) the copy is removed and the original stays.
Every link made is recorded in `.local/links.json`; `--remove-links` deletes those links, and only while they
still point into `.local/`, so the data stays in `.local/`. A target that already exists is left alone.

  --probe   its `archive/` moves to `.local/archive/` (with INDEX.md); its `tools/templates/` (full screens
            of the main window and the title screen) yield the privacy-mask templates and
            `.local/evidence/masks.json`, which the `evidence-annotate` skill reads (`--masks`).
  --unpack  moves to `.local/unpack/`: the game data, with `raw/Localize/<lang>/` in it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from local_dir import main_checkout

# Where the account shows, in 1280x720 game space. The template is a button next to it that stays put.
MASKS = [
    # (template file, screen it is cut from, crop box x0 y0 x1 y1, boxes to black out)
    ("main-copy.png", "MainWindow.png", (255, 130, 335, 158), [[55, 126, 200, 36]]),  # UID plate
    # the player name above "LV": bound to the LV label, which every screen with that panel shows (MainWindow, Drive, SinnersTab)
    ("main-lv.png", "MainWindow.png", (30, 647, 54, 665), [[30, 620, 125, 34]]),
    ("title-change-account.png", "Title.png", (45, 638, 172, 672), [[1000, 652, 200, 38]]),  # account e-mail
]
LINKS = "links.json"


def link(src: Path, dst: Path) -> None:
    """Make `dst` a directory link to `src`: a junction on Windows (no admin rights needed), a symlink elsewhere."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], check=True, capture_output=True)
    else:
        dst.symlink_to(src, target_is_directory=True)


def is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())


def unlink_dir(p: Path) -> None:
    """Remove a directory link itself, never what it points at."""
    if p.is_symlink() and not (hasattr(p, "is_junction") and p.is_junction()):
        p.unlink()
    else:
        os.rmdir(p)  # a junction is removed like an empty directory; its target is untouched


def tree(root: Path) -> dict[str, int]:
    """Relative path -> size of every file under root."""
    return {p.relative_to(root).as_posix(): p.stat().st_size for p in root.rglob("*") if p.is_file()}


def move_and_link(src: Path, dst: Path) -> None:
    """Copy src to dst, check it, put a link to dst where src was, then delete the original."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True)
    if tree(src) != tree(dst):
        shutil.rmtree(dst)
        raise RuntimeError(f"copy of {src} differs from the original; nothing changed")
    aside = src.with_name(src.name + ".migrating")
    try:
        src.rename(aside)
    except OSError as e:
        shutil.rmtree(dst)
        raise RuntimeError(f"{src} is in use ({e}); copy removed, original kept") from e
    link(dst, src)
    shutil.rmtree(aside)


def record(local: Path, path: Path) -> None:
    f = local / LINKS
    links = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    if str(path) not in links:
        links.append(str(path))
    f.write_text(json.dumps(links, indent=1), encoding="utf-8")


def remove_links(local: Path, apply: bool) -> None:
    f = local / LINKS
    links = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    kept = []
    for s in links:
        p = Path(s)
        inside = is_link(p) and Path(os.path.realpath(p)).is_relative_to(local.resolve())
        if not inside:
            print(f"skip   {p}: not a link into {local}")
            continue
        print(f"{'remove' if apply else 'would remove'} {p}")
        if apply:
            unlink_dir(p)
        else:
            kept.append(s)
    if apply:
        f.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    if not links:
        print(f"no links recorded in {f}")


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


def migrate(local: Path, probe: Path | None, unpack: Path | None, apply: bool) -> None:
    for kind, src, dst in plan(local, probe, unpack):
        verb = {"masks": "write masks from", "folder": "move here and link back from"}[kind]
        if not src.exists():
            print(f"skip   {dst}: {src} does not exist")
        elif is_link(src):
            print(f"skip   {dst}: {src} is already a link")
        elif dst.exists() and (kind == "folder" or (dst / "masks.json").exists()):
            print(f"skip   {dst}: exists")
        else:
            print(f"{'do   ' if apply else 'would'}  {dst}: {verb} {src}")
            if apply and kind == "masks":
                write_masks(src, dst)
            elif apply:
                move_and_link(src, dst)
                record(local, src)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", type=Path)
    ap.add_argument("--unpack", type=Path)
    ap.add_argument("--remove-links", action="store_true", help="delete the links left at the old places")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    local = main_checkout() / ".local"
    local.mkdir(exist_ok=True)
    if a.remove_links:
        remove_links(local, a.apply)
    else:
        migrate(local, a.probe, a.unpack, a.apply)
    if not a.apply:
        print("dry run: add --apply to do it")


if __name__ == "__main__":
    main()
