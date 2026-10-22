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
    assert ranked == [("Line", -5), ("To be C", 2)]  # the second is alike to two weights: unlisted


def test_a_card_matching_no_pack_or_an_unweighed_one_takes_the_unlisted_weight():
    plan = {"weights": {"To be Crushed": -3}, "unlisted": -1}
    ranked = rs.rank_packs([["To be Crushed"], ["Lake World"], ["Brand New Pack"]], NAMES, plan)
    assert ranked == [("To be Crushed", -3), ("Lake World", -1), ("Brand New Pack", -1)]


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
    slots = rs.event_slots(floor, [t for t, _ in ranked], EVENTS, KNOWN)
    assert rs.pick_pack([w for _, w in ranked], slots, plan) == expected


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
    assert ranked == [("Tearful Things", 3), ("Line 1", -5), ("ZZZ", 3)]


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
    assert [lines for _, lines in cards] == [["Tearful Things"], ["Degraded Gloom"], ["Timekilling", "Time"],
                                              ["Crawling Abyss"], ["Walpurgis Night", "Full-Stopped by a", "Bullet"]]
    assert [x for x, _ in cards][2] == 638  # the swipe lands in the middle of the card's text, not on its first box


def test_a_card_titled_in_capitals_is_listed_and_the_logo_alone_is_not_a_card():
    # #266: LINE 1 MADNESS reads only as MADNESS; the capitals were dropped and the whole card with them. The
    # narrow LIMBUS logo and noise beside a lowercase title add no card.
    cards = rs.pack_cards(LINE_1_PAGE)
    assert [lines for _, lines in cards] == [["The Surrendered", "Witnessing"], ["MADNESS"],
                                              ["Four", "Houses and", "Greed"], ["Tangling Lust"]]
    assert rs.pack_cards([("LIMBUS", (311, 414, 37, 15)), ("WYAM", (871, 445, 16, 8))]) == []
