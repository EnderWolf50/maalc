"""#258: Shop.heal waits for what each tap brings (the heal page, Select, the Cost, the shop again), not a fixed sleep."""
import actions
import test_actions
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # its fixtures


def heal(context, monkeypatch, mode, answers):
    """Shop.heal as a test_actions.TimedGame of `answers`: Cost 3302, Yi Sang the one grey portrait on the bar."""
    reads = {tuple(actions.SHOP_COST): "3302", tuple(actions.HEAL_COST): "3302", tuple(actions.HEAL_TITLE): "",
             tuple(actions.BOTTOM_LABEL): "Leave"}
    game = test_actions.TimedGame(monkeypatch, context, reads, answers)
    patch_all(monkeypatch, "bar_dead", lambda image: {"Yi Sang"})
    monkeypatch.setattr(actions.Shop, "to_main", staticmethod(lambda context: True))
    actions.Shop.heal(context, test_actions.shop_team({"heal": mode}))
    return game


HEAL_PAGE = (0.5, {tuple(actions.HEAL_TITLE): "Heal Sinners", tuple(actions.BOTTOM_LABEL): "Return"}, 30)
HEAL_LEFT = (0.5, {tuple(actions.HEAL_TITLE): ""}, 150)  # the result's Leave: back to the shop
YI_SANG = (actions.SHOP_PORTRAIT_X[0], 655)


def test_a_revive_goes_step_by_step_as_each_page_answers_not_after_fixed_waits(context, clock, monkeypatch):
    # #258: the heal button, the revive option, the portrait, Select and Leave slept 2, 1.5, 1.2, 2 and 2 s; the
    # 2026-11-08 run revived 14 sinners this way. Each step now waits for what it brings.
    game = heal(context, monkeypatch, "revive", {
        actions.SHOP_BUTTONS["heal"]: [HEAL_PAGE],
        actions.HEAL_OPTIONS["revive"]: [(0.3, {}, 60)],  # the bar's portraits turn selectable
        YI_SANG: [(0.3, {tuple(actions.BOTTOM_LABEL): "Select"}, 90)],
        actions.BOTTOM_RIGHT: [(0.6, {tuple(actions.HEAL_COST): "3202", tuple(actions.BOTTOM_LABEL): "Leave"}, 120), HEAL_LEFT]})
    assert game.taps == [actions.SHOP_BUTTONS["heal"], actions.HEAL_OPTIONS["revive"], YI_SANG, actions.BOTTOM_RIGHT,
                         actions.BOTTOM_RIGHT]
    assert sum(clock) < 4, str(clock)  # was 8.7 s


def test_a_revive_the_cost_does_not_show_taps_nothing_more(context, clock, monkeypatch):
    # Select taken by nothing: after its old 2 s the Cost reads as before, and the heal ends without the result's Leave.
    game = heal(context, monkeypatch, "revive", {
        actions.SHOP_BUTTONS["heal"]: [HEAL_PAGE],
        actions.HEAL_OPTIONS["revive"]: [(0.3, {}, 60)],
        YI_SANG: [(0.3, {tuple(actions.BOTTOM_LABEL): "Select"}, 90)]})
    assert game.taps == [actions.SHOP_BUTTONS["heal"], actions.HEAL_OPTIONS["revive"], YI_SANG, actions.BOTTOM_RIGHT]
    assert sum(clock) < 5  # Select's old 2 s spent in full; the steps before it were 4.75 s


def test_a_full_heal_reads_the_cost_once_it_drops(context, clock, monkeypatch):
    game = heal(context, monkeypatch, "full", {
        actions.SHOP_BUTTONS["heal"]: [HEAL_PAGE],
        actions.HEAL_OPTIONS["full"]: [(0.4, {tuple(actions.HEAL_COST): "3202"}, 120)],
        actions.BOTTOM_RIGHT: [HEAL_LEFT]})
    assert game.taps == [actions.SHOP_BUTTONS["heal"], actions.HEAL_OPTIONS["full"], actions.BOTTOM_RIGHT]
    assert sum(clock) < 3  # was 5.5 s


def test_a_heal_page_left_over_is_left_by_its_bottom_right_button(context, clock, monkeypatch):
    # Shop.to_main on a heal page (handed back mid-heal, #118): Return, then the main page once it stops moving.
    leaves = {tuple(actions.HEAL_TITLE): "", tuple(actions.REFRESH["normal"][1]): "100"}  # the main page's Refresh fee
    game = test_actions.TimedGame(monkeypatch, context, {tuple(actions.HEAL_TITLE): "Heal Sinners"},
                                  {actions.BOTTOM_RIGHT: [(0.3, leaves, 60)]})
    assert actions.Shop.to_main(context)
    assert game.taps == [actions.BOTTOM_RIGHT]
    assert sum(clock) < 1.2  # was 1.5 s


def test_the_heal_pages_bottom_label_is_read_where_the_shop_node_reads_leave():
    from test_pipeline import load_nodes
    leave = next(n for n in load_nodes("mirror_dungeon.json")["Shop"]["any_of"] if n["sub_name"] == "ShopLeave")
    assert actions.BOTTOM_LABEL == leave["roi"]
