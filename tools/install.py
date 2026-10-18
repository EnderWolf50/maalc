"""Assemble a runnable <root> in install/: interface.json, resource/, agent/,
maafw/ (the MaaFramework DLLs MXU loads, taken from the installed maafw; on Windows
MaaFramework.dll comes from MAAFW_FIX), and
the settings GUI maalc-gui.exe when it has been built.

Drop MXU or MFAAvalonia into install/ and start it. child_exec is pinned to the
Python running this script (run it with `uv run`), because MXU on Windows
resolves a bare `python` to the Microsoft Store alias. Run tools/fetch_ocr.py first.

`--release` (Windows x64 only, used by .github/workflows/release.yml) makes
install/ self-contained instead: python.org's embeddable Python in python/ with
the locked runtime deps, child_exec `./python/python.exe` (MXU joins a relative
child_exec onto the interface.json folder), and MXU's mxu.exe and LICENSE,
shipped unmodified from its release (MXU is AGPL-3.0, see NOTICE.md).
"""

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
# MaaFramework.dll from the EnderWolf50/MaaFramework fork: v5.14.3 plus a fix for batch OCR re-recognizing
# 1 px slivers at roi edges (GBs of memory, MaaXYZ/MaaFramework#1568, #157). Windows only; the rest of maafw/
# stays the wheel's. Drop this once a maafw release has the fix.
MAAFW_FIX = ("5.14.3",
             "https://github.com/EnderWolf50/MaaFramework/releases/download/v5.14.3-maalc.1/MaaFramework-v5.14.3-maalc.1-win-x64.zip",
             "1be145b32c9e5338ce6802621244617c2cebdd8485f3140067ef5e3c57c97998")
MXU = ("https://github.com/MistEO/MXU/releases/download/v2.7.1/MXU-win-x86_64-v2.7.1.zip",
       "825a62af7a344a7a47adca09d1414128e6f53a222a11cdf456f08d2e83d31724")

repo = Path(__file__).resolve().parent.parent
install = repo / "install"


def fetch_zip(url: str, sha256: str) -> zipfile.ZipFile:
    with urlopen(url) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        sys.exit(f"SHA-256 mismatch: {url}")
    return zipfile.ZipFile(io.BytesIO(data))


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
    subprocess.run(["uv", "pip", "install", "--target", str(python / "Lib" / "site-packages"),
                    "--python-version", "3.12", "--python-platform", "x86_64-pc-windows-msvc",
                    "--requirements", str(requirements)], check=True)
    requirements.unlink()


def bundle_mxu() -> None:
    with fetch_zip(*MXU) as mxu:
        (install / "mxu.exe").write_bytes(mxu.read("mxu.exe"))
        (install / "LICENSE-MXU").write_bytes(mxu.read("LICENSE"))


if __name__ == "__main__":
    release = "--release" in sys.argv[1:]
    if version("maafw").lstrip("v") != MAAFW_FIX[0]:  # the wheel's metadata says "v5.14.3"
        sys.exit(f"maafw {version('maafw')} installed, MAAFW_FIX is built for {MAAFW_FIX[0]}: update or drop it")
    shutil.copytree(repo / "assets", install, dirs_exist_ok=True)
    shutil.copytree(repo / "agent", install / "agent", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    interface = install / "interface.json"
    text = interface.read_text(encoding="utf-8")
    exe = "./python/python.exe" if release else Path(sys.executable).as_posix()
    interface.write_text(text.replace('"child_exec": "python"', f'"child_exec": "{exe}"'),
                         encoding="utf-8")
    shutil.copytree(Path(maa.__file__).parent / "bin", install / "maafw", dirs_exist_ok=True)
    if sys.platform == "win32":
        fetch_zip(*MAAFW_FIX[1:]).extract("MaaFramework.dll", install / "maafw")
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
