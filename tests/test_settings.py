import copy
import json
from pathlib import Path

import pytest

import settings
from settings import SettingsError, load_settings

DATA = Path(__file__).parent.parent / "assets" / "resource" / "base" / "data"
SEARCH = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
RECIPES = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
KEYWORDS = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]
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
        "gift_list": "default", "sell_max_tier": 4, "sell_vestiges": False, **kw,
    }


def gift_list(keyword="Burn", **kw):
    """What the version 11 migration makes of a team of this main keyword that keeps nothing else, worked out from the data
    files on their own: the keyword's buyable gifts wanted, the rest of its gifts and every keywordless gift kept (a vestige only when keep_gifts names it)."""
    want = sorted(g["id"] for g in SEARCH if g["keyword"] == keyword)
    every = SEARCH + RECIPES["gifts"] + RECIPES["materials"]
    keep = {g["id"] for g in every if g["keyword"] in (keyword, "Keywordless")}
    gorder = {k: [g["id"] for tier in (3, 2, 1) for g in SEARCH if g["keyword"] == k and g["tier"] == tier] for k in KEYWORDS}
    return {
        "order": [keyword] + [k for k in KEYWORDS if k != keyword], "want": want, "keep": sorted(keep - set(want)),
        "gorder": gorder, "fusion_condition": "any", **kw,
    }


VALID = {
    "version": 11,
    "language": "zh_tw",
    "run": {
        "difficulty": "auto", "runs": 1, "weekly_bonus_use": "hard", "weekly_bonus_amount": "all",
        "stop_when_weekly_bonus_out": False, "starlight_unaffordable": "skip", "wipe_retries": 2,
        "after_retries": "stop", "webhook_url": "", "theme_pack_refresh": "all",
        "auto_accept_terms": True, "auto_download": True,
    },
    "deployment_order_plans": [{"id": "d1", "name": "Bleed order", "order": ORDER}],
    "starlight_plans": [{"id": "s1", "name": "Cheap", **STARLIGHT}],
    "theme_pack_plans": [{"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5}, "threshold": 0, "unlisted": 0, "event_packs": "weight"}],
    "gift_lists": [{"id": "g1", "name": "Mine", "order": KEYWORDS, "want": [9053], "keep": [9071], "gorder": {"Burn": [9071, 9053]},
                    "fusion_condition": "upgrade"}],
    "teams": [
        team("a", 1, deployment_order={"plan": "d1"}, starlight={"plan": "s1"}, theme_pack_plan="p1", gift_list="g1"),
        team("b", 2),
    ],
    "event_overrides": [{"question": "Q?", "option": "Yes"}],
    "trial_risk_overrides": [{"trial": "Growth I", "risk": 3}],
}


def as_v10(valid):
    """The same settings as version 10 wrote them: the teams keep the shop's keep settings themselves, there are no lists."""
    old = copy.deepcopy(valid)
    old["version"] = 10
    del old["gift_lists"]
    for t in old["teams"]:
        del t["gift_list"]
        t.update(keep_keywords=[], keywordless="keep", keep_gifts=[], fusion_condition="any")
    return old


V10 = as_v10(VALID)
# What migrating V10 gives: both teams keep nothing but Burn, so they share one list, named after the first team.
MIGRATED = {**VALID, "gift_lists": [{"id": "gift-list-1", "name": "Team a", **gift_list()}],
            "teams": [{**t, "gift_list": "gift-list-1"} for t in VALID["teams"]]}
VALID_FROM_ZEROS = {**MIGRATED, "run": {**VALID["run"], "runs": None}}  # version 5's 0 run limit migrated


def load(tmp_path, data):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    return load_settings(tmp_path)


def errors(tmp_path, data):
    with pytest.raises(SettingsError) as e:
        load(tmp_path, data)
    return e.value.errors


def edited(fn, base=VALID):
    data = copy.deepcopy(base)
    fn(data)
    return data


def edited10(fn):
    return edited(fn, V10)


def test_valid_settings_load(tmp_path):
    loaded = load(tmp_path, VALID)
    assert {**loaded, "gift_lists": None} == {**VALID, "gift_lists": None}
    assert loaded["gift_lists"] == [{**VALID["gift_lists"][0], "gorder": {**gift_list()["gorder"], "Burn": [9071, 9053] + [i for i in gift_list()["gorder"]["Burn"] if i not in (9071, 9053)]}}]


def test_loading_drops_ids_no_data_file_has_and_fills_gorder(tmp_path):
    # An id a new season removed is ignored, even when it is in want and keep (the GUI drops it on load and warns).
    data = edited(lambda d: d["gift_lists"][0].update(want=[9053, 424242], keep=[9071, 424242], gorder={"Burn": [9071, 5]}))
    loaded = load(tmp_path, data)["gift_lists"][0]
    assert (loaded["want"], loaded["keep"]) == ([9053], [9071])
    assert loaded["gorder"]["Burn"][:2] == [9071, 9053] and sorted(loaded["gorder"]["Burn"]) == sorted(gift_list()["gorder"]["Burn"])
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
])
def test_schema_errors_name_the_field(tmp_path, fn, where):
    assert any(e.startswith(where + ":") for e in errors(tmp_path, edited(fn)))


