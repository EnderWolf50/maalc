import json
import struct
from pathlib import Path

import pytest
from PIL import Image

import gift_plates as gp

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "gui/src/gift_plates"
PLATES = json.loads((OUT / "plates.json").read_text(encoding="utf-8"))
EFFECTS = json.loads((ROOT / "gui/src/gift_effects.json").read_text(encoding="utf-8"))["effects"]
SCREENS = ROOT / "tests/screens"
MAX_BYTES = 48_000  # the seven plates together, lossless (#786; 37,020 bytes for client 1.119.0)


def manager(colours_before, pairs, extra_list=((11, 360.0, 1.0, 1.0),)):
    """UIColorManager's bytes as the client lays them out: the MonoBehaviour header and an empty name, its Colors, a list of
    {key, 3 floats}, then the list of {ATTRIBUTE_TYPE key, Color}."""
    raw = bytearray(28) + struct.pack("<i", 0)
    raw += b"".join(struct.pack("<4f", 1, 1, 1, 1) for _ in range(colours_before))
    raw += struct.pack("<i", len(extra_list)) + b"".join(struct.pack("<i3f", *e) for e in extra_list)
    raw += struct.pack("<i", len(pairs)) + b"".join(struct.pack("<i4f", k, *c) for k, c in pairs)
    return bytes(raw) + struct.pack("<i", 0)


def test_the_sin_colours_are_read_from_ui_colour_manager_s_list_by_attribute_type():
    # client 1.118.1's list, WHITE (7), BLACK (8) and NEUTRAL (11) after the seven sins
    game = ["#ff0000", "#fd6600", "#fecc2b", "#9eff00", "#15c3ee", "#004bd5", "#9400dc", "#ffffff", "#464646", "#a16a3b"]
    pairs = [(k, tuple(v / 255 for v in gp.rgb(h)) + (1.0,)) for k, h in zip([*range(9), 11], game)]
    assert gp.sin_colours(manager(gp.COLOURS_BEFORE, pairs)) == dict(zip(gp.ATTRIBUTE_TYPES, game))


@pytest.mark.parametrize("raw", [
    manager(gp.COLOURS_BEFORE - 1, [(k, (0, 0, 0, 1)) for k in range(7)]),  # a field less before the list: the layout moved
    manager(gp.COLOURS_BEFORE, [(k, (0, 0, 0, 1)) for k in range(6)]),  # no VIOLET
    manager(gp.COLOURS_BEFORE, [(k, (0, 0, 0, 0.5)) for k in range(7)]),  # a see-through colour is no plate colour
])
def test_a_colour_list_that_is_not_where_the_layout_puts_it_stops_the_tool(raw):
    with pytest.raises(SystemExit):
        gp.sin_colours(raw)


def white_plate(halftone=255):
    """A 200 x 80 white plate with a dark edge, and a patch of `halftone` grey inside the name's band at the bottom right."""
    im = Image.new("RGBA", (200, 80), (40, 40, 40, 255))
    im.paste((255, 255, 255, 255), (3, 3, 197, 77))
    im.paste((halftone, halftone, halftone, 255), (120, 45, 180, 58))
    return im


def test_a_light_plate_takes_the_dark_ink_on_the_game_s_colour():
    p = gp.plate(white_plate(), "#fecc2b")  # AMBER
    assert (p.ink, p.shade) == ("dark", 1) and p.contrast >= gp.TARGET
    # the sprite times the colour, as the game tints its Image: white takes the colour, the grey edge a darker one
    assert p.image.getpixel((100, 40)) == (0xfe, 0xcc, 0x2b, 255) and p.image.getpixel((0, 0)) == (40, 32, 7, 255)


def test_a_dark_plate_takes_the_light_ink_on_the_game_s_colour():
    p = gp.plate(white_plate(), "#9400dc")  # VIOLET
    assert (p.ink, p.shade) == ("light", 1) and p.contrast >= gp.TARGET


def test_a_plate_neither_ink_holds_on_is_darkened_just_enough_for_the_light_ink():
    # CRIMSON with the sprite's halftone (its dots as dark as 0.57): black fails on the dots, white holds 4.0:1 on the flat red
    p = gp.plate(white_plate(halftone=150), "#ff0000")
    assert p.ink == "light" and 0.85 < p.shade < 1 and gp.TARGET <= p.contrast < gp.TARGET + 0.1


def test_the_halftone_under_the_name_counts_and_the_edge_does_not():
    # black holds 5.25:1 on the flat red, not on a dot of the halftone under the name; the dark edge lies outside the band
    assert gp.plate(white_plate(), "#ff0000").ink == "dark"
    assert gp.plate(white_plate(halftone=150), "#ff0000").ink == "light"
    assert gp.plate(white_plate(halftone=128), "#fecc2b").ink == "light"


def test_each_sin_the_gifts_carry_has_its_plate_and_its_name_holds_4_5_to_1_on_it():
    # measured on the committed pixels: the ink against every pixel of the band the name can cover, halftone included
    assert {e["sin"] for e in EFFECTS.values()} == set(PLATES["plates"]) == set(gp.ATTRIBUTE_TYPES)
    for sin, p in PLATES["plates"].items():
        im = Image.open(OUT / f"{sin}.webp")
        assert im.mode == "RGBA" and im.size == tuple(PLATES["size"]), sin
        assert gp.contrast(im, PLATES["inks"][p["ink"]]) == p["contrast"] >= 4.5, sin
    assert sum(f.stat().st_size for f in OUT.glob("*.webp")) < MAX_BYTES
    assert {f.stem for f in OUT.glob("*.webp")} == set(gp.ATTRIBUTE_TYPES)


def most_common(image, box, keep=lambda c: True):
    pixels = [c for c in Image.open(SCREENS / image).convert("RGB").crop(box).get_flattened_data() if keep(c)]
    return max(set(pixels), key=pixels.count)


@pytest.mark.parametrize("image, box, sin", [
    ("ShopPurchase.png", (350, 365, 500, 425), "CRIMSON"),  # UPS System's plate
    ("GiftGet.png", (330, 412, 490, 480), "CRIMSON"),  # Wound Clerid's plate
    ("GiftSearchSelected.png", (930, 216, 1090, 236), "CRIMSON"),  # Smokes and Wires: its name, in its sin's colour
    ("GiftSearchSelected.png", (930, 326, 1105, 346), "SCARLET"),  # Rusted Cutting Knife
    ("GiftSearchSelected.png", (930, 437, 1078, 457), "SHAMROCK"),  # White Gossypium
])
def test_the_game_colours_the_names_of_its_gifts_by_the_colours_the_tool_read(image, box, sin):
    # the game's screens, 720p: within 6 levels a channel of the colour plates.json gives the sin (the screen's rendering
    # moves them a little: SCARLET's #fd6600 shows as #fe6b00)
    seen = most_common(image, box, keep=lambda c: max(c) > 128)
    game = PLATES["plates"][sin]["colour"]
    assert all(abs(a - b) <= 6 for a, b in zip(seen, gp.rgb(game))), (seen, game)
