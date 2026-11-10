"""tools/event_table.py: the random options' odds and the checks' failure costs (#234)."""

import json
from pathlib import Path

import event_table

TABLE = json.loads((Path(__file__).resolve().parent.parent / "assets/resource/base/data/event_table.json").read_text(encoding="utf-8"))


def _option(event_id, text, where="events"):
    rows = TABLE[where]
    return next(o for e in rows if e["id"] == event_id for o in e["options"] if o["text"] == text)


def test_the_bizarre_machine_gives_its_gift_one_time_in_a_hundred():
    assert _option(971055, "Insert the coin in the slot.")["odds"] == [
        {"p": 0.01, "gets": [["gift", 9800]]}, {"p": 0.99, "gets": [["cost", 50]]}]


def test_a_coin_flip_option_gives_its_gift_half_the_time_and_a_sure_one_has_no_odds():
    assert _option(971003, "Give a few subtle hints.")["odds"] == [
        {"p": 0.5, "gets": [["gift", 9705]]}, {"p": 0.5, "gets": []}]
    assert "odds" not in _option(971003, "You saw nothing.")


def test_a_page_without_story_text_keeps_its_odds_and_the_option_that_leads_there_names_it():
    assert _option(901023, "Sprinkle water.")["next"] == [90102301]
    assert _option(90102301, "Give it more water.", "pages")["odds"] == [
        {"p_per_pick": 0.125, "gets": [["gift", 9023], ["hp", 30, "EveryAlly"], ["sp", 30, "EveryAlly"]]},
        {"p_per_pick": -0.125, "gets": [["next", 90102301]]}]


def test_a_check_keeps_what_its_failure_costs():
    # 901008 Remove the nails: failing the check still gives 40 Cost
    assert _option(901008, "Remove the nails.")["fail"] == [{"p": 1, "gets": [["cost", 40]]}]
    # 858502's checks have no failure result in the data: no field, rather than one that reads as a safe failure
    assert all("fail" not in o for e in TABLE["events"] if e["id"] == 858502 for o in e["options"])


def test_a_check_whose_failure_starts_a_fight_is_marked_so():
    fights = [o for e in TABLE["events"] for o in e["options"]
              if any(g[0] == "battle" for b in o.get("fail", []) for g in b["gets"])]
    assert len(fights) == 14  # client 1.117.0; a new season's table may change it
    assert all(o["kind"].startswith("check") or o["kind"] in ("battle", "followup") for o in fights)


SRC = {"meta": {"client": "9.9.9"}, "events": [
    {"id": 1, "type": "choice", "desc": "A story.", "options": [{
        "text": "Look.", "hint": "Pass to gain a gift", "kind": "check", "gifts": [], "followup": [],
        "results": [{"cond": "Prob_1", "effects": [], "next": 2}],
        "checks": [{"event": 2, "failure": [
            {"cond": "Prob_1", "effects": [{"effect": "LoseHpMpDifferentAmount", "args": [12, 8], "target": "ChosenPersonality"},
                                           {"effect": "StartBattle_Abnormality", "battle": 2060018},
                                           {"effect": "MirrorDungeonLossCost", "cost": 60},
                                           {"effect": "Nothing"}]}]}]}]}]}


def test_build_writes_the_failure_cost_of_a_check_that_starts_a_fight(tmp_path):
    src = tmp_path / "events.json"
    src.write_text(json.dumps(SRC), encoding="utf-8")
    table = json.loads(event_table.build(src, tmp_path))
    assert table["events"][0]["options"][0]["fail"] == [
        {"p": 1, "gets": [["hp", -12, "ChosenPersonality"], ["sp", -8, "ChosenPersonality"], ["battle", 2060018], ["cost", -60]]}]
    assert table["pages"] == []


def test_build_refuses_an_effect_it_does_not_know(tmp_path):
    src = tmp_path / "events.json"
    bad = json.loads(json.dumps(SRC))
    bad["events"][0]["options"][0]["checks"][0]["failure"][0]["effects"] = [{"effect": "SomethingNew"}]
    src.write_text(json.dumps(bad), encoding="utf-8")
    try:
        event_table.build(src, tmp_path)
    except ValueError as e:
        assert "SomethingNew" in str(e)
    else:
        raise AssertionError("an unknown effect was written as nothing")
