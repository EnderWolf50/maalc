"""Compose one theme pack card the way the game's MirrorDungeonThemeCardUI prefab stacks it (#241).

Layers, bottom to top (every anchor, size and TextMeshPro setting below is read from the prefab in the client's
sharedassets7, see docs/spec/05-game-data.md section 2): the cover art inside the pack silhouette, the boss picture
(`bossSpriteId`), the "Long Battle" overlay (`isShowBaton`), the Limbus Company logo (unless `isHideLogo`), the WARNING
triangle (`isShowWarning`), the attack type and attribute badges, the plastic wrap and the title.
Not drawn: the hanging clip and the magnifier stamp (page UI, not the card) and the tilt (the page sways the cards).
"""

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD = (680, 1069)  # the prefab says 650 wide; the screenshots say 680 (badge grid and title width), see docs/spec/05-game-data.md section 2. Every box below is (x0, y0, x1, y1) as a fraction of it, y up
MAIN, FRONT = (-0.045, 0.033, 1.054, 0.98), (-0.045, 0.059, 1.054, 0.98)
BOSS, LOGO = (0.13, 0.25, 0.875, 0.836), (0.34, 0.26, 0.66, 0.34)
# Image_baton is a child of `main` (anchors (0,0.1)-(1,0.9) of it); its Text_Content (0.3,0.715)-(0.7,0.815) of that
BATON = (MAIN[0], MAIN[1] + 0.1 * (MAIN[3] - MAIN[1]), MAIN[2], MAIN[1] + 0.9 * (MAIN[3] - MAIN[1]))
BATON_TEXT = (0.3, 0.715, 0.7, 0.815)  # of BATON
BATON_COLOR, BATON_FONT = "73fbed", (5, 35)  # Text_Content: fontColor32, autosize range
BATON_LABEL = "Long Battle"  # EN_MirrorDungeonUI_5 mirror_theme_pack_baton
WARNING = (0.38, 0.79, 0.62, 0.92)  # read off two screenshots: the triangle is not in the prefab (set from code)
# [Rect]Attributes (0.128,0.035)-(0.5,0.125) holds a GridLayoutGroup with 96 x 96 cells, upper left first
CELL = (96 / CARD[0], 96 / CARD[1])
CELL0 = (0.128, 0.035)
CELL_ICON = ((0.05, 0.05, 1.0, 1.0), (0.13, 0.13, 0.87, 0.87))  # the two Icon children's anchors inside their cell
BADGE_SCALE = 1.12  # measured: the badges on screen are about 12 % bigger than the 96 px cells
DEFAULT_TINT = "a16a3b"  # the badge icons wear mapOptions SetColor_Cleared (a16a3b of 1204, measured on a screenshot)
ATTACK_ICON = {"PENETRATE": "pierce", "HIT": "hit", "SLASH": "slash"}
# attributeType -> (Icon_evil_2_<n>, fill colour). CRIMSON, AMBER, SHAMROCK and VIOLET are read off screenshots (the flame, the
# cracked rock, the leaf, the thorn wreath, with their fills); SCARLET, AZURE and INDIGO are guesses from the icons left over.
SIN_ICON = {
    "CRIMSON": (11, "940606"), "AMBER": (14, "e38600"), "SHAMROCK": (13, "689e07"), "VIOLET": (8, "6c0591"),
    "SCARLET": (12, "e05a14"), "AZURE": (9, "1e8cb4"), "INDIGO": (10, "1e3caa"),
}
SIN_OUTLINE = "ebcaa2"  # the attribute icons wear a cream outline

# [Text]Name: rect (0.15,0.17)-(0.85,0.255) with sizeDelta (9, 0) and anchoredPosition (4.5, 0); TextMeshProUGUI settings
NAME = (0.15, 0.17, 0.85, 0.255)
NAME_PAD, NAME_SHIFT = 9.0, 4.5
TMP = {"max": 65.0, "min": 1.0, "char": -2.0, "word": 1.0, "line": -5.0, "default_color": "ebcaa2"}
FACE = {"point": 195.0, "ascent": 148.2, "descent": 46.8, "line_height": 212.55, "spacing_offset": 6.0}  # the Mikodacs SDF font asset: FaceInfo, normalSpacingOffset
# material "Mikodacs SDF UnderLine": no outline, no glow, an underlay (drop shadow) offset (1, -1) in atlas texels,
# _GradientScale 12 texels sampled at point size 195
SHADOW = {"color": (4, 0, 1), "offset": 1.0, "gradient": 12.0}


