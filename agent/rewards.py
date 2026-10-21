"""Event, reward card and gift decisions, free of MaaFramework (docs/spec/03-decisions.md sections 10-12).

actions.py reads the pages and taps; everything here is plain data in, plain data out.
"""

import re
from difflib import SequenceMatcher

from ocrtext import compact, has
from run_start import match_pack

ODDS = ("very low", "low", "normal", "high", "very high")
GIFT_SCORE = {"main": 3, "other": 2, "owned": 0}
RISK_WEIGHT = {"low": 0.5, "medium": 1, "high": 2}
MAX_RISK = 5
KEYWORDS = ("Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless")


def pick_choice(options, keyword, override=None, closed=(), event=None):
    """Index of the event option to take (spec 03 section 10), or None when every option is closed.

    options are each option's OCR text (its line plus the hint under it); closed are the indices that
    cannot be taken (greyed out, or a tap left the page as it was). Among the rest an override's option
    text wins when it matches. Then AALC's order (#233): ??? / random > direct gain > advantage check
    (pass to gain) > "gain ... depending on ..." > the rest; inside a tier an option with a main-keyword gift
    first, then the screen order. With the event's table options (match_event) each option is ranked by its
    own entry, found by its texts; an option no entry matches (or no table at all) is ranked by its hint.
    """
    open_ = [i for i in range(len(options)) if i not in closed]
    if override:
        for i in open_:
            if compact(override) in compact(options[i]):
                return i
    return min(open_, key=lambda i: (*_rank(options[i], _entry(options[i], event) if event else None, keyword), i), default=None)


def _gift(text):
    # A third option's hint may be cut off at the panel edge: "... Pass to gain a Sinking".
    return re.search(rf"E\.?\s*G\.?\s*O\b.*Gift|\bgain an? ({'|'.join(KEYWORDS)})\b", text, re.I)


def _rank(text, entry, keyword):
    """(tier, 0 when the main keyword is in it) of an option: by its table entry, else by its OCR'd hint.

    Tiers: 0 ???, 1 direct gain, 2 check (pass to gain), 3 "gain ... depending on", 4 the rest. A battle and a
    gift only when a check fails have no AALC tier: the rest, where the main keyword is no tie-break.
    """
    if entry:
        kind = entry["kind"]
        main = any(k == keyword for k, _ in entry.get("gifts", ()))
        if kind in ("random", "direct"):
            return (0 if kind == "random" else 1), not main
        if kind in ("check", "followup"):  # AALC matches "Advantage check" before "Gain ... depending on"
            return (2 if re.search(r"\bcheck\b", entry["hint"], re.I) else 3), not main
        return 4, True
    main = bool(re.search(rf"\b{keyword}\b", text, re.I))
    if "???" in text:
        return 0, not main
    if not _gift(text) or re.search(r"\bwin the battle", text, re.I):
        return 4, True
    if re.search(r"\bcheck\b", text, re.I):
        return 2, not main
    return (3 if re.search(r"\bdepending on\b", text, re.I) else 1), not main


def _entry(text, event, min_ratio=0.8):
    """The table option an on-screen option is: its OCR text (option line + hint) against each entry's text + hint.

    The OCR may stop short (a hint cut off at the panel edge): it is held against as much of the entry,
    but must cover the option line. Ties go to the entry closest in length; a tie between entries of
    different outcomes is None, as is no entry close enough: the hint ranks that option then.
    """
    s = _key(text)
    scored = []
    for o in event:
        target = _key(o["text"] + o["hint"])
        if len(s) >= len(_key(o["text"])) and s:
            scored.append((SequenceMatcher(None, s, target[:len(s)]).ratio(), -abs(len(target) - len(s)), o))
    scored.sort(key=lambda t: t[:2], reverse=True)
    if not scored or scored[0][0] < min_ratio:
        return None
    best = scored[0]
    if any(t[:2] == best[:2] and _outcome(t[2]) != _outcome(best[2]) for t in scored[1:]):
        return None
    return best[2]


