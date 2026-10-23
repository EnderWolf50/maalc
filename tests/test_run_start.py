import re
from pathlib import Path

import pytest
import yaml

import run_start as rs
from ocrtext import compact

LEVELS = ["plus2", "base", "plus", "base", "none", "none", "none", "none", "none", "base"]
PRIORITY = [3, 1, 10, 4, 2, 5, 6, 7, 8, 9]


@pytest.mark.parametrize(("setting", "weekly", "expected"), [
    ("auto", 3, "hard"), ("auto", 0, "normal"), ("hard", 0, "hard"), ("normal", 3, "normal"),
])
def test_run_difficulty(setting, weekly, expected):
    assert rs.run_difficulty(setting, weekly) == expected


def test_resolve_plan():
    settings = {"starlight_plans": [{"id": "a", "levels": LEVELS}]}
    assert rs.resolve_plan(settings, {"starlight": {"plan": "a"}}, "starlight")["levels"] == LEVELS
    assert rs.resolve_plan(settings, {"starlight": {"custom": {"x": 1}}}, "starlight") == {"x": 1}


def test_starlight_skip_buys_past_an_unaffordable_grace():
    # The live run of 2026-10-14: 120 available, grace 10 (60) no longer fits after 3+ and 1++.
    buys, missed = rs.starlight_purchases({"levels": LEVELS, "priority": PRIORITY}, 120, "skip")
    assert buys == [(3, "plus", 40), (1, "plus2", 30), (4, "base", 20), (2, "base", 10)]
    assert missed == [(10, "base", 60)]


def test_starlight_stop_buys_nothing_after_an_unaffordable_grace():
    buys, missed = rs.starlight_purchases({"levels": LEVELS, "priority": PRIORITY}, 120, "stop")
    assert buys == [(3, "plus", 40), (1, "plus2", 30)]
    assert missed == [(10, "base", 60)]


def test_starlight_never_buys_more_than_available():
    plan = {"levels": ["plus2"] * 10, "priority": list(range(1, 11))}
    for available in range(0, 400, 7):
        buys, _ = rs.starlight_purchases(plan, available, "skip")
        assert sum(p for _, _, p in buys) <= available


@pytest.mark.parametrize(("floor", "run_hard", "from_floor", "expected"), [
    (1, True, 1, True), (5, True, 1, True), (2, True, 3, False), (3, True, 3, True), (1, False, 1, False),
    # The switch off (#137): a hard run here is one the global difficulty "hard" forced (team_difficulty): every floor.
    (1, True, None, True), (5, True, None, True), (1, False, None, False),
])
def test_hard_wanted(floor, run_hard, from_floor, expected):
    assert rs.hard_wanted(floor, run_hard, from_floor) is expected


@pytest.mark.parametrize(("setting", "decided", "from_floor", "expected"), [
    ("auto", "hard", None, "normal"),  # #137: the switch off plays NORMAL under auto, weekly bonuses or not
    ("hard", "hard", None, "hard"),  # the global "hard" wins: HARD on every floor
    ("normal", "normal", None, "normal"),
    ("auto", "hard", 2, "hard"), ("auto", "normal", 2, "normal"),  # the switch on: as decided
])
def test_a_team_with_its_switch_to_hard_off_plays_normal_unless_the_run_says_hard(setting, decided, from_floor, expected):
    assert rs.team_difficulty(setting, decided, from_floor) == expected


@pytest.mark.parametrize(("floor", "shown_hard", "want_hard", "expected"), [
    (1, False, True, "hard"),
    (1, True, False, "normal"),  # floor 1, nothing chosen yet: the game's remembered HARD may go
    (2, True, False, None),  # HARD once chosen is kept
    (3, False, True, "hard"),
    (2, True, True, None),
    (1, True, None, None),  # run difficulty unknown: keep what the game shows
])
def test_difficulty_move(floor, shown_hard, want_hard, expected):
    assert rs.difficulty_move(floor, shown_hard, want_hard) == expected


NAMES = ["To be Crushed", "To be Cleaved", "To be Pierced", "Nagel und Hammer",
         "Walpurgis Night: Hatred and Despair", "Charm, Wander, Doubt"]


