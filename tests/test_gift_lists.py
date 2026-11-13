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
VESTIGES = {g["id"] for g in RECIPES["vestiges"]}
SOLD = set(RECIPES["shop"]["sells"])  # what a shop may sell (#626)
KEYWORD_GIFTS = SEARCH + RECIPES["gifts"] + RECIPES["materials"] + RECIPES["extra_gifts"]
KNOWN = {g["id"] for g in KEYWORD_GIFTS} | VESTIGES  # what a list may name
ICON_IDS = KNOWN
MAX_BYTES = 2_000_000  # 466 icons of 112 px weigh 1,572 KB (3.4 KB each; 677 KB at 56 px, soft on a 2x screen, #721)


def test_default_list_ids_all_exist():
    ids = LIST["want"] + LIST["keep"] + [i for ids in LIST["gorder"].values() for i in ids]
    assert set(ids) <= KNOWN
    assert len(set(LIST["want"])) == len(LIST["want"]) and len(set(LIST["keep"])) == len(LIST["keep"])
    assert not set(LIST["want"]) & set(LIST["keep"])


# The Keywordless gifts the shop sells that a theme pack's own pool holds (specificEgoGiftPool of the game's
# mirrordungeon-theme-floor-* data, 1.118.1; the unpacked game data is in neither the repo nor CI, so the ids are listed here).
PACK_POOL = [9219, 9225, 9266, 9273, 9276, 9284, 9285, 9302, 9414, 9419, 9420, 9423, 9427, 9431, 9433, 9435, 9439, 9703, 9705, 9707,
             9711, 9712, 9723, 9727, 9732, 9733, 9748, 9749, 9751, 9753, 9755, 9757, 9760, 9762, 9763, 9766, 9769, 9778, 9779,
             9781, 9794, 9801, 9805, 9810, 9811, 9813, 9826]
PACK_POOL_EXTRA = [9208, 9209, 9246, 9752, 9754, 9758, 9797]  # the pools' Keywordless extra_gifts: sold, so wanted since #626
LUNAR_MEMORY = 9083
LUNAR_MATERIALS = [9105, 9110, 9116, 9121, 9126, 9131, 9136, 9142, 9147, 9152]  # its 7 fragments and 3 memories, all tier IV


def test_default_list_wants_the_keywordless_fusions_and_the_pack_pools_keywordless_gifts():
    # The user, 2026-10-30: the default list only holds the Keywordless gifts; it wants the ones a fusion makes, then the
    # ones only a theme pack's pool gives that the shop sells; but not Lunar Memory (the user, 2026-11-11: see the next test).
    fusions = [g["id"] for g in RECIPES["gifts"] if g["keyword"] == "Keywordless"]
    assert fusions == [9083, 9249, 9764, 9780]
    assert LIST["want"] == [9249, 9764, 9780] + sorted(PACK_POOL + PACK_POOL_EXTRA)
    assert len(LIST["want"]) == 57
    assert set(PACK_POOL) <= {g["id"] for g in SEARCH} and set(PACK_POOL + PACK_POOL_EXTRA) <= SOLD
    assert set(PACK_POOL_EXTRA) <= {g["id"] for g in RECIPES["extra_gifts"]}
    pooled = {i for pool in RECIPES["pack_gifts"].values() for i in pool}  # #417: the committed pools, the unpack is not in CI
    assert {g["id"] for g in KEYWORD_GIFTS if g["keyword"] == "Keywordless"} & pooled == set(PACK_POOL) | set(PACK_POOL_EXTRA)
    keywordless = {g["id"] for g in KEYWORD_GIFTS if g["keyword"] == "Keywordless"}  # extra_gifts' too (#310's live run)
    # vestiges I-IV (9991-9994) are fusion materials, so `drop`; Lunar Vestige (V, 9995) is never a material, so `keep`
    assert set(LIST["keep"]) == keywordless - set(LIST["want"]) | {max(VESTIGES)} | set(LUNAR_MATERIALS)
    assert len(LIST["keep"]) == 70  # 59 Keywordless gifts (Lunar Memory among them), the Lunar Vestige, its 10 materials
    assert LIST["order"] == KEYWORDS
    assert LIST["fusion_condition"] == "any"


def test_default_list_keeps_lunar_memory_s_materials_and_buys_nothing_for_it():
    # The user, 2026-11-11 (#626, option C): its 5 materials of tier IV cost about 400 Cost each, and its 5-slot fusion only a
    # Super Shop allows; kept, they are never bought (here), sold or used by an ordinary fusion (tests/test_gift_list_shop.py).
    import gifts  # noqa: PLC0415

    lunar = next(g for g in RECIPES["gifts"] if g["id"] == LUNAR_MEMORY)
    assert sorted(i for group in lunar["groups"] for i in group["ids"]) == LUNAR_MATERIALS
    assert LUNAR_MEMORY not in LIST["want"] and set(LUNAR_MATERIALS) <= set(LIST["keep"])
    bought = [i for i, _ in gifts.purchases(LIST)]
    assert not set(bought) & set(LUNAR_MATERIALS)


def test_default_gorder_is_what_a_shop_may_sell_tier_iv_to_i_in_data_order():
    sold = [g for g in SEARCH + RECIPES["materials"] + RECIPES["extra_gifts"] if g["id"] in SOLD]
    for kw in KEYWORDS:
        want = [g["id"] for t in (4, 3, 2, 1) for g in sold if g["keyword"] == kw and g["tier"] == t]
        assert LIST["gorder"][kw] == want
    assert 9070 in LIST["gorder"]["Poise"] and 9205 in LIST["gorder"]["Bleed"]  # #626: a sold IV; a pack pool's gift


def test_every_gift_has_a_small_transparent_icon():
    index = json.loads((ICONS / "index.json").read_text(encoding="utf-8"))
    assert {int(i) for i in index} == set(gift_icons.gift_ids()) == ICON_IDS
    transparent = 0
    for i, f in index.items():
        im = Image.open(ICONS / f)
        assert im.mode == "RGBA" and max(im.size) == gift_icons.SIZE, i
        transparent += im.getchannel("A").getextrema()[0] == 0  # a few sprites fill their whole frame
    assert transparent > len(index) * 0.9
    assert {p.name for p in ICONS.glob("*.webp")} == set(index.values())
    assert sum(p.stat().st_size for p in ICONS.glob("*.webp")) < MAX_BYTES


def test_the_default_list_is_what_the_data_files_give():
    import default_gift_list  # noqa: PLC0415

    text = (DATA / "gift_lists.yaml").read_text(encoding="utf-8")
    assert default_gift_list.render(text) == text  # run `tools/default_gift_list.py` when this fails
