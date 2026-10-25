"""Compose the theme pack cards (#241) from the game files into assets/resource/base/data/theme_pack_covers/.

Usage: uv run --group unpack python tools/theme_pack_covers.py [--width 180] [--contact-sheet FILE]
Reads `.local/unpack/` (the pulled UnityCache bundles, the APK's player data and the static data, see
docs/agents/local-dev.md "Game data"; the yearly rerun is docs/spec/05-game-data.md section 8).
Each card stacks the game's own layers (tools/theme_pack_card.py): the cover art and boss picture from the bundles, the
frame, logo, warning and badge sprites and the Mikodacs and Pretendard fonts from the player data, the title from the English localization,
the colours and flags from `uiConfigs`. Writes `<pack id>.webp` per pack of theme_packs.yaml plus `index.json`
({pack name: file}) and lists every pack without a cover.
Run it as a `bench` ticket (tools/live/queue.py): it reads all 12 GB of bundles and the player data.
"""

import argparse
import ctypes
import json
import re
import sys
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_dir import local_dir  # noqa: E402
from theme_pack_card import card  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
OUT = DATA / "theme_pack_covers"
PLAYER_DATA = "apk-data/assets/bin/Data"
THEME_FLOOR_DIR = "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-theme-floor"
ATLAS_PARTS = {  # key -> (sprite name, size): MirrorDungeonThemeCardUI's layers, in sharedassets2
    "badge": ("MainUI_MirrorDungeon4_4_4", (46, 46)),
    "warning": ("MainUI_MirrorDungeon4_4_6", (128, 115)),
    "silhouette": ("MainUI_MirrorDungeon4_4_7", (190, 340)),
    "front": ("MainUI_MirrorDungeon4_4_8", (190, 336)),
    "logo": ("MainUI_MirrorDungeon4_4_16", (127, 66)),
}
ICON_PARTS = {  # the attack type icons and the attribute silhouettes (Icon_evil_2_8..14), in sharedassets1
    "attack_pierce": ("Icon_AttackType_pierce", (90, 70)),
    "attack_hit": ("Icon_AttackType_hit", (78, 79)),
    "attack_slash": ("Icon_AttackType_slash", (80, 69)),
    **{f"sin_{i}": (f"Icon_evil_2_{i}", size) for i, size in zip(range(8, 15), [(102, 94), (91, 90), (86, 110), (88, 100), (70, 95), (76, 94), (89, 89)])},
}
FONTS = {"title": "Mikodacs", "baton": "Pretendard-Regular"}  # the EN fonts of the card's title and the baton label (OFL 1.1 both)
BATON = "Baton"  # the "Long Battle" overlay, a bundle sprite (Sprite/UI/ThemePack/Baton.png)


def pack_ids(yaml_text: str) -> dict[str, int]:
    """Pack name -> id of the `packs:` list of theme_packs.yaml (its `pack_ids` also names the Extreme-only packs the list leaves out)."""
    data = yaml.safe_load(yaml_text)
    return {name: data["pack_ids"][name] for name in data["packs"]}


def ui_configs(floor_dir: Path) -> dict[int, dict]:
    """Pack id -> `uiConfigs` (cover and boss sprite names, title colour, logo and warning flags), from the static data."""
    out = {}
    for f in floor_dir.glob("*.json"):
        for t in json.loads(f.read_text(encoding="utf-8-sig"))["list"]:
            out[t["id"]] = t["uiConfigs"]
    return out


def titles(localize: Path) -> dict[int, str]:
    """Pack id -> the title the card shows: `specialName` (TMP rich text) when the pack has one, else `name`."""
    rows = json.loads(localize.read_text(encoding="utf-8-sig"))["dataList"]
    return {r["id"]: r.get("specialName") or r["name"] for r in rows}


def player_files(data: Path) -> list[Path]:
    """The player data files, each once: a file the APK split into `<name>.splitN` loads whole from `.split0`."""
    return sorted(p for p in data.iterdir() if p.suffix not in (".resS", ".resource") and not re.search(r"\.split(?!0$)\d+$", p.name))


def unity(path: Path):
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"  # the files carry a stripped version, 1.117.0's engine
    return UnityPy.load(str(path))


def game_parts(data: Path) -> dict[str, Image.Image]:
    """The card's layer sprites from the player data, found by name and checked by size (a renumbered atlas fails here)."""
    out = {}
    for file, wanted in (("sharedassets2.assets.split0", ATLAS_PARTS), ("sharedassets1.assets.split0", ICON_PARTS)):
        names = {sprite: key for key, (sprite, _) in wanted.items()}
        for o in unity(data / file).objects:
            if o.type.name == "Sprite" and (r := o.read()).m_Name in names:
                out[names[r.m_Name]] = r.image
    for key, (sprite, size) in {**ATLAS_PARTS, **ICON_PARTS}.items():
        if key not in out or out[key].size != size:
            got = out[key].size if key in out else "missing"
            raise SystemExit(f"card part {sprite}: {got}, expected {size}: the client renumbered its sprites, re-read the card prefab (docs/spec/05-game-data.md section 8)")
    return out


