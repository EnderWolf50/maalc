from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

import grace_icons as gi

GUI = Path(__file__).resolve().parent.parent / "gui/src"
CARD = GUI / "grace_card"
# What tools/grace_icons.py writes for the card (#726): name -> size. The sprites keep the game's size; the page background
# and the price icon are made smaller (PAGE_SIZE, STAR_SIZE). The lit plate is the button's size.
PARTS = {"face": (380, 438), "face-picked": (380, 444), "hover": (365, 432), "button": (209, 69), "button-lit": (209, 69),
         "plus": (54, 56), "plus-lit": (39, 26), "star": (62, 64), "side": (276, 258), "page": (1024, 1024)}
MAX_BYTES = 400_000  # the card's images together (#726)


def solid(size, rgba):
    return Image.new("RGBA", size, rgba)


def white_sprites():
    """Every sprite card_sprites returns, each white at its game size."""
    return {key: solid(size, (255, 255, 255, 255)) for parts in gi.CARD_PARTS.values() for key, (_, size) in parts.items()}


def test_a_tinted_sprite_is_its_white_times_the_colour_and_keeps_its_alpha():
    im = gi.tint(solid((2, 2), (255, 255, 255, 128)), (235, 202, 162))
    assert im.getpixel((0, 0)) == (235, 202, 162, 128)
    assert gi.tint(solid((1, 1), (100, 0, 255, 255)), (235, 202, 162)).getpixel((0, 0)) == (92, 0, 162, 255)


def test_the_lit_plate_is_the_button_with_the_focused_plate_over_its_middle():
    out = gi.over_centre(solid((209, 69), (0, 0, 0, 255)), solid((191, 51), (200, 200, 255, 255)))
    assert out.size == (209, 69)
    assert out.getpixel((9, 9)) == (200, 200, 255, 255) and out.getpixel((199, 59)) == (200, 200, 255, 255)
    assert out.getpixel((8, 8)) == (0, 0, 0, 255) and out.getpixel((200, 60)) == (0, 0, 0, 255)


def test_card_parts_are_the_files_the_gui_reads_at_their_sizes():
    parts = gi.card_parts(white_sprites())
    assert {k: v.size for k, v in parts.items()} == PARTS
    assert parts["plus"].getpixel((0, 0)) == (*gi.PLUS_TINT, 255)


def test_a_card_sprite_of_another_size_stops_the_tool(monkeypatch, tmp_path):
    """A renumbered atlas: the name now holds another sprite. The tool says which, and to read the prefabs again."""
    def sprite(name, size):
        r = NS(m_Name=name, image=solid(size, (0, 0, 0, 255)), m_Rect=NS(width=size[0], height=size[1]))
        return NS(type=NS(name="Sprite"), read=lambda: r)

    def unity(path):
        parts = gi.CARD_PARTS[path.name]
        return NS(objects=[sprite(s, (1, 1) if s == "MainUI_MirrorDungeon8_2_9" else size) for s, size in parts.values()])

    for f in gi.CARD_PARTS:
        (tmp_path / f).write_bytes(b"")
    monkeypatch.setattr(gi, "unity", unity)
    with pytest.raises(SystemExit, match=r"MainUI_MirrorDungeon8_2_9 .*\(1, 1\), expected \(209, 69\).*prefabs"):
        gi.card_sprites(tmp_path)


def test_the_committed_card_images_are_the_tools_and_stay_small():
    files = {f.stem: f for f in CARD.glob("*.webp")}
    assert {k: Image.open(f).size for k, f in files.items()} == PARTS
    assert sum(f.stat().st_size for f in files.values()) < MAX_BYTES
