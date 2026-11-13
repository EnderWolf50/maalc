"""tools/events_md8.py on a small unpack folder of its own: what each option gives, and which events the pools reach."""
import json

import pytest

import events_md8 as md8


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def gift_form(gid):
    return {"resultForm": {"resultEffect": "GetEgoGift", "itemReward": {"type": "EGO_GIFT", "rewardId": gid}}}


def unpack(tmp_path):
    """Event 100 on a theme floor: a gift (9001), a check whose pass gives 9002, a hidden battle buff. Event 200 only in
    a battle the floor pools. A second file repeats 100 and loses to the first."""
    root = tmp_path / "unpack"
    write(root / "client.json", {"client": "9.9.9"})
    static, en = root / md8.STATIC, root / md8.LOCALIZE
    write(static / "abnormality-event/a.json", {"list": [
        {"id": 100, "actionEvent": {"eachOptionList": [
            {"index": 0, "resultList": [{"resultCondition": "Prob_1", "eventResultDataList": [gift_form(9001)]}]},
            {"index": 1, "resultList": [{"resultCondition": "Prob_1", "eventResultDataList": [], "nextEventID": 101}]},
            {"index": 2, "resultList": [{"resultCondition": "Prob_1", "eventResultDataList": [gift_form(990001)]}]}]}},
        {"id": 101, "personalityEvent": {
            "judgement": {"judgementDataList": [{"attributeType": "CRIMSON"}], "upDownType": "UP", "inclusiveValue": 3, "exclusiveValue": 99},
            "eventResults": [{"eventResult": "SUCCESS", "eventResultDataList": [{"resultCondition": "Prob_1", "eventResultDataList": [gift_form(9002)]}]},
                             {"eventResult": "FAILURE", "eventResultDataList": [{"resultCondition": "Prob_1", "eventResultDataList": []}]}]}},
        {"id": 200, "actionEvent": {"eachOptionList": [{"index": 0, "resultList": []}]}}]})
    write(static / "abnormality-event/b.json", {"list": [{"id": 100, "actionEvent": {"eachOptionList": []}}]})
    write(static / "ego-gift-mirrordungeon/g.json", {"list": [{"id": 9001, "keyword": "Combustion", "tag": ["TIER1"]},
                                                              {"id": 9002, "keyword": "Laceration", "tag": ["TIER2"]}]})
    write(static / "battle-mirrordungeon/x.json", {"list": [{"id": 5000, "abnormalityEventList": [200]}]})
    write(static / "mirrordungeon-theme-floor/f.json", {"list": [
        {"id": 1, "mapGenOption": {"eventPool": [100], "battlePool": [5000]}, "mapGenSequence": []}]})
    write(en / "EN_ActionEvents.json", {"dataList": [
        {"id": 100, "name": "Test Event", "desc": "A story.",
         "options": [{"message": "Take it.", "messageDesc": "Gain a Burn gift"}, {"message": "Look closer.", "messageDesc": "???"},
                     {"message": "Leave."}]},
        {"id": 101, "successDesc": "It holds.", "failureDesc": "It snaps."},
        {"id": 200, "desc": "In battle.", "options": [{"message": "Fine."}]}]})
    write(en / "EN_EGOgift_mirror.json", {"dataList": [{"id": 9001, "name": "Hot Coal"}, {"id": 9002, "name": "Red Thread"}]})
    write(en / "EN_ChoiceEventEffect.json", {"dataList": []})
    return root


@pytest.fixture
def out(tmp_path):
    """The folder run wrote the table of unpack() into."""
    md8.run(unpack(tmp_path), tmp_path / "out")
    return tmp_path / "out"


def test_options_get_their_kind_gifts_and_checks(out):
    doc = json.loads((out / "events-md8.json").read_text(encoding="utf-8"))
    assert doc["meta"] == {"client": "9.9.9", "dungeon": 8, "events": 3, "choiceEvents": 2, "checkEvents": 1, "mapEvents": 2,
                           "battleEvents": 1}
    event = {e["id"]: e for e in doc["events"]}
    take, look, leave = event[100]["options"]
    assert event[100]["file"] == "a.json" and event[100]["title"] == "Test Event"  # the first file wins
    assert [o["kind"] for o in (take, look, leave)] == ["direct", "check", "other"]
    assert [(g["id"], g["name"], g["keyword"], g["tier"], g["how"]) for g in take["gifts"]] == [(9001, "Hot Coal", "Burn", "TIER1", "direct")]
    assert [(g["id"], g["keyword"], g["how"]) for g in look["gifts"]] == [(9002, "Bleed", "check_pass")]
    assert look["hintHidden"] and look["checks"][0]["sins"] == ["Wrath"] and look["checks"][0]["successText"] == "It holds."
    assert leave["gifts"] == [] and leave["results"][0]["effects"][0]["hiddenBuff"] == 990001  # a battle buff, no gift
    assert (event[101]["scope"], event[101]["root"], event[101]["parent"]) == ("map", False, [100, 1])
    assert (event[200]["scope"], event[200]["root"], event[200]["battles"]) == ("battle", True, [5000])
    assert event[100]["themeFloors"] == [1]


def test_the_other_files_count_and_list_what_the_table_holds(out):
    cov = json.loads((out / "events-md8-coverage.json").read_text(encoding="utf-8"))
    assert cov["coverage"]["kinds"] == {"direct": 1, "check": 1, "other": 2}
    assert cov["hiddenHint"] == [[100, 1, "check"]] and cov["coverage"]["optionsNoHintAtAll"] == 2
    assert "| 100 | Test Event | 0. Take it. | Gain a Burn gift | direct | Burn Hot Coal (direct) |" in (
        (out / "events-md8-summary.md").read_text(encoding="utf-8"))
    rows = (out / "events-md8.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(rows) == 1 + 4  # the header, then an option a row (event 101 is a check: it has none)


def test_main_reads_the_main_checkouts_unpack_and_writes_to_its_out_by_default(tmp_path, monkeypatch):
    root = unpack(tmp_path)
    monkeypatch.setattr(md8, "local_dir", lambda *parts: root)
    md8.main([])
    assert (root / "out/events-md8.json").is_file()
    md8.main([str(tmp_path / "elsewhere")])
    assert (tmp_path / "elsewhere/events-md8-summary.md").is_file()
