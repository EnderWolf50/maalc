"""tools/game_data.py (#625): which bundles a new client changed, the client version, and the per-file data diff."""

import pytest

import game_data as gd


def test_a_bundle_whose_version_folder_changed_or_is_new_is_pulled():
    device = gd.parse_cache_listing("aa/v1/\nbb/v2/\ncc/v3/\n")
    assert device == {"aa": "v1", "bb": "v2", "cc": "v3"}
    assert gd.changed_bundles(device, {"aa": "v1", "bb": "v1", "dd": "v9"}) == ["bb", "cc"]


def test_the_static_data_comes_from_every_bundle_that_holds_some_changed_or_not():
    # 1.118.1 changed one of the three bundles 1.117.0's static data was in: the other two still hold 15 files (#625).
    index = ["aa/v1\tTextAsset\tAssets/Resources_moved/StaticData/static-data/x/x-1.json", "aa/v1\t-\t-",
             "bb/v2\tSprite\tAssets/Resources_moved/Sprite/a.png", "cc/v3\tTextAsset\tAssets/Resources_moved/StaticData/static-data/y.json"]
    assert gd.static_bundles(index) == {"aa/v1", "cc/v3"}


def unpack_with_a_pull(root):
    """1.117.0 in place (static, one bundle), a 1.118.1 pull of new static data and a new version of that bundle."""
    (root / "client.json").write_text('{"client": "1.117.0"}', encoding="utf-8")
    for d in ("static/a", "raw/UnityCache/aa/v1", "incoming/1.118.1/static/b", "incoming/1.118.1/raw/UnityCache/aa/v2"):
        (root / d).mkdir(parents=True)
    (root / "raw/UnityCache/bb/v9").mkdir(parents=True)  # gone from the device
    (root / "incoming/1.118.1/pulled.json").write_text('{"client": "1.118.1", "bundles": ["aa"], "gone": ["bb"]}', encoding="utf-8")


def test_install_moves_the_pull_in_and_the_replaced_and_gone_files_to_prev(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "local_dir", lambda *parts: tmp_path)  # local_dir("unpack")
    unpack_with_a_pull(tmp_path)
    assert gd.cmd_install(None) == 0
    assert (tmp_path / "static/b").is_dir() and (tmp_path / "raw/UnityCache/aa/v2").is_dir()
    assert (tmp_path / "prev/1.117.0/static/a").is_dir() and (tmp_path / "prev/1.117.0/raw/UnityCache/aa/v1").is_dir()
    assert (tmp_path / "prev/1.117.0/raw/UnityCache/bb/v9").is_dir() and not (tmp_path / "raw/UnityCache/bb").exists()
    assert gd.unpack_client(tmp_path) == "1.118.1" and not (tmp_path / "incoming/1.118.1").exists()


def test_install_moves_nothing_when_a_destination_is_taken(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "local_dir", lambda *parts: tmp_path)  # local_dir("unpack")
    unpack_with_a_pull(tmp_path)
    (tmp_path / "prev/1.117.0/raw/UnityCache/bb").mkdir(parents=True)  # the last move's destination
    with pytest.raises(SystemExit, match="nothing installed"):
        gd.cmd_install(None)
    assert (tmp_path / "static/a").is_dir() and (tmp_path / "incoming/1.118.1/static/b").is_dir()
    assert gd.unpack_client(tmp_path) == "1.117.0"


def test_the_client_version_comes_from_dumpsys():
    text = "Packages:\n  Package [com.ProjectMoon.LimbusCompany]\n    versionCode=1180100\n    versionName=1.118.1\n"
    assert gd.client_version(text) == "1.118.1"


def test_a_data_file_diff_names_the_ids_added_removed_and_changed_per_list():
    old = {"note": "a", "gifts": [{"id": 1, "en": "A"}, {"id": 2, "en": "B"}], "pack_gifts": {"7": [1], "8": [2]},
           "default_list": {"want": [9083, 9285], "order": ["Burn"]}}
    new = {"note": "b", "gifts": [{"id": 2, "en": "B2"}, {"id": 3, "en": "C"}], "pack_gifts": {"7": [1, 3], "9": [4]},
           "default_list": {"want": [9083, 9285, 9302], "order": ["Burn"]}}
    assert gd.id_changes(old, new) == {
        "note": "changed",
        "gifts": {"added": [3], "removed": [1], "changed": [2]},
        "pack_gifts.7": {"added": [3], "removed": []}, "pack_gifts.8": "removed", "pack_gifts.9": "added",
        "default_list.want": {"added": [9302], "removed": []},
    }
    assert gd.id_changes(old, old) == {}
