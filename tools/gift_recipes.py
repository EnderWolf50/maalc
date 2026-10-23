"""Write the fusion gift data: assets/resource/base/data/gift_recipes.json and image/GiftRecipe/<id>.png.

Usage: uv run --group unpack python tools/gift_recipes.py [--release 2026101602] [--no-icons]
Reads `.local/unpack/` (static data, English localization, the pulled UnityCache bundles; see docs/agents/local-dev.md).
Chinese names: tools/llc_text.py (the Localize Limbus Company release; this tool only fills `zh` from it).
Recipes: `combineFixed` and `combineMixed` of mirror-dungeon-common-data-md8.json; `specific` is its `isSpecific`, `packs` the
theme packs whose `specificEgoGiftPool` (mirrordungeon-theme-floor-*.json) holds a recipe ingredient.
Icons: the game's EgoGiftIcon sprite of each fusion gift and of each recipe material that gift_search.json lacks, scaled
by 0.21, transparency filled green, as the Gift Search icons. The first run indexes the 12 GB of bundles into
`.local/unpack/out/sprite-index.tsv` (run it as a `bench` ticket, tools/live/queue.py); the quarterly rerun is docs/spec/05-game-data.md section 8.
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llc_text import NOTE_ZH, credit, gift_names, release_zip  # noqa: E402
from local_dir import local_dir  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
ICONS = REPO / "assets/resource/base/image/GiftRecipe"
STATIC = "static/Assets/Resources_moved/StaticData/static-data"
KEYWORDS = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
            "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}  # the rest: Keywordless
SCALE = 0.21  # the icon on the Gift Search page, as for GiftSearch/<id>.png
NOTE = ("Fusion gifts and their recipes. Recipes: combineFixed (any one of a gift's `recipes` fuses it; each is a list of the "
        "required gift ids; `specific` marks a gift whose recipe uses a theme pack's exclusive gift, `packs` is the union of the "
        "theme pack ids of those gifts (one recipe can need several packs), from isSpecific and the packs' specificEgoGiftPool) and combineMixed (`groups`: take `need` of each group's `ids`) of the game client 1.117.0's "
        "mirror-dungeon-common-data-md8. Ids, tiers, keywords and English names: the same client's ego-gift static data and "
        "EN_EGOgift localization. `materials` are the recipe ingredients gift_search.json does not list. Icons: "
        "image/GiftRecipe/<id>.png, the game's EgoGiftIcon sprites (by the ego-gift iconId) scaled by 0.21 with transparency "
        "filled green. "+NOTE_ZH+" "
        "Written by tools/gift_recipes.py.")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def gift_table(unpack):
    """id -> (tier, keyword, iconId) from the ego-gift* static data; the first record that has a tier tag."""
    table = {}
    for path in glob.glob(str(unpack / STATIC / "ego-gift*" / "*.json")):
        data = load(path)
        for x in data.get("list", []) if isinstance(data, dict) else []:
            tiers = [t for t in x.get("tag", []) if t.startswith("TIER_")]
            if tiers and x["id"] not in table:
                table[x["id"]] = (int(tiers[0][5:]), KEYWORDS.get(x.get("keyword"), "Keywordless"), x.get("iconId") or x["id"])
    return table


def english_names(unpack):
    names = {}
    for path in glob.glob(str(unpack / "raw/Localize/en/EN_EGOgift_*.json")):
        for x in load(path).get("dataList", []):
            names.setdefault(x["id"], x["name"])
    return names


def pack_pools(unpack):
    """Theme pack id -> its `specificEgoGiftPool` (the pack-exclusive gifts), from mirrordungeon-theme-floor-*.json."""
    return {x["id"]: set(x["specificEgoGiftPool"]) for p in glob.glob(str(unpack / STATIC / "mirrordungeon-theme-floor/*.json"))
            for x in load(p)["list"] if x.get("specificEgoGiftPool")}


def build(unpack, release):
    combine = load(unpack / STATIC / "mirror-dungeon-common-data/mirror-dungeon-common-data-md8.json")["egoGiftCombineFixedTable"]
    table, en, zh = gift_table(unpack), english_names(unpack), gift_names(release_zip(release))
    searchable = {g["id"] for g in load(DATA / "gift_search.json")["gifts"]}
    recipes, specific = defaultdict(list), set()
    for c in combine["combineFixed"]:
        recipes[c["resultEgoGiftId"]].append(c["requiredEgoGiftIds"])
        if c.get("isSpecific"):
            specific.add(c["resultEgoGiftId"])
    pools = pack_pools(unpack)
    groups = {m["resultEgoGiftId"]: [{"ids": m["aEgoGiftIds"], "need": m["aEgoGiftRequiredNum"]},
                                     {"ids": m["bEgoGiftIds"], "need": m["bEgoGiftRequiredNum"]}] for m in combine["combineMixed"]}

    def entry(gid):
        tier, keyword, _ = table[gid]
        return {"id": gid, "keyword": keyword, "tier": tier, "en": en[gid], "zh": zh[gid]}  # a gift the release lacks stops the run

    results = sorted(recipes.keys() | groups.keys(), key=lambda g: (-table[g][0], g))
    def pack_fields(g):  # a gift's recipes are all flagged or none are (the test checks it)
        if g not in specific:
            return {}
        used_ids = {i for rec in recipes[g] for i in rec}
        return {"specific": True, "packs": sorted(p for p, pool in pools.items() if pool & used_ids)}

    gifts = [{**entry(g), **({"recipes": recipes[g]} if g in recipes else {"groups": groups[g]}), **pack_fields(g)} for g in results]
    used = {i for r in recipes.values() for rec in r for i in rec} | {i for gs in groups.values() for grp in gs for i in grp["ids"]}
    materials = [entry(i) for i in sorted(used - searchable - set(results))]
    return {"note": NOTE, **credit(release), "gifts": gifts, "materials": materials}, table


def sprite_index(cache, index_path):
    """Bundle hash -> EgoGiftIcon sprite names, from a tsv of `hash, type, path` per container entry (built on first use)."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"  # the bundles carry a stripped version, 1.117.0's engine
    if index_path.is_file() and any(not (cache / h.split("\t")[0]).is_dir() for h in index_path.read_text(encoding="utf-8").splitlines()):
        index_path.unlink()  # a new client has new bundle folders: reindex
    if not index_path.is_file():
        with index_path.open("w", encoding="utf-8") as f:
            for root, _, files in os.walk(cache):
                if "__data" in files:
                    try:
                        for p, obj in UnityPy.load(os.path.join(root, "__data")).container.items():
                            f.write(f"{os.path.relpath(root, cache).split(os.sep)[0]}\t{obj.type.name}\t{p}\n")
                    except Exception as e:  # a bundle UnityPy cannot read holds none of the wanted sprites we know of
                        print("skip", root, e, file=sys.stderr)
    where = defaultdict(set)
    for line in index_path.read_text(encoding="utf-8").splitlines():
        h, kind, p = (line.split("\t") + ["", ""])[:3]
        name = p.rsplit("/", 1)[-1][:-4]
        if kind == "Sprite" and "/egogifticon/" in p.lower() and name.isdigit():
            where[h].add(int(name))
    return where


