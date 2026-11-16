"""Write the settings GUI's gift name plates (#786): gui/src/gift_plates/<sin>.webp and plates.json.

Usage: uv run --group unpack python tools/gift_plates.py
Reads `.local/unpack/` (see docs/agents/local-dev.md "Game data"); gui/src/gift_effects.json gives each gift its sin
(tools/llc_text.py gift_sins).

The game's gift panels (EgoGiftInfomationUI and EgoGiftInformationUIWithCombineExplain, scene level7 of the APK's player
data) draw a gift's name over the Image `NamePanel/img_namePlate`: a white plate with a dark edge and a halftone at its
bottom right (sprite MainUI_MirrorDungeon3_3_1, 235 x 86), sliced by its border, its colour white in the prefab. At run time
the game tints it by the gift's sin: the colours of UIColorManager (scene level1), whose fields are, in this order, 17
Colors, a List<{int key, 3 floats}> and a List<{ATTRIBUTE_TYPE key, Color}> (0..6 CRIMSON..VIOLET, the order
tools/sin_icons.py checks against EN_AttributeText). That the panel tints by this list is read off the game's screens: the
plates and the gift names of tests/screens match it (tests/test_gift_plates.py), the code that sets it was not read.

Both are found through the game's own objects, never by sprite name or path id, and checked: a second plate sprite, an Image
whose layout or white colour differs, or a colour list out of place stops the tool before a file is written.

Each plate is the sprite times its sin's colour, as the game tints it. The name goes on it in the dark or the light ink
(INKS), and the ink must hold TARGET contrast against every pixel of the plate the name can cover (BAND, halftone
included): the dark ink on the game's colour when it holds, else the light ink on the game's colour darkened by `shade`
just enough. plates.json gives each sin its game colour, shade, ink and the contrast its ink reaches, and the sprite's
border, by which the GUI slices the plate. Written against client 1.119.0; rerun it after a client update
(docs/spec/05-game-data.md section 8).
"""

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from local_dir import local_dir
from sin_icons import ATTRIBUTES, COLOURS as SINS, check_sin_order, load, obj
from unity_files import PLAYER_DATA, sprite_image, write_webps

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "gui/src/gift_plates"
EFFECTS = REPO / "gui/src/gift_effects.json"
PANEL_SCENE, PLATE, PANEL = "level7", "img_namePlate", "NamePanel"  # the plate's GameObject and its parent's name
COLOUR_SCENE, MANAGER = "level1", "UIColorManager"
COLOURS_BEFORE = 17  # UIColorManager's Colors before its two keyed lists
INKS = {"dark": "#000000", "light": "#ffffff"}
TARGET = 4.6  # 4.5:1, and a margin for the screen's scaling and rounding
# The part of the sprite (left, top, right, bottom, as fractions) the name can cover: the GUI centres it on the plate with
# padding, its line in the middle half of the height (gui/src/giftlists.css .gl-plate).
BAND = (0.08, 0.25, 0.92, 0.75)
STEP = 0.005  # how much darker each try of the light ink's shade
QUALITY = 100  # lossless: the contrast is measured on these pixels


@dataclass
class Plate:
    image: Image.Image
    shade: float
    ink: str
    contrast: float


def rgb(hexc: str) -> tuple[int, int, int]:
    return tuple(int(hexc[i:i + 2], 16) for i in (1, 3, 5))


def luminance(pixels: np.ndarray) -> np.ndarray:
    """WCAG relative luminance of 0..255 RGB values (the last axis)."""
    c = pixels / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def contrast(image: Image.Image, ink: str) -> float:
    """The least contrast of `ink` against the opaque pixels of BAND, rounded down to 0.01."""
    a = np.asarray(image.convert("RGBA"), dtype=np.float64)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = (round(f * n) for f, n in zip(BAND, (w, h, w, h)))
    band = a[y0:y1, x0:x1].reshape(-1, 4)
    lum = luminance(band[band[:, 3] == 255][:, :3])
    ink_lum = luminance(np.array(rgb(ink), dtype=np.float64))
    ratios = (np.maximum(lum, ink_lum) + 0.05) / (np.minimum(lum, ink_lum) + 0.05)
    return math.floor(float(ratios.min()) * 100) / 100


