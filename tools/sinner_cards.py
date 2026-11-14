"""Write the settings GUI's sinner cards: assets/resource/base/data/sinner_cards/<identity id>.webp and index.json (#718), and
the formation card's frame they sit in, gui/src/sinner_card/<part>.webp (#732).

Usage: uv run --group unpack python tools/sinner_cards.py [--width 240]
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). A sinner's default identity (LCB Sinner) is the personality
of the static data whose `unitKeywordList` holds BASE_APPEARANCE (10101-11201 in 1.118.1); the sinner is the one of
EN_Characters whose English name the settings use. Its card is the identity list's art,
`Sprite/Unit/Info/Normal/<id>_normal_info.png` (537 x 827) of the UnityCache bundles, written `--width` wide as WebP, with
`index.json` ({sinner: file}, in the settings' sinner order). The deployment order tiles of the settings GUI show it.
The frame is the formation screen's (FRAME_PARTS, from the APK's player data): the card's frame, the glow over a sinner in
the order, and the deployed and backup plates with their English word taken off (the GUI writes its own).
Run it as a `bench` ticket (tools/live/queue.py): the bundle index (tools/unity_files.py bundle_index) reads all ~12 GB of
bundles when it is new or the client changed; the quarterly rerun is docs/spec/05-game-data.md section 8.
"""

import argparse
import ctypes
import io
import json
import sys
from pathlib import Path

from PIL import Image

from local_dir import local_dir
from unity_files import PLAYER_DATA, bundle_sprites, player_sprites

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets/resource/base/data/sinner_cards"
FRAME_OUT = REPO / "gui/src/sinner_card"
SCHEMA = REPO / "agent/settings.schema.json"
PERSONALITY = "static/Assets/Resources_moved/StaticData/static-data/personality"
CHARACTERS = "raw/Localize/en/EN_Characters.json"
CARD = "Assets/Resources_moved/Sprite/Unit/Info/Normal/{}_normal_info.png"
QUALITY = 80  # every file the tool writes, the art and the frame parts
# The formation screen's card: player-data file -> {part: (sprite, size)}. Read from the slot prefab
# `PersonalityFormationSlot_<sinner>` of `[UIPanel]PersonalityFormationUIPanel` (sharedassets2) and the frame tables
# `GacksungLevelFrame_Rank<rarity>` (IntSpritePairs: Uptie level 1-4 -> frame) in client 1.118.1. A part missing or of another
# size: the client renumbered its atlases, read those again (docs/spec/05-game-data.md section 8).
FRAME_PARTS = {
    # GacksungLevelFrame_Rank1 at Uptie 3: an LCB Sinner is rarity 1, and the identity list draws this vine frame round it
    # (#718's reference capture); its foot holds the shade the name sits on
    "cd12113d96c76ee4dbe6f2dc1b7b6d7b": {"frame": ("New_MainUI_Formation_3_2", (162, 230))},
    # IsPartipating: an orange ring and a 20 % orange wash over a sinner in the order
    "a7c25cf26ea7b654ead0b18206724124": {"glow": ("MainUI_Formation_5_24", (161, 230))},
    "679a596d5cb01f0468099be0b83bd64b": {
        "plate-deployed": ("New_MainUI_Formation_1_2", (138, 42)),  # ParticipateSlotUI: the red SELECTED plate
        "plate-backup": ("New_MainUI_Formation_1_55", (130, 33)),  # the teal BACKUP plate
    },
}
PLATE_END = 16  # px at each end of a plate that hold none of its word (SELECTED starts 26 px in, BACKUP 33)


def sinner_names() -> list[str]:
    """The settings' 12 sinners, in their order (the deployment order's enum)."""
    return json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]["order"]["items"]["enum"]


def default_identities(personalities) -> dict[int, int]:
    """characterId -> the id of its BASE_APPEARANCE personality; a character with two stops the tool."""
    out = {}
    for p in personalities:
        if "BASE_APPEARANCE" in p.get("unitKeywordList", []):
            if p["characterId"] in out:
                raise SystemExit(f"character {p['characterId']}: two default identities, {out[p['characterId']]} and {p['id']}")
            out[p["characterId"]] = p["id"]
    return out


