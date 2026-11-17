"""Assemble a runnable <root> in install/: interface.json, resource/, agent/,
maafw/ (the MaaFramework DLLs the bot and what runs its tasks load, taken from the installed maafw;
on Windows MaaFramework.dll comes from MAAFW_FIX), and
the settings GUI maalc-gui.exe when it has been built, which runs the tasks (ADR 0015).

interface.json's child_exec, which a tool that starts the agent from it reads (MaaDebugger), is pinned to the
Python running this script (run it with `uv run`), because Windows resolves a bare `python` to the Microsoft Store
alias. Run tools/fetch_ocr.py first.

`--release` (Windows x64 only, used by .github/workflows/release.yml) makes
install/ self-contained instead: python.org's embeddable Python in python/ with
the locked runtime deps but without the maafw wheel's DLLs (agent/main.py points
it at maafw/), and child_exec `./python/python.exe`, relative to the interface.json folder.
"""

import argparse
import filecmp
import hashlib
import io
import shutil
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from time import sleep
from urllib.error import HTTPError
from urllib.request import urlopen

import maa

import build_resource_package

PYTHON = ("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
          "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")
# MaaFramework.dll from the EnderWolf50/MaaFramework fork: v5.14.3 plus two fixes. Batch OCR no longer
# re-recognizes a cached box cut to less than half its height at a roi edge, a sliver down to 1 px (GBs of memory,
# MaaXYZ/MaaFramework#1568, #157): that roi runs its own det+rec, as it does unbatched. A task keeps
# only the details of its last 200 nodes, so a whole dungeon run as one task stays flat without clear_cache, which also
# dropped the runner ids of the queued tasks (MaaXYZ/MaaFramework#1578, #176, G1). Windows only; the rest of
# maafw/ stays the wheel's. Drop both once a maafw release has both fixes (MaaXYZ/MaaFramework#1573, #1578).
MAAFW_FIX_VERSION = "5.14.3"
MAAFW_FIX = ("https://github.com/EnderWolf50/MaaFramework/releases/download/v5.14.3-maalc.4/MaaFramework-v5.14.3-maalc.4-win-x64.zip",
             "5f606362da84fbaf94ef1753bf04cafc023bccb53da0efd6faf2fdb43c25da81")
# GitHub's release downloads answered 504, some after about 2 minutes, five times on 2026-11-08 (#571).
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_WAITS = (10, 20, 40)

repo = Path(__file__).resolve().parent.parent
install = repo / "install"
wheel_bin = Path(maa.__file__).parent / "bin"


def retryable(error: OSError) -> bool:
    """A 5xx or a timeout may pass on the next try; a 4xx comes back the same."""
    if isinstance(error, HTTPError):
        return error.code >= 500
    return isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)


def fetch_zip(url: str, sha256: str) -> zipfile.ZipFile:
    tries = len(DOWNLOAD_WAITS) + 1
    for n, wait in enumerate((*DOWNLOAD_WAITS, None), start=1):
        try:
            with urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
                data = response.read()
            break
        except OSError as error:
            if wait is None or not retryable(error):
                raise
            print(f"{url}: {error} on try {n} of {tries}; trying again in {wait} s", flush=True)
            sleep(wait)
    if hashlib.sha256(data).hexdigest() != sha256:
        sys.exit(f"SHA-256 mismatch: {url}")
    return zipfile.ZipFile(io.BytesIO(data))


def fixed_framework_dll() -> bytes:
    """MAAFW_FIX's MaaFramework.dll, the one maafw/ ships on Windows."""
    return fetch_zip(*MAAFW_FIX).read("MaaFramework.dll")


@contextmanager
def exit_if_held(path: Path):
    """A file another process holds cannot be written or deleted: the bot and what runs its tasks load maafw/'s DLLs,
    the settings window runs maalc-gui.exe. Stop with one line that names it, not a traceback (#757). Windows says so as
    WinError 32 (shutil.copy2, unlink) or as errno 13 (open, unlink of a loaded DLL): PermissionError both."""
    try:
        yield
    except PermissionError as error:
        sys.exit(f"cannot change {path} ({error.strerror}): the settings window or the bot may hold it;"
                 " close it and run install.py again")


def copy_file(src: Path, dst: Path) -> None:
    """copy2, unless dst holds src's bytes already (size, then bytes: copy2 keeps the source's mtime). A rebuild
    that changes none of the DLLs a running bot holds then goes through (#757)."""
    with exit_if_held(dst):
        if not (dst.is_file() and filecmp.cmp(src, dst, shallow=False)):
            shutil.copy2(src, dst)


def write_file(dst: Path, data: bytes) -> None:
    """copy_file for bytes in memory."""
    with exit_if_held(dst):
        if not (dst.is_file() and dst.stat().st_size == len(data) and dst.read_bytes() == data):
            dst.write_bytes(data)


