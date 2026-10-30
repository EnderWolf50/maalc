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
BUYABLE = {g["id"] for g in SEARCH}
KEYWORD_GIFTS = SEARCH + RECIPES["gifts"] + RECIPES["materials"] + RECIPES["extra_gifts"]
KNOWN = {g["id"] for g in KEYWORD_GIFTS} | VESTIGES  # what a list may name
ICON_IDS = KNOWN
MAX_BYTES = 900_000  # 464 icons weigh 675 KB (1.4 KB each)


def test_default_list_ids_all_exist():
    ids = LIST["want"] + LIST["keep"] + [i for ids in LIST["gorder"].values() for i in ids]
    assert set(ids) <= KNOWN
    assert len(set(LIST["want"])) == len(LIST["want"]) and len(set(LIST["keep"])) == len(LIST["keep"])
    assert not set(LIST["want"]) & set(LIST["keep"])


# The Keywordless gifts the shop sells that a theme pack's own pool holds (specificEgoGiftPool of the game's
# mirrordungeon-theme-floor-* data, 1.117.0; the unpacked game data is in neither the repo nor CI, so the ids are listed here).
PACK_POOL = [9219, 9225, 9266, 9273, 9276, 9284, 9285, 9414, 9419, 9420, 9423, 9427, 9431, 9433, 9435, 9439, 9703, 9705, 9707,
             9711, 9712, 9723, 9727, 9732, 9733, 9748, 9749, 9751, 9753, 9755, 9757, 9760, 9762, 9763, 9766, 9769, 9778, 9779,
             9781, 9794, 9801, 9805, 9810, 9811, 9813, 9826]
PACK_POOL_EXTRA = [9208, 9209, 9246, 9752, 9754, 9758, 9797]  # the pools' other Keywordless gifts: extra_gifts, never wanted


def test_default_list_wants_the_keywordless_fusions_and_the_pack_pools_keywordless_gifts():
    # The user, 2026-10-30: the default list only holds the Keywordless gifts; it wants the ones a fusion makes, then the
    # ones only a theme pack's pool gives that the shop sells.
    fusions = [g["id"] for g in RECIPES["gifts"] if g["keyword"] == "Keywordless"]
    assert fusions == [9083, 9249, 9764, 9780]
    assert LIST["want"] == fusions + PACK_POOL
    assert len(LIST["want"]) == 50
    assert all(i in BUYABLE for i in PACK_POOL)
    assert set(PACK_POOL_EXTRA) <= {g["id"] for g in RECIPES["extra_gifts"]}
    assert set(PACK_POOL_EXTRA) <= set(LIST["keep"])
    keywordless = {g["id"] for g in KEYWORD_GIFTS if g["keyword"] == "Keywordless"}  # extra_gifts' too (#310's live run)
    # vestiges I-IV (9991-9994) are fusion materials, so `drop`; Lunar Vestige (V, 9995) is never a material, so `keep`
    assert set(LIST["keep"]) == keywordless - set(LIST["want"]) | {max(VESTIGES)}
    assert len(LIST["keep"]) == 66
    assert LIST["order"] == KEYWORDS
    assert LIST["fusion_condition"] == "any"


def test_default_gorder_is_tier_iii_to_i_in_data_order():
    for kw in KEYWORDS:
        want = [g["id"] for t in (3, 2, 1) for g in SEARCH if g["keyword"] == kw and g["tier"] == t]
        assert LIST["gorder"][kw] == want


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
