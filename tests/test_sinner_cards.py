import json
from pathlib import Path

import pytest
from PIL import Image

import sinner_cards as sc

REPO = Path(__file__).resolve().parent.parent
CARDS = REPO / "assets/resource/base/data/sinner_cards"
# tools/sinner_cards.py --width: twice the widest deployment tile of gui/src/index.css (`.sinners`, 6 columns in 760 px); the
# identity list's art is 537 x 827, so 240 x 370
WIDTH, HEIGHT = 240, 370
MAX_BYTES = 600_000  # the 12 cards together (#718)


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
