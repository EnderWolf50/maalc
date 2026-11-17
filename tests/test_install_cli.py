import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

import resource_package as rp
from install import mirror_maafw, mirror_repo, write_resource_manifest

INSTALL = Path(__file__).resolve().parent.parent / "tools/install.py"
EXE = "./python/python.exe"


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
    mirror_repo(repo, root, EXE)
    (root / "config").mkdir()
    (root / "config/settings.json").write_text("{}", encoding="utf-8")

    for name in ("agent/state.py", "agent/old/__init__.py", "assets/resource/base/pipeline/Deleted.json"):
        (repo / name).unlink()
    (repo / "agent/old").rmdir()
    mirror_repo(repo, root, EXE)

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


OLD = 1_000_000_000  # an mtime no copy leaves: copy2 keeps the source's, a write sets now


def test_a_file_already_the_same_is_not_written_again(tmp_path):
    """A running bot holds maafw/'s DLLs, so a rebuild that changes none of them must not write them (#757)."""
    wheel, repo, root = tmp_path / "bin", tmp_path / "repo", tmp_path / "install"
    for path in (wheel / "MaaFramework.dll", wheel / "plugins/MaaPluginDemo.dll", repo / "agent/main.py",
                 repo / "assets/interface.json", repo / "assets/resource/base/pipeline/Node.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    (repo / "assets/interface.json").write_bytes(b'{\r\n    "child_exec": "python",\r\n}\r\n')
    mirror_repo(repo, root, EXE)
    mirror_maafw(wheel, root, b"fixed")
    for path in root.rglob("*"):
        os.utime(path, (OLD, OLD))

    mirror_repo(repo, root, EXE)
    mirror_maafw(wheel, root, b"fixed")

    written = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.stat().st_mtime != OLD}
    assert written == set()
    assert (root / "maafw/MaaFramework.dll").read_bytes() == b"fixed"
    assert (root / "interface.json").read_bytes() == b'{\r\n    "child_exec": "./python/python.exe",\r\n}\r\n'


def test_a_file_that_differs_is_written_even_with_the_same_size_and_mtime(tmp_path):
    wheel, root = tmp_path / "bin", tmp_path / "install"
    wheel.mkdir()
    (wheel / "MaaToolkit.dll").write_bytes(b"new toolkit")
    (wheel / "MaaFramework.dll").write_bytes(b"wheel framework")
    mirror_maafw(wheel, root, b"fixed")
    (root / "maafw/MaaToolkit.dll").write_bytes(b"old toolkit")  # what an older wheel shipped, as long
    stat = (wheel / "MaaToolkit.dll").stat()
    os.utime(root / "maafw/MaaToolkit.dll", ns=(stat.st_atime_ns, stat.st_mtime_ns))
    (root / "maafw/MaaFramework.dll").write_bytes(b"fixex")

    mirror_maafw(wheel, root, b"fixed")

    assert (root / "maafw/MaaToolkit.dll").read_bytes() == b"new toolkit"
    assert (root / "maafw/MaaFramework.dll").read_bytes() == b"fixed"


@contextmanager
def held(*paths: Path):
    """Open each file as a loaded DLL is held: reading shared, writing and deleting denied."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    generic_read, file_share_read, open_existing = 0x80000000, 0x1, 3
    handles = [kernel32.CreateFileW(str(p), generic_read, file_share_read, None, open_existing, 0, None) for p in paths]
    assert wintypes.HANDLE(-1).value not in handles, ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        for handle in handles:
            kernel32.CloseHandle(handle)


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="holds a file the way Windows holds a loaded DLL")


def maafw_installed(tmp_path: Path) -> tuple[Path, Path]:
    wheel, root = tmp_path / "bin", tmp_path / "install"
    for name in ("MaaFramework.dll", "MaaToolkit.dll", "Dropped.dll"):
        (wheel / name).parent.mkdir(parents=True, exist_ok=True)
        (wheel / name).write_bytes(f"wheel {name}".encode())
    mirror_maafw(wheel, root, b"fixed")
    return wheel, root


@windows_only
def test_held_files_that_stay_the_same_do_not_stop_the_install(tmp_path):
    """MXU open on 2026-11-15 held every DLL of maafw/, none of which changed: the rebuild failed (#757)."""
    wheel, root = maafw_installed(tmp_path)
    (wheel / "MaaToolkit.dll").write_bytes(b"wheel MaaToolkit.dll, a new build")
    (root / "maafw/MaaToolkit.dll").unlink()  # not held, so it may change
    with held(root / "maafw/MaaFramework.dll", root / "maafw/Dropped.dll"):
        mirror_maafw(wheel, root, b"fixed")
    assert (root / "maafw/MaaFramework.dll").read_bytes() == b"fixed"
    assert (root / "maafw/MaaToolkit.dll").read_bytes() == b"wheel MaaToolkit.dll, a new build"


@windows_only
@pytest.mark.parametrize("change", ["wheel file", "fixed DLL", "dropped file"])
def test_a_held_file_that_has_to_change_stops_with_one_line_naming_it(tmp_path, change):
    wheel, root = maafw_installed(tmp_path)
    fixed = b"fixed"
    if change == "wheel file":
        name = "MaaToolkit.dll"
        (wheel / name).write_bytes(b"a newer wheel's MaaToolkit.dll")
    elif change == "fixed DLL":
        name, fixed = "MaaFramework.dll", b"a newer fix"
    else:
        name = "Dropped.dll"
        (wheel / name).unlink()
    with held(root / "maafw" / name), pytest.raises(SystemExit) as stop:
        mirror_maafw(wheel, root, fixed)
    message = str(stop.value.code)
    assert len(message.splitlines()) == 1
    assert str(root / "maafw" / name) in message and "the bot" in message and "run" in message


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


def test_the_install_gets_a_manifest_with_no_sources_and_a_release_one_with_the_real_list(tmp_path):
    base = tmp_path / "resource/base"
    for name in ("data/client.json", "data/a.json", "pipeline/p.json", "model/ocr/det.onnx"):
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text('{"client": "1.118.1"}', encoding="utf-8")
    write_resource_manifest(tmp_path, release=False)
    dev = rp.read_manifest(base)
    assert dev["sources"] == [] and "model/ocr/det.onnx" not in dev["files"] and "data/a.json" in dev["files"]
    write_resource_manifest(tmp_path, release=True)
    assert rp.read_manifest(base)["sources"] == rp.SOURCES and rp.SOURCES