def runs(text: str, color: str) -> list[tuple[str, str]]:
    """Split TMP rich text (`<color=#rrggbb>..</color>`) into (text, color) runs."""
    out, pos = [], 0
    for m in re.finditer(r"<color=#(\w+)>(.*?)</color>", text):
        if m.start() > pos:
            out.append((text[pos : m.start()], color))
        out.append((m[2], m[1]))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], color))
    return out


class Glyphs:
    """A font's glyph metrics in em, measured at the font asset's point size: advance, ascent and descent per character."""

    def __init__(self, font_path: Path):
        self.font = ImageFont.truetype(str(font_path), int(FACE["point"]))
        self.cache: dict[str, tuple[float, float, float]] = {}

    def of(self, c: str) -> tuple[float, float, float]:
        if c not in self.cache:
            _, top, _, bottom = self.font.getbbox(c, anchor="ls")
            ink = bool(c.strip())
            self.cache[c] = (self.font.getlength(c) / FACE["point"], -top / FACE["point"] if ink else 0.0, bottom / FACE["point"] if ink else 0.0)
        return self.cache[c]


def layout(tokens: list[tuple[str, str]], size: float, width: float, glyphs) -> list[tuple[list[tuple[str, str, float]], float]]:
    """Word-wrap coloured runs the way TextMeshPro does at font `size`: a list of (chars, width), each char (char, color, x)
    with x the pen position inside the line. A glyph advances by its own advance plus the font asset's normal spacing offset
    and the text's character spacing; a space also by the word spacing (all in 1/100 em)."""
    em = size * 0.01

    def adv(c: str) -> float:
        return glyphs.of(c)[0] * size + (FACE["spacing_offset"] + TMP["char"]) * em + (TMP["word"] * em if c == " " else 0.0)

    words = [(w, c) for t, c in tokens for w in re.findall(r"\S+|\s+", t)]
    lines: list[list[tuple[str, str, float]]] = []
    cur: list[tuple[str, str, float]] = []
    x = 0.0
    for text, color in words:
        if cur and not text.isspace() and x + sum(adv(c) for c in text) > width:
            lines.append(cur)
            cur, x = [], 0.0
        if text.isspace() and not cur:
            continue
        for c in text:
            cur.append((c, color, x))
            x += adv(c)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:  # a line ends at its last visible glyph: trailing spaces do not count
        while ln and ln[-1][0] == " ":
            ln.pop()
        out.append((ln, (ln[-1][2] + adv(ln[-1][0])) if ln else 0.0))
    return out


def line_advance(size: float) -> float:
    """Baseline to baseline distance: the font's line height plus the line spacing (1/100 em)."""
    return FACE["line_height"] / FACE["point"] * size + TMP["line"] * 0.01 * size


def text_height(lines, size: float, glyphs) -> float:
    """From the top of the first line's tallest glyph to the bottom of the last line's lowest one."""
    first, last = lines[0][0], lines[-1][0]
    ascent = max((glyphs.of(c)[1] for c, _, _ in first), default=0.0) * size
    descent = max((glyphs.of(c)[2] for c, _, _ in last), default=0.0) * size
    return ascent + (len(lines) - 1) * line_advance(size) + descent


def round_size(size: float) -> float:
    """TMP keeps the auto-size in steps of 0.05."""
    return int(size * 20 + 0.5) / 20


