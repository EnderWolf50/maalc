"""A fake maalc-resource and an install to update from it, for the tests of agent/resource_update.py (#771).

The remote is a folder laid out as the real one: `main/manifest.json` and `<version>/<path>` for each file of a version.
The install's own manifest lists that folder as its source, so no test needs the network or a switch in the agent.
"""

import hashlib
import json
from pathlib import Path


def manifest_of(files: dict, version: str, *, format=1, template=1, client="1.118.1", sources=()) -> dict:
    return {"version": version, "client": client, "format": format, "template": template, "sources": list(sources),
            "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())}}


def write_files(root: Path, files: dict) -> None:
    for name, data in files.items():
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def install(base: Path, files: dict, version: str, sources, **fields) -> dict:
    """An installed package: `files` under `base` and the manifest that describes them."""
    write_files(base, files)
    manifest = manifest_of(files, version, sources=sources, **fields)
    Path(base, "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def publish(remote: Path, files: dict, version: str, **fields) -> dict:
    """A publish: the files of `version` and `main/manifest.json` pointing at it."""
    write_files(Path(remote) / version, files)
    manifest = manifest_of(files, version, **fields)
    (Path(remote) / "main").mkdir(parents=True, exist_ok=True)
    Path(remote, "main", "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def tree(base: Path) -> dict:
    """{POSIX path: bytes} of every file under `base`: what a test compares before and after an update."""
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(Path(base).rglob("*")) if p.is_file()}
