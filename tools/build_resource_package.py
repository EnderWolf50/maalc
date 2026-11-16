"""Build the resource package's manifest, and the package itself (ADR 0012, #766).

Usage: uv run python tools/build_resource_package.py [--base assets/resource/base] [--out <folder>] [--version YYYY.MM.DD]
                                                      [--client <game client>] [--source <url> ...]

Without --out the manifest.json is written into --base (what tools/install.py does for install/resource/base). With --out
the package is built there: data/, image/ and pipeline/ copied from --base, plus manifest.json; the model/ folder of the
OCR model is not part of it. An --out that is a checkout (maalc-resource) keeps its own files, such as .git. The
manifest is generated, never committed in maalc.

The version is the publish date, YYYY.MM.DD (the second publish of a day is YYYY.MM.DD.2, given with --version); the client
version is read from data/client.json, which `tools/game_data.py regen` writes. --source defaults to the program's own list,
`resource_package.SOURCES`; `--no-sources` writes an empty list, which turns updates off (a dev install).
"""

import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))
import resource_package as rp  # noqa: E402

BASE = REPO / "assets" / "resource" / "base"
CLIENT = "client.json"  # data/: the game client the data came from


def package_files(base: Path) -> dict[str, Path]:
    """POSIX path under `base` -> file, for every file of data/, image/ and pipeline/, sorted."""
    found = {}
    for part in rp.PARTS:
        for path in (Path(base) / part).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                found[path.relative_to(base).as_posix()] = path
    return dict(sorted(found.items()))


def data_client(base: Path) -> str:
    f = Path(base) / "data" / CLIENT
    if not f.is_file():
        raise SystemExit(f"{f} is missing: `tools/game_data.py regen` writes the game client version there (or pass --client)")
    return json.loads(f.read_text(encoding="utf-8"))["client"]


def today() -> str:
    return datetime.date.today().strftime("%Y.%m.%d")


def build_manifest(base: Path, version: str, sources: list[str], client: str | None = None) -> dict:
    rp.version_key(version)
    files = {name: {"size": path.stat().st_size, "sha256": rp.sha256_file(path)} for name, path in package_files(base).items()}
    return {"version": version, "client": client or data_client(base), "format": rp.FORMAT, "template": rp.TEMPLATE,
            "sources": list(sources), "files": files}


def dump(manifest: dict, dst: Path) -> None:
    """Whole or not at all: a reader never sees half a manifest."""
    part = dst.with_name(dst.name + ".part")
    part.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    os.replace(part, dst)


def write_manifest(base: Path, version: str, sources: list[str], client: str | None = None) -> dict:
    """manifest.json in `base`, from the files `base` holds."""
    manifest = build_manifest(base, version, sources, client)
    dump(manifest, Path(base) / rp.MANIFEST)
    return manifest


def build_package(base: Path, out: Path, version: str, sources: list[str], client: str | None = None) -> dict:
    """The package in `out`: each of data/, image/ and pipeline/ replaced by `base`'s, then manifest.json."""
    manifest = build_manifest(base, version, sources, client)
    out = Path(out)
    for part in rp.PARTS:
        shutil.rmtree(out / part, ignore_errors=True)
    (out / rp.MANIFEST).unlink(missing_ok=True)
    for name, path in package_files(base).items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out / name)
    dump(manifest, out / rp.MANIFEST)
    return manifest


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, default=BASE, help="the resource/base folder to take the package from")
    ap.add_argument("--out", type=Path, help="build the package here instead of writing manifest.json into --base")
    ap.add_argument("--version", default=today())
    ap.add_argument("--client", help="the game client version (default: data/client.json)")
    ap.add_argument("--source", action="append", dest="sources", help="a download source; repeatable")
    ap.add_argument("--no-sources", action="store_true", help="an empty source list: updates off")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    sources = [] if args.no_sources else args.sources or rp.SOURCES
    build = build_package if args.out else write_manifest
    manifest = build(args.base, *([args.out] if args.out else []), version=args.version, sources=sources, client=args.client)
    print(f"{manifest['version']}: {len(manifest['files'])} files, client {manifest['client']}, "
          f"format {manifest['format']}, template {manifest['template']}")
