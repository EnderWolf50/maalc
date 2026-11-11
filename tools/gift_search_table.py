"""Write assets/resource/base/data/gift_search.json and image/GiftSearch/<id>.png from the unpacked client (#625).

Usage: uv run --group unpack python tools/gift_search_table.py [--release <LLC tag>] [--no-icons]
Reads `.local/unpack/` (tools/game_data.py): mirror-dungeon-egogift-observation-data-md8.json lists the E.G.O Gift Search
page's tabs and their gifts. The page shows the tabs in the table's order with the keywordless tab last, and each tab's
gifts by tier III, II, I, in the table's order within a tier (the 1.117.0 table gives the live page of 2026-10-16 this
way). Tiers and keywords: tools/gift_recipes.py's gift_table; English names its english_names; Chinese names
tools/llc_text.py. Icons: the EgoGiftIcon sprite scaled as gift_recipes.py's, written for each gift that has none yet.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gift_recipes as gr  # noqa: E402
from game_data import unpack_client  # noqa: E402
from llc_text import NOTE_ZH, credit, current_release, dump_search, gift_names, release_zip  # noqa: E402
from local_dir import local_dir  # noqa: E402

OUT = gr.DATA / "gift_search.json"
ICONS = gr.REPO / "assets/resource/base/image/GiftSearch"
OBSERVATION = "mirror-dungeon-egogift-observation-data/mirror-dungeon-egogift-observation-data-md8.json"
KEYWORDLESS_TAB = "None"


def note(client):
    return ("Gifts the E.G.O Gift Search page offers, tab by tab, tiers III-I, in page order. List, ids, tiers and English "
            f"names: the game client {client}'s static data (mirror-dungeon-egogift-observation-data-md8: its tabs in order, "
            "the keywordless tab last, each tab's gifts by tier III-I in the table's order: the order the live page showed for "
            "1.117.0 on 2026-10-16; the ego-gift tier tags, EN_EGOgift localization). Icon templates: image/GiftSearch/<id>.png, the "
            "game's EgoGiftIcon sprites (by the ego-gift iconId) scaled by 0.21. English names: the plain apostrophe where the "
            "game writes ’ (as this file always had; a version 10 keep_gifts name matches it). Written by "
            "tools/gift_search_table.py. " + NOTE_ZH)


def gifts(unpack) -> tuple[list[dict], dict]:
    """The page's gifts in order, and the observation table's cost list."""
    obs = gr.load(unpack / gr.STATIC / OBSERVATION)["list"][0]
    table, en = gr.gift_table(unpack), gr.english_names(unpack)
    tabs = sorted(obs["observationEgoGiftDataList"], key=lambda t: t["uiKeyword"] == KEYWORDLESS_TAB)
    rows = []
    for tab in tabs:
        for gid in sorted(tab["egogiftIdList"], key=lambda i: -table[i][0]):
            tier, keyword, _ = table[gid]
            rows.append({"id": gid, "keyword": keyword, "tier": tier, "en": en[gid].replace("’", "'")})
    return rows, obs["observationEgoGiftCostDataList"]


def build(unpack, release) -> str:
    rows, costs = gifts(unpack)
    zh = gift_names(release_zip(release))
    data = {"note": note(unpack_client(unpack)), **credit(release),
            "starlight_cost": {str(c["egogiftCount"]): c["starlightCost"] for c in costs},
            "gifts": [{**g, "zh": zh[g["id"]]} for g in rows]}  # a gift the release lacks stops the run
    return dump_search(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=current_release(), help="the LLC release tag the Chinese names come from")
    ap.add_argument("--no-icons", action="store_true", help="write the json only")
    args = ap.parse_args()
    unpack = local_dir("unpack")
    OUT.write_text(build(unpack, args.release), encoding="utf-8")
    rows = json.loads(OUT.read_text(encoding="utf-8"))["gifts"]
    print(f"{len(rows)} gifts -> {OUT}")
    if not args.no_icons:
        table = gr.gift_table(unpack)
        new = {g["id"]: table[g["id"]][2] for g in rows if not (ICONS / f"{g['id']}.png").is_file()}
        missing = gr.extract_icons(unpack, new, out=ICONS)
        print(f"{len(new) - len(missing)} new icons; no sprite: {missing}")  # an icon of a gift that left the page stays (the vestiges' are here too)


if __name__ == "__main__":
    main()