def test_newer_version_is_refused(tmp_path):
    assert "newer" in errors(tmp_path, {**VALID, "version": 12})[0]


def test_version_1_gets_guard_turns_off(tmp_path):
    old = edited10(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [(t.pop("guard_turns"), t.pop("gift_search"), t.pop("allow_white_gossypium")) for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 1}) == VALID_FROM_ZEROS


def test_version_2_gets_gift_search_off(tmp_path):
    old = edited10(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [(t.pop("gift_search"), t.pop("allow_white_gossypium")) for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 2}) == VALID_FROM_ZEROS


def test_version_3_refreshes_all_avoid_theme_packs_as_before(tmp_path):
    old = edited10(lambda d: [old_numbers(d)] + [d["run"].pop("theme_pack_refresh")] + [t.pop("allow_white_gossypium") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 3}) == VALID_FROM_ZEROS


def old_numbers(d):
    """V10 as version 5 wrote it: 0 for no run limit and a whole HARD run, nothing kept out of the shop."""
    d["run"]["runs"] = 0
    for t in d["teams"]:
        t.update(hard_from_floor=0)
    no_keep(d)


def no_keep(d):
    """V10 as version 6 wrote it: no keep fields."""
    for t in d["teams"]:
        for k in ("keep_keywords", "keywordless", "keep_gifts", "sell_max_tier", "sell_vestiges"):
            t.pop(k)


def test_version_5_zeros_become_switches(tmp_path):
    # #137: runs 0 -> off (no limit); hard_from_floor 0 (the whole run HARD) -> on from floor 1. min_alive 0 stays: no check.
    assert load(tmp_path, {**edited10(old_numbers), "version": 5}) == VALID_FROM_ZEROS


def test_version_5_numbers_stay(tmp_path):
    def numbers(d):
        d["run"].update(runs=3)
        for t in d["teams"]:
            t.update(hard_from_floor=3, min_alive=5)
    assert load(tmp_path, {**edited10(lambda d: [numbers(d), no_keep(d)]), "version": 5}) == edited(numbers, MIGRATED)


def test_version_6_keeps_what_the_shop_kept_before(tmp_path):
    # #77: only the main keyword's and keywordless gifts (and the observed ones) stayed out of fusions and sales.
    assert load(tmp_path, {**edited10(no_keep), "version": 6}) == MIGRATED


def test_version_7_accepts_terms_and_downloads(tmp_path):
    # The user's decision (2026-10-21): the bot may tick the User Agreement and accept downloads.
    old = edited10(lambda d: [d["run"].pop("auto_accept_terms"), d["run"].pop("auto_download")])
    assert load(tmp_path, {**old, "version": 7}) == MIGRATED


