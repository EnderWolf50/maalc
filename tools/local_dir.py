"""The machine-local folder `<main checkout>/.local/`, found from any worktree.

Every worktree shares one `.local/` through git's common dir, so probe data, the evidence
archive and the resource queues have one home. The folder is gitignored.
"""
import subprocess
from pathlib import Path


def main_checkout(cwd: str | Path | None = None) -> Path:
    """The main checkout of the repo `cwd` is in; without `cwd`, of the repo this file is in (so any caller's cwd works)."""
    cwd = cwd or Path(__file__).resolve().parent
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    return Path(common).parent


def local_dir(*parts: str, cwd: str | Path | None = None) -> Path:
    """`.local/<parts>` of the main checkout; the folder is created."""
    path = main_checkout(cwd).joinpath(".local", *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
