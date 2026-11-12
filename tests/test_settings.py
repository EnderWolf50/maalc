import copy
import json
from pathlib import Path

import pytest
import yaml

import settings
from settings import SettingsError, load_settings

DATA = Path(__file__).parent.parent / "assets" / "resource" / "base" / "data"
SEARCH = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
RECIPES = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
SOLD = [g for g in SEARCH + RECIPES["materials"] + RECIPES["extra_gifts"] if g["id"] in RECIPES["shop"]["sells"]]  # what a shop may sell (#626)
KEYWORDS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
ORDER = ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu",
         "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"]
SWAPS = ["s1_s3", "s2_s3", "s1_s2"]  # data/shop.yaml skill_replacement
# a new team: no sinner listed, so every deck stays the game's 3/2/1; ID Skill Search off, paid in Cost
# (#454); the GUI's tests read the same literal
DEFAULT_SKILLS = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["skill_replacement_default"]
STARLIGHT = {"levels": ["none"] * 10, "priority": list(range(1, 11)), "convert_leftover": False}


def team(id, game_team, **kw):
    return {
        "id": id, "name": f"Team {id}", "enabled": True, "game_team": game_team,
        "usage": "any", "hard_from_floor": 1, "deployment_order": {"custom": ORDER},
        "starlight": {"custom": STARLIGHT}, "theme_pack_plan": "default",
        "reward_cards": ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"],
        "shop_refresh_keyword": 2, "shop_refresh_normal": 0, "heal": "revive", "reserve_cost": 0, "min_alive": 0, "guard_turns": 0,
        "gift_search": {"enabled": False, "gifts": []}, "allow_white_gossypium": True,
        "gift_list": "default", "sell_max_tier": 4, "sell_vestiges": False,
        "skill_replacement": copy.deepcopy(DEFAULT_SKILLS), **kw,
    }


# every keyword's gifts a shop may sell, the highest tier first (no V is sold): a list's gorder once loaded
GORDER = {k: [g["id"] for tier in (4, 3, 2, 1) for g in SOLD if g["keyword"] == k and g["tier"] == tier] for k in KEYWORDS}


def custom_skills():
    """Team b's setting: Gregor first and aiming for four skill 3s, Yi Sang at 2/2/2 trying the other swap first, Ryōshū listed
    but still at 3/2/1 (allowed, it does nothing); ID Skill Search on, paid in starlight."""
    return {
        "sinners": [
            {"sinner": "Gregor", "target": {"s1": 1, "s2": 1, "s3": 4}, "s1_s3_first": True},
            {"sinner": "Yi Sang", "target": {"s1": 2, "s2": 2, "s3": 2}, "s1_s3_first": False},
            {"sinner": "Ryōshū", "target": {"s1": 3, "s2": 2, "s3": 1}, "s1_s3_first": True},
        ],
        "id_skill_search": {"enabled": True, "pay": "starlight"},
    }


