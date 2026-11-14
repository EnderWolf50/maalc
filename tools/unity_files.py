"""The client's Unity files under `.local/unpack/` (docs/agents/local-dev.md "Game data"): loading one, the index of the
UnityCache bundles' container entries, and the sprites the bundles hold.

tools/game_data.py dumps the static data through it; the art tools (gift_recipes, gift_icons, grace_icons, sinner_cards,
theme_pack_covers) find their sprites through it. The first read of a new client's bundles takes all ~12 GB: run those tools
as a `bench` ticket (tools/live/queue.py).
"""

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:  # Pillow is imported where an image is made: tools/game_data.py imports this module for the index alone
    from PIL import Image

BUNDLES = "raw/UnityCache"  # the bundles under .local/unpack/: <hash of the bundle name>/<content hash>/__data
PLAYER_DATA = "apk-data/assets/bin/Data"  # the APK's player data under .local/unpack/
INDEX = "out/sprite-index.tsv"  # every bundle's container entries (bundle_index)
UNITY_VERSION = "6000.3.12f1"  # the engine in libunity.so (1.117.0 and 1.118.1); the files carry a stripped version
K = TypeVar("K")  # what a caller names a wanted sprite by


def unity(path: Path):
    """A Unity file (a bundle, a player data file) loaded by UnityPy."""
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    return UnityPy.load(str(path))


def bundle_index(cache: Path, index_path: Path) -> list[str]:
    """Every container entry of the bundles under `cache`, one `hash/version<TAB>type<TAB>path` line each, kept in
    `index_path` (out/sprite-index.tsv). A bundle folder the file lacks (the first run reads all ~12 GB; a new client's
    version folders) is read and added, the lines of a folder that is gone are dropped; `hash/version - -` marks a bundle
    as read, entries or not."""
    bundles = {f"{p.parent.parent.name}/{p.parent.name}": p for p in Path(cache).glob("*/*/__data")}
    lines = index_path.read_text(encoding="utf-8").splitlines() if index_path.is_file() else []
    kept = [line for line in lines if line.split("\t")[0] in bundles]  # an index of bare `hash` lines (before #625) goes whole
    new = sorted(bundles.keys() - {line.split("\t")[0] for line in kept})
    if new or len(kept) != len(lines):
        for key in new:
            try:
                kept += [f"{key}\t{obj.type.name}\t{p}" for p, obj in unity(bundles[key]).container.items()]
            except Exception as e:  # a bundle UnityPy cannot read holds none of the files the generators want, as far as we know
                print("skip", key, e, file=sys.stderr)
            kept.append(f"{key}\t-\t-")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    return kept


def index_rows(lines: list[str]) -> list[tuple[str, str, str]]:
    """The index lines as (bundle key `hash/version`, type, container path); a bundle's read mark is (key, "-", "-")."""
    return [tuple((line.split("\t") + ["", ""])[:3]) for line in lines]


def sprite_bundles(lines: list[str], pick: Callable[[str], K | None]) -> list[str]:
    """The keys of the bundles, sorted, that hold a Sprite whose container path `pick` maps to a key (None: not wanted)."""
    return sorted({key for key, kind, path in index_rows(lines) if kind == "Sprite" and pick(path) is not None})


def bundle_sprites(unpack: Path, pick: Callable[[str], K | None]) -> Iterator[tuple[K, object]]:
    """(key, Sprite) for each Sprite of the UnityCache bundles whose container path `pick` maps to a key (None: not wanted),
    each key once, the first bundle in key order winning. Only the bundles the index (bundle_index) names for one are read.
    A sprite is found by its container path, the name the bundle files it under: one the container does not list, or a
    texture with no Sprite of its own, is not found. The Sprite is UnityPy's, read: `.image` is its texture's part,
    sprite_image the whole rect.

    Each tool chose its own way before (#729): the last bundle won in grace_icons, sinner_cards and theme_pack_covers, the
    first one in gift_recipes; theme_pack_covers matched every object's name in every bundle, its Texture2D too. On client
    1.118.1 no container path is in two bundles, every wanted sprite is a container's Sprite, and the tools write the same
    bytes either way."""
    cache = unpack / BUNDLES
    seen = set()
    for key in sprite_bundles(bundle_index(cache, unpack / INDEX), pick):
        for path, obj in unity(cache / key / "__data").container.items():
            if obj.type.name == "Sprite" and (k := pick(path)) is not None and k not in seen:
                seen.add(k)
                yield k, obj.read()


def sprite_image(sprite) -> "Image.Image":
    """The sprite over its whole rect. A tight-packed sprite (the boss pictures) keeps only its opaque part in the texture
    and UnityPy's `image` is that part; the UI lays out the whole rect, so the part goes back where `textureRectOffset`
    (from the rect's bottom left) puts it."""
    from PIL import Image

    im = sprite.image
    w, h = round(sprite.m_Rect.width), round(sprite.m_Rect.height)
    if im.size == (w, h):
        return im
    off = sprite.m_RD.textureRectOffset
    full = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    full.paste(im.convert("RGBA"), (round(off.x), h - round(off.y) - im.height))
    return full
