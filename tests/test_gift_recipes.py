import json
from pathlib import Path

from local_dir import local_dir

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
    path = local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data/mirror-dungeon-common-data/mirror-dungeon-common-data-md8.json"
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


def test_39_recipes_use_a_theme_pack_exclusive_gift():
    specific = [g for g in DATA["gifts"] if g.get("specific")]
    assert sum(len(g["recipes"]) for g in specific) == 39
    assert all(g["packs"] == sorted(g["packs"]) and g["packs"] for g in specific)
    assert not [g for g in DATA["gifts"] if "packs" in g and not g.get("specific")]
    by_id = {g["id"]: g for g in DATA["gifts"]}
    assert by_id[9410]["packs"] == [1004, 1005] and by_id[9717]["packs"] == [1104, 1116] and by_id[9248]["packs"] == [1010, 1012]


def test_every_pack_a_recipe_names_has_an_id_in_the_theme_pack_file():
    # #306: recipes speak pack ids, the agent notes the run's packs by id; theme_packs.yaml's pack_ids is where they meet.
    import yaml
    packs = yaml.safe_load((BASE / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))
    ids = packs["pack_ids"]
    assert len(set(ids.values())) == len(ids)  # one name per id
    assert set(packs["packs"]) <= set(ids)  # every listed pack has an id
    named = {p for g in DATA["gifts"] for p in g.get("packs", [])}
    assert sorted(named - set(ids.values())) == []  # a season's new pack id shows up here


def test_the_theme_pack_ids_match_the_game_data_when_it_is_unpacked():
    import pytest
    import yaml
    path = local_dir("unpack") / "raw/Localize/en/EN_MirrorDungeonTheme-1.json"
    if not path.is_file():
        pytest.skip("no unpacked game data")
    names = {r["id"]: r["name"] for r in json.loads(path.read_text(encoding="utf-8-sig"))["dataList"]}
    ids = yaml.safe_load((BASE / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))["pack_ids"]
    wrong = {n: i for n, i in ids.items() if names.get(i) != n and i != 1119}  # 1119's name was read live (theme_packs.yaml)
    assert wrong == {}


def test_specific_and_packs_match_the_game_data_when_it_is_unpacked():
    import pytest
    static = local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data"
    common = static / "mirror-dungeon-common-data/mirror-dungeon-common-data-md8.json"
    if not common.is_file():
        pytest.skip("no unpacked game data")
    pools = {x["id"]: set(x["specificEgoGiftPool"]) for p in (static / "mirrordungeon-theme-floor").glob("*.json")
             for x in json.loads(p.read_text(encoding="utf-8-sig"))["list"] if x.get("specificEgoGiftPool")}
    fixed = json.loads(common.read_text(encoding="utf-8-sig"))["egoGiftCombineFixedTable"]["combineFixed"]
    for g in (g for g in DATA["gifts"] if "recipes" in g):
        mine = [c for c in fixed if c["resultEgoGiftId"] == g["id"]]
        assert g.get("specific", False) == any(c.get("isSpecific") for c in mine) == all(c.get("isSpecific") for c in mine), g["id"]
        if g.get("specific"):  # the packs of all the gift's recipes' exclusive ingredients
            used = {i for c in mine for i in c["requiredEgoGiftIds"]}
            assert g["packs"] == sorted(p for p, pool in pools.items() if pool & used), g["id"]
    assert sum(1 for c in fixed if c.get("isSpecific")) == 39


def test_the_five_vestiges_are_data_ids_9991_to_9995_keywordless_tier_i_to_v():
    # #161: agent/settings.py and the GUI take the vestiges (ids, names, tiers) from here, not from the schema.
    assert [(v["id"], v["tier"], v["keyword"], v["en"]) for v in DATA["vestiges"]] == [
        (9991, 1, "Keywordless", "Dark Vestige"), (9992, 2, "Keywordless", "Faint Vestige"), (9993, 3, "Keywordless", "Twinkling Vestige"),
        (9994, 4, "Keywordless", "Brilliant Vestige"), (9995, 5, "Keywordless", "Lunar Vestige")]
    assert all(v["zh"] for v in DATA["vestiges"])


def test_the_pack_pools_hold_the_check_up_packs_materials_of_the_9780_fusion():
    # #417: "pack_gifts" is pack id -> the gifts of its specificEgoGiftPool; 9778 and 9779 (materials of 9780) are in both Check-up packs.
    import yaml
    pools = DATA["pack_gifts"]
    ids = yaml.safe_load((BASE / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))["pack_ids"]
    assert ids["LCB Regular Check-up"] == 1115 and ids["LCB Regular Check-up BokGak"] == 1125
    assert {9778, 9779} <= set(pools["1115"]) and {9778, 9779} <= set(pools["1125"])
    assert next(g for g in DATA["gifts"] if g["id"] == 9780)["packs"] == [1115, 1125]
    assert all(pool == sorted(set(pool)) for pool in pools.values()) and list(pools) == sorted(pools, key=int)


def test_every_pack_a_pool_names_is_a_theme_pack_and_every_pool_gift_a_known_gift():
    import yaml
    ids = set(yaml.safe_load((BASE / "data" / "theme_packs.yaml").read_text(encoding="utf-8"))["pack_ids"].values())
    known = SEARCHABLE | {g["id"] for k in ("gifts", "materials", "extra_gifts", "vestiges") for g in DATA[k]}
    pools = DATA["pack_gifts"]
    assert sorted(int(p) for p in pools if int(p) not in ids) == []  # every pool pack is named by theme_packs.yaml (1504 since #387)
    assert {i for pool in pools.values() for i in pool} - known <= {9247}  # the one gift without a name or an icon (note)
    assert all(int(p) in {int(q) for q in pools} for g in DATA["gifts"] for p in g.get("packs", []))  # every recipe pack has a pool


def test_regenerating_the_recipe_data_gives_the_committed_file_when_it_is_unpacked():
    import pytest
    if not (unpack := local_dir("unpack")).joinpath("static").is_dir():
        pytest.skip("no unpacked game data")
    release = json.loads((BASE / "data" / "gift_search.json").read_text(encoding="utf-8"))["zh_release"]
    if not local_dir("llc").joinpath(f"{release}.zip").is_file():
        pytest.skip("no Chinese names release downloaded")
    pytest.importorskip("cv2", reason="cv2 is in the unpack group: `uv sync --group unpack` to run this check")
    import gift_recipes  # noqa: PLC0415
    built, _ = gift_recipes.build(unpack, release)
    assert json.loads(json.dumps(built, ensure_ascii=False)) == DATA  # run `tools/gift_recipes.py --no-icons` when this fails
