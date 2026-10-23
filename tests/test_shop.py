import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

import shop as s

# Grid crops of live 1280x720 captures (written by recovery.png: one IDAT, filter 0), and where each sat on screen.
CROPS = Path(__file__).resolve().parent / "shop"
SCREENS = Path(__file__).resolve().parent / "screens"
CROP_AT = {
    "fuse_spiderweb": (620, 236),  # live 2026-10-18 (probe capture rec/m3/fuse-140): Spiderweb Entangled in Red first
    "fuse": (620, 236),  # tests/screens/ShopFuse.png
    "fuse_recipe": (620, 236),  # tests/screens/ShopFuseRecipe.png (#103): the owned row sits at y 427
    "fuse_tooltip": (620, 236),  # a tooltip (Hellterfly's Dream's) over the first row's right half and the row under it (#297)
    # The fuse page's slots and first two columns (#77): live 2026-10-18 (probe capture rec/m3/fuse-152), Spiderweb tapped
    # in; captures/97 (2 in, a tooltip over the grid), Super Shop captures/172 (cells 5 and 6 in) and 169 (empty).
    "fuse_one_in": (180, 165),
    "fuse_two_in": (180, 165),
    "fuse_super_two_in": (180, 165),
    "fuse_super_open": (180, 165),
    # The Forecasts row of live 2026-10-23 captures (1080p scaled to 720p, #285): a shop's I + II + I (II Guaranteed, 90%)
    # and a Super Shop's II + II + III (IV Guaranteed, 90%).
    "forecast_shop_ii": (180, 165),
    "forecast_super_iv": (180, 165),
    "sell": (620, 200),  # live 2026-10-16 (probe capture s29/025_sell): the sell page of ShopFuse.png's gifts
    "offers": (560, 210),  # tests/screens/Shop.png
    "offers_super": (560, 210),  # tests/screens/SuperShop.png
    "offers_red": (560, 210),  # live (probe capture s28/013): Fragment of Hellfire, a red gem, 400 orange
    "offers_short": (560, 210),  # live 2026-10-18 (probe capture live-all/f/shopd_2590.6): 106 Cost, 3 offers tagged Not Enough Cost
    # Map nodes (test_map_shop.py): 200 px around the node, live 2026-10-18 probe capture live2/f (map_f2_c, map_f1_c, map_f1_a)
    "map_shop_cyan": (230, 45),
    "map_shop_orange": (230, 45),
    "map_event_orange": (226, 44),
    # The shop's "+" variant on hard floors (#287): the 120 px window around the node, live captures of 2026-10-22; the notshop
    # ones are the slots that scored highest on its templates among 1187 others
    **{name: (270, 85) for name in ("map_shop_plus0", "map_shop_plus1", "map_shop_plus2", "map_shop_plus3", "map_shop_plus4",
                                    "map_shop_plus5", "map_shop_torn", "map_notshop0", "map_notshop1", "map_notshop2",
                                    "map_notshop3")},
}
OWNED, OFFER = 1.1, 0.8  # a gift icon's size on the fuse / sell pages and on the offers, over its GiftSearch template's


def screen_with(name):
    """A black 1280x720 BGR screen with the crop tests/shop/<name>.png back in its place."""
    data = (CROPS / f"{name}.png").read_bytes()
    w, h = struct.unpack(">II", data[16:24])
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(h, 1 + w * 3)
    x, y = CROP_AT[name]
    image = np.zeros((720, 1280, 3), np.uint8)
    image[y:y + h, x:x + w] = rows[:, 1:].reshape(h, w, 3)[:, :, ::-1]
    return image


@pytest.mark.parametrize("name, scale, cells, tiers", [
    ("fuse_spiderweb", OWNED, [(678 + 96 * c, 294) for c in range(5)], [3, 2, 2, 1, 1]),
    ("fuse_recipe", OWNED, [(678 + 96 * c, 427) for c in range(5)], [1, 4, 4, 3, 3]),
    ("fuse_recipe", OWNED, [(678, 293)], [4]),  # the Fusion Available cell
    ("offers", OFFER, [(624, 265), (778, 265), (932, 265), (1086, 265), (624, 418)], [None, 1, 2, 2, 2]),  # a skill first
    ("offers_super", OFFER, [(624 + 154 * c, 418) for c in range(4)], [2, 1, 1, 1]),  # flames and a sun by the numerals
])
def test_tier_is_read_from_the_cells_numerals(name, scale, cells, tiers):
    image = screen_with(name)
    assert [s.tier(s.cell_crop(image, x, y, scale)) for x, y in cells] == tiers


