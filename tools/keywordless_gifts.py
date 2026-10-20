"""Write assets/resource/base/data/keywordless_gifts.json: the English names of every keywordless Mirror Dungeon gift (#161).

Usage: uv run python tools/keywordless_gifts.py [unpack dir]   (default: .local/unpack of the main checkout)

The shop tells a gift whose badge is cut off by the name its tooltip shows; a keywordless one then follows the team's
keywordless setting alone. data/gift_search.json lists only the Gift Search tiers I-III, so this list comes from the
client's static data: a gift with a tier tag in ego-gift-mirrordungeon whose records name no keyword (a gift id has
several records, and only some carry its keyword: Grimy Iron Stake), less the vestiges (their own kind).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_dir import local_dir  # noqa: E402

UNPACK = Path(sys.argv[1]) if len(sys.argv) > 1 else local_dir("unpack")
STATIC = UNPACK / "static/Assets/Resources_moved/StaticData/static-data"
OUT = Path(__file__).resolve().parent.parent / "assets/resource/base/data/keywordless_gifts.json"
VESTIGES = range(9991, 9996)


def records():
    for f in STATIC.glob("ego-gift*/*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        for g in data.get("list", []) if isinstance(data, dict) else []:
            if isinstance(g, dict) and "id" in g:
                yield f.parent.name, g


def main():
    keyword, tiered = {}, set()
    for folder, g in records():
        if g.get("keyword", "None") != "None":
            keyword[g["id"]] = g["keyword"]
        if folder == "ego-gift-mirrordungeon" and any(re.fullmatch(r"TIER_[1-5]", str(t)) for t in g.get("tag") or []):
            tiered.add(g["id"])
    names = {}
    for f in (UNPACK / "raw/Localize/en").glob("EN_EGOgift*.json"):
        for e in json.loads(f.read_text(encoding="utf-8-sig")).get("dataList", []):
            if e.get("name"):
                names.setdefault(e["id"], e["name"].replace("’", "'"))
    ids = sorted(i for i in tiered - set(keyword) - set(VESTIGES) if i in names)
    doc = {"note": "English names of the keywordless Mirror Dungeon gifts, tiers I-V (#161): the game client's static data "
                   "(ego-gift-mirrordungeon: a tier tag and no keyword on any record of the id, vestiges left out) and "
                   "its EN_EGOgift localization, via tools/keywordless_gifts.py. Game data (c) Project Moon, see NOTICE.md.",
           "client": "1.117.0",
           "names": sorted({names[i] for i in ids})}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(doc['names'])} names ({len(ids)} ids) -> {OUT}")


if __name__ == "__main__":
    main()
