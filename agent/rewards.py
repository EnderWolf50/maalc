"""Event, reward card and gift decisions, free of MaaFramework (docs/spec/03-decisions.md sections 10-12).

actions.py reads the pages and taps; everything here is plain data in, plain data out.
"""

import re

from run_start import match_pack

ODDS = ("very low", "low", "normal", "high", "very high")
GIFT_SCORE = {"main": 3, "other": 2, "owned": 0}
RISK_WEIGHT = {"low": 0.5, "medium": 1, "high": 2}
MAX_RISK = 5
KEYWORDS = ("Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless")


def pick_choice(options, keyword, override=None):
    """Index of the event option to take (spec 03 section 10).

    options are each option's OCR text (its line plus the hint under it). An override's option
    text wins when it matches; else a main-keyword E.G.O Gift > any E.G.O Gift > the first option.
    """
    if override:
        for i, o in enumerate(options):
            if _norm(override) in _norm(o):
                return i
    # A third option's hint may be cut off at the panel edge: "... Pass to gain a Sinking".
    gift = [i for i, o in enumerate(options) if re.search(rf"E\.?\s*G\.?\s*O\b.*Gift|\bgain an? ({'|'.join(KEYWORDS)})\b", o, re.I)]
    main = [i for i in gift if re.search(rf"\b{keyword}\b", options[i], re.I)]
    return (main or gift or [0])[0]


def odds_rank(caption):
    """0 (Very Low) to 4 (Very High) for a skill-check caption; None when it reads as none of them."""
    c = re.sub(r"[^a-z]", "", caption.lower())  # OCR drops the space and may misread the tail ("Normat")
    very = c.startswith("very")
    rest = c[4:] if very else c
    level = next((w for w in ("high", "low", "normal") if rest[:2] == w[:2]), None)
    if level is None or (very and level == "normal"):
        return None
    return ODDS.index(f"very {level}" if very else level)


def pick_checker(captions):
    """Index into captions [(text, x)] of the sinner to take the check: best odds, leftmost; None when none read."""
    ranked = [(odds_rank(t), x, i) for i, (t, x) in enumerate(captions) if odds_rank(t) is not None]
    return min(ranked, key=lambda r: (-r[0], r[1]))[2] if ranked else None


def card_type(text):
    """The reward card type its text stands for, or None (spec 03 section 11)."""
    t = text.lower()
    if "starlight" in t:
        return "Starlight"
    if "resource" in t:
        return "E.G.O Resource"
    if "cost" in t:
        return "Cost & Keyword Gift Chance" if "gift" in t or "chance" in t else "Cost"
    if "gift" in t:
        return "Random E.G.O Gift"
    return None


def pick_card(types, order, taken=()):
    """Index of the reward card to take, skipping taken: the first type in the team's order, else the leftmost."""
    left = [i for i in range(len(types)) if i not in taken]
    return min(left, key=lambda i: (order.index(types[i]) if types[i] in order else len(order), i))


def gift_kind(text, keyword, owned):
    """"main", "other" or "owned" for a gift card's OCR text."""
    if owned:
        return "owned"
    # ponytail: keyword = its word anywhere in the card text; a Bleed gift that says "Slash Skill"
    # counts for a Slash team too. Read the keyword icon if that picks wrong gifts.
    return "main" if re.search(rf"\b{keyword}\b", text, re.I) else "other"


def trial_risk(text, risks):
    """Risk of the trial named in text (one OCR line); MAX_RISK when it is not in the table."""
    exact = {_norm(n): n for n in risks}  # "Growth I" and "Growth II" are too alike for the fuzzy margin
    name = exact.get(_norm(text)) or match_pack(text, list(risks))
    if name and _numeral(name) != _numeral(text):
        name = None  # fuzzy "Growth II" -> "Growth I" would understate the risk
    return risks[name] if name else MAX_RISK


def _numeral(s):
    m = re.search(r"\s([IVX]+)\s*$", s)
    return m[1] if m else ""


def rank_gifts(cards, weight):
    """Card indexes best first (spec 03 section 12).

    cards are (kind, trial risk or None); score = gift score - weight x risk, ties to the lower
    risk, then the leftmost. Without trials (risk None) it is main > other > owned.
    """
    w = RISK_WEIGHT[weight]

    def key(i):
        kind, risk = cards[i]
        return (-(GIFT_SCORE[kind] - w * (risk or 0)), risk or 0, i)

    return sorted(range(len(cards)), key=key)


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())
