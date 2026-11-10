import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import yaml

import rewards as r

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
SCREENS = Path(__file__).resolve().parent / "screens"

ORDER = ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"]


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


def table():
    return json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))["events"]


def test_match_event_reads_the_end_of_the_story():
    # EventChoices.png (901069): the box shows the last lines of a story longer than it holds.
    story = ("What looked like palms are made of black rocks. At the tip of the fingers attached to the palms are smaller palms "
             "and smaller fingers. It reaches out with the hand of the hand.")
    assert [o["text"] for o in r.match_event(story, table())] == ["Shake hands.", "Push the hand away."]
    assert r.match_event(story.replace("palms", "pa1ms").replace("hand.", "hand"), table())  # OCR slips
    assert r.match_event("A story this season's table does not have.", table()) is None


def test_match_event_prefers_the_longest_story_matched():
    # Five pages tell only "What will you do?": a long story ending the same way is that story's event, the
    # short ones are pooled, each on-screen option then finds its own entry by its texts.
    events = [{"key": "whatwillyoudo", "options": [{"text": "Take the painting.", "hint": "", "kind": "other"}]},
              {"key": "whatwillyoudo", "options": [{"text": "Leave.", "hint": "", "kind": "other"}]},
              {"key": "thepaintinghangsonthewallwhatwillyoudo", "options": [{"text": "Burn it.", "hint": "", "kind": "other"}]}]
    assert [o["text"] for o in r.match_event("What will you do?", events)] == ["Take the painting.", "Leave."]
    assert [o["text"] for o in r.match_event("The painting hangs on the wall. What will you do?", events)] == ["Burn it."]


def opt(text, hint, kind, *gifts):
    return {"text": text, "hint": hint, "kind": kind, "gifts": [list(g) for g in gifts]}


RANKED = [  # AALC's order (#233), best last; on screen as "<text> <hint>"
    opt("Leave.", "", "other"),
    opt("Read it.", "Run a Wrath check to gain an E.G.O Gift.", "check_fail_gift", ("Burn", "check_fail")),
    opt("Fight.", "Win the battle to earn a Burn E.G.O Gift", "battle", ("Burn", "win_battle")),
    opt("Wait.", "Then, maybe gain a Bleed E.G.O Gift depending on the subsequent choice", "followup", ("Bleed", "later_direct")),
    opt("Open it.", "Lust check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass")),
    opt("Take it.", "Select to gain a Bleed E.G.O Gift", "direct", ("Bleed", "direct")),
    opt("Hold it.", "Select to gain a Burn E.G.O Gift", "direct", ("Burn", "direct")),
    opt("Insert the coin.", "???", "random", ("Keywordless", "direct_random")),
]


def shown(event):
    return [f"{o['text']} {o['hint']}" for o in event]


def test_pick_choice_ranks_by_the_event_table():
    # ??? / random > direct gain > check pass > "gain ... depending on" > the rest (AALC's order, #233)
    options = shown(RANKED)
    for best in range(len(RANKED) - 1, 2, -1):
        assert r.pick_choice(options, "Burn", closed=range(best + 1, len(RANKED)), event=RANKED) == best
    # a battle or a gift only when a check fails is no tier: the first of the rest
    assert r.pick_choice(options, "Burn", closed=range(3, len(RANKED)), event=RANKED) == 0
    assert r.pick_choice(options, "Bleed", event=RANKED) == 7  # the main keyword never lifts an option across tiers
    assert r.pick_choice(options, "Burn", closed={7}, event=RANKED) == 6
    assert r.pick_choice(options, "Bleed", closed={7}, event=RANKED) == 5
    assert r.pick_choice(options, "Burn", closed={5, 6, 7}, event=RANKED) == 4
    assert r.pick_choice(options, "Burn", "Leave", event=RANKED) == 0  # an override still wins


def test_pick_choice_depending_on_check_text_is_the_fourth_tier():
    # 971003: a check entry whose hint only says "Gain ... depending on" ranks with the follow-ups, below a plain check
    depending = opt("Alert it.", "Gain a Bleed E.G.O Gift depending on the result of the following choice", "check", ("Bleed", "check_pass"))
    plain = opt("Pull.", "Wrath check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass"))
    event = [depending, plain]
    assert r.pick_choice(shown(event), "Bleed", event=event) == 1
    assert r.pick_choice(shown(event[::-1]), "Bleed", event=event) == 0


