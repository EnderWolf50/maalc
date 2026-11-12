"""Write the fusion gift data: assets/resource/base/data/gift_recipes.json and image/GiftRecipe/<id>.png.

Usage: uv run --group unpack python tools/gift_recipes.py [--release 2026101602] [--no-icons]
Reads `.local/unpack/` (static data, English localization, the pulled UnityCache bundles; see docs/agents/local-dev.md).
Chinese names: tools/llc_text.py (the Localize Limbus Company release; this tool only fills `zh` from it).
Pools: `pack_gifts` is each theme pack's whole `specificEgoGiftPool` (the want_kind rule of agent/gifts.py reads it, #417).
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
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from llc_text import NOTE_ZH, credit, gift_names, release_zip
from game_data import INDEX, UNITY_VERSION, bundle_index, unpack_client
from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
ICONS = REPO / "assets/resource/base/image/GiftRecipe"
STATIC = "static/Assets/Resources_moved/StaticData/static-data"
KEYWORDS = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
            "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}  # the rest: Keywordless
GIFT_IDS = range(9000, 10000)  # the game's gift ids; `extra_gifts` holds those neither gift_search.json, a recipe nor the vestiges list (#332)
VESTIGE_IDS = range(9991, 9996)  # written to `vestiges`: the one place the ids are named, every reader takes them from the data file
SCALE = 0.21  # the icon on the Gift Search page, as for GiftSearch/<id>.png
DROP_POOL = "mirrordungeon-egogift-droppool/mirrordungeon-egogift-droppool-8.json"
LOCKED_DESC = "raw/Localize/en/EN_MirrorDungeonEgoGiftLockedDesc.json"  # the codex text of a gift not acquired yet
FUSE_ONLY = "- Shops - 「Fuse E.G.O Gift」"  # its one unlock condition for a gift only fusing makes
NORMAL = 0  # the typeIndex of mirrordungeon-08.json (hard 1, infinite 2, extreme 3), what excludeTargetIdxList names


def note(client, gift_count, named, fuse_only, unmarked):
    return ("Fusion gifts and their recipes. Recipes: combineFixed (any one of a gift's `recipes` fuses it; each is a list of the "
        "required gift ids; `specific` marks a gift whose recipe uses a theme pack's exclusive gift, `packs` is the union of the "
        "theme pack ids of those gifts (one recipe can need several packs), from isSpecific and the packs' specificEgoGiftPool) and combineMixed (`groups`: take `need` of each group's `ids`) of the game client " + client + "'s "
        "mirror-dungeon-common-data-md8. Ids, tiers, keywords and English names: the same client's ego-gift static data and "
        "EN_EGOgift localization. `materials` are the recipe ingredients gift_search.json does not list. `vestiges` (#161) are the five gifts 9991-9995 (tier I-V, keywordless) that are only fusion or sale material. Icons: "
        "image/GiftRecipe/<id>.png, the game's EgoGiftIcon sprites (by the ego-gift iconId) scaled by 0.21 with transparency "
        "filled green. `extra_gifts` (#332) are the rest of the client's gift ids 9000-9999 (static data ego-gift*, "
        f"{gift_count} in {client}, {named} with a name: 9247 has neither a name nor an icon sprite, so it is left out): no recipe uses "
        "them (some are the theme packs' specificEgoGiftPool gifts, and `shop` names those a shop may sell); "
        "the Gift Search icons ignore them, the shop cell match (agent/gift_cells.py) takes them as candidates, and a gift list "
        "names them as any gift of their keyword. "+NOTE_ZH+" "
        "`shop` (#626) holds the gifts a shop may sell, which a gift list may want: `sells` is the drop pool "
        "mirrordungeon-egogift-droppool-8's egoGifts and the theme packs' own pools (`pack_gifts`: 9205 is in no egoGifts and "
        "was seen on sale, live 2026-10-22), less its globalExcludeEgoGifts, less the gifts whose codex text "
        f"(EN_MirrorDungeonEgoGiftLockedDesc) names one unlock condition, fusing at a shop ({fuse_only} in {client}), less every "
        f"fusion gift here (the codex text does not mark {unmarked}: they stay fusion gifts, never bought). `not_on_normal` are "
        "those of its excludeEgoGifts: excludeTargetIdxList [0] is the typeIndex of mirrordungeon-08.json, NORMAL (read from "
        "the fields, not the game code; live, 79 sightings of them on HARD floors and none in 158 on NORMAL ones). The server "
        "picks each shop's offers from the pool; a theme pack's own gifts (`pack_gifts`) show only in that pack. "
        "`pack_gifts` (#417) is the theme pack id (as a string) -> the gift ids of that pack's specificEgoGiftPool (the gifts only "
        "it can offer), for every pack that has a pool, whether theme_packs.yaml names it or not. "
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


def fusion_only(unpack):
    """The gifts whose codex text names one unlock condition: fusing them at a shop (FUSE_ONLY)."""
    out = set()
    for x in load(unpack / LOCKED_DESC)["dataList"]:
        ways = [line.strip() for line in x["content"].partition("<Unlock Conditions>")[2].splitlines() if line.strip().startswith("-")]
        if ways == [FUSE_ONLY]:
            out.add(int(x["id"]))
    return out


def shop_pool(unpack, fusions, fuse_only, pack_pool):
    """{"sells": the ids a shop may sell, "not_on_normal": those a NORMAL floor's shop does not} (the note's `shop`): the drop
    pool's egoGifts and the theme packs' own pools (`pack_pool`), less the global excludes, the fusion-only gifts
    (`fuse_only`) and the fusion gifts."""
    pool = load(unpack / STATIC / DROP_POOL)["list"][0]
    if pool["excludeTargetIdxList"] != [NORMAL]:
        raise SystemExit(f"{DROP_POOL}: excludeTargetIdxList is {pool['excludeTargetIdxList']}, not [{NORMAL}]: read it again (#626)")
    sells = (set(pool["egoGifts"]) | pack_pool) - set(pool["globalExcludeEgoGifts"]) - fuse_only - set(fusions)
    return {"sells": sorted(sells), "not_on_normal": sorted(sells & set(pool["excludeEgoGifts"]))}


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
    listed = searchable | set(results) | {m["id"] for m in materials} | set(VESTIGE_IDS)
    extra = [entry(i) for i in sorted(table) if i in GIFT_IDS and i in en and i not in listed]
    vestiges = [entry(i) for i in VESTIGE_IDS]
    ids = [i for i in table if i in GIFT_IDS]
    fuse_only = fusion_only(unpack)
    unmarked = " ".join(map(str, sorted(set(results) - fuse_only)))
    shop = shop_pool(unpack, results, fuse_only, {i for p in pools.values() for i in p})
    unknown = set(shop["sells"]) - searchable - {g["id"] for g in materials + extra}
    if unknown:
        raise SystemExit(f"the drop pool sells gifts no list here holds: {sorted(unknown)}")
    return {"note": note(unpack_client(unpack), len(ids), sum(i in en for i in ids), len(fuse_only), unmarked), **credit(release),
            "gifts": gifts, "materials": materials, "extra_gifts": extra, "vestiges": vestiges,
            "pack_gifts": {str(p): sorted(pool) for p, pool in sorted(pools.items())}, "shop": shop}, table


def sprite_index(cache, index_path):
    """Bundle hash -> EgoGiftIcon sprite names, from the bundle index (tools/game_data.py bundle_index)."""
    where = defaultdict(set)
    for line in bundle_index(cache, index_path):
        key, kind, p = (line.split("\t") + ["", ""])[:3]
        name = p.rsplit("/", 1)[-1][:-4]
        if kind == "Sprite" and "/egogifticon/" in p.lower() and name.isdigit():
            where[key.split("/")[0]].add(int(name))
    return where


def extract_icons(unpack, ids_to_icon, write=None, out=ICONS):
    """Write out/<gift id>.png (the green-filled template, GiftRecipe/ unless told) for each {gift id: iconId}, or call
    `write(sprite image, gift id)`; returns the gift ids without a sprite."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    cache = unpack / "raw/UnityCache"
    where = sprite_index(cache, unpack / INDEX)
    by_icon = defaultdict(list)
    for gid, icon in ids_to_icon.items():
        by_icon[icon].append(gid)
    if write is None:
        out.mkdir(parents=True, exist_ok=True)

        def png(image, gid):
            scaled(np.array(image.convert("RGBA")), out / f"{gid}.png")

        write = png

    done = set()
    for h, names in where.items():
        if not names & by_icon.keys() - done:
            continue
        path = next(os.path.join(r, "__data") for r, _, f in os.walk(cache / h) if "__data" in f)
        for p, obj in UnityPy.load(path).container.items():
            name = p.rsplit("/", 1)[-1][:-4]
            if obj.type.name == "Sprite" and "/egogifticon/" in p.lower() and name.isdigit() and int(name) in by_icon and int(name) not in done:
                for gid in by_icon[int(name)]:
                    write(obj.read().image, gid)
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
    entries = data["gifts"] + data["materials"] + data["extra_gifts"]
    print(f"{len(data['gifts'])} fusion gifts, {len(data['materials'])} materials, {len(data['extra_gifts'])} extra gifts; no zh name: {[g['id'] for g in entries if not g['zh']]}")
    if not args.no_icons:
        print("no icon:", extract_icons(unpack, {g["id"]: table[g["id"]][2] for g in entries}))


if __name__ == "__main__":
    main()