def test_can_spend_keeps_the_reserve():
    assert s.can_spend(300, 200, 100)
    assert not s.can_spend(299, 200, 100)


@pytest.mark.parametrize("mode, cost, reserve, dead, plan", [
    ("none", 3000, 0, 3, None),
    ("full", 100, 0, 0, ("full", 1)),
    ("full", 199, 100, 0, None),  # heal all only at Cost >= 100 + reserve
    ("revive", 3000, 0, 0, None),  # nobody dead
    ("revive", 3000, 0, 2, ("revive", 2)),
    ("revive", 250, 0, 3, ("revive", 2)),  # as many as the Cost pays for
    ("revive", 250, 100, 3, ("revive", 1)),
    ("revive", 150, 100, 3, None),
])
def test_heal_plan(mode, cost, reserve, dead, plan):
    assert s.heal_plan(mode, cost, reserve, dead, 100) == plan


@pytest.mark.parametrize("cost, reserve, used, limit, choice", [
    (210, 0, 0, 2, "keyword"),  # 90 + 120
    (209, 0, 0, 2, "normal"),  # short of a keyword refresh: 15 + 120 still fits
    (134, 0, 0, 2, None),
    (310, 100, 0, 2, "keyword"),  # the reserve counts on top
    (309, 100, 0, 2, "normal"),
    (3000, 0, 2, 2, None),  # limit reached; both kinds count
    (3000, 0, 0, 0, None),
])
def test_refresh_choice(cost, reserve, used, limit, choice):
    assert s.refresh_choice(cost, reserve, used, limit, 15, 90, 120) == choice


def test_refresh_choice_unread_fee_is_skipped():
    assert s.refresh_choice(3000, 0, 0, 2, 15, None, 120) == "normal"
    assert s.refresh_choice(3000, 0, 0, 2, None, None, 120) is None


def test_to_sell_the_dearest_spare_first():
    gifts = [(0, 50), (2, 100), (5, 90), (7, 60)]
    assert s.to_sell(gifts, 200, 120, 0) == [2]
    # Nothing spare: no sale helps.
    assert s.to_sell([], 200, 120, 0) is None
    # Two spare, both needed; sold from the back so earlier cells stay put.
    assert s.to_sell([(1, 50), (4, 60)], 200, 100, 0) == [4, 1]
    # Already affordable: nothing to sell.
    assert s.to_sell([(1, 50)], 200, 300, 0) == []
    # The reserve counts too.
    assert s.to_sell([(1, 50)], 200, 200, 60) is None


def test_to_sell_takes_an_avoided_gift_first():
    # #90: White Gossypium (cell 7, 60) goes before the dearer leftover.
    gifts = [(0, 50), (2, 100), (5, 90), (7, 60)]
    assert s.to_sell(gifts, 150, 100, 0, first={7}) == [7]


def ocr(*lines):
    return [(t, box) for t, box in lines]


def test_read_slots_from_live_ocr():
    # 1.117.0 floor 5 shop: a skill slot priced "??", four gifts, junk tier numerals on the icons.
    results = ocr(
        ("Replace Ryōshū's Skill", (558, 334, 131, 14)), ("Reverberation", (576, 486, 94, 17)),
        ("216", (595, 457, 49, 25)), ("来??", (598, 305, 42, 24)), ("155", (749, 306, 48, 23)),
        ("Rags", (757, 330, 39, 21)), ("1", (794, 280, 9, 10)), ("Plume of Proof", (882, 333, 97, 17)),
        ("米", (905, 310, 14, 15)), ("203", (920, 306, 31, 22)), ("Temporal Bridle", (1035, 334, 100, 14)),
        ("212", (1056, 305, 48, 24)),
    )
    slots = s.read_slots(results)
    assert [(x["name"], x["price"]) for x in slots] == [
        ("Replace Ryōshū's Skill", None), ("Rags", 155), ("Plume of Proof", 203), ("Temporal Bridle", 212), ("Reverberation", 216),
    ]
    assert [s.buyable(x) for x in slots] == [False, True, True, True, True]


