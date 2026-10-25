import json
from pathlib import Path
from types import SimpleNamespace as NS

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


def test_pack_ids_reads_the_id_from_each_pack_comment():
    text = (
        "packs:\n  The B.E.: H345  # 3001\n  \"Hell's Chicken\": N2 H2  # 1101\n  S.E.A.: N2 H23  # 1102 DIFFICULT\n"
        '  "Line 4 - Section #3": N4  # 1208\n  "Walpurgis Night: Hatred and Despair": N34 H34  # 1119\n\n'
        "event_packs:\n  - S.E.A.\n"
    )
    assert tpc.pack_ids(text) == {
        "The B.E.": 3001,
        "Hell's Chicken": 1101,
        "S.E.A.": 1102,
        "Line 4 - Section #3": 1208,
        "Walpurgis Night: Hatred and Despair": 1119,
    }


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


def test_a_tight_packed_sprite_gets_its_transparent_margin_back():
    # the boss sprites are 391 x 432 rects whose textureRect drops the empty margin: UnityPy's image is the opaque part only.
    # The card lays out the whole rect, so the art goes back to where textureRectOffset (from the bottom left) puts it
    opaque = Image.new("RGBA", (4, 3), (255, 0, 0, 255))
    sprite = NS(image=opaque, m_Rect=NS(width=10.0, height=8.0), m_RD=NS(textureRectOffset=NS(x=2.0, y=1.0)))
    full = tpc.sprite_image(sprite)
    assert full.size == (10, 8)
    assert full.getchannel("A").getbbox() == (2, 4, 6, 7)  # 1 px above the bottom edge, 2 px from the left
    whole = NS(image=opaque, m_Rect=NS(width=4.0, height=3.0), m_RD=NS(textureRectOffset=NS(x=0.0, y=0.0)))
    assert tpc.sprite_image(whole) is opaque