def test_pick_choice_a_check_or_followup_without_the_aalc_text_is_the_rest():
    # 901061 (check, empty hint), 971088 and 901023 (follow-ups whose hint says neither check nor depending on)
    blank = opt("Open it.", "", "check", ("Sinking", "check_pass"))
    cost = opt("Gamble.", "Choose to gain or lose Cost", "followup", ("Keywordless", "later_direct"))
    chance = opt("Reach in.", "Select for a chance to gain a Rupture E.G.O Gift", "followup", ("Rupture", "later_direct"))
    depending = opt("Wait.", "Gain a Keywordless E.G.O Gift depending on the result of the following choice", "followup", ("Keywordless", "later_direct"))
    for odd in (blank, cost, chance):
        event = [odd, depending]
        assert r.pick_choice(shown(event), "Rupture", event=event) == 1
        assert r.pick_choice(shown(event[::-1]), "Rupture", event=event) == 0


def test_pick_choice_a_random_option_with_a_stated_chance_is_no_question_mark_tier():
    # 971003 (the real entries): "Select for a 50% chance to gain" is not AALC's ??? template; the direct gain wins
    alert = opt("Alert it truthfully.", "Gain a Bleed E.G.O Gift depending on the result of the following choice", "check", ("Bleed", "check_pass"))
    nothing = opt("You saw nothing.", "Select to gain a Keywordless E.G.O Gift", "direct", ("Keywordless", "direct"))
    chance = opt("Give a few subtle hints.", "Select for a 50% chance to gain a Keywordless E.G.O Gift.", "random", ("Keywordless", "direct_random"))
    event = [alert, nothing, chance]
    for kw in r.KEYWORDS:
        assert r.pick_choice(shown(event), kw, event=event) == 1
        assert r.pick_choice(shown(event[::-1]), kw, event=event[::-1]) == 1
    # a ??? random option (971055) is still the first tier, with or without the table
    coin = opt("Insert the coin in the slot.", "???", "random", ("Keywordless", "direct_random"))
    assert r.pick_choice(shown([nothing, coin]), "Burn", event=[nothing, coin]) == 1
    # no table (or an option it does not know): the hint text ranks by the same rule
    assert r.pick_choice(shown(event), "Burn") == 1
    assert r.pick_choice(shown([nothing, coin]), "Burn") == 1
    assert r.pick_choice(["Hints. Select for a 50% chance to gain a Burn E.G.O Gift.", "Leave."], "Burn") == 0  # the rest: screen order


def test_pick_choice_ties_go_to_the_main_keyword_then_the_screen_order():
    event = [opt("Pull.", "Wrath check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass")),
             opt("Push.", "Wrath check. Pass to gain a Bleed E.G.O Gift.", "check", ("Bleed", "check_pass"))]
    assert r.pick_choice(shown(event), "Bleed", event=event) == 1
    assert r.pick_choice(shown(event), "Tremor", event=event) == 0


def test_pick_choice_ties_each_option_to_its_entry_by_its_texts():
    hidden = [opt("Kick the machine.", "???", "other"),
              opt("Insert the coin in the slot.", "???", "random", ("Keywordless", "direct_random"))]
    assert r.pick_choice(["Insert the coin in the slot. ???", "Kick the machine. ???"], "Burn", event=hidden) == 0
    same_hint = [opt("Walk into the mist.", "Wrath & Lust Advantage check.", "check", ("Burn", "check_pass")),
                 opt("Look the mist in the eye.", "Wrath & Lust Advantage check.", "check_other")]
    assert r.pick_choice(shown(same_hint[::-1]), "Burn", event=same_hint) == 1
    # "Leave." is its own entry, not the start of "Leave the room."
    rooms = [opt("Leave.", "", "other"), opt("Leave the room.", "Select to gain a Charge E.G.O Gift", "direct", ("Charge", "direct"))]
    assert r.pick_choice(["Leave.", "Leave the room. Select to gain a Charge E.G.O Gift"][::-1], "Burn", event=rooms) == 0
    # a hint cut off at the panel edge still finds its entry
    cut = shown(RANKED[:1]) + ["Hold it. Select to gain a Bu"]
    assert r.pick_choice(cut, "Burn", event=RANKED) == 1


