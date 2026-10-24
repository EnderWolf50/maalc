import json
from pathlib import Path

from PIL import Image

import theme_pack_card as card
import theme_pack_covers as tpc

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
COVERS = DATA / "theme_pack_covers"
WIDTH, HEIGHT = 180, 322  # tools/theme_pack_covers.py --width, and the aspect-ratio of `.img` in gui/src/index.css (180 / 322): change all together
# 94 cards weigh 1.59 MB (16.9 KB each); the static data holds 121 packs, so a season that lists all of them needs about 2.1 MB
MAX_BYTES = 2_200_000


class Glyphs:
    """Every letter half an em wide and 0.7 em tall without a descender; spaces have no ink."""

    def of(self, c):
        return (0.5, 0.0, 0.0) if c == " " else (0.5, 0.7, 0.0)


def test_pack_ids_reads_the_id_of_each_listed_pack():
    text = (
        "packs:\n  The B.E.: H345\n  S.E.A.: N2 H23  # DIFFICULT\n  \"Line 4 - Section #3\": N4\n\n"
        'pack_ids:\n  The B.E.: 3001\n  S.E.A.: 1102\n  "Line 4 - Section #3": 1208\n  S.E.A. BokGak: 1113\n'
    )
    assert tpc.pack_ids(text) == {"The B.E.": 3001, "S.E.A.": 1102, "Line 4 - Section #3": 1208}  # BokGak is not listed


def test_rich_text_title_splits_into_coloured_runs():
    text = "<color=#ee4893>Hatred</color> and <color=#0060c5>Despair</color>"
    assert card.runs(text, "ffffff") == [("Hatred", "ee4893"), (" and ", "ffffff"), ("Despair", "0060c5")]
    assert card.runs("To be Pierced", "ffffff") == [("To be Pierced", "ffffff")]


def test_layout_wraps_at_words_keeps_run_colours_and_drops_trailing_spaces():
    tokens = card.runs("Nest, Workshop, and Technology", "ffffff")
    lines = card.layout(tokens, 10.0, 10_000, Glyphs())
    assert len(lines) == 1
    # a glyph is 0.5 em + the font's spacing offset 6 + the text's -2 (1/100 em); the first line holds 19 glyphs
    lines = card.layout(tokens, 10.0, 19 * 5.4 + 0.3, Glyphs())
    assert ["".join(c for c, _, _ in ln) for ln, _ in lines] == ["Nest, Workshop, and", "Technology"]
    colours = card.layout(card.runs("<color=#ee4893>Hatred</color> and <color=#0060c5>Despair</color>", "ffffff"), 10.0, 10_000, Glyphs())
    assert {color for _, color, _ in colours[0][0]} == {"ee4893", "ffffff", "0060c5"}


def test_auto_size_caps_at_65_and_prefers_two_lines_when_they_allow_a_bigger_font():
    box = (485.0, 90.865)  # the title rect: 0.7 * 680 + 9 wide, 0.085 * 1069 tall
    size, lines = card.fit_title(card.runs("The Unloving", "ffffff"), *box, Glyphs())
    assert size == 65.0 and len(lines) == 1
    # 20 glyphs of 0.54 em: one line fits up to 44.9, two lines (0.7 + 1.04 em tall) up to 52.2
    size, lines = card.fit_title(card.runs("Charm, Wander, Doubt", "ffffff"), *box, Glyphs())
    assert len(lines) == 2 and 51.5 < size < 52.5


def test_every_pack_of_the_yaml_has_a_card():
    packs = tpc.pack_ids((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
    index = json.loads((COVERS / "index.json").read_text(encoding="utf-8"))
    assert set(index) == set(packs)
    for name, file in index.items():
        assert file == f"{packs[name]}.webp"
        assert Image.open(COVERS / file).size == (WIDTH, HEIGHT)


def test_the_thumbnails_stay_small():
    assert sum(f.stat().st_size for f in COVERS.glob("*.webp")) < MAX_BYTES