VALID = {
    "version": 20,
    "language": "zh_tw",
    "run": {
        "difficulty": "auto", "target_floor": 5, "runs": 1, "weekly_bonus_use": "hard", "weekly_bonus_amount": "all",
        "stop_when_weekly_bonus_out": False, "starlight_unaffordable": "skip", "wipe_retries": 2,
        "after_retries": "stop", "webhook_url": "", "theme_pack_refresh": "all",
        "auto_accept_terms": True, "auto_download": True, "keep_dismissed_screens": True,
    },
    "deployment_order_plans": [{"id": "d1", "name": "Bleed order", "order": ORDER}],
    "starlight_plans": [{"id": "s1", "name": "Cheap", **STARLIGHT}],
    "theme_pack_plans": [{"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5}, "threshold": 0, "unlisted": 0, "event_packs": "weight"}],
    "gift_lists": [{"id": "g1", "name": "Mine", "order": KEYWORDS, "want": [9053], "keep": [9071], "gorder": {"Burn": [9071, 9053]},
                    "fusion_condition": "upgrade"}],
    "teams": [
        team("a", 1, deployment_order={"plan": "d1"}, starlight={"plan": "s1"}, theme_pack_plan="p1", gift_list="g1"),
        team("b", 2, skill_replacement=custom_skills()),
    ],
    "event_overrides": [{"question": "Q?", "option": "Yes"}],
    "trial_risk_overrides": [{"trial": "Growth I", "risk": 1.5}],
    "luxcavation": {"exp": {"mode": "daily", "count": 1, "team": None, "retries": 0, "consecutive": True},
                    "thread": {"mode": "daily", "count": 3, "team": None, "retries": 0, "consecutive": True}},
    "charge_enkephalin": {"count": 0},
}


def load(tmp_path, data):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    return load_settings(tmp_path)


def errors(tmp_path, data):
    with pytest.raises(SettingsError) as e:
        load(tmp_path, data)
    return e.value.errors


def edited(fn):
    data = copy.deepcopy(VALID)
    fn(data)
    return data


def test_valid_settings_load(tmp_path):
    loaded = load(tmp_path, VALID)
    assert {**loaded, "gift_lists": None} == {**VALID, "gift_lists": None}
    assert loaded["gift_lists"] == [{**VALID["gift_lists"][0], "gorder": {**GORDER, "Burn": [9071, 9053] + [i for i in GORDER["Burn"] if i not in (9071, 9053)]}}]


def test_loading_drops_ids_no_data_file_has_and_fills_gorder(tmp_path):
    # An id a new season removed is ignored, even when it is in want and keep (the GUI drops it on load and warns).
    data = edited(lambda d: d["gift_lists"][0].update(want=[9053, 424242], keep=[9071, 424242], gorder={"Burn": [9071, 5]}))
    loaded = load(tmp_path, data)["gift_lists"][0]
    assert (loaded["want"], loaded["keep"]) == ([9053], [9071])
    # 9105 Fragment of Hellfire: the first Burn gift a shop may sell, tier IV (#626)
    assert loaded["gorder"]["Burn"][:2] == [9071, 9105] and sorted(loaded["gorder"]["Burn"]) == sorted(GORDER["Burn"])
    assert list(loaded["gorder"]) == KEYWORDS


def test_missing_file_asks_for_a_team(tmp_path):
    with pytest.raises(SettingsError) as e:
        load_settings(tmp_path)
    assert "set up a team" in str(e.value)


def test_broken_json(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text("{", encoding="utf-8")
    with pytest.raises(SettingsError, match="not readable JSON"):
        load_settings(tmp_path)


@pytest.mark.parametrize("fn, where", [
    (lambda d: d["run"].update(difficulty="extreme"), "run/difficulty"),
    (lambda d: d["run"].update(runs=-1), "run/runs"),
    (lambda d: d["teams"][0].update(game_team=41), "teams/0/game_team"),
    (lambda d: d["teams"][0].update(min_alive=13), "teams/0/min_alive"),
    (lambda d: d["teams"][0].update(min_alive=None), "teams/0/min_alive"),  # a number; 0 is no check (#137)
    (lambda d: d["teams"][0].update(hard_from_floor=0), "teams/0/hard_from_floor"),
    (lambda d: d["run"].update(runs=0), "run/runs"),
    (lambda d: d["deployment_order_plans"][0]["order"].__setitem__(1, "Yi Sang"), "deployment_order_plans/0/order"),
    (lambda d: d["teams"][1].update(reward_cards=["Cost"] * 5), "teams/1/reward_cards"),
    (lambda d: d["starlight_plans"][0]["priority"].__setitem__(0, 2), "starlight_plans/0/priority"),
    (lambda d: d["teams"][1].update(starlight={"custom": {**STARLIGHT, "levels": ["max"] * 10}}), "teams/1/starlight"),
    (lambda d: d["theme_pack_plans"][0]["weights"].update(X=11), "theme_pack_plans/0/weights/X"),
    (lambda d: d["theme_pack_plans"][0].update(event_packs="skip"), "theme_pack_plans/0/event_packs"),
    (lambda d: d["theme_pack_plans"][0].update(id="default"), "theme_pack_plans/0/id"),
    (lambda d: d.update(extra=1), "(root)"),
    (lambda d: d["teams"][0].pop("heal"), "teams/0"),
    (lambda d: d["teams"][0]["gift_search"]["gifts"].append({"keyword": "Bleed", "tier": 4, "name": "X"}), "teams/0/gift_search/gifts/0/tier"),
    (lambda d: d["teams"][0].update(sell_max_tier=6), "teams/0/sell_max_tier"),
    (lambda d: d["teams"][0].update(fusion_condition="any"), "teams/0"),  # moved to the gift list
    (lambda d: d["teams"][0].update(keep_gifts=[]), "teams/0"),
    (lambda d: d["teams"][0].pop("gift_list"), "teams/0"),
    (lambda d: d["teams"][0].update(gift_list=""), "teams/0/gift_list"),
    (lambda d: d.pop("gift_lists"), "(root)"),
    (lambda d: d["gift_lists"][0].update(fusion_condition="aggressive"), "gift_lists/0/fusion_condition"),
    (lambda d: d["gift_lists"][0].update(id="default"), "gift_lists/0/id"),
    (lambda d: d["gift_lists"][0].update(name=""), "gift_lists/0/name"),
    (lambda d: d["gift_lists"][0].update(order=KEYWORDS[:10]), "gift_lists/0/order"),  # all 11
    (lambda d: d["gift_lists"][0].update(order=KEYWORDS[:10] + ["Burn"]), "gift_lists/0/order"),
    (lambda d: d["gift_lists"][0].update(order=KEYWORDS[:10] + ["Other"]), "gift_lists/0/order/10"),
    (lambda d: d["gift_lists"][0].update(want=[9053, 9053]), "gift_lists/0/want"),
    (lambda d: d["gift_lists"][0].update(keep=["9071"]), "gift_lists/0/keep/0"),
    (lambda d: d["gift_lists"][0]["gorder"].update(Other=[1]), "gift_lists/0/gorder"),
    (lambda d: d["gift_lists"][0]["gorder"].update(Burn="9053"), "gift_lists/0/gorder/Burn"),
    (lambda d: d["gift_lists"][0].pop("keep"), "gift_lists/0"),
    (lambda d: d["teams"][0].update(sell_max_tier=0), "teams/0/sell_max_tier"),
    (lambda d: d["teams"][0].pop("skill_replacement"), "teams/0"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0]["target"].update(s3=7), "teams/1/skill_replacement/sinners/0/target/s3"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0]["target"].update(s3=-1), "teams/1/skill_replacement/sinners/0/target/s3"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0]["target"].update(s3=1.5), "teams/1/skill_replacement/sinners/0/target/s3"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0]["target"].pop("s2"), "teams/1/skill_replacement/sinners/0/target"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0].pop("s1_s3_first"), "teams/1/skill_replacement/sinners/0"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0].update(s1_s3_first=1), "teams/1/skill_replacement/sinners/0/s1_s3_first"),
    # options went away on 2026-11-06 (#454); the version 19 that had it never shipped, so no file carries it
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0].update(options=SWAPS), "teams/1/skill_replacement/sinners/0"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0].update(sinner="Dante"), "teams/1/skill_replacement/sinners/0/sinner"),
    (lambda d: d["teams"][1]["skill_replacement"].update(sinners=[{"sinner": s, "target": {"s1": 3, "s2": 2, "s3": 1}, "s1_s3_first": True}
                                                                  for s in ORDER + ["Yi Sang"]]), "teams/1/skill_replacement/sinners"),
    (lambda d: d["teams"][0]["skill_replacement"]["id_skill_search"].update(pay="lunacy"), "teams/0/skill_replacement/id_skill_search/pay"),
    (lambda d: d["teams"][0]["skill_replacement"]["id_skill_search"].update(enabled="yes"), "teams/0/skill_replacement/id_skill_search/enabled"),
])
def test_schema_errors_name_the_field(tmp_path, fn, where):
    assert any(e.startswith(where + ":") for e in errors(tmp_path, edited(fn)))


