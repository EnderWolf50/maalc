"""The tree `tools/install.py --release` assembles in install/, the one release.yml zips (#497). Skipped unless install/
is a release build (it has the bundled python/); release.yml runs this file right after the build."""

import subprocess
from collections import Counter
from pathlib import Path

import pytest

from install import MAAFW_FIX, fetch_zip
from install import install as TREE

PYTHON = TREE / "python" / "python.exe"
pytestmark = pytest.mark.skipif(not PYTHON.exists(), reason="install/ is not a --release build")


def test_each_maafw_binary_ships_once():
    names = {p.name for p in (TREE / "maafw").rglob("*") if p.is_file()}
    copies = Counter(p.name for p in TREE.rglob("*") if p.name in names)
    assert "MaaFramework.dll" in names
    assert {name: n for name, n in copies.items() if n > 1} == {}


def test_maafw_holds_the_fixed_framework_dll():
    """MXU loads MaaFramework from <root>/maafw/."""
    assert (TREE / "maafw" / "MaaFramework.dll").read_bytes() == fetch_zip(*MAAFW_FIX).read("MaaFramework.dll")


def test_bundled_python_loads_the_agent_server_from_maafw():
    """The agent the clients start (child_exec ./python/python.exe, agent/main.py) takes its DLLs from maafw/.
    -B: release.yml zips this tree next, so the check writes no __pycache__ into it."""
    code = "import main; from maa.library import Library; Library.agent_server(); print(Library.agent_server_libpath)"
    r = subprocess.run([str(PYTHON), "-B", "-c", code], cwd=TREE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == (TREE / "maafw" / "MaaAgentServer.dll").resolve()
