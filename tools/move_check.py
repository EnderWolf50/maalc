"""Prove a commit range only moves code: the lines it adds or removes that the other side does not account for.

    uv run python tools/move_check.py <base> <head>

Every removed and added line of `git diff <base>...<head>` (from their merge-base, so what landed on <base> since
stays out) is compared as a multiset, leading indentation and blank lines ignored, so a function cut from one file
and pasted into another (or one level deeper) cancels out. What is left is printed as `file:line: text`, added
lines first. For a move this is the new import lines and the `actions.X` -> `<module>.X` rewrites in the tests;
anything else is a change the move did not announce. Read it next to
`git diff --color-moved=zebra --color-moved-ws=allow-indentation-change <base>...<head>`.

Exit code 0 when nothing is left over, 1 otherwise.
"""

import sys
from collections import Counter

import git_diff
from git_diff import git

def changed_lines(base, head, cwd=None):
    """(added, removed): (file, line number, text without leading whitespace) of every non-blank changed line."""
    # a/ b/ prefixes and unquoted paths whatever the user's diff.noprefix or core.quotepath says
    diff = git("-c", "core.quotepath=false", "diff", "-U0", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", f"{base}...{head}", cwd=cwd)
    added, removed = [], []
    for line in git_diff.lines(diff):
        if text := line.text.strip():
            if line.sign == "+":
                added.append((line.new, line.no, text))
            else:
                removed.append((line.old, line.no, text))
    return added, removed


def leftover(lines, other):
    """The lines that no line of `other` with the same text pairs off, each line of `other` used once."""
    spare = Counter(text for _, _, text in other)
    left = []
    for path, no, text in lines:
        if spare[text]:
            spare[text] -= 1
        else:
            left.append((path, no, text))
    return left


def unmatched(base, head, cwd=None):
    """(added, removed): the changed lines the other side does not account for as moved."""
    added, removed = changed_lines(base, head, cwd)
    return leftover(added, removed), leftover(removed, added)


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
