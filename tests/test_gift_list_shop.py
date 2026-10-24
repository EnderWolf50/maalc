"""#299: the shop fuses and sells by the team's gift list: only a gift the list lets go and whose icon is known is touched."""
import pytest

import actions
import test_actions
from test_actions import fusion_taps, sale_taps, wants

clock, context = test_actions.clock, test_actions.context  # its fixtures

# Wanted fusions and what they lock (#294): 9092 Coupled Oscillation (9031, 9091, 9165), 9212 The End of all Evil (a pack's
# exclusive: 9427, 9428), 9083 Lunar Memory (seven fragments 9105.. and three memories 9142..).
LOCKS = [(9092, (9031, 9091, 9165)), (9212, (9427, 9428)), (9083, (9105, 9110, 9142, 9147))]


def test_a_fusion_taps_only_the_drop_gifts_it_knows(context, monkeypatch):
    # One screenshot decides. The list wants 9009 and keeps 9053; the cell whose icon no candidate matched (id None) is kept
    # too. Three known drop gifts are left, whatever their badges: a Keywordless one joins (no special setting).
    fused, taps, ok = fusion_taps(context, monkeypatch, {"list": wants(9009, keep=[9053])}, ("Burn", 2, 9009),
                                  ("Burn", 3, 9053), ("Bleed", 2, None), ("Keywordless", 3), ("Tremor", 2), ("Pierce", 2))
    assert fused and ok and taps == [0, 0, 0, 1, 1, 1]


@pytest.mark.parametrize("tier, vestige_id", [(1, 9991), (2, 9992), (3, 9993), (4, 9994)])
def test_a_vestige_the_list_lets_go_is_fused(context, monkeypatch, tier, vestige_id):
    # A vestige I-IV is a drop gift in the default list: material like any other, told by its id.
    fused, taps, _ = fusion_taps(context, monkeypatch, {}, ("Keywordless", tier, vestige_id), ("Tremor", tier), ("Pierce", tier))
    assert fused and taps == [1, 1, 1]


def test_a_lunar_vestige_is_never_fused(context, monkeypatch):
    # A tier V is never a material (MAX_MATERIAL_TIER), though the list lets it go.
    fused, taps, ok = fusion_taps(context, monkeypatch, {}, ("Keywordless", 5, 9995), ("Tremor",), ("Pierce",))
    assert not fused and not ok and taps == [0, 0, 0]


def test_a_vestige_the_list_keeps_is_not_fused(context, monkeypatch):
    fused, taps, _ = fusion_taps(context, monkeypatch, {"list": wants(keep=[9991])}, ("Keywordless", 1, 9991),
                                 ("Tremor", 1), ("Pierce", 1), ("Sinking", 1))
    assert fused and taps == [0, 1, 1, 1]  # kept, it would be the first of four tier I


@pytest.mark.parametrize("wanted, locked", LOCKS)
def test_the_materials_of_a_wanted_fusion_are_locked_for_fusing(context, monkeypatch, wanted, locked):
    # A pack's exclusive recipe locks all the same, the run's pack being unknown (#306 unlocks it by the run's pack).
    fused, taps, _ = fusion_taps(context, monkeypatch, {"list": wants(wanted)}, *[("Burn", 2, i) for i in locked],
                                 ("Tremor",), ("Pierce",), ("Sinking",))
    assert fused and taps == [0] * len(locked) + [1, 1, 1]


def test_a_gift_nothing_locks_is_fused_though_a_fusion_is_wanted(context, monkeypatch):
    fused, taps, _ = fusion_taps(context, monkeypatch, {"list": wants(9092)}, ("Burn", 2, 9003), ("Tremor",), ("Pierce",))
    assert fused and taps == [1, 1, 1]


def test_keywordless_and_other_keyword_gifts_join_the_highest_tier_pick(context, monkeypatch):
    # No keyword is kept by the team any more: the list alone decides. Tremor III + Pierce III + Sinking I would make a III;
    # with the keywordless III, a IV.
    fused, taps, _ = fusion_taps(context, monkeypatch, {}, ("Keywordless", 3), ("Tremor", 3), ("Pierce", 3), ("Sinking", 1))
    assert fused and taps == [1, 1, 1, 0]


def test_a_sale_reads_ids_and_prices_off_the_grid_and_taps_only_what_it_sells(context, monkeypatch):
    # No gift is tapped to read its panel. The list wants 9009 and keeps 9053; the cell with no id is kept too. Tremor III +
    # Pierce III + Sinking II fuse into a tier IV (#79); the Bleed I no fusion uses goes, though Tremor's price is higher.
    taps = sale_taps(context, monkeypatch, {"list": wants(9009, keep=[9053])}, [90, 300, 200, 250, 120, 60, 80],
                     ("Bleed", 1), ("Burn", 2, 9009), ("Burn", 3, 9053), ("Keywordless", 3, None),
                     ("Tremor", 3), ("Pierce", 3), ("Sinking", 2))
    assert taps == [actions.SELL_CELLS[0]]


