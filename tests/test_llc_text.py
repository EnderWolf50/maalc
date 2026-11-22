import json
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = {"gift_search": ROOT / "assets/resource/base/data/gift_search.json",
         "gift_recipes": ROOT / "assets/resource/base/data/gift_recipes.json", "graces": ROOT / "assets/resource/base/data/graces.json",
         "gift_effects": ROOT / "assets/resource/base/data/gift_effects.json",
         "theme_pack_names": ROOT / "assets/resource/base/data/theme_pack_names.json"}
DATA = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in FILES.items()}


def gifts(data):
    return data["gifts"] + data.get("materials", [])


def test_every_gift_and_grace_has_a_chinese_name_and_the_graces_their_effects_in_english_and_chinese():
    for key in ("gift_search", "gift_recipes"):
        assert all(g["zh"] for g in gifts(DATA[key])), key
    graces = DATA["graces"]["graces"]
    assert len(graces) == 10
    for g in graces:
        assert g["zh"] and set(g["effects"]) == {"en", "zh"}, g["en"]
        for lang, levels in g["effects"].items():
            assert set(levels) == {"base", "plus", "plus2"}, (g["en"], lang)
            for level, lines in levels.items():
                assert lines, (g["en"], lang, level)
                for runs in lines:  # a line is runs of text, each yellow or not, the next one the other
                    assert runs and all(r["text"] and isinstance(r["up"], bool) for r in runs), (g["en"], lang, level)
                    assert all(a["up"] != b["up"] for a, b in zip(runs, runs[1:])), (g["en"], lang, level)
        # the same effects in both languages: a line for a line, and yellow where the other is
        en, zh = g["effects"]["en"], g["effects"]["zh"]
        for level in en:
            assert len(en[level]) == len(zh[level]), (g["en"], level)
            assert [any(r["up"] for r in runs) for runs in en[level]] == [any(r["up"] for r in runs) for runs in zh[level]], (g["en"], level)


def english(name, level):
    """Grace `name`'s English effect lines at a level, each as its runs' (text, yellow) pairs."""
    g = next(g for g in DATA["graces"]["graces"] if g["en"] == name)
    return [[(r["text"], r["up"]) for r in runs] for runs in g["effects"]["en"][level]]


def test_the_english_effects_read_as_the_game_s_english_starlight_page():
    # tests/screens/StarlightPage.png: the game's English page, every card at base, its keywords in the season's colour
    def text(name):
        return ["".join(t for t, _ in runs) for runs in english(name, "base")]
    assert text("Star of the Beginning") == ["Starting Cost +150", "Theme Pack Selection +1", "Shop E.G.O Gift Choice +1",
                                             "1 Free normal Refresh(es) for Shops"]
    assert text("Moon Star-shop") == ["1 Free Keyword Refresh(es) for Shops", "Upon entering Floor 1, gain 1 random Tier 1 E.G.O Gift(s)"]
    assert text("Favor of the Nebulae") == ["Upon entering Floor 1, all Identities gain 3 Level(s)",
                                            "Upon Floor clear, all Identities gain 1 Level(s) (max 5)"]
    assert text("Starlight Guidance") == ["Max Speed +2", "Gain 1 Clash Power Up", "Gain 1 Damage Up", "Gain 1 Protection"]
    for g in DATA["graces"]["graces"]:  # the base text has no yellow, as the game's
        assert not any(up for runs in english(g["en"], "base") for _, up in runs), g["en"]


