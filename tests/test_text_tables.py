"""tools/text_tables.py (#768): the joined English, Simplified and Traditional text of events, gifts and trials."""

import json
import re

import text_tables as tt


def test_plain_drops_markup_and_edges_and_a_missing_text():
    assert tt.plain("  <color=#f8c200>Hit</color> now \n") == "Hit now"
    assert tt.plain(None) == ""


def test_zh_keeps_llc_s_words_in_taiwan_s_glyphs():
    # #899, as the settings GUI's data files: LLC's words kept (s2twp would write 重新整理 資訊素 機率), Taiwan's glyphs (s2t
    # alone would write 污 爲)
    assert tt.zh("<b>刷新</b> 获得信息素 污秽 概率") == "刷新 獲得信息素 汙穢 概率"
    assert tt.zh("转化为") == "轉化為"


def test_every_table_names_the_one_conversion_it_was_written_with():
    # #899: all LLC text by s2tw and the 松肉 fix, as the settings GUI's data files
    for name in ("event_text.json", "gift_text.json", "trial_text.json"):
        note = json.loads((tt.DATA / name).read_text(encoding="utf-8"))["note"]
        assert re.findall(r"OpenCC (\w+)", note) == ["s2tw"] and "松肉->鬆肉" in note, name


def test_gift_text_names_the_buff_tags_squeezes_blank_lines_and_drops_markup():
    names = {"Combustion": "Burn"}
    text = "Gain <b>[Combustion]</b>.\r\n\n\n\n[Unknown] now"
    assert tt.gift_text(text, names) == "Gain 「Burn」.\n\n「Unknown」 now"


def test_gift_info_reads_keyword_tier_and_both_names_of_a_gift():
    static = [{"id": 9001, "keyword": "Combustion", "tag": ["X", "TIER_2"]}, {"id": 9002, "tag": []}, {"id": 5, "keyword": "Hit"}]
    en = {9001: "Hellterfly’s Dream", 9002: "Perversion"}
    cn = {9001: "地狱蝶之梦", 9002: "倒错症"}
    info = tt.gift_info({9001, 9002}, static, en, cn)
    assert info[9001] == {"en": "Hellterfly's Dream", "zh": "地獄蝶之夢", "keyword": "Burn", "tier": 2}
    assert info[9002] == {"en": "Perversion", "zh": "倒錯症", "keyword": "Keywordless", "tier": None}
    assert 5 not in info
    assert tt.gift_info({9007}, [], {}, {9007: "朱红蛾群"})[9007]["zh"] == "硃紅蛾群"  # Taiwan's 群, not s2t's 羣 (#899): the GUI's name of the gift


def test_event_text_joins_the_full_english_text_to_llc_by_the_event_files_name():
    table = {"events": [{"id": 1, "key": "k", "options": [{"text": "short", "hint": "h"}, {"text": "other", "hint": ""}]}],
             "pages": [{"id": 2, "key": "p", "options": []}]}
    md8 = [{"id": 1, "title": "<b>T</b>", "desc": "Story one", "locFile": "EN_ActionEvents_A.json",
            "options": [{"text": "Full option text"}]},
           {"id": 2, "title": "", "desc": "Page", "locFile": "EN_ActionEvents_A.json", "options": []}]
    llc = {"ActionEvents_A.json": {1: {"desc": "<i>故事</i>", "options": [{"message": "选项", "messageDesc": "有概率获得"}]}}}
    out = tt.event_text(table, md8, lambda name: llc.get(name, {}))
    assert out == {
        "1": {"title": "T", "story": "Story one", "story_cn": "故事", "story_zh": "故事",
              "options": [{"text": "Full option text", "text_cn": "选项", "text_zh": "選項", "hint_cn": "有概率获得", "hint_zh": "有概率獲得"},
                          {"text": "other", "text_cn": "", "text_zh": "", "hint_cn": "", "hint_zh": ""}]},  # no md8 option: the table's text
        "2": {"title": "", "story": "Page", "story_cn": "", "story_zh": "", "options": []}}  # no LLC row: empty Chinese


def test_event_text_reads_a_pages_story_from_eventDesc_when_desc_is_empty():
    table = {"events": [{"id": 1, "key": "k", "options": []}], "pages": []}
    md8 = [{"id": 1, "title": "", "desc": "", "locFile": "EN_X.json", "options": []}]
    out = tt.event_text(table, md8, lambda name: {1: {"desc": "", "eventDesc": "页面"}})
    assert out["1"]["story_cn"] == "页面"


def test_gift_rows_carry_names_both_effects_and_the_enhanced_effect_by_id_plus_10000():
    base = {9006: {"en": "Coffee and Cranes", "zh": "咖啡與紙鶴", "keyword": "Keywordless", "tier": 2}}
    en = {9006: {"name": "x", "desc": "Gain [Combustion]"}, 19006: {"name": "x+", "desc": "Gain 2 [Combustion]"}}
    cn = {9006: {"name": "咖啡与纸鹤", "desc": "获得[Combustion]，转化为信息素"}}  # a gift's effect: Taiwan's 為, LLC's 信息素 (#899)
    rows = tt.gift_rows(base, en, cn, {9006: "咖啡与纸鹤"}, {"Combustion": "Burn"}, {"Combustion": "烧伤"})
    assert rows == {9006: {"en": "Coffee and Cranes", "zh": "咖啡與紙鶴", "cn": "咖啡与纸鹤", "keyword": "Keywordless", "tier": 2,
                           "desc_en": "Gain 「Burn」", "desc_cn": "获得「烧伤」，转化为信息素", "desc_zh": "獲得「燒傷」，轉化為信息素",
                           "plus_en": "Gain 2 「Burn」", "plus_cn": "", "plus_zh": ""}}


def test_first_names_skips_a_row_without_a_name_and_takes_the_first_file_that_names_an_id():
    files = [[{"id": 1, "name": ""}, {"id": 2, "name": "<b>甲</b>"}], [{"id": 1, "name": "乙"}, {"id": 2, "name": "丙"}]]
    assert tt.first_names(files) == {1: "乙", 2: "甲"}


def test_trial_rows_are_keyed_by_buff_id_with_english_simplified_and_traditional_text():
    table = {"trials": {"Offense Level Up I": {"id": "MD511", "pool": 1}, "No Text": {"id": "MD999"}}}
    en = {"MD511": {"desc": "Offense Level +1"}}
    cn = {"MD511": {"name": "攻击等级强化I", "desc": "攻击等级+1，50%概率"}}
    rows = tt.trial_rows(table, en, cn)
    assert rows["MD511"] == {"desc_en": "Offense Level +1", "cn": "攻击等级强化I", "desc_cn": "攻击等级+1，50%概率", "zh": "攻擊等級強化I",
                             "desc_zh": "攻擊等級+1，50%概率"}  # LLC's 概率, not Taiwan's 機率 (#899)
    assert rows["MD999"] == {"desc_en": "", "cn": "", "desc_cn": "", "zh": "", "desc_zh": ""}


def test_dump_writes_the_header_keys_then_one_line_per_id():
    text = tt.dump({"note": "n", "client": "1", "events": {"1": {"a": "é"}, "2": {"a": "b"}}}, "events")
    assert text == '{\n "note": "n",\n "client": "1",\n "events": {\n  "1": {"a": "é"},\n  "2": {"a": "b"}\n }\n}\n'
    assert json.loads(text)["events"]["2"] == {"a": "b"}
