import json
from pathlib import Path

import pytest
from PIL import Image

import sinner_cards as sc

REPO = Path(__file__).resolve().parent.parent
CARDS = REPO / "assets/resource/base/data/sinner_cards"
FRAME = REPO / "assets/resource/base/data/sinner_frame"
# tools/sinner_cards.py --width: the art shows in the frame's opening, at most 143 CSS px wide (a 162 px tile, #732), so 240 holds
# it at 150 % scaling; the identity list's art is 537 x 827, so 240 x 370
WIDTH, HEIGHT = 240, 370
MAX_BYTES = 600_000  # the 12 cards together (#718)
# What the tool writes for the formation card's frame (#732): name -> size, each the game's sprite at its own size
PART_SIZES = {"frame": (162, 230), "glow": (161, 230), "plate-deployed": (138, 42), "plate-backup": (130, 33)}
FRAME_MAX_BYTES = 60_000


def person(pid, character, *keywords):
    return {"id": pid, "characterId": character, "rank": 1, "unitKeywordList": list(keywords)}


def test_a_sinners_default_identity_is_the_one_of_base_appearance():
    rows = [person(10101, 1, "BASE_APPEARANCE", "SMALL"), person(10102, 1, "SMALL"), person(10201, 2, "BASE_APPEARANCE"),
            person(10207, 2)]
    assert sc.default_identities(rows) == {1: 10101, 2: 10201}


def test_a_sinner_with_two_base_appearances_stops_the_tool():
    with pytest.raises(SystemExit, match="character 1"):
        sc.default_identities([person(10101, 1, "BASE_APPEARANCE"), person(10199, 1, "BASE_APPEARANCE")])


def test_sinners_are_found_by_their_english_name():
    characters = [{"id": 1, "name": "Yi Sang"}, {"id": 4, "name": "Ryōshū"}, {"id": 400005, "name": "Jia Xichun"}]
    assert sc.sinner_identities(["Ryōshū", "Yi Sang"], characters, {1: 10101, 4: 10401}) == {"Ryōshū": 10401, "Yi Sang": 10101}
    with pytest.raises(SystemExit, match="Faust"):
        sc.sinner_identities(["Faust"], characters, {1: 10101})


def test_every_sinner_of_the_settings_has_a_card():
    index = json.loads((CARDS / "index.json").read_text(encoding="utf-8"))
    assert list(index) == ["Yi Sang", "Faust", "Don Quixote", "Ryōshū", "Meursault", "Hong Lu", "Heathcliff", "Ishmael", "Rodion",
                           "Sinclair", "Outis", "Gregor"]
    assert list(index) == sc.sinner_names()
    for file in index.values():
        assert Image.open(CARDS / file).size == (WIDTH, HEIGHT)
    assert {f.name for f in CARDS.glob("*.webp")} == set(index.values())


def test_the_cards_stay_small():
    assert sum(f.stat().st_size for f in CARDS.glob("*.webp")) < MAX_BYTES


def test_a_plate_keeps_its_ends_and_loses_its_word():
    """The game's plate has SELECTED or BACKUP drawn on it; the GUI writes its own word (上場, 替補), so the middle of each row
    becomes the column beside its left end. The plate's lines run across it, so the row reads the same."""
    im = Image.new("RGBA", (40, 3), (200, 0, 0, 255))
    im.putpixel((0, 1), (10, 10, 10, 255))  # the left end
    im.putpixel((39, 1), (20, 20, 20, 255))  # the right end
    im.putpixel((5, 0), (90, 0, 0, 255))  # a line of the plate, in the column beside the left end
    im.putpixel((20, 1), (255, 255, 200, 255))  # a pixel of the word
    out = sc.plain_plate(im, end=5)
    assert out.size == im.size
    assert out.getpixel((0, 1)) == (10, 10, 10, 255) and out.getpixel((39, 1)) == (20, 20, 20, 255)
    assert [out.getpixel((x, 0)) for x in range(5, 35)] == [(90, 0, 0, 255)] * 30
    assert out.getpixel((20, 1)) == (200, 0, 0, 255)


def ringed(width=21, height=25, gap=False):
    """A glow drawn as the game's IsPartipating sprite is: a soft outer edge (alpha 0.3), the ring's crest (1), its inner
    slope (0.6), then the 20 % wash over the middle, with a fainter speck in it (0.1). `gap` breaks the crest on one side."""
    im = Image.new("RGBA", (width, height))
    alpha = {0: 77, 1: 255, 2: 153}
    for y in range(height):
        for x in range(width):
            d = min(x, y, width - 1 - x, height - 1 - y)  # how far in from the edge
            im.putpixel((x, y), (255, 132, 0, alpha.get(d, 51)))
    im.putpixel((width // 2, height // 2), (255, 132, 0, 26))
    if gap:
        im.putpixel((1, height // 2), (255, 132, 0, 51))
    return im


def test_the_glow_keeps_its_ring_and_loses_its_wash():
    """The game's sprite lays a 20 % orange wash over the whole card inside its ring; the formation screen shows the art
    without it (#756), so the tool takes the wash out of the alpha inside the ring's crest: what is left of a pixel there is
    the ring's own light, (a - 0.2) / 0.8, and nothing under 0.2. The crest and the soft edge outside it stay as they are."""
    out = sc.ring_only(ringed())
    w, h = out.size
    assert out.size == (21, 25)
    assert out.getpixel((0, h // 2)) == (255, 132, 0, 77)  # outside the crest
    assert out.getpixel((1, h // 2)) == (255, 132, 0, 255)  # the crest
    assert out.getpixel((2, h // 2)) == (255, 132, 0, 128)  # the inner slope: (0.6 - 0.2) / 0.8 of its light
    assert out.getpixel((w // 2, 5)) == (255, 132, 0, 0)  # the wash
    assert out.getpixel((w // 2, h // 2)) == (255, 132, 0, 0)  # a speck fainter than the wash


def test_a_glow_whose_ring_is_open_stops_the_tool():
    with pytest.raises(SystemExit, match="ring"):
        sc.ring_only(ringed(gap=True))


def test_frame_parts_are_the_files_the_gui_reads_at_their_sizes():
    white = {k: Image.new("RGBA", size, (255, 255, 255, 255)) for parts in sc.FRAME_PARTS.values() for k, (_, size) in parts.items()}
    assert {k: v.size for k, v in sc.frame_parts(white).items()} == PART_SIZES


def test_the_glow_part_is_its_ring():
    parts = sc.frame_parts({"glow": ringed()})
    assert parts["glow"].getpixel((10, 5))[3] == 0 and parts["glow"].getpixel((1, 12))[3] == 255


def test_the_committed_glow_has_no_wash():
    """data/sinner_frame/glow.webp is the ring alone (#756): nothing over the art's middle, the ring's crest opaque."""
    glow = Image.open(FRAME / "glow.webp").convert("RGBA")
    w, h = glow.size
    middle = glow.crop((w // 4, h // 4, w * 3 // 4, h * 3 // 4))
    assert max(middle.getchannel("A").getdata()) <= 3
    assert max(glow.getpixel((x, h // 2))[3] for x in range(12)) >= 250


def test_the_committed_frame_parts_are_the_tools_and_stay_small():
    files = {f.stem: f for f in FRAME.glob("*.webp")}
    assert {k: Image.open(f).size for k, f in files.items()} == PART_SIZES
    assert sum(f.stat().st_size for f in files.values()) < FRAME_MAX_BYTES
