import struct
from pathlib import Path

import pytest
from PIL import Image

import sin_icons as si

OUT = Path(__file__).resolve().parent.parent / "assets/resource/base/data/sin_icons"
# What tools/sin_icons.py writes: sin -> size of the game's "BattleUI_Choice 1_<colour>" sprite (Wrath's is 4 px shorter)
SIZES = {"Wrath": (120, 124), "Lust": (120, 128), "Sloth": (120, 128), "Gluttony": (120, 128), "Gloom": (120, 128),
         "Pride": (120, 128), "Envy": (120, 128)}
MAX_BYTES = 100_000  # the 7 icons together (lc-helper's overlay draws them at a fraction of this size)


def keyed(entries):
    """A serialized List<{int key, PPtr}>: the count, then key, fileID and pathID of each entry."""
    return struct.pack("<i", len(entries)) + b"".join(struct.pack("<iiq", k, f, p) for k, f, p in entries)


def test_a_keyed_list_reads_its_entries_and_says_where_it_ends():
    raw = b"xx" + keyed([(0, 0, 500), (1, 2, 501)]) + b"tail"
    found, end = si.keyed_list(raw, 2)
    assert found == {0: (0, 500), 1: (2, 501)}
    assert raw[end:] == b"tail"


def test_bytes_that_are_not_a_list_stop_the_tool():
    with pytest.raises(SystemExit, match="not a keyed list"):
        si.keyed_list(struct.pack("<i", 9999) + bytes(64), 0)


def test_the_sins_are_in_the_attribute_order_of_the_game():
    assert list(si.SINS) == ["Wrath", "Lust", "Sloth", "Gluttony", "Gloom", "Pride", "Envy"]
    assert [c.title() for c in si.COLOURS] == ["Crimson", "Scarlet", "Amber", "Shamrock", "Azure", "Indigo", "Violet"]


def test_the_attribute_order_is_checked_against_the_localization():
    rows = [{"id": "CRIMSON", "name": "Wrath"}, {"id": "SCARLET", "name": "Lust"}, {"id": "AMBER", "name": "Sloth"},
            {"id": "SHAMROCK", "name": "Glut."}, {"id": "AZURE", "name": "Gloom"}, {"id": "INDIGO", "name": "Pride"},
            {"id": "VIOLET", "name": "Envy"}, {"id": "WHITE", "name": "Mad."}]  # the game's list, with its abbreviation
    si.check_sin_order(rows)
    rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(SystemExit, match="EN_AttributeText"):
        si.check_sin_order(rows)


def test_a_sprite_of_another_colour_stops_the_tool():
    si.check_colour("BattleUI_Choice 1_Crimson", "CRIMSON")
    with pytest.raises(SystemExit, match="order broken"):
        si.check_colour("BattleUI_Choice 1_Azure", "CRIMSON")


def test_every_sin_has_its_icon_at_the_games_size():
    assert {f.stem: Image.open(f).size for f in OUT.glob("*.png")} == SIZES
    assert all(Image.open(f).mode == "RGBA" for f in OUT.glob("*.png"))


def test_the_icons_stay_small():
    assert sum(f.stat().st_size for f in OUT.glob("*.png")) < MAX_BYTES