def test_the_english_effects_mark_up_what_the_client_s_english_text_colours_yellow():
    # the client's EN_DungeonStartBuffs_MD7.json marks the + / ++ changes with the same <color=#f8c200> as LLC's Chinese
    assert english("Star of the Beginning", "plus2")[0] == [("Starting Cost ", False), ("+250", True)]
    assert english("Star of the Beginning", "plus2")[3] == [("2", True), (" Free normal Refresh(es) for Shops", False)]
    assert english("Chance Comet", "plus2")[1:3] == [[("· Floor 5 or lower : Tier 2~3", True)], [("· Floor 6 or higher : Tier 3~4", True)]]
    assert english("Chance Comet", "plus2")[3] == [
        ("Upon entering Floor 3", False), ("/Floor 5/Floor 7", True), (", gain 1 random ", False), ("Tier 4", True),
        (" E.G.O Gift(s) from the ", False), ("selected Keyword category", True)]
    assert english("Perfected Possibility", "plus")[3] == [("Upon entry, gain 1 Dark Vestige and 1 ", False), ("Faint Vestige", True), (" each", False)]


def test_every_gift_the_gui_shows_has_its_effect_in_english_and_chinese_as_runs():
    # every gift of the GUI's catalog, in its order; gui/src/GiftPopover.test.tsx checks the catalog itself has each one
    import llc_text
    effects, keywords = DATA["gift_effects"]["effects"], DATA["gift_effects"]["keywords"]
    assert list(effects) == [str(i) for i in llc_text.catalog_ids()] and len(effects) == 475  # 1.119.0 added 9292-9300
    for gid, e in effects.items():
        assert set(e) == {"sin", "en", "zh"} and e["sin"] in llc_text.ATTRIBUTE_TYPES, gid
        for lang, runs in ((k, v) for k, v in e.items() if k != "sin"):
            assert runs, (gid, lang)
            for r in runs:  # plain text, a keyword the table names, or styled text
                assert isinstance(r, str) and r or set(r) == {"kw"} and r["kw"] in keywords or r["text"] and set(r) <= {"text", "i", "colour"}, (gid, lang, r)
            # no tag the game parses left in the text: [Combustion] is a keyword run, markup a run's style
            assert "[Combustion]" not in str(runs) and "noparse" not in str(runs), (gid, lang)
    used = {r["kw"] for e in effects.values() for runs in (e["en"], e["zh"]) for r in runs if isinstance(r, dict) and "kw" in r}
    assert set(keywords) == used
    for k, v in keywords.items():  # each with the game's name in both languages, its buff's colour and its icon
        assert v["en"] and v["zh"] and v["colour"] in ("Positive", "Negative", "Neutral") and v["icon"], k


def test_distant_star_reads_as_the_game_s_gift_panel():
    # the game's panel for Distant Star (#764): three Sinking keywords, each its icon and the name in the Negative red
    e = DATA["gift_effects"]["effects"]["9125"]["en"]
    sinking = {"kw": "Sinking"}
    assert e[:7] == ["When activating the ", sinking, " effect(including 'Unique Sinking') on the target with an On Hit effect from a "
                     "Base Attack Skill that inflicts or gains ", sinking, " Potency, ", sinking, " Count, or 'Unique Sinking', heal 3 SP "
                     "at Turn End (2 times per turn per Identity)\n\nIf the said unit was at 45 SP at Turn Start, the effect changes to "
                     "the following: when activating the "]
    assert DATA["gift_effects"]["keywords"]["Sinking"] == {"colour": "Negative", "icon": "Sinking", "en": "Sinking", "zh": "沉淪"}
    assert DATA["gift_effects"]["keywords"]["Breath"]["colour"] == "Positive"  # Poise: a Positive buff, the game's yellow
    assert "燒傷" == DATA["gift_effects"]["keywords"]["Combustion"]["zh"]


def test_each_gift_carries_the_sin_the_game_colours_its_name_by():
    # #786, as the game shows them: the plate of Distant Star (#764's still) and of UPS System (tests/screens/ShopPurchase.png)
    # and Wound Clerid (GiftGet.png), the names on the Gift Search (GiftSearchSelected.png: Smokes and Wires, Rusted Cutting
    # Knife, White Gossypium), each in its sin's colour
    effects = DATA["gift_effects"]["effects"]
    shown = {9125: "VIOLET", 9132: "CRIMSON", 9005: "CRIMSON", 9042: "CRIMSON", 9048: "SCARLET", 9020: "SHAMROCK"}
    assert {i: effects[str(i)]["sin"] for i in shown} == shown


