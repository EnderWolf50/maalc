"""tools/build_resource_package.py (#766): the manifest and the package built from assets/resource/base."""

import hashlib
import json

import pytest

import build_resource_package as brp
import resource_package as rp
from install import repo


def make_base(root):
    """A resource/base with the three package folders, an OCR model and a manifest left over from an earlier build."""
    for name, data in {"data/a.json": b'{"client": "1"}', "data/sub/b.png": b"\x89PNG", "image/x/c.png": b"cc",
                       "pipeline/p.json": b"{}", "model/ocr/det.onnx": b"model", "manifest.json": b"old"}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def build(base, **kw):
    return brp.build_manifest(base, **{"version": "2026.11.16", "client": "1.118.1", "sources": ["https://example.test/r"], **kw})


def test_the_manifest_lists_every_package_file_with_size_and_sha256_and_never_the_model(tmp_path):
    manifest = build(make_base(tmp_path))
    assert list(manifest["files"]) == ["data/a.json", "data/sub/b.png", "image/x/c.png", "pipeline/p.json"]  # sorted, POSIX
    assert manifest["files"]["image/x/c.png"] == {"size": 2, "sha256": hashlib.sha256(b"cc").hexdigest()}


def test_the_manifest_carries_the_versions_the_client_and_the_sources(tmp_path):
    manifest = build(make_base(tmp_path))
    assert {k: manifest[k] for k in ("version", "client", "format", "template", "sources")} == {
        "version": "2026.11.16", "client": "1.118.1", "format": rp.FORMAT, "template": rp.TEMPLATE,
        "sources": ["https://example.test/r"]}
    assert rp.check_manifest(manifest) is manifest


def test_the_client_comes_from_data_client_json_unless_given(tmp_path):
    base = make_base(tmp_path)
    (base / "data" / "client.json").write_text('{"client": "1.119.0"}', encoding="utf-8")
    assert brp.build_manifest(base, version="2026.11.16", sources=[])["client"] == "1.119.0"


def test_no_client_to_read_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match="client"):
        brp.build_manifest(make_base(tmp_path), version="2026.11.16", sources=[])


def test_write_manifest_puts_manifest_json_in_the_folder_and_replaces_an_old_one(tmp_path):
    base = make_base(tmp_path)
    brp.write_manifest(base, version="2026.11.16", client="1.118.1", sources=[])
    written = rp.read_manifest(base)
    assert written["sources"] == [] and "manifest.json" not in written["files"]
    assert written["files"]["data/a.json"]["size"] == 15


def test_build_package_copies_the_three_folders_and_the_manifest_but_not_the_model(tmp_path):
    base, out = make_base(tmp_path / "base"), tmp_path / "out"
    (out / "data").mkdir(parents=True)
    (out / "data" / "stale.json").write_bytes(b"gone upstream")
    (out / ".git").mkdir()
    brp.build_package(base, out, version="2026.11.16", client="1.118.1", sources=[])
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "data/a.json", "data/sub/b.png", "image/x/c.png", "manifest.json", "pipeline/p.json"]
    assert (out / ".git").is_dir()  # an output folder that is a checkout keeps its own files
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["version"] == "2026.11.16"


def test_an_out_folder_that_holds_the_base_is_refused_before_anything_is_deleted(tmp_path):
    base = make_base(tmp_path)
    for out in (base, base / "sub"):
        with pytest.raises(SystemExit, match="--out"):
            brp.build_package(base, out, version="2026.11.16", client="1.118.1", sources=[])
    assert (base / "data" / "a.json").is_file()


def test_the_repos_own_resource_builds_a_manifest_that_matches_its_files():
    base = repo / "assets" / "resource" / "base"
    manifest = brp.build_manifest(base, version="2026.11.16", sources=[])
    assert manifest["client"] == json.loads((base / "data" / "event_table.json").read_text(encoding="utf-8"))["client"]
    assert {"data/event_table.json", "pipeline/mirror_dungeon.json"} <= set(manifest["files"])
    assert not any(path.startswith("model/") for path in manifest["files"])
    for path, entry in manifest["files"].items():
        assert entry["size"] == (base / path).stat().st_size
