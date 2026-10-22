"""Run-start decisions, free of MaaFramework (docs/spec/03-decisions.md sections 1, 2, 4, 6).

actions.py reads the screen and taps; everything here is plain data in, plain data out.
"""

from difflib import SequenceMatcher

from ocrtext import compact

# Grace base prices, numbered as on the starlight page (spec 04 section 7).
# Live 2026-10-14: base / + / ++ cost 1x / 2x / 3x the base price.
GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)
LEVEL_MULT = {"base": 1, "plus": 2, "plus2": 3}


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


def grace_price(n, level):
    """Starlight grace n (1-10) costs at level."""
    return GRACE_BASE[n - 1] * LEVEL_MULT[level]


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
        price = grace_price(n, level)
        if price > available:
            missed.append((n, level, price))
            if unaffordable == "stop":
                break
            continue
        buys.append((n, level, price))
        available -= price
    return buys, missed


def hard_wanted(floor, run_hard, hard_from_floor):
    """Whether this floor should be HARD: a hard run goes HARD from floor N on (1: all floors).

    hard_from_floor None (the team's switch off): a hard run of that team is one the global difficulty "hard"
    forced (team_difficulty), HARD on every floor (#137).
    """
    return run_hard and floor >= (hard_from_floor or 1)


def team_difficulty(setting, difficulty, hard_from_floor):
    """The run's difficulty once the team is picked (#137).

    A team whose switch to hard is off (hard_from_floor None) plays NORMAL, unless the global setting is "hard"
    outright: then the setting wins. Under "auto" such a team's runs are NORMAL, weekly bonuses left or not.
    """
    return "normal" if hard_from_floor is None and setting != "hard" else difficulty


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
    key = compact(text)
    scores = sorted(((SequenceMatcher(None, key, compact(n)).ratio(), n) for n in set(names)), reverse=True)
    if not scores or scores[0][0] < min_ratio:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    return scores[0][1]


def match_title(text, names, min_ratio=0.8):
    """The pack name a card's OCR title stands for, or None (spec 05 section 2, #89).

    Each name is looked for inside the text, letters and digits only: the window of the text as long as the
    name that is most like it scores r, so a logo fragment or a lost second line costs nothing and an OCR slip
    or two still passes min_ratio. Of the names that pass, the one covering the most letters (r x its length)
    wins by a letter at least, so "Sea" inside "Mountain of Corpses, Sea of Blood" loses to the whole title;
    a tie ("Line" for Line 1-3) is None.
    """
    best = title_candidates(text, names, min_ratio)
    return best[0] if len(best) == 1 else None


def title_candidates(text, names, min_ratio=0.8):
    """The names tied for the best match of text (match_title), best first; [] when none passes."""
    key = compact(text)
    found = []
    for name in set(names):
        n = compact(name)
        if not key or not n:
            continue
        r = max(SequenceMatcher(None, key[i:i + len(n)], n).ratio() for i in range(max(1, len(key) - len(n) + 1)))
        if r >= min_ratio:
            found.append((r * len(n), name))
    found.sort(reverse=True)
    return [name for score, name in found if found[0][0] - score < 1]


def match_card(lines, names):
    """(pack name or None, title text) for a card's OCR lines, top to bottom.

    Logo fragments read above the title are dropped by trying the lines from each start. Failing that, the lines are
    tried bottom up: live, a tilted card's two title boxes sorted "World", "Lake" (#240).
    """
    for order in (lines, lines[::-1]):
        for i in range(len(order)):
            title = " ".join(order[i:])
            name = match_title(title, names)
            if name:
                return name, title
    return None, " ".join(lines)


def rank_packs(cards, names, plan):
    """(title, weight) per card; a card that matches no weighed pack takes the plan's unlisted weight.

    A title alike to several packs that share one weight takes it: live, "Line 1" read as "Line", and every
    Line pack is avoided (#89). A matched card's title is the pack's name.
    """
    weights, unlisted = plan["weights"], plan["unlisted"]
    out = []
    for lines in cards:
        name, title = match_card(lines, names)
        if name:
            out.append((name, weights.get(name, unlisted)))
            continue
        shared = {weights.get(n, unlisted) for n in title_candidates(title, names)}
        out.append((title, shared.pop() if len(shared) == 1 else unlisted))
    return out


def event_slots(floor, titles, event_packs, packs):
    """Per card, whether the plan's event_packs mode applies to it (spec 03 section 6, #240).

    Only floor 5's leftmost card: while an event runs, its pack sits there (the user, 2026-10-22). It counts when it is
    an event story pack (event_packs) or a pack the data file lacks, as a running event's new pack is; an ended
    event's pack, or one anywhere else, is one pack among others. packs: the data file's; a title alike to one is not
    new. Leftmost is the leftmost card whose title was read, and a title misread past matching counts as new.
    """
    slots = [False] * len(titles)
    if floor == 5 and titles:
        first = titles[0]
        slots[0] = first in event_packs or (first not in packs and not title_candidates(first, packs))
    return slots


def pick_pack(weights, slots, plan):
    """(index of the card to take, whether it meets the plan's threshold) (spec 03 section 6, #240).

    The highest weight, leftmost among equals. slots[i] says the plan's event_packs mode applies to card i
    (event_slots): "prefer" takes it, threshold or not; "avoid" leaves it out while another card shows.
    """
    mode = plan["event_packs"]
    pool = range(len(weights))
    if mode != "weight" and any(slots) and not all(slots):
        pool = [i for i in pool if slots[i] == (mode == "prefer")]
    i = max(pool, key=lambda i: (weights[i], -i))
    return i, (mode == "prefer" and slots[i]) or weights[i] >= plan["threshold"]


def refresh_wanted(meets, setting, used):
    """Whether to use a free refresh: only when the best card is below the threshold, then per theme_pack_refresh.

    "none" never, "once" for the first refresh on the floor, "all" until the caller sees a refresh change nothing.
    """
    return not meets and (setting == "all" or (setting == "once" and used == 0))


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
