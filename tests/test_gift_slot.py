from pathlib import Path

import pytest
from PIL import Image

import gift_slot as gs

PLATE = Path(__file__).resolve().parent.parent / "assets/resource/base/data/gift_slot/plate.png"
SIZE = (128, 128)  # the Legacy theme's EgoGift_bg1
MAX_BYTES = 30_000


def rect(w, h, x=0, y=0, anchor=(0.5, 0.5)):
    return {"m_SizeDelta": {"x": w, "y": h}, "m_AnchoredPosition": {"x": x, "y": y}, "m_AnchorMin": {"x": anchor[0], "y": anchor[1]}}


def prefab(**changes):
    """The slot's children as `prefab()` returns them: name -> (RectTransform typetree, DUISpriteSetter keys), as 1.118.1 has it."""
    children = {"EgoGiftIconPrefab": (rect(350, 350), []), "img_basePanel": (rect(350, 350), ["Icon/EgoGift_bg1"]),
                "img_Icon": (rect(256, 256, 0, 8), []), "img_keywordIcon1": (rect(100, 100, -5, 5, (1, 0)), []),
                "tmp_Tier": (rect(60, 60, 20, -20, (0, 1)), [])}
    children.update(changes)
    return children


def test_the_slot_the_game_lays_out_is_the_one_the_tool_expects(capsys):
    gs.check_layout(prefab())
    assert "layout:" in capsys.readouterr().out


def test_the_tool_stops_when_the_slot_changes_size():
    with pytest.raises(SystemExit, match="slot"):
        gs.check_layout(prefab(EgoGiftIconPrefab=(rect(360, 360), [])))


def test_the_tool_stops_when_the_picture_moves():
    with pytest.raises(SystemExit, match="img_Icon"):
        gs.check_layout(prefab(img_Icon=(rect(256, 256, 0, 20), [])))


def test_the_tool_stops_when_a_child_is_anchored_elsewhere():
    with pytest.raises(SystemExit, match="anchored"):
        gs.check_layout(prefab(img_keywordIcon1=(rect(100, 100, -5, 5, (0, 0)), [])))


def test_the_slot_is_as_the_overlay_draws_it():
    assert gs.SLOT == {"slot": 350, "picture": 256, "picture_rise": 8, "keyword": 100, "keyword_in": 5}


def test_the_plate_is_the_games_at_its_size():
    im = Image.open(PLATE)
    assert im.size == SIZE and im.mode == "RGBA"


def test_the_plate_stays_small():
    assert PLATE.stat().st_size < MAX_BYTES