def test_newer_version_is_refused(tmp_path):
    assert "newer" in errors(tmp_path, {**VALID, "version": 21})[0]


def test_skill_swaps_are_game_data_the_gui_shares():
    # data/shop.yaml holds the three swaps and their prices (ADR 0005, #264: read off the game's upgradePersonality); a target
    # names no swap, the swaps it needs follow from it (docs/spec/04-settings.md section 9).
    swaps = yaml.safe_load((DATA / "shop.yaml").read_text(encoding="utf-8"))["skill_replacement"]
    assert list(swaps) == SWAPS
    assert {k: (v["from"], v["to"]) for k, v in swaps.items()} == {"s1_s3": (1, 3), "s2_s3": (2, 3), "s1_s2": (1, 2)}
    assert {k: v["shop"] for k, v in swaps.items()} == {"s1_s3": 120, "s2_s3": 75, "s1_s2": 45}
    assert {k: v["id_search"] for k, v in swaps.items()} == {
        "s1_s3": {"cost": 240, "starlight": 75}, "s2_s3": {"cost": 150, "starlight": 50}, "s1_s2": {"cost": 90, "starlight": 25}}
    team = settings.SCHEMA["properties"]["teams"]["items"]["properties"]["skill_replacement"]
    assert team["default"] == DEFAULT_SKILLS
    # s1_s3_first true tries S1→S3 first, as the dropped options list did by default (s1_s3, s2_s3, s1_s2)
    assert settings.SCHEMA["$defs"]["skill_sinner"]["properties"]["s1_s3_first"]["default"] is True