def mirror(src: Path, dst: Path, caller_writes: str | None = None) -> None:
    """Make dst hold what src holds, but for `caller_writes` (a path relative to dst), which is neither copied nor
    deleted: the caller writes it."""
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):  # a folder before what it holds
        name = path.relative_to(src)
        if "__pycache__" in name.parts or name.as_posix() == caller_writes:
            continue
        if path.is_dir():
            (dst / name).mkdir(exist_ok=True)
        else:
            copy_file(path, dst / name)
    for path in sorted(dst.rglob("*"), reverse=True):  # a folder after what it holds, so it is empty by then
        name = path.relative_to(dst)
        if (src / name).exists() or name.as_posix() == caller_writes:
            continue
        with exit_if_held(path):
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()


def mirror_repo(repo: Path, root: Path, child_exec: str) -> None:
    """Copy agent/ and what assets/ holds (interface.json, resource/, locales/) into root. A file the repo deleted
    leaves those folders too; the rest of root (config/, state/, logs/, maafw/) is left alone. interface.json gets
    child_exec in place of the bare python."""
    root.mkdir(parents=True, exist_ok=True)
    for src in (*(repo / "assets").iterdir(), repo / "agent"):
        if src.is_dir():
            mirror(src, root / src.name)
        elif src.name == "interface.json":
            pinned = f'"child_exec": "{child_exec}"'.encode()
            write_file(root / src.name, src.read_bytes().replace(b'"child_exec": "python"', pinned))
        else:
            copy_file(src, root / src.name)


def write_resource_manifest(root: Path, release: bool) -> None:
    """root/resource/base/manifest.json (ADR 0012, #766), after mirror_repo, which drops it. A release lists the
    published sources; a dev install lists none, so the agent never replaces a branch's files with the published ones."""
    sources = build_resource_package.rp.SOURCES if release else []
    manifest = build_resource_package.write_manifest(root / "resource" / "base", build_resource_package.today(), sources)
    print(f"Resource package {manifest['version']}: {len(manifest['files'])} files, {len(sources)} sources")


def mirror_maafw(wheel_bin: Path, root: Path, fixed_dll: bytes | None) -> None:
    maafw = root / "maafw"
    if fixed_dll is None:
        mirror(wheel_bin, maafw)
        return
    # The wheel's MaaFramework.dll is not copied in first: the fixed one a running bot holds would have to change twice.
    mirror(wheel_bin, maafw, caller_writes="MaaFramework.dll")
    write_file(maafw / "MaaFramework.dll", fixed_dll)


def bundle_python() -> None:
    python = install / "python"
    fetch_zip(*PYTHON).extractall(python)
    # The ._pth replaces sys.path and leaves out the script folder, so list
    # site-packages and agent/ (main.py imports its sibling modules).
    with (python / "python312._pth").open("a", encoding="utf-8") as pth:
        pth.write("Lib\\site-packages\n..\\agent\n")
    requirements = install / "requirements.txt"
    subprocess.run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project",
                    "--output-file", str(requirements)], cwd=repo, check=True)
    site_packages = python / "Lib" / "site-packages"
    subprocess.run(["uv", "pip", "install", "--target", str(site_packages),
                    "--python-version", "3.12", "--python-platform", "x86_64-pc-windows-msvc",
                    "--requirements", str(requirements)], check=True)
    requirements.unlink()
    wheel_dlls = site_packages / "maa" / "bin"
    if wheel_dlls.exists():  # a rerun finds maafw installed already, its bin/ gone
        shutil.rmtree(wheel_dlls)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", action="store_true", help="self-contained install/ (Windows x64 only)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    release = parse_args().release  # before anything changes: --help and a typo leave install/ alone
    fixed_dll = None
    if sys.platform == "win32":
        if version("maafw").lstrip("v") != MAAFW_FIX_VERSION:  # the wheel's metadata says "v5.14.3"
            sys.exit(f"maafw {version('maafw')} installed, MAAFW_FIX is built for {MAAFW_FIX_VERSION}: update or drop it")
        # Fetched before anything is copied: a failed download or hash leaves install/ as it was,
        # never with the wheel's unpatched DLL.
        fixed_dll = fixed_framework_dll()
    mirror_repo(repo, install, "./python/python.exe" if release else Path(sys.executable).as_posix())
    write_resource_manifest(install, release)
    mirror_maafw(wheel_bin, install, fixed_dll)
    for name in ("LICENSE", "NOTICE.md"):
        copy_file(repo / name, install / name)
    # The settings GUI finds <root> from its own folder, so it sits next to agent/.
    # Build it first with `pnpm tauri build --no-bundle` in gui/.
    gui = repo / "gui" / "src-tauri" / "target" / "release" / "maalc-gui.exe"
    if gui.exists():
        copy_file(gui, install / gui.name)
    if release:
        bundle_python()
    print(f"Installed to {install}")
