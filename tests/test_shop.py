import pytest

import shop as s


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