def ego_gift_tables(root, tables):
    """A static data folder of ego-gift tables under `root`: {"<folder>/<file>": [records]}."""
    import llc_text
    for name, records in tables.items():
        path = root / llc_text.STATIC / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"list": records}), encoding="utf-8")
    return root


def test_a_gift_s_sin_is_its_mirror_dungeon_record_s_attribute_type(tmp_path):
    # three gifts carry another attributeType in the plain ego-gift tables (9038, 9111, 9195): the mirror dungeon's record wins
    import llc_text
    unpack = ego_gift_tables(tmp_path, {
        "ego-gift-mirrordungeon/ego-gift-mirrordungeon.json": [{"id": 9038, "attributeType": "AZURE", "tag": ["TIER_3"]}],
        "ego-gift/ego-gift.json": [{"id": 9038, "attributeType": "VIOLET"}, {"id": 9006, "attributeType": "AMBER"}],
        "ego-gift-mirrordungeon/hidden-ego-gift-mirrordungeon.json": [{"id": 990001}]})
    assert llc_text.gift_sins(unpack, [9038, 9006]) == {9038: "AZURE", 9006: "AMBER"}


@pytest.mark.parametrize("record", [{"id": 9500}, {"id": 9500, "attributeType": "NEUTRAL"}])
def test_a_gift_the_gui_shows_with_no_sin_stops_the_tool(tmp_path, record):
    # every gift of client 1.118.1 and 1.119.0 has one; the GUI would have no plate for one that has not
    import llc_text
    unpack = ego_gift_tables(tmp_path, {"ego-gift-mirrordungeon/a.json": [{"id": 9001, "attributeType": "CRIMSON"}, record]})
    with pytest.raises(ValueError, match="9500"):
        llc_text.gift_sins(unpack, [9001, 9500])


def test_two_mirror_dungeon_records_of_a_gift_that_disagree_stop_the_tool(tmp_path):
    import llc_text
    unpack = ego_gift_tables(tmp_path, {"ego-gift-mirrordungeon/a.json": [{"id": 9001, "attributeType": "CRIMSON"}],
                                        "ego-gift-mirrordungeon/b.json": [{"id": 9001, "attributeType": "AZURE"}]})
    with pytest.raises(ValueError, match="9001"):
        llc_text.gift_sins(unpack, [9001])


def test_an_effect_is_runs_a_keyword_tag_its_own_run_and_a_bracketed_note_kept_as_text():
    # #764: the game draws a [tag] that names a keyword as the keyword's icon and name; a note naming none, it prints as written
    import llc_text
    names = {"Combustion": "Burn"}
    assert llc_text.effect_runs("inflict 5 [Combustion] Potency [Cannot Stack]", names) == [
        "inflict 5 ", {"kw": "Combustion"}, " Potency [Cannot Stack]"]
    assert llc_text.effect_runs("[Combustion][Combustion]", names) == [{"kw": "Combustion"}, {"kw": "Combustion"}]


def test_flavour_text_is_a_run_of_its_own_italic_and_in_the_game_s_colour_by_name():
    # the client's EN_EGOgift_a1c8p2.json 2061 ends on <i><color=#a16a3b>...</color></i>, StoryDungeon 2015 on <i>...</i>; the
    # colour is named as the game's ColorCode table names it (#a16a3b: Neutral)
    import llc_text
    coin = "+0.5% damage for every Coin\n\n<i><color=#a16a3b>Artifacts used for the second round.</color></i>"
    assert llc_text.effect_runs(coin, {}) == [
        "+0.5% damage for every Coin\n\n", {"text": "Artifacts used for the second round.", "i": True, "colour": "Neutral"}]
    quote = 'Speed Up next turn\n\n<i>"Taking a backward glance at our trails."</i>'
    assert llc_text.effect_runs(quote, {}) == ["Speed Up next turn\n\n", {"text": '"Taking a backward glance at our trails."', "i": True}]


