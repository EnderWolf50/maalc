"""tools/live/maafw_loaded.py names the MaaFramework.dll a process has loaded by its bytes (#497)."""

import shutil
import subprocess
import sys
from pathlib import Path

import maa
import pytest
from install import MAAFW_FIX, fetch_zip

pytest.importorskip("psutil")  # the probe group's (pyproject.toml)
from live import maafw_loaded  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="MAAFW_FIX is a Windows DLL")

WHEEL = Path(maa.__file__).parent / "bin"
LOAD = ("import ctypes, os, sys, time; os.add_dll_directory(sys.argv[1]); "
        "ctypes.WinDLL(os.path.join(sys.argv[1], 'MaaFramework.dll')); print('loaded', flush=True); time.sleep(60)")


def run_on_child_loading(folder: Path, capsys) -> tuple[int, str]:
    child = subprocess.Popen([sys.executable, "-c", LOAD, str(folder)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "loaded"
        code = maafw_loaded.main([str(child.pid)])
    finally:
        child.kill()
        child.wait()
    return code, capsys.readouterr().out


def test_the_wheels_dll_is_named_and_fails(capsys):
    code, out = run_on_child_loading(WHEEL, capsys)
    assert f"{WHEEL / 'MaaFramework.dll'}  wheel" in out
    assert code == 1


def test_the_fixed_dll_is_named_and_passes(tmp_path, capsys):
    folder = tmp_path / "maafw"
    shutil.copytree(WHEEL, folder)
    (folder / "MaaFramework.dll").write_bytes(fetch_zip(*MAAFW_FIX).read("MaaFramework.dll"))
    code, out = run_on_child_loading(folder, capsys)
    assert f"{folder / 'MaaFramework.dll'}  MAAFW_FIX" in out
    assert code == 0