def _outcome(o):
    return o["kind"], sorted(map(tuple, o.get("gifts", ())))


def match_event(story, events, min_ratio=0.85):
    """The table options of the event whose story ends as the OCR'd story box does, or None (spec 03 section 10).

    events are data/event_table.json's: key = the story's last letters and digits (the box shows a long story's
    end). The longest key that matches wins; pages with the same key (several only say "What will you do?")
    are pooled, each on-screen option finding its own entry by its texts.
    """
    s = _key(story)
    hits = [e for e in events if s and SequenceMatcher(None, e["key"], s[-len(e["key"]):]).ratio() >= min_ratio]
    longest = max((len(e["key"]) for e in hits), default=0)
    return [o for e in hits if len(e["key"]) == longest for o in e["options"]] or None


def choice_open(image, y):
    """Whether the event option whose first line is at y (1280x720 BGR) can be taken: its frame is red-brown.

    Live 2026-10-17 (#34): in a boss's rounds of questions an answer taken in an earlier round turns grey
    (red - blue ~0) and a tap on it does nothing; open options read red - blue ~20 left of their text.
    """
    b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)
    return bool(r - b > 10)


CHOICE_LIST_Y = (165, 512)  # the option list's view; options past it are cut off
CARD_GAP = 50  # px between two edges at most for a card's bottom and the next card's top: 17-21 apart (9 under a lit card), a card's own 100-121


def choice_cards(image):
    """Option frames top to bottom in the list's view as (top, bottom) y, None for an edge cut off (1280x720 BGR).

    Read down the frames' left edge at x 700. Two edges under CARD_GAP apart are a card's bottom and the next
    card's top; an edge alone in the view is a top when a double line (~9 px), a bottom when a single one (~3 px).
    The gap goes before the thickness: the card a drag lifts over glows orange, its bottom edge 12-13 px (#196).
    EventChoicesUsed.png: [(170, 302), (320, 452), (469, None)], the third cut at the bottom.
    """
    y0, y1 = CHOICE_LIST_Y
    bright = image[y0:y1, 700].astype(int).sum(1) > 200
    edges = []  # [first, last] bright rows, gaps up to 6 px joined
    for y in (y0 + i for i in range(len(bright)) if bright[i]):
        if edges and y - edges[-1][1] <= 6:
            edges[-1][1] = y
        else:
            edges.append([y, y])

    def is_top(k):
        first, last = edges[k]
        if k and first - edges[k - 1][1] < CARD_GAP:
            return True
        if k + 1 < len(edges):
            return edges[k + 1][0] - last >= CARD_GAP
        if k:
            return False  # the last edge, a card's height below another: that card's bottom
        return last - first >= 6  # alone in the view: a double line is a top

    cards = []
    for k, (first, last) in enumerate(edges):
        if is_top(k):
            cards.append((first, None))
        elif cards and cards[-1][1] is None and cards[-1][0] is not None:
            cards[-1] = (cards[-1][0], last + 1)
        else:
            cards.append((None, last + 1))
    return cards


def choice_scrollbar(image):
    """Whether the option list shows its scrollbar (a brown track right of the options): more options than fit."""
    b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)
    return bool(r > 40 and r - b > 20)


def odds_rank(caption):
    """0 (Very Low) to 4 (Very High) for a skill-check caption; None when it reads as none of them."""
    c = re.sub(r"[^a-z]", "", compact(caption))  # OCR drops the space and may misread the tail ("Normat")
    very = c.startswith("very")
    rest = c[4:] if very else c
    level = next((w for w in ("high", "low", "normal") if rest[:2] == w[:2]), None)
    if level is None or (very and level == "normal"):
        return None
    return ODDS.index(f"very {level}" if very else level)