def test_text_the_game_does_not_parse_is_printed_as_written():
    # <noparse> keeps its text from TextMeshPro's parser (MirrorDungeon 9065); a <word> TextMeshPro has no tag for is printed
    # as it is, the client's English "If there is a <Bloodfiend> among allies" (MirrorDungeon_7) and LLC's <血魔>
    import llc_text
    names = {"Combustion": "Burn"}
    assert llc_text.effect_runs("[<noparse>Dawn Office</noparse> Identities Exclusive Effect] [Combustion]", names) == [
        "[Dawn Office Identities Exclusive Effect] ", {"kw": "Combustion"}]
    assert llc_text.effect_runs("<noparse>[Combustion] <i></noparse>", names) == ["[Combustion] <i>"]
    assert llc_text.effect_runs("If there is a <Bloodfiend> or <Mechanical Amalgam> among allies; 若有<血魔>", names) == [
        "If there is a <Bloodfiend> or <Mechanical Amalgam> among allies; 若有<血魔>"]


def test_the_chinese_is_converted_run_by_run_and_must_read_as_the_text_converted_whole():
    import llc_text
    assert llc_text.effect_runs("使[Sinking]层数增加<i><color=#a16a3b>铜钱</color></i>", {"Sinking": "沉沦"}, llc_text.to_traditional) == [
        "使", {"kw": "Sinking"}, "層數增加", {"text": "銅錢", "i": True, "colour": "Neutral"}]

    def convert(text):  # reads "AB" as one phrase, as OpenCC's phrase table might read one across a keyword's edge
        return text.replace("AB", "X")
    with pytest.raises(ValueError, match="run by run"):
        llc_text.effect_runs("A[K]", {"K": "B"}, convert)


@pytest.mark.parametrize("text", ["<style=highlight>Unique</style>", "<b>bold</b>", "<B>bold</B>", "<color=#5bffde>new</color>",
                                  "<sprite name=X>", "a</color>", "a</i>"])
def test_markup_the_gui_does_not_draw_is_an_error(text):
    # a new mark in a new client, or a closing tag with nothing open: the tool stops rather than drop it (as effect_lines does
    # for a grace's colours). TextMeshPro reads its tags in any case, so <B> is a tag too.
    import llc_text
    with pytest.raises(ValueError, match="markup"):
        llc_text.effect_runs(f"heal 3 SP {text}", {})


def test_a_tag_in_capitals_is_read_as_the_game_reads_it():
    import llc_text
    assert llc_text.effect_runs("a <I><COLOR=#A16A3B>b</COLOR></I>", {}) == ["a ", {"text": "b", "i": True, "colour": "Neutral"}]


def test_the_chinese_text_credits_llc_under_its_non_commercial_license_and_not_the_wiki():
    for key, data in DATA.items():
        assert data["license"] == "CC BY-NC-SA 4.0" and "by-nc-sa" in data["license_url"], key
        assert data["zh_source"].endswith("LocalizeLimbusCompany/LocalizeLimbusCompany") and data["zh_release"].isdigit(), key
        assert "huiji" not in FILES[key].read_text(encoding="utf-8").lower(), key
    assert len({d["zh_release"] for d in DATA.values()}) == 1


def test_every_file_names_the_conversion_it_was_written_with():
    # s2tw, the characters alone (#899)
    for key, data in DATA.items():
        assert re.search(r"\bOpenCC s2tw\b", data["note"]) and "s2twp" not in data["note"], key


def test_the_data_matches_the_llc_release_when_it_is_downloaded():
    import llc_text
    from local_dir import local_dir
    path = local_dir("llc") / f"{DATA['graces']['zh_release']}.zip"
    if not path.is_file():
        pytest.skip("release zip not downloaded (tools/llc_text.py)")
    names = llc_text.gift_names(zipfile.ZipFile(path))
    for key in ("gift_search", "gift_recipes"):
        assert {g["id"]: g["zh"] for g in gifts(DATA[key])} == {g["id"]: names[g["id"]] for g in gifts(DATA[key])}, key