def test_pick_choice_an_option_not_in_the_entry_falls_back_to_its_hint():
    event = [opt("Stay.", "", "other"), opt("Go.", "Select to gain a Burn E.G.O Gift", "direct", ("Burn", "direct"))]
    # never by position: the first option on screen is an OCR miss, not "Stay."
    assert r.pick_choice(["Qwerty plugh.", "Stay."], "Burn", event=event) == 0
    assert r.pick_choice(["Stay.", "Grab it. Win the battle to earn a Burn E.G.O Gift"], "Burn", event=event) == 0  # a battle is no tier
    assert r.pick_choice(["Fight. Win the battle to earn a Burn E.G.O Gift", "Grab it. Select to gain a Bleed E.G.O Gift",
                          "Coin. ???"], "Burn", event=event) == 2


def test_pick_choice_override_wins():
    options = ["Take the gift. Pass to gain a Burn E.G.O Gift.", "Leave it alone."]
    assert r.pick_choice(options, "Burn", "Leave it") == 1
    assert r.pick_choice(options, "Burn", "not on screen") == 0


def test_pick_choice_passes_over_closed_options():
    # Live 2026-10-17 (#34), floor 5 boss's second round of questions: the first answer was taken last round.
    options = [
        "What if you do feel like what you did was wrong? Weakens the Poise Passive 「Adaptation, for this Encounter",
        "You're running away from something. Weakens the Shield Passive 「Defense Mechanism, for this Encounter",
    ]
    assert r.pick_choice(options, "Poise", closed={0}) == 1
    assert r.pick_choice(options, "Poise", options[0][:20], closed={0}) == 1  # an override of a closed one too
    gift = ["Leave.", "Pass to gain a Burn E.G.O Gift."]
    assert r.pick_choice(gift, "Burn", closed={1}) == 0
    assert r.pick_choice(options, "Poise", closed={0, 1}) is None  # all closed: scroll for more


def test_choice_open_reads_the_frame_colour():
    # EventChoicesUsed.png (live 2026-10-17, #34): an answer taken in an earlier round turns grey and does
    # nothing when tapped; the open ones stay red-brown. y is each option's first line (Event.rows).
    image = screen("EventChoicesUsed")
    assert not r.choice_open(image, 208)
    assert r.choice_open(image, 367)


def test_choice_cards_and_scrollbar_show_a_list_that_scrolls():
    # EventChoicesUsed.png (#34): three options, the third cut off at the list's bottom edge, a scrollbar right of them.
    used = screen("EventChoicesUsed")
    assert r.choice_scrollbar(used)
    assert r.choice_cards(used) == [(170, 302), (320, 452), (469, None)]
    # EventChoices.png: two options that fit, no scrollbar.
    fits = screen("EventChoices")
    assert not r.choice_scrollbar(fits)
    assert r.choice_cards(fits) == [(170, 284), (301, 414)]


def test_choice_cards_read_a_lit_card_whole():
    # #196 (live 2026-10-20, recording frames): the card a drag lifts over lights orange, its glow making its
    # bottom edge 12-13 px, as thick as a top. Top: East lit, West cut. Bottom: West lit, East's top cut off.
    assert r.choice_cards(screen("EventChoicesLitTop")) == [(170, 283), (300, 423), (431, None)]
    assert r.choice_cards(screen("EventChoicesLitBottom")) == [(None, 237), (254, 377), (385, 498)]
    assert r.choice_cards(screen("EventChoicesScrolledBack")) == [(None, 257), (274, 387), (405, None)]


def screen(name):
    """tests/screens/<name>.png as BGR, for fixtures written by recovery.png (one IDAT, filter 0 on every row)."""
    data = (SCREENS / f"{name}.png").read_bytes()
    w, h = struct.unpack(">II", data[16:24])
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(h, 1 + w * 3)
    return rows[:, 1:].reshape(h, w, 3)[:, :, ::-1]


