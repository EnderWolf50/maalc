"""Shop decisions, free of MaaFramework (docs/spec/03-decisions.md section 13).

actions.py reads the shop pages and taps; everything here is plain data in, plain data out.
"""

from difflib import SequenceMatcher

import numpy as np

from gift_search import _runs

ROUNDS = 10
CELL_HALF = 48  # screen px kept around a cell's centre: its icon, tier numerals and keyword badge
TIERS = {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}  # numeral strokes at its top and bottom row: I-V


LOOKALIKE = str.maketrans("OoDQIl|SsBZz", "000011155822")


def cost_value(text):
    """The Cost an OCR read stands for, look-alike letters taken as digits (33O2 -> 3302); None without a digit (#82)."""
    if not any(c.isdigit() for c in text):
        return None
    return int("".join(c for c in text.translate(LOOKALIKE) if c.isdigit()))


def rescale(image, factor):
    """image resized by factor, nearest pixel (no OpenCV in the agent)."""
    h, w = image.shape[:2]
    ys = np.minimum((np.arange(round(h * factor)) / factor).astype(int), h - 1)
    xs = np.minimum((np.arange(round(w * factor)) / factor).astype(int), w - 1)
    return np.ascontiguousarray(image[ys][:, xs])


def cell_crop(image, x, y, scale):
    """The grid cell centred at (x, y), resized so its gift icon is at its GiftSearch template's size.

    scale: the page's icon size over the template's (fuse and sell pages 1.1, offers 0.8; live captures).
    The cell's centre is the crop's centre.
    """
    return rescale(image[y - CELL_HALF:y + CELL_HALF, x - CELL_HALF:x + CELL_HALF], 1 / scale)


def tier(cell):
    """A cell's tier (1-5) from its yellow numerals top left (cell_crop), or None (no numerals: a skill, a dim page).

    I, II and III are 1-3 bars top to bottom; IV and V end in a V, so the bottom row has a stroke fewer.
    """
    mid = cell.shape[0] // 2
    box = cell[mid - 36:mid - 8, mid - 36:mid - 16].astype(int)
    b, g, r = box[:, :, 0], box[:, :, 1], box[:, :, 2]
    yellow = (r > 200) & (g > 140) & (b < 90)
    top, bottom = 9, 19  # rows inside every numeral on both scales
    bars = [(x, n) for x, n in _runs(np.flatnonzero(yellow[top])) if n >= 2]
    if not bars:
        return None
    lo, hi = bars[0][0] - 1, bars[-1][0] + bars[-1][1] + 1  # icon art beside the numerals stays out
    ends = [n for _, n in _runs(np.flatnonzero(yellow[bottom, lo:hi])) if n >= 2]
    return TIERS.get((len(bars), len(ends)))


def can_spend(cost, price, reserve):
    """Whether paying price still leaves the reserve (spec 03 section 13: every spend keeps it)."""
    return cost - price >= reserve


