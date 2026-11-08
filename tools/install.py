"""Assemble a runnable <root> in install/: interface.json, resource/, agent/,
maafw/ (the MaaFramework DLLs MXU and the agent load, taken from the installed maafw;
on Windows MaaFramework.dll comes from MAAFW_FIX), and
the settings GUI maalc-gui.exe when it has been built.

Drop MXU or MFAAvalonia into install/ and start it. child_exec is pinned to the
Python running this script (run it with `uv run`), because MXU on Windows
resolves a bare `python` to the Microsoft Store alias. Run tools/fetch_ocr.py first.

`--release` (Windows x64 only, used by .github/workflows/release.yml) makes
install/ self-contained instead: python.org's embeddable Python in python/ with
the locked runtime deps but without the maafw wheel's DLLs (agent/main.py points
it at maafw/), child_exec `./python/python.exe` (MXU joins a relative
child_exec onto the interface.json folder), and MXU's mxu.exe and LICENSE,
shipped unmodified from its release (MXU is AGPL-3.0, see NOTICE.md).
"""

import argparse
import hashlib
import io
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path
from urllib.request import urlopen

import maa

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
MXU = ("https://github.com/MistEO/MXU/releases/download/v2.7.1/MXU-win-x86_64-v2.7.1.zip",
       "825a62af7a344a7a47adca09d1414128e6f53a222a11cdf456f08d2e83d31724")

repo = Path(__file__).resolve().parent.parent
install = repo / "install"
wheel_bin = Path(maa.__file__).parent / "bin"


def fetch_zip(url: str, sha256: str) -> zipfile.ZipFile:
    with urlopen(url) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        sys.exit(f"SHA-256 mismatch: {url}")
    return zipfile.ZipFile(io.BytesIO(data))


def fixed_framework_dll() -> bytes:
    """MAAFW_FIX's MaaFramework.dll, the one maafw/ ships on Windows."""
    return fetch_zip(*MAAFW_FIX).read("MaaFramework.dll")


def mirror(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for path in sorted(dst.rglob("*"), reverse=True):  # a folder after what it holds, so it is empty by then
        if (src / path.relative_to(dst)).exists():
            continue
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()


def mirror_repo(repo: Path, root: Path) -> None:
    """Copy agent/ and what assets/ holds (interface.json, resource/, locales/) into root. A file the repo deleted
    leaves those folders too; the rest of root (config/, state/, logs/, maafw/) is left alone."""
    root.mkdir(parents=True, exist_ok=True)
    for src in (*(repo / "assets").iterdir(), repo / "agent"):
        if src.is_dir():
            mirror(src, root / src.name)
        else:
            shutil.copy2(src, root)


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


def bundle_mxu() -> None:
    with fetch_zip(*MXU) as mxu:
        (install / "mxu.exe").write_bytes(mxu.read("mxu.exe"))
        (install / "LICENSE-MXU").write_bytes(mxu.read("LICENSE"))


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", action="store_true", help="self-contained install/ (Windows x64 only)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    release = parse_args().release  # before anything changes: --help and a typo leave install/ alone
    if sys.platform == "win32":
        if version("maafw").lstrip("v") != MAAFW_FIX_VERSION:  # the wheel's metadata says "v5.14.3"
            sys.exit(f"maafw {version('maafw')} installed, MAAFW_FIX is built for {MAAFW_FIX_VERSION}: update or drop it")
        # Fetched before anything is copied: a failed download or hash leaves install/ as it was,
        # never with the wheel's unpatched DLL.
        fixed_dll = fixed_framework_dll()
    mirror_repo(repo, install)
    interface = install / "interface.json"
    text = interface.read_text(encoding="utf-8")
    exe = "./python/python.exe" if release else Path(sys.executable).as_posix()
    interface.write_text(text.replace('"child_exec": "python"', f'"child_exec": "{exe}"'),
                         encoding="utf-8")
    shutil.copytree(wheel_bin, install / "maafw", dirs_exist_ok=True)
    if sys.platform == "win32":
        (install / "maafw" / "MaaFramework.dll").write_bytes(fixed_dll)
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copy2(repo / name, install)
    # The settings GUI finds <root> from its own folder, so it sits next to agent/.
    # Build it first with `pnpm tauri build --no-bundle` in gui/.
    gui = repo / "gui" / "src-tauri" / "target" / "release" / "maalc-gui.exe"
    if gui.exists():
        shutil.copy2(gui, install)
    if release:
        bundle_python()
        bundle_mxu()
    print(f"Installed to {install}")
