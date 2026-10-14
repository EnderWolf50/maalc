"""Run-start decisions, free of MaaFramework (docs/spec/03-decisions.md sections 1, 2, 4, 6).

actions.py reads the screen and taps; everything here is plain data in, plain data out.
"""

from difflib import SequenceMatcher

# Grace base prices, numbered as on the starlight page (spec 04 section 7).
# Live 2026-10-14: base / + / ++ cost 1x / 2x / 3x the base price.
GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)
LEVEL_MULT = {"base": 1, "plus": 2, "plus2": 3}

PACK_RANK = {"prefer": 0, "neutral": 1, "avoid": 2}


def run_difficulty(setting, weekly_left):
    """"hard" or "normal" for this run; auto runs hard while weekly bonuses remain (spec 03 section 2)."""
    if setting != "auto":
        return setting
    return "hard" if weekly_left > 0 else "normal"


def resolve_plan(settings, team, key):
    """A team's {"plan": id} or {"custom": value} resolved to the value."""
    ref = team[key]
    if "custom" in ref:
        return ref["custom"]
    plans = {"deployment_order": "deployment_order_plans", "starlight": "starlight_plans"}[key]
    plan = next(p for p in settings[plans] if p["id"] == ref["plan"])
    return plan["order"] if key == "deployment_order" else plan


def starlight_purchases(plan, available, unaffordable):
    """Graces to buy as [(grace number 1-10, level, price)] in priority order, and the ones not bought.

    unaffordable "skip" passes over a grace the remaining starlight cannot pay for;
    "stop" buys nothing after it. A grace is never bought at a lower level than planned.
    """
    buys, missed = [], []
    for n in plan["priority"]:
        level = plan["levels"][n - 1]
        if level == "none":
            continue
        price = GRACE_BASE[n - 1] * LEVEL_MULT[level]
        if price > available:
            missed.append((n, level, price))
            if unaffordable == "stop":
                break
            continue
        buys.append((n, level, price))
        available -= price
    return buys, missed


def hard_wanted(floor, run_hard, hard_from_floor):
    """Whether this floor should be HARD: a hard run goes HARD from floor N on, N = 0 means all floors."""
    return run_hard and floor >= hard_from_floor


def difficulty_move(floor, shown_hard, want_hard):
    """None (keep), "hard" or "normal": the switch to make on the theme pack page.

    want_hard None means the run's difficulty is unknown: keep what the game shows.
    Once a floor is HARD the run stays HARD; only floor 1, before any pack is chosen,
    may still go back to NORMAL.
    """
    if want_hard is None or shown_hard == want_hard:
        return None
    if want_hard:
        return "hard"
    return "normal" if floor == 1 else None


def match_pack(text, names, min_ratio=0.9, margin=0.04):
    """The pack name OCR text stands for, or None (spec 05 section 1: >= 0.9 and 0.04 ahead of the runner-up)."""
    key = _norm(text)
    scores = sorted(((SequenceMatcher(None, key, _norm(n)).ratio(), n) for n in set(names)), reverse=True)
    if not scores or scores[0][0] < min_ratio:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    return scores[0][1]


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def match_card(lines, names):
    """(pack name or None, title text) for a card's OCR lines, top to bottom.

    Logo fragments read above the title are dropped by trying the lines from each start.
    """
    for i in range(len(lines)):
        title = " ".join(lines[i:])
        name = match_pack(title, names)
        if name:
            return name, title
    return None, " ".join(lines)


def rank_packs(cards, names, marks):
    """(title, mark) per card; a card that matches no known pack is neutral."""
    out = []
    for lines in cards:
        name, title = match_card(lines, names)
        out.append((name or title, marks.get(name, "neutral") if name else "neutral"))
    return out


def pick_pack(ranks):
    """Index of the card to take: best mark, leftmost among equals."""
    return min(range(len(ranks)), key=lambda i: (PACK_RANK[ranks[i]], i))


def team_list_move(visible, target):
    """Next step on the team picker list.

    visible maps slot number -> y of each fully shown "TEAMS #n" row.
    Returns ("tap", y), "down" (scroll towards higher numbers) or "up".
    """
    if target in visible:
        return ("tap", visible[target])
    if not visible or target > max(visible):
        return "down"
    return "up"