@pytest.mark.parametrize("risk, ok", [(0, True), (0.25, True), (12, True), (-0.5, False), ("1", False)])
def test_a_trial_override_is_a_score_of_0_or_more(tmp_path, risk, ok):
    data = edited(lambda d: d["trial_risk_overrides"][0].update(risk=risk))
    if ok:
        assert load(tmp_path, data)["trial_risk_overrides"][0]["risk"] == risk
    else:
        assert [e.split(":")[0] for e in errors(tmp_path, data)] == ["trial_risk_overrides/0/risk"]


def test_an_older_version_is_migrated_in_memory(tmp_path, monkeypatch):
    # The frame a later version's migration plugs into: MIGRATIONS[n] takes version n to n + 1, the file on disk stays as it was.
    def v19_to_v20(d):
        d["run"]["target_floor"] = d["run"].pop("floors")
        return d

    monkeypatch.setattr(settings, "MIGRATIONS", {19: v19_to_v20})
    old = edited(lambda d: [d.update(version=19), d["run"].update(floors=d["run"].pop("target_floor"))])
    got = load(tmp_path, old)
    assert (got["version"], got["run"]) == (20, VALID["run"])
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))["version"] == 19


def test_every_version_from_the_oldest_has_its_migration():
    assert set(settings.MIGRATIONS) == set(range(settings.OLDEST_VERSION, settings.CURRENT_VERSION))


@pytest.mark.parametrize("fn, expected", [
    (lambda d: d["teams"][1].update(game_team=1), "TEAMS #1"),
    (lambda d: d["teams"][0].update(deployment_order={"plan": "gone"}), "teams/0/deployment_order"),
    (lambda d: d["teams"][0].update(starlight={"plan": "gone"}), "teams/0/starlight"),
    (lambda d: d["teams"][0].update(theme_pack_plan="gone"), "teams/0/theme_pack_plan"),
    (lambda d: d["teams"][0].update(gift_list="gone"),
     "teams/0/gift_list: team 'Team a' uses missing plan 'gone' (not in gift_lists)"),
    (lambda d: d["gift_lists"].append({**d["gift_lists"][0], "name": "Other"}), "gift_lists: id 'g1' appears 2 times"),
    (lambda d: d["gift_lists"].append({**d["gift_lists"][0], "id": "g2"}), "gift_lists: name 'Mine' appears 2 times"),
    (lambda d: d["gift_lists"][0].update(keep=[9071, 9053]),
     "gift_lists/0: list 'Mine' has gift 9053 in both want and keep"),
    (lambda d: d["teams"][1].update(id="a"), "teams: id 'a'"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][1]["target"].update(s3=3),
     "teams/1/skill_replacement/sinners/1/target: team 'Team b' sinner 'Yi Sang' targets 7 skills, not 6"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][0]["target"].update(s3=1),
     "teams/1/skill_replacement/sinners/0/target: team 'Team b' sinner 'Gregor' targets 3 skills, not 6"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][1].update(sinner="Gregor"),
     "teams/1/skill_replacement/sinners: sinner 'Gregor' appears 2 times"),
    # #454: the deck starts at 3/2/1 and every swap moves a card up, so S1 above 3 or S3 below 1 is never reached
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][1].update(target={"s1": 4, "s2": 1, "s3": 1}),
     "teams/1/skill_replacement/sinners/1/target/s1: team 'Team b' sinner 'Yi Sang' targets 4 of skill 1, but swaps only lower it from the game's 3"),
    (lambda d: d["teams"][1]["skill_replacement"]["sinners"][1].update(target={"s1": 3, "s2": 3, "s3": 0}),
     "teams/1/skill_replacement/sinners/1/target/s3: team 'Team b' sinner 'Yi Sang' targets 0 of skill 3, but swaps only raise it from the game's 1"),
    (lambda d: d["starlight_plans"].append({**d["starlight_plans"][0], "name": "Other"}), "starlight_plans: id 's1'"),
    (lambda d: d["deployment_order_plans"].append({"id": "d2", "name": "Bleed order", "order": ORDER}),
     "deployment_order_plans: name 'Bleed order'"),
    (lambda d: d["event_overrides"].append({"question": "Q?", "option": "No"}), "event_overrides: question 'Q?'"),
    (lambda d: d["trial_risk_overrides"].append({"trial": "Growth I", "risk": 1}), "trial_risk_overrides: trial 'Growth I'"),
])
def test_cross_checks(tmp_path, fn, expected):
    assert any(expected in e for e in errors(tmp_path, edited(fn)))


