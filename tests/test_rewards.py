import json
import struct
import zlib
from pathlib import Path

import numpy as np
import yaml

import rewards as r

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
SCREENS = Path(__file__).resolve().parent / "screens"

ORDER = ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"]
RISKS = {"Defense Level Up": 1, "Growth I": 3, "Offense Level Up I": 2, "Offense Level Up II": 4}


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


RANKED = [  # the user's order (#93), best last; on screen as "<text> <hint>"
    opt("Leave.", "", "other"),
    opt("Read it.", "Run a Wrath check to gain an E.G.O Gift.", "check_fail_gift", ("Burn", "check_fail")),
    opt("Fight.", "Win the battle to earn a Burn E.G.O Gift", "battle", ("Burn", "win_battle")),
    opt("Wait.", "Then, maybe gain a Burn E.G.O Gift depending on the subsequent choice", "followup", ("Burn", "later_direct")),
    opt("Open it.", "Lust check. Pass to gain a Burn E.G.O Gift.", "check", ("Burn", "check_pass")),
    opt("Insert the coin.", "???", "random", ("Keywordless", "direct_random")),
    opt("Take it.", "Select to gain a Bleed E.G.O Gift", "direct", ("Bleed", "direct")),
    opt("Hold it.", "Select to gain a Burn E.G.O Gift", "direct", ("Burn", "direct")),
]


def shown(event):
    return [f"{o['text']} {o['hint']}" for o in event]


def test_pick_choice_ranks_by_the_event_table():
    # direct main > direct other > ??? / random > check pass > follow-up page > win battle > the rest
    options = shown(RANKED)
    for best in range(len(RANKED) - 1, 1, -1):
        assert r.pick_choice(options, "Burn", closed=range(best + 1, len(RANKED)), event=RANKED) == best
    # a gift only when a check fails is no gain: the first of the rest
    assert r.pick_choice(options, "Burn", closed=range(2, len(RANKED)), event=RANKED) == 0
    assert r.pick_choice(options, "Bleed", event=RANKED) == 6  # the direct Bleed gift is the main one now
    assert r.pick_choice(options, "Burn", "Leave", event=RANKED) == 0  # an override still wins


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
    assert r.pick_choice(["Stay.", "Grab it. Win the battle to earn a Burn E.G.O Gift"], "Burn", event=event) == 1
    assert r.pick_choice(["Fight. Win the battle to earn a Burn E.G.O Gift", "Grab it. Select to gain a Bleed E.G.O Gift",
                          "Coin. ???"], "Burn", event=event) == 1


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


def test_trial_risk_unknown_is_max():
    assert r.trial_risk("Defense Level Up", RISKS) == 1
    assert r.trial_risk("Offense Level Up II", RISKS) == 4
    assert r.trial_risk("Resilient I", RISKS) == r.MAX_RISK
    assert r.trial_risk("Growth II", RISKS) == r.MAX_RISK  # not Growth I's risk
    assert r.trial_risk("Defense Leve1 Up", RISKS) == 1  # OCR slips still match


def test_rank_gifts_without_trials():
    assert r.rank_gifts([("other", None), ("main", None), ("owned", None), ("main", None)], "high") == [1, 3, 0, 2]


def test_rank_gifts_with_trials():
    # score = gift - weight x risk; high weight 2: main/1 -> 1, other/0 -> 2, main/3 -> -3, other/5 -> -8
    cards = [("main", 1), ("other", 0), ("main", 3), ("other", 5)]
    assert r.rank_gifts(cards, "high") == [1, 0, 2, 3]
    # low weight 0.5: main/1 -> 2.5, other/0 -> 2, main/3 -> 1.5
    assert r.rank_gifts(cards, "low")[:3] == [0, 1, 2]
    # equal scores: the lower risk first (medium: main/1 -> 2, other/0 -> 2)
    assert r.rank_gifts([("main", 1), ("other", 0)], "medium") == [1, 0]


class GiftPage:
    """Select n/m over the gift cards: a tap picks a card, or drops it when picked; full, a tap does nothing."""

    def __init__(self, picks, unread=0):
        self.picks, self.unread = picks, unread  # unread: count reads that come back empty first
        self.picked, self.taps = [], []

    def read(self):
        if self.unread:
            self.unread -= 1
            return None
        return len(self.picked), self.picks

    def tap(self, i):
        self.taps.append(i)
        if i in self.picked:
            self.picked.remove(i)
        elif len(self.picked) < self.picks:
            self.picked.append(i)


def test_pick_gifts_taps_every_card_when_the_count_never_reads():
    page = GiftPage(picks=2, unread=99)  # #81: hard boss, Select 0/2 not read
    r.pick_gifts([1, 0], page.read, page.tap)
    assert sorted(page.picked) == [0, 1]


def test_pick_gifts_stops_at_the_count_once_it_reads():
    page = GiftPage(picks=1, unread=1)  # the first read misses, the second reads Select 0/1
    r.pick_gifts([2, 0, 1], page.read, page.tap)
    assert page.taps == [2]
    page = GiftPage(picks=1, unread=2)  # unread until the first card is in: Select 1/1
    r.pick_gifts([2, 0, 1], page.read, page.tap)
    assert page.taps == [2]


def test_pick_gifts_a_lone_card_is_tapped_once():
    page = GiftPage(picks=1, unread=99)  # one card shows no count
    r.pick_gifts([0], page.read, page.tap)
    assert page.taps == [0]


def test_pick_gifts_repicks_a_card_the_tap_dropped():
    page = GiftPage(picks=2)
    page.picked = [1]  # left picked by the last try, Select 1/2
    r.pick_gifts([1, 0, 2], page.read, page.tap)
    assert sorted(page.picked) == [0, 1]


def test_data_files():
    risks = yaml.safe_load((DATA / "trial_risks.yaml").read_text(encoding="utf-8"))
    assert risks and all(isinstance(v, int) and 0 <= v <= r.MAX_RISK for v in risks.values())
    assert yaml.safe_load((DATA / "events.yaml").read_text(encoding="utf-8")) == {}
    events = json.loads((DATA / "event_table.json").read_text(encoding="utf-8"))
    assert events["client"] == "1.117.0" and "Project Moon" in events["note"]
    nails = next(e for e in events["events"] if e["id"] == 901008)["options"][0]  # Grimy Iron Stake is a Bleed gift
    assert (nails["text"], nails["kind"], nails["gifts"]) == ("Remove the nails.", "check", [["Bleed", "check_pass"]])
