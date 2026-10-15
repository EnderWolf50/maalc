from pathlib import Path

import yaml

import rewards as r

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"

ORDER = ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"]
RISKS = {"Defense Level Up": 1, "Growth I": 3, "Offense Level Up I": 2, "Offense Level Up II": 4}


def test_pick_choice_prefers_a_main_keyword_gift():
    options = [
        "Choose the laughing skull.",
        "Choose the angry skull. Wrath & Envy Advantage check. Pass to gain a Rupture E.G.O Gift.",
        "Choose the deranged skull. Lust & Gloom check. Pass to gain a Burn E.G.O Gift.",
    ]
    assert r.pick_choice(options, "Burn") == 2
    assert r.pick_choice(options, "Bleed") == 1  # any gift beats none
    assert r.pick_choice(options[:1] + ["Leave."], "Burn") == 0
    # OCR may drop the dots of E.G.O.
    assert r.pick_choice(["Leave.", "Pass to gain a Keywordless EGO Gift."], "Burn") == 1
    # Live: the last option's hint cut off at the panel edge.
    cut = ["I command death.", "I command life.", "Don't command anything. Gloom & Pride Advantage check. Pass to gain a Sinking"]
    assert r.pick_choice(cut, "Burn") == 2
    assert r.pick_choice(["Gain 100 Cost.", "Leave."], "Burn") == 0


def test_pick_choice_override_wins():
    options = ["Take the gift. Pass to gain a Burn E.G.O Gift.", "Leave it alone."]
    assert r.pick_choice(options, "Burn", "Leave it") == 1
    assert r.pick_choice(options, "Burn", "not on screen") == 0


def test_pick_checker_takes_best_odds_leftmost():
    captions = [("High", 216), ("Very High", 286), ("Very Low", 355), ("Very High", 147), ("Normal", 700)]
    assert r.pick_checker(captions) == 3
    assert r.pick_checker([("Low", 77), ("Very  low", 147), ("???", 216)]) == 0
    # Live OCR: one caption per portrait, spaces dropped, tails misread.
    assert r.pick_checker([("VeryLow", 77), ("Normat", 147), ("VeryHigh", 216), ("High", 286)]) == 2
    assert r.pick_checker([("??", 77)]) is None
    assert r.pick_checker([]) is None


def test_card_type():
    assert r.card_type("Gain a random Tier 1~2 E.G.O Gift") == "Random E.G.O Gift"
    assert r.card_type("E.G.O Resource +6 for 2 of the least-owned Affinities") == "E.G.O Resource"
    assert r.card_type("Gain 100~150 Cost") == "Cost"
    assert r.card_type("Gain 55~83 Cost 33% chance to gain a random Tier 2~3 Bleed E.G.O Gift") == "Cost & Keyword Gift Chance"
    assert r.card_type("Gain additional 8~10 Starlight upon clearing the Mirror Dungeon") == "Starlight"
    assert r.card_type("") is None


def test_pick_card_follows_the_team_order():
    assert r.pick_card(["Random E.G.O Gift", "E.G.O Resource", "Cost"], ORDER) == 0
    assert r.pick_card(["Cost", "E.G.O Resource", "Starlight"], ORDER) == 2
    assert r.pick_card([None, None], ORDER) == 0
    assert r.pick_card(["E.G.O Resource", "Cost"], list(reversed(ORDER))) == 0
    assert r.pick_card(["Cost", "E.G.O Resource", "Starlight"], ORDER, taken={2}) == 0  # Selectable 0/2


def test_gift_kind():
    assert r.gift_kind("When applying Burn Potency", "Burn", False) == "main"
    assert r.gift_kind("inflict 2 Rupture Potency", "Burn", False) == "other"
    assert r.gift_kind("When applying Burn Potency", "Burn", True) == "owned"
    assert r.gift_kind("Burning heart", "Burn", False) == "other"  # whole words only


def test_trial_risk_unknown_is_max():
    assert r.trial_risk("Defense Level Up", RISKS) == 1
    assert r.trial_risk("Offense Level Up II", RISKS) == 4
    assert r.trial_risk("Resilient I", RISKS) == r.MAX_RISK
    assert r.trial_risk("Growth II", RISKS) == r.MAX_RISK  # not Growth I's risk
    assert r.trial_risk("Defense Leve1 Up", RISKS) == 1  # OCR slips still match


def test_rank_gifts_without_trials():
    assert r.rank_gifts([("other", None), ("main", None), ("owned", None), ("main", None)], "high") == [1, 3, 0, 2]


def test_rank_gifts_with_trials():
    # score = gift - weight x risk; high weight 2: main/1 -> 1, other/0 -> 2, main/3 -> -3, other/5 -> -8
    cards = [("main", 1), ("other", 0), ("main", 3), ("other", 5)]
    assert r.rank_gifts(cards, "high") == [1, 0, 2, 3]
    # low weight 0.5: main/1 -> 2.5, other/0 -> 2, main/3 -> 1.5
    assert r.rank_gifts(cards, "low")[:3] == [0, 1, 2]
    # equal scores: the lower risk first (medium: main/1 -> 2, other/0 -> 2)
    assert r.rank_gifts([("main", 1), ("other", 0)], "medium") == [1, 0]


def test_data_files():
    risks = yaml.safe_load((DATA / "trial_risks.yaml").read_text(encoding="utf-8"))
    assert risks and all(isinstance(v, int) and 0 <= v <= r.MAX_RISK for v in risks.values())
    assert yaml.safe_load((DATA / "events.yaml").read_text(encoding="utf-8")) == {}
