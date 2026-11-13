"""Write the settings GUI's starlight grace art: the icons (#719) and the card's own textures (#726).

Usage: uv run --group unpack python tools/grace_icons.py
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data").

- `gui/src/grace_icons/<n>.webp` for grace n (1-10) of gui/src/graces.json: the game's `StartBuffIcon_<id>` sprite (a white
  glyph on transparency, the top left of each card on the starlight page), `<id>` the grace's start-buff id, found by its English
  name in the English localization (`mirror_dungeon_5_buffs_title_<id>`). Fitted into 96 px, alpha kept, WebP. It reads the bundle
  index `.local/unpack/out/sprite-index.tsv` (tools/game_data.py bundle_index); when a new client's bundles are not in it yet, the
  first run reads them all (~12 GB): run it as a `bench` ticket then (tools/live/queue.py, docs/spec/05-game-data.md section 8).
- `gui/src/grace_card/<part>.webp`: the sprites the starlight page's prefabs draw, from the APK's player data (CARD_PARTS):
  the card face unselected and selected, the hover frame, the + / ++ button plate unlit and lit, the + glyph unlit and lit, the
  starlight price icon, the Enhance All panel and the page's background. Each is found by name in its file and checked by size, as
  tools/theme_pack_covers.py does for the theme pack card: a renamed or resized sprite stops the tool, and the prefabs are read again.
"""

import json
from pathlib import Path

from PIL import Image

from game_data import INDEX, UNITY_VERSION, bundle_index
from gift_icons import webp
from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
GRACES = REPO / "gui/src/graces.json"
OUT = REPO / "gui/src/grace_icons"
CARD_OUT = REPO / "gui/src/grace_card"
TITLE = "mirror_dungeon_5_buffs_title_"
SPRITE = "StartBuffIcon_"
SIZE = 96
QUALITY = 80
PLAYER_DATA = "apk-data/assets/bin/Data"
# The card's sprites: player-data file -> {part: (sprite, size)}. Read from the Image components of the card prefab
# `[Script]StartBuffCardUIWithLevel_MD7` (Panel, Selected, Hover, the level buttons' plate, Focused, Icon and FocusedIcon, Cost) and
# of the page prefab `Prefab_MirrorDungeonStartBuffCardUIPanel` (its background Image, ApplyAllCardLevel) in client 1.118.1; the
# files keep their names from 1.117.0 to 1.118.1. A part missing or of another size: the client renumbered its atlases, find
# the sprites again from those two prefabs (docs/spec/05-game-data.md section 8).
CARD_PARTS = {
    "6e4a9190330af674daae57c8cb3b4ef1": {
        "face": ("MainUI_MirrorDungeon8_2_2", (380, 438)),  # Panel: the card unselected
        "face-picked": ("MainUI_MirrorDungeon8_2_24", (380, 444)),  # Selected: the card selected, its frame glowing
        "hover": ("MainUI_MirrorDungeon8_2_4", (365, 432)),  # Hover: a glowing frame, 9-sliced at 105 px
        "button": ("MainUI_MirrorDungeon8_2_9", (209, 69)),  # the + / ++ plate, 9-sliced at 25 px
        "button-focus": ("MainUI_MirrorDungeon8_2_10", (191, 51)),  # Focused: the lighter plate a lit + / ++ lays over it
        "side": ("MainUI_MirrorDungeon8_2_14", (276, 258)),  # ApplyAllCardLevel: the Select All / Enhance All panel
    },
    "7038d4f99cd650d40a9aab6d45e24727": {"plus": ("MainUI_MirrorDungeon6_2_9", (54, 56))},  # Icon: a white + glyph
    "17536cbbb31cf8f4791a827fbd868109": {"plus-lit": ("MainUI_MirrorDungeon3_3_22", (39, 26))},  # FocusedIcon: the orange +
    "8585dbab324242243bc2e8d86f4be1ff": {"star": ("MainUI_BattleSelection_7_15", (123, 126))},  # Cost: the starlight icon
    "81cbaa41b7d7f3d4e8abb7b3e332faf1": {"page": ("MainUI_MirrorDungeon8_1_0", (2048, 2048))},  # the page's background
}
PLUS_TINT = (235, 202, 162)  # the + glyph's Image colour in the prefab, (0.922, 0.792, 0.635, 1)
PAGE_SIZE = 1024  # the page background, from 2048: the panel is about 800 CSS px wide
STAR_SIZE = 64  # the price icon, from 123: it shows at about 20 CSS px
CARD_QUALITY = 80


