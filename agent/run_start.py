"""Run-start decisions, free of MaaFramework (docs/spec/03-decisions.md sections 1, 2, 4, 6).

actions.py reads the screen and taps; everything here is plain data in, plain data out.
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache

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


RERUN = " BokGak"  # a re-run copy's name: its original's and this, the small line its card shows under the title


def rerun_copy(name, text, names):
    """name's re-run copy when text holds the BokGak line and names has the copy, else name."""
    copy = f"{name}{RERUN}"
    return copy if copy in names and compact(RERUN) in compact(text) else name


def title_candidates(text, names, min_ratio=0.8):
    """The names tied for the best match of text (match_title), best first; [] when none passes.

    A re-run copy's name is left out: it holds its original's, which a plain title would match as well as the copy's
    (rerun_copy tells them apart by the BokGak line).
    """
    key = compact(text)
    found = []
    for name in set(names):
        n = compact(name)
        if not key or not n or name.endswith(RERUN):
            continue
        r = max(SequenceMatcher(None, key[i:i + len(n)], n).ratio() for i in range(max(1, len(key) - len(n) + 1)))
        if r >= min_ratio:
            found.append((r * len(n), name))
    found.sort(reverse=True)
    return [name for score, name in found if found[0][0] - score < 1]


KEYWORD_MIN = 4  # letters; a shorter fragment turns up in OCR noise
KEYWORD_RATIO = 0.85  # a keyword of 4 to 6 letters must read exactly; from 7 letters on, one slip passes


@lru_cache(maxsize=8)
def _keywords(names):
    compacts = {n: compact(n) for n in names if not n.endswith(RERUN)}  # a copy holds its original's every stretch
    out = {}
    for name in compacts:
        c = compacts[name]
        words = sorted((compact(w) for w in re.split(r"[\W_]+", name)), key=len)
        stretches = [c[i:i + n] for n in range(KEYWORD_MIN, len(c) + 1) for i in range(len(c) - n + 1)]
        # a word first (OCR reads a word whole or not at all), else the shortest stretch of the name
        for found in ([w for w in words if len(w) >= KEYWORD_MIN], stretches):
            unique = [k for k in found if not any(k in other for n, other in compacts.items() if n != name)]
            if unique:
                out[name] = unique[0]
                break
    return out


def pack_keywords(names):
    """{pack name: its keyword} (#274): the shortest word of the name, or else the shortest stretch of it, of at least
    KEYWORD_MIN letters and digits that no other name contains. A name whose every stretch another contains has none,
    nor has a re-run copy (RERUN)."""
    return _keywords(tuple(sorted(set(names))))


def match_keyword(text, names):
    """The one pack whose keyword shows in text (letters and digits only), else None.

    For a card whose whole title did not match (match_title): a half-read title still holds the word that sets its pack
    apart. A keyword read exactly wins; two of them in one text is None. With none exact, a slip is allowed in a long
    one (KEYWORD_RATIO), and the keyword covering the most letters wins, "crushers" over "crushed".
    """
    keywords = pack_keywords(names)
    key = compact(text)
    exact = [n for n, k in keywords.items() if k in key]
    if exact:
        return exact[0] if len(exact) == 1 else None
    by_keyword = {k: n for n, k in keywords.items()}
    found = title_candidates(text, list(by_keyword), KEYWORD_RATIO)
    return by_keyword[found[0]] if len(found) == 1 else None


CARD_GAP = 15  # px between two OCR boxes of one card's text; adjacent cards' texts sit 25+ px apart (pitch 211)
CARD_SPAN = 105  # px: texts of two cards are at least this far apart by centre (cards 182 px wide on a 211 px pitch)
# What the card shows besides its title, as OCR reads it (compared letters and digits only): the logo, the CAUTION stamp,
# the "CLEAR BONUS" caption, the level badge. Read off 112 captures (#274): LIMBUS 83 times (LImBUS too) and LV twice, the
# others 0 (the stamp and caption sit behind or below the title strip; the logo's second word reads as noise like WOPIS).
NOT_TITLE = {compact(t) for t in ("LIMBUS", "COMPANY", "LIMBUS COMPANY", "CAUTION", "CLEAR BONUS", "LV")}