@pytest.mark.parametrize(("lines", "expected"), [
    (["bimus", "To be Crushed"], "To be Crushed"),  # logo fragment above the title
    (["Walpurgis g Hatred and 'Despair"], "Walpurgis Night: Hatred and Despair"),
    (["Charm, Wander Doubt"], "Charm, Wander, Doubt"),
    (["Lake World"], None),
])
def test_match_card(lines, expected):
    assert rs.match_card(lines, NAMES)[0] == expected


def test_close_names_need_a_margin():
    assert rs.match_title("To be Cxxxxed", NAMES) is None


SHORT = ["Line 1", "Line 2", "Line 3", "Line 4 - Section #3", "Line 4 - Section #4", "S.E.A.", "Lake World",
         "Mountain of Corpses, Sea of Blood", "Emotional Craving", "Emotional Flood", "Repressed Wrath",
         "Emotional Repression", "Hell's Chicken", "The B.E.", "Timekilling Time"]


@pytest.mark.parametrize(("text", "expected"), [
    # #89: one OCR slip in a short title no longer makes an avoided pack neutral.
    ("Lime 2", "Line 2"), ("Line Z", None), ("Lake Wor1d", "Lake World"), ("Lake Worl", "Lake World"),
    ("Line 4 - Sectlon #3", "Line 4 - Section #3"),
    ("S.E.A", "S.E.A."), ("SEA.", "S.E.A."),
    ("Mountain of Corpses, Sea of Blood", "Mountain of Corpses, Sea of Blood"),  # not S.E.A., found inside it
    ("Mountain of Corpses, Sea", "Mountain of Corpses, Sea of Blood"),  # the title's second line not read
    ("Emotional Cravlng", "Emotional Craving"), ("Emotiona1 Flood", "Emotional Flood"),
    ("Emotional Repressicn", "Emotional Repression"), ("Repressed Wrath", "Repressed Wrath"),
    ("Hell's Chickn", "Hell's Chicken"), ("The B.E", "The B.E."), ("Timekiling Time", "Timekilling Time"),
    ("Line", None),  # Line 1-3 alike: no guess
    ("Emotional", None),
])
def test_a_title_is_found_despite_ocr_slips(text, expected):
    assert rs.match_title(text, SHORT) == expected


@pytest.mark.parametrize(("lines", "expected"), [
    (["World", "Lake"], "Lake World"),  # live logs: a tilted card's two title boxes sorted bottom word first
    (["WONr", "Abyss", "Crawling"], "Crawling Abyss"),  # with a logo fragment
    (["Lake", "World"], "Lake World"),
    (["Sea of Blood", "Mountain of Corpses,"], "Mountain of Corpses, Sea of Blood"),  # not S.E.A., found top-down
    (["Mountain of Corpses,", "Sea of Blood"], "Mountain of Corpses, Sea of Blood"),
    (["Defining", "The Evil"], "The Evil Defining"),  # not The B.E.
])
def test_a_title_read_in_reverse_order_still_matches(lines, expected):
    assert rs.match_card(lines, DATA_NAMES)[0] == expected


@pytest.mark.parametrize(("lines", "expected"), [
    # #246, recordings 2026-10-22: S.E.A.'s card art reads "The Magic Hello Bus"; The Noon of Violet's tops its name
    # with "Walpurgis Night" and OCR often loses the last word.
    (["HellOBus"], "S.E.A."), (["HellBus"], "S.E.A."), (["HelIOBus"], "S.E.A."), (["The Magic SHellBus"], "S.E.A."),
    (["WalpurgisN The Noon of"], "The Noon of Violet"), (["Walpurgis Night", "The Noon of Violet"], "The Noon of Violet"),
    (["Walpurgis", "Hatred and 'Despair"], "Walpurgis Night: Hatred and Despair"),  # the other Walpurgis pack stays
    (["MADNESS"], "Line 1"),  # #266: "LINE 1 MADNESS" reads only as its capitals
])
def test_title_art_finds_its_pack_through_the_data_file(lines, expected):
    plan = {"weights": {}, "unlisted": 0}
    assert rs.rank_packs([lines], DATA_NAMES, plan, DATA_TITLE_ART)[0][0] == expected


