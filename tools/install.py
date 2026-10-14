"""Assemble a runnable <root> in install/: interface.json, resource/, agent/,
and maafw/ (the MaaFramework DLLs MXU loads, taken from the installed maafw).

Drop MXU or MFAAvalonia into install/ and start it. child_exec is pinned to the
Python running this script (run it with `uv run`), because MXU on Windows
resolves a bare `python` to the Microsoft Store alias. Run tools/fetch_ocr.py first.
"""

import shutil
import sys
from pathlib import Path

import maa

repo = Path(__file__).resolve().parent.parent
install = repo / "install"

if __name__ == "__main__":
    shutil.copytree(repo / "assets", install, dirs_exist_ok=True)
    shutil.copytree(repo / "agent", install / "agent", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    interface = install / "interface.json"
    text = interface.read_text(encoding="utf-8")
    exe = Path(sys.executable).as_posix()
    interface.write_text(text.replace('"child_exec": "python"', f'"child_exec": "{exe}"'),
                         encoding="utf-8")
    shutil.copytree(Path(maa.__file__).parent / "bin", install / "maafw", dirs_exist_ok=True)
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copy2(repo / name, install)
    print(f"Installed to {install}")
