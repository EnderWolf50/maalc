import copy
import json
import re
from pathlib import Path

import pytest
import yaml

import settings
from settings import SettingsError, load_settings
from agent_patch import patch_all

DATA = Path(__file__).parent.parent / "assets" / "resource" / "base" / "data"
SEARCH = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
RECIPES = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
SOLD = [g for g in SEARCH + RECIPES["materials"] + RECIPES["extra_gifts"] if g["id"] in RECIPES["shop"]["sells"]]  # what a shop may sell (#626)
KEYWORDS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
ORDER = ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu",
         "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"]
SWAPS = ["s1_s3", "s2_s3", "s1_s2"]  # data/shop.yaml skill_replacement
SHARED = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))
# a new team: no sinner listed, so every deck stays the game's 3/2/1; ID Skill Search off, paid in Cost
# (#454); the GUI's tests read the same literal
DEFAULT_SKILLS = SHARED["skill_replacement_default"]
# the sections version 23 brought back or added (#813), as a new file has them: run, luxcavation, charge_enkephalin, tasks,
# emulator, schedules
ADDED = {k: SHARED["valid"][k] for k in SHARED["added_v23"]}
STARLIGHT = {"levels": ["none"] * 10, "priority": list(range(1, 11)), "convert_leftover": False}


def team(id, game_team, **kw):
    return {
        "id": id, "name": f"Team {id}", "game_team": game_team,
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
    "version": 25,
    "language": "zh_tw",
    "deployment_order_plans": [{"id": "d1", "name": "Bleed order", "order": ORDER}],
    "starlight_plans": [{"id": "s1", "name": "Cheap", **STARLIGHT}],
    "theme_pack_plans": [{"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5}, "threshold": 0, "unlisted": 0, "event_packs": "weight"}],
    "gift_lists": [{"id": "g1", "name": "Mine", "order": KEYWORDS, "want": [9053], "keep": [9071], "gorder": {"Burn": [9071, 9053]},
                    "fusion_condition": "upgrade"}],
    "teams": [
        team("a", 1, deployment_order={"plan": "d1"}, starlight={"plan": "s1"}, theme_pack_plan="p1", gift_list="g1"),
        team("b", 2, skill_replacement=custom_skills()),
    ],
    "team_queue": ["a", "b"],
    "event_overrides": [{"question": "Q?", "option": "Yes"}],
    "trial_risk_overrides": [{"trial": "Growth I", "risk": 1.5}],
    **copy.deepcopy(ADDED),
    "device": {"kind": "emulator", "pc_size": "1440"},
}


def load(tmp_path, data, **kw):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    return load_settings(tmp_path, **kw)


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
    (lambda d: d["teams"][0].update(usage="extreme"), "teams/0/usage"),
    (lambda d: d["teams"][0].update(game_team=41), "teams/0/game_team"),
    (lambda d: d["teams"][0].update(min_alive=13), "teams/0/min_alive"),
    (lambda d: d["teams"][0].update(min_alive=None), "teams/0/min_alive"),  # a number; 0 is no check (#137)
    (lambda d: d["teams"][0].update(hard_from_floor=0), "teams/0/hard_from_floor"),
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
    assert "newer" in errors(tmp_path, {**VALID, "version": settings.CURRENT_VERSION + 1})[0]


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


NOTE_23 = ("settings older than version 23: the task options are read from its run, luxcavation and charge_enkephalin "
        "again (#813), each value it lacks at its default; values set in MXU or MFAAvalonia are not read; open the "
        "settings GUI once: it writes the file as version 25")
NOTE_24 = ("settings older than version 24: the disabled teams are left out of the team queue, and run.start_team is not "
           "read (#954); open the settings GUI once: it writes the file as version 25")


def older(version, edits=()):
    """settings_cases' valid file at an older version, these edits made: without the device section version 25 added (#939);
    below version 24 each team with the switch version 24 dropped, and run with version 23's start_team (#954); below
    version 23 without the sections it added (#813), below 22 without its team_queue (#803), and version 20's with the three
    sections it had."""
    old = {k: v for k, v in copy.deepcopy(CASES["valid"]).items() if k not in CASES["added_v25"]}
    if version == 24:
        return apply_edits({**old, "version": version}, list(edits))
    for t in old["teams"]:
        t["enabled"] = True
    if version == 23:
        old["run"]["start_team"] = None
    else:
        old = {k: v for k, v in old.items() if k not in CASES["added_v23"] and (version >= 22 or k != "team_queue")}
    return apply_edits({**old, "version": version, **(CASES["v20"] if version == 20 else {})}, list(edits))


def v20(edits=()):
    return older(20, edits)


@pytest.mark.parametrize("version, said", [(20, [NOTE_23, NOTE_24]), (21, [NOTE_23, NOTE_24]), (22, [NOTE_23, NOTE_24]),
                                           (23, [NOTE_24]), (24, [])])
def test_an_older_file_is_read_as_the_current_version_in_memory_and_says_what_is_read_anew(tmp_path, version, said):
    # #813: the options are the file's again, at their defaults where it has none (a version 20 file has its own); #954: no
    # team switch and no start team; #939: the device is the emulator, which no task reads. The file on disk stays as it
    # was, and a task's start logs the lines (TaskStart) until the GUI writes the file back.
    old = older(version)
    notes = []
    got = load(tmp_path, old, notes=notes)
    assert {**got, "gift_lists": None} == {**CASES["valid"], "gift_lists": None}
    assert notes == said
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8")) == old


def test_a_current_file_says_nothing(tmp_path):
    notes = []
    load(tmp_path, VALID, notes=notes)
    assert notes == []


def test_the_sections_version_23_added_are_the_schemas_defaults_as_the_shared_valid_file_has_them():
    # the agent's migration fills them from the schema, the GUI's from its own new file (validate.test.ts): both give valid
    assert settings.defaults() == ADDED


def test_a_new_files_task_list_is_every_task_once_all_ticked_in_the_users_order_the_readmes_suggested_order():
    # #874 (the user's order, 2026-11-20): ready to run as installed; README's 日常任務 table names each task's id
    order = ["ExpLuxcavation", "ThreadLuxcavation", "ClaimMail", "ChargeEnkephalin", "AssembleModules", "ClaimPassMissions",
             "MirrorDungeon"]
    tasks = settings.defaults()["tasks"]
    assert tasks == [{"id": id, "enabled": True} for id in order]
    assert set(order) == set(settings.SCHEMA["$defs"]["task"]["enum"])
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    ids = dict(re.findall(r"^\| (\S+?)（`(\w+)`）", readme, re.M))
    suggested = readme.split("### 建議順序", 1)[1].strip().splitlines()[0].split(" → ")
    assert [ids[name] for name in suggested] == order


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


@pytest.mark.parametrize("fn", [lambda d: d.update(team_queue=[]), lambda d: d.update(teams=[], team_queue=[])])
def test_only_the_mirror_dungeon_wants_a_team_in_the_queue(tmp_path, fn):
    # #364, #954: a file with an empty team queue loads (the dailies need none); MirrorDungeon asks with need_team.
    data = edited(fn)
    assert load(tmp_path, data)["teams"] == data["teams"]
    with pytest.raises(SettingsError) as e:
        load_settings(tmp_path, need_team=True)
    assert e.value.errors == [settings.NO_TEAM]


def test_cross_check_allows_what_the_spec_allows(tmp_path):
    def fn(d):
        d["teams"][1].update(game_team=1)  # a team out of the queue may share a slot
        d["teams"].append(team("c", 3, name="Team a"))  # team names are not checked
        d["team_queue"] = ["c", "a", "c"]  # the queue in an order of its own, a team twice, b not in it (#954)
        d["theme_pack_plans"][0]["weights"] = {}  # empty plan = every pack unlisted
        d["starlight_plans"].append({**d["starlight_plans"][0], "id": "s2", "name": "Bleed order"})  # names per kind
        d["gift_lists"].append({**d["gift_lists"][0], "id": "g2", "name": "Cheap", "want": [1, 2, 3], "gorder": {}})  # ids are not looked up
        d["teams"][1].update(gift_list="g2")
        d["gift_lists"][0]["gorder"] = {"Burn": [9053, 9053, 99999]}  # gorder is not a permutation
    load(tmp_path, edited(fn))


def test_every_error_is_reported(tmp_path):
    data = edited(lambda d: (d["teams"][1].update(game_team=1), d["teams"][0].update(starlight={"plan": "x"})))
    assert len(errors(tmp_path, data)) == 2


CASES = SHARED


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


@pytest.mark.parametrize("version, case", [(v, c) for v in (20, 22, 23, 24) for c in CASES[f"migrate_v{v}"]],
                         ids=lambda x: x if isinstance(x, int) else x["name"])
def test_shared_v20_v22_v23_and_v24_migration(tmp_path, version, case):
    """#813: a version 20 file keeps its run, luxcavation and charge_enkephalin, a version 22 file gets them at their
    defaults, both every other section version 23 added; #954: the disabled teams leave the queue, the start team goes;
    #939: every older file gets the device section at its defaults, the emulator, its emulator section as it was; a
    value broken by hand stays, for the schema to name. The GUI migrates the same cases to the same file
    (gui/src/validate.test.ts)."""
    old = older(version, case["edits"])
    if "schema" in case:
        paths = {e.split(": ", 1)[0] for e in errors(tmp_path, old)}
        assert paths == set(case["schema"])
        return
    loaded = load(tmp_path, old)
    assert {**loaded, "gift_lists": None} == {**apply_edits(CASES["valid"], case["gives"]), "gift_lists": None}


@pytest.mark.parametrize("case", CASES["migrate_v21"], ids=lambda c: c["name"])
def test_shared_v21_migration(tmp_path, case):
    """#803: a version 21 file reads with team_queue, the queue in the order of teams, and on to version 23 (#813) and 24
    (#954: the disabled teams left out of it); the file on disk stays as it was. The GUI migrates the same cases to the same file (gui/src/validate.test.ts)."""
    old = older(21, case["edits"])
    loaded = load(tmp_path, old)
    teams = [{k: v for k, v in t.items() if k != "enabled"} for t in old["teams"]]
    want = {**old, "version": settings.CURRENT_VERSION, "teams": teams, "team_queue": case["team_queue"], **ADDED,
            **{k: CASES["valid"][k] for k in CASES["added_v25"]}, "gift_lists": None}
    assert {**loaded, "gift_lists": None} == want
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8")) == old


@pytest.mark.parametrize("case", CASES["too_old"], ids=lambda c: str(c["version"]))
def test_shared_too_old(tmp_path, case):
    """The GUI refuses the same files in the same words (gui/src/validate.test.ts)."""
    assert errors(tmp_path, {**CASES["valid"], "version": case["version"]}) == [case["error"]]


def test_a_run_stops_on_a_too_old_file_and_logs_why(tmp_path, monkeypatch):
    # #653: PlanRun fails before it looks at the screen (no context needed), as for any bad settings, and its log says why.
    import run_start_actions

    case = CASES["too_old"][0]
    patch_all(monkeypatch, "ROOT", tmp_path)
    logs = []
    patch_all(monkeypatch, "log", logs.append)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps({**VALID, "version": case["version"]}), encoding="utf-8")
    assert run_start_actions.PlanRun().run(None, None) is False
    assert logs == [f"stop: Invalid settings:\n- {case['error']}"]


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
