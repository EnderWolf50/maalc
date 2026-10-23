import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = {"gift_search": ROOT / "assets/resource/base/data/gift_search.json",
         "gift_recipes": ROOT / "assets/resource/base/data/gift_recipes.json", "graces": ROOT / "gui/src/graces.json"}
DATA = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in FILES.items()}


def gifts(data):
    return data["gifts"] + data.get("materials", [])


def test_every_gift_and_grace_has_a_chinese_name_and_the_graces_their_effects():
    for key in ("gift_search", "gift_recipes"):
        assert all(g["zh"] for g in gifts(DATA[key])), key
    graces = DATA["graces"]["graces"]
    assert len(graces) == 10
    for g in graces:
        assert g["zh"] and set(g["effects"]) == {"base", "plus", "plus2"}, g["en"]
        assert all(g["effects"][level] and all(g["effects"][level]) for level in g["effects"]), g["en"]


def test_the_chinese_text_credits_llc_under_its_non_commercial_license_and_not_the_wiki():
    for key, data in DATA.items():
        assert data["license"] == "CC BY-NC-SA 4.0" and "by-nc-sa" in data["license_url"], key
        assert data["zh_source"].endswith("LocalizeLimbusCompany/LocalizeLimbusCompany") and data["zh_release"].isdigit(), key
        assert "huiji" not in FILES[key].read_text(encoding="utf-8").lower(), key
    assert len({d["zh_release"] for d in DATA.values()}) == 1


def test_the_data_matches_the_llc_release_when_it_is_downloaded():
    import llc_text
    from local_dir import local_dir
    path = local_dir("llc") / f"{DATA['graces']['zh_release']}.zip"
    if not path.is_file():
        pytest.skip("release zip not downloaded (tools/llc_text.py)")
    names = llc_text.gift_names(zipfile.ZipFile(path))
    for key in ("gift_search", "gift_recipes"):
        assert {g["id"]: g["zh"] for g in gifts(DATA[key])} == {g["id"]: names[g["id"]] for g in gifts(DATA[key])}, key


def test_traditional_conversion_keeps_the_game_s_words():
    import llc_text
    assert llc_text.to_traditional("生锈的指针 通过阶层 镜像迷宫 刷新 松肉锤") == "生鏽的指針 通過階層 鏡像迷宮 刷新 鬆肉錘"
    assert llc_text.effect_line("<color=#5bffde>初始经费</color> +{0}(最多{1})", {"value": 150, "value2": 100}, {}) == "初始經費 +150(最多100)"
    assert llc_text.effect_line("获得{2}层 {1}", {"referenceData": {"buffKeyword": "K", "stack": 2, "turn": 0}}, {"K": "守护"}) == "獲得2層 守護"


def test_a_rerun_without_a_release_keeps_the_one_the_data_carries(tmp_path, monkeypatch):
    import llc_text
    assert llc_text.current_release() == DATA["gift_search"]["zh_release"]
    (tmp_path / "gift_search.json").write_text('{"zh_release": "2099010101"}', encoding="utf-8")
    monkeypatch.setattr(llc_text, "DATA", tmp_path)
    assert llc_text.current_release() == "2099010101"


def test_an_effect_missing_a_value_its_template_needs_is_an_error():
    import llc_text
    with pytest.raises(ValueError):
        llc_text.effect_line("获得{0}层", {"referenceData": {"buffKeyword": "K", "stack": 2, "turn": 0}}, {"K": "守护"})


def test_the_graces_match_the_llc_release_and_the_client_values_when_both_are_there():
    import llc_text
    from local_dir import local_dir
    zip_path = local_dir("llc") / f"{DATA['graces']['zh_release']}.zip"
    static = local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-start-buffs/mirrordungeon-start-buffs-08.json"
    if not (zip_path.is_file() and static.is_file()):
        pytest.skip("release zip or unpacked client data missing")
    titles, effects = llc_text.grace_texts(zipfile.ZipFile(zip_path), json.loads(static.read_text(encoding="utf-8-sig")))
    got = {g["zh"]: g["effects"] for g in DATA["graces"]["graces"]}
    assert got == {titles[i]: effects[i] for i in titles}