def test_every_pack_of_the_season_matches_itself_and_with_a_letter_lost():
    # The data file's own names: each one read back, and read with one letter dropped, finds itself.
    packs = yaml.safe_load(DATA.read_text(encoding="utf-8"))["packs"]
    for name in packs:
        assert rs.match_title(name, packs) == name
        i = len(name) // 2
        if len(compact(name)) >= 6:
            assert rs.match_title(name[:i] + name[i + 1:], packs) == name, name


def test_a_title_alike_to_several_packs_takes_their_weight_when_they_share_it():
    # Live 2026-10-18, floor 5: OCR read "Line 1" as "Line"; every Line pack weighs -5, so does this card.
    weights = {"Line 1": -5, "Line 2": -5, "Line 3": -5, "To be Crushed": 5, "To be Cleaved": -5}
    ranked = rs.rank_packs([["Line"], ["To be C"]], SHORT + NAMES, {"weights": weights, "unlisted": 2})
    assert ranked == [("Line", -5, "shared"), ("To be C", 2, "unread")]  # the second is alike to two weights: unlisted


def test_a_card_matching_no_pack_or_an_unweighed_one_takes_the_unlisted_weight():
    plan = {"weights": {"To be Crushed": -3}, "unlisted": -1}
    ranked = rs.rank_packs([["To be Crushed"], ["Lake World"], ["Brand New Pack"]], NAMES, plan)
    assert ranked == [("To be Crushed", -3, "name"), ("Lake World", -1, "unread"), ("Brand New Pack", -1, "unread")]


PLAN = {"threshold": 0, "unlisted": 0, "event_packs": "weight"}


@pytest.mark.parametrize(("weights", "threshold", "expected"), [
    ([-5, 0, 7], 0, (2, True)),  # the highest weight
    ([3, 7, 7], 0, (1, True)),  # leftmost among equals
    ([-5, -2, -5], 0, (1, False)),  # below the threshold: refresh if one is left, else take the best
    ([4, 2], 5, (0, False)),
    ([-10, -10], -10, (0, True)),  # a threshold at the lowest weight never refreshes
])
def test_the_best_card_is_taken_and_checked_against_the_threshold(weights, threshold, expected):
    assert rs.pick_pack(weights, [False] * len(weights), {**PLAN, "threshold": threshold}) == expected


@pytest.mark.parametrize(("mode", "weights", "events", "expected"), [
    ("weight", [5, -5], [False, True], (0, True)),  # an event pack is one pack among others
    ("weight", [-5, 5], [False, True], (1, True)),
    ("prefer", [5, -5, -3], [False, True, True], (2, True)),  # the best event pack, threshold or not
    ("prefer", [5, 3], [False, False], (0, True)),  # none shown: by weight
    ("avoid", [-5, 5], [False, True], (0, False)),  # left out while another card shows
    ("avoid", [5, -5], [True, True], (0, True)),  # only event packs: by weight
])
def test_event_packs_by_weight_preferred_or_avoided(mode, weights, events, expected):
    assert rs.pick_pack(weights, events, {**PLAN, "event_packs": mode}) == expected


EVENTS = {"Hell's Chicken", "Twining Threads"}
KNOWN = NAMES + ["Hell's Chicken", "Twining Threads", "Repressed Wrath", "Crawling Abyss"]


@pytest.mark.parametrize(("floor", "titles", "expected"), [
    (5, ["Twining Threads", "Repressed Wrath", "To be Crushed"], [True, False, False]),  # an event story pack
    (5, ["Brand New Event Pack", "Repressed Wrath"], [True, False]),  # a pack the data file lacks: a running event's
    (5, ["Repressed Wrath", "Twining Threads"], [False, False]),  # a plain pack leftmost; an event pack elsewhere
    (5, ["Line", "Twining Threads"], [False, False]),  # alike to known packs: not new
    (5, ["Crawling Abyss", "Twining Threads"], [False, False]),  # a plain pack, as rank_packs names a reversed read
    (3, ["Hell's Chicken", "Repressed Wrath"], [False, False]),  # another floor: an ended event's pack, by weight
    (4, ["Brand New Event Pack", "Repressed Wrath"], [False, False]),
    (5, [], []),
])
def test_only_floor_5s_leftmost_event_or_new_pack_takes_the_event_mode(floor, titles, expected):
    # #240, the user (2026-10-22): a running event's pack sits on floor 5, leftmost; an ended one is a plain pack.
    assert rs.event_slots(floor, titles, EVENTS, KNOWN + SHORT) == expected


