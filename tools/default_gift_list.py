"""Rewrite the default gift list's want, keep and gorder in assets/resource/base/data/gift_lists.yaml from the data files.

Usage: uv run python tools/default_gift_list.py [--check]
The rules are docs/spec/05-game-data.md section 9 (the user, 2026-10-30): the list holds Keywordless gifts only. `want`:
gift_recipes.json's Keywordless fusion gifts in data order, then, by id, the Keywordless gifts a shop may sell (`shop.sells`,
#626) that a theme pack's own pool holds (`pack_gifts`). `keep`: every other Keywordless gift (gift_search.json's in page
order, the Lunar Vestige 9995, then gift_recipes.json's in data order). `gorder`: agent/settings.py default_gorder. The
file's other lines (the comment, `order`, `fusion_condition`) stay. --check writes nothing and exits 1 when the file differs.
Rerun it after gift_search_table.py and gift_recipes.py (tools/game_data.py regen does).
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))
import settings  # noqa: E402

DATA = REPO / "assets/resource/base/data"
OUT = DATA / "gift_lists.yaml"
LUNAR_VESTIGE = 9995  # tier V, never a fusion material, so kept; vestiges I-IV are drop (fusion material)


def fields() -> dict[str, list[int]]:
    search = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
    recipes = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
    pooled = {i for pool in recipes["pack_gifts"].values() for i in pool}
    sold = set(recipes["shop"]["sells"])
    others = recipes["gifts"] + recipes["materials"] + recipes["extra_gifts"]
    fusions = [g["id"] for g in recipes["gifts"] if g["keyword"] == "Keywordless"]
    want = fusions + sorted({g["id"] for g in search + others if g["keyword"] == "Keywordless"} & pooled & sold)
    keep = ([g["id"] for g in search if g["keyword"] == "Keywordless" and g["id"] not in want] + [LUNAR_VESTIGE]
            + [g["id"] for g in others if g["keyword"] == "Keywordless" and g["id"] not in want])
    return {"want": want, "keep": keep, **settings.default_gorder()}


def render(text: str) -> str:
    """The file's text with the default list's want, keep and every gorder keyword's line from fields()."""
    for key, ids in fields().items():
        line = re.compile(rf"^(\s+{key}: )\[[^\]]*\]$", re.M)
        if len(line.findall(text)) != 1:
            raise SystemExit(f"gift_lists.yaml: no single `{key}: [...]` line")
        text = line.sub(lambda m: m[1] + "[" + ", ".join(map(str, ids)) + "]", text)
    return text


def main(argv):
    text = OUT.read_text(encoding="utf-8")
    new = render(text)
    if "--check" in argv:
        print("gift_lists.yaml is up to date" if new == text else "gift_lists.yaml differs from the data files: rerun tools/default_gift_list.py")
        return 0 if new == text else 1
    OUT.write_text(new, encoding="utf-8")
    print(f"default list -> {OUT}: want {len(fields()['want'])}, keep {len(fields()['keep'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
