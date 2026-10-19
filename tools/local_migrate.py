"""Move data that lives outside the repo into `<main checkout>/.local/`, leaving a link at the old place
(docs/agents/local-dev.md).

  uv run python tools/local_migrate.py [--probe <old probe folder>] [--unpack <unpacked game data>] [--apply]
  uv run python tools/local_migrate.py --remove-links [--apply]

Dry run unless `--apply`. On the same drive a folder is renamed into `.local/`. Across drives it is copied to
`<target>.partial`, the copy is checked against the original (the same files with the same sizes and times),
the original is renamed aside to `<name>.migrating` and checked once more against the copy (a file written
in between stops the move), the copy takes its final name, and only then is the original deleted. Either way
a directory junction (a symlink off Windows) is left at the old place, pointing into `.local/`, so a task still
using the old path keeps working, and each link is recorded in `.local/links.json`. Every step that fails
puts things back as they were. A `.partial` or `.migrating` folder left by an interrupted run stops the tool
with a message instead of being guessed at. `--remove-links` deletes the recorded links, and only while they
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
import stat
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
    return p.is_junction() or p.is_symlink()


def unlink_dir(p: Path) -> None:
    """Remove a directory link itself, never what it points at."""
    if p.is_junction():
        os.rmdir(p)  # a junction is removed like an empty directory; its target is untouched
    else:
        p.unlink()


def force_writable(func, path, _exc) -> None:
    """rmtree's onexc: Windows refuses to delete a read-only file, so clear the flag and retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(p: Path) -> None:
    shutil.rmtree(p, onexc=force_writable)


def file_stats(root: Path) -> dict[str, tuple[int, int]]:
    """Relative path -> (size, mtime in whole seconds) of every file under root; copy2 keeps both."""
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_size, int(st.st_mtime))
    return out


def same_drive(a: Path, b: Path) -> bool:
    return os.stat(a).st_dev == os.stat(b.parent if not b.exists() else b).st_dev


def leftovers(src: Path, dst: Path) -> list[Path]:
    return [p for p in (src.with_name(src.name + ".migrating"), dst.with_name(dst.name + ".partial")) if p.exists()]


def move_and_link(src: Path, dst: Path, local: Path) -> None:
    """Put src's data at dst and a link to it at src. Raises with everything back as it was on any failure."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if same_drive(src, dst):
        src.rename(dst)  # one atomic step; a folder in use fails here and nothing changes
        try:
            link(dst, src)
        except (OSError, subprocess.CalledProcessError):
            dst.rename(src)
            raise
        record_link(local, src)
        return
    partial = dst.with_name(dst.name + ".partial")
    try:
        shutil.copytree(src, partial, symlinks=True)
    except BaseException:
        if partial.exists():
            remove_tree(partial)
        raise
    if file_stats(src) != file_stats(partial):
        remove_tree(partial)
        raise RuntimeError(f"copy of {src} differs from the original; nothing changed")
    aside = src.with_name(src.name + ".migrating")
    try:
        src.rename(aside)
    except OSError as e:
        remove_tree(partial)
        raise RuntimeError(f"{src} is in use ({e}); copy removed, original kept") from e
    if file_stats(aside) != file_stats(partial):  # written to between the check and the rename
        aside.rename(src)
        remove_tree(partial)
        raise RuntimeError(f"{src} changed while it was copied; copy removed, original kept")
    partial.rename(dst)
    try:
        link(dst, src)
    except (OSError, subprocess.CalledProcessError):
        aside.rename(src)
        remove_tree(dst)
        raise
    record_link(local, src)
    remove_tree(aside)


def read_links(local: Path) -> list[str]:
    f = local / LINKS
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def write_links(local: Path, links: list[str]) -> None:
    (local / LINKS).write_text(json.dumps(links, indent=1), encoding="utf-8")


def record_link(local: Path, path: Path) -> None:
    links = read_links(local)
    if str(path) not in links:
        write_links(local, links + [str(path)])


def remove_links(local: Path, apply: bool) -> None:
    links, kept = read_links(local), []
    for s in links:
        p = Path(s)
        if not (is_link(p) and Path(os.path.realpath(p)).is_relative_to(local.resolve())):
            print(f"skip   {p}: not a link into {local} (kept in {LINKS})")
            kept.append(s)
            continue
        print(f"{'remove' if apply else 'would remove'} {p}")
        if apply:
            unlink_dir(p)
        else:
            kept.append(s)
    if apply and links:
        write_links(local, kept)
    if not links:
        print(f"no links recorded in {local / LINKS}")


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
        if kind == "folder" and (left := leftovers(src, dst)):
            raise SystemExit(f"stop: an interrupted run left {', '.join(map(str, left))}; the original is the "
                             f"`.migrating` folder if there is one. Put it back by hand, then rerun.")
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
                move_and_link(src, dst, local)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", type=Path)
    ap.add_argument("--unpack", type=Path)
    ap.add_argument("--remove-links", action="store_true", help="delete the links left at the old places")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    local = main_checkout() / ".local"
    if a.apply:
        local.mkdir(exist_ok=True)
    if a.remove_links:
        remove_links(local, a.apply)
    else:
        migrate(local, a.probe, a.unpack, a.apply)
    if not a.apply:
        print("dry run: add --apply to do it")


if __name__ == "__main__":
    main()