@pytest.mark.parametrize(("floor", "titles", "mode", "expected"), [
    (5, ["Twining Threads", "Repressed Wrath"], "prefer", (0, True)),  # taken although -5
    (5, ["Twining Threads", "Repressed Wrath"], "avoid", (1, True)),  # left out: the next best
    (5, ["Twining Threads", "Repressed Wrath"], "weight", (1, True)),
    (5, ["Brand New Event Pack", "Repressed Wrath"], "prefer", (0, True)),
    (5, ["Repressed Wrath", "Twining Threads"], "prefer", (0, True)),  # plain leftmost: by weight, Repressed Wrath 3
    (3, ["Hell's Chicken", "Repressed Wrath"], "avoid", (0, True)),  # another floor: by weight, Hell's Chicken 4
    (5, ["Abyss Crawling", "Repressed Wrath"], "prefer", (1, True)),  # a plain pack read in reverse: not taken
])

def test_the_event_mode_on_floor_5s_leftmost_card(floor, titles, mode, expected):
    plan = {**PLAN, "event_packs": mode, "weights": {"Twining Threads": -5, "Repressed Wrath": 3, "Hell's Chicken": 4},
            "unlisted": 0}
    ranked = rs.rank_packs([t.split(" ", 1) for t in titles], KNOWN, plan)  # two OCR boxes per title
    slots = rs.event_slots(floor, [t for t, _, _ in ranked], EVENTS, KNOWN)
    assert rs.pick_pack([w for _, w, _ in ranked], slots, plan) == expected


def test_a_reversed_title_holding_an_event_packs_name_is_not_floor_5s_event_slot():
    # Read bottom up, "Mountain of Corpses, Sea of Blood" holds "Sea": not S.E.A., an event story pack (#240 review).
    ranked = rs.rank_packs([["Sea of Blood", "Mountain of Corpses,"]], DATA_NAMES, PLAN | {"weights": {}})
    assert ranked[0][0] == "Mountain of Corpses, Sea of Blood"
    assert rs.event_slots(5, [ranked[0][0]], {"S.E.A."}, DATA_NAMES) == [False]


@pytest.mark.parametrize(("setting", "used", "expected"), [
    ("all", 0, True), ("all", 3, True),  # every free refresh (#25's rule, the default)
    ("once", 0, True), ("once", 1, False),
    ("none", 0, False),
])
def test_a_page_below_the_threshold_is_refreshed_as_often_as_the_setting_allows(setting, used, expected):
    # #41: none / once / all; "all" stops only when a refresh changes nothing (the caller sees that).
    assert rs.refresh_wanted(False, setting, used) is expected


@pytest.mark.parametrize("setting", ["none", "once", "all"])
def test_a_page_meeting_the_threshold_is_never_refreshed(setting):
    assert rs.refresh_wanted(True, setting, 0) is False


@pytest.mark.parametrize(("marks", "refresh", "pick"), [
    (["avoid", "avoid"], True, 0), (["avoid", "neutral", "prefer"], False, 2), (["neutral", "avoid", "neutral"], False, 0),
])
def test_marks_migrated_to_weights_pick_and_refresh_as_before(marks, refresh, pick):
    # #240: prefer / neutral / avoid became +5 / 0 / -5 with threshold 0; v8's rule was "refresh only when all avoid,
    # take the best mark, leftmost".
    weights = [{"prefer": 5, "neutral": 0, "avoid": -5}[m] for m in marks]
    i, meets = rs.pick_pack(weights, [False] * len(marks), PLAN)
    assert (i, rs.refresh_wanted(meets, "all", 0)) == (pick, refresh)