def plain(text):
    """An effect line with nothing in yellow, as effect_lines gives it."""
    return [{"text": text, "up": False}]


def test_traditional_conversion_changes_the_characters_and_keeps_the_words():
    # the user's call of 2026-11-23 (#899): Simplified characters to Traditional ones (OpenCC s2tw), no Taiwan wording (s2twp)
    import llc_text
    assert llc_text.to_traditional("软件 鼠标 信息 内存") == "軟件 鼠標 信息 內存"  # s2twp: 軟體 滑鼠 資訊 記憶體
    assert llc_text.to_traditional("生锈的指针 通过阶层 镜像迷宫 刷新 保存的信念 循环呼吸") == "生鏽的指針 通過階層 鏡像迷宮 刷新 保存的信念 循環呼吸"
    # 松 is both 松 (pine) and 鬆 (loose) in Traditional: s2tw keeps the pine, the fix table makes the hammer's 鬆
    assert llc_text.to_traditional("松肉锤") == "鬆肉錘"
    assert llc_text.effect_lines("<color=#627eff>初始经费</color> +{0}(最多{1})", {"value": 150, "value2": 100}, {}) == [plain("初始經費 +150(最多100)")]
    assert llc_text.effect_lines("获得{2}层 {1}", {"referenceData": {"buffKeyword": "K", "stack": 2, "turn": 0}}, {"K": "守护"}) == [plain("獲得2層 守護")]


def test_an_effect_marks_up_what_its_template_colours_yellow_and_shows_the_keywords_blue_plain():
    # #733: the game prints what a + or ++ level changed in its yellow, <color=#f8c200>; the template says which words
    import llc_text
    assert llc_text.effect_lines("初始<color=#627eff>经费</color> <color=#f8c200>+{0}</color>", {"value": 250}, {}) == [
        [{"text": "初始經費 ", "up": False}, {"text": "+250", "up": True}]]
    # a yellow span across a line break marks the text on both lines
    assert llc_text.effect_lines("获得1件<color=#627eff>饰品</color>\n<color=#f8c200>· 第5层：1~3级\n· 第6层：2~3级</color>", {}, {}) == [
        plain("獲得1件飾品"), [{"text": "· 第5層：1~3級", "up": True}], [{"text": "· 第6層：2~3級", "up": True}]]
    # colours nest: the inner one holds until its own closing tag (TextMeshPro's colour stack)
    assert llc_text.effect_lines("获得<color=#627eff>黯淡的残影、<color=#f8c200>微茫的残影</color></color>各1个", {}, {}) == [
        [{"text": "獲得黯淡的殘影、", "up": False}, {"text": "微茫的殘影", "up": True}, {"text": "各1個", "up": False}]]


def test_a_template_colour_other_than_the_game_s_yellow_and_blue_is_an_error():
    import llc_text
    with pytest.raises(ValueError, match="#5bffde"):
        llc_text.effect_lines("<color=#5bffde>初始经费</color> +{0}", {"value": 150}, {})


def test_a_rerun_without_a_release_keeps_the_one_the_data_carries(tmp_path, monkeypatch):
    import llc_text
    assert llc_text.current_release() == DATA["gift_search"]["zh_release"]
    (tmp_path / "gift_search.json").write_text('{"zh_release": "2099010101"}', encoding="utf-8")
    monkeypatch.setattr(llc_text, "DATA", tmp_path)
    assert llc_text.current_release() == "2099010101"


def test_an_effect_missing_a_value_its_template_needs_is_an_error():
    import llc_text
    with pytest.raises(ValueError):
        llc_text.effect_lines("获得{0}层", {"referenceData": {"buffKeyword": "K", "stack": 2, "turn": 0}}, {"K": "守护"})


