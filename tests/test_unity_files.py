from types import SimpleNamespace as NS

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
        (tmp_path / uf.CACHE / key).mkdir(parents=True)
        (tmp_path / uf.CACHE / key / "__data").write_bytes(b"")
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
