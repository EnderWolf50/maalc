"""Free disk space taken by machine-local evidence under `.local/`. Every subcommand is a dry run until `--apply`.

  uv run python tools/local_clean.py usage <dir> [--top N]
  uv run python tools/local_clean.py dedupe <root> [--min-mb 1] [--apply]
  uv run python tools/local_clean.py shrink <root> [--keep <folder>...] [--recent-hours 24] [--limit N] [--apply]
  uv run python tools/local_clean.py prune <archive> [--days 7] [--apply]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path

SHRINK_HEIGHT = 720
SHRINK_MIN_BPS = 2e6
DURATION_TOLERANCE_S = 1.0


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


# ---- usage ----

def tree_size(path: Path) -> int:
    """Bytes under `path`; a link inside it is not followed."""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not is_link(here / d)]
        for name in filenames:
            try:
                total += (here / name).stat().st_size
            except OSError:
                pass
    return total


def usage(directory: Path, top: int = 15) -> list[tuple[int, str, float]]:
    rows = [(tree_size(p), p.name, p.stat().st_mtime) for p in directory.iterdir() if not is_link(p)]
    return sorted(rows, reverse=True)[:top]


def cmd_usage(a: argparse.Namespace) -> None:
    for size, name, mtime in usage(a.dir, a.top):
        print(f"{size / 1e9:8.2f} GB  {time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))}  {name}")


# ---- dedupe ----

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def relink(keep: Path, dup: Path) -> None:
    """Make `dup` a hard link to `keep`'s data, through a temp name so `dup` never goes missing."""
    tmp = dup.with_name(dup.name + ".linktmp")
    tmp.unlink(missing_ok=True)
    os.link(keep, tmp)
    os.replace(tmp, dup)