# #216: the OCR lines of two live shops (2026-10-22, NORMAL, replayed from the recordings) whose first slot is a skill
# replacement. A stray glyph from a gift icon's corner (the keyword badge: "3", "5", "8") reads as a tall line without
# letters, so it passed for a price and the real price just under it became its name ('196' 3, '214' 3).
STONE_TOMB_SHOP = ocr(
    ("Replace Ryōshū's Skill", (557, 330, 131, 19)), ("Pendant of Nostalgia", (557, 484, 132, 19)),
    ("Purchased", (581, 372, 85, 18)), (" 145", (595, 459, 48, 23)), ("米??", (599, 305, 42, 24)),
    ("8", (635, 426, 20, 23)), ("Melted Paraffin", (727, 334, 99, 15)), ("150", (750, 307, 46, 20)),
    ("Stone Tomb", (890, 332, 82, 18)), ("196", (903, 307, 47, 20)), ("3", (945, 275, 15, 18)),
    ("Bloody Gadget", (1035, 331, 99, 18)), ("163", (1057, 307, 46, 20)),
)
OLD_DOLL_SHOP = ocr(
    ("Replace Gregor's Skill", (558, 331, 131, 18)), ("Deathseeker", (580, 485, 85, 18)), ("271", (597, 459, 46, 23)),
    ("??", (599, 306, 42, 23)), ("Portable Battery Socket", (711, 332, 131, 16)), ("190", (750, 307, 46, 20)),
    ("Old Wooden Doll", (877, 332, 109, 18)), ("214", (903, 306, 48, 23)), ("3", (945, 275, 14, 18)),
    ("Rusted Muzzle", (1036, 332, 98, 18)), ("164", (1057, 307, 46, 20)), ("5", (1097, 277, 18, 18)),
)


def test_a_glyph_on_an_icon_is_not_a_price_and_the_real_price_is_not_its_name():
    slots = s.read_slots(OLD_DOLL_SHOP)
    assert [(x["name"], x["price"]) for x in slots] == [
        ("Replace Gregor's Skill", None), ("Portable Battery Socket", 190), ("Old Wooden Doll", 214), ("Rusted Muzzle", 164),
        ("Deathseeker", 271),
    ]
    assert [s.on_sale(x) for x in slots] == [False, True, True, True, True]


def test_a_glyph_over_the_price_of_a_bought_slot_is_not_a_slot_either():
    slots = s.read_slots(STONE_TOMB_SHOP)
    assert [(x["name"], x["price"]) for x in slots] == [
        ("Replace Ryōshū's Skill", None), ("Melted Paraffin", 150), ("Stone Tomb", 196), ("Bloody Gadget", 163),
        ("Pendant of Nostalgia", 145),
    ]
    assert [s.on_sale(x) for x in slots] == [False, True, True, True, False]  # the Replace slot, the bought one


def test_a_price_whose_name_is_not_read_is_still_a_slot():
    assert [(x["name"], x["price"]) for x in s.read_slots(ocr(("150", (750, 307, 46, 20))))] == [("", 150)]


def test_read_slots_purchased():
    results = ocr(("UPS System", (581, 483, 84, 20)), ("Purchased", (582, 373, 83, 18)), ("156", (595, 457, 49, 25)),
                  ("Thorny Path", (737, 332, 81, 17)), ("160", (749, 306, 48, 23)))
    slots = {x["name"]: x for x in s.read_slots(results)}
    assert slots["UPS System"]["purchased"] and not s.buyable(slots["UPS System"])
    assert not slots["Thorny Path"]["purchased"] and s.buyable(slots["Thorny Path"])


def test_read_slots_not_enough_cost():
    # Live 2026-10-18, 77 Cost: the dearer offers carry a red "Not Enough Cost" where a bought one says Purchased.
    results = ocr(("Tomorrow's Fortune", (713, 333, 128, 17)), ("Not-Enough-Cost", (733, 221, 90, 12)), ("140", (760, 307, 30, 22)),
                  ("Thorny Path", (1023, 332, 81, 17)), ("60", (1040, 306, 30, 23)))
    slots = {x["name"]: x for x in s.read_slots(results)}
    assert slots["Tomorrow's Fortune"]["short"] and not s.buyable(slots["Tomorrow's Fortune"])
    assert not slots["Thorny Path"]["short"] and s.buyable(slots["Thorny Path"])


def test_an_offer_dearer_than_the_cost_is_not_opened():
    slot = {"name": "Devil's Share", "price": 144, "purchased": False, "short": False}
    assert not s.buyable(slot, cost=77)
    assert s.buyable(slot, cost=144) and s.buyable(slot, cost=None)  # unread Cost: open it and see