@pytest.mark.parametrize(("visible", "target", "expected"), [
    ({1: 309, 2: 345}, 2, ("tap", 345)),
    ({1: 309, 7: 527}, 13, "down"),
    ({8: 303, 14: 523}, 2, "up"),
    ({}, 3, "down"),
])
def test_team_list_move(visible, target, expected):
    assert rs.team_list_move(visible, target) == expected


DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data/theme_packs.yaml"
DATA_YAML = yaml.safe_load(DATA.read_text(encoding="utf-8"))
DATA_NAMES, DATA_TITLE_ART = list(DATA_YAML["packs"]), DATA_YAML["title_art"]


def test_theme_pack_data_file():
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    packs, plan = data["packs"], data["default_plan"]
    # Each pack maps to its floors; an unquoted "a: b" name would parse as a nested dict.
    assert packs and all(isinstance(p, str) and re.fullmatch(r"(N[1-5]+)?( ?H[1-5]+)?", f) for p, f in packs.items())
    # #240: the default plan is AALC's weights, threshold 0, unlisted 0, event packs by weight.
    assert (plan["threshold"], plan["unlisted"], plan["event_packs"]) == (0, 0, "weight")
    assert all(p in packs and isinstance(w, int) and -10 <= w <= 10 for p, w in plan["weights"].items())
    assert plan["weights"]["The B.E."] == 10 and plan["weights"]["Hell's Chicken"] == 1
    # #89: the 1.117.0 client's packs with a NORMAL or HARD floor.
    assert len(packs) >= 90
    assert set(data["event_packs"]) <= set(packs) and len(data["event_packs"]) == 15
    # #246: each title art read names a pack of the season.
    assert data["title_art"] and set(data["title_art"].values()) <= set(packs)


def test_a_card_nothing_names_takes_the_unlisted_weight_and_keeps_its_place():
    # #266: a read that names no pack ("ZZZ") is still a card in the ranking, with the plan's unlisted weight.
    plan = {"weights": {"Line 1": -5}, "unlisted": 3}
    ranked = rs.rank_packs([["Tearful Things"], ["MADNESS"], ["ZZZ"]], DATA_NAMES, plan, DATA_TITLE_ART)
    assert ranked == [("Tearful Things", 3, "name"), ("Line 1", -5, "title_art"), ("ZZZ", 3, "unread")]


# OCR boxes read off 2026-10-22 captures (title strip), the logo and noise reads kept: #266, #267
TIMEKILLING_PAGE = [
    ("Tearful Things", (143, 443, 148, 24)), ("WIOPIS", (203, 413, 42, 25)), ("Degraded Gloom", (349, 444, 158, 22)),
    ("H", (401, 413, 54, 24)), ("Timekilling", (560, 446, 108, 18)), ("TIMKILLING", (563, 400, 151, 19)),
    ("TME", (605, 416, 65, 26)), ("Time", (672, 447, 44, 16)), ("Crawling Abyss", (773, 445, 154, 22)),
    ("WOPIS", (835, 413, 42, 24)), ("Walpurgis Night", (986, 412, 142, 22)), ("Full-Stopped by a", (986, 438, 139, 22)),
    ("Bullet", (1038, 457, 45, 14)),
]
LINE_1_PAGE = [
    ("The Surrendered", (261, 440, 123, 16)), ("Witnessing", (282, 454, 82, 17)), ("LIMBUS", (311, 414, 37, 15)),
    ("MADNESS", (458, 400, 161, 60)), ("Four", (684, 442, 34, 15)), ("Houses and", (720, 443, 85, 14)),
    ("Greed", (721, 456, 45, 16)), ("LIMBUS", (733, 414, 35, 15)), ("WYAM", (871, 445, 16, 8)),
    ("Tangling Lust", (880, 444, 148, 22)),
]


def test_a_title_split_into_two_boxes_on_one_line_is_one_card():
    # #267: "Timekilling" and "Time" sit 4 px apart but their centres 80 px: the old 80 px test made two cards.
    cards = rs.pack_cards(TIMEKILLING_PAGE)
    # (the logo's misreads and the art's capitals stay lines of their card, #274)
    assert [lines for _, lines in cards] == [["WIOPIS", "Tearful Things"], ["H", "Degraded Gloom"],
                                              ["TIMKILLING", "TME", "Timekilling", "Time"], ["WOPIS", "Crawling Abyss"],
                                              ["Walpurgis Night", "Full-Stopped by a", "Bullet"]]
    assert [x for x, _ in cards][2] == 638  # the swipe lands in the middle of the card's text, not on its first box