def test_pick_checker_takes_best_odds_leftmost():
    captions = [("High", 216), ("Very High", 286), ("Very Low", 355), ("Very High", 147), ("Normal", 700)]
    assert r.pick_checker(captions) == 3
    assert r.pick_checker([("Low", 77), ("Very  low", 147), ("???", 216)]) == 0
    # Live OCR: one caption per portrait, spaces dropped, tails misread.
    assert r.pick_checker([("VeryLow", 77), ("Normat", 147), ("VeryHigh", 216), ("High", 286)]) == 2
    assert r.pick_checker([("??", 77)]) is None
    assert r.pick_checker([]) is None
    # A sinner a tap did nothing on is passed over: the next best, then none.
    assert r.pick_checker(captions, skip={3}) == 1
    assert r.pick_checker([("Low", 77), ("High", 147)], skip={0, 1}) is None


def test_card_type():
    assert r.card_type("Gain a random Tier 1~2 E.G.O Gift") == "Random E.G.O Gift"
    assert r.card_type("E.G.O Resource +6 for 2 of the least-owned Affinities") == "E.G.O Resource"
    assert r.card_type("Gain 100~150 Cost") == "Cost"
    assert r.card_type("Gain 55~83 Cost 33% chance to gain a random Tier 2~3 Bleed E.G.O Gift") == "Cost & Keyword Gift Chance"
    assert r.card_type("Gain additional 8~10 Starlight upon clearing the Mirror Dungeon") == "Starlight"
    assert r.card_type("") is None
    assert r.card_type("Ｇａｉｎ ８~１０ Ｓｔａｒｌｉｇｈｔ") == "Starlight"  # #138: full-width as OCR may read it


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


@pytest.mark.parametrize("text", [
    "White Gossypium Bleed", "Whte Gossypiurn Bleed", "WhiteGossypium Bleed", "White Gossypiu Bleed",  # OCR slips
])
def test_a_gift_the_team_avoids_is_told_by_its_name_whatever_its_keyword(text):
    # #90: a Bleed team that does not hold White Gossypium.
    assert r.gift_kind(text, "Bleed", False, avoid=["White Gossypium"]) == "avoid"
    assert r.gift_kind(text, "Bleed", True, avoid=["White Gossypium"]) == "avoid"
    assert r.gift_kind(text, "Bleed", False) == "main"


def test_a_gift_like_the_avoided_one_is_not_avoided():
    assert r.gift_kind("White Bleed Potency", "Bleed", False, avoid=["White Gossypium"]) == "main"


def test_rank_gifts_without_trials():
    assert r.rank_gifts([("other", None, None), ("main", None, None), ("owned", None, None), ("main", None, None)]) == [1, 3, 0, 2]


def test_rank_gifts_with_trials():
    # score = gift - burden: main/1 -> 2, other/0 -> 2 (the lighter first), main/3 -> 0, other/5 -> -3
    cards = [("main", None, 1), ("other", None, 0), ("main", None, 3), ("other", None, 5)]
    assert r.rank_gifts(cards) == [1, 0, 2, 3]


class GiftPage:
    """Select n/m over the gift cards: a tap picks a card, or drops it when picked; full, a tap does nothing.

    A page that shows no count (counted=False, #494) reads "Select" alone and takes one card: a tap on another card
    moves the pick to it.
    """

    def __init__(self, picks, unread=0, counted=True, missed=""):
        self.picks, self.unread, self.counted = picks, unread, counted  # unread: count reads that come back as missed first
        self.missed = missed
        self.picked, self.taps = [], []

    def read(self):
        if self.unread:
            self.unread -= 1
            return self.missed
        return f"Select {len(self.picked)}/{self.picks}" if self.counted else "Select"

    def tap(self, i):
        self.taps.append(i)
        if i in self.picked:
            self.picked.remove(i)
        elif len(self.picked) < self.picks:
            self.picked.append(i)
        elif not self.counted:
            self.picked = [i]


@pytest.mark.parametrize("missed", ["", "Select O/2"])  # nothing read, or the count misread: not a page with no count
def test_pick_gifts_taps_every_card_when_the_count_never_reads(missed):
    page = GiftPage(picks=2, unread=99, missed=missed)  # #81: hard boss, Select 0/2 not read
    r.pick_gifts([1, 0], page.read, page.tap)
    assert sorted(page.picked) == [0, 1]


