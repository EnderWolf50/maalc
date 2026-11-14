from types import SimpleNamespace as NS

import pytest
from PIL import Image

import unity_files as uf

CARD = "Assets/Resources_moved/Sprite/Unit/Info/Normal/{}_normal_info.png"


def test_index_lines_are_key_type_and_path_and_a_read_mark_is_dashes():
    lines = ["24b6/8b71\tSprite\ta/b.png", "aaaa/bbbb\t-\t-", "cccc"]  # the last: a bare hash line of an index before #625
    assert uf.index_rows(lines) == [("24b6/8b71", "Sprite", "a/b.png"), ("aaaa/bbbb", "-", "-"), ("cccc", "", "")]


def test_the_bundles_of_a_wanted_sprite_are_found_in_the_index():
    lines = [
        f"24b6/8b71\tTexture2D\t{CARD.format(10101)}",
        f"24b6/8b71\tSprite\t{CARD.format(10101)}",
        "66e4/e37b\tSprite\tAssets/Resources_moved/Sprite/UnitCgThumbnail/Default/10101_normal.png",  # the CG thumbnail: not the card
        f"11aa/0001\tSprite\t{CARD.format(10201)}",
        f"99ff/0002\tTexture2D\t{CARD.format(10301)}",  # a texture alone holds no sprite
        "aaaa/bbbb\t-\t-",
    ]
    cards = {CARD.format(i): i for i in (10101, 10201, 10301)}
    assert uf.sprite_bundles(lines, cards.get) == ["11aa/0001", "24b6/8b71"]


def fake_cache(tmp_path, monkeypatch, bundles):
    """A UnityCache whose index names `bundles` ({key: {path: (type, sprite)}}), and unity() that loads them: returns the keys read."""
    lines = []
    for key, entries in bundles.items():
        (tmp_path / uf.BUNDLES / key).mkdir(parents=True)
        (tmp_path / uf.BUNDLES / key / "__data").write_bytes(b"")
        lines += [f"{key}\t{kind}\t{path}" for path, (kind, _) in entries.items()] + [f"{key}\t-\t-"]
    (tmp_path / uf.INDEX).parent.mkdir(parents=True)
    (tmp_path / uf.INDEX).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    read = []

    def unity(path):
        key = f"{path.parent.parent.name}/{path.parent.name}"
        read.append(key)
        return NS(container={p: NS(type=NS(name=kind), read=lambda s=sprite: s) for p, (kind, sprite) in bundles[key].items()})

    monkeypatch.setattr(uf, "unity", unity)
    return read


def test_each_wanted_sprite_comes_once_from_the_bundles_the_index_names(tmp_path, monkeypatch):
    read = fake_cache(tmp_path, monkeypatch, {
        "bb/v1": {"x/9001.png": ("Sprite", "late 9001"), "x/9002.png": ("Sprite", "9002")},
        "aa/v1": {"x/9001.png": ("Sprite", "9001"), "x/9001.png.tex": ("Texture2D", "texture")},
        "cc/v1": {"x/7.png": ("Sprite", "unwanted")},
    })
    pick = {"x/9001.png": 9001, "x/9002.png": 9002}.get
    assert list(uf.bundle_sprites(tmp_path, pick)) == [(9001, "9001"), (9002, "9002")]  # the first bundle in key order wins
    assert read == ["aa/v1", "bb/v1"]  # cc/v1 holds nothing wanted: not opened


def player_file(names_sizes):
    """unity() of a player-data file holding these sprites ({name: size})."""
    def sprite(name, size):
        r = NS(m_Name=name, image=Image.new("RGBA", size), m_Rect=NS(width=size[0], height=size[1]))
        return NS(type=NS(name="Sprite"), read=lambda: r)
    return NS(objects=[sprite(n, s) for n, s in names_sizes.items()] + [NS(type=NS(name="Texture2D"), read=None)])


def test_player_data_sprites_are_found_by_name_in_their_file_and_checked_by_size(tmp_path, monkeypatch):
    files = {"f1": {"Atlas_1_2": (162, 230), "Atlas_1_3": (10, 10)}, "f2": {"Plate_7": (138, 42)}}
    for f in files:
        (tmp_path / f).write_bytes(b"")
    monkeypatch.setattr(uf, "unity", lambda path: player_file(files[path.name]))
    parts = {"f1": {"frame": ("Atlas_1_2", (162, 230))}, "f2": {"plate": ("Plate_7", (138, 42))}}
    assert {k: im.size for k, im in uf.player_sprites(tmp_path, parts, "the prefab").items()} == {"frame": (162, 230), "plate": (138, 42)}
    # a renumbered atlas: the name now holds another sprite, or none; the tool says which, and what to read again
    files["f2"] = {"Plate_7": (60, 27)}
    with pytest.raises(SystemExit, match=r"Plate_7 in f2: \(60, 27\), expected \(138, 42\): re-read the prefab"):
        uf.player_sprites(tmp_path, parts, "the prefab")
    files["f2"] = {}
    with pytest.raises(SystemExit, match=r"Plate_7 in f2: missing"):
        uf.player_sprites(tmp_path, parts, "the prefab")


def test_a_tight_packed_sprite_gets_its_transparent_margin_back():
    # the boss sprites are 391 x 432 rects whose textureRect drops the empty margin: UnityPy's image is the opaque part only.
    # The card lays out the whole rect, so the art goes back to where textureRectOffset (from the bottom left) puts it
    opaque = Image.new("RGBA", (4, 3), (255, 0, 0, 255))
    sprite = NS(image=opaque, m_Rect=NS(width=10.0, height=8.0), m_RD=NS(textureRectOffset=NS(x=2.0, y=1.0)))
    full = uf.sprite_image(sprite)
    assert full.size == (10, 8)
    assert full.getchannel("A").getbbox() == (2, 4, 6, 7)  # 1 px above the bottom edge, 2 px from the left
    whole = NS(image=opaque, m_Rect=NS(width=4.0, height=3.0), m_RD=NS(textureRectOffset=NS(x=0.0, y=0.0)))
    assert uf.sprite_image(whole) is opaque
