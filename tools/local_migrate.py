"""Move data that lives outside the repo into `<main checkout>/.local/`, leaving a link at the old place
(docs/agents/local-dev.md).

  uv run python tools/local_migrate.py [--probe <old probe folder>] [--unpack <unpacked game data>] [--apply]
  uv run python tools/local_migrate.py --remove-links [--apply]

Dry run unless `--apply`. The old place is recorded in `.local/links.json` first, and the record is undone if
the move fails. On the same drive a folder is then renamed into `.local/`. Across drives it is copied to
`<target>.partial`, the copy is checked against the original (the same files with the same sizes and times),
the original is renamed aside to `<name>.migrating` and checked once more against the copy, byte for byte (a
file written in between, or a bad copy, stops the move), and the copy takes its final name. Either way a
directory junction (a symlink off Windows) then takes the old place, pointing into `.local/`, so a task still
using the old path keeps working, and only after that is the original renamed `<name>.deleting` and deleted.
A step that fails puts things back as they were. An interrupted run leaves one of a few states: a rerun
finishes the known ones (an original left `.migrating` or `.deleting` behind a working link, a recorded place
whose link is missing) and stops with a message on the rest (an unchecked `.partial` copy, a `.migrating`
original with no link, a `.local/` target that is itself a link). `--remove-links` deletes the recorded links,
and only while they still point into `.local/`, so the data stays in `.local/`.

  --probe   its `archive/` moves to `.local/archive/` (with INDEX.md); its `tools/templates/` (full screens
            of the main window and the title screen) yield the privacy-mask templates and
            `.local/evidence/masks.json`, which the `evidence-annotate` skill reads (`--masks`).
  --unpack  moves to `.local/unpack/`: the game data, with `raw/Localize/<lang>/` in it.
"""
import argparse
import filecmp
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


def link(target: Path, at: Path) -> None:
    """Make `at` a directory link to `target`: a junction on Windows (no admin rights needed), a symlink elsewhere."""
    at.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(at), str(target)], check=True, capture_output=True)
    else:
        at.symlink_to(target, target_is_directory=True)


def is_link(p: Path) -> bool:
    return p.is_junction() or p.is_symlink()


def points_to(at: Path, target: Path) -> bool:
    return is_link(at) and Path(os.path.realpath(at)) == target.resolve()


def points_into(at: Path, folder: Path) -> bool:
    return is_link(at) and Path(os.path.realpath(at)).is_relative_to(folder.resolve())


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
    """Relative path -> (size, mtime in whole seconds) of every file under root; copy2 keeps both. Fast."""
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (st.st_size, int(st.st_mtime))
    return out


def same_content(a: Path, b: Path) -> bool:
    """The same files with the same sizes and times, and byte for byte the same: checked before the original goes."""
    stats = file_stats(a)
    return stats == file_stats(b) and all(filecmp.cmp(a / n, b / n, shallow=False) for n in stats)


def same_drive(a: Path, b: Path) -> bool:
    return os.stat(a).st_dev == os.stat(b.parent if not b.exists() else b).st_dev


def aside_of(src: Path) -> Path:
    return src.with_name(src.name + ".migrating")  # the original, renamed while the copy is checked


def deleting_of(src: Path) -> Path:
    return src.with_name(src.name + ".deleting")  # the original once the link is in: safe to delete


def partial_of(dst: Path) -> Path:
    return dst.with_name(dst.name + ".partial")  # a copy not yet checked


def leftovers(src: Path, dst: Path) -> list[Path]:
    """The folders an interrupted run can leave behind."""
    return [p for p in (aside_of(src), deleting_of(src), partial_of(dst)) if p.exists()]


# ---------------------------------------------------------------- links.json

def read_links(local: Path) -> list[str]:
    f = local / LINKS
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def write_links(local: Path, links: list[str]) -> None:
    f = local / LINKS
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(links, indent=1), encoding="utf-8")
    os.replace(tmp, f)  # never a half-written file


def record_link(local: Path, path: Path) -> None:
    links = read_links(local)
    if str(path) not in links:
        write_links(local, links + [str(path)])


def forget_link(local: Path, path: Path) -> None:
    links = read_links(local)
    if str(path) in links:
        write_links(local, [s for s in links if s != str(path)])


# ---------------------------------------------------------------- the move

def restore(aside: Path, src: Path, part: Path) -> None:
    """Put the original back and drop the unchecked copy."""
    aside.rename(src)
    remove_tree(part)


def drop_copy(dst: Path) -> None:
    """Remove a copy that will not be used. Renamed to .partial first, so a removal that stops halfway still
    reads as an unchecked copy, never as the finished target."""
    part = partial_of(dst)
    dst.rename(part)
    remove_tree(part)


def link_in(src: Path, dst: Path, undo) -> None:
    """Put the link to dst at src; on failure run `undo` and re-raise."""
    try:
        link(dst, src)
    except (OSError, subprocess.CalledProcessError):
        undo()
        raise


