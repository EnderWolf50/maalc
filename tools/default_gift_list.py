"""Rewrite the default gift list's want, keep and gorder in assets/resource/base/data/gift_lists.yaml from the data files.

Usage: uv run python tools/default_gift_list.py [--check]
The rules are docs/spec/05-game-data.md section 9 (the user, 2026-10-30 and 2026-11-11): the list holds the Keywordless
gifts and Lunar Memory's materials. `want`: gift_recipes.json's Keywordless fusion gifts in data order but Lunar Memory,
then, by id, the Keywordless gifts a shop may sell (`shop.sells`, #626) that a theme pack's own pool holds (`pack_gifts`).
`keep`: every other Keywordless gift (gift_search.json's in page order, the Lunar Vestige 9995, then gift_recipes.json's in
data order), then Lunar Memory's materials by id (never bought, sold or used by an ordinary fusion). `gorder`:
agent/settings.py default_gorder. The file's other lines (the comment, `order`, `fusion_condition`) stay. --check writes nothing and exits 1 when the file differs.
Rerun it after gift_search_table.py and gift_recipes.py (tools/game_data.py regen does).
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))
import settings  # noqa: E402

OUT = settings.data_dir() / "gift_lists.yaml"
LUNAR_VESTIGE = 9995  # tier V, never a fusion material, so kept; vestiges I-IV are drop (fusion material)
# Not wanted, its materials kept (the user, 2026-11-11, #626 option C): its 5 materials of tier IV cost about 400 Cost each,
# and its 5-slot fusion only a Super Shop allows, so the shop neither buys nor refreshes for them.
LUNAR_MEMORY = 9083


def fields() -> dict[str, list[int]]:
    search, fusion_gifts, materials = settings.gift_tables()
    pooled = {i for pool in settings.pack_gifts().values() for i in pool}
    sold = set(settings.shop_pool()["sells"])
    others = fusion_gifts + materials + settings.extra_gifts()
    fusions = [g["id"] for g in fusion_gifts if g["keyword"] == "Keywordless" and g["id"] != LUNAR_MEMORY]
    lunar = next(g for g in fusion_gifts if g["id"] == LUNAR_MEMORY)
    want = fusions + sorted({g["id"] for g in search + others if g["keyword"] == "Keywordless"} & pooled & sold)
    keep = ([g["id"] for g in search if g["keyword"] == "Keywordless" and g["id"] not in want] + [LUNAR_VESTIGE]
            + [g["id"] for g in others if g["keyword"] == "Keywordless" and g["id"] not in want]
            + sorted(i for group in lunar["groups"] for i in group["ids"]))
    return {"want": want, "keep": keep, **settings.default_gorder()}


def render(text: str, lines: dict[str, list[int]] | None = None) -> str:
    """The file's text with the default list's want, keep and every gorder keyword's line from `lines` (fields())."""
    for key, ids in (lines or fields()).items():
        line = re.compile(rf"^(\s+{key}: )\[[^\]]*\]$", re.M)
        if len(line.findall(text)) != 1:
            raise SystemExit(f"gift_lists.yaml: no single `{key}: [...]` line")
        text = line.sub(lambda m: m[1] + "[" + ", ".join(map(str, ids)) + "]", text)
    return text


def main(argv):
    text, lines = OUT.read_text(encoding="utf-8"), fields()
    new = render(text, lines)
    if "--check" in argv:
        print("gift_lists.yaml is up to date" if new == text else "gift_lists.yaml differs from the data files: rerun tools/default_gift_list.py")
        return 0 if new == text else 1
    OUT.write_text(new, encoding="utf-8")
    print(f"default list -> {OUT}: want {len(lines['want'])}, keep {len(lines['keep'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