def test_an_offer_too_dear_is_still_on_sale():
    # Its badge tells its keyword without opening it (#76): it can become the gift to sell for.
    dear = {"name": "Devil's Share", "price": 144, "purchased": False, "short": True}
    assert s.on_sale(dear) and not s.buyable(dear, cost=77)
    assert not s.on_sale({"name": "Replace Ryōshū's Skill", "price": None, "purchased": False, "short": False})
    assert not s.on_sale({"name": "UPS System", "price": 156, "purchased": True, "short": False})


def test_a_skill_offer_is_not_on_sale_however_ocr_reads_its_name():
    # #138: a stray price read next to it, the name in capitals or run together.
    for name in ("REPLACE RYOSHU'S SKILL", "ReplaceRyōshū's Skill", "Ｒｅｐｌａｃｅ Ryōshū's Skill"):
        assert not s.on_sale({"name": name, "price": 100, "purchased": False, "short": False}), name


def test_dialog_price_from_the_cost_preview():
    assert s.dialog_price(2864, "28642612") == 252  # live OCR runs the two numbers together
    assert s.dialog_price(540, "540 ▶ 384") == 156
    assert s.dialog_price(2618, "2218") is None  # not the Cost we read
    assert s.dialog_price(2618, "2618") is None
    assert s.dialog_price(None, "28642612") is None


POINTS = {1: 3, 2: 6, 3: 10, 4: 15, 5: 30}  # data/shop.yaml
SHOP, SUPER = [10, 16, 24], [9, 14, 21]


@pytest.mark.parametrize("points, shop, super_shop", [
    (9, 1, 1), (10, 1, 2), (11, 2, 2), (14, 2, 2), (15, 2, 3), (16, 2, 3), (17, 3, 3), (21, 3, 3), (22, 3, 4),
    (24, 3, 4), (25, 4, 4),
])
def test_fusion_tier_follows_the_points(points, shop, super_shop):
    assert (s.fusion_tier(points, SHOP), s.fusion_tier(points, SUPER)) == (shop, super_shop)


def test_pick_fusion_makes_the_highest_tier_first():
    # #77: III + III + II = 26 points, a tier IV; the three I left fuse into a tier I.
    materials = [("a", 1), ("b", 3), ("c", 1), ("d", 2), ("e", 3), ("f", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["b", "d", "e"], 4), (["a", "c", "f"], 1)]


def test_pick_fusion_of_three_tier_one_gives_tier_one():
    assert s.pick_fusion([("a", 1), ("b", 1), ("c", 1)], 3, SHOP, POINTS) == [(["a", "b", "c"], 1)]
    assert s.pick_fusion([("a", 1), ("b", 1)], 3, SHOP, POINTS) == []  # fewer than 3: nothing


def test_pick_fusion_takes_the_fewest_points_for_the_tier():
    # IV takes 25 points: III + III + II (26) rather than III + III + III (30); the III left over waits.
    materials = [("a", 3), ("b", 3), ("c", 3), ("d", 2)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["a", "b", "d"], 4)]


def test_pick_fusion_on_a_super_shop_fills_its_5_slots_by_its_own_thresholds():
    # 5 tier I are 15 points: tier III at a Super Shop (15-21), where 3 of them make only a tier I.
    materials = [(k, 1) for k in "abcde"]
    assert s.pick_fusion(materials, 5, SUPER, POINTS) == [(list("abcde"), 3)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["a", "b", "c"], 1)]
    # II + II + I = 15: tier III at a Super Shop, II at a shop.
    assert s.pick_fusion([("a", 2), ("b", 2), ("c", 1)], 5, SUPER, POINTS) == [(["a", "b", "c"], 3)]


ASSETS = Path(__file__).resolve().parents[1] / "assets" / "resource" / "base" / "data"
# mirror-dungeon-common-data-md8.json (client 1.117.0, read 2026-10-22) egoGiftCombineTierTable: combineTwo and combineThree.
GAME_TWO = [(1, 1, 1), (1, 2, 1), (1, 3, 2), (2, 2, 2), (2, 3, 2), (3, 3, 3)]  # a, b, the tier it gives
GAME_THREE = [(1, 1, 1, 1), (1, 1, 2, 2), (1, 1, 3, 2), (1, 2, 2, 2), (1, 2, 3, 3), (1, 3, 3, 3), (2, 2, 2, 3), (2, 2, 3, 3),
              (2, 3, 3, 4), (3, 3, 3, 4)]