def test_version_9_fuses_as_before(tmp_path):
    # #263: any, the fusion the shop made before the condition existed.
    old = edited10(lambda d: [t.pop("fusion_condition") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 9}) == MIGRATED


def v8_plan(marks):
    """V10 as version 8 wrote it, its theme pack plan holding these marks."""
    def fn(d):
        plan = d["theme_pack_plans"][0]
        for k in ("weights", "threshold", "unlisted", "event_packs"):
            plan.pop(k)
        plan["marks"] = marks
    return {**edited10(fn), "version": 8}


def test_version_8_theme_pack_marks_become_weights(tmp_path):
    # #240: prefer / neutral / avoid -> 5 / 0 / -5, threshold 0, unlisted 0, event packs by weight: picks as before.
    marks = {"Automated Factory": "avoid", "The Forgotten": "prefer", "Lake World": "neutral"}
    plan = load(tmp_path, v8_plan(marks))["theme_pack_plans"][0]
    assert plan == {"id": "p1", "name": "Mine", "weights": {"Automated Factory": -5, "The Forgotten": 5, "Lake World": 0},
                    "threshold": 0, "unlisted": 0, "event_packs": "weight"}


def test_version_8_bad_mark_stays_an_error(tmp_path):
    assert any(e.startswith("theme_pack_plans/0/weights/X:") for e in errors(tmp_path, v8_plan({"X": "love"})))


def test_version_4_teams_may_hold_white_gossypium_as_before(tmp_path):
    old = edited10(lambda d: [old_numbers(d)] + [t.pop("allow_white_gossypium") for t in d["teams"]])
    assert load(tmp_path, {**old, "version": 4}) == VALID_FROM_ZEROS


def test_old_version_is_migrated_in_memory(tmp_path, monkeypatch):
    def v0_to_v1(d):
        d["language"] = d.pop("lang")
        return d

    monkeypatch.setattr(settings, "MIGRATIONS", {**settings.MIGRATIONS, 0: v0_to_v1})
    old = {**edited10(lambda d: d.pop("language")), "version": 0, "lang": "en_us"}
    assert load(tmp_path, old)["language"] == "en_us"
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))["version"] == 0


def test_unmigratable_version(tmp_path):
    assert "cannot be migrated" in errors(tmp_path, {**VALID, "version": 0})[0]


@pytest.mark.parametrize("fn, expected", [
    (lambda d: [t.update(enabled=False) for t in d["teams"]], "set up a team"),
    (lambda d: d.update(teams=[]), "set up a team"),
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
    (lambda d: d["starlight_plans"].append({**d["starlight_plans"][0], "name": "Other"}), "starlight_plans: id 's1'"),
    (lambda d: d["deployment_order_plans"].append({"id": "d2", "name": "Bleed order", "order": ORDER}),
     "deployment_order_plans: name 'Bleed order'"),
    (lambda d: d["event_overrides"].append({"question": "Q?", "option": "No"}), "event_overrides: question 'Q?'"),
    (lambda d: d["trial_risk_overrides"].append({"trial": "Growth I", "risk": 1}), "trial_risk_overrides: trial 'Growth I'"),
])
def test_cross_checks(tmp_path, fn, expected):
    assert any(expected in e for e in errors(tmp_path, edited(fn)))


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


def test_shared_valid10_migrates_and_loads(tmp_path):
    loaded = load(tmp_path, CASES["valid10"])
    assert loaded["version"] == 11 and [t["gift_list"] for t in loaded["teams"]] == ["gift-list-1", "gift-list-2"]


