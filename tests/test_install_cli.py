import subprocess
import sys
from pathlib import Path

INSTALL = Path(__file__).resolve().parent.parent / "tools/install.py"


def snapshot(root: Path):
    return sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*")) if root.exists() else None


def run(*args):
    return subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, encoding="utf-8")


def test_help_prints_usage_and_changes_nothing():
    install = INSTALL.parent.parent / "install"
    before = snapshot(install)
    r = run("--help")
    assert r.returncode == 0 and "usage:" in r.stdout and "--release" in r.stdout
    assert snapshot(install) == before


def test_unknown_flag_prints_usage_and_changes_nothing():
    install = INSTALL.parent.parent / "install"
    before = snapshot(install)
    r = run("--hepl")
    assert r.returncode == 2 and "usage:" in r.stderr
    assert snapshot(install) == before
