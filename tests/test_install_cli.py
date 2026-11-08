import subprocess
import sys
from pathlib import Path

from install import mirror_maafw, mirror_repo

INSTALL = Path(__file__).resolve().parent.parent / "tools/install.py"


def snapshot(root: Path):
    return sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*")) if root.exists() else None


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_assembling_again_drops_what_the_repo_deleted_and_keeps_config(tmp_path):
    repo, root = tmp_path / "repo", tmp_path / "install"
    for name in ("agent/main.py", "agent/state.py", "agent/old/__init__.py", "assets/interface.json",
                 "assets/locales/zh_tw.json", "assets/resource/base/pipeline/Kept.json",
                 "assets/resource/base/pipeline/Deleted.json"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(name, encoding="utf-8")
    mirror_repo(repo, root)
    (root / "config").mkdir()
    (root / "config/settings.json").write_text("{}", encoding="utf-8")

    for name in ("agent/state.py", "agent/old/__init__.py", "assets/resource/base/pipeline/Deleted.json"):
        (repo / name).unlink()
    (repo / "agent/old").rmdir()
    mirror_repo(repo, root)

    assert files(root) == {"agent/main.py", "interface.json", "locales/zh_tw.json",
                           "resource/base/pipeline/Kept.json", "config/settings.json"}
    assert not (root / "agent/old").exists()
    assert (root / "config/settings.json").read_text(encoding="utf-8") == "{}"


def test_maafw_drops_what_the_wheel_dropped_and_keeps_the_fixed_dll(tmp_path):
    wheel, root = tmp_path / "bin", tmp_path / "install"
    wheel.mkdir()
    for name in ("MaaFramework.dll", "MaaToolkit.dll", "Dropped.dll"):
        (wheel / name).write_bytes(f"wheel {name}".encode())
    mirror_maafw(wheel, root, b"fixed")

    (wheel / "Dropped.dll").unlink()
    mirror_maafw(wheel, root, b"fixed")

    assert files(root) == {"maafw/MaaFramework.dll", "maafw/MaaToolkit.dll"}
    assert (root / "maafw/MaaFramework.dll").read_bytes() == b"fixed"
    assert (root / "maafw/MaaToolkit.dll").read_bytes() == b"wheel MaaToolkit.dll"


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