@pytest.mark.parametrize("case", CASES["migrations"], ids=lambda c: c["name"])
def test_shared_migrations(tmp_path, case):
    """The GUI runs the same cases (gui/src/validate.test.ts); the migrated file must pass both layers of checks."""
    old = apply_edits(CASES["valid10"], case["edits"])
    assert settings.gift_lists_from_v10(old["teams"])[2] == case["dropped"]
    data = load(tmp_path, old)
    assert [t["gift_list"] for t in data["teams"]] == case["teams"]
    assert [g["id"] for g in data["gift_lists"]] == [x["id"] for x in case["lists"]]
    for got, want in zip(data["gift_lists"], case["lists"]):
        assert (got["id"], got["name"], got["order"][0], got["fusion_condition"]) == (want["id"], want["name"], want["order_first"], want["fusion_condition"])
        assert (len(got["want"]), len(got["keep"])) == (want["want_count"], want["keep_count"])
        assert (sum(got["want"]), sum(got["keep"])) == (want["want_sum"], want["keep_sum"])
        assert set(want["want_has"]) <= set(got["want"]) and set(want["keep_has"]) <= set(got["keep"])
        assert not set(want["keep_lacks"]) & set(got["keep"])
    assert all(g["gorder"] == gift_list()["gorder"] for g in data["gift_lists"])
    assert all(not {"keep_keywords", "keywordless", "keep_gifts", "fusion_condition"} & t.keys() for t in data["teams"])


@pytest.mark.parametrize("case", CASES["clean_gift_list"], ids=lambda c: c["name"])
def test_shared_clean_gift_list(case):
    cleaned, dropped = settings.clean_gift_list(case["list"])
    assert (cleaned["want"], cleaned["keep"], dropped) == (case["want"], case["keep"], case["dropped"])
    assert list(cleaned["gorder"]) == KEYWORDS
    for kw, head in case["gorder_head"].items():
        assert cleaned["gorder"][kw][: len(head)] == head
    for kw, size in case["gorder_size"].items():
        assert len(cleaned["gorder"][kw]) == size
    assert all(sorted(ids) == sorted(g["id"] for g in SEARCH if g["keyword"] == kw) for kw, ids in cleaned["gorder"].items())


def test_version_10_keeps_what_the_team_kept(tmp_path):
    # #292: the main keyword's buyable gifts are wanted; its other gifts, the keep_keywords', every keywordless gift (whatever
    # keywordless said) and the matching keep_gifts are kept; the shop's old fusion_condition goes with the team's list.
    def fn(d):
        a, b = d["teams"]
        a.update(keyword="Tremor", keywordless="fuse_or_sell", fusion_condition="upgrade")
        b.update(keyword="Pierce", keep_keywords=["Blunt"], keywordless="fuse", keep_gifts=[
            {"keyword": "Poise", "tier": 2, "name": "Cigarette Holder"}, {"keyword": "Keywordless", "tier": 1, "name": "Dark Vestige"}])
    data = load(tmp_path, edited(fn, V10))
    first, second = data["gift_lists"]
    assert first == {"id": "gift-list-1", "name": "Team a", **gift_list("Tremor", fusion_condition="upgrade")}
    expected = gift_list("Pierce")
    blunt = {g["id"] for g in SEARCH + RECIPES["gifts"] + RECIPES["materials"] if g["keyword"] == "Blunt"}
    poise = {g["id"] for g in SEARCH if g["keyword"] == "Poise" and g["en"] == "Cigarette Holder"}
    assert poise  # the test names a real gift
    expected["keep"] = sorted(set(expected["keep"]) | blunt | poise | {9991})  # 9991: Dark Vestige, named in keep_gifts
    assert second == {"id": "gift-list-2", "name": "Team b", **expected}


def test_version_10_one_team_one_list_no_team_no_list(tmp_path):
    one = load(tmp_path, edited(lambda d: d.update(teams=d["teams"][:1]), V10))
    assert [g["name"] for g in one["gift_lists"]] == ["Team a"]
    assert settings.gift_lists_from_v10([]) == ([], [], 0)
