"""The version MXU shows is the `version` of assets/interface.json. Every manifest that names a version names that one,
and release.yml names the zip and the draft release after a tag that must be it too (TAG, set by release.yml only)."""

import json
import os
import tomllib

import pytest

from daily_child import ROOT, interface


def repo_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_manifest_names_the_version_mxu_shows():
    shown = interface()["version"].removeprefix("v")
    versions = {
        "pyproject.toml": tomllib.loads(repo_text("pyproject.toml"))["project"]["version"],
        "gui/package.json": json.loads(repo_text("gui/package.json"))["version"],
        "gui/src-tauri/tauri.conf.json": json.loads(repo_text("gui/src-tauri/tauri.conf.json"))["version"],
        "gui/src-tauri/Cargo.toml": tomllib.loads(repo_text("gui/src-tauri/Cargo.toml"))["package"]["version"],
    }
    assert {path: v for path, v in versions.items() if v != shown} == {}, f"interface.json shows {shown}"


@pytest.mark.skipif(not os.environ.get("TAG"), reason="release.yml sets TAG to the tag it releases")
def test_the_release_tag_is_the_version_mxu_shows():
    assert interface()["version"] == os.environ["TAG"]