@pytest.mark.parametrize("list_, gift", [
    (wants(9003), 9003), (wants(keep=[9003]), 9003),
    (wants(9092), 9031), (wants(9212), 9427), (wants(9083), 9105),
], ids=["wanted", "kept", "locked by a fixed recipe", "locked by a pack's exclusive recipe", "locked by Lunar Memory"])
def test_a_sale_never_sells_what_the_list_wants_keeps_or_locks(context, monkeypatch, list_, gift):
    # The dearest gift (400) would cover the price, and no fusion would use it (the others are 3 of a kind): it stays.
    taps = sale_taps(context, monkeypatch, {"list": list_}, [400, 90, 60, 70, 80], ("Bleed", 1, gift),
                     ("Bleed",), ("Tremor",), ("Pierce",), ("Sinking",))
    assert taps == [actions.SELL_CELLS[4]]  # of the 4 drop gifts, 3 fuse and the one left over goes


def test_a_gift_nothing_recognises_is_not_sold(context, monkeypatch):
    # No id (the icon matched no candidate): kept, though it is the dearest and no fusion would use it.
    taps = sale_taps(context, monkeypatch, {}, [400, 90, 60, 70, 80], ("Bleed", 1, None), ("Bleed",), ("Tremor",),
                     ("Pierce",), ("Sinking",))
    assert taps == [actions.SELL_CELLS[4]]


def test_a_keywordless_drop_gift_is_sold_like_any_other(context, monkeypatch):
    # No keywordless setting any more: only the list says. A Keywordless leftover that the list lets go goes.
    taps = sale_taps(context, monkeypatch, {}, [90, 60, 70, 95], ("Bleed",), ("Tremor",), ("Pierce",), ("Keywordless", 2))
    assert taps == [actions.SELL_CELLS[3]]


def test_a_vestige_the_list_keeps_is_not_sold_though_the_team_sells_vestiges(context, monkeypatch):
    taps = sale_taps(context, monkeypatch, {"sell_vestiges": True, "list": wants(keep=[9991])}, [90, 60, 70, 95],
                     ("Bleed",), ("Tremor",), ("Pierce",), ("Keywordless", 1, 9991))
    assert taps == []


def test_the_cells_of_the_sell_and_fuse_pages_are_logged_with_their_state_in_the_list(context, monkeypatch):
    # #291 user story 68: each cell's id and what the list makes of it: wanted, kept, locked by a wanted fusion, dropped, unknown.
    lines = []
    monkeypatch.setattr(actions, "log", lines.append)
    readings = [("Burn", 2, 9009), ("Burn", 3, 9053), ("Tremor", 2, 9031), ("Bleed", 2, 9005), ("Pierce", 2, None)]
    team = {"list": wants(9009, 9092, keep=[9053])}
    sale_taps(context, monkeypatch, team, [90, 80, 70, 60, 50], *readings)
    fusion_taps(context, monkeypatch, team, *readings)
    for page in ("sell cells", "fuse cells"):
        (line,) = [m for m in lines if f"shop: {page}" in m]
        for text in ("9009 Fiery Down (0.90): keep, want", "9053 Dust to Dust (0.90): keep, keep",
                     "(0.90): keep, locked", "9005 Wound Clerid (0.90): material, drop", "(best 0.90): keep, unknown"):
            assert text in line, (page, text, line)


def exclusive_team(*, keep=()):
    """A team that wants Hoarfrost Footprint (9410, exclusive to packs 1004 and 1005; materials 9408, 9409), nothing else."""
    return test_actions.shop_team({"list": wants(9410, keep=keep)})


@pytest.mark.parametrize("packs, role", [
    ([], "material"),  # a new run, nothing taken yet
    ([1011], "material"),  # other packs only
    ([1011, 1005], "keep"),  # one of the fusion's packs was taken
    (None, "keep"),  # unknown (the agent restarted): locked all the same
])
def test_an_exclusive_recipes_material_is_locked_only_by_the_packs_the_run_took(packs, role):
    # #306: lockers' run_packs comes from the run.
    if packs is not None:
        actions.RUN["packs"] = packs
    team = exclusive_team()
    for page_name in ("sell", "fuse"):
        assert actions.cell_role({"id": 9408}, team, page_name, ()) == role
    assert actions.cell_state({"id": 9408}, team["list"]) == ("locked" if role == "keep" else "drop")


@pytest.mark.parametrize("packs, sold", [([], True), ([1004], False)])
def test_a_sale_spares_an_exclusive_recipes_material_only_in_a_run_that_took_its_pack(context, monkeypatch, packs, sold):
    # #306: the tier II material 9408 is priced 300 on a 180 wanted: sold when the run took no pack of 9410, spared when it did.
    actions.RUN["packs"] = packs
    taps = sale_taps(context, monkeypatch, {"list": wants(9410)}, [300], ("Sinking", 2, 9408))
    assert taps == ([actions.SELL_CELLS[0]] if sold else [])
