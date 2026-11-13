"""Write the settings GUI's starlight grace icons: gui/src/grace_icons/<n>.webp for grace n (1-10) of gui/src/graces.json (#719).

Usage: uv run --group unpack python tools/grace_icons.py
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). A grace's icon is the game's `StartBuffIcon_<id>` sprite (a white
glyph on transparency, the top left of each card on the starlight page), `<id>` the grace's start-buff id, found by its English
name in the English localization (`mirror_dungeon_5_buffs_title_<id>`). Fitted into 96 px, alpha kept, WebP. It reads the bundle
index `.local/unpack/out/sprite-index.tsv` (tools/game_data.py bundle_index); when a new client's bundles are not in it yet, the
first run reads them all (~12 GB): run it as a `bench` ticket then (tools/live/queue.py, docs/spec/05-game-data.md section 8).
"""

import io
import json
from pathlib import Path

from game_data import INDEX, UNITY_VERSION, bundle_index
from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
GRACES = REPO / "gui/src/graces.json"
OUT = REPO / "gui/src/grace_icons"
TITLE = "mirror_dungeon_5_buffs_title_"
SPRITE = "StartBuffIcon_"
SIZE = 96
QUALITY = 80


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


def webp(image) -> bytes:
    """The sprite fitted into SIZE x SIZE, alpha kept."""
    im = image.convert("RGBA")
    im.thumbnail((SIZE, SIZE))
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


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
        (OUT / f"{n}.webp").write_bytes(webp(found[i]))
    for stale in set(OUT.glob("*.webp")) - files:
        stale.unlink()
    total = sum(f.stat().st_size for f in files)
    print(f"{len(files)} icons -> {OUT} ({total} bytes)")


if __name__ == "__main__":
    main()