def sinner_identities(sinners: list[str], characters: list[dict], identities: dict[int, int]) -> dict[str, int]:
    """Sinner name -> its default identity id, the character found by its English name."""
    by_name = {c["name"]: c["id"] for c in characters}
    lost = [s for s in sinners if identities.get(by_name.get(s)) is None]
    if lost:
        raise SystemExit(f"no default identity for {lost}: EN_Characters or the BASE_APPEARANCE keyword changed")
    return {s: identities[by_name[s]] for s in sinners}


def plain_plate(plate: Image.Image, end: int = PLATE_END) -> Image.Image:
    """The plate without its word: each row's middle, from `end` px in on both sides, is the row's pixel `end` px from the left.
    The plate's lines run across it, so a row reads the same; the GUI writes 上場 or 替補 on it."""
    im = plate.convert("RGBA")
    out = im.copy()
    column = im.crop((end, 0, end + 1, im.height))
    out.paste(column.resize((im.width - 2 * end, im.height), Image.NEAREST), (end, 0))
    return out


def frame_parts(found: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """The files the GUI uses, from the sprites: the frame and the glow as they are, the plates without their word."""
    parts = {k: v.convert("RGBA") for k, v in found.items()}
    for k in ("plate-deployed", "plate-backup"):
        parts[k] = plain_plate(found[k])
    return parts


def write_parts(images: dict[str, Image.Image], out: Path) -> int:
    """Each image as `<name>.webp` in out, alpha kept; files of other names removed. The bytes written."""
    out.mkdir(exist_ok=True)
    for name, im in images.items():
        im.save(out / f"{name}.webp", "WEBP", quality=QUALITY, method=6)
    for stale in set(out.glob("*.webp")) - {out / f"{n}.webp" for n in images}:
        stale.unlink()
    return sum((out / f"{n}.webp").stat().st_size for n in images)


def webp(image: Image.Image, width: int) -> bytes:
    im = image.convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=240, help="the art's width: it shows at most 143 CSS px wide in a tile (1.5 x at 150 %%)")
    args = ap.parse_args()
    if sys.platform == "win32":  # below normal: a bench job beside a live run
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    unpack = local_dir("unpack")
    rows = [p for f in sorted((unpack / PERSONALITY).glob("personality-*.json")) for p in json.loads(f.read_text(encoding="utf-8-sig"))["list"]]
    characters = json.loads((unpack / CHARACTERS).read_text(encoding="utf-8-sig"))["dataList"]
    ids = sinner_identities(sinner_names(), characters, default_identities(rows))
    cards = {CARD.format(i): i for i in ids.values()}  # the card Sprite's container path -> identity id
    frame = frame_parts(player_sprites(unpack / PLAYER_DATA, FRAME_PARTS, "the formation slot prefab and its frame tables"))

    OUT.mkdir(exist_ok=True)
    written = set()
    for identity, sprite in bundle_sprites(unpack, cards.get):
        (OUT / f"{identity}.webp").write_bytes(webp(sprite.image, args.width))
        written.add(identity)
    missing = {s: i for s, i in ids.items() if i not in written}
    if missing:
        raise SystemExit(f"no card sprite for {missing}")
    index = {s: f"{i}.webp" for s, i in ids.items()}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for stale in set(OUT.glob("*.webp")) - {OUT / f for f in index.values()}:
        stale.unlink()
    sizes = {f: (OUT / f).stat().st_size for f in index.values()}
    print(f"{len(index)} cards -> {OUT} ({sum(sizes.values())} bytes; largest {max(sizes.values())})")
    print(f"{len(frame)} frame parts -> {FRAME_OUT} ({write_parts(frame, FRAME_OUT)} bytes)")


if __name__ == "__main__":
    main()
