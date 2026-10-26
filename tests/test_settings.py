import copy
import json
from pathlib import Path

import pytest

import settings
from settings import SettingsError, load_settings

ORDER = ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu",
         "Heathcliff", "Ishmael", "Rodion", "Sinclair", "Outis", "Gregor"]
STARLIGHT = {"levels": ["none"] * 10, "priority": list(range(1, 11)), "convert_leftover": False}


def team(id, game_team, **kw):
    return {
        "id": id, "name": f"Team {id}", "enabled": True, "game_team": game_team, "keyword": "Burn",
        "usage": "any", "hard_from_floor": 1, "deployment_order": {"custom": ORDER},
        "starlight": {"custom": STARLIGHT}, "theme_pack_plan": "default",
        "reward_cards": ["Starlight", "Random E.G.O Gift", "Cost & Keyword Gift Chance", "Cost", "E.G.O Resource"],
        "shop_refresh_limit": 2, "heal": "revive", "reserve_cost": 0, "min_alive": 0, "guard_turns": 0,
        "trial_risk_weight": "high", "gift_search": {"enabled": False, "gifts": []}, "allow_white_gossypium": True,
        "keep_keywords": [], "keywordless": "keep", "keep_gifts": [], "sell_max_tier": 4,
        "sell_vestiges": False, "fusion_condition": "any", **kw,
    }


VALID = {
    "version": 11,
    "language": "zh_tw",
    "run": {
        "difficulty": "auto", "runs": 1, "weekly_bonus_use": "hard", "weekly_bonus_amount": "all",
        "stop_when_weekly_bonus_out": False, "starlight_unaffordable": "skip", "wipe_retries": 2,
        "after_retries": "stop", "webhook_url": "", "theme_pack_refresh": "all",
        "auto_accept_terms": True, "auto_download": True, "keep_dismissed_screens": True,
    },
    "deployment_order_plans": [{"id": "d1", "name": "Bleed order", "order": ORDER}],
    "starlight_plans": [{"id": "s1", "name": "Cheap", **STARLIGHT}],
    "theme_pack_plans": [{"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5}, "threshold": 0, "unlisted": 0, "event_packs": "weight"}],
    "teams": [
        team("a", 1, deployment_order={"plan": "d1"}, starlight={"plan": "s1"}, theme_pack_plan="p1"),
        team("b", 2),
    ],
    "event_overrides": [{"question": "Q?", "option": "Yes"}],
    "trial_risk_overrides": [{"trial": "Growth I", "risk": 3}],
}


VALID_FROM_ZEROS = {**VALID, "run": {**VALID["run"], "runs": None}}  # version 5's 0 run limit migrated


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
    assert load(tmp_path, VALID) == VALID


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
    (lambda d: d["teams"][0].update(keep_keywords=["Keywordless"]), "teams/0/keep_keywords/0"),  # keywordless says it
    (lambda d: d["teams"][0].update(keywordless=True), "teams/0/keywordless"),
    (lambda d: d["teams"][0].update(sell_max_tier=6), "teams/0/sell_max_tier"),
    (lambda d: d["teams"][0].update(fusion_condition="aggressive"), "teams/0/fusion_condition"),
    (lambda d: d["teams"][0].pop("fusion_condition"), "teams/0"),
    (lambda d: d["teams"][0].update(sell_max_tier=0), "teams/0/sell_max_tier"),
    (lambda d: d["teams"][0].update(keep_keywords=["Bleed", "Bleed"]), "teams/0/keep_keywords"),
    (lambda d: d["teams"][0]["keep_gifts"].append({"keyword": "Bleed", "tier": 4, "name": "X"}), "teams/0/keep_gifts/0"),  # neither a Gift Search gift nor a vestige
])
def test_schema_errors_name_the_field(tmp_path, fn, where):
    assert any(e.startswith(where + ":") for e in errors(tmp_path, edited(fn)))


def test_newer_version_is_refused(tmp_path):
    assert "newer" in errors(tmp_path, {**VALID, "version": 12})[0]


def test_version_1_gets_guard_turns_off(tmp_path):
    old = edited(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [(t.pop("guard_turns"), t.pop("gift_search"), t.pop("allow_white_gossypium")) for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 1}) == VALID_FROM_ZEROS


def test_version_2_gets_gift_search_off(tmp_path):
    old = edited(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [(t.pop("gift_search"), t.pop("allow_white_gossypium")) for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 2}) == VALID_FROM_ZEROS


def test_version_3_refreshes_all_avoid_theme_packs_as_before(tmp_path):
    old = edited(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [t.pop("allow_white_gossypium") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 3}) == VALID_FROM_ZEROS


def old_numbers(d):
    """VALID as version 5 wrote it: 0 for no run limit and a whole HARD run, nothing kept out of the shop."""
    d["run"]["runs"] = 0
    for t in d["teams"]:
        t.update(hard_from_floor=0)
    no_keep(d)


