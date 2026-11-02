"""#305: the main keyword is the first keyword of the team's gift list, and every path that reads it follows the list.

Each test plays a team whose list order starts with Bleed (run_team makes its team) and fails when the path reads Burn."""
import actions
import test_actions
from test_actions import Choices, FUSE_PAGE, cells_read, fuse_slots, gift_page, listed, live_shop, reads, shop_team, with_ids, wants

clock, context = test_actions.clock, test_actions.context  # its fixtures


def bleed_team(**extra):
    """The team a run plays: a list with Bleed first that wants Wound Clerid (9005, buyable) and keeps nothing else."""
    settings = listed("Bleed")
    settings["gift_lists"] = [{"id": "g", "name": "G", **wants(9005, order=("Bleed",))}]
    return {"reserve_cost": 0, "shop_refresh_keyword": 0, "shop_refresh_normal": 0, **extra, **actions.run_team(settings, settings["teams"][0])}


def test_the_keyword_refresh_picks_the_lists_first_keyword(context, clock):
    def reads_now(taps):
        cost = "410" if actions.KEYWORD_REFRESH in taps else "500"
        return {tuple(actions.SHOP_COST): [(cost, (560, 120, 60, 30))],
                tuple(actions.REFRESH["normal"][1]): [("100", (970, 145, 40, 20))],
                tuple(actions.REFRESH["keyword"][1]): [("90", (1110, 145, 40, 20))],
                tuple(actions.KEYWORD_LABELS): [("Bleed", (300, 400, 60, 20))]}  # the dialog lists no Burn here
    taps = live_shop(context, reads_now)
    visit = {"wanted": None, "sold": False, "refreshes": {"keyword": 0, "normal": 0}}
    assert actions.Shop.buy(context, bleed_team(shop_refresh_keyword=1), visit)
    assert taps == [actions.REFRESH["keyword"][0], (330, 360), actions.KEYWORD_REFRESH]


def test_the_fusion_page_picks_the_lists_first_keyword(context, monkeypatch):
    reads(context, {**FUSE_PAGE, tuple(actions.KEYWORD_LABELS): [("Bleed", (300, 400, 60, 20))],
                    tuple(actions.FUSE_CONFIRM): [("Selected E.G.O Gifts 3/3", (330, 175, 320, 30))],
                    tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]})
    fuse_slots(context, monkeypatch)
    cells_read(monkeypatch, *with_ids([("Pierce",), ("Slash",), ("Blunt",)]))
    assert actions.Shop.fuse(context, shop_team(bleed_team()), {})  # no Burn label: a Burn team finds no keyword dialog


def test_an_event_takes_the_option_that_gains_a_gift_of_the_lists_first_keyword(context, monkeypatch):
    actions.RUN["team"] = bleed_team()
    actions.RUN["settings"] = {"event_overrides": []}
    options = [("Left.", "Select to gain a Burn E.G.O Gift"), ("Right.", "Select to gain a Bleed E.G.O Gift")]
    page = Choices(context, monkeypatch, options, ["Unknown story."])
    actions.Event().run(context, None)
    assert page.tapped == ["Right."]


def test_the_gift_choice_takes_the_card_of_the_lists_first_keyword(context, monkeypatch):
    taps = gift_page(context, monkeypatch, ["Hellterfly's Dream", "Wound Clerid"])
    inner = actions.ocr

    def ocr(context, image, roi, only_rec=False):  # the first card says Burn, the second Bleed
        return [(t.replace("Inflict Bleed", "Inflict Burn") if b[0] < 400 else t, b) for t, b in inner(context, image, roi, only_rec)] \
            if roi == actions.GIFT_CARDS else inner(context, image, roi, only_rec)
    monkeypatch.setattr(actions, "ocr", ocr)
    actions.RUN["team"] = bleed_team()
    actions.PickGift().run(context, None)
    assert taps[0] == (536, 300)  # the second card's centre: its tab sits at x 500 + 150 - 114
