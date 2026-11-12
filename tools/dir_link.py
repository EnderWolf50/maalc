"""A directory link that needs no privilege: a junction on Windows, a symlink elsewhere (#654)."""
import os
import sys
from pathlib import Path


def link(at: Path, target: Path) -> None:
    """Make `at` a link to the directory `target`. Raises OSError when it cannot."""
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(at))
    else:
        os.symlink(target, at, target_is_directory=True)


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def unlink(at: Path) -> None:
    """Remove the link at `at`, never what it points to; nothing when `at` is no link or cannot be removed."""
    if not is_link(at):
        return
    try:
        os.rmdir(at)  # a junction, or a symlink to a directory on Windows
    except OSError:
        try:
            os.unlink(at)  # a symlink on POSIX
        except OSError:
            pass