def pack_cards(results):
    """The theme pack page's OCR results (text, (x, y, w, h)) as cards left to right: (x centre, [lines top to bottom]).

    Boxes that overlap or sit within CARD_GAP px sideways are one card: live, a tilted "Timekilling Time" came as two
    boxes 80 px apart by centre and made two cards (#267). Only a box that reads exactly a word of NOT_TITLE (or nothing)
    is dropped; every other read, capitals too, stays a line of its card for the name, keyword and cover paths to
    judge: a title art read in capitals ("LINE 1 MADNESS", "THE DUSK OF AMBER") is still a card (#266, #274). Without
    the lowercase rule, noise boxes (a lone "M", the badge's "IV") would be cards of their own: texts nearer than
    CARD_SPAN by centre are one card. A card with no box read at all is lost.
    """
    boxes = sorted((x, x + w, y, t) for t, (x, y, w, h) in results if compact(t) and compact(t) not in NOT_TITLE)
    groups = []
    for box in boxes:
        if groups and box[0] - groups[-1][1] < CARD_GAP:
            groups[-1][1] = max(groups[-1][1], box[1])
            groups[-1][2].append(box)
        else:
            groups.append([box[0], box[1], [box]])
    cards = []
    for left, right, group in groups:
        if cards and (left + right) / 2 - (cards[-1][0] + cards[-1][1]) / 2 < CARD_SPAN:
            cards[-1] = [cards[-1][0], max(cards[-1][1], right), cards[-1][2] + group]
        else:
            cards.append([left, right, group])
    return [((left + right) // 2, [t for _, t in sorted((y, t) for _, _, y, t in group)]) for left, right, group in cards]


def match_card(lines, names):
    """(pack name or None, title text) for a card's OCR lines, top to bottom.

    Logo fragments read above the title are dropped by trying the lines from each start. The lines are also tried
    bottom up: live, a tilted card's two title boxes sorted "World", "Lake" (#240). Of the two reads the longer name
    wins, as it covers more of the card: "Sea of Blood" over "Mountain of Corpses," finds S.E.A. top-down. A card
    showing the BokGak line is its pack's re-run copy (rerun_copy).
    """
    found = []
    for order in (lines, lines[::-1]):
        for i in range(len(order)):
            title = " ".join(order[i:])
            name = match_title(title, names)
            if name:
                found.append((name, title))
                break
    if not found:
        return None, " ".join(lines)
    name, title = max(found, key=lambda f: len(compact(f[0])))  # max keeps the top-down read on a tie
    return rerun_copy(name, " ".join(lines), names), title


def rank_packs(cards, names, plan, title_art=None, cover=None):
    """(title, weight, how) per card; a card that matches no weighed pack takes the plan's unlisted weight.

    A card is named by the first of these paths that reads it, and how says which: "name" (its whole title), "title_art"
    (what OCR reads off title art that does not spell its pack's name -> that pack, the data file's title_art, #246),
    "keyword" (the word that sets its pack apart, pack_keywords #274), "cover N" (cover(i, allowed) is the pack its
    art looks like and the correlation, or None; allowed: the packs the title is alike to, None when to none, #274).
    A title alike to several packs that share one weight takes it ("shared"): live, "Line 1" read as "Line", and every
    Line pack is avoided (#89); else "unread". A matched card's title is the pack's name; a card showing the BokGak
    line is the re-run copy of the pack a path names (rerun_copy).
    """
    title_art = title_art or {}
    weights, unlisted = plan["weights"], plan["unlisted"]
    names = list(names) + list(title_art)
    out = []
    for i, lines in enumerate(cards):
        name, title = match_card(lines, names)
        how = "title_art" if name in title_art else "name"
        if not name:
            name, how = match_keyword(title, names), "keyword"
        candidates = [] if name else title_candidates(title, names)
        if not name and cover:
            found = cover(i, {title_art.get(n, n) for n in candidates} or None)
            name, how = found and found[0], found and f"cover {found[1]:.2f}"
        if name:
            name = rerun_copy(title_art.get(name, name), " ".join(lines), names)
            out.append((name, weights.get(name, unlisted), how))
            continue
        shared = {weights.get(title_art.get(n, n), unlisted) for n in candidates}
        out.append((title, *((shared.pop(), "shared") if len(shared) == 1 else (unlisted, "unread"))))
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