def pick_checker(captions, skip=()):
    """Index into captions [(text, x)] of the sinner to take the check: best odds, leftmost; None when none read.

    skip: indices a tap did nothing on.
    """
    ranked = [(odds_rank(t), x, i) for i, (t, x) in enumerate(captions) if odds_rank(t) is not None and i not in skip]
    return min(ranked, key=lambda r: (-r[0], r[1]))[2] if ranked else None


def card_type(text):
    """The reward card type its text stands for, or None (spec 03 section 11)."""
    if has(text, "starlight"):
        return "Starlight"
    if has(text, "resource"):
        return "E.G.O Resource"
    if has(text, "cost"):
        return "Cost & Keyword Gift Chance" if has(text, "gift", "chance") else "Cost"
    if has(text, "gift"):
        return "Random E.G.O Gift"
    return None


def pick_card(types, order, taken=()):
    """Index of the reward card to take, skipping taken: the first type in the team's order, else the leftmost."""
    left = [i for i in range(len(types)) if i not in taken]
    return min(left, key=lambda i: (order.index(types[i]) if types[i] in order else len(order), i))


def gift_kind(text, keyword, owned, avoid=()):
    """"main", "other", "owned" or "avoid" for a gift card's OCR text; avoid: gift names the team takes last (#90)."""
    if any(names_gift(text, name) for name in avoid):
        return "avoid"
    if owned:
        return "owned"
    # ponytail: keyword = its word anywhere in the card text; a Bleed gift that says "Slash Skill"
    # counts for a Slash team too. Read the keyword icon if that picks wrong gifts.
    return "main" if re.search(rf"\b{keyword}\b", text, re.I) else "other"


def names_gift(text, name, min_ratio=0.8):
    """Whether OCR text names the gift: the name's longest word shows in it, an OCR slip or two allowed."""
    word, key = compact(max(name.split(), key=len)), compact(text)
    return any(SequenceMatcher(None, key[i:i + len(word)], word).ratio() >= min_ratio
               for i in range(max(1, len(key) - len(word) + 1)))


def trial_risk(text, risks):
    """Risk of the trial named in text (one OCR line); MAX_RISK when it is not in the table."""
    exact = {compact(n): n for n in risks}  # "Growth I" and "Growth II" are too alike for the fuzzy margin
    name = exact.get(compact(text)) or match_pack(text, list(risks))
    if name and _numeral(name) != _numeral(text):
        name = None  # fuzzy "Growth II" -> "Growth I" would understate the risk
    return risks[name] if name else MAX_RISK


def _numeral(s):
    m = re.search(r"\s([IVX]+)\s*$", s)
    return m[1] if m else ""


def rank_gifts(cards, weight):
    """Card indexes best first (spec 03 section 12).

    cards are (kind, trial risk or None); score = gift score - weight x risk, ties to the lower
    risk, then the leftmost. Without trials (risk None) it is main > other > owned. An avoided gift
    comes after every other card: taken only to fill the count, rather than a random trial (#90).
    """
    w = RISK_WEIGHT[weight]

    def key(i):
        kind, risk = cards[i]
        return (kind == "avoid", -(GIFT_SCORE.get(kind, 0) - w * (risk or 0)), risk or 0, i)

    return sorted(range(len(cards)), key=key)


def pick_gifts(ranked, read, tap):
    """Tap gift cards best first until Select n/m is full (spec 03 section 12).

    read() gives (n, m) off the screen or None; tap(i) taps card i. A lone card shows no count.
    With several cards and no count read, it is read again, then cards are tapped in order until
    it reads, every card when it never does (#81).
    """
    count = read()
    if count is None and len(ranked) > 1:
        count = read()
    for i in ranked:
        if count and count[0] >= count[1]:
            break
        tap(i)
        now = read()
        if count and now and now[0] < count[0]:  # it was picked already: pick it again, go on to the next
            tap(i)
            now = read()
        count = now or count


def _key(s):
    """Letters and digits of s, lower case, as tools/event_table.py keys the table."""
    return re.sub(r"[^a-z0-9]", "", s.lower())
