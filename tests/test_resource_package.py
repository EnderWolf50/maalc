"""The versions the program knows and the manifest helpers the agent and the tools share (#766, ADR 0012)."""

import hashlib
import json

import pytest

import resource_package as rp


def test_the_program_knows_format_1_and_template_1():
    assert (rp.FORMAT, rp.TEMPLATE) == (1, 1)


def test_versions_compare_as_tuples_of_ints():
    assert rp.version_key("2026.11.16") < rp.version_key("2026.11.16.2") < rp.version_key("2026.11.17")
    assert rp.version_key("2026.11.9") < rp.version_key("2026.11.16")  # numbers, not text
    assert rp.is_newer("2026.11.16.2", "2026.11.16") and not rp.is_newer("2026.11.16", "2026.11.16")
    assert not rp.is_newer("2026.11.15", "2026.11.16")


def test_a_version_that_is_not_dotted_numbers_is_refused():
    for bad in ("", "2026-11-16", "2026.11.x", "v1"):
        with pytest.raises(ValueError):
            rp.version_key(bad)


def test_sha256_of_a_file_is_its_hex_digest(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    assert rp.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # the FIPS 180 vector


def write_manifest(base, **fields):
    manifest = {"version": "2026.11.16", "client": "1.118.1", "format": 1, "template": 1, "sources": [], "files": {}}
    (base / "manifest.json").write_text(json.dumps({**manifest, **fields}), encoding="utf-8")


def test_read_manifest_returns_the_package_in_use(tmp_path):
    write_manifest(tmp_path, sources=["https://example.test/r"])
    assert rp.read_manifest(tmp_path)["sources"] == ["https://example.test/r"]


def test_no_manifest_reads_as_none(tmp_path):
    assert rp.read_manifest(tmp_path) is None


def test_a_manifest_that_is_not_one_is_an_error_naming_what_is_wrong(tmp_path):
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(rp.ManifestError, match="manifest.json"):
        rp.read_manifest(tmp_path)
    write_manifest(tmp_path, format="1")
    with pytest.raises(rp.ManifestError, match="format"):
        rp.read_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"version": "2026.11.16"}), encoding="utf-8")
    with pytest.raises(rp.ManifestError, match="client"):
        rp.read_manifest(tmp_path)


def test_the_log_line_names_version_client_format_and_template(tmp_path):
    write_manifest(tmp_path, version="2026.11.16.2", client="1.119.0", format=1, template=2)
    assert rp.log_line(tmp_path) == "resource package: version 2026.11.16.2, client 1.119.0, format 1, template 2"


def test_the_log_line_says_so_when_there_is_no_package_or_it_cannot_be_read(tmp_path):
    assert rp.log_line(tmp_path) == "resource package: none (no manifest.json)"
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    assert rp.log_line(tmp_path).startswith("resource package: unreadable (")


def test_sha256_matches_hashlib_on_a_file_bigger_than_one_read(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * (3 * 1024 * 1024 + 5))
    assert rp.sha256_file(f) == hashlib.sha256(f.read_bytes()).hexdigest()