def test_a_card_titled_in_capitals_is_listed_and_the_known_logo_alone_is_not_a_card():
    # #266: LINE 1 MADNESS reads only as MADNESS; the capitals were dropped and the whole card with them. #274: the
    # filter is the words the card shows besides its title (NOT_TITLE), not "no lowercase letter": noise beside a title
    # stays a line of that card (it is read past), and the logo's own word alone is no card.
    cards = rs.pack_cards(LINE_1_PAGE)
    assert [lines for _, lines in cards] == [["The Surrendered", "Witnessing"], ["MADNESS"],
                                              ["Four", "Houses and", "Greed"], ["Tangling Lust", "WYAM"]]
    assert rs.pack_cards([("LIMBUS", (311, 414, 37, 15)), ("LIMBUS COMPANY", (500, 414, 90, 15)), ("", (700, 414, 20, 15))]) == []


@pytest.mark.parametrize("word", ["LIMBUS", "limbus", "COMPANY", "LIMBUS COMPANY", "Limbus  Company", "CAUTION", "CLEAR BONUS", "LV"])
def test_a_box_reading_exactly_a_non_title_word_is_dropped(word):
    assert rs.pack_cards([(word, (300, 414, 90, 15)), ("Lake World", (300, 440, 90, 15))]) == [(345, ["Lake World"])]


@pytest.mark.parametrize("text", ["THE DUSK OF AMBER", "AMBER", "MURDER", "WARP EXPRESS", "LINE 2", "LIMBUS RISING", "CAUTION IV", "WOPIS", "深夜清扫"])
def test_every_other_read_stays_a_card_capitals_included(text):
    # read off the captures (#274): capitals that are a title (the old rule kept only a box 80 px wide or more, and none
    # with a lowercase letter beside it), the logo's second word misread, a Chinese art title
    assert rs.pack_cards([(text, (300, 420, 40, 15))]) == [(320, [text])]


@pytest.mark.parametrize(("noise_x", "cards"), [(rs.CARD_SPAN - 2, 1), (rs.CARD_SPAN + 2, 2)])
def test_a_noise_box_near_a_title_belongs_to_its_card(noise_x, cards):
    # #274: with no lowercase rule, a lone "M" beside a card (live: 70 px from the centre) must not be a card
    title = ("Lake World", (200, 440, 80, 20))  # centre 240
    noise = ("M", (240 + noise_x - 10, 400, 20, 20))
    found = rs.pack_cards([title, noise])
    assert len(found) == cards
    if cards == 1:
        assert found[0][1] == ["M", "Lake World"]


def test_texts_of_neighbouring_cards_stay_apart():
    # the cards' pitch is 211 px: two titles are two cards, long or short
    found = rs.pack_cards([("The Surrendered Witnessing", (150, 440, 130, 20)), ("Tangling Lust", (380, 444, 148, 22))])
    assert [lines for _, lines in found] == [["The Surrendered Witnessing"], ["Tangling Lust"]]


@pytest.mark.parametrize(("gap", "cards"), [(rs.CARD_GAP - 1, 1), (rs.CARD_GAP, 2)])
def test_two_boxes_are_one_card_below_the_gap(gap, cards):
    # wide boxes, whose centres are past CARD_SPAN either way: the gap alone decides
    assert len(rs.pack_cards([("Lake", (100, 440, 120, 20)), ("World", (220 + gap, 440, 120, 20))])) == cards


# keywords and the paths a card is read by (#274)
ALL_NAMES = DATA_NAMES + list(DATA_TITLE_ART)


