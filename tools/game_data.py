"""Bring the repo's game data up to a new client (#625): detect the version, pull, dump, regenerate, diff.

Usage: uv run --group unpack python tools/game_data.py <command> [--serial 127.0.0.1:16384]
  status   the client on the emulator, the one `.local/unpack/` holds and the one the data files carry; exits 1 when
           the emulator's differs from the data files' (a new client to regenerate for), 0 otherwise.
  pull     read-only `adb pull` of what changed into `.local/unpack/incoming/<version>/`: the UnityCache bundles whose
           version folder is new, the Localize folder (en, jp, kr), the Addressables catalog, global-metadata.dat and the
           APKs (their player data unzipped to apk-data/); then dumps the static data of every bundle that holds some
           (the pulled ones and the unchanged ones, by the bundle index out/sprite-index.tsv).
  dump     dumps `.local/unpack/`'s static data again from its bundles, into static/.
  install  moves the pulled files into place; what they replace, and the bundles gone from the device, go to
           `.local/unpack/prev/<old version>/`, and `.local/unpack/client.json` names the version.
  regen    runs every generator (GENERATORS) against `.local/unpack/`; `--release` names the Localize Limbus Company
           release (default: the newest).
  diff     the per-file summary of what regen changed against git HEAD (`--ref`), and of the static data against prev/.
  update   pull and install (unless `.local/unpack/` holds the emulator's version already), then regen and diff.
A step that stops half way leaves nothing a later step takes for whole: each pulled piece is written as `<name>.part` and
renamed once whole, pull writes `incoming/<version>/pulled.json` last, and install checks every destination before it
moves anything. Run pull, regen and update as a `bench` ticket (tools/live/queue.py): the icon and cover generators open
the 12 GB of bundles. Nothing here starts, stops or taps the game; it reads the files of
/sdcard/Android/data/com.ProjectMoon.LimbusCompany/files/ and the installed APKs.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
PACKAGE = "com.ProjectMoon.LimbusCompany"
FILES = f"/sdcard/Android/data/{PACKAGE}/files"
CACHE = f"{FILES}/UnityCache/Shared"
SERIAL = "127.0.0.1:16384"  # MuMu instance 0
STATIC = "static/Assets/Resources_moved/StaticData/static-data"
INDEX = "out/sprite-index.tsv"  # every bundle's container entries (bundle_index)
UNITY_VERSION = "6000.3.12f1"  # the engine in libunity.so (1.117.0 and 1.118.1); the bundles carry a stripped version
LLC_LATEST = "https://api.github.com/repos/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/latest"
# Pulled piece -> its place under .local/unpack/ (the UnityCache bundles go one by one).
PIECES = {"localize": "raw/Localize", "catalog": "raw/addressables", "metadata": "raw/Metadata", "apk": "raw/apk",
          "player": "apk-data", "static": "static"}
# The generators in order (theme packs before their covers, gift_search before gift_recipes, both before the icons):
# (script, whether it takes --release, the Localize Limbus Company release of the Chinese names).
GENERATORS = [("tools/theme_pack_floors.py", False), ("tools/trial_table.py", False), ("tools/events_md8.py", False),
              ("tools/event_table.py", False), ("tools/gift_search_table.py", True), ("tools/gift_recipes.py", True), ("tools/default_gift_list.py", False),
              ("tools/llc_text.py", True), ("tools/gift_icons.py", False), ("tools/grace_icons.py", False), ("tools/theme_pack_covers.py", False),
              ("tools/theme_pack_signatures.py", False), ("tools/sinner_cards.py", False)]
# What regen writes, for diff.
OUTPUTS = ["assets/resource/base/data", "assets/resource/base/image/GiftSearch", "assets/resource/base/image/GiftRecipe",
           "gui/src/graces.json", "gui/src/grace_icons"]


def parse_cache_listing(text: str) -> dict[str, str]:
    """`ls -d */*/` of UnityCache/Shared -> bundle name hash -> its version folder (the device keeps one per bundle)."""
    out = {}
    for line in text.split():
        name, version = line.strip("/").split("/")[:2]
        out[name] = version
    return out


def changed_bundles(device: dict[str, str], local: dict[str, str]) -> list[str]:
    """The bundles the device holds in another version than `local`, or that `local` lacks."""
    return sorted(n for n, v in device.items() if local.get(n) != v)


def client_version(dumpsys: str) -> str:
    return re.search(r"versionName=(\S+)", dumpsys).group(1)


def id_changes(old: dict, new: dict, prefix="") -> dict:
    """Key path ("a.b") -> what changed, for every value that differs: a nested mapping is walked; a list of {"id": ...}
    rows gives the ids added, removed and changed; a list of plain values the values added and removed; anything else
    "added", "removed" or "changed"."""
    out = {}
    for key in sorted(old.keys() | new.keys(), key=str):
        a, b, path = old.get(key), new.get(key), f"{prefix}{key}"
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            out |= id_changes(a, b, path + ".")
        elif rows(a) is not None and rows(b) is not None:
            ra, rb = rows(a), rows(b)
            out[path] = {"added": sorted(rb.keys() - ra.keys()), "removed": sorted(ra.keys() - rb.keys()),
                         "changed": sorted(k for k in ra.keys() & rb.keys() if ra[k] != rb[k])}
        elif plain_list(a) and plain_list(b):
            out[path] = {"added": sorted(set(b) - set(a), key=str), "removed": sorted(set(a) - set(b), key=str)}
        else:
            out[path] = "added" if a is None else "removed" if b is None else "changed"
    return out


def rows(value):
    """A list of {"id": ...} rows by id, else None."""
    if isinstance(value, list) and value and all(isinstance(r, dict) and "id" in r for r in value):
        return {r["id"]: r for r in value}
    return None


def plain_list(value) -> bool:
    return isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value)


# ---- the device


def adb(serial, *args) -> str:
    run = subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode:
        raise SystemExit(f"adb {' '.join(args)} failed: {run.stderr or run.stdout}")
    return run.stdout


def device_client(serial) -> str:
    return client_version(adb(serial, "shell", f"dumpsys package {PACKAGE}"))


def device_cache(serial) -> dict[str, str]:
    return parse_cache_listing(adb(serial, "shell", f"cd {CACHE} && ls -d */*/"))


def local_cache(cache: Path) -> dict[str, str]:
    return {p.parent.parent.name: p.parent.name for p in cache.glob("*/*/__data")}


def fetch(dest: Path, make):
    """`make(part)` writes dest's content at a `.part` path, which becomes dest once whole; a dest that exists is done."""
    if dest.exists():
        return
    part = dest.with_name(dest.name + ".part")
    if part.is_dir():
        shutil.rmtree(part)
    elif part.exists():
        part.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    make(part)
    os.replace(part, dest)


