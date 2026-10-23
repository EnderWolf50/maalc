"""Write the settings GUI's gift icons: assets/resource/base/data/gift_icons/<id>.webp and index.json (#293).

Usage: uv run --group unpack python tools/gift_icons.py
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). One icon per gift id the GUI lists: the 320 of gift_search.json,
the 60 fusion gifts and 12 recipe materials of gift_recipes.json and the 5 vestiges (9991-9995). The icon is the game's EgoGiftIcon
sprite with its transparency (the image/GiftSearch templates are green-filled for matching and stay as they are), 56 px, WebP.
`index.json` lists the ids ({id: file}). Run it as a `bench` ticket (tools/live/queue.py): it opens the UnityCache bundles
(the first run indexes them, ~12 GB; the quarterly rerun is docs/spec/05-game-data.md section 8).
"""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_dir import local_dir  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
OUT = DATA / "gift_icons"
SIZE = 56
QUALITY = 72
VESTIGES = range(9991, 9996)


def gift_ids() -> list[int]:
    """Every id the GUI lists: gift_search.json, the fusion gifts and materials of gift_recipes.json, the vestiges."""
    search = json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
    recipes = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
    return [g["id"] for g in search] + [g["id"] for g in recipes["gifts"] + recipes["materials"]] + list(VESTIGES)


def webp(sprite) -> bytes:
    """The sprite fitted into SIZE x SIZE, alpha kept."""
    im = sprite.convert("RGBA")
    im.thumbnail((SIZE, SIZE))
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    return buf.getvalue()


def main():
    import gift_recipes as gr

    unpack = local_dir("unpack")
    table = gr.gift_table(unpack)
    ids = gift_ids()
    OUT.mkdir(exist_ok=True)
    missing = gr.extract_icons(unpack, {i: table[i][2] for i in ids}, lambda image, gid: (OUT / f"{gid}.webp").write_bytes(webp(image)))
    if missing:
        raise SystemExit(f"no EgoGiftIcon sprite for {missing}")
    index = {str(i): f"{i}.webp" for i in sorted(ids)}
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    for stale in set(OUT.glob("*.webp")) - {OUT / f for f in index.values()}:
        stale.unlink()
    total = sum(f.stat().st_size for f in OUT.glob("*.webp"))
    print(f"{len(index)} icons -> {OUT} ({total} bytes)")


if __name__ == "__main__":
    main()
