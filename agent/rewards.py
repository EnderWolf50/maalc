"""Event, reward card and gift decisions, free of MaaFramework (docs/spec/03-decisions.md sections 10-12).

actions.py reads the pages and taps; everything here is plain data in, plain data out.
"""

import re
from difflib import SequenceMatcher

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
    text wins when it matches. With the event's table options (match_event) each option is ranked by its
    own entry, found by its texts: direct gain of the main keyword > direct gain > ??? / random > check
    pass > follow-up page > win battle > the rest, ties to the main keyword, then the screen order; an
    option no entry matches is ranked by its hint. Without them: a main-keyword E.G.O Gift > any E.G.O
    Gift > the first option.
    """
    open_ = [i for i in range(len(options)) if i not in closed]
    if override:
        for i in open_:
            if _norm(override) in _norm(options[i]):
                return i
    if event:
        return min(open_, key=lambda i: (*_rank(options[i], _entry(options[i], event), keyword), i), default=None)
    gift = [i for i in open_ if _gift(options[i])]
    main = [i for i in gift if re.search(rf"\b{keyword}\b", options[i], re.I)]
    return (main or gift or open_ or [None])[0]


KIND_TIER = {"random": 2, "check": 3, "followup": 4, "battle": 5}  # direct 0-1, the rest 6


def _gift(text):
    # A third option's hint may be cut off at the panel edge: "... Pass to gain a Sinking".
    return re.search(rf"E\.?\s*G\.?\s*O\b.*Gift|\bgain an? ({'|'.join(KEYWORDS)})\b", text, re.I)


def _rank(text, entry, keyword):
    """(tier, 0 when the main keyword is in it) of an option: by its table entry, else by its OCR'd hint."""
    if entry:
        main = any(k == keyword for k, _ in entry.get("gifts", ()))
        if entry["kind"] == "direct":
            return (0 if any(k == keyword and how == "direct" for k, how in entry["gifts"]) else 1), not main
        tier = KIND_TIER.get(entry["kind"], 6)
        return tier, tier == 6 or not main  # the rest gain nothing: a gift when a check fails is no tie-break
    main = bool(re.search(rf"\b{keyword}\b", text, re.I))
    if "???" in text:
        return 2, not main
    if not _gift(text):
        return 6, not main
    for tier, word in ((5, r"\bwin the battle"), (3, r"\bcheck\b"), (4, r"\bdepending on\b")):
        if re.search(word, text, re.I):
            return tier, not main
    return (0 if main else 1), not main


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


def choice_cards(image):
    """Option frames top to bottom in the list's view as (top, bottom) y, None for an edge cut off (1280x720 BGR).

    Read down the frames' left edge at x 700: a top edge is a double line (~9 px), a bottom edge a single one
    (~3 px). EventChoicesUsed.png: [(170, 302), (320, 452), (469, None)], the third cut at the bottom.
    """
    y0, y1 = CHOICE_LIST_Y
    bright = image[y0:y1, 700].astype(int).sum(1) > 200
    edges = []  # [first, last] bright rows, gaps up to 6 px joined
    for y in (y0 + i for i in range(len(bright)) if bright[i]):
        if edges and y - edges[-1][1] <= 6:
            edges[-1][1] = y
        else:
            edges.append([y, y])
    cards = []
    for first, last in edges:
        if last - first >= 6:
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
    c = re.sub(r"[^a-z]", "", caption.lower())  # OCR drops the space and may misread the tail ("Normat")
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
    word, key = _norm(max(name.split(), key=len)), _norm(text)
    return any(SequenceMatcher(None, key[i:i + len(word)], word).ratio() >= min_ratio
               for i in range(max(1, len(key) - len(word) + 1)))


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


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def _key(s):
    """Letters and digits of s, lower case, as tools/event_table.py keys the table."""
    return re.sub(r"[^a-z0-9]", "", s.lower())
