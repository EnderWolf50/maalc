import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

import buf_icons as bi

GUI = Path(__file__).resolve().parent.parent / "gui/src"
OUT = GUI / "buf_icons"
KEYWORDS = json.loads((GUI / "gift_effects.json").read_text(encoding="utf-8"))["keywords"]
MAX_BYTES = 200_000  # every status icon the gifts' effect texts draw, together (#764)


def test_a_sprite_path_names_the_icon_of_the_buf_folder_only():
    pick = bi.picker({"Sinking", "BloodArmor"})
    assert pick("Assets/Resources_moved/Buf/Sinking.png") == "Sinking"
    assert pick("Assets/Resources_moved/Buf/BloodArmor.png") == "BloodArmor"
    assert pick("Assets/Resources_moved/Buf/SinkingBlack.png") is None  # another sprite of the folder
    assert pick("Assets/Sprites/UI/MainUI/3_BattleSelection/Everydungeon/boss/Sinking.png") is None


def test_an_icon_is_fitted_into_its_size_and_keeps_its_alpha():
    im = bi.icon(Image.new("RGBA", (128, 96), (10, 20, 30, 40)))
    assert im.size == (bi.SIZE, bi.SIZE * 96 // 128) and im.mode == "RGBA" and im.getpixel((0, 0))[3] == 40
    assert bi.icon(Image.new("RGBA", (16, 16))).size == (16, 16)  # a small one stays as it is


def test_a_keyword_icon_with_no_sprite_stops_the_tool(monkeypatch):
    def found(unpack, pick):
        sprite = NS(image=Image.new("RGBA", (64, 64)), m_Rect=NS(width=64, height=64))
        return [(k, sprite) for k in ("Sinking",) if pick(f"Assets/Resources_moved/Buf/{k}.png")]
    monkeypatch.setattr(bi, "bundle_sprites", found)
    with pytest.raises(SystemExit, match="BloodArmor"):
        bi.icons(Path("."), {"Sinking", "BloodArmor"})


def test_the_committed_icons_are_the_ones_the_effects_draw_and_stay_small():
    files = {f.stem: f for f in OUT.glob("*.webp")}
    assert set(files) == {k["icon"] for k in KEYWORDS.values()}
    assert all(max(Image.open(f).size) <= bi.SIZE for f in files.values())
    assert sum(f.stat().st_size for f in files.values()) < MAX_BYTES
