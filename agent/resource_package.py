"""The resource package the program runs on (ADR 0012, spec #759): the versions it knows and the manifest helpers the
agent and tools/build_resource_package.py share. Stdlib only: the release's bundled Python imports it.

The package is `data/`, `image/` and `pipeline/` of `resource/base/` and a `manifest.json` at its root. FORMAT covers
`data/`, TEMPLATE `image/` and `pipeline/`; the program applies a package part only when its version is the one it knows.
"""

import hashlib
import json
from pathlib import Path

FORMAT = 1  # 格式版本: the structure of the files under data/
TEMPLATE = 4  # 模板版本: the template images and the pipeline, which go with this agent and assets/interface.json
SOURCES = ["https://raw.githubusercontent.com/EnderWolf50/maalc-resource"]  # the list the release zip's manifest carries
MANIFEST = "manifest.json"
PARTS = ("data", "image", "pipeline")  # the folders of the package; `model/` is not one


class ManifestError(ValueError):
    pass


def version_key(version: str) -> tuple[int, ...]:
    """`2026.11.16` -> (2026, 11, 16); the second publish of a day, `2026.11.16.2`, is greater than the first."""
    try:
        return tuple(int(part) for part in version.split("."))
    except (ValueError, AttributeError):
        raise ValueError(f"not a version (dotted numbers): {version!r}") from None


def is_newer(remote: str, local: str) -> bool:
    return version_key(remote) > version_key(local)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def check_manifest(manifest) -> dict:
    """The manifest when it has every field the program reads, else a ManifestError naming the first one that is wrong."""
    if not isinstance(manifest, dict):
        raise ManifestError(f"{MANIFEST} is not an object")
    for key, kind in (("version", str), ("client", str), ("format", int), ("template", int), ("sources", list), ("files", dict)):
        if not isinstance(manifest.get(key), kind) or isinstance(manifest.get(key), bool):
            raise ManifestError(f"{MANIFEST}: {key} is missing or not a {kind.__name__}")
    try:
        version_key(manifest["version"])
    except ValueError as e:
        raise ManifestError(f"{MANIFEST}: version: {e}") from None
    return manifest


def read_manifest(base: Path) -> dict | None:
    """The manifest in `base` (the folder of `data/`), None when there is none; ManifestError when it is not one."""
    path = Path(base) / MANIFEST
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ManifestError(f"{MANIFEST} cannot be read: {e}") from None
    return check_manifest(manifest)


def log_line(base: Path) -> str:
    """The line TaskStart logs: the package `base` holds. Never raises: a task must start without one."""
    try:
        manifest = read_manifest(base)
    except ManifestError as e:
        return f"resource package: unreadable ({e})"
    if manifest is None:
        return f"resource package: none (no {MANIFEST})"
    return (f"resource package: version {manifest['version']}, client {manifest['client']}, "
            f"format {manifest['format']}, template {manifest['template']}")
