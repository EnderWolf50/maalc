import json
from pathlib import Path

import yaml
from PIL import Image

import gift_icons

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
SEARCH = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
RECIPES = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
LIST = yaml.safe_load((DATA / "gift_lists.yaml").read_text(encoding="utf-8"))["default_list"]
ICONS = DATA / "gift_icons"
KEYWORDS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
VESTIGES = set(gift_icons.VESTIGES)
BUYABLE = {g["id"] for g in SEARCH}
KNOWN = BUYABLE | {g["id"] for g in RECIPES["gifts"] + RECIPES["materials"]} | VESTIGES
MAX_BYTES = 800_000  # 397 icons weigh 575 KB (1.4 KB each)


def test_default_list_ids_all_exist():
    ids = LIST["want"] + LIST["keep"] + [i for ids in LIST["gorder"].values() for i in ids]
    assert set(ids) <= KNOWN
    assert len(set(LIST["want"])) == len(LIST["want"]) and len(set(LIST["keep"])) == len(LIST["keep"])
    assert not set(LIST["want"]) & set(LIST["keep"])


def test_default_list_is_the_former_default_team():
    burn = {g["id"] for g in SEARCH if g["keyword"] == "Burn"}
    assert set(LIST["want"]) == burn | {9083}
    keywordless = {g["id"] for g in SEARCH + RECIPES["gifts"] + RECIPES["materials"] if g["keyword"] == "Keywordless"}
    assert set(LIST["keep"]) == (keywordless | VESTIGES) - {9083}
    assert LIST["order"] == KEYWORDS and LIST["fusion_condition"] == "any"


def test_default_gorder_is_tier_iii_to_i_in_data_order():
    for kw in KEYWORDS:
        want = [g["id"] for t in (3, 2, 1) for g in SEARCH if g["keyword"] == kw and g["tier"] == t]
        assert LIST["gorder"][kw] == want


def test_every_gift_has_a_small_transparent_icon():
    index = json.loads((ICONS / "index.json").read_text(encoding="utf-8"))
    assert {int(i) for i in index} == set(gift_icons.gift_ids()) == KNOWN
    transparent = 0
    for i, f in index.items():
        im = Image.open(ICONS / f)
        assert im.mode == "RGBA" and max(im.size) == gift_icons.SIZE, i
        transparent += im.getchannel("A").getextrema()[0] == 0  # a few sprites fill their whole frame
    assert transparent > len(index) * 0.9
    assert {p.name for p in ICONS.glob("*.webp")} == set(index.values())
    assert sum(p.stat().st_size for p in ICONS.glob("*.webp")) < MAX_BYTES