def no_keep(d):
    """VALID as version 6 wrote it: no keep fields."""
    for t in d["teams"]:
        for k in ("keep_keywords", "keywordless", "keep_gifts", "sell_max_tier", "sell_vestiges"):
            t.pop(k)


def test_version_5_zeros_become_switches(tmp_path):
    # #137: runs 0 -> off (no limit); hard_from_floor 0 (the whole run HARD) -> on from floor 1. min_alive 0 stays: no check.
    expected = edited(lambda d: d["run"].update(runs=None))
    assert load(tmp_path, {**edited(old_numbers), "version": 5}) == expected


def test_version_5_numbers_stay(tmp_path):
    def numbers(d):
        d["run"].update(runs=3)
        for t in d["teams"]:
            t.update(hard_from_floor=3, min_alive=5)
    assert load(tmp_path, {**edited(lambda d: [numbers(d), no_keep(d)]), "version": 5}) == edited(numbers)


def test_version_6_keeps_what_the_shop_kept_before(tmp_path):
    # #77: only the main keyword's and keywordless gifts (and the observed ones) stayed out of fusions and sales.
    assert load(tmp_path, {**edited(no_keep), "version": 6}) == VALID


def test_version_7_accepts_terms_and_downloads(tmp_path):
    # The user's decision (2026-10-21): the bot may tick the User Agreement and accept downloads.
    old = edited(lambda d: [d["run"].pop("auto_accept_terms"), d["run"].pop("auto_download")])
    assert load(tmp_path, {**old, "version": 7}) == VALID


def test_version_10_keeps_the_dismissed_screens(tmp_path):
    # #244: on, so the first run after the update already keeps them.
    old = edited(lambda d: d["run"].pop("keep_dismissed_screens"))
    assert load(tmp_path, {**old, "version": 10}) == VALID


def test_version_9_fuses_as_before(tmp_path):
    # #263: any, the fusion the shop made before the condition existed.
    old = edited(lambda d: [t.pop("fusion_condition") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 9}) == VALID


def v8_plan(marks):
    """VALID as version 8 wrote it, its theme pack plan holding these marks."""
    def fn(d):
        plan = d["theme_pack_plans"][0]
        for k in ("weights", "threshold", "unlisted", "event_packs"):
            plan.pop(k)
        plan["marks"] = marks
    return {**edited(fn), "version": 8}


def test_version_8_theme_pack_marks_become_weights(tmp_path):
    # #240: prefer / neutral / avoid -> 5 / 0 / -5, threshold 0, unlisted 0, event packs by weight: picks as before.
    marks = {"Automated Factory": "avoid", "The Forgotten": "prefer", "Lake World": "neutral"}
    plan = load(tmp_path, v8_plan(marks))["theme_pack_plans"][0]
    assert plan == {"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5, "The Forgotten": 5, "Lake World": 0},
                    "threshold": 0, "unlisted": 0, "event_packs": "weight"}


def test_version_8_bad_mark_stays_an_error(tmp_path):
    assert any(e.startswith("theme_pack_plans/0/weights/X:") for e in errors(tmp_path, v8_plan({"X": "love"})))


def test_version_4_teams_may_hold_white_gossypium_as_before(tmp_path):
    old = edited(lambda d: [old_numbers(d)] + [t.pop("allow_white_gossypium") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 4}) == VALID_FROM_ZEROS


def test_old_version_is_migrated_in_memory(tmp_path, monkeypatch):
    def v0_to_v1(d):
        d["language"] = d.pop("lang")
        return d

    monkeypatch.setattr(settings, "MIGRATIONS", {**settings.MIGRATIONS, 0: v0_to_v1})
    old = {**edited(lambda d: d.pop("language")), "version": 0, "lang": "en_us"}
    assert load(tmp_path, old)["language"] == "en_us"
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))["version"] == 0


def test_unmigratable_version(tmp_path):
    assert "cannot be migrated" in errors(tmp_path, {**VALID, "version": 0})[0]


@pytest.mark.parametrize("fn, expected", [
    (lambda d: d["teams"][1].update(game_team=1), "TEAMS #1"),
    (lambda d: d["teams"][0].update(deployment_order={"plan": "gone"}), "teams/0/deployment_order"),
    (lambda d: d["teams"][0].update(starlight={"plan": "gone"}), "teams/0/starlight"),
    (lambda d: d["teams"][0].update(theme_pack_plan="gone"), "teams/0/theme_pack_plan"),
    (lambda d: d["teams"][1].update(id="a"), "teams: id 'a'"),
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
    load(tmp_path, edited(fn))


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
    assert load(tmp_path, CASES["valid"]) == CASES["valid"]