def heal_plan(mode, cost, reserve, dead, heal_cost):
    """("full", 1), ("revive", n) or None for the team's heal setting.

    full heals everyone once when it can pay; revive brings back as many of the dead as it can pay for.
    """
    if mode == "full" and can_spend(cost, heal_cost, reserve):
        return "full", 1
    if mode == "revive":
        n = min(dead, max(0, (cost - reserve) // heal_cost))
        if n:
            return "revive", n
    return None


def read_slots(results):
    """Shop slots from the OCR results [(text, (x, y, w, h))] of the offer grid, top row first.

    Each is {"name", "price", "purchased", "x", "y"}, x and y the price line's centre. A price is the
    tall line with no letters (a "??" price is None); the name is the line just under it; a bought
    slot has "Purchased" over its icon. Lines are found relative to each other, not at fixed rows.
    """
    lines = [(t, x + w // 2, y + h // 2, h) for t, (x, y, w, h) in results]
    slots = []
    for t, x, y, h in sorted(lines, key=lambda line: (line[2] // 40, line[1])):
        if h < 18 or any(c.isascii() and c.isalpha() for c in t):
            continue  # tier numerals on the icons read as short lines
        near = [(u, uy) for u, ux, uy, _ in lines if abs(ux - x) < 75 and u != t]
        name = next((u for u, uy in near if 10 < uy - y < 40), "")
        digits = "".join(c for c in t if c.isdigit())
        slots.append({
            "name": name,
            "price": int(digits) if digits and "?" not in t else None,
            "purchased": any("Purchased" in u for u, uy in near if -110 < uy - y < 0),
            "short": any("Enough" in u for u, uy in near if -110 < uy - y < 0),  # red "Not Enough Cost"
            "x": x,
            "y": y,
        })
    return slots


def red_pixels(box):
    """How many pixels of box (BGR) are dark-to-bright red: R over 110, G and B under 60, R over 3x G."""
    b, g, r = (box[:, :, i].astype(int) for i in range(3))
    return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())


def short_cell(image, x, y):
    """Whether the offer whose icon is centred at (x, y) is tagged Not Enough Cost: its price line is red.

    Told by colour, as OCR misses the red tag and reads a red 160 as 16 (live 2026-10-18). The price line sits 12 px
    under the icon's frame, so a red gift cannot colour it. 165 offers on 31 shop screens: a red price 141-167 red
    pixels, an orange one 0-16 (up to 47 on video stills); red icons up to 261. The tag over the icon adds nothing:
    it came with a red price every time, and the band it needs ends 3 px over the frame.
    """
    return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90


def dialog_price(cost, preview):
    """The price a purchase dialog's Cost preview ("2864 > 2612", read as "28642612") stands for; None when unread.

    It is the offer actually opened, so it beats the grid's price if the grid moved under the tap.
    """
    digits = "".join(c for c in preview if c.isdigit())
    head = str(cost)
    if cost is None or not digits.startswith(head) or len(digits) == len(head):
        return None
    return cost - int(digits[len(head):])


def buyable(slot, cost=None):
    """Whether a shop slot {"name", "price", "purchased", "short"} is worth reading: a gift on sale for Cost.

    Skill replacements and ID Skill Search show "??" (no price) or take Starlight; a bought slot moves
    to the end of the grid, tagged Purchased. One dearer than the Cost (tagged Not Enough Cost) opens
    no purchase dialog (live 2026-10-18), so it is not tapped.
    """
    if not on_sale(slot) or slot.get("short"):
        return False
    return cost is None or slot["price"] <= cost


def on_sale(slot):
    """Whether a shop slot is a gift on sale for Cost, affordable or not: not bought, not a skill, not "??"."""
    name = slot["name"]
    return slot["price"] is not None and not slot["purchased"] and "Replace" not in name and "ID Skill" not in name


def buy_plan(offers, cost, reserve, sold):
    """(grid indexes to buy, last first; the wanted price or None) for the main-keyword offers on show (#76).

    offers: [(grid index, tier or None, price)]. Highest tier first, cheapest first within a tier, each only
    while the reserve stays. When the first choice is too dear and no sale has been tried for it, nothing is
    bought: wanted asks the next round to sell first. Bought from the back, a purchase (moved to the grid's
    end) leaves the offers before it in place, so the grid is read once.
    """
    order = sorted(offers, key=lambda o: (-(o[1] or 0), o[2]))
    if order and not sold and not can_spend(cost, order[0][2], reserve):
        return [], order[0][2]
    picked = []
    for i, _, price in order:
        if can_spend(cost, price, reserve):
            picked.append(i)
            cost -= price
    return sorted(picked, reverse=True), None


def refresh_choice(cost, reserve, used, limit, normal_fee, keyword_fee, margin):
    """"keyword", "normal" or None: the refresh to use now (spec 03 section 13).

    Keyword refresh first, then normal; either one only while it leaves margin plus the reserve
    to buy with, and only limit times per shop (both kinds count).
    """
    if used >= limit:
        return None
    for kind, fee in (("keyword", keyword_fee), ("normal", normal_fee)):
        if fee is not None and can_spend(cost, fee + margin, reserve):
            return kind
    return None


def cell_prices(results, cells):
    """{cell index: sell price} from the OCR results [(text, (x, y, w, h))] of the sell page's grid.

    A price is a number line 35-60 px under its cell's centre (its coin reads as junk left of it); a cell
    whose price is cut off by the grid's edge has none.
    """
    prices = {}
    for t, (x, y, w, h) in results:
        tx, ty = x + w // 2, y + h // 2
        if not t.isdigit() or h < 15:
            continue
        i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60), None)
        if i is not None:
            prices[i] = int(t)
    return prices


def to_sell(gifts, wanted, cost, reserve):
    """Indexes of the non-main gifts to sell so the wanted gift's price fits, highest index first.

    gifts are [(index on the sell page, sell price)] of the non-main gifts. Only the ones fusion
    cannot use go: what is left over after groups of 3. The dearest go first, fewest sales.
    None when even all of those would not cover the price: then nothing is sold.
    """
    spare = sorted(gifts, key=lambda g: -g[1])[:len(gifts) % 3]
    picked = []
    for i, price in spare:
        if can_spend(cost, wanted, reserve):
            break
        picked.append(i)
        cost += price
    if not can_spend(cost, wanted, reserve):
        return None
    return sorted(picked, reverse=True)  # selling from the back keeps the earlier cells in place


def gift_role(keyword, gift, main):
    """"keep", "material" or "unknown" for an owned gift read off its grid cell, on the fuse and the sell page.

    keyword: its badge's keyword, "Keywordless" with no badge, None when the badge is cut off or unread;
    gift: the team's observed gift its icon matched, or None. Kept: the main keyword, every keywordless gift
    and the observed gifts (#103, #112). Unknown is left to the tooltip.
    """
    if gift or keyword in (main, "Keywordless"):
        return "keep"
    return "unknown" if keyword is None else "material"


def protected(name, names, min_ratio=0.85):
    """Whether an OCR'd gift name is one of names (fuzzy): a gift the shop must not fuse or sell (#103)."""
    key = _norm(name)
    return bool(key) and any(SequenceMatcher(None, key, _norm(n)).ratio() >= min_ratio for n in names)


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())