def test_the_data_file_holds_the_games_points_and_thresholds():
    # The guide in the game (mirrordungeon_egogift_combine_guide_result_total_*): 10-/11~16/17~24/25+ in a shop, and with
    # the _upgrade keys (the Super Shop, mirrordungeon_upgrade_shop_title) 9-/10~14/15~21/22+.
    d = yaml.safe_load((ASSETS / "shop.yaml").read_text(encoding="utf-8"))
    assert d["fusion_points"] == POINTS
    assert d["fusion_tiers"] == {"shop": SHOP, "super_shop": SUPER}


@pytest.mark.parametrize("tiers", [row[:-1] for row in GAME_TWO + GAME_THREE])
def test_the_points_of_a_shop_give_the_games_own_table_for_two_and_three_materials(tiers):
    # combineTwo / combineThree hold no result the shop's points table does not give.
    want = {row[:-1]: row[-1] for row in GAME_TWO + GAME_THREE}[tiers]
    assert s.fusion_tier(sum(POINTS[t] for t in tiers), SHOP) == want


@pytest.mark.parametrize("tiers, shop, super_shop", [
    ((1, 1, 3), 2, 3), ((1, 2, 2), 2, 3), ((1, 3, 3), 3, 4), ((2, 2, 3), 3, 4), ((2, 3), 2, 3), ((2, 2, 2), 3, 3),
    ((1, 1, 1), 1, 1), ((1, 3), 2, 2),
])
def test_a_super_shop_gives_a_higher_tier_for_some_of_the_same_materials(tiers, shop, super_shop):
    points = sum(POINTS[t] for t in tiers)
    assert (s.fusion_tier(points, SHOP), s.fusion_tier(points, SUPER)) == (shop, super_shop)


@pytest.mark.parametrize("condition, in_shop, in_super_shop", [
    ("any", [(list("abc"), 3)], [(list("abc"), 4)]),
    ("upgrade", [], [(list("abc"), 4)]),  # III + III + I: a III is no upgrade of a III; a Super Shop's IV is
    ("tier4", [], [(list("abc"), 4)]),
])
def test_the_fusion_condition_reads_the_tier_of_the_shop_it_is_in(condition, in_shop, in_super_shop):
    materials = [("a", 3), ("b", 3), ("c", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition=condition) == in_shop
    assert s.pick_fusion(materials, 3, SUPER, POINTS, condition=condition) == in_super_shop


def test_the_upgrade_condition_in_a_super_shop_with_the_materials_of_a_shop_iii():
    # II + II + I is 15 points: a II in a shop (no upgrade of a II), a III in a Super Shop.
    materials = [("a", 2), ("b", 2), ("c", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="upgrade") == []
    assert s.pick_fusion(materials, 3, SUPER, POINTS, condition="upgrade") == [(list("abc"), 3)]


@pytest.mark.parametrize("name, is_super", [("SuperShop", True), ("Shop", False)])
def test_a_super_shop_is_told_by_its_red_title(name, is_super):
    image = np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]
    assert s.is_super(image) == is_super


def test_the_super_shop_title_sweep_over_tests_screens():
    # CODING_STANDARDS "Recognition": is_super only runs on a shop's main page, but over every 1280x720 screen of tests/screens
    # its one false positive is not a shop page: the update download, a red screen (the resource download and a battle
    # turn have a few red pixels, under the threshold).
    hits = []
    for path in sorted(SCREENS.glob("*.png")):
        image = np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1]
        if image.shape[:2] == (720, 1280) and s.is_super(image):
            hits.append(path.stem)
    assert hits == ["DownloadingUpdate", "SuperShop"]


def test_pick_fusion_any_makes_every_group_it_can():
    # #263: the default fuses a group that gives no higher tier than its materials: three I make a I.
    assert s.pick_fusion([("a", 1), ("b", 1), ("c", 1)], 3, SHOP, POINTS, condition="any") == [(["a", "b", "c"], 1)]


def test_pick_fusion_upgrade_wants_a_tier_over_the_highest_material():
    # #263: three I stay a I, IV + I + I (21 points) is a III: neither is worth the materials.
    assert s.pick_fusion([("a", 1), ("b", 1), ("c", 1)], 3, SHOP, POINTS, condition="upgrade") == []
    assert s.pick_fusion([("a", 4), ("b", 1), ("c", 1)], 3, SHOP, POINTS, condition="upgrade") == []
    # II + II + I = 15 is a II, no better than its II; II + II + II = 18 is a III.
    assert s.pick_fusion([("a", 2), ("b", 2), ("c", 1)], 3, SHOP, POINTS, condition="upgrade") == []
    assert s.pick_fusion([("a", 2), ("b", 2), ("c", 2)], 3, SHOP, POINTS, condition="upgrade") == [(list("abc"), 3)]


