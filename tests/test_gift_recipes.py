import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "assets" / "resource" / "base"
DATA = json.loads((BASE / "data" / "gift_recipes.json").read_text(encoding="utf-8"))
SEARCHABLE = {g["id"] for g in json.loads((BASE / "data" / "gift_search.json").read_text(encoding="utf-8"))["gifts"]}


def test_the_game_s_fusion_gifts_are_all_there():
    # combineFixed: 67 recipes of 59 gifts (8 with two); combineMixed: the Memory of the Moon (9083), 2 of 7 fragments + 3 of 3 memories.
    fixed = [g for g in DATA["gifts"] if "recipes" in g]
    assert len(fixed) == 59 and sum(len(g["recipes"]) for g in fixed) == 67
    assert sum(len(g["recipes"]) == 2 for g in fixed) == 8
    mixed = [g for g in DATA["gifts"] if "groups" in g]
    assert [g["id"] for g in mixed] == [9083]
    assert [(len(x["ids"]), x["need"]) for x in mixed[0]["groups"]] == [(7, 2), (3, 3)]


def test_every_ingredient_is_a_searchable_gift_a_listed_material_or_a_fusion_gift():
    known = SEARCHABLE | {g["id"] for g in DATA["gifts"]} | {m["id"] for m in DATA["materials"]}
    used = {i for g in DATA["gifts"] for r in g.get("recipes", []) for i in r} | {i for g in DATA["gifts"] for x in g.get("groups", []) for i in x["ids"]}
    assert used <= known
    assert not {m["id"] for m in DATA["materials"]} & (SEARCHABLE | {g["id"] for g in DATA["gifts"]})


def test_every_fusion_gift_and_material_has_its_icon_and_an_english_name():
    for g in DATA["gifts"] + DATA["materials"]:
        assert (BASE / "image" / "GiftRecipe" / f"{g['id']}.png").is_file(), g["id"]
        assert g["en"] and 1 <= g["tier"] <= 5, g["id"]


def test_recipes_match_the_game_data_when_it_is_unpacked():
    import pytest
    path = Path(__file__).resolve().parent.parent / ".local/unpack/static/Assets/Resources_moved/StaticData/static-data/mirror-dungeon-common-data/mirror-dungeon-common-data-md8.json"
    if not path.is_file():
        pytest.skip("no unpacked game data")
    table = json.loads(path.read_text(encoding="utf-8-sig"))["egoGiftCombineFixedTable"]
    got = {(g["id"], tuple(r)) for g in DATA["gifts"] for r in g.get("recipes", [])}
    assert got == {(c["resultEgoGiftId"], tuple(c["requiredEgoGiftIds"])) for c in table["combineFixed"]}
    mixed = table["combineMixed"][0]
    assert next(g for g in DATA["gifts"] if "groups" in g)["groups"] == [
        {"ids": mixed["aEgoGiftIds"], "need": mixed["aEgoGiftRequiredNum"]}, {"ids": mixed["bEgoGiftIds"], "need": mixed["bEgoGiftRequiredNum"]}]


def test_chinese_names_are_traditional():
    assert all(g["zh"] for g in DATA["gifts"] + DATA["materials"])
    assert next(g for g in DATA["gifts"] if g["id"] == 9083)["zh"] == "月之記憶"
    assert not [g["id"] for g in DATA["gifts"] + DATA["materials"] if "记" in g["zh"] or "镜" in g["zh"]]
