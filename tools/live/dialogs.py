"""List the confirm-style dialog strings of the game client, to diff against the pipeline's known dialogs.

  python tools/live/dialogs.py [--lang en] [--dir <folder with the Localize JSON>] [--pattern <regex>]

The strings come from `<main checkout>/.local/unpack/` (any `Localize/<lang>/` below it), see
docs/agents/local-dev.md. A Localize file is `{"dataList": [{"id": ..., "content": ...}, ...]}`; UI strings
have a text `id` (`mirrordungeonui_ask_level_up`), story and lyric lines a number, so only text ids are listed.
Output: `<file>\t<id>\t<first 120 characters>`.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parents[1])

from local_dir import main_checkout

CONFIRM = r"\?\s*$|\bClaim\b|\bConfirm\b|Give Up|\bSpend\b|Download|\bProceed\b"


def dialogs(root: Path, pattern: str = CONFIRM):
    pat = re.compile(pattern, re.I | re.M)
    for f in sorted(root.rglob("*.json")):
        data = json.loads(f.read_bytes().decode("utf-8-sig"))  # a few files start with a BOM
        for item in data.get("dataList", []) if isinstance(data, dict) else []:
            id_, text = item.get("id"), item.get("content")
            if isinstance(id_, str) and not id_.isdigit() and isinstance(text, str) and pat.search(text):
                yield f.stem, id_, text


def find_root(lang: str) -> Path:
    base = main_checkout() / ".local" / "unpack"
    for found in base.rglob(lang):
        if found.is_dir() and found.parent.name == "Localize":
            return found
    sys.exit(f"no Localize/{lang}/ under {base}: unpack the game data first (docs/agents/local-dev.md)")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--dir", type=Path)
    ap.add_argument("--pattern", default=CONFIRM)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    for stem, id_, text in dialogs(a.dir or find_root(a.lang), a.pattern):
        print(f"{stem}\t{id_}\t{' '.join(text.split())[:120]}")


if __name__ == "__main__":
    main()