def test_pick_fusion_upgrade_skips_the_best_group_when_it_is_no_upgrade():
    # #263: IV + II + II is a IV (27 points), the most; but a IV material cannot be topped, so II + II + II (a III) is made.
    materials = [("a", 4), ("b", 2), ("c", 2), ("d", 2)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="tier4") == [(["a", "b", "c"], 4)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="upgrade") == [(["b", "c", "d"], 3)]


def test_pick_fusion_any_makes_an_upgrade_before_a_higher_tier_that_is_none():
    # user 2026-10-23: IV + II + II is a IV (the highest) but no upgrade; II + II + II is a III over its II: made first.
    materials = [("a", 4), ("b", 2), ("c", 2), ("d", 2)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["b", "c", "d"], 3)]

    # each shop's own thresholds say what upgrades: bce (II + II + I, 15 points) is a II in a shop, a III in a Super Shop.
    materials = [("a", 4), ("b", 2), ("c", 2), ("e", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["a", "b", "c"], 4)]
    assert s.pick_fusion(materials, 3, SUPER, POINTS) == [(["b", "c", "e"], 3)]


def test_pick_fusion_tier4_makes_only_a_tier_iv():
    # #263: III + III + II (26 points) is a IV; the three I left would make a I and stay.
    materials = [("a", 1), ("b", 3), ("c", 1), ("d", 2), ("e", 3), ("f", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="tier4") == [(["b", "d", "e"], 4)]
    assert s.pick_fusion([(k, 3) for k in "abc"], 3, SHOP, POINTS, condition="tier4") == [(list("abc"), 4)]
    assert s.pick_fusion([(k, 1) for k in "abc"], 3, SHOP, POINTS, condition="tier4") == []
    # III + III + I is 23 points: a III in a shop, a IV in a Super Shop (22 and up).
    materials = [("a", 3), ("b", 3), ("c", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="tier4") == []
    assert s.pick_fusion(materials, 5, SUPER, POINTS, condition="tier4") == [(list("abc"), 4)]


def test_pick_fusion_tier4_can_use_more_slots_to_get_there():
    # #263: a Super Shop's 5 slots: 5 x III is 50 points; with 5 II (30 points) a IV needs only 22.
    assert s.pick_fusion([(k, 2) for k in "abcde"], 5, SUPER, POINTS, condition="tier4") == [(list("abcd"), 4)]
    assert s.pick_fusion([(k, 2) for k in "abcde"], 3, SHOP, POINTS, condition="tier4") == []


def test_pick_fusion_never_takes_a_tier_v_gift():
    # #161, the user: a fusion tops out at tier IV, so a tier V material is always a downgrade; not even to make a group.
    assert s.pick_fusion([("v", 5), ("a", 1), ("b", 1)], 3, SHOP, POINTS) == []
    assert s.pick_fusion([("v", 5), ("a", 3), ("b", 3), ("c", 2)], 5, SUPER, POINTS) == [(["a", "b", "c"], 4)]


def test_pick_fusion_puts_an_avoided_gift_in_first():
    # #90: White Gossypium ("w", a II) goes in rather than the other II for the same tier.
    materials = [("a", 2), ("b", 2), ("c", 2), ("w", 2)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(["a", "b", "c"], 3)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, first={"w"}) == [(["a", "b", "w"], 3)]


@pytest.mark.parametrize("name, placed, picked", [
    ("ShopFuse", 0, []), ("ShopFuseRecipe", 3, [0]),
    ("ShopFuseLocked", 0, []),  # #304: "Select a Keyword." dims the list; nothing is placed or framed
    ("ShopFuseAvailable", 0, []),  # #304: keyword picked, the Fusion Available cell is not framed until its materials go in
    ("ShopFuseRecipeTwo", 2, [0]),  # #304: tapping the Fusion Available cell put its 2 materials in the slots and framed it
])
def test_the_fuse_read_back_on_the_whole_fuse_pages_of_tests_screens(name, placed, picked):
    # CODING_STANDARDS' sweep of fuse_slots, placed and picked: no false hit. ShopFuseRecipe really holds 3 materials
    # in its slots, and its Fusion Available cell (where FUSE_CELLS' cell 0 sits) is framed orange.
    image = np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]
    cells = [(678 + 96 * c, y) for y in (294, 385, 477) for c in range(5)]
    assert s.fuse_slots(image) == 3
    assert s.placed(image, 3) == placed
    assert [i for i, (x, y) in enumerate(cells) if s.picked(image, x, y, 493)] == picked


@pytest.mark.parametrize("name, slots, placed, picked", [
    ("fuse_one_in", 3, 1, [0]),  # Spiderweb, cell 0, in the right slot
    ("fuse_two_in", 3, 2, [0, 1]),
    ("fuse_super_two_in", 5, 2, [5, 6]),
    ("fuse_super_open", 5, 0, []),  # "Select a Keyword." over the grid
])
def test_the_fuse_page_reads_back_its_slots_and_the_picked_cells(name, slots, placed, picked):
    image = screen_with(name)
    cells = [(678 + 96 * c, y) for y in (294, 385) for c in range(2)]  # the first two columns on these crops
    index = [0, 1, 5, 6]
    assert s.fuse_slots(image) == slots
    assert s.placed(image, slots) == placed
    assert [i for i, (x, y) in zip(index, cells) if s.picked(image, x, y)] == picked


@pytest.mark.parametrize("name, tier", [
    ("fuse_two_in", 1), ("fuse_super_two_in", 1),  # captures/97 and 172: "I Guaranteed, Bleed 60%"
    ("forecast_shop_ii", 2), ("forecast_super_iv", 4),
    ("fuse_super_open", None), ("fuse_one_in", None),  # the row shows nothing before a second material is in
])
def test_the_forecasts_row_tier_is_read_from_the_fuse_page(name, tier):
    assert s.forecast_tier(screen_with(name)) == tier


@pytest.mark.parametrize("name, tier", [("ShopFuse", None), ("ShopFuseRecipe", 4)])  # a fixed recipe: IV, 100%
def test_the_forecasts_row_tier_on_the_whole_fuse_pages_of_tests_screens(name, tier):
    assert s.forecast_tier(np.asarray(Image.open(SCREENS / f"{name}.png").convert("RGB"))[:, :, ::-1]) == tier


def test_the_forecasts_row_tier_reads_a_tier_iii_and_never_a_tier_v():
    # No live capture shows a III or a V: a third bar painted next to the II's, and the IV's I bar taken away.
    ii = screen_with("forecast_shop_ii")
    iii = ii.copy()
    iii[459:477, 321:324] = ii[459:477, 316:319]
    assert s.forecast_tier(iii) == 3
    v = screen_with("forecast_super_iv")
    v[459:477, 308:311] = 0  # the IV's I bar (x 308-310 at this size)
    assert s.forecast_tier(v) is None  # a V is no tier a fusion gives


def test_the_forecasts_row_sweep_over_tests_screens_finds_no_unlisted_hit():
    # CODING_STANDARDS' sweep: the reading is asked on the fuse page only, yet of the 1280x720 screens of tests/screens
    # one other reads a tier (a yellow numeral in the box on the gift-get page over the map).
    hits = {}
    for png in sorted(SCREENS.glob("*.png")):
        img = Image.open(png)
        if img.size == (1280, 720):
            hits[png.stem] = s.forecast_tier(np.asarray(img.convert("RGB"))[:, :, ::-1])
    # ShopFuseRecipeTwo (#304) is a fuse page with a recipe placed: its row reads III Guaranteed.
    assert {k: v for k, v in hits.items() if v} == {"GiftGetOverMap": 1, "ShopFuseRecipe": 4, "ShopFuseRecipeTwo": 3}


def test_pick_fusion_leaves_out_a_refused_group():
    # #285: the page turned down a III + III + II (a IV by the points); the next best is made, and none when every group
    # was turned down. The forecast depends on the tiers only: another III + III + II is left out, too.
    materials = [("a", 3), ("b", 3), ("c", 2), ("d", 1)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="tier4") == [(list("abc"), 4)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, condition="tier4", refused=[(2, 3, 3)]) == []
    assert s.pick_fusion(materials, 3, SHOP, POINTS) == [(list("abc"), 4)]
    assert s.pick_fusion(materials, 3, SHOP, POINTS, refused=[(2, 3, 3)]) == [(list("acd"), 3)]  # fewest points of the III
    assert s.pick_fusion(materials + [("e", 2)], 3, SHOP, POINTS, condition="tier4", refused=[(2, 3, 3)]) == []


SELL_OCR = [  # Maa OCR of the sell page's grid (crop "sell"): coins read as 米/水/*, icon art as junk
    ('生', (656, 330, 29, 40)), ('米', (659, 293, 21, 21)), ('Rooy', (678, 342, 35, 48)), ('100', (680, 293, 26, 20)),
    ('100', (680, 400, 26, 21)), ('*', (755, 294, 19, 19)), ('水', (756, 402, 17, 18)), ('2', (760, 479, 12, 12)),
    ('50', (773, 292, 23, 22)), ('97', (775, 400, 19, 20)), ('米', (847, 296, 14, 15)), ('水', (848, 403, 18, 16)),
    ('Fa', (857, 349, 20, 17)), ('131', (867, 294, 20, 18)), ('91', (867, 401, 18, 19)), ('关', (936, 399, 22, 22)),
    ('*', (940, 295, 17, 18)), ('0', (949, 441, 27, 23)), ('99', (958, 294, 20, 19)), ('101', (958, 401, 21, 19)),
    ('光', (973, 378, 23, 23)), ('61N', (977, 487, 18, 8)), ('米', (1029, 401, 21, 19)), ('*', (1031, 295, 18, 18)),
    ('石', (1039, 452, 14, 13)), ('ZA', (1048, 463, 14, 13)), ('93', (1050, 294, 20, 19)), ('96', (1050, 401, 21, 19)),
    ('4', (1053, 255, 9, 12)),
]


def test_sell_prices_are_the_numbers_under_each_cell():
    cells = [(683 + 92 * c, y) for y in (258, 363, 473) for c in range(5)]
    assert s.cell_prices(SELL_OCR, cells) == {0: 100, 1: 50, 2: 131, 3: 99, 4: 93, 5: 100, 6: 97, 7: 91, 8: 101, 9: 96}


def test_buy_plan_takes_the_queue_order_not_the_tier_or_the_price_and_buys_from_the_back():
    # #298: (grid index, place in the buy queue, price) of the offers on show the list wants.
    offers = [(0, 3, 140), (1, 1, 200), (3, 0, 250), (4, 2, 180)]
    # Queue order 3, 1, 4, 0 though 0 is the cheapest; 140 no longer fits after them. Bought last cell first,
    # so the offers before it keep their places (a bought one moves to the end of the grid).
    assert s.buy_plan(offers, 700, 0, sold=False) == ([4, 3, 1], None)
    assert s.buy_plan(offers, 700, 100, sold=False) == ([3, 1, 0], None)  # the reserve: 180 no longer fits, the cheaper 140 does
    assert s.buy_plan(offers, 600, 100, sold=False) == ([3, 1], None)
    assert s.buy_plan([(2, 1, 150), (5, 1, 140)], 200, 0, sold=False) == ([5], None)  # one gift twice on show: the cheaper


def test_buy_plan_sells_first_when_the_first_in_the_queue_is_too_dear():
    offers = [(0, 4, 140), (2, 0, 250)]
    assert s.buy_plan(offers, 200, 0, sold=False) == ([], 250)  # nothing bought: the next round sells for it
    assert s.buy_plan(offers, 200, 0, sold=True) == ([0], None)  # sold already (or nothing to sell): what fits
    assert s.buy_plan([], 200, 0, sold=False) == ([], None)


def test_an_offer_tagged_not_enough_cost_is_told_by_its_red_not_by_its_ocr():
    # Live 2026-10-18: OCR missed the tag and read Elytra's red 160 as 16, so it was tapped (opened no purchase dialog).
    OFFER = [(624 + 154 * c, y) for y in (265, 418) for c in range(4)]
    short = screen_with("offers_short")
    assert [s.short_cell(short, x, y) for x, y in OFFER] == [False, True, True, True, False, False, False, False]
    for name in ("offers", "offers_super"):  # affordable offers, skills and a Purchased one show no red
        image = screen_with(name)
        assert not any(s.short_cell(image, x, y) for x, y in OFFER), name


def test_a_red_gift_on_an_affordable_offer_is_not_short():
    # The user: a red gift must not read as never affordable. offers_red: Fragment of Hellfire, a red gem (261 red
    # pixels in its frame), sells for an orange 400.
    image = screen_with("offers_red")
    assert not s.short_cell(image, 932, 265)
    # Worst case: red art over the whole card, up to the Not Enough Cost tag's place; the price stays orange.
    image[265 - 37:265 + 37, 932 - 37:932 + 37] = (0, 0, 200)
    assert not s.short_cell(image, 932, 265)
