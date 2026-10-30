"""Mounting Trials after a boss (#381, spec 03 section 12): the trials.yaml table, telling a card's trial, its score,
and PickGift on a boss page."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

import actions
import rewards as r
import test_actions

clock, context = test_actions.clock, test_actions.context  # its fixtures
ROOT = Path(__file__).resolve().parent.parent
TABLE = yaml.safe_load((ROOT / "assets/resource/base/data/trials.yaml").read_text(encoding="utf-8"))
MODEL = TABLE["model"]


def pool(n):
    return r.trials_of(TABLE, n)


def test_the_table_holds_every_pool_of_a_15_floor_run():
    assert TABLE["client"] == "1.117.0"
    assert TABLE["pools"] == {1: 6, 2: 7, 3: 8, 4: 9, 5: 8, 6: 8, 7: 8, 8: 8, 9: 8, 10: 7, 11: 7, 12: 7, 13: 7, 14: 7}
    assert len(TABLE["trials"]) == 105
    assert [sum(t["pool"] == n for t in TABLE["trials"].values()) for n in TABLE["pools"]] == list(TABLE["pools"].values())
    assert MODEL == {"early_pools": 4, "level": 0.5, "coin_budget": 0, "coin_in": 1.5, "coin_over": 3.0}
    assert "Project Moon" in (ROOT / "assets/resource/base/data/trials.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("name, effects, score", [
    ("Growth II", {"hp": 10}, 0.05),
    ("Take Less Damage", {"taken": 5}, 4.0),  # pools 1-4: Damage Taken, Damage Dealt and Coin Power are never taken
    ("Brutality", {"coin": 1}, 4.0),
    ("Final Power Boost", {"final": 1, "hp": 5}, 1.075),
    ("Body Up II", {"offense": 2, "defense": 3, "hp": 12.5}, 0.8025),  # the static Max HP, not the description's 10%
    ("Brutality II", {"coin": 1, "dealt": 5}, 2.0),  # pools 5+: a Coin unit 1.5 in the budget, 1% damage 0.1
    ("Growth XIII", {"coin": 1, "offense": 3, "defense": 3, "hp": 80, "dealt": 10, "boss_hp": 30}, 4.13),
])
def test_scores_follow_the_model(name, effects, score):
    assert TABLE["trials"][name]["effects"] == effects
    assert TABLE["trials"][name]["score"] == pytest.approx(score)


def test_every_score_is_its_effects_weighed_by_the_file_s_own_weights():
    # Without the game data (CI): the scores and the weights in the file agree, whatever the tool's run
    for name, t in TABLE["trials"].items():
        weights = TABLE["weights"]["early" if t["pool"] <= MODEL["early_pools"] else "late"]
        assert t["score"] == pytest.approx(sum(weights[k] * v for k, v in t["effects"].items()), abs=1e-4), name


@pytest.mark.parametrize("text, effects", [
    ("Defense Level +1, Max HP +7.5%", {"defense": 1, "hp": 7.5}),
    ("Defense Level +1. Max HP +7.5%", {"defense": 1, "hp": 7.5}),  # OCR reads the comma as a dot
    ("Offense Level+3 Defense Level +2, Max HP +10%", {"offense": 3, "defense": 2, "hp": 10}),
    ("Plus Coin Power +1, Minus Coin Power -1", {"coin": 1}),
    ("Defense Skill Final Power +1", {"defskill": 1}),
    ("Final Power +1, Max HP +5%", {"final": 1, "hp": 5}),
    ("Damage Taken -5%", {"taken": 5}),
    ("Clash Power +1, Offense Level +8, Defense Level +3, Max HP +40%, Damage Dealt +10%, Boss Max HP +30%",
     {"clash": 1, "offense": 8, "defense": 3, "hp": 40, "dealt": 10, "boss_hp": 30}),
    ("Defense Skill Final Power", {}),  # its "+1" on the next line not read: nothing to go by
    ("", {}),
])
def test_parse_effects_reads_an_effect_line(text, effects):
    assert r.parse_effects(text) == effects


def test_a_name_is_looked_for_in_the_pool_of_the_floor_just_cleared():
    assert r.read_trial("Resilient V", "", pool(3)) == ("Resilient V", "name")
    assert r.read_trial("Resilient V", "", pool(2)) == (None, None)  # not in pool 2
    assert r.read_trial("Resi1ient V", "", pool(3)) == ("Resilient V", "name")  # an OCR slip
    assert r.read_trial("Growth Il", "", pool(2)) == (None, None)  # a numeral misread is no name
    assert r.read_trial("Keen I", "", pool(3)) == (None, None)  # Keen II and III: the fuzzy match would pick one


def test_the_effect_line_wins_over_the_name():
    # #381, 2026-10-28 floor 2: Growth II scored as Growth I, the OCR (likely) dropping an I; the line tells them apart.
    assert r.read_trial("Growth I", "Max HP +10%", pool(2)) == ("Growth II", "effects")
    assert r.read_trial("Growth Il", "Max HP +10%", pool(2)) == ("Growth II", "effects")
    assert r.read_trial("", "Defense Level +4, Max HP +5%", pool(3)) == ("Resilient V", "effects")
    # Body Up II shows Max HP +10% (static 12.5%): the trial whose other values agree, not Body Up III's +10%
    assert r.read_trial("", "Offense Level +2 Defense Level +3, Max HP +10%", pool(4)) == ("Body Up II", "effects")
    # a line cut short names no trial: the name decides
    assert r.read_trial("Defense Skill Up", "Defense Skill Final Power", pool(1)) == ("Defense Skill Up", "name")
    assert r.read_trial("Resilient II", "Defense Level +1, Max HP", pool(2)) == ("Resilient II", "name")


def test_an_unread_card_scores_the_pool_s_worst():
    scores = r.scores(pool(4), MODEL)
    assert max(scores.values()) == scores["Headstrong II"] == pytest.approx(40)
    assert r.scores(pool(2), MODEL, overrides={"Growth II": 1.5})["Growth II"] == 1.5


def test_coin_units_past_the_run_budget_cost_coin_over():
    brutality = {"Brutality III": TABLE["trials"]["Brutality III"]}  # pool 6: Coin 1, Dealt 5%
    assert r.scores(brutality, MODEL)["Brutality III"] == pytest.approx(3.5)  # budget 0 (the default): 3.0 a unit
    budget = MODEL | {"coin_budget": 2}
    assert r.scores(brutality, budget, coins=1)["Brutality III"] == pytest.approx(2.0)  # 1 of 2 left: in the budget
    assert r.scores(brutality, budget, coins=2)["Brutality III"] == pytest.approx(3.5)
    v = {"Brutality V": TABLE["trials"]["Brutality V"]}  # pool 8: Coin 2, Dealt 7.5%
    assert r.scores(v, budget, coins=1)["Brutality V"] == pytest.approx(3.75 + 1.5)  # one unit in, one over
    # pools 1-4 weigh Coin at 4 pt a unit whatever the budget
    assert r.scores({"Brutality": TABLE["trials"]["Brutality"]}, budget)["Brutality"] == pytest.approx(4)


def test_the_gift_score_rises_half_a_point_a_tier_for_main_and_other():
    assert [r.gift_score("main", t) for t in (1, 2, 4, None)] == [3, 3.5, 4.5, 3]  # unread: tier I
    assert r.gift_score("other", 3) == 3
    assert r.gift_score("owned", 4) == r.gift_score("avoid", 2) == 0


def test_rank_gifts_takes_level_ups_at_half_a_point():
    # card = gift - weight x (trial + 0.5 x N), ties to the lighter trial, then the leftmost
    cards = [("main", 1, r.burden(4.0, 2, MODEL)), ("other", 1, r.burden(0.1, 1, MODEL)), ("owned", 1, r.burden(0.8, 1, MODEL))]
    assert r.rank_gifts(cards, "medium") == [1, 2, 0]
    assert r.burden(0.1, None, MODEL) == pytest.approx(1.1)  # N unread counts as 2
    assert r.rank_gifts([("main", 1, 1.0), ("other", 1, 0.0)], "medium") == [1, 0]  # 2 = 2: the lighter first
    assert r.rank_gifts([("other", None, None), ("main", None, None), ("owned", None, None)], "high") == [1, 0, 2]


def test_an_avoided_gift_is_ranked_last():
    # #90 (the user, 2026-10-18): taken only when nothing else is left, rather than a random trial.
    assert r.rank_gifts([("avoid", 1, None), ("owned", 1, None), ("main", 1, None)], "high") == [2, 1, 0]
    assert r.rank_gifts([("avoid", 1, 0.0), ("other", 1, 40.0)], "high") == [1, 0]


# The three boss pages of the 2026-10-28 NORMAL run (#381): (kind, the tier the gift data gives, trial, Enemy Level Up N)
PAGES = {
    2: [("other", 3, "Resilient II", 2), ("other", 1, "Resilient III", 1), ("other", 1, "Growth II", 2)],  # Disk Fragment, Phlebotomy Pack, Blue Zippo Lighter
    3: [("other", 1, "Resilient V", 2), ("other", 2, "Final Power Boost", 1), ("owned", 2, "Keen III", 1)],  # Ashes to Ashes, Barbed Lasso, Nebulizer
    4: [("other", 1, "Body Up III", 1), ("main", 2, "Brutality", 2), ("owned", 1, "Body Up II", 1)],  # Burning Intellect, Huge Gift Sack, Pendant of Nostalgia
}


def pick(floor, tiers=True, weight="medium"):
    scores = r.scores(pool(floor), MODEL)
    cards = [(kind, tier if tiers else None, r.burden(scores[name], n, MODEL)) for kind, tier, name, n in PAGES[floor]]
    return PAGES[floor][r.rank_gifts(cards, weight)[0]][2:]


def test_the_2026_10_28_pages_without_the_tier_bonus_pick_as_the_issue_says():
    # #381's update: Resilient III +1, Resilient V +2, Body Up III +1 (no longer Brutality +2), worked out from main 3 /
    # other 2 / owned 0 alone
    assert [pick(f, tiers=False) for f in PAGES] == [("Resilient III", 1), ("Resilient V", 2), ("Body Up III", 1)]


def test_the_2026_10_28_pages_with_their_gifts_tiers():
    # The same pages with each gift's tier: Disk Fragment is tier III (2 + 1 = 3 - (0.06 + 1) = 1.94 over Phlebotomy Pack's
    # 1.43) and Barbed Lasso tier II (2.5 - (1.075 + 0.5) = 0.93 over Ashes to Ashes' 0.90).
    assert [pick(f) for f in PAGES] == [("Resilient II", 2), ("Final Power Boost", 1), ("Body Up III", 1)]


def boss_page(context, monkeypatch, cards, floor=None):
    """A boss gift page whose OCR reads cards [(gift text, owned, N, trial name, effect lines)] (the trial half's read,
    TRIAL_HALF), card i centred at 375 + 264 i, Select 0/1; a Sinking team, weight medium. Its taps and log lines."""
    taps, logs = [], []
    monkeypatch.setattr(actions, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    monkeypatch.setattr(actions, "log", logs.append)
    centres = [375 + 264 * i for i in range(len(cards))]
    halves = {(x - 125, 438, 250, 105): [(f"+{n}", (x - 103, 444, 22, 22)), (name, (x - 4, 448, 90, 20))]
              + [(t, (x - 92, 486 + 20 * k, 177, 20)) for k, t in enumerate(lines)]
              for x, (_, _, n, name, lines) in zip(centres, cards)}

    def ocr(context, image, roi, only_rec=False):
        if roi == actions.GIFT_CARDS:
            return [r for x, (gift, owned, *_) in zip(centres, cards) for r in
                    [("Acquire E.G.O Gift", (x + 7, 152, 107, 22)), (gift, (x - 60, 181, 120, 20)),
                     ("Mounting Trials", (x + 10, 421, 98, 16))] + ([("Owned", (x - 80, 152, 55, 17))] if owned else [])]
        if tuple(roi) in halves:
            return halves[tuple(roi)]
        picked = any(y == 300 for _, y in taps)
        if roi == actions.GIFT_COUNT:
            return [(f"Select {int(picked)}/1", (1080, 565, 100, 30))]
        if roi == actions.REFUSE_GIFT and not (actions.GIFT_SELECT in taps and picked):
            return [("Refuse Gift", (900, 570, 100, 25))]
        return []
    monkeypatch.setattr(actions, "ocr", ocr)
    actions.RUN.update(settings={"trial_risk_overrides": []}, team={**test_actions.NO_GOSSYPIUM, "keyword": "Sinking",
                                                                    "trial_risk_weight": "medium"})
    if floor:
        actions.RUN["floor"] = floor
    return taps, logs


FLOOR_3 = [("Ashes to Ashes", False, 2, "Resilient V", ["Defense Level +4, Max HP", "+5%"]),
           ("Barbed Lasso", False, 1, "Final Power Boost", ["Final Power +1, Max HP", "+5%"]),
           ("Nebulizer", True, 1, "Keen III", ["Offense Level +3, Max HP", "+5%"])]


@pytest.mark.parametrize("floor", [3, None])  # the floor unknown after a restart: every trial, the names are unique
def test_a_boss_page_takes_the_card_whose_trial_and_level_ups_weigh_least(context, monkeypatch, floor):
    # The 2026-10-28 floor-3 page; a black screen shows no tier numerals: tier I each
    taps, logs = boss_page(context, monkeypatch, FLOOR_3, floor)
    assert actions.PickGift().run(context, None)
    assert [t for t in taps if t[1] == 300] == [(375, 300)]
    assert logs[0] == ("gifts: other/Resilient V +2 score 0.105, other/Final Power Boost +1 score 1.075, "
                       "owned/Keen III +1 score 1.045: order [0, 1, 2]")
    assert "trial_coins" not in actions.RUN


def test_a_boss_page_adds_the_tier_the_numeral_over_each_icon_shows(context, monkeypatch):
    # The same page on its capture (BossGiftTrialsFloor3.png): Barbed Lasso is tier II, 2.5 - (1.075 + 0.5) = 0.925 over
    # Ashes to Ashes' 2 - (0.105 + 1) = 0.895; the owned Nebulizer's II adds nothing.
    image = np.asarray(Image.open(ROOT / "tests/screens/BossGiftTrialsFloor3.png").convert("RGB"))[:, :, ::-1].copy()
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image
    taps, logs = boss_page(context, monkeypatch, FLOOR_3, 3)
    assert actions.PickGift().run(context, None)
    assert [t for t in taps if t[1] == 300] == [(639, 300)]
    assert logs[0] == ("gifts: other/Resilient V +2 score 0.105 tier I, other/Final Power Boost +1 score 1.075 tier II, "
                       "owned/Keen III +1 score 1.045 tier II: order [1, 0, 2]")


def test_a_fight_s_gift_page_does_not_weigh_tiers(context, monkeypatch):
    # #381 adds the tier on the boss page only: a fight's page stays main > other > owned. A main tier I card on the left,
    # an other tier IV on the right (3.5 over 3, were tiers counted).
    taps = test_actions.gift_page(context, monkeypatch, ["Ashes to Ashes", "Barbed Lasso"])  # "Inflict Bleed" on both
    actions.RUN["team"]["keyword"] = "Bleed"
    inner = actions.ocr
    monkeypatch.setattr(actions, "ocr", lambda context, image, roi, only_rec=False: [
        (t.replace("Bleed", "Burn") if b[0] > 400 else t, b) for t, b in inner(context, image, roi, only_rec)])
    monkeypatch.setattr(actions, "gift_tier", lambda image, x: 1 if x < 400 else 4)
    actions.PickGift().run(context, None)
    assert [t for t in taps if t[1] == 300] == [(236, 300)]


def test_a_card_read_by_its_effects_or_not_at_all_says_what_was_read(context, monkeypatch):
    cards = [("Disk Fragment", False, 2, "Resilient Il", ["Defense Level +1, Max HP", "+7.5%"]),
             ("Phlebotomy Pack", False, 1, "", [])]
    taps, logs = boss_page(context, monkeypatch, cards, 2)
    actions.PickGift().run(context, None)
    assert logs[0] == ("gifts: other/Resilient II +2 score 0.0575 (by its effects, read 'Resilient Il' / "
                       "'Defense Level +1, Max HP +7.5%'), other/? +1 score 12 (unread: the pool worst, read '' / ''): order [0, 1]")


def test_a_coin_power_trial_taken_counts_toward_the_run_s_budget(context, monkeypatch):
    actions.RUN["trial_coins"] = 1
    taps, logs = boss_page(context, monkeypatch, [("Huge Gift Sack", False, 2, "Brutality", ["Plus Coin Power +1, Minus", "Coin Power -1"])], 4)
    assert actions.PickGift().run(context, None)
    assert actions.RUN["trial_coins"] == 2 and logs[-1] == "trials: 2 Coin Power units this run"


def test_a_run_logs_the_trial_overrides_the_settings_migration_emptied(context, monkeypatch, tmp_path):
    import test_settings
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(test_settings.V15), encoding="utf-8")  # ROOT: context's
    logs = []
    monkeypatch.setattr(actions, "log", logs.append)
    monkeypatch.setitem(actions.TASK, "runs", 0)  # what TaskStart leaves; another file's test may have cleared it
    monkeypatch.setattr(actions.settlement, "runs_done", lambda done, limit: True)
    monkeypatch.setattr(actions, "finish", lambda context, reason: True)
    assert actions.PlanRun().run(context, None)
    assert logs == ["settings version 16: 1 trial risk override (0-5) emptied, trials score in pt now (#381)"]


def test_the_table_is_what_the_game_data_gives_when_it_is_unpacked():
    from local_dir import local_dir  # noqa: PLC0415
    if not local_dir("unpack").joinpath("static").is_dir():
        pytest.skip("no unpacked game data")
    sys.path.insert(0, str(ROOT / "tools"))
    import trial_table  # noqa: PLC0415
    assert trial_table.main(["--check"]) == 0
