"""Write the settings GUI's status icons (#764): gui/src/buf_icons/<icon>.webp, one for each icon the keywords of
gui/src/gift_effects.json name.

Usage: uv run --group unpack python tools/buf_icons.py  (after tools/llc_text.py, which names the icons)
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"). The game prints a keyword of a gift's effect text as
`<sprite name="BUFF_ICON">` and the keyword's name (the client's global-metadata string literals): the sprite is the buff's
icon, `Assets/Resources_moved/Buf/<icon>.png` in the UnityCache bundles, `<icon>` the buff's iconId, else its id
(tools/llc_text.py keyword_entry). Each is fitted into SIZE px, alpha kept, WebP. It reads the bundle index
`.local/unpack/out/sprite-index.tsv` (tools/unity_files.py bundle_index); when a new client's bundles are not in it yet, the
first run reads them all (~12 GB): run it as a `bench` ticket then (tools/live/queue.py, docs/spec/05-game-data.md section 8).
A keyword icon with no sprite stops the tool before a file is written.
"""

import json
from pathlib import Path

from PIL import Image

from local_dir import local_dir
from unity_files import bundle_sprites, sprite_image, write_webps

REPO = Path(__file__).resolve().parent.parent
EFFECTS = REPO / "gui/src/gift_effects.json"
OUT = REPO / "gui/src/buf_icons"
FOLDER = "Assets/Resources_moved/Buf/"
SIZE = 32  # px: the card draws an icon at about 15 CSS px, so 2x screens get theirs sharp
QUALITY = 80


def picker(names):
    """A bundle_sprites pick: a Buf folder sprite's container path -> its icon name, when `names` holds it."""
    def pick(path):
        name = path[len(FOLDER):-len(".png")] if path.startswith(FOLDER) and path.endswith(".png") else None
        return name if name in names else None
    return pick


def icon(sprite: Image.Image) -> Image.Image:
    """A status icon: the sprite fitted into SIZE px, alpha kept."""
    im = sprite.convert("RGBA")
    im.thumbnail((SIZE, SIZE), Image.LANCZOS)
    return im


def icons(unpack: Path, names) -> dict[str, Image.Image]:
    """icon name -> its icon, for each of `names`; a name with no sprite stops the tool."""
    found = {k: icon(sprite_image(s)) for k, s in bundle_sprites(unpack, picker(set(names)))}
    missing = sorted(set(names) - set(found))
    if missing:
        raise SystemExit(f"no {FOLDER}<icon>.png sprite for {missing}: the client moved its buff icons (docs/spec/05-game-data.md section 8)")
    return found


def main():
    names = {k["icon"] for k in json.loads(EFFECTS.read_text(encoding="utf-8"))["keywords"].values()}
    out = icons(local_dir("unpack"), names)
    print(f"{len(out)} icons -> {OUT} ({write_webps(out, OUT, QUALITY)} bytes)")


if __name__ == "__main__":
    main()