def tint(sprite: Image.Image, colour: tuple[float, float, float]) -> Image.Image:
    """The sprite times a colour (0..255 a channel), alpha kept: what the game's Image colour does."""
    a = np.asarray(sprite.convert("RGBA"), dtype=np.float64)
    out = a.copy()
    out[..., :3] = np.rint(a[..., :3] * np.array(colour) / 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def plate(sprite: Image.Image, colour: str) -> Plate:
    """A sin's plate: the dark ink on the game's colour when it holds TARGET, else the light ink on the colour darkened by
    the largest shade that holds it."""
    game = rgb(colour)
    image = tint(sprite, game)
    if (c := contrast(image, INKS["dark"])) >= TARGET:
        return Plate(image, 1, "dark", c)
    shade = 1.0
    while shade > 0:
        image = tint(sprite, tuple(v * shade for v in game))
        if (c := contrast(image, INKS["light"])) >= TARGET:
            return Plate(image, shade, "light", c)
        shade = round(shade - STEP, 3)
    raise SystemExit(f"no shade of {colour} holds {TARGET}:1 for the light ink")


def keyed(raw: bytes, off: int, fmt: str) -> tuple[list[tuple], int]:
    """A serialized List of `fmt` structs at off, and the offset after it; one that does not fit stops the tool."""
    size = struct.calcsize(fmt)
    count = struct.unpack_from("<i", raw, off)[0]
    if not 0 < count < 64 or off + 4 + size * count > len(raw):
        raise SystemExit(f"{MANAGER}: no list at {off} (count {count}): its fields moved, read the class again")
    return [struct.unpack_from(fmt, raw, off + 4 + size * i) for i in range(count)], off + 4 + size * count


def sin_colours(raw: bytes) -> dict[str, str]:
    """sin -> its colour (#rrggbb) in UIColorManager's raw bytes: past the MonoBehaviour header, the name, COLOURS_BEFORE
    Colors and the list of {key, 3 floats}, the list of {ATTRIBUTE_TYPE, Color}. A sin missing, or a colour that is not an
    opaque one, stops the tool."""
    name_len = struct.unpack_from("<i", raw, 28)[0]
    _, off = keyed(raw, 32 + (name_len + 3) // 4 * 4 + 16 * COLOURS_BEFORE, "<i3f")
    pairs, _ = keyed(raw, off, "<i4f")
    colours = {key: rgba for key, *rgba in pairs}
    out = {}
    for key, sin in enumerate(SINS):
        c = colours.get(key)
        if c is None or not all(0 <= v <= 1 for v in c) or c[3] != 1:
            raise SystemExit(f"{MANAGER}: ATTRIBUTE_TYPE {key} ({sin}) has no opaque colour: {c}")
        out[sin] = "#" + "".join(f"{round(v * 255):02x}" for v in c[:3])
    return out


def script_name(data: Path, scene: str, raw: bytes) -> str:
    """The class of a MonoBehaviour of `scene`, from its m_Script pointer."""
    file_id, path_id = struct.unpack_from("<iq", raw, 16)
    externals = [e.path for e in next(iter(load(data, scene).files.values())).externals]
    return obj(load(data, scene if file_id == 0 else externals[file_id - 1]), path_id).read().m_ClassName


def resolve(data: Path, scene: str, pointer):
    externals = [e.path for e in next(iter(load(data, scene).files.values())).externals]
    file_id, path_id = (pointer.m_FileID, pointer.m_PathID) if hasattr(pointer, "m_FileID") else pointer
    name = scene if file_id == 0 else externals[file_id - 1]
    return name, obj(load(data, name), path_id)


def image_sprite(data: Path, scene: str, raw: bytes):
    """The Sprite a UI Image draws, from its raw bytes: past the header and name, m_Material, m_Color (white, or the tool
    stops: the game tints the plate itself), m_RaycastTarget, m_RaycastPadding, m_Maskable and an empty
    m_OnCullStateChanged, m_Sprite."""
    off = 32 + (struct.unpack_from("<i", raw, 28)[0] + 3) // 4 * 4 + 12
    colour = struct.unpack_from("<4f", raw, off)
    calls = struct.unpack_from("<i", raw, off + 16 + 4 + 16 + 4)[0]
    if colour != (1, 1, 1, 1) or calls != 0:
        raise SystemExit(f"{PLATE}: colour {colour}, {calls} cull callbacks: the Image's layout or colour changed")
    _, sprite = resolve(data, scene, struct.unpack_from("<iq", raw, off + 16 + 4 + 16 + 4 + 4))
    if sprite.type.name != "Sprite":
        raise SystemExit(f"{PLATE}: draws a {sprite.type.name}, not a Sprite")
    return sprite.read()


def plate_sprite(data: Path):
    """The Sprite of every `NamePanel/img_namePlate` Image of PANEL_SCENE; more than one sprite, or none, stops the tool."""
    found = {}
    for o in load(data, PANEL_SCENE).objects:
        if o.type.name != "GameObject" or o.peek_name() != PLATE:
            continue
        go = o.read()
        parts = [resolve(data, PANEL_SCENE, c.component if hasattr(c, "component") else c)[1] for c in go.m_Component]
        transform = next(p for p in parts if p.type.name in ("RectTransform", "Transform")).read()
        _, father = resolve(data, PANEL_SCENE, transform.m_Father)
        if resolve(data, PANEL_SCENE, father.read().m_GameObject)[1].read().m_Name != PANEL:
            continue
        images = [p for p in parts if p.type.name == "MonoBehaviour" and script_name(data, PANEL_SCENE, p.get_raw_data()) == "Image"]
        for image in images:
            sprite = image_sprite(data, PANEL_SCENE, image.get_raw_data())
            found[sprite.m_Name] = sprite
    if len(found) != 1:
        raise SystemExit(f"{PANEL}/{PLATE} draws {sorted(found) or 'nothing'} in {PANEL_SCENE}: expected one plate sprite")
    return next(iter(found.values()))


def manager_raw(data: Path) -> bytes:
    """The raw bytes of the one UIColorManager of COLOUR_SCENE."""
    found = [o for o in load(data, COLOUR_SCENE).objects if o.type.name == "MonoBehaviour"
             and len(raw := o.get_raw_data()) > 32 and script_name(data, COLOUR_SCENE, raw) == MANAGER]
    if len(found) != 1:
        raise SystemExit(f"{len(found)} {MANAGER} in {COLOUR_SCENE}, expected 1")
    return found[0].get_raw_data()


def main():
    unpack = local_dir("unpack")
    data = unpack / PLAYER_DATA
    if not (data / PANEL_SCENE).exists() and not (data / f"{PANEL_SCENE}.split0").exists():
        raise SystemExit(f"no unpacked client at {data}: see docs/agents/local-dev.md 'Game data'")
    check_sin_order(json.loads((unpack / ATTRIBUTES).read_text(encoding="utf-8-sig"))["dataList"])
    sprite = plate_sprite(data)
    image = sprite_image(sprite).convert("RGBA")
    colours = sin_colours(manager_raw(data))
    plates = {sin: plate(image, colour) for sin, colour in colours.items()}
    used = {e["sin"] for e in json.loads(EFFECTS.read_text(encoding="utf-8"))["effects"].values()}
    if used - set(plates):
        raise SystemExit(f"gift_effects.json names sins with no plate: {sorted(used - set(plates))}")
    size = write_webps({sin: p.image for sin, p in plates.items()}, OUT, QUALITY, lossless=True)
    b = sprite.m_Border  # x left, y bottom, z right, w top, in the sprite's pixels
    doc = {
        "note": (f"The plate the game draws a gift's name on, one per sin (#786), written by tools/gift_plates.py: sprite "
                 f"{sprite.m_Name} (the Image NamePanel/img_namePlate of the game's gift panels) times the sin's colour in "
                 "UIColorManager, as the game tints it. colour: the game's; shade: what the colour is multiplied by so the "
                 f"ink holds {TARGET}:1; ink: the name's ink (inks); contrast: the least the ink reaches against the plate where "
                 "the name can go (the sprite's middle half in height, all but 8 % at each end in width, halftone included). "
                 "border: the sprite's slice border in its pixels (top, right, bottom, left)."),
        "sprite": sprite.m_Name,
        "size": list(image.size),
        "border": [b.w, b.z, b.y, b.x],
        "inks": INKS,
        "plates": {sin: {"colour": colours[sin], "shade": p.shade, "ink": p.ink, "contrast": p.contrast} for sin, p in plates.items()},
    }
    (OUT / "plates.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    for sin, p in plates.items():
        print(f"{sin:8} {colours[sin]} x{p.shade:.3f} {p.ink:5} {p.contrast:.2f}:1")
    print(f"{len(plates)} plates -> {OUT} ({size} bytes)")


if __name__ == "__main__":
    main()