def test_the_gift_effects_match_the_llc_release_and_the_client_text_when_both_are_there():
    import llc_text
    from local_dir import local_dir
    zip_path = local_dir("llc") / f"{DATA['gift_effects']['zh_release']}.zip"
    unpack = local_dir("unpack")
    if not (zip_path.is_file() and (unpack / "raw/Localize/en").is_dir() and (unpack / llc_text.BUFFS).is_dir()):
        pytest.skip("release zip or unpacked client data missing")
    keywords, effects = llc_text.gift_effects(zipfile.ZipFile(zip_path), unpack, llc_text.catalog_ids())
    assert (keywords, effects) == (DATA["gift_effects"]["keywords"], DATA["gift_effects"]["effects"])


def test_the_graces_match_the_llc_release_and_the_client_values_when_both_are_there():
    import llc_text
    from local_dir import local_dir
    zip_path = local_dir("llc") / f"{DATA['graces']['zh_release']}.zip"
    static_path = local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-start-buffs/mirrordungeon-start-buffs-08.json"
    if not (zip_path.is_file() and static_path.is_file()):
        pytest.skip("release zip or unpacked client data missing")
    static = json.loads(static_path.read_text(encoding="utf-8-sig"))
    titles, effects = llc_text.grace_texts(zipfile.ZipFile(zip_path), static)
    got = {g["zh"]: g["effects"]["zh"] for g in DATA["graces"]["graces"]}
    assert got == {titles[i]: effects[i] for i in titles}
    if not (local_dir("unpack") / "raw/Localize/en").is_dir():
        pytest.skip("the client's English text missing")
    names, english = llc_text.english_grace_texts(local_dir("unpack"), static)
    assert {g["en"]: g["effects"]["en"] for g in DATA["graces"]["graces"]} == {names[i]: english[i] for i in names}


# #899: the settings GUI shows each theme pack's Chinese name, by its id in theme_packs.yaml's pack_ids.
def theme_packs():
    import yaml
    return yaml.safe_load((ROOT / "assets/resource/base/data/theme_packs.yaml").read_text(encoding="utf-8"))


def test_every_theme_pack_has_a_chinese_name_or_is_listed_as_one_llc_lacks():
    table, names = theme_packs(), DATA["theme_pack_names"]
    missing = set(names["missing"])
    for name in table["packs"]:
        i = table["pack_ids"][name]
        row = names["packs"].get(str(i))
        assert (row is None) == (i in missing), f"{name} ({i}): named and listed as missing, or neither"
        assert row is None or row == {"en": name, "zh": row["zh"]} and row["zh"], f"{name} ({i}): {row}"
    assert sorted(names["packs"], key=int) == sorted(str(i) for i in table["pack_ids"].values() if i not in missing)


def test_a_theme_pack_s_chinese_name_is_llc_s_name_of_its_id_and_a_pack_llc_lacks_is_listed():
    import llc_text
    packs, missing = llc_text.pack_rows({1001: "被遗忘者们", 1119: "憎恶与绝望", 1500: ""},
                                        {"The Forgotten": 1001, "Walpurgis Night: Hatred and Despair": 1119, "New Pack": 1500, "Newer": 1501})
    assert packs == {"1001": {"en": "The Forgotten", "zh": "被遺忘者們"}, "1119": {"en": "Walpurgis Night: Hatred and Despair", "zh": "憎惡與絕望"}}
    assert missing == [1500, 1501]


def test_the_theme_pack_names_match_the_llc_release_when_it_is_downloaded():
    import llc_text
    from local_dir import local_dir
    path = local_dir("llc") / f"{DATA['theme_pack_names']['zh_release']}.zip"
    if not path.is_file():
        pytest.skip("release zip not downloaded (tools/llc_text.py)")
    packs, missing = llc_text.pack_names(zipfile.ZipFile(path), theme_packs()["pack_ids"])
    assert (packs, missing) == (DATA["theme_pack_names"]["packs"], DATA["theme_pack_names"]["missing"])
