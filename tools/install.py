"""Assemble a runnable <root> in install/: interface.json, resource/, agent/.

Drop MXU or MFAAvalonia into install/ and start it from a shell where `python`
has maafw (e.g. after activating .venv); interface.json launches the agent with
`python ./agent/main.py`. Run tools/fetch_ocr.py first.
"""

import shutil
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
install = repo / "install"

if __name__ == "__main__":
    shutil.copytree(repo / "assets", install, dirs_exist_ok=True)
    shutil.copytree(repo / "agent", install / "agent", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copy2(repo / name, install)
    print(f"Installed to {install}")
