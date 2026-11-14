"""Write the settings GUI's sinner cards: assets/resource/base/data/sinner_cards/<identity id>.webp and index.json (#718).

Usage: uv run --group unpack python tools/sinner_cards.py [--width 240]
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). A sinner's default identity (LCB Sinner) is the personality
of the static data whose `unitKeywordList` holds BASE_APPEARANCE (10101-11201 in 1.118.1); the sinner is the one of
EN_Characters whose English name the settings use. Its card is the identity list's art,
`Sprite/Unit/Info/Normal/<id>_normal_info.png` (537 x 827) of the UnityCache bundles, written `--width` wide as WebP, with
`index.json` ({sinner: file}, in the settings' sinner order). The deployment order tiles of the settings GUI show it.
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
from unity_files import bundle_sprites

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets/resource/base/data/sinner_cards"
SCHEMA = REPO / "agent/settings.schema.json"
PERSONALITY = "static/Assets/Resources_moved/StaticData/static-data/personality"
CHARACTERS = "raw/Localize/en/EN_Characters.json"
CARD = "Assets/Resources_moved/Sprite/Unit/Info/Normal/{}_normal_info.png"
QUALITY = 80


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


def webp(image: Image.Image, width: int) -> bytes:
    im = image.convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=240, help="twice the widest deployment tile of the GUI")
    args = ap.parse_args()
    if sys.platform == "win32":  # below normal: a bench job beside a live run
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    unpack = local_dir("unpack")
    rows = [p for f in sorted((unpack / PERSONALITY).glob("personality-*.json")) for p in json.loads(f.read_text(encoding="utf-8-sig"))["list"]]
    characters = json.loads((unpack / CHARACTERS).read_text(encoding="utf-8-sig"))["dataList"]
    ids = sinner_identities(sinner_names(), characters, default_identities(rows))
    cards = {CARD.format(i): i for i in ids.values()}  # the card Sprite's container path -> identity id

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


if __name__ == "__main__":
    main()