def test_pick_gifts_stops_at_the_count_once_it_reads():
    page = GiftPage(picks=1, unread=1)  # the first read misses, the second reads Select 0/1
    r.pick_gifts([2, 0, 1], page.read, page.tap)
    assert page.taps == [2]
    page = GiftPage(picks=1, unread=2)  # unread until the first card is in: Select 1/1
    r.pick_gifts([2, 0, 1], page.read, page.tap)
    assert page.taps == [2]


@pytest.mark.parametrize("unread", [0, 99])
def test_pick_gifts_a_lone_card_is_tapped_once(unread):
    page = GiftPage(picks=1, unread=unread, counted=False)
    r.pick_gifts([0], page.read, page.tap)
    assert page.taps == [0]


def test_pick_gifts_a_page_with_no_count_takes_the_best_card():
    page = GiftPage(picks=1, counted=False)  # #494's floor-4 page, ranked [0, 2, 1]
    assert r.pick_gifts([0, 2, 1], page.read, page.tap) == [0]
    assert page.picked == [0]


def test_pick_gifts_select_alone_on_a_page_with_trials_is_a_count_missed():
    # #494: every page with trials showed its count (20 of 20 in #344's runs); a Select 0/2 read short goes on as #81
    page = GiftPage(picks=2, unread=99, missed="Select")
    r.pick_gifts([1, 0, 2], page.read, page.tap, has_trials=True)
    assert sorted(page.picked) == [0, 1]


def test_pick_gifts_repicks_a_card_the_tap_dropped():
    page = GiftPage(picks=2)
    page.picked = [1]  # left picked by the last try, Select 1/2
    assert r.pick_gifts([1, 0, 2], page.read, page.tap) == [1, 0]  # the cards it took, for the trials' Coin count (#381)
    assert sorted(page.picked) == [0, 1]


def test_data_files():
    assert yaml.safe_load((DATA / "events.yaml").read_text(encoding="utf-8")) == {}
    events = json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))
    assert events["client"] == "1.117.0" and "Project Moon" in events["note"]
    nails = next(e for e in events["events"] if e["id"] == 901008)["options"][0]  # Grimy Iron Stake is a Bleed gift
    assert (nails["text"], nails["kind"], nails["gifts"]) == ("Remove the nails.", "check", [["Bleed", "check_pass"]])


def _option(event_id, text):
    events = json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))["events"]
    return next(o for e in events if e["id"] == event_id for o in e["options"] if o["text"] == text)


def test_event_table_keeps_each_gift_id_with_how_it_is_given():
    assert _option(901001, "Reach out.")["gift_ids"] == [[9001, "direct"]]
    assert _option(971003, "Give a few subtle hints.")["gift_ids"] == [[9705, "direct_random"]]


def test_event_table_gift_ids_are_gifts_and_match_the_keyword_pairs():
    events = json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))["events"]
    assert len(events) == 197
    for e in events:
        for o in e["options"]:
            assert ("gifts" in o) == ("gift_ids" in o)
            if "gifts" in o:  # the same ways of giving, once as the keyword pairs and once as the ids
                assert {h for _, h in o["gifts"]} == {h for _, h in o["gift_ids"]}
            assert all(i < 990000 for i, _ in o.get("gift_ids", []))  # a hidden battle buff is no gift


def test_event_table_matches_the_game_data_when_it_is_unpacked():
    import event_table
    from local_dir import local_dir
    unpack = local_dir("unpack")
    src = unpack / "out/events-md8.json"
    static = unpack / "static/Assets/Resources_moved/StaticData/static-data"
    if not src.is_file() or not static.is_dir():
        pytest.skip("no unpacked game data")
    got = event_table.build(src, static)
    assert got == (DATA / "event_table.json").read_text(encoding="utf-8")


def gift_opt(text, hint, kind, gifts, how="direct"):
    return {"text": text, "hint": hint, "kind": kind, "gifts": [["Burn", how]] * bool(gifts),
            **({"gift_ids": [[g, h] for g, h in gifts]} if gifts else {})}


WANT = {9001: "want", 9002: "pack-want", 9003: "material"}.get
PAGE = [gift_opt("Reach out.", "Select to gain a Burn E.G.O Gift", "direct", [(9001, "direct")]),
        gift_opt("???", "???", "random", []),
        gift_opt("Look closer.", "Pass to gain a Burn E.G.O Gift", "check", [(9001, "check_pass"), (9005, "check_fail")])]


