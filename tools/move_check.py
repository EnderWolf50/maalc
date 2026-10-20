"""Prove a commit range only moves code: the lines it adds or removes that the other side does not account for.

    uv run python tools/move_check.py <base> <head>

Every removed and added line of `git diff <base> <head>` is compared as a multiset, leading indentation and blank
lines ignored, so a function cut from one file and pasted into another (or one level deeper) cancels out. What is
left is printed as `file:line: text`, added lines first. For a move this is the new import lines and the
`actions.X` -> `<module>.X` rewrites in the tests; anything else is a change the move did not announce. Read it
next to `git diff --color-moved=zebra --color-moved-ws=allow-indentation-change <base> <head>`.

Exit code 0 when nothing is left over, 1 otherwise.
"""

import re
import subprocess
import sys
from collections import Counter

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)")


def changed_lines(base, head, cwd=None):
    """(added, removed): (file, line number, text without leading whitespace) of every non-blank changed line."""
    diff = subprocess.run(["git", "diff", "-U0", "--no-color", "--no-ext-diff", base, head], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout
    added, removed = [], []
    old = new = None
    old_no = new_no = 0
    header = False  # between `diff --git` and the first hunk, where `--- a/x` names a file, not a removed line
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            header = True
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
            if text := line[1:].strip():
                removed.append((old, old_no, text))
            old_no += 1
        elif line.startswith("+"):
            if text := line[1:].strip():
                added.append((new, new_no, text))
            new_no += 1
    return added, removed


def unmatched(base, head, cwd=None):
    """The added and removed lines that no removed or added line with the same text pairs off."""
    added, removed = changed_lines(base, head, cwd)
    spare_removed = Counter(text for _, _, text in removed)
    spare_added = Counter(text for _, _, text in added)
    left_added, left_removed = [], []
    for line in added:
        if spare_removed[line[2]]:
            spare_removed[line[2]] -= 1
        else:
            left_added.append(line)
    for line in removed:
        if spare_added[line[2]]:
            spare_added[line[2]] -= 1
        else:
            left_removed.append(line)
    return left_added, left_removed


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    added, removed = unmatched(sys.argv[1], sys.argv[2])
    sys.stdout.reconfigure(encoding="utf-8")  # the code and comments hold CJK; a redirected Windows console is cp950
    for title, lines in (("added", added), ("removed", removed)):
        print(f"== {len(lines)} {title} lines not moved")
        for path, no, text in lines:
            print(f"{path}:{no}: {text}")
    sys.exit(1 if added or removed else 0)


if __name__ == "__main__":
    main()