def font_files(data: Path, dest: Path) -> dict[str, Path]:
    """The card's fonts cut out of the player data once and kept next to it: key -> file."""
    need = {name: dest / f"{name}.ttf" for name in FONTS.values()}
    if not all(p.exists() for p in need.values()):
        for p in player_files(data):
            for o in unity(p).objects:
                if o.type.name == "Font" and (r := o.read()).m_Name in need:
                    need[r.m_Name].write_bytes(bytes(r.m_FontData))
        missing = [n for n, p in need.items() if not p.exists()]
        if missing:
            raise SystemExit(f"fonts {missing} not found in the player data")
    return {key: need[name] for key, name in FONTS.items()}


def sprite_image(sprite) -> Image.Image:
    """The sprite over its whole rect. A tight-packed sprite (the boss pictures) keeps only its opaque part in the texture
    and UnityPy's `image` is that part; the UI lays out the whole rect, so the part goes back where `textureRectOffset`
    (from the rect's bottom left) puts it."""
    im = sprite.image
    w, h = round(sprite.m_Rect.width), round(sprite.m_Rect.height)
    if im.size == (w, h):
        return im
    off = sprite.m_RD.textureRectOffset
    full = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    full.paste(im.convert("RGBA"), (round(off.x), h - round(off.y) - im.height))
    return full


def bundle_sprites(cache: Path, wanted: set[str]) -> dict[str, Image.Image]:
    """Sprite name -> image over its whole rect (a Sprite wins over its Texture2D)."""
    out = {}
    for p in sorted(cache.glob("*/*/__data")):  # UnityCache/<hash of the bundle name>/<content hash>/__data; 1556 bundles, ~2 minutes
        for o in unity(p).objects:
            if o.type.name in ("Sprite", "Texture2D"):
                r = o.read()
                if r.m_Name in wanted and (o.type.name == "Sprite" or r.m_Name not in out):
                    out[r.m_Name] = sprite_image(r) if o.type.name == "Sprite" else r.image
    return out


def contact_sheet(files: list[tuple[str, Path]], dest: Path):
    """Every thumbnail on one PNG, labelled with the pack id, for the PR."""
    from PIL import ImageDraw

    ims = [(name, Image.open(f).convert("RGBA")) for name, f in files]
    w, h = ims[0][1].size
    cols = 12
    sheet = Image.new("RGB", (cols * (w + 6) + 6, -(-len(ims) // cols) * (h + 22) + 6), "#222")
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(ims):
        x, y = 6 + i % cols * (w + 6), 6 + i // cols * (h + 22)
        sheet.paste(im, (x, y), im)
        d.text((x, y + h + 4), name, fill="#ddd")
    sheet.save(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=180)
    ap.add_argument("--contact-sheet", type=Path)
    args = ap.parse_args()
    if sys.platform == "win32":  # below normal: a bench job beside a live run
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)

    unpack = local_dir("unpack")
    packs = pack_ids((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
    ui = ui_configs(unpack / THEME_FLOOR_DIR)
    name = titles(unpack / "raw/Localize/en/EN_MirrorDungeonTheme-1.json")
    parts = game_parts(unpack / PLAYER_DATA)
    fonts = font_files(unpack / PLAYER_DATA, local_dir("unpack", "fonts"))
    wanted = {n for i in packs.values() for n in (ui.get(i, {}).get("packSpriteId"), ui.get(i, {}).get("bossSpriteId")) if n}
    images = bundle_sprites(unpack / "raw/UnityCache", wanted | {BATON})
    if BATON not in images:
        raise SystemExit("sprite Baton (the Long Battle overlay) not found in the bundles")
    parts["baton"] = images[BATON]

    OUT.mkdir(exist_ok=True)
    index, missing = {}, []
    for pack, pid in packs.items():
        u = ui.get(pid, {})
        art, boss = images.get(u.get("packSpriteId", "")), images.get(u.get("bossSpriteId", ""))
        if art is None or (u.get("bossSpriteId") and boss is None) or pid not in name:
            missing.append(f"{pid} {pack} (cover {u.get('packSpriteId')}, boss {u.get('bossSpriteId')})")
            continue
        im = card(parts, art, boss, u, name[pid], fonts)
        im.resize((args.width, round(im.height * args.width / im.width)), Image.LANCZOS).save(OUT / f"{pid}.webp", quality=80, method=6)
        index[pack] = f"{pid}.webp"
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for stale in set(OUT.glob("*.webp")) - {OUT / f for f in index.values()}:
        stale.unlink()
    total = sum(f.stat().st_size for f in OUT.glob("*.webp"))
    print(f"{len(index)}/{len(packs)} covers -> {OUT} ({total} bytes)")
    for m in missing:
        print("no cover:", m)
    if args.contact_sheet:
        contact_sheet([(str(packs[n]), OUT / f) for n, f in index.items()], args.contact_sheet)


if __name__ == "__main__":
    main()