def plan(options, entries, **kw):
    return r.choice_plan(options, "Burn", event=entries, want=WANT, **kw)


def test_an_option_giving_a_wanted_gift_goes_ahead_of_the_hint_levels():
    # Without a want the ??? option is first; with 9001 wanted "Reach out." is.
    texts = ["Reach out. Select to gain a Burn E.G.O Gift", "??? ???"]
    assert r.pick_choice(texts, "Burn", event=PAGE[:2]) == 1
    assert plan(texts, PAGE[:2]) == (0, False)


def test_a_wanted_gift_given_only_after_a_check_or_a_battle_goes_first_too():
    page = [gift_opt("Reach out.", "Select to gain a Burn E.G.O Gift", "direct", [(9100, "direct")]),
            gift_opt("Look closer.", "Pass to gain a Burn E.G.O Gift", "check", [(9001, "check_pass")]),
            gift_opt("Fight.", "Win the battle to gain", "battle", [(9001, "win_battle")]),
            gift_opt("Wait.", "", "other", [(9001, "later_direct")])]
    texts = [o["text"] + " " + o["hint"] for o in page]
    assert plan(texts, page)[0] == 1  # the old level breaks the tie between equal scores: the check (2) before battle (4)
    assert plan(texts, page, closed={1})[0] == 2
    assert plan(texts, page, closed={1, 2})[0] == 3


def test_the_higher_gift_score_wins_between_wanted_options():
    page = [gift_opt("A.", "Select to gain a Burn E.G.O Gift", "direct", [(9001, "direct")]),
            gift_opt("B.", "Pass to gain a Burn E.G.O Gift", "check", [(9003, "check_pass")]),
            gift_opt("C.", "Win the battle to gain", "battle", [(9002, "win_battle")])]
    texts = [o["text"] + " " + o["hint"] for o in page]
    assert plan(texts, page)[0] == 2  # pack-want 9 > want 6 > material 5.5
    assert plan(texts, page, closed={2})[0] == 0
    assert plan(texts, page, closed={2, 0})[0] == 1


def test_a_wanted_gift_only_a_failed_check_gives_asks_for_the_lowest_odds_sinner():
    fail_only = gift_opt("Learn.", "Advantage check", "check_fail_gift", [(9001, "check_fail")])
    both = gift_opt("Look closer.", "Pass to gain a Burn E.G.O Gift", "check", [(9001, "check_pass"), (9001, "check_fail")])
    other = gift_opt("Leave.", "Select to gain a Burn E.G.O Gift", "direct", [(9100, "direct")])
    texts = ["Leave. Select to gain a Burn E.G.O Gift", "Learn. Advantage check"]
    assert plan(texts, [other, fail_only]) == (1, True)
    assert plan(["Look closer. Pass to gain a Burn E.G.O Gift", texts[0]], [both, other]) == (0, False)
    # The best wanted gift decides: a pack-want 9002 on pass beats a want 9001 on fail.
    mixed = gift_opt("Mixed.", "Advantage check", "check", [(9001, "check_fail"), (9002, "check_pass")])
    assert plan(["Mixed. Advantage check"], [mixed]) == (0, False)


def test_between_equally_wanted_gifts_the_one_a_passed_check_gives_decides_whatever_their_order():
    # As 901015's "I don't know how to live without alcohol.": one gift on a pass, another on a fail, in either order.
    want = {9001: "want", 9004: "want"}.get
    for ids in ([(9001, "check_pass"), (9004, "check_fail")], [(9004, "check_fail"), (9001, "check_pass")]):
        drink = gift_opt("Drink.", "Advantage check", "check", ids)
        assert r.choice_plan(["Drink. Advantage check"], "Burn", event=[drink], want=want) == (0, False)