def pull(serial, src, dest: Path):
    """adb pull of a device file or folder to dest, whole or not at all (fetch)."""
    fetch(dest, lambda part: adb(serial, "pull", src, str(part)))


# ---- .local/unpack


def unpack_of(path: Path) -> Path:
    """The unpack folder `path` is in: the nearest one holding client.json, else the main checkout's .local/unpack/."""
    return next((p for p in [Path(path), *Path(path).parents] if (p / "client.json").is_file()), None) or local_dir("unpack")


def unpack_client(unpack: Path) -> str:
    """The client version `.local/unpack/` holds (client.json, written by install)."""
    f = unpack / "client.json"
    if not f.is_file():
        raise SystemExit(f"{f} is missing: write {{\"client\": \"<version>\"}} for the client .local/unpack/ holds")
    return json.loads(f.read_text(encoding="utf-8"))["client"]


def data_client() -> str:
    return json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))["client"]


def bundle_index(cache: Path, index_path: Path) -> list[str]:
    """Every container entry of the bundles under `cache`, one `hash/version<TAB>type<TAB>path` line each, kept in
    `index_path` (out/sprite-index.tsv). A bundle folder the file lacks (the first run reads all ~12 GB; a new client's
    version folders) is read and added, the lines of a folder that is gone are dropped; `hash/version - -` marks a bundle
    as read, entries or not."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    bundles = {f"{p.parent.parent.name}/{p.parent.name}": p for p in Path(cache).glob("*/*/__data")}
    lines = index_path.read_text(encoding="utf-8").splitlines() if index_path.is_file() else []
    kept = [line for line in lines if line.split("\t")[0] in bundles]  # an index of bare `hash` lines (before #625) goes whole
    new = sorted(bundles.keys() - {line.split("\t")[0] for line in kept})
    if new or len(kept) != len(lines):
        for key in new:
            try:
                kept += [f"{key}\t{obj.type.name}\t{p}" for p, obj in UnityPy.load(str(bundles[key])).container.items()]
            except Exception as e:  # a bundle UnityPy cannot read holds none of the files the generators want, as far as we know
                print("skip", key, e, file=sys.stderr)
            kept.append(f"{key}\t-\t-")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    return kept


def static_bundles(index: list[str]) -> set[str]:
    """The `hash/version` keys of the bundles that hold a StaticData TextAsset: the static data is spread over several
    (1.117.0: three, 2185 + 14 + 1 files), and a new client may change only some of them."""
    return {key for key, kind, path in (line.split("\t") for line in index) if kind == "TextAsset" and "staticdata" in path.lower()}


def dump_static(bundles: list[Path], out: Path) -> int:
    """The TextAssets under StaticData of these bundles -> out/Assets/Resources_moved/StaticData/..."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    hits = 0
    for path in bundles:
        try:
            entries = UnityPy.load(str(path)).container.items()
        except Exception as e:  # as in bundle_index: a bundle UnityPy cannot read holds no static data we know of
            print("skip", path, e, file=sys.stderr)
            continue
        for p, obj in entries:
            if "staticdata" in p.lower() and obj.type.name == "TextAsset":
                data = obj.read().m_Script
                dest = out / p.replace("assets/resources_moved/staticdata/", "Assets/Resources_moved/StaticData/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data.encode("utf-8", "surrogateescape") if isinstance(data, str) else data)
                hits += 1
    return hits


def cmd_status(args):
    unpack = local_dir("unpack")
    device, held, data = device_client(args.serial), unpack_client(unpack), data_client()
    changed = changed_bundles(device_cache(args.serial), local_cache(unpack / "raw/UnityCache"))
    print(f"emulator {device}, .local/unpack {held}, data files {data}; {len(changed)} bundles differ from .local/unpack")
    return 0 if device == data else 1


def cmd_pull(args):
    unpack = local_dir("unpack")
    version = device_client(args.serial)
    if version == unpack_client(unpack) and not args.force:
        print(f".local/unpack/ holds {version} already: nothing to pull (--force pulls the changed bundles all the same)")
        return 1
    incoming, cache = unpack / "incoming" / version, unpack / "raw/UnityCache"
    device, local = device_cache(args.serial), local_cache(cache)
    changed, gone = changed_bundles(device, local), sorted(local.keys() - device.keys())
    print(f"client {version}: {len(changed)} changed bundles, {len(gone)} gone from the device -> {incoming}")
    for name in changed:
        pull(args.serial, f"{CACHE}/{name}/{device[name]}", incoming / "raw/UnityCache" / name / device[name])
    for key, src in (("localize", f"{FILES}/Assets/Resources_moved/Localize"), ("catalog", f"{FILES}/com.unity.addressables"),
                     ("metadata", f"{FILES}/il2cpp/Metadata")):
        pull(args.serial, src, incoming / PIECES[key])
    for apk in (line.removeprefix("package:").strip() for line in adb(args.serial, "shell", f"pm path {PACKAGE}").splitlines()):
        if apk:
            pull(args.serial, apk, incoming / PIECES["apk"] / apk.rsplit("/", 1)[-1])

    def unzip(part):
        for apk in sorted((incoming / PIECES["apk"]).glob("*.apk")):
            with zipfile.ZipFile(apk) as z:
                z.extractall(part, [n for n in z.namelist() if n.startswith("assets/bin/Data/")])

    fetch(incoming / PIECES["player"], unzip)
    unchanged = [cache / key / "__data" for key in sorted(static_bundles(bundle_index(cache, unpack / INDEX)))
                 if key.split("/")[0] not in {*changed, *gone}]
    pulled = sorted((incoming / "raw/UnityCache").glob("*/*/__data"))

    def dump(part):
        print(f"static data: {dump_static(unchanged + pulled, part)} files from {len(unchanged)} unchanged and the "
              f"{len(pulled)} pulled bundles")

    fetch(incoming / PIECES["static"], dump)
    (incoming / "pulled.json").write_text(json.dumps({"client": version, "bundles": changed, "gone": gone,
                                                      "date": datetime.date.today().isoformat()}, indent=1) + "\n", encoding="utf-8")
    return 0


def cmd_dump(args):
    """Dump the static data of `.local/unpack/`'s bundles again, into static/ (what pull does for a new client)."""
    unpack = local_dir("unpack")
    cache, fresh = unpack / "raw/UnityCache", unpack / "static.new"
    keys = sorted(static_bundles(bundle_index(cache, unpack / INDEX)))
    if fresh.exists():
        shutil.rmtree(fresh)
    n = dump_static([cache / key / "__data" for key in keys], fresh)
    shutil.rmtree(unpack / PIECES["static"])
    os.replace(fresh, unpack / PIECES["static"])
    print(f"static data: {n} files from {len(keys)} bundles")
    return 0


def install_moves(unpack: Path, incoming: Path, prev: Path, info: dict) -> list[tuple[Path, Path]]:
    """The renames install makes, in order: each replaced piece or bundle to prev/ before the pulled one takes its place,
    and the bundles gone from the device to prev/."""
    moves = []
    for rel in PIECES.values():
        if (incoming / rel).exists():
            moves += [(unpack / rel, prev / rel), (incoming / rel, unpack / rel)]
    for name in info["bundles"]:
        moves += [(unpack / "raw/UnityCache" / name, prev / "raw/UnityCache" / name),
                  (incoming / "raw/UnityCache" / name, unpack / "raw/UnityCache" / name)]
    moves += [(unpack / "raw/UnityCache" / name, prev / "raw/UnityCache" / name) for name in info.get("gone", [])]
    return [(a, b) for a, b in moves if a.exists()]


def cmd_install(args):
    unpack = local_dir("unpack")
    pulled = list((unpack / "incoming").glob("*/pulled.json"))
    if len(pulled) != 1:
        raise SystemExit("nothing pulled: run `game_data.py pull` first" if not pulled else
                         f"{len(pulled)} pulls under {unpack / 'incoming'}: keep the one to install, move the others away")
    info = json.loads(pulled[0].read_text(encoding="utf-8"))
    incoming, old = pulled[0].parent, unpack_client(unpack)
    prev = unpack / "prev" / old
    moves = install_moves(unpack, incoming, prev, info)
    vacated = {a for a, _ in moves}
    taken = [b for _, b in moves if b.exists() and b not in vacated]
    if taken:
        raise SystemExit(f"nothing installed: {taken[0]} exists already ({len(taken)} in all); move them away first")
    for a, b in moves:
        b.parent.mkdir(parents=True, exist_ok=True)
        os.replace(a, b)
    (unpack / "client.json").write_text(json.dumps({"client": info["client"], "installed": datetime.date.today().isoformat(),
                                                    "previous": old, "bundles": info["bundles"], "gone": info.get("gone", [])},
                                                   indent=1) + "\n", encoding="utf-8")
    shutil.rmtree(incoming)
    print(f"installed {info['client']} in {unpack}; the replaced files of {old} are in {prev}")
    return 0


def latest_release() -> str:
    with urllib.request.urlopen(urllib.request.Request(LLC_LATEST, headers={"User-Agent": "maalc-game-data"}), timeout=30) as r:
        return json.load(r)["tag_name"]


def cmd_regen(args):
    release = args.release or latest_release()
    for script, takes_release in GENERATORS:
        command = [script, *(["--release", release] if takes_release else [])]
        print("==", " ".join(command), flush=True)
        if code := subprocess.run(["uv", "run", "--group", "unpack", "python", *command], cwd=REPO).returncode:
            raise SystemExit(f"{script} failed ({code})")
    return 0


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def cmd_diff(args):
    for line in summary(args.ref):
        print(line)
    unpack = local_dir("unpack")
    previous = json.loads((unpack / "client.json").read_text(encoding="utf-8")).get("previous")
    prev = unpack / "prev" / str(previous)
    if previous and (prev / STATIC).is_dir():
        print(static_summary(prev / STATIC, unpack / STATIC))
    return 0


def summary(ref) -> list[str]:
    """One line per changed output file: what id_changes finds in a JSON or YAML table, else line counts; counts of the
    image folders."""
    status = git("status", "--porcelain", "--untracked-files=all", "--", *OUTPUTS).splitlines()
    status += [f" M {p}" for p in git("diff", "--name-only", ref, "--", *OUTPUTS).splitlines()]
    paths = sorted({line[3:].strip().strip('"') for line in status})
    lines, images = [], {}
    for p in paths:
        if p.endswith((".png", ".webp")):
            folder = p.rsplit("/", 1)[0]
            kind = "added" if not exists_at(ref, p) else "removed" if not (REPO / p).exists() else "changed"
            images.setdefault(folder, {}).setdefault(kind, []).append(Path(p).stem)
            continue
        if (what := describe(ref, p)) is not None:
            lines.append(f"{p}: {what}")
    for folder, kinds in sorted(images.items()):
        lines.append(f"{folder}: " + ", ".join(f"{k} {len(v)} {short(sorted(v))}" for k, v in sorted(kinds.items())))
    return lines


def exists_at(ref, path) -> bool:
    return subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{ref}:{path}"], capture_output=True).returncode == 0


def describe(ref, path) -> str | None:
    """What changed in one text file; None when only its line endings did."""
    new = (REPO / path).read_text(encoding="utf-8") if (REPO / path).exists() else None
    old = git("show", f"{ref}:{path}") if exists_at(ref, path) else None
    if old is None or new is None:
        return "added" if old is None else "removed"
    if path.endswith((".json", ".yaml")):
        import yaml

        a, b = (json.loads(t) if path.endswith(".json") else yaml.safe_load(t) for t in (old, new))
        if isinstance(a, dict) and isinstance(b, dict):
            return "; ".join(f"{k} {v}" if isinstance(v, str) else
                             f"{k}: " + ", ".join(f"{n} {len(ids)} {short(ids)}" for n, ids in v.items() if ids)
                             for k, v in id_changes(a, b).items()) or None
    stat = git("diff", "--numstat", ref, "--", path).split()
    return f"+{stat[0]} -{stat[1]} lines" if stat else None


def short(ids) -> str:
    return "[" + " ".join(map(str, ids[:12])) + (" ..." if len(ids) > 12 else "") + "]"


def static_summary(old: Path, new: Path) -> str:
    a = {p.relative_to(old).as_posix(): p for p in old.rglob("*.json")}
    b = {p.relative_to(new).as_posix(): p for p in new.rglob("*.json")}
    changed = sorted(k for k in a.keys() & b.keys() if a[k].read_bytes() != b[k].read_bytes())
    return (f"static data: {len(b)} files, added {len(b.keys() - a.keys())} {sorted(b.keys() - a.keys())}, "
            f"removed {len(a.keys() - b.keys())} {sorted(a.keys() - b.keys())}, changed {len(changed)} {changed}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["status", "pull", "dump", "install", "regen", "diff", "update"])
    ap.add_argument("--serial", default=SERIAL)
    ap.add_argument("--release", help="the Localize Limbus Company release for the Chinese names (default: the newest)")
    ap.add_argument("--ref", default="HEAD", help="diff against this git ref")
    ap.add_argument("--force", action="store_true", help="pull although .local/unpack/ holds the emulator's version")
    args = ap.parse_args(argv)
    if args.command == "update":
        if args.force or device_client(args.serial) != unpack_client(local_dir("unpack")):
            if cmd_pull(args) == 0:
                cmd_install(args)
        else:
            print(".local/unpack/ holds the emulator's client already: nothing to pull; regenerating")
        cmd_regen(args)
        return cmd_diff(args)
    return {"status": cmd_status, "pull": cmd_pull, "dump": cmd_dump, "install": cmd_install, "regen": cmd_regen,
            "diff": cmd_diff}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