@pytest.mark.parametrize("fn", [lambda d: [t.update(enabled=False) for t in d["teams"]], lambda d: d.update(teams=[])])
def test_only_the_mirror_dungeon_wants_an_enabled_team(tmp_path, fn):
    # #364: a file with no enabled team loads (the dailies need none); MirrorDungeon asks with need_team.
    data = edited(fn)
    assert load(tmp_path, data)["teams"] == data["teams"]
    with pytest.raises(SettingsError) as e:
        load_settings(tmp_path, need_team=True)
    assert e.value.errors == [settings.NO_TEAM]


def test_cross_check_allows_what_the_spec_allows(tmp_path):
    def fn(d):
        d["teams"][1].update(game_team=1, enabled=False)  # disabled teams may share a slot
        d["teams"].append(team("c", 3, name="Team a"))  # team names are not checked
        d["theme_pack_plans"][0]["weights"] = {}  # empty plan = every pack unlisted
        d["starlight_plans"].append({**d["starlight_plans"][0], "id": "s2", "name": "Bleed order"})  # names per kind
        d["gift_lists"].append({**d["gift_lists"][0], "id": "g2", "name": "Cheap", "want": [1, 2, 3], "gorder": {}})  # ids are not looked up
        d["teams"][1].update(gift_list="g2")
        d["gift_lists"][0]["gorder"] = {"Burn": [9053, 9053, 99999]}  # gorder is not a permutation
    load(tmp_path, edited(fn))


@pytest.mark.parametrize("target", [10, 15])
def test_a_disabled_team_does_not_hide_a_normal_only_team_behind_it_from_a_target_past_floor_5(tmp_path, target):
    # #640 (settings.py): the check passed over a disabled team with `break`, so teams after it went unchecked.
    def fn(d):
        d["run"]["target_floor"] = target
        d["teams"][0]["enabled"] = False
        d["teams"][1]["usage"] = "normal_only"
    got = errors(tmp_path, edited(fn))
    assert [e for e in got if "teams/1/usage" in e and "normal_only" in e], got
    assert not [e for e in got if "teams/0/" in e]  # the disabled team itself is not asked


def test_every_error_is_reported(tmp_path):
    data = edited(lambda d: (d["teams"][1].update(game_team=1), d["teams"][0].update(starlight={"plan": "x"})))
    assert len(errors(tmp_path, data)) == 2


CASES = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))


def apply_edits(data, edits):
    """The edit format of tests/settings_cases.json; gui/src/validate.test.ts reads it the same way."""
    data = copy.deepcopy(data)
    for edit in edits:
        *parents, last = (edit["set"] if "set" in edit else edit["delete"]).split("/")
        node = data
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        if "delete" in edit:
            del node[last]
        elif last == "-":
            node.append(edit["value"])
        else:
            node[int(last) if isinstance(node, list) else last] = edit["value"]
    return data


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_shared_cases(tmp_path, case):
    """The GUI runs the same cases; both sides must agree on what is wrong."""
    data = apply_edits(CASES["valid"], case["edits"])
    if case.get("cross") == []:
        load(tmp_path, data)
    elif "cross" in case:
        assert errors(tmp_path, data) == case["cross"]
    else:
        paths = {e.split(": ", 1)[0] for e in errors(tmp_path, data)}
        assert set(case["schema"]) <= paths
        assert all(any(p == s or p.startswith(s + "/") for s in case["schema"]) for p in paths)


def test_shared_valid_loads(tmp_path):
    loaded = load(tmp_path, CASES["valid"])
    assert {**loaded, "gift_lists": None} == {**CASES["valid"], "gift_lists": None}  # the list is cleaned on load


@pytest.mark.parametrize("case", CASES["too_old"], ids=lambda c: str(c["version"]))
def test_shared_too_old(tmp_path, case):
    """The GUI refuses the same files in the same words (gui/src/validate.test.ts)."""
    assert errors(tmp_path, {**CASES["valid"], "version": case["version"]}) == [case["error"]]


@pytest.mark.parametrize("case", CASES["clean_gift_list"], ids=lambda c: c["name"])
def test_shared_clean_gift_list(case):
    cleaned, dropped = settings.clean_gift_list(case["list"])
    assert (cleaned["want"], cleaned["keep"], dropped) == (case["want"], case["keep"], case["dropped"])
    assert list(cleaned["gorder"]) == KEYWORDS
    for kw, head in case["gorder_head"].items():
        assert cleaned["gorder"][kw][: len(head)] == head
    for kw, size in case["gorder_size"].items():
        assert len(cleaned["gorder"][kw]) == size
    assert all(sorted(ids) == sorted(g["id"] for g in SOLD if g["keyword"] == kw) for kw, ids in cleaned["gorder"].items())