def test_pooled_pages_whose_same_option_gives_another_gift_rank_it_by_its_hint():
    # Shaped after 971098 and 971099: they share their story's end and option texts, only "Accept the deal."'s gift
    # id differs (9237, 9236). The screen cannot tell them apart, so a want of one of the ids is no reason to go first.
    take = "Take it. Select to gain a Burn E.G.O Gift"
    deal = "Accept the deal. Wrath check. Pass to gain a Burn E.G.O Gift"
    pooled = [gift_opt("Accept the deal.", "Wrath check. Pass to gain a Burn E.G.O Gift", "check", [(9001, "check_pass")]),
              gift_opt("Take it.", "Select to gain a Burn E.G.O Gift", "direct", [(9100, "direct")]),
              gift_opt("Accept the deal.", "Wrath check. Pass to gain a Burn E.G.O Gift", "check", [(9101, "check_pass")]),
              gift_opt("Take it.", "Select to gain a Burn E.G.O Gift", "direct", [(9100, "direct")])]
    assert plan([deal, take], pooled) == (1, False)  # the direct gain (level 1) before the check (2)
    assert plan([deal, take], pooled[:2]) == (0, False)  # one page alone: the wanted 9001 goes first


def test_without_a_want_the_plan_is_the_old_choice():
    texts = [o["text"] + " " + o["hint"] for o in PAGE]
    none = lambda i: None
    assert r.choice_plan(texts, "Burn", event=PAGE, want=none) == (r.pick_choice(texts, "Burn", event=PAGE), False)
    assert r.choice_plan(texts, "Burn", event=None, want=WANT) == (r.pick_choice(texts, "Burn"), False)


def test_pick_checker_lowest_takes_the_worst_odds_leftmost():
    captions = [("High", 216), ("Very Low", 286), ("Very Low", 355), ("Normal", 147)]
    assert r.pick_checker(captions, lowest=True) == 1
    assert r.pick_checker(captions, skip=(1,), lowest=True) == 2
    assert r.pick_checker([("??", 77)], lowest=True) is None


IDS = {"Gift": 9764, "Melted Spring": 9054, "Illusory Hunt": 9038, "Hellterfly's Dream": 9001, "Rusted Muzzle": 9089}


def test_a_card_s_title_is_its_topmost_line_with_the_boxes_on_it_joined_left_to_right():
    # BossGiftTrialsHard.png / GiftChoiceNoCount.png: the Owned label sits above the title, a long title may come as two boxes
    assert r.card_title([(152, "Owned"), (182, "Nebulizer"), (242, "0"), (281, "First Turn Start of an")]) == "Nebulizer"
    assert r.card_title([(176, "Illusory"), (180, "Hunt"), (301, "Focused Encounter Start:")]) == "Illusory Hunt"
    assert r.card_title([]) == ""


@pytest.mark.parametrize(("lines", "gift_id"), [
    ([(177, "Melted Spring"), (281, "Turn Start: enemies with")], 9054),
    ([(180, "Hellterfly's Dream"), (281, "When applyingBurn")], 9001),
    ([(176, "Illusory"), (180, "Hunt"), (301, "Focused Encounter Start:")], 9038),
    ([(152, "Owned"), (181, "Rusted Muzzle")], 9089),
    ([(181, "Rusted Muzle")], 9089),  # an OCR slip
    ([(181, "Gift"), (281, "Gain a Gift")], 9764),  # a card named Gift
    ([(181, "Rusted Muzzle"), (281, "Gift of the Rust Spring")], 9089),  # "gift" in the description: not 9764
    ([(181, "Frosted Gift Box"), (281, "Gift")], None),  # another gift's name that holds the word is no Gift
    ([(181, "Unheard Of"), (281, "Gift")], None),
    ([], None),
])
def test_a_card_is_the_gift_whose_whole_name_its_title_line_reads(lines, gift_id):
    assert r.card_gift(lines, IDS) == gift_id


def test_a_card_line_names_the_gift_its_category_scores_and_the_total():
    card = r.Card("main", 2, 0.465, "Melted Spring", 9054, "Defense Level Up +1 score 0.105")
    assert r.card_line(card) == "Melted Spring/main gift 3.5 tier II trial Defense Level Up +1 score 0.105 total 3.035"
    assert r.card_line(r.Card("other", None, None, "'Mystery'", None, None)) == "'Mystery'/other gift 2 total 2"
    assert r.rank_gifts([r.Card("other", None, None, "a", 1, None), r.Card("main", None, None, "b", 2, None)]) == [1, 0]
