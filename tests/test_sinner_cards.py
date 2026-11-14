import json
from pathlib import Path

import pytest
from PIL import Image

import sinner_cards as sc

REPO = Path(__file__).resolve().parent.parent
CARDS = REPO / "assets/resource/base/data/sinner_cards"
FRAME = REPO / "gui/src/sinner_card"
# tools/sinner_cards.py --width: the art shows in the frame's opening, at most 143 CSS px wide (a 162 px tile, #732), so 240 holds
# it at 150 % scaling; the identity list's art is 537 x 827, so 240 x 370
WIDTH, HEIGHT = 240, 370
MAX_BYTES = 600_000  # the 12 cards together (#718)
# What the tool writes for the formation card's frame (#732): name -> size, each the game's sprite at its own size
FRAME_PARTS = {"frame": (162, 230), "glow": (161, 230), "plate-deployed": (138, 42), "plate-backup": (130, 33)}
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


def test_frame_parts_are_the_files_the_gui_reads_at_their_sizes():
    white = {k: Image.new("RGBA", size, (255, 255, 255, 255)) for parts in sc.FRAME_PARTS.values() for k, (_, size) in parts.items()}
    assert {k: v.size for k, v in sc.frame_parts(white).items()} == FRAME_PARTS


def test_the_committed_frame_parts_are_the_tools_and_stay_small():
    files = {f.stem: f for f in FRAME.glob("*.webp")}
    assert {k: Image.open(f).size for k, f in files.items()} == FRAME_PARTS
    assert sum(f.stat().st_size for f in files.values()) < FRAME_MAX_BYTES
