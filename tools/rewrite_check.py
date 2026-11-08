"""What a rewrite of an issue or PR body dropped from the original.

  uv run python tools/rewrite_check.py <original> <rewrite>

A rewrite (an English body put into Traditional Chinese, docs/agents/pr.md "Language") keeps the facts as they were. This
prints each code span, fenced block, link, `#n` reference and number of the original that the rewrite holds fewer times,
then the English words the rewrite still has outside code and links, for a person to judge (game terms stay English).
Exit 1 when something was dropped.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

FENCE = re.compile(r"^```.*?^```", re.S | re.M)
CODE = re.compile(r"`[^`\n]+`")
URL = re.compile(r"https?://[^\s)>\]]+")
# ASCII word boundaries: Chinese counts as \w otherwise, and 第5層 or 用CSP來 would hide the number or the word.
REF = re.compile(r"(?<![\w/])#\d+\b", re.ASCII)
NUMBER = re.compile(r"(?<![\w.#])\d+(?:[.:]\d+)*\b", re.ASCII)
WORD = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b", re.ASCII)


def tokens(text: str) -> tuple[Counter, str]:
    """(kinds and values of every kept token, the prose left once code and links are cut out)."""
    found: Counter = Counter()
    for kind, pattern in (("fenced block", FENCE), ("code", CODE), ("link", URL)):
        found.update((kind, m.group(0).strip()) for m in pattern.finditer(text))
        text = pattern.sub(" ", text)
    found.update(("reference", m.group(0)) for m in REF.finditer(text))
    found.update(("number", m.group(0)) for m in NUMBER.finditer(text))
    return found, text


def check(original: str, rewrite: str) -> tuple[list[str], list[str]]:
    """(what the rewrite dropped, English words left in its prose)."""
    before, _ = tokens(original)
    after, prose = tokens(rewrite)
    dropped = [f"{kind}: {value}" + (f" (x{n})" if n > 1 else "") for (kind, value), n in (before - after).items()]
    english = sorted(set(WORD.findall(prose)), key=str.lower)
    return dropped, english


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    original, rewrite = (Path(a).read_text(encoding="utf-8") for a in args)
    dropped, english = check(original, rewrite)
    for line in dropped:
        print(f"dropped {line}")
    print(f"English words left outside code: {', '.join(english) if english else 'none'}")
    return 1 if dropped else 0


if __name__ == "__main__":
    sys.exit(main())
