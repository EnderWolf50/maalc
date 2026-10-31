"""Event, reward card and gift decisions, free of MaaFramework (docs/spec/03-decisions.md sections 10-12).

actions.py reads the pages and taps; everything here is plain data in, plain data out.
"""

import re
from difflib import SequenceMatcher

from ocrtext import compact, has, normalize
from run_start import match_pack

ODDS = ("very low", "low", "normal", "high", "very high")
GIFT_SCORE = {"main": 3, "other": 2, "owned": 0}
TIER_STEP = 0.5  # a main or other gift's score per tier above I (#381)
RISK_WEIGHT = {"low": 0.5, "medium": 1, "high": 2}
UNREAD_LEVELS = 2  # an Enemy Level Up badge that does not read counts as +2, the most seen live (#381)
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
    gift only when a check fails have no AALC tier: the rest, where the main keyword is no tie-break. So is a
    random gain whose hint states its chance ("Select for a 50% chance to gain"): it is not AALC's ??? template.
    """
    if entry:
        kind = entry["kind"]
        main = any(k == keyword for k, _ in entry.get("gifts", ()))
        if kind == "direct" or (kind == "random" and "???" in entry["hint"]):
            return (0 if kind == "random" else 1), not main
        if kind in ("check", "followup"):  # AALC matches "Advantage check" before "Gain ... depending on"
            if re.search(r"\bcheck\b", entry["hint"], re.I):
                return 2, not main
            if re.search(r"\bdepending on\b", entry["hint"], re.I):
                return 3, not main
            return 4, True  # a hint with neither text (901061, 901023, 971088) matches no AALC template
        return 4, True
    main = bool(re.search(rf"\b{keyword}\b", text, re.I))
    if "???" in text:
        return 0, not main
    if not _gift(text) or re.search(r"\bwin the battle|\d%\s*chance", text, re.I):
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


# Effects on the enemy as a trial's line shows them (data/trials.yaml's keys), case folded: "Offense Level+3", "Max HP
# +7.5%", "Damage Taken -5%". Minus Coin Power comes with Plus Coin Power, the same number: coin is one of them.
NUMBER = r"\s*(\d+(?:\.\d+)?)"
EFFECTS = {"offense": r"offense level\s*\+" + NUMBER, "defense": r"defense level\s*\+" + NUMBER,
           "hp": r"(?<!boss )max hp\s*\+" + NUMBER + "%", "boss_hp": r"boss max hp\s*\+" + NUMBER + "%",
           "clash": r"clash power\s*\+" + NUMBER, "final": r"(?<!skill )final power\s*\+" + NUMBER,
           "base": r"base power\s*\+" + NUMBER, "coin": r"plus coin power\s*\+" + NUMBER,
           "taken": r"damage taken\s*[-−–]" + NUMBER + "%", "dealt": r"damage dealt\s*\+" + NUMBER + "%",
           "defskill": r"defense skill final power\s*\+" + NUMBER}


def parse_effects(text):
    """{effect: number} an effect line reads as (data/trials.yaml's keys); an effect without its number is left out."""
    t = normalize(text)
    return {k: float(m[1]) for k, p in EFFECTS.items() if (m := re.search(p, t))}


def trials_of(table, pool):
    """{name: entry} of data/trials.yaml's trials the pick after the floor-`pool` boss draws from; every trial when the
    floor is unknown (None)."""
    return {n: t for n, t in table["trials"].items() if pool is None or t["pool"] == pool}


def read_trial(name, line, trials):
    """(trial, how) a card shows: its name's and its effect line's OCR held against trials, the pool's (spec 03 section 12).

    The effect line goes first ("effects"): a pool's trials differ in what they do, and a numeral slip in the name
    ("Growth I" for Growth II, #381) does not touch it. It names the trial with the same effects whose values agree most
    (Body Up II shows Max HP +10%, its static data 12.5%); none when a value is cut off or two agree as much. Then the
    name ("name"): found exactly, else by match_pack, and dropped when its numeral is not the one read (Keen I is
    neither Keen II nor III). Neither: (None, None).
    """
    read = parse_effects(line)
    alike = sorted(((sum(abs(t["effects"][k] - v) < 1e-6 for k, v in read.items()), n)
                    for n, t in trials.items() if read and set(t["effects"]) == set(read)), reverse=True)
    if alike and alike[0][0] and (len(alike) == 1 or alike[1][0] < alike[0][0]):
        return alike[0][1], "effects"
    exact = {compact(n): n for n in trials}
    found = exact.get(compact(name)) or match_pack(name, list(trials))
    if found and _numeral(found) == _numeral(name):
        return found, "name"
    return None, None


def _numeral(s):
    m = re.search(r"\s([IVX]+)\s*$", s)
    return m[1] if m else ""


def scores(trials, model, coins=0, overrides=None):
    """{name: score in pt} of trials (spec 03 section 12): the table's, and past early_pools each Coin unit beyond the
    run's coin_budget at coin_over instead of coin_in; coins: the units the run's trials took so far. An override
    (settings trial_risk_overrides) replaces the score."""
    left = max(0, model["coin_budget"] - coins)
    out = {}
    for n, t in trials.items():
        coin = t["effects"].get("coin", 0) if t["pool"] > model["early_pools"] else 0
        out[n] = t["score"] + (model["coin_over"] - model["coin_in"]) * max(0, coin - left)
    return out | {n: v for n, v in (overrides or {}).items() if n in out}


def burden(score, levels, model):
    """What a card's trial costs in pt: its score and model["level"] per Enemy Level Up; levels None (unread) counts
    UNREAD_LEVELS."""
    return score + model["level"] * (UNREAD_LEVELS if levels is None else levels)


def gift_score(kind, tier):
    """A gift card's worth: main 3, other 2, owned 0; main and other TIER_STEP more per tier above I (unread: I)."""
    return GIFT_SCORE.get(kind, 0) + (TIER_STEP * (tier - 1) if tier and kind in ("main", "other") else 0)


def rank_gifts(cards, weight):
    """Card indexes best first (spec 03 section 12).

    cards are (kind, tier, burden or None); score = gift_score - weight x burden, ties to the lighter burden, then the
    leftmost. Without trials (burden None) the gift score alone. An avoided gift comes after every other card: taken
    only to fill the count, rather than a random trial (#90).
    """
    w = RISK_WEIGHT[weight]

    def key(i):
        kind, tier, cost = cards[i]
        return (kind == "avoid", -(gift_score(kind, tier) - w * (cost or 0)), cost or 0, i)

    return sorted(range(len(cards)), key=key)


def pick_gifts(ranked, read, tap):
    """Tap gift cards best first until Select n/m is full (spec 03 section 12); the cards tapped, in order.

    read() gives (n, m) off the screen or None; tap(i) taps card i. A lone card shows no count.
    With several cards and no count read, it is read again, then cards are tapped in order until
    it reads, every card when it never does (#81).
    """
    count = read()
    if count is None and len(ranked) > 1:
        count = read()
    taken = []
    for i in ranked:
        if count and count[0] >= count[1]:
            break
        tap(i)
        taken.append(i)
        now = read()
        if count and now and now[0] < count[0]:  # it was picked already: pick it again, go on to the next
            tap(i)
            now = read()
        count = now or count
    return taken


def _key(s):
    """Letters and digits of s, lower case, as tools/event_table.py keys the table."""
    return re.sub(r"[^a-z0-9]", "", s.lower())