def fit_title(tokens: list[tuple[str, str]], box_w: float, box_h: float, glyphs):
    """TMP's auto-size: bisect the font size between the largest size that fitted and the smallest that overflowed.
    The prefab's `lineSpacingMax` (-20, tighten the lines before shrinking) is not applied: with it the solver picks
    sizes and line breaks the screenshots do not show (docs/spec/05-game-data.md section 2). Returns (size, lines)."""
    size, lo, hi = TMP["max"], TMP["min"], TMP["max"]
    for _ in range(64):
        lines = layout(tokens, size, box_w, glyphs)
        if all(w <= box_w + 1e-4 for _, w in lines) and text_height(lines, size, glyphs) <= box_h + 1e-4:
            lo = size
            if hi - size <= 0.051:
                break
            size = round_size(size + max((hi - size) / 2, 0.05))
        else:
            hi = size
            nxt = max(round_size(size - max((size - lo) / 2, 0.05)), TMP["min"])
            if nxt >= size:
                break
            size = nxt
    return size, layout(tokens, size, box_w, glyphs)


def draw_title(img: Image.Image, tokens, font_path: Path, k: float, rect: tuple[float, float, float, float]):
    """Title text with the material's drop shadow; `rect` is the TMP rect in card pixels (y down)."""
    glyphs = Glyphs(font_path)
    x0, y0, x1, y1 = rect
    size, lines = fit_title(tokens, x1 - x0, y1 - y0, glyphs)
    # middle alignment centres the lines' own ascent..descent band (the font's 0.76 / 0.24 em), not the glyph extents
    first = (y0 + y1) / 2 + (FACE["ascent"] - FACE["descent"]) / 2 / FACE["point"] * size - (len(lines) - 1) / 2 * line_advance(size)
    font = ImageFont.truetype(str(font_path), size * k)
    shift = SHADOW["offset"] * SHADOW["gradient"] / FACE["point"] * size
    d = ImageDraw.Draw(img)
    for i, (ln, width) in enumerate(lines):
        base = first + i * line_advance(size)
        left = (x0 + x1) / 2 - width / 2
        for c, color, x in ln:
            for off, fill in (((shift, shift), SHADOW["color"]), ((0.0, 0.0), "#" + color)):
                d.text(((left + x + off[0]) * k, (base + off[1]) * k), c, font=font, fill=fill, anchor="ls")


def scaled(frac, factor: float):
    """The anchor box `frac` grown by `factor` around its centre."""
    cx, cy, w, h = (frac[0] + frac[2]) / 2, (frac[1] + frac[3]) / 2, (frac[2] - frac[0]) / 2 * factor, (frac[3] - frac[1]) / 2 * factor
    return cx - w, cy - h, cx + w, cy + h


def px(frac) -> tuple[float, float, float, float]:
    """An anchor box (y up) in card pixels (y down)."""
    return frac[0] * CARD[0], (1 - frac[3]) * CARD[1], frac[2] * CARD[0], (1 - frac[1]) * CARD[1]


def sub(frac, rel):
    """The box `rel` (anchors, y up) inside the box `frac`."""
    w, h = frac[2] - frac[0], frac[3] - frac[1]
    return frac[0] + rel[0] * w, frac[1] + rel[1] * h, frac[0] + rel[2] * w, frac[1] + rel[3] * h