def finish_delete(src: Path, aside: Path) -> None:
    gone = deleting_of(src)
    aside.rename(gone)
    remove_tree(gone)


def move_and_link(src: Path, dst: Path, local: Path) -> None:
    """Put src's data at dst and a link to it at src. Raises with everything back as it was on any failure."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    record_link(local, src)  # first, so a run that stops after the move can always be healed
    try:
        move(src, dst)
    except BaseException:
        if not points_to(src, dst):
            forget_link(local, src)
        raise


def move(src: Path, dst: Path) -> None:
    if same_drive(src, dst):
        src.rename(dst)  # one atomic step; a folder in use fails here and nothing changes
        link_in(src, dst, undo=lambda: dst.rename(src))
        return
    part = partial_of(dst)
    try:
        shutil.copytree(src, part, symlinks=True)
    except BaseException:
        if part.exists():
            remove_tree(part)
        raise
    if file_stats(src) != file_stats(part):
        remove_tree(part)
        raise RuntimeError(f"copy of {src} differs from the original; nothing changed")
    aside = aside_of(src)
    try:
        src.rename(aside)
    except OSError as e:
        remove_tree(part)
        raise RuntimeError(f"{src} is in use ({e}); copy removed, original kept") from e
    if not same_content(aside, part):  # written to between the checks, or a bad copy
        restore(aside, src, part)
        raise RuntimeError(f"{src} changed while it was copied, or the copy is not identical; copy removed, original kept")
    try:
        part.rename(dst)
    except OSError:
        restore(aside, src, part)
        raise

    def undo():
        aside.rename(src)
        drop_copy(dst)
    link_in(src, dst, undo)
    finish_delete(src, aside)


# ---------------------------------------------------------------- reruns

def heal(src: Path, dst: Path, local: Path, apply: bool) -> bool:
    """Finish what an interrupted run left in a known state. True when there was something to finish."""
    did = False
    say = lambda verb, what: print(f"{verb if apply else 'would ' + verb} {what}")  # noqa: E731
    linked = points_to(src, dst)
    for left in (aside_of(src), deleting_of(src)):
        if left.exists() and linked and not partial_of(dst).exists():  # the copy was checked before the link
            say("finish deleting", f"{left}: its data is complete in {dst}")
            if apply:
                finish_delete(src, left) if left == aside_of(src) else remove_tree(left)
            did = True
    if (str(src) in read_links(local) and dst.is_dir() and not is_link(dst) and not os.path.lexists(src)
            and not aside_of(src).exists() and not partial_of(dst).exists()):
        say("relink", f"{src}: its data is in {dst} but the link is missing")
        if apply:
            link(dst, src)
        did = True
    return did


def stop_reason(src: Path, dst: Path) -> str | None:
    """Why an interrupted or unexpected state needs a person, or None."""
    if is_link(dst):
        return (f"{dst} is a link ({os.path.realpath(dst)}), from an older version of this tool. Remove that link "
                f"(the folder it points at stays), then rerun to move the data in.")
    if partial_of(dst).exists():
        return (f"{partial_of(dst)} is an unchecked copy left by an interrupted run; the original is "
                f"{aside_of(src) if aside_of(src).exists() else src}. Delete the copy, put the original back at "
                f"{src} if it was set aside, then rerun.")
    if aside_of(src).exists() and not points_to(src, dst):
        return f"{aside_of(src)} is the original, set aside by an interrupted run. Rename it back to {src}, then rerun."
    return None


def migrate(local: Path, probe: Path | None, unpack: Path | None, apply: bool) -> None:
    for kind, src, dst in plan(local, probe, unpack):
        if kind == "masks":
            if not src.exists():
                print(f"skip   {dst}: {src} does not exist")
            elif (dst / "masks.json").exists():
                print(f"skip   {dst}: exists")
            else:
                print(f"{'do   ' if apply else 'would'}  {dst}: write masks from {src}")
                if apply:
                    write_masks(src, dst)
            continue
        if heal(src, dst, local, apply):
            continue
        if reason := stop_reason(src, dst):
            raise SystemExit("stop: " + reason)
        if not src.exists():
            print(f"skip   {dst}: {src} does not exist")
        elif is_link(src):
            print(f"skip   {dst}: {src} is already a link")
        elif dst.exists():
            print(f"skip   {dst}: exists")
        else:
            print(f"{'do   ' if apply else 'would'}  {dst}: move here and link back from {src}")
            if apply:
                move_and_link(src, dst, local)


def remove_links(local: Path, apply: bool) -> None:
    links, kept = read_links(local), []
    for s in links:
        p = Path(s)
        if not points_into(p, local):
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


def absolute(p: Path | None) -> Path | None:
    """An absolute path as given: links.json must name the same place from any directory, and resolve() would
    follow a link that is already there."""
    return Path(os.path.abspath(p)) if p else None


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
        migrate(local, absolute(a.probe), absolute(a.unpack), a.apply)
    if not a.apply:
        print("dry run: add --apply to do it")


if __name__ == "__main__":
    main()