def dedupe(root: Path, min_bytes: float = 1e6, apply: bool = False) -> list[tuple[int, Path, Path]]:
    """(size, duplicate, kept) for each byte-identical file that is not yet the same inode as the kept one."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            size = p.stat().st_size
            if size >= min_bytes:
                by_size[size].append(p)
    found = []
    for size, paths in by_size.items():
        inodes: dict[tuple[int, int], Path] = {}
        for p in paths:
            st = p.stat()
            inodes.setdefault((st.st_dev, st.st_ino), p)
        if len(inodes) < 2:
            continue
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for p in inodes.values():
            by_hash[sha256(p)].append(p)
        for group in by_hash.values():
            keep, *dups = sorted(group, key=lambda q: (len(str(q)), str(q)))
            for d in dups:
                found.append((size, d, keep))
                if apply:
                    relink(keep, d)
    return found


def cmd_dedupe(a: argparse.Namespace) -> None:
    found = dedupe(a.root, a.min_mb * 1e6, a.apply)
    for size, dup, keep in found:
        print(f"{size / 1e9:7.2f} GB  {dup}  ->  {keep}")
    print(f"{'saved' if a.apply else 'would save'} {sum(s for s, _, _ in found) / 1e9:.1f} GB")


# ---- shrink ----

def qualifies(height: int, duration: float, size: int) -> bool:
    """Above 720p and above 2 Mbps."""
    return height > SHRINK_HEIGHT and duration > 0 and size * 8 / duration >= SHRINK_MIN_BPS


def should_replace(src_duration: float, src_size: int, out_duration: float, out_size: int) -> bool:
    return abs(out_duration - src_duration) <= DURATION_TOLERANCE_S and out_size < src_size


def is_kept(paths: list[Path], keep: list[str]) -> bool:
    return any(k in part for p in paths for part in p.parts for k in keep)


def probe(path: Path) -> dict | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=height:format=duration,size", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        return {"h": int(j["streams"][0]["height"]), "dur": float(j["format"]["duration"]),
                "size": int(j["format"]["size"])}
    except (KeyError, IndexError, ValueError):
        return None


def encode(src: Path, tmp: Path) -> int:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a?", "-vf", f"scale_cuda=-2:{SHRINK_HEIGHT}",
           "-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "28", "-b:v", "0",
           "-c:a", "copy", "-movflags", "+faststart", str(tmp)]
    return subprocess.run(cmd).returncode


def cmd_shrink(a: argparse.Namespace) -> None:
    cut = time.time() - a.recent_hours * 3600
    by_inode: dict[tuple[int, int], list[Path]] = defaultdict(list)
    for p in a.root.rglob("*.mp4"):
        st = p.stat()
        by_inode[(st.st_dev, st.st_ino)].append(p)

    jobs = []
    for paths in by_inode.values():
        if is_kept(paths, a.keep):
            continue
        src = paths[0]
        if src.stat().st_mtime > cut:
            continue
        info = probe(src)
        if not info or not qualifies(info["h"], info["dur"], info["size"]):
            continue
        jobs.append((info["size"], src, paths, info))
    jobs.sort(key=lambda j: j[0], reverse=True)
    if a.limit:
        jobs = jobs[: a.limit]

    before = after = 0
    for size, src, paths, info in jobs:
        print(f"{size / 1e9:6.2f} GB  {info['h']}p  {info['dur'] / 60:6.1f} min  x{len(paths)}  {src}", flush=True)
        if not a.apply:
            before += size
            continue
        tmp = src.with_name(src.stem + ".shrink.mp4")
        rc = encode(src, tmp)
        out = probe(tmp) if rc == 0 and tmp.exists() else None
        if not out or not should_replace(info["dur"], size, out["dur"], out["size"]):
            print(f"   SKIP (rc={rc}, out={out})", flush=True)
            tmp.unlink(missing_ok=True)
            continue
        st = src.stat()
        os.utime(tmp, (st.st_atime, st.st_mtime))
        os.replace(tmp, src)
        for other in paths[1:]:
            relink(src, other)
        before += size
        after += out["size"]
        print(f"   -> {out['size'] / 1e9:.2f} GB", flush=True)
    print(f"{'done' if a.apply else 'plan'}: {len(jobs)} files, {before / 1e9:.1f} GB"
          + (f" -> {after / 1e9:.1f} GB" if a.apply else ""), flush=True)


# ---- prune ----

def gh_states() -> dict[int, str]:
    """Issue and PR number -> `open` / `closed` / `merged` from gh."""
    states: dict[int, str] = {}
    for kind in ("issue", "pr"):
        r = subprocess.run(["gh", kind, "list", "--state", "all", "--limit", "1000", "--json", "number,state"],
                           capture_output=True, text=True, encoding="utf-8", check=True)
        for item in json.loads(r.stdout):
            states[item["number"]] = item["state"].lower()
    return states


def mentions(name: str, line: str) -> bool:
    return re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", line) is not None


def issue_refs(name: str, index_lines: list[str]) -> list[int]:
    """Issue/PR numbers of the INDEX.md rows that name the folder."""
    nums = {int(n) for line in index_lines if line.startswith("|") and mentions(name, line)
            for n in re.findall(r"#(\d+)", line)}
    return sorted(nums)


class Folder:
    def __init__(self, name: str, age_days: float, size: int, refs: list[int], open_refs: list[int]):
        self.name, self.age_days, self.size, self.refs, self.open_refs = name, age_days, size, refs, open_refs


def archive_folders(archive: Path, states: dict[int, str], now: float | None = None) -> list[Folder]:
    now = now or time.time()
    index = archive / "INDEX.md"
    lines = index.read_text(encoding="utf-8").splitlines() if index.exists() else []
    folders = []
    for d in sorted(p for p in archive.iterdir() if p.is_dir() and not is_link(p)):
        files = [f for f in d.rglob("*") if f.is_file()]
        newest = max((f.stat().st_mtime for f in files), default=d.stat().st_mtime)
        refs = issue_refs(d.name, lines)
        folders.append(Folder(d.name, (now - newest) / 86400, sum(f.stat().st_size for f in files), refs,
                              [n for n in refs if states.get(n) == "open"]))
    return sorted(folders, key=lambda f: -f.size)


def deletable(f: Folder, days: float) -> bool:
    return f.name != "recordings" and f.age_days > days and not f.open_refs


def prune(archive: Path, days: float = 7, apply: bool = False,
          states: Callable[[], dict[int, str]] = gh_states) -> list[Folder]:
    folders = archive_folders(archive, states())
    for f in folders:
        why = "kept" if not deletable(f, days) else "delete"
        open_note = " open:" + ",".join(f"#{n}" for n in f.open_refs) if f.open_refs else ""
        refs = " ".join(f"#{n}" for n in f.refs)
        print(f"{why:6}  {f.size / 1e9:6.2f} GB  {f.age_days:6.1f} d  {f.name}  [{refs}]{open_note}")
    doomed = [f for f in folders if deletable(f, days)]
    print(f"{len(doomed)} folders, {sum(f.size for f in doomed) / 1e9:.1f} GB (hard links counted per path)")
    if apply and doomed:
        index = archive / "INDEX.md"
        tag = f"（{date.today().isoformat()} 已刪除：超過 {days:g} 天且無開啟中的 issue）"
        if index.exists():
            lines = index.read_text(encoding="utf-8").splitlines()
            lines = [ln + tag if ln.startswith("|") and tag not in ln and any(mentions(f.name, ln) for f in doomed)
                     else ln for ln in lines]
            index.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for f in doomed:
            shutil.rmtree(archive / f.name)
        print("deleted")
    return doomed


def cmd_prune(a: argparse.Namespace) -> None:
    prune(a.archive, a.days, a.apply)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("usage", help="sizes of the items in a folder, largest first")
    p.add_argument("dir", type=Path)
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(fn=cmd_usage)

    p = sub.add_parser("dedupe", help="replace byte-identical files with hard links")
    p.add_argument("root", type=Path)
    p.add_argument("--min-mb", type=float, default=1.0)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_dedupe)

    p = sub.add_parser("shrink", help="re-encode mp4 above 720p and 2 Mbps to 720p HEVC (NVENC)")
    p.add_argument("root", type=Path)
    p.add_argument("--keep", action="append", default=[], help="folder name to leave untouched; repeatable")
    p.add_argument("--recent-hours", type=float, default=24)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_shrink)

    p = sub.add_parser("prune", help="delete old archive folders with no open issue or PR")
    p.add_argument("archive", type=Path)
    p.add_argument("--days", type=float, default=7)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_prune)
    return ap


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = build_parser().parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
