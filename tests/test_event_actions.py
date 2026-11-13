"""The encounter page actions (agent/event_actions.py): the event and its choices, the reward cards, and the gift choice."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

import actions
import event_actions
import map_actions
import shop_actions
import gifts
from agent_patch import patch_all
import test_actions

from test_actions import Choices, DOLL, REAL_GUARD, SCROLLED, TABLE, argv, button_taps, check_page, corner_taps, event_portrait_taps, event_text, gift_page, moved, page_until, picked, reads, shop_team, taps, wants

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def test_event_text_is_tapped_through_until_the_choices_show(context):
    # The user's tip: taps on a dead corner run the text on; stop once there is something to pick.
    shots = []

    def screencap():
        shots.append(1)
        return np.full((720, 1280, 3), len(shots), np.uint8)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = screencap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        if roi == tuple(event_actions.CHOICES_HEADER) and image[0, 0, 0] >= 4:
            return SimpleNamespace(all_results=[SimpleNamespace(text="Choices", box=(700, 110, 100, 30))])
        if roi == tuple(event_actions.EVENT_BUTTON_LABEL):  # the grey button
            return SimpleNamespace(all_results=[SimpleNamespace(text="Continue", box=(1065, 625, 140, 40))])
        return None
    context.run_recognition.side_effect = run_recognition
    event_actions.Event().run(context, None)
    corner = [c for c in context.tasker.controller.post_click.call_args_list if c.args == event_actions.EVENT_NEUTRAL]
    assert len(corner) == 3


def test_event_text_is_tapped_every_0_15_s_and_read_every_third_tap(context, clock):
    # Live 2026-10-20: a screenshot and 3 OCRs after each tap made it one every 0.3-1.1 s, whatever its wait; the
    # text keeps up with a tap every 0.15 s (the user by hand; no tap lost live). The Choices show after tap 4.
    reads = event_text(context, choices_from=6)
    event_actions.Event().run(context, None)
    assert len(corner_taps(context)) == 6  # read at taps 3 and 6
    assert reads.count(tuple(event_actions.EVENT_BUTTON_LABEL)) == 2
    assert sum(clock) == pytest.approx(0.2 + 5 * event_actions.EVENT_TAP_EVERY)  # still()'s second look, then the 5 gaps


def test_the_text_is_tapped_on_right_after_the_lit_button(context, clock):
    # The user (#188): after the red button the taps paused ~1.6-5.3 s (live 2026-10-20: a 0.5 s settle, then
    # MirrorHub's 200 ms delays and its look). Now the corner taps go on at the same 0.15 s in the same call;
    # the button still lit while its press fades out is no button to press again.
    event_text(context, red_from=1, red_to=3, choices_from=7)
    event_actions.Event().run(context, None)
    clicks = context.tasker.controller.post_click.call_args_list
    assert clicks[0].args == event_actions.EVENT_BUTTON and len(button_taps(context)) == 1
    assert len(corner_taps(context)) == 6  # 2 while it fades, read at once on the first unlit screen, then every third
    waits = [s for s in clock if s][1:]  # tap(wait=0) sleeps 0; the first is still()'s, before the press
    assert waits[0] == pytest.approx(event_actions.EVENT_TAP_EVERY) and max(waits) <= event_actions.EVENT_TAP_EVERY


def test_no_corner_tap_once_the_lit_button_left_the_event(context, clock):
    # The last Continue ends the event: the first screen without the lit button is read before another tap.
    event_text(context, red_from=1, red_to=3, label_to=3)
    event_actions.Event().run(context, None)
    assert len(corner_taps(context)) == 2  # both on the fading event page


@pytest.mark.parametrize("label_to, misread", [
    (3, ()),  # read empty mid-fade
    (1, ()),  # read empty before the press
    (float("inf"), (1,)),  # read in part before the press
    (3, (2,)),  # read in part mid-fade
])
def test_a_label_not_read_whole_while_it_fades_is_no_other_button(context, clock, label_to, misread):
    # Handed back, MirrorHub's Event node would still match the fading button and press it again.
    event_text(context, red_from=1, red_to=5, label_to=label_to, misread=misread)
    event_actions.Event().run(context, None)
    assert len(button_taps(context)) == 1 and len(corner_taps(context)) >= 4  # on through the fade's 3 lit screens


def test_a_press_that_did_not_take_is_handed_back_to_be_pressed_again(context, clock):
    # The button lit on for EVENT_TAKE s: the press was lost, MirrorHub presses it again. Counted in time, not taps:
    # a label OCR a lit screen (0.2 s here) slows the taps.
    event_text(context, red_from=1)
    inner = context.run_recognition.side_effect
    context.run_recognition.side_effect = lambda *a, **k: actions.time.sleep(0.2) or inner(*a, **k)
    event_actions.Event().run(context, None)
    assert len(button_taps(context)) == 1 and len(corner_taps(context)) == math.ceil(event_actions.EVENT_TAKE / 0.2)


GOSSYPIUM = "White Gossypium"


def test_a_team_without_white_gossypium_picks_another_gift(context, monkeypatch):
    taps = gift_page(context, monkeypatch, [GOSSYPIUM, "Wound Clerid"])
    event_actions.PickGift().run(context, None)
    assert [t for t in taps if t[1] == 300] == [(536, 300)]  # the second card only


def test_a_wanted_gift_is_taken_over_a_main_keyword_card(context, monkeypatch):
    # #419: a normal page, no trials: Rusted Muzzle wanted (6) over Wound Clerid (main, 3), though Clerid is leftmost
    taps = gift_page(context, monkeypatch, ["Wound Clerid", "Rusted Muzzle"])
    actions.RUN["team"]["list"] = wants(9089)
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [536]


def test_a_page_without_wants_takes_the_leftmost_of_equal_cards(context, monkeypatch):
    taps = gift_page(context, monkeypatch, ["Wound Clerid", "Rusted Muzzle"])
    actions.RUN["team"]["list"] = wants()
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [236]


def test_two_want_cards_on_a_page_that_takes_two_are_both_taken(context, monkeypatch):
    # #416 story 9: Select 0/2 with the main card leftmost
    taps = gift_page(context, monkeypatch, ["Wound Clerid", "Rusted Muzzle", "Gift"], slots=2)
    actions.RUN["team"]["list"] = wants(9089, 9764)
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [536, 836]


def test_a_pack_exclusive_material_is_taken_over_a_plain_want(context, monkeypatch):
    # #419: Oil-gunked Spanner (pack 1102's own pool, a material of the Violin the default list makes) 9 over Gift (6)
    taps = gift_page(context, monkeypatch, ["Gift", "Oil-gunked Spanner"])
    actions.RUN["team"]["list"] = gifts.default_list()
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [536]


def left_shop_holding(context, monkeypatch, owned):
    """A shop visit that read `owned` on its pages and was left by hand, then the next node entered: the flow that ends RUN["shop"]."""
    actions.RUN["team"] = shop_team({"heal": "none", "list": gifts.default_list()})
    monkeypatch.setattr(shop_actions.Shop, "to_main", staticmethod(lambda context: True))
    monkeypatch.setattr(shop_actions.Shop, "sell", staticmethod(lambda *a: False))
    handed_over = actions.page_guard
    patch_all(monkeypatch, "page_guard", REAL_GUARD)

    def buy(context, team, visit):
        visit["owned"] = list(owned)
        actions.page_guard(context, "Shop")
    monkeypatch.setattr(shop_actions.Shop, "buy", staticmethod(buy))
    assert shop_actions.Shop().run(context, argv())
    map_actions.enter_node(context)
    assert "shop" not in actions.RUN
    patch_all(monkeypatch, "page_guard", handed_over)


def test_a_material_of_a_fusion_made_in_the_shop_scores_as_a_main_card_on_the_next_gift_page(context, monkeypatch):
    # #419: the Violin (9249) was made in the shop; on the gift page after it the Spanner is a main card like Wound
    # Clerid (leftmost), not a 9. RUN["shop"] is gone by then (#118), so the run must remember what the shop held.
    left_shop_holding(context, monkeypatch, [9249])
    taps = gift_page(context, monkeypatch, ["Wound Clerid", "Oil-gunked Spanner"])
    actions.RUN["team"]["list"] = gifts.default_list()
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [236]


def test_a_gift_taken_on_a_gift_page_is_held_for_the_next_one(context, monkeypatch):
    # #416: the Violin (9249) taken from a page; a page after it ranks the Spanner (its material) as a main card
    taps = gift_page(context, monkeypatch, ["A Small, Lovely Violin"])
    actions.RUN["team"]["list"] = gifts.default_list()
    event_actions.PickGift().run(context, None)
    taps = gift_page(context, monkeypatch, ["Wound Clerid", "Oil-gunked Spanner"])
    actions.RUN["team"]["list"] = gifts.default_list()
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [236]


def test_a_wanted_gift_the_team_avoids_is_still_taken_last(context, monkeypatch):
    # #90: White Gossypium is on the list as a want; with the team not holding it, the other card goes first
    taps = gift_page(context, monkeypatch, [GOSSYPIUM, "Rusted Muzzle"])
    actions.RUN["team"]["list"] = wants(9020)
    event_actions.PickGift().run(context, None)
    assert picked(taps) == [536]


def test_a_team_without_white_gossypium_takes_it_when_it_is_the_only_card(context, monkeypatch):
    # #90 (the user, 2026-10-18): taken rather than a random trial for the choice left; the shop then
    # fuses or sells it first (test_a_team_without_white_gossypium_fuses_it_first).
    taps = gift_page(context, monkeypatch, [GOSSYPIUM])
    event_actions.PickGift().run(context, None)
    assert taps == [(236, 300), event_actions.GIFT_SELECT]
    assert actions.STUCK["flag"] is None


def test_a_check_with_no_odds_read_taps_no_sinner_and_hands_back(context):
    # #380: the prompt shows before the odds are drawn; the first sinner was taken blind, the right one read 1.8 s later.
    check_page(context, [(x, "") for x in event_actions.EVENT_PORTRAIT_X])
    assert event_actions.Event().run(context, None) is True
    actions.time.sleep(event_actions.EVENT_ODDS_WAIT - 0.5)
    assert event_actions.Event().run(context, None) is True  # still inside the wait
    assert event_portrait_taps(context) == []


def test_a_check_with_no_odds_read_tries_the_next_sinner_when_a_tap_did_nothing(context):
    # #92: with no odds read it was always the first sinner; when she cannot be picked it never ended.
    # #380: only once the odds are 2 s late; the prompt's first look just hands back.
    check_page(context)
    event_actions.Event().run(context, None)
    actions.time.sleep(event_actions.EVENT_ODDS_WAIT)
    for _ in range(3):
        event_actions.Event().run(context, None)  # the screen never changes: each tap did nothing
    assert event_portrait_taps(context) == event_actions.EVENT_PORTRAIT_X[:3]


def test_a_check_with_some_odds_read_still_takes_the_best_of_them(context):
    check_page(context, [(event_actions.EVENT_PORTRAIT_X[3], "Very High")])
    event_actions.Event().run(context, None)
    assert event_portrait_taps(context) == [event_actions.EVENT_PORTRAIT_X[3]]


def test_a_check_with_odds_read_takes_the_next_best_when_a_tap_did_nothing(context):
    check_page(context, [(event_actions.EVENT_PORTRAIT_X[0], "Low"), (event_actions.EVENT_PORTRAIT_X[2], "Very High"), (event_actions.EVENT_PORTRAIT_X[4], "High")])
    for _ in range(3):
        event_actions.Event().run(context, None)
    assert event_portrait_taps(context) == [event_actions.EVENT_PORTRAIT_X[i] for i in (2, 4, 0)]


def test_a_check_tap_that_took_is_not_held_against_the_sinner(context):
    check_page(context, [(event_actions.EVENT_PORTRAIT_X[0], "High")])
    ctl = context.tasker.controller
    ctl.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: np.full((720, 1280, 3), 9 if ctl.post_click.called else 0, np.uint8)
    event_actions.Event().run(context, None)
    event_actions.Event().run(context, None)
    assert event_portrait_taps(context) == [event_actions.EVENT_PORTRAIT_X[0]] * 2


def event_for(context, seconds):
    """Run Event once a second on a page it cannot read, for `seconds` or until it hands over to recovery."""
    for _ in range(seconds):
        event_actions.Event().run(context, None)
        if actions.STUCK["flag"]:
            return
        actions.time.sleep(1)


def test_one_event_that_goes_on_past_its_limit_goes_to_recovery(context):
    event_for(context, event_actions.EVENT_LIMIT + 60)
    flag = actions.STUCK["flag"]
    assert flag and flag[1] == 1 and "event" in flag[2]
    assert actions.RUN.get("event") is None  # recovery's next look starts a new clock


def test_an_event_after_a_pause_starts_its_own_clock(context):
    # Each event alone stays under the limit (a call taps the text for up to 0.3 s on top of event_for's 1 s);
    # together they would not.
    event_for(context, event_actions.EVENT_LIMIT // 2 + 30)
    actions.time.sleep(event_actions.EVENT_LIMIT)  # the event ended; the next one comes later
    event_for(context, event_actions.EVENT_LIMIT // 2 + 30)
    assert actions.STUCK["flag"] is None


def test_an_event_in_the_table_takes_a_direct_gift_over_a_check_for_the_main_keyword(context, monkeypatch):
    # 901013 for a Poise team: the hint rules took the check that may give Poise; the table ranks the sure gift first.
    actions.RUN["team"] = {"keyword": "Poise"}
    actions.RUN["settings"] = {"event_overrides": []}
    page = Choices(context, monkeypatch, [
        ("Remove the doll's talismans.", "Select to gain a Rupture E.G.O Gift"),
        ("Remove the wall talismans.", "Sloth & Wrath Advantage check. Then, maybe gain a Poise E.G.O Gift depending on the subsequent choice")],
        DOLL)
    event_actions.Event().run(context, None)
    assert page.tapped == ["Remove the doll's talismans."]
    assert page.drags == []  # two options fit: no scrolling


@pytest.mark.parametrize("best", [0, 2, 4])
def test_a_list_that_scrolls_is_read_whole_and_the_pick_scrolled_into_view(context, monkeypatch, best):
    # #93: more options than fit: read top to bottom anchored on their texts, the pick tapped whole in view.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = list(SCROLLED)
    options[best] = (f"Option {best}.", "Select to gain a Burn E.G.O Gift")
    table = [{"key": TABLE[0]["key"], "options": [{"text": t, "hint": h, "kind": "direct" if h else "other",
                                                   "gifts": [["Burn", "direct"]] if h else []} for t, h in options]}]
    patch_all(monkeypatch, "event_table", lambda: table)
    page = Choices(context, monkeypatch, options, DOLL, offset=100)  # left part way down
    event_actions.Event().run(context, None)
    assert page.tapped == [f"Option {best}."]


def test_the_card_a_drag_lights_is_read_and_taken(context, monkeypatch):
    # #196: four options, three in view. The drags light East on every screen it shows whole on; it was never read.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = [("North.", ""), ("East.", "Select to gain a Burn E.G.O Gift"), ("West.", ""), ("Turn back.", "")]
    page = Choices(context, monkeypatch, options, ["Unknown story."])
    event_actions.Event().run(context, None)
    assert page.tapped == ["East."]


def test_into_view_drags_on_past_options_it_did_not_read(context, monkeypatch):
    # #196: the one card whole on screen is an option the read missed; it dragged no further and gave up.
    page = Choices(context, monkeypatch, [(f"Option {k}.", "") for k in range(4)], offset=70)  # only Option 1 whole
    options = [(f"Option {k}.", True, 0) for k in (0, 2, 3)]
    y, _ = event_actions.Event.into_view(context, page.render(), options, 0)
    assert y is not None and page.tops()[0] < y < page.tops()[0] + 130


def test_into_view_gives_up_at_the_end_the_pick_lies_beyond(context, monkeypatch):
    # The options on screen put the pick above them: the top of the list ends the search, no turn back down.
    page = Choices(context, monkeypatch, [(f"Option {k}.", "") for k in range(4)], offset=236)  # at the bottom
    options = [("Gone.", True, 0)] + [(f"Option {k}.", True, 0) for k in range(4)]
    y, _ = event_actions.Event.into_view(context, page.render(), options, 0)
    assert y is None and page.drags == [150, 150, 150]  # two to the top, one that does not move


def test_an_option_cut_off_with_no_scrollbar_still_scrolls(context, monkeypatch):
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    options = [("Option 0.", ""), ("Option 1.", ""), ("Option 2.", "Select to gain a Burn E.G.O Gift")]
    page = Choices(context, monkeypatch, options, ["Unknown story."], scrollbar=False)
    event_actions.Event().run(context, None)
    assert page.tapped == ["Option 2."]  # the hint rules, on the option read once scrolled


def test_event_text_taps_stop_once_the_event_is_gone(context, guarded):
    # The text tapped on at a dead corner (up to 30 taps); the event page went away after the first. The page is
    # looked at with its text, every EVENT_READ_EVERY taps (#174: one OCR a tap undid the 0.15 s): the taps in
    # between land on the dead corner, which takes none.
    reads(context, {tuple(event_actions.EVENT_BUTTON_LABEL): [("Continue", (1065, 625, 140, 40))]})
    page_until(context, "Event", 1)
    assert event_actions.Event().run(context, None)
    assert len(taps(context)) == event_actions.EVENT_READ_EVERY
    assert actions.STUCK["flag"] is None


def test_a_gift_choice_gone_is_handed_back_untouched(context, guarded):
    actions.RUN["team"] = {"keyword": "Burn", "list": wants(9001)}
    actions.RUN["settings"] = {"trial_risk_overrides": []}
    reads(context, {tuple(event_actions.GIFT_CARDS): [("Acquire E.G.O Gift", (300, 160, 150, 30)), ("Hellterfly's Dream", (200, 250, 150, 30))]})
    assert event_actions.PickGift().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_an_event_gone_is_not_scrolled(context, guarded):
    with pytest.raises(actions.PageGone):
        event_actions.Event.drag(context, np.zeros((720, 1280, 3), np.uint8), event_actions.CHOICE_STEP)
    assert moved(context) == 0


def test_reward_cards_gone_after_one_card_are_handed_back(context, guarded):
    # A title check alone reads through a popup: the guard takes the page, and the page goes after a card.
    actions.RUN["team"] = {"reward_cards": ["Starlight"]}
    reads(context, {tuple(event_actions.REWARD_TITLE): [("Encounter Reward", (300, 120, 200, 30))],
                    tuple(event_actions.SELECTABLE): [("Selectable 0/1", (890, 120, 150, 30))],
                    tuple(event_actions.CARD_TEXT): [("Gain 8~10 Starlight", (200, 360, 200, 30)), ("Gain 100 Cost", (600, 360, 200, 30))]})
    page_until(context, "RewardCard", 1)
    assert event_actions.RewardCard().run(context, argv())
    assert len(taps(context)) == 1 and event_actions.CARD_CONFIRM not in taps(context)
    assert actions.STUCK["flag"] is None


def test_a_gift_choice_gone_after_one_card_does_not_press_select(context, guarded):
    actions.RUN["team"] = {"keyword": "Burn", "list": wants(9001)}
    actions.RUN["settings"] = {"trial_risk_overrides": []}
    reads(context, {tuple(event_actions.GIFT_CARDS): [("Acquire E.G.O Gift", (300, 160, 150, 30)), ("Hellterfly's Dream", (200, 250, 150, 30)),
                                                ("Acquire E.G.O Gift", (700, 160, 150, 30)), ("Ashes to Ashes", (600, 250, 150, 30))]})
    page_until(context, "GiftChoice", 1)
    assert event_actions.PickGift().run(context, argv())
    assert len(taps(context)) == 1 and event_actions.GIFT_SELECT not in taps(context)
