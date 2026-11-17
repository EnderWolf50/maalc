"""The tree `tools/install.py --release` assembles in install/, the one release.yml zips (#497). Skipped unless install/
is a release build (it has the bundled python/); release.yml runs this file right after the build."""

import json
import os
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
    """MXU's full update moves away every top-level item the zip has (update.rs): a config/ in the zip would take the
    user's settings and team options file (#780) with it."""
    assert not (TREE / "config").exists()


def test_maafw_holds_the_fixed_framework_dll():
    """MXU loads MaaFramework from <root>/maafw/."""
    assert (TREE / "maafw" / "MaaFramework.dll").read_bytes() == fixed_framework_dll()


def test_bundled_python_loads_the_agent_server_from_maafw():
    """The agent the clients start (child_exec ./python/python.exe, agent/main.py) takes its DLLs from maafw/.
    -B: release.yml zips this tree next, so the check writes no __pycache__ into it."""
    code = "import main; from maa.library import Library; Library.agent_server(); print(Library.agent_server_libpath)"
    r = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=TREE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == (TREE / "maafw" / "MaaAgentServer.dll").resolve()


def test_bundled_python_runs_the_runner_and_it_answers_in_its_protocol():
    """The window starts `python/python.exe runner/__main__.py` (#812); its python312._pth puts no script folder on
    sys.path, so the runner loads itself by its path. A stop with no run is refused: it reads, writes and ends with
    code 2, before MaaFramework, a device or a log file is touched. -B: no __pycache__ in the tree release.yml zips."""
    assert (TREE / "runner" / "__main__.py").is_file()
    r = subprocess.run([str(PYTHON), "-B", str(TREE / "runner" / "__main__.py")], input='{"v": 1, "cmd": "stop"}\n',
                       cwd=TREE, capture_output=True, text=True, encoding="utf-8", timeout=120)
    events = [json.loads(line) for line in r.stdout.splitlines()]
    assert r.returncode == 2, r.stdout + r.stderr
    assert [e["event"] for e in events] == ["ready", "error", "end"] and events[1]["kind"] == "protocol"
    assert not (TREE / "logs").exists()


def test_bundled_python_loads_maafw_through_the_runners_framework(tmp_path):
    """The runner's Framework (runner/framework.py) on the bundled Python loads MaaFramework and MaaToolkit from
    maafw/. Its root is tmp_path, which takes the toolkit's debug/ (the zipped tree gets none), with maafw/ named by
    MAAFW_BINARY_PATH, which Framework keeps when its root has no maafw/ of its own."""
    code = ("import runpy; from pathlib import Path; "
            f"runpy.run_path({str(TREE / 'runner' / '__main__.py')!r}, run_name='loaded'); "
            "from runner.framework import Framework; from maa.library import Library; "
            f"Framework(Path({str(tmp_path)!r})); Library.framework(); print(Library.framework_libpath)")
    env = {**os.environ, "MAAFW_BINARY_PATH": str(TREE / "maafw")}
    r = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip().splitlines()[-1]).resolve() == (TREE / "maafw" / "MaaFramework.dll").resolve()
    assert (tmp_path / "debug").is_dir()


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
