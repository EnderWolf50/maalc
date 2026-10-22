"""Compose one theme pack card the way the game's MirrorDungeonThemeCardUI prefab stacks it (#241).

Layers, bottom to top (anchors read from the prefab in the client's sharedassets7): the cover art inside the pack silhouette,
the boss picture (packs with a `bossSpriteId`), the Limbus Company logo (unless `isHideLogo`), the WARNING triangle
(`isShowWarning`), the attack type badge (`attackType`), the plastic wrap, the title (Mikodacs, `textColor`, auto-sized).
Not drawn: the hanging clip and the magnifier stamp (page UI, not the card), the tilt (the page sways the cards).
"""

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARD = (650, 1069)  # the prefab's RectTransform; every box below is (x0, y0, x1, y1) as a fraction of it, y up
MAIN, FRONT = (-0.045, 0.033, 1.054, 0.98), (-0.045, 0.059, 1.054, 0.98)
BOSS, LOGO, NAME = (0.13, 0.25, 0.875, 0.836), (0.34, 0.26, 0.66, 0.34), (0.15, 0.17, 0.85, 0.255)
WARNING = (0.38, 0.79, 0.62, 0.92)  # read off a screenshot, the prefab does not hold it
BADGE = (0.209, 0.035, 0.346, 0.118)  # likewise: where "To be Pierced" shows its attack type
BADGE_TINT = (217, 149, 74)  # likewise
MAX_FONT = 62  # px on the 650 px card: a one-line title is width-limited, the cap keeps short titles from growing past the game's
OUTLINE = (16, 24, 32)
ATTACK_ICON = {"PENETRATE": "pierce", "HIT": "hit", "SLASH": "slash"}


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


def wrap(tokens: list[tuple[str, str]], font, width: float) -> list[list[tuple[str, str]]]:
    """Greedy word wrap of coloured runs into lines no wider than `width` (a single longer word stays on its line)."""
    words = [(w, c) for t, c in tokens for w in re.findall(r"\S+|\s+", t)]
    lines, cur, w = [], [], 0.0
    for word, c in words:
        n = font.getlength(word)
        if cur and not word.isspace() and w + n > width:
            lines.append(cur)
            cur, w = [], 0.0
        if cur or not word.isspace():
            cur.append((word, c))
            w += n
    return lines + [cur] if cur else lines


def draw_title(img: Image.Image, box, tokens, font_path: Path, cap: float):
    """Largest font up to `cap` whose wrapped title fits `box`; centred, with a dark outline."""
    size = int(cap)
    while True:
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap(tokens, font, box[2] - box[0])
        height = len(lines) * size * 1.1
        if size <= 6 or (height <= box[3] - box[1] and all(sum(font.getlength(w) for w, _ in ln) <= box[2] - box[0] for ln in lines)):
            break
        size -= 1
    d = ImageDraw.Draw(img)
    y = (box[1] + box[3]) / 2 - height / 2 + size * 0.55
    for ln in lines:
        x = (box[0] + box[2]) / 2 - sum(font.getlength(w) for w, _ in ln) / 2
        for w, c in ln:
            d.text((x, y), w, font=font, fill="#" + c, anchor="lm", stroke_width=max(1, size // 14), stroke_fill=OUTLINE)
            x += font.getlength(w)
        y += size * 1.1


def fit(im: Image.Image, frac, k: float) -> tuple[Image.Image, tuple[int, int]]:
    """`im` scaled to fit the anchor box `frac` keeping its aspect, centred: (image, (x, y) of its corner)."""
    x0, y0, x1, y1 = frac[0] * CARD[0] * k, (1 - frac[3]) * CARD[1] * k, frac[2] * CARD[0] * k, (1 - frac[1]) * CARD[1] * k
    s = min((x1 - x0) / im.width, (y1 - y0) / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    return im, (round((x0 + x1) / 2 - im.width / 2), round((y0 + y1) / 2 - im.height / 2))


def card(parts: dict[str, Image.Image], art: Image.Image, boss: Image.Image | None, ui: dict, title: str, font_path: Path, k: float = 0.6) -> Image.Image:
    """The card as the game stacks it, cropped to the pack silhouette. `ui` is the pack's `uiConfigs` of the static data."""
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
    if not ui.get("isHideLogo"):
        put(base, *fit(parts["logo"], LOGO, k))
    if ui.get("isShowWarning"):
        put(base, *fit(parts["warning"], WARNING, k))
    if ui.get("attackType") in ATTACK_ICON:
        badge, pos = fit(parts["badge"], BADGE, k)
        put(base, badge, pos)
        icon = parts["attack_" + ATTACK_ICON[ui["attackType"]]]
        icon = Image.composite(Image.new("RGBA", icon.size, BADGE_TINT + (255,)), Image.new("RGBA", icon.size, (0, 0, 0, 0)), icon.getchannel("A"))
        icon, _ = fit(icon, (BADGE[0] + 0.2 * (BADGE[2] - BADGE[0]), BADGE[1] + 0.2 * (BADGE[3] - BADGE[1]), BADGE[2] - 0.2 * (BADGE[2] - BADGE[0]), BADGE[3] - 0.2 * (BADGE[3] - BADGE[1])), k)
        put(base, icon, (pos[0] + (badge.width - icon.width) // 2, pos[1] + (badge.height - icon.height) // 2))
    put(base, *fit(parts["front"], FRONT, k))
    box = (NAME[0] * size[0], (1 - NAME[3]) * size[1], NAME[2] * size[0], (1 - NAME[1]) * size[1])
    draw_title(base, box, runs(title, ui.get("textColor") or "ffffff"), font_path, MAX_FONT * k)
    return base.crop(mask.getbbox() or (0, 0, *size))