def test_a_keyword_is_the_shortest_word_no_other_name_contains():
    assert rs.pack_keywords(["To be Cleaved", "To be Pierced"]) == {"To be Cleaved": "cleaved", "To be Pierced": "pierced"}
    # "flood" sits inside no other name; "emotional" is in both, "craving" and "flood" are the shortest words left
    assert rs.pack_keywords(["Emotional Flood", "Emotional Craving"]) == {"Emotional Flood": "flood", "Emotional Craving": "craving"}
    # a word another name contains is out ("sink" is in "Sinking"): the next word
    assert rs.pack_keywords(["Sink Hole", "Sinking Pang"]) == {"Sink Hole": "hole", "Sinking Pang": "pang"}
    # no word is its own: the shortest stretch of the name instead
    assert rs.pack_keywords(["Line 1", "Line 2"]) == {"Line 1": "ine1", "Line 2": "ine2"}
    # a name every stretch of which another holds, or too short a one, has none
    assert rs.pack_keywords(["Sea", "Sea of Blood"]) == {"Sea of Blood": "blood"}


def test_every_keyword_of_the_season_is_in_one_name_only_and_every_pack_but_one_has_one():
    keywords = rs.pack_keywords(ALL_NAMES)
    for name, keyword in keywords.items():
        assert len(keyword) >= rs.KEYWORD_MIN
        assert [n for n in ALL_NAMES if keyword in compact(n)] == [name]
    assert [n for n in DATA_NAMES if n not in keywords] == ["S.E.A."]  # "sea" is in Mountain of Corpses, Sea of Blood


def test_every_keyword_finds_its_pack_and_no_other():
    # sweep: each pack's keyword alone, and inside noise; the name it finds is its own, never a neighbour's
    for name, keyword in rs.pack_keywords(ALL_NAMES).items():
        for text in (keyword, f"LImBUS {keyword}", f"{keyword.upper()} wopis"):
            assert rs.match_keyword(text, ALL_NAMES) == name, (name, text)


@pytest.mark.parametrize(("text", "expected"), [
    ("miiracle InDistrict", "Miracle in District 20"),  # live: a slip inside a 7-letter keyword
    ("Houses and Four Greed", "Four Houses and Greed"),
    ("Tangling", "Tangling Lust"),
    ("Tang1ing", "Tangling Lust"),  # one slip in an 8-letter keyword passes
    ("Tangl", None), ("lake", "Lake World"), ("Lakx", None),  # a 4-letter keyword reads exactly
    ("LImBUS", None), ("WOPIS", None), ("", None),  # logo and noise
    ("Nagel cleaved", None),  # two packs' keywords: no guess
])
def test_a_half_read_title_is_named_by_its_keyword(text, expected):
    assert rs.match_keyword(text, ALL_NAMES) == expected


def test_each_path_of_a_card_is_named_in_the_ranking_and_a_failed_path_falls_through_to_the_next():
    plan = {"weights": {"Line 1": -5, "Line 2": -5, "Line 3": -5, "Line 5": -5}, "unlisted": 0}
    asked = []

    def cover(i, allowed):
        asked.append((i, allowed))
        return ("Line 5", 0.93) if i == 3 else None

    cards = [["Nagel und Hammer"], ["MADNESS"], ["WOPIS", "Four"], ["WOPIS", "Line"], ["Line"], ["ZZZ"]]
    ranked = rs.rank_packs(cards, DATA_NAMES, plan, DATA_TITLE_ART, cover)
    assert ranked == [("Nagel und Hammer", 0, "name"), ("Line 1", -5, "title_art"), ("Four Houses and Greed", 0, "keyword"),
                      ("Line 5", -5, "cover 0.93"), ("Line", -5, "shared"), ("ZZZ", 0, "unread")]
    # the first three never ask the cover; the title narrows it to the packs it is alike to; a title like none leaves it free
    assert [i for i, _ in asked] == [3, 4, 5]
    assert asked[0][1] == {"Line 1", "Line 2", "Line 3", "Line 5"} == asked[1][1]
    assert asked[2][1] is None


def test_without_a_cover_a_card_no_title_path_reads_is_unlisted_as_before():
    ranked = rs.rank_packs([["WOPIS", "Line"]], DATA_NAMES, {"weights": {"Line 1": -5, "Line 2": -9}, "unlisted": 3})
    assert ranked == [("WOPIS Line", 3, "unread")]  # alike titles with two weights: unlisted

