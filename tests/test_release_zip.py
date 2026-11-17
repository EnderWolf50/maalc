"""The tree `tools/install.py --release` assembles in install/, the one release.yml zips (#497). Skipped unless install/
is a release build (it has the bundled python/); release.yml runs this file right after the build."""

import subprocess
from collections import Counter
from pathlib import Path

import pytest

import resource_package as rp
from install import fixed_framework_dll
from install import install as TREE

PYTHON = TREE / "python" / "python.exe"
pytestmark = pytest.mark.skipif(not PYTHON.exists(), reason="install/ is not a --release build")


def test_each_maafw_binary_ships_once():
    names = {p.name for p in (TREE / "maafw").rglob("*") if p.is_file()}
    copies = Counter(p.name for p in TREE.rglob("*") if p.name in names)
    assert "MaaFramework.dll" in names
    assert {name: n for name, n in copies.items() if n > 1} == {}


def test_the_release_ships_no_config_folder():
    """An update replaces the top-level items the zip has (v1.0.0's MXU every one, update.rs): a config/ in the zip
    would take the user's settings with it."""
    assert not (TREE / "config").exists()


def test_the_release_ships_no_mxu():
    """The settings window runs the tasks (ADR 0015): no MXU and no licence of it in the zip, as NOTICE.md lists none."""
    assert not [p.name for p in TREE.iterdir() if "mxu" in p.name.lower()]


def test_maafw_holds_the_fixed_framework_dll():
    """The agent loads MaaFramework from <root>/maafw/ (agent/main.py)."""
    assert (TREE / "maafw" / "MaaFramework.dll").read_bytes() == fixed_framework_dll()


def test_bundled_python_loads_the_agent_server_from_maafw():
    """The agent as interface.json starts it (child_exec ./python/python.exe, agent/main.py) takes its DLLs from maafw/.
    -B: release.yml zips this tree next, so the check writes no __pycache__ into it."""
    code = "import main; from maa.library import Library; Library.agent_server(); print(Library.agent_server_libpath)"
    r = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=TREE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == (TREE / "maafw" / "MaaAgentServer.dll").resolve()


def test_resource_base_holds_the_package_and_its_manifest():
    """The zip works on first use and offline (#766): data/, image/ and pipeline/ with a manifest that lists each file by
    sha256, the real sources, and no OCR model."""
    base = TREE / "resource" / "base"
    manifest = rp.read_manifest(base)
    assert manifest is not None
    assert (manifest["format"], manifest["template"]) == (rp.FORMAT, rp.TEMPLATE) and manifest["sources"] == rp.SOURCES
    assert manifest["client"] and manifest["version"]
    on_disk = {p.relative_to(base).as_posix() for part in rp.PARTS for p in (base / part).rglob("*") if p.is_file()}
    assert set(manifest["files"]) == on_disk and on_disk
    assert not any(name.startswith("model/") for name in manifest["files"])
    for name, entry in manifest["files"].items():
        assert (entry["size"], entry["sha256"]) == ((base / name).stat().st_size, rp.sha256_file(base / name)), name