def extract_icons(unpack, ids_to_icon):
    """Write ICONS/<gift id>.png for each {gift id: iconId}; returns the gift ids without a sprite."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"
    cache = unpack / "raw/UnityCache"
    where = sprite_index(cache, unpack / "out/sprite-index.tsv")
    by_icon = defaultdict(list)
    for gid, icon in ids_to_icon.items():
        by_icon[icon].append(gid)
    ICONS.mkdir(parents=True, exist_ok=True)
    done = set()
    for h, names in where.items():
        if not names & by_icon.keys() - done:
            continue
        path = next(os.path.join(r, "__data") for r, _, f in os.walk(cache / h) if "__data" in f)
        for p, obj in UnityPy.load(path).container.items():
            name = p.rsplit("/", 1)[-1][:-4]
            if obj.type.name == "Sprite" and "/egogifticon/" in p.lower() and name.isdigit() and int(name) in by_icon and int(name) not in done:
                for gid in by_icon[int(name)]:
                    scaled(np.array(obj.read().image.convert("RGBA")), ICONS / f"{gid}.png")
                done.add(int(name))
    return sorted(g for icon, gs in by_icon.items() if icon not in done for g in gs)


def scaled(rgba, out):
    """The Gift Search template: 0.21 INTER_AREA, alpha under 128 filled green (BGR 0,255,0)."""
    bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
    h, w = bgra.shape[:2]
    small = cv2.resize(bgra, (round(w * SCALE), round(h * SCALE)), interpolation=cv2.INTER_AREA)
    bgr = small[..., :3].copy()
    bgr[small[..., 3] < 128] = (0, 255, 0)
    cv2.imwrite(str(out), bgr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=load(DATA / "gift_search.json")["zh_release"], help="the LLC release tag the Chinese names come from")
    parser.add_argument("--no-icons", action="store_true", help="write the json only")
    args = parser.parse_args()
    unpack = local_dir("unpack")
    data, table = build(unpack, args.release)
    (DATA / "gift_recipes.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    entries = data["gifts"] + data["materials"]
    print(f"{len(data['gifts'])} fusion gifts, {len(data['materials'])} materials; no zh name: {[g['id'] for g in entries if not g['zh']]}")
    if not args.no_icons:
        print("no icon:", extract_icons(unpack, {g["id"]: table[g["id"]][2] for g in entries}))


if __name__ == "__main__":
    main()
