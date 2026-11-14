"""Write the game's seven sin icons: assets/resource/base/data/sin_icons/<Wrath|Lust|Sloth|Gluttony|Gloom|Pride|Envy>.png.

Usage: uv run --group unpack python tools/sin_icons.py
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). Neither the Agent nor the settings GUI reads these files:
they are in the resource package for lc-helper (docs/adr/0012), which draws them on its check cards.

They are the emblems the game draws on a Choices page, full colour with a cream outline (sprites `BattleUI_Choice
1_<Crimson|...|Violet>`, 120 x 124 to 120 x 128), found through the game's own objects, never by sprite name: the
UISpriteDataManager MonoBehaviour of scene level1 (path id 1906, in the APK's player data) holds, in this order, _uiSprites
(one PPtr), evilSpriteList, attributeOutlineList and totalAttributeSpriteList, each a list of {ATTRIBUTE_TYPE key,
PPtr<Sprite>}; these are the last list's, resolved through the scene's externals table. ATTRIBUTE_TYPE 0..6 is CRIMSON
SCARLET AMBER SHAMROCK AZURE INDIGO VIOLET, Wrath Lust Sloth Gluttony Gloom Pride Envy (raw/Localize/en/EN_AttributeText.json,
which spells Gluttony `Glut.`): the tool stops when that file's order differs, or when a sprite's name does not end in its
key's colour. Each sprite is written over its whole rect (tools/unity_files.py sprite_image) as PNG. Written against client
1.118.1; rerun it after a client update (docs/spec/05-game-data.md section 8).
"""

import json
import struct
from pathlib import Path

from local_dir import local_dir
from unity_files import PLAYER_DATA, sprite_image, unity

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets/resource/base/data/sin_icons"
ATTRIBUTES = "raw/Localize/en/EN_AttributeText.json"
COLOURS = ["CRIMSON", "SCARLET", "AMBER", "SHAMROCK", "AZURE", "INDIGO", "VIOLET"]  # ATTRIBUTE_TYPE 0..6
SINS = ["Wrath", "Lust", "Sloth", "Gluttony", "Gloom", "Pride", "Envy"]  # the files, in the same order
SCENE, MANAGER = "level1", 1906  # UISpriteDataManager's file and path_id
BEFORE_TOTAL = 2  # evilSpriteList and attributeOutlineList, between _uiSprites and totalAttributeSpriteList

_envs = {}


def load(data: Path, name: str):
    """A player data file by its name (a split one from its split0), each file once."""
    if name not in _envs:
        path = data / name
        _envs[name] = unity(path if path.exists() else data / f"{name}.split0")
    return _envs[name]


def obj(env, path_id: int):
    return next(o for o in env.objects if o.path_id == path_id)


def keyed_list(raw: bytes, off: int) -> tuple[dict[int, tuple[int, int]], int]:
    """A serialized List<{int key, PPtr}> at off: {key: (fileID, pathID)}, and the offset after it."""
    count = struct.unpack_from("<i", raw, off)[0]
    if not 0 <= count < 64:
        raise SystemExit(f"not a keyed list at {off}: count {count}")
    found = {}
    for i in range(count):
        key, file_id, path_id = struct.unpack_from("<iiq", raw, off + 4 + 16 * i)
        found[key] = (file_id, path_id)
    return found, off + 4 + 16 * count


def total_list(data: Path) -> dict[int, tuple[int, int]]:
    """UISpriteDataManager's totalAttributeSpriteList, read from its raw bytes: past its header (m_GameObject,
    m_Enabled, m_Script, m_Name) and _uiSprites, then the lists before it."""
    raw = obj(load(data, SCENE), MANAGER).get_raw_data()
    name_len = struct.unpack_from("<i", raw, 28)[0]
    off = 32 + (name_len + 3) // 4 * 4 + 12
    for _ in range(BEFORE_TOTAL):
        _, off = keyed_list(raw, off)
    return keyed_list(raw, off)[0]


def check_sin_order(rows: list[dict]):
    """Stop unless EN_AttributeText's first rows are COLOURS, named as SINS are (the file abbreviates Gluttony to `Glut.`)."""
    if len(rows) < len(SINS):
        raise SystemExit(f"EN_AttributeText: {len(rows)} rows, expected at least {len(SINS)}: the sin order changed")
    for colour, sin, row in zip(COLOURS, SINS, rows):
        if row["id"] != colour or not (name := row["name"].rstrip(".")) or not sin.startswith(name):
            raise SystemExit(f"EN_AttributeText: {row['id']} is {row['name']}, expected {colour} as {sin}: the sin order changed")


def check_colour(sprite_name: str, colour: str):
    """Stop unless the sprite a key holds is named for that key's colour."""
    if not sprite_name.upper().endswith("_" + colour):
        raise SystemExit(f"ATTRIBUTE_TYPE order broken: the {colour} key holds {sprite_name}")


def main():
    unpack = local_dir("unpack")
    data = unpack / PLAYER_DATA
    if not (data / SCENE).is_file():
        raise SystemExit(f"no unpacked client at {data}: see docs/agents/local-dev.md 'Game data'")
    check_sin_order(json.loads((unpack / ATTRIBUTES).read_text(encoding="utf-8-sig"))["dataList"])
    pointers = total_list(data)
    externals = [e.path for e in next(iter(load(data, SCENE).files.values())).externals]
    images = {}
    for key, (sin, colour) in enumerate(zip(SINS, COLOURS)):
        if key not in pointers:
            raise SystemExit(f"totalAttributeSpriteList has no entry for ATTRIBUTE_TYPE {key}")
        file_id, path_id = pointers[key]
        sprite = obj(load(data, SCENE if file_id == 0 else externals[file_id - 1]), path_id).read()
        check_colour(sprite.m_Name, colour)
        images[sin] = sprite_image(sprite).convert("RGBA")  # every sprite found before any file is written
        print(f"{sin}: {sprite.m_Name} {images[sin].width}x{images[sin].height}")
    OUT.mkdir(parents=True, exist_ok=True)
    for sin, image in images.items():
        image.save(OUT / f"{sin}.png")


if __name__ == "__main__":
    main()
