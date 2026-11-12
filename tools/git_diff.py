"""`git` output and the lines of a `git diff -U0`, shared by red_check, review_lint and move_check (#654).

Standard library only: CI runs tools/review_lint.py with a plain `python3`.
"""
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)")


def git(*args: str, cwd: Path | str | None, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=check).stdout


@dataclass(frozen=True)
class Line:
    """One added (`+`) or removed (`-`) line of a diff."""
    old: str | None  # the file on the old side, None for an added file
    new: str | None  # the file on the new side, None for a deleted file
    sign: str
    no: int  # its line number on its own side
    text: str  # without the sign

    @property
    def path(self) -> str | None:
        """The file as the branch has it: the new side, or the old one for a deleted file."""
        return self.new or self.old


def lines(diff: str) -> Iterator[Line]:
    """Every added and removed line of `diff`, which names its files with `a/` and `b/` prefixes."""
    old = new = None
    old_no = new_no = 0
    header = False  # between `diff --git` and the first hunk, where `--- a/x` names a file, not a removed line
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            header, old, new = True, None, None
        elif header and line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
        elif header and line.startswith("+++ "):
            new = line[6:] if line.startswith("+++ b/") else None
        elif m := HUNK.match(line):
            header = False
            old_no, new_no = int(m[1]), int(m[2])
        elif header:
            continue
        elif line.startswith("-"):
            yield Line(old, new, "-", old_no, line[1:])
            old_no += 1
        elif line.startswith("+"):
            yield Line(old, new, "+", new_no, line[1:])
            new_no += 1