def fit(im: Image.Image, frac, k: float, stretch: bool = False) -> tuple[Image.Image, tuple[int, int]]:
    """`im` scaled into the anchor box `frac`, keeping its aspect unless `stretch`, centred: (image, (x, y) of its corner)."""
    x0, y0, x1, y1 = (v * k for v in px(frac))
    if stretch:
        return im.resize((max(1, round(x1 - x0)), max(1, round(y1 - y0))), Image.LANCZOS), (round(x0), round(y0))
    s = min((x1 - x0) / im.width, (y1 - y0) / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    return im, (round((x0 + x1) / 2 - im.width / 2), round((y0 + y1) / 2 - im.height / 2))


def tinted(icon: Image.Image, color: str) -> Image.Image:
    solid = Image.new("RGBA", icon.size, tuple(int(color[i : i + 2], 16) for i in (0, 2, 4)) + (255,))
    return Image.composite(solid, Image.new("RGBA", icon.size, (0, 0, 0, 0)), icon.convert("RGBA").getchannel("A"))


def outlined(icon: Image.Image, fill: str, outline: str, width: int = 6) -> Image.Image:
    """The silhouette in `fill` over a copy grown by `width` px in `outline`."""
    pad = Image.new("RGBA", (icon.width + 2 * width, icon.height + 2 * width), (0, 0, 0, 0))
    pad.paste(tinted(icon, fill), (width, width))
    grown = Image.new("RGBA", pad.size, (0, 0, 0, 0))
    grown.paste(tinted(icon, outline), (width, width))
    grown.putalpha(grown.getchannel("A").filter(ImageFilter.MaxFilter(2 * width + 1)))
    grown.alpha_composite(pad)
    return grown


def map_color(ui: dict, key: str, default: str) -> str:
    return next((o["value"] for o in ui.get("mapOptions", []) if o["key"] == key), default)


def card(parts: dict[str, Image.Image], art: Image.Image, boss: Image.Image | None, ui: dict, title: str, fonts: dict[str, Path], k: float = 0.6) -> Image.Image:
    """The card as the game stacks it, cropped to the pack silhouette. `ui` is the pack's `uiConfigs` of the static data,
    `fonts` the Mikodacs ("title") and Pretendard ("baton") font files."""
    size = (round(CARD[0] * k), round(CARD[1] * k))
    sil, sil_pos = fit(parts["silhouette"], MAIN, k)
    mask = Image.new("L", size, 0)
    mask.paste(sil.getchannel("A"), sil_pos)

    def put(base: Image.Image, im: Image.Image, pos, clip: bool = False):
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(im, pos)
        if clip:
            layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", size, 0), mask))
        base.alpha_composite(layer)

    base = Image.new("RGBA", size, (0, 0, 0, 0))
    put(base, *fit(art.convert("RGBA"), MAIN, k), clip=True)
    if boss is not None:
        put(base, *fit(boss.convert("RGBA"), BOSS, k), clip=True)
    if ui.get("isShowBaton"):
        put(base, *fit(parts["baton"], BATON, k, stretch=True), clip=True)
        x0, y0, x1, y1 = px(sub(BATON, BATON_TEXT))
        glyphs, fs = Glyphs(fonts["baton"]), BATON_FONT[1]
        while fs > BATON_FONT[0] and (sum(glyphs.of(c)[0] for c in BATON_LABEL) * fs > x1 - x0 or fs > y1 - y0):  # TMP auto-size, no wrapping
            fs -= 0.05
        font = ImageFont.truetype(str(fonts["baton"]), fs * k)
        ImageDraw.Draw(base).text(((x0 + x1) / 2 * k, (y0 + y1) / 2 * k), BATON_LABEL, font=font, fill="#" + BATON_COLOR, anchor="mm")
    if not ui.get("isHideLogo"):
        put(base, *fit(parts["logo"], LOGO, k))
    if ui.get("isShowWarning"):
        put(base, *fit(parts["warning"], WARNING, k))
    tint = map_color(ui, "SetColor_Cleared", DEFAULT_TINT)
    icons = []  # (icon image, box inside its cell)
    if ui.get("attackType") in ATTACK_ICON:
        icons.append((tinted(parts["attack_" + ATTACK_ICON[ui["attackType"]]], tint), CELL_ICON[0]))
    if ui.get("attributeType") in SIN_ICON:
        n, fill = SIN_ICON[ui["attributeType"]]
        icons.append((outlined(parts[f"sin_{n}"], fill, SIN_OUTLINE), CELL_ICON[1]))
    for i, (icon, rel) in enumerate(icons):
        cell = scaled((CELL0[0] + i * CELL[0], CELL0[1], CELL0[0] + (i + 1) * CELL[0], CELL0[1] + CELL[1]), BADGE_SCALE)
        put(base, *fit(parts["badge"], cell, k))
        put(base, *fit(icon, sub(cell, rel), k))
    put(base, *fit(parts["front"], FRONT, k))
    cx = (NAME[0] + NAME[2]) / 2 * CARD[0] + NAME_SHIFT
    w = (NAME[2] - NAME[0]) * CARD[0] + NAME_PAD
    top, bottom = (1 - NAME[3]) * CARD[1], (1 - NAME[1]) * CARD[1]
    draw_title(base, runs(title, ui.get("textColor") or TMP["default_color"]), fonts["title"], k, (cx - w / 2, top, cx + w / 2, bottom))
    return base.crop(mask.getbbox() or (0, 0, *size))