def grace_ids(unpack: Path) -> list[str]:
    """The game's start-buff id of each grace, in graces.json order, by its English name."""
    english = json.loads((unpack / "raw/Localize/en/EN_MirrorDungeonUI_5.json").read_text(encoding="utf-8-sig"))["dataList"]
    ids = {x["content"]: x["id"][len(TITLE):] for x in english if x["id"].startswith(TITLE)}
    names = [g["en"] for g in json.loads(GRACES.read_text(encoding="utf-8"))["graces"]]
    missing = [n for n in names if n not in ids]
    if missing:
        raise SystemExit(f"no start-buff title in the client for {missing}")
    return [ids[n] for n in names]


def sprites(unpack: Path, ids: list[str]) -> dict:
    """{start-buff id: its StartBuffIcon sprite image} for the ids the bundles hold."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    cache = unpack / "raw/UnityCache"
    want = {SPRITE + i for i in ids}
    rows = [(line.split("\t") + ["", ""])[:3] for line in bundle_index(cache, unpack / INDEX)]
    bundles = {key for key, kind, p in rows if kind == "Sprite" and Path(p).stem in want}
    found = {}
    for key in sorted(bundles):
        for p, obj in UnityPy.load(str(cache / key / "__data")).container.items():
            if obj.type.name == "Sprite" and Path(p).stem in want:
                found[Path(p).stem[len(SPRITE):]] = obj.read().image
    return found


def card_sprites(data: Path) -> dict[str, Image.Image]:
    """The card's sprites from the player data, each over its whole rect, found by name and checked by size."""
    from theme_pack_covers import sprite_image, unity

    out = {}
    for file, wanted in CARD_PARTS.items():
        names = {sprite: key for key, (sprite, _) in wanted.items()}
        if (data / file).exists():
            for o in unity(data / file).objects:
                if o.type.name == "Sprite" and (r := o.read()).m_Name in names:
                    out[names[r.m_Name]] = sprite_image(r)
        for key, (sprite, size) in wanted.items():
            if key not in out or out[key].size != size:
                got = out[key].size if key in out else "missing"
                raise SystemExit(f"card part {sprite} in {file}: {got}, expected {size}: re-read the starlight prefabs (docs/spec/05-game-data.md section 8)")
    return out


def tint(im: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """The sprite as a Unity Image of that colour draws it: each channel multiplied by the colour, alpha kept."""
    r, g, b, a = im.convert("RGBA").split()
    r, g, b = (ch.point(lambda v, c=c: round(v * c / 255)) for ch, c in zip((r, g, b), rgb))
    return Image.merge("RGBA", (r, g, b, a))


def over_centre(base: Image.Image, top: Image.Image) -> Image.Image:
    """`top` laid over the middle of `base`: the lit plate, whose Focused child sits centred on the button (171 x 52 on 188 x 70)."""
    out = base.convert("RGBA").copy()
    out.alpha_composite(top.convert("RGBA"), ((base.width - top.width) // 2, (base.height - top.height) // 2))
    return out


def card_parts(found: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """The files the GUI uses, from the sprites: the lit plate composed, the + glyph in its colour, the large ones made smaller."""
    parts = {k: v for k, v in found.items() if k != "button-focus"}
    parts["button-lit"] = over_centre(found["button"], found["button-focus"])
    parts["plus"] = tint(found["plus"], PLUS_TINT)
    parts["star"] = found["star"].copy()
    parts["star"].thumbnail((STAR_SIZE, STAR_SIZE), Image.LANCZOS)
    parts["page"] = found["page"].convert("RGB").resize((PAGE_SIZE, PAGE_SIZE), Image.LANCZOS)
    return parts


def write(images: dict[str, Image.Image], out: Path) -> int:
    """Each image as `<name>.webp` in out, alpha kept; files of other names removed. The bytes written."""
    out.mkdir(exist_ok=True)
    for name, im in images.items():
        im.save(out / f"{name}.webp", "WEBP", quality=CARD_QUALITY, method=6)
    for stale in set(out.glob("*.webp")) - {out / f"{n}.webp" for n in images}:
        stale.unlink()
    return sum((out / f"{n}.webp").stat().st_size for n in images)


def main():
    unpack = local_dir("unpack")
    ids = grace_ids(unpack)
    found = sprites(unpack, ids)
    missing = [i for i in ids if i not in found]
    if missing:
        raise SystemExit(f"no {SPRITE}<id> sprite for {missing}")
    OUT.mkdir(exist_ok=True)
    files = {OUT / f"{n}.webp" for n in range(1, len(ids) + 1)}
    for n, i in enumerate(ids, 1):
        (OUT / f"{n}.webp").write_bytes(webp(found[i], SIZE, QUALITY))
    for stale in set(OUT.glob("*.webp")) - files:
        stale.unlink()
    total = sum(f.stat().st_size for f in files)
    print(f"{len(files)} icons -> {OUT} ({total} bytes)")
    parts = card_parts(card_sprites(unpack / PLAYER_DATA))
    print(f"{len(parts)} card parts -> {CARD_OUT} ({write(parts, CARD_OUT)} bytes)")


if __name__ == "__main__":
    main()
