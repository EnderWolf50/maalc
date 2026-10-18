import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

import shop as s

# Grid crops of live 1280x720 captures (written by recovery.png: one IDAT, filter 0), and where each sat on screen.
CROPS = Path(__file__).resolve().parent / "shop"
CROP_AT = {
    "fuse_spiderweb": (620, 236),  # live 2026-10-18 (maalc-probe rec/m3/fuse-140): Spiderweb Entangled in Red first
    "fuse": (620, 236),  # tests/screens/ShopFuse.png
    "fuse_recipe": (620, 236),  # tests/screens/ShopFuseRecipe.png (#103): the owned row sits at y 427
    "sell": (620, 200),  # live 2026-10-16 (maalc-probe s29/025_sell): the sell page of ShopFuse.png's gifts
    "offers": (560, 210),  # tests/screens/Shop.png
    "offers_super": (560, 210),  # tests/screens/SuperShop.png
    "offers_red": (560, 210),  # live (maalc-probe s28/013): Fragment of Hellfire, a red gem, 400 orange
    "offers_short": (560, 210),  # live 2026-10-18 (maalc-probe live-all/f/shopd_2590.6): 106 Cost, 3 offers tagged Not Enough Cost
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


def test_to_sell_only_what_fusion_leaves_over():
    # 4 non-main gifts: 3 fuse, 1 may go; the dearest one.
    gifts = [(0, 50), (2, 100), (5, 90), (7, 60)]
    assert s.to_sell(gifts, 200, 120, 0) == [2]
    # 3 non-main gifts all fuse: nothing to sell, so no sale helps.
    assert s.to_sell(gifts[:3], 200, 120, 0) is None
    # Two leftovers, both needed; sold from the back so earlier cells stay put.
    assert s.to_sell([(1, 50), (4, 60)], 200, 100, 0) == [4, 1]
    # Already affordable: nothing to sell.
    assert s.to_sell([(1, 50)], 200, 300, 0) == []
    # The reserve counts too.
    assert s.to_sell([(1, 50)], 200, 200, 60) is None


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


def test_dialog_price_from_the_cost_preview():
    assert s.dialog_price(2864, "28642612") == 252  # live OCR runs the two numbers together
    assert s.dialog_price(540, "540 ▶ 384") == 156
    assert s.dialog_price(2618, "2218") is None  # not the Cost we read
    assert s.dialog_price(2618, "2618") is None
    assert s.dialog_price(None, "28642612") is None


@pytest.mark.parametrize("read, kept", [
    ("Spiderweb Entangled in Red", True),
    ("Spiderweb Entangledin Red", True),  # OCR runs words together
    ("SpiderwebEntangled in Rcd", True),
    ("Hellterfly's Dream", False),
    ("", False),
])
def test_protected_gifts_are_matched_by_name(read, kept):
    assert s.protected(read, ["Spiderweb Entangled in Red", "Sunshower"]) == kept


@pytest.mark.parametrize("read, cost", [
    ("3302", 3302),
    ("33O2", 3302),  # OCR reads digits as look-alike letters (#82)
    ("l5S", 155),
    ("2B4", 284),
    ("", None),
    ("Cost", None),  # no digit at all: not a number
])
def test_cost_value_reads_look_alike_letters_as_digits(read, cost):
    assert s.cost_value(read) == cost


@pytest.mark.parametrize("keyword, gift, role", [
    ("Bleed", None, "material"),  # another keyword: fuse or sell it
    ("Burn", None, "keep"),  # the main keyword
    ("Keywordless", None, "keep"),  # no badge: every keywordless gift is kept (#103)
    ("Bleed", "Hellterfly's Dream", "keep"),  # its icon is one of the team's observed gifts
    (None, None, "unknown"),  # badge cut off or unread: the tooltip decides
    (None, "Spiderweb Entangled in Red", "keep"),
])
def test_gift_role_from_the_cells_badge_and_icon(keyword, gift, role):
    assert s.gift_role(keyword, gift, "Burn") == role


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


def test_buy_plan_takes_high_tier_first_and_buys_from_the_back():
    # #76: (grid index, tier, price) of the main-keyword offers on show.
    offers = [(0, 1, 140), (1, 2, 200), (3, 2, 180), (4, 3, 250)]
    # Tier 3, then the cheaper tier 2, then the dearer one; tier 1 no longer fits. Bought last cell first,
    # so the offers before it keep their places (a bought one moves to the end of the grid).
    assert s.buy_plan(offers, 700, 0, sold=False) == ([4, 3, 1], None)
    assert s.buy_plan(offers, 700, 100, sold=False) == ([4, 3, 0], None)  # the reserve: 200 no longer fits, 140 does
    assert s.buy_plan([(2, None, 150), (5, 1, 160)], 200, 0, sold=False) == ([5], None)  # an unread tier comes last


def test_buy_plan_sells_first_when_the_top_tier_is_too_dear():
    offers = [(0, 1, 140), (2, 3, 250)]
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
