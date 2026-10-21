"""Cut the theme pack covers (#241) out of the game's asset bundles into assets/resource/base/data/theme_pack_covers/.

Usage: uv run --group unpack python tools/theme_pack_covers.py [--width 120] [--contact-sheet FILE]
Reads `.local/unpack/` (the pulled UnityCache bundles and the static data, see docs/spec/05-game-data.md section 2);
writes `<pack id>.webp` per pack of theme_packs.yaml plus `index.json` ({pack name: file}), and lists every pack without a cover.
Run it as a `bench` ticket (tools/live/queue.py), it reads all 12 GB of bundles.
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

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
OUT = DATA / "theme_pack_covers"
THEME_PACK_LINE = re.compile(r'^\s+- ("[^"]*"|[^#"]+?)\s*#\s*(\d+)\b')  # `  - Name  # 1001 N1 H1`: the comment carries the pack id
THEME_FLOOR_DIR = "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-theme-floor"


def pack_ids(yaml_text: str) -> dict[str, int]:
    """Pack name -> id of the `packs:` list of theme_packs.yaml."""
    packs, inside = {}, False
    for line in yaml_text.splitlines():
        if line.startswith("packs:"):
            inside = True
        elif inside and line and not line.startswith((" ", "#")):
            break
        elif inside and (m := THEME_PACK_LINE.match(line)):
            packs[yaml.safe_load(m[1])] = int(m[2])
    return packs


def sprite_ids(floor_dir: Path) -> dict[int, str]:
    """Pack id -> `packSpriteId`, the cover's sprite name, from the static data."""
    out = {}
    for f in floor_dir.glob("*.json"):
        for t in json.loads(f.read_text(encoding="utf-8-sig"))["list"]:
            out[t["id"]] = t["uiConfigs"]["packSpriteId"]
    return out


def covers(cache: Path, wanted: set[str]) -> dict[str, Image.Image]:
    """Sprite name -> image (a Sprite wins over its Texture2D)."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"  # the bundles carry a stripped version, 1.117.0's engine
    out = {}
    for p in sorted(cache.glob("*/*/__data")):  # UnityCache/<hash of the bundle name>/<content hash>/__data; 1556 bundles, ~2 minutes
        for o in UnityPy.load(str(p)).objects:
            if o.type.name in ("Sprite", "Texture2D"):
                r = o.read()
                if r.m_Name in wanted and (o.type.name == "Sprite" or r.m_Name not in out):
                    out[r.m_Name] = r.image
    return out


def contact_sheet(files: list[tuple[str, Path]], dest: Path):
    """Every thumbnail on one PNG, labelled with the pack id, for the PR."""
    from PIL import ImageDraw

    ims = [(name, Image.open(f).convert("RGBA")) for name, f in files]
    w, h = ims[0][1].size
    cols = 16
    sheet = Image.new("RGB", (cols * (w + 6) + 6, -(-len(ims) // cols) * (h + 22) + 6), "#222")
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(ims):
        x, y = 6 + i % cols * (w + 6), 6 + i // cols * (h + 22)
        sheet.paste(im, (x, y), im)
        d.text((x, y + h + 4), name, fill="#ddd")
    sheet.save(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=120)
    ap.add_argument("--contact-sheet", type=Path)
    args = ap.parse_args()
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # below normal: a bench job beside a live run

    unpack = local_dir("unpack")
    packs = pack_ids((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
    sprite = sprite_ids(unpack / THEME_FLOOR_DIR)
    images = covers(unpack / "raw/UnityCache", {sprite[i] for i in packs.values() if i in sprite})

    OUT.mkdir(exist_ok=True)
    index, missing = {}, []
    for name, pid in packs.items():
        im = images.get(sprite.get(pid, ""))
        if im is None:
            missing.append(f"{pid} {name} ({sprite.get(pid)})")
            continue
        im = im.convert("RGBA").resize((args.width, round(im.height * args.width / im.width)), Image.LANCZOS)
        im.save(OUT / f"{pid}.webp", quality=80, method=6)
        index[name] = f"{pid}.webp"
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for stale in set(OUT.glob("*.webp")) - {OUT / f for f in index.values()}:
        stale.unlink()
    total = sum(f.stat().st_size for f in OUT.glob("*.webp"))
    print(f"{len(index)}/{len(packs)} covers -> {OUT} ({total} bytes)")
    for m in missing:
        print("no cover:", m)
    if args.contact_sheet:
        contact_sheet([(f.split(".")[0], OUT / f) for f in index.values()], args.contact_sheet)


if __name__ == "__main__":
    main()
