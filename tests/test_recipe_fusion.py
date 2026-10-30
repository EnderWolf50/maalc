"""#300: a wanted fusion whose recipe the owned gifts hold is made by recipe before any ordinary fusion."""
import actions
import test_actions
from test_actions import fusion_taps, wants

clock, context = test_actions.clock, test_actions.context  # its fixtures

SOOTHE = 9088  # Burn IV: [9003, 9053, 9157] or [9003, 9053, 9101, 9155]
RUPTURE = 9248  # [9419, 9424] or [9419, 9119, 9423]
LUNAR = 9083  # 2 of [9105, 9110, ...] and 3 of [9142, 9147, 9152]


def team(*wanted):
    return {"list": wants(*wanted)}


def junk(n):
    return [("Bleed", 2)] * n  # gifts the list drops: an ordinary fusion's materials


def test_a_wanted_fixed_recipe_with_its_materials_owned_is_fused_by_putting_exactly_them_in(context, monkeypatch):
    # junk(3) would make an ordinary fusion too; the recipe goes first and is the only one this call makes.
    readings = [*junk(3), ("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *readings)
    assert fused and ok and taps == [0, 0, 0, 1, 1, 1]


def test_the_recipe_that_is_complete_is_the_one_put_in(context, monkeypatch):
    # RUPTURE's first recipe lacks 9424; the second is complete.
    readings = [("Rupture", 2, 9419), ("Rupture", 2, 9119), ("Rupture", 2, 9423), ("Rupture", 2, 9488)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(RUPTURE), *readings)
    assert fused and ok and taps == [1, 1, 1, 0]


def test_lunar_memory_takes_the_first_two_shards_of_the_data_file_and_three_memories(context, monkeypatch):
    # Owned in an order other than the data file's: 9116 comes before 9110 in the grid but 9110 first in the file.
    readings = [("Burn", 4, 9116), ("Burn", 4, 9142), ("Burn", 4, 9110), ("Burn", 4, 9105), ("Burn", 4, 9147), ("Burn", 4, 9152)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(LUNAR), *readings, slots=5, confirm=5)
    assert fused and ok and taps == [0, 1, 1, 1, 1, 1]  # 9105 and 9110, not 9116


def test_materials_that_fall_short_make_no_recipe_and_the_ordinary_fusion_goes_on(context, monkeypatch):
    # 9157 missing: the two owned materials are locked by the wanted fusion (not tapped), three junk gifts fuse as before.
    readings = [("Burn", 3, 9003), ("Burn", 3, 9053), *junk(3)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *readings)
    assert fused and ok and taps == [0, 0, 1, 1, 1]


def test_a_recipe_the_page_cannot_hold_does_not_block_the_next_wanted_one(context, monkeypatch):
    # Lunar Memory (first in the list's order) takes 5 materials, a 3-slot fuse page holds three: Soothe the Dead goes in.
    readings = [("Burn", 4, i) for i in (9105, 9110, 9142, 9147, 9152)] + [("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157)]
    lunar_first = {"list": wants(LUNAR, SOOTHE, order=("Keywordless", "Burn"))}
    fused, taps, ok = fusion_taps(context, monkeypatch, lunar_first, *readings)
    assert fused and ok and taps == [0] * 5 + [1, 1, 1]


def test_a_recipe_the_dialog_counts_wrong_is_not_confirmed(context, monkeypatch):
    readings = [("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *readings, confirm=2)
    assert ok and not fused


def test_a_made_recipe_leaves_the_owned_gifts_to_be_read_again(context, monkeypatch):
    # The grid changed: the next call reads it again (visit["fuse_scanned"] stays False) and may make the next recipe.
    visit = {}
    test_actions.reads(context, {**test_actions.FUSE_PAGE, tuple(actions.FUSE_CONFIRM): [("Selected E.G.O Gifts 3/3", (330, 175, 320, 30))],
                                 tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]})
    test_actions.fuse_slots(context, monkeypatch)
    test_actions.cells_read(monkeypatch, ("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157))
    assert actions.Shop.fuse(context, test_actions.shop_team(team(SOOTHE)), visit)
    assert not visit["fuse_scanned"]


def test_an_exclusive_recipe_is_made_though_the_run_took_none_of_its_packs(context, monkeypatch):
    # #306 unlocks the materials of a pack's exclusive recipe in a run without the pack; the recipe is made all the same.
    actions.RUN["packs"] = []
    fused, taps, ok = fusion_taps(context, monkeypatch, team(9410), ("Sinking", 2, 9408), ("Sinking", 2, 9409), *junk(2), confirm=2)
    assert fused and ok and taps == [1, 1, 0, 0]


def test_a_recipe_that_does_not_go_in_leaves_the_ordinary_fusion_to_be_made_the_same_call(context, monkeypatch):
    # The page ignores the taps on the recipe's cells (9003, 9053, 9157): it is passed over for this visit, not tried
    # again and again, and the three junk gifts fuse as the round's order says (recipe first, then the ordinary one).
    readings = [("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157), *junk(3)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *readings, ignored=actions.FUSE_CELLS[:3])
    assert fused and ok and taps[3:] == [1, 1, 1]


REMINISCENCE = 9179  # Poise III: [9063, 9177]
REMINISCENCE_MATERIALS = [("Poise", 1, 9063), ("Poise", 2, 9177)]


def test_a_wanted_fusion_is_made_from_materials_the_list_wants_too(context, monkeypatch):
    # accept-301c's list wanted Reminiscence and both its materials; the user (2026-10-30): the fusion takes them.
    fused, taps, ok = fusion_taps(context, monkeypatch, team(REMINISCENCE, 9063, 9177), *REMINISCENCE_MATERIALS, confirm=2)
    assert fused and ok and taps == [1, 1]


def test_a_wanted_material_short_of_its_partner_is_no_ordinary_fusion_material(context, monkeypatch):
    # 9177 not owned yet: 9063 waits for it (a wanted gift is never an ordinary fusion's material), three junk gifts fuse.
    fused, taps, ok = fusion_taps(context, monkeypatch, team(REMINISCENCE, 9063, 9177), ("Poise", 1, 9063), *junk(3))
    assert fused and ok and taps == [0, 1, 1, 1]


def test_a_wanted_fusion_takes_a_material_the_list_keeps(context, monkeypatch):
    # The user, 2026-10-30: "want is the highest priority, it may eat a keep".
    keeps_one = {"list": wants(REMINISCENCE, 9063, keep=(9177,))}
    fused, taps, ok = fusion_taps(context, monkeypatch, keeps_one, *REMINISCENCE_MATERIALS, confirm=2)
    assert fused and ok and taps == [1, 1]


def test_the_materials_of_a_wanted_fusion_owned_are_ordinary_materials_again_and_the_log_says_so(context, monkeypatch):
    # Soothe the Dead owned: 9003 and 9053 are no longer locked, so they fuse with the Bleed II; Soothe itself is wanted, kept.
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), ("Burn", 4, SOOTHE), ("Burn", 3, 9003), ("Burn", 3, 9053), *junk(1))
    assert fused and ok and taps == [0, 1, 1, 1]
    assert any(f"wanted fusion {SOOTHE} " in line and "no longer bought or kept" in line for line in logs)


# The Forecasts row (#300): a recipe fusion whose page tier is not the recipe's own is left unpressed.
SOOTHE_MATERIALS = [("Burn", 3, 9003), ("Burn", 3, 9053), ("Burn", 3, 9157)]


def forecasting(monkeypatch, tier):
    monkeypatch.setattr(actions.shop, "forecast_tier", lambda image: tier)


def test_a_recipe_whose_forecast_is_not_its_tier_is_not_fused_and_the_materials_come_out(context, monkeypatch):
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    forecasting(monkeypatch, 3)  # Soothe the Dead is a IV
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *SOOTHE_MATERIALS)
    assert not fused and not ok and taps == [2, 2, 2]
    assert any(f"recipe fusion {SOOTHE} " in line and "page tier 3" in line and "cancelled" in line for line in logs)


def test_a_cancelled_recipe_leaves_the_ordinary_fusion_to_be_made_the_same_call(context, monkeypatch):
    forecasting(monkeypatch, 3)
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *SOOTHE_MATERIALS, *junk(3))
    assert fused and ok and taps == [2, 2, 2, 1, 1, 1]


def test_a_recipe_whose_forecast_is_its_tier_is_fused(context, monkeypatch):
    forecasting(monkeypatch, 4)
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *SOOTHE_MATERIALS)
    assert fused and ok and taps == [1, 1, 1]


def test_a_recipe_whose_forecast_is_unread_is_fused_all_the_same(context, monkeypatch):
    # A recipe's tier is no points tier, so there is nothing to fall back on but the recipe itself.
    forecasting(monkeypatch, None)
    fused, taps, ok = fusion_taps(context, monkeypatch, team(SOOTHE), *SOOTHE_MATERIALS)
    assert fused and ok and taps == [1, 1, 1]


def test_a_tier_v_recipe_is_not_checked_as_the_row_never_reads_a_v(context, monkeypatch):
    forecasting(monkeypatch, 4)  # a misread: shop.forecast_tier gives a V never
    readings = [("Burn", 4, i) for i in (9105, 9110, 9142, 9147, 9152)]
    fused, taps, ok = fusion_taps(context, monkeypatch, team(LUNAR), *readings, slots=5, confirm=5)
    assert fused and ok and taps == [1] * 5
