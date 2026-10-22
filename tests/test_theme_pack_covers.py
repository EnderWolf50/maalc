import json
from pathlib import Path

from PIL import Image, ImageFont

import theme_pack_card as card
import theme_pack_covers as tpc

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
COVERS = DATA / "theme_pack_covers"
WIDTH = 180
# 94 cards weigh 1.56 MB (16.6 KB each); the static data holds 121 packs, so a season that lists all of them needs about 2.0 MB
MAX_BYTES = 2_000_000


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


def test_wrap_breaks_at_words_and_keeps_the_run_colours():
    font = ImageFont.load_default(20)
    one = card.runs("Nest, Workshop, and Technology", "ffffff")
    assert len(card.wrap(one, font, 10_000)) == 1
    lines = card.wrap(one, font, font.getlength("Nest, Workshop, and") + 1)
    assert ["".join(w for w, _ in ln).strip() for ln in lines] == ["Nest, Workshop, and", "Technology"]
    two = card.runs("<color=#ee4893>Hatred</color> and <color=#0060c5>Despair</color>", "ffffff")
    assert {c for ln in card.wrap(two, font, font.getlength("Hatred and") + 1) for _, c in ln} == {"ee4893", "ffffff", "0060c5"}


def test_every_pack_of_the_yaml_has_a_card():
    packs = tpc.pack_ids((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
    index = json.loads((COVERS / "index.json").read_text(encoding="utf-8"))
    assert set(index) == set(packs)
    for name, file in index.items():
        assert file == f"{packs[name]}.webp"
        assert Image.open(COVERS / file).size[0] == WIDTH


def test_the_thumbnails_stay_small():
    assert sum(f.stat().st_size for f in COVERS.glob("*.webp")) < MAX_BYTES
