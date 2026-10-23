"""Shop decisions, free of MaaFramework (docs/spec/03-decisions.md section 13).

actions.py reads the shop pages and taps; everything here is plain data in, plain data out.
"""

from itertools import combinations

import numpy as np

from gift_search import _runs
from ocrtext import has

ROUNDS = 10
CELL_HALF = 48  # screen px kept around a cell's centre: its icon, tier numerals and keyword badge
TIERS = {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}  # numeral strokes at its top and bottom row: I-V


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


def filled(image, x, y):
    """Whether the grid cell centred at (x, y) holds a gift: textured (live: spread 41-84), an empty one flat (1-2)."""
    return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)


def yellow(box):
    """The numerals' yellow pixels of box (BGR)."""
    b, g, r = (box[:, :, i].astype(int) for i in range(3))
    return (r > 200) & (g > 140) & (b < 90)


def numeral(mask, top, bottom):
    """A tier (1-5) from a yellow mask's rows top and bottom, or None: the bars at each row (an unseen reading is no tier).

    I, II and III are 1-3 bars top to bottom; IV and V end in a V, so the bottom row has a stroke fewer.
    """
    bars = [(x, n) for x, n in _runs(np.flatnonzero(mask[top])) if n >= 2]
    if not bars:
        return None
    lo, hi = bars[0][0] - 1, bars[-1][0] + bars[-1][1] + 1  # icon art beside the numerals stays out
    ends = [n for _, n in _runs(np.flatnonzero(mask[bottom, lo:hi])) if n >= 2]
    return TIERS.get((len(bars), len(ends)))


def tier(cell):
    """A cell's tier (1-5) from its yellow numerals top left (cell_crop), or None (no numerals: a skill, a dim page)."""
    mid = cell.shape[0] // 2
    return numeral(yellow(cell[mid - 36:mid - 8, mid - 36:mid - 16]), 9, 19)  # rows inside every numeral on both scales


FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fuse page, centred at x 315


def forecast_tier(image):
    """The tier (1-4) the fuse page's Forecasts row predicts, or None (no numeral: no material in, or the row is covered).

    The row's numeral is the cells' (numeral), 19 px tall, its top and bottom rows found from its own yellow. Live
    2026-10-23: I, II and IV on a shop's and a Super Shop's page, IV on a fixed recipe's (tests/shop, ShopFuseRecipe).
    """
    x, y, w, h = FORECAST_NUMERAL
    mask = yellow(image[y:y + h, x:x + w])
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) < 8:
        return None
    t = numeral(mask, rows[0] + 2, rows[-1] - 3)
    return t if t and t <= FUSION_TOP_TIER else None  # a fusion gives a V never


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


def has_letters(t):
    """Whether OCR text t has an ASCII letter: a name or a tag, not a price, a numeral or a glyph."""
    return any(c.isascii() and c.isalpha() for c in t)


def read_slots(results):
    """Shop slots from the OCR results [(text, (x, y, w, h))] of the offer grid, top row first.

    Each is {"name", "price", "purchased", "x", "y"}, x and y the price line's centre. A price is the
    tall line with no letters (a "??" price is None); the name is the line just under it; a bought
    slot has "Purchased" over its icon. Lines are found relative to each other, not at fixed rows.
    A stray glyph of an icon (a badge read as "3") is as tall as a price, but the line under it is the
    real price, not a name (#216): it is no slot.
    """
    lines = [(t, x + w // 2, y + h // 2, h) for t, (x, y, w, h) in results]
    slots = []
    for t, x, y, h in sorted(lines, key=lambda line: (line[2] // 40, line[1])):
        if h < 18 or has_letters(t):
            continue  # tier numerals on the icons read as short lines
        near = [(u, uy) for u, ux, uy, _ in lines if abs(ux - x) < 75 and u != t]
        name = next((u for u, uy in near if 10 < uy - y < 40), "")
        if name and not has_letters(name):
            continue
        digits = "".join(c for c in t if c.isdigit())
        slots.append({
            "name": name,
            "price": int(digits) if digits and "?" not in t else None,
            "purchased": any(has(u, "Purchased") for u, uy in near if -110 < uy - y < 0),
            "short": any(has(u, "Enough") for u, uy in near if -110 < uy - y < 0),  # red "Not Enough Cost"
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
    return slot["price"] is not None and not slot["purchased"] and not has(name, "Replace", "ID Skill")


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


def to_sell(spare, wanted, cost, reserve, first=()):
    """Indexes of the spare gifts to sell so the wanted gift's price fits, highest index first.

    spare: [(index on the sell page, sell price)] of the gifts fusion cannot use (#79: what pick_fusion leaves over,
    and the gifts the team avoids). The indexes in first (the avoided ones, #90) go first, then the dearest, fewest
    sales. None when even all of those would not cover the price: then nothing is sold.
    """
    picked = []
    for i, price in sorted(spare, key=lambda g: (g[0] not in first, -g[1])):
        if can_spend(cost, wanted, reserve):
            break
        picked.append(i)
        cost += price
    if not can_spend(cost, wanted, reserve):
        return None
    return sorted(picked, reverse=True)  # selling from the back keeps the earlier cells in place


def gift_role(keyword, gift, kept, avoid=(), material=()):
    """"keep", "material" or "unknown" for an owned gift read off its grid cell, on the fuse and the sell page.

    keyword: its badge's keyword, "Keywordless" with no badge, None when the badge is cut off or unread;
    gift: the gift its icon matched (an observed, a kept, an avoided one or a vestige), or None; kept: the keywords
    the team keeps (kept_keywords: the main one, the ones it names and "Keywordless" unless it lets them go, #77).
    Kept too: the gifts whose icon matched (observed #103, #112, or named in keep_gifts #77); a gift in avoid (#90) or
    material (the vestiges the team lets go, #161) is material whatever its keyword. No badge and no icon matched is a
    keywordless gift (the user, #161). Unknown, a cut-off or unread badge, is neither fused nor sold.
    """
    if gift in avoid or gift in material:
        return "material"
    if gift or keyword in kept:
        return "keep"
    return "unknown" if keyword is None else "material"


SHOP_TITLE = (190, 108, 130, 30)  # x, y, w, h: the title on the main page's plate, top left


def is_super(image):
    """Whether the main shop page is a Super Shop: its title is red, a shop's is tan (#263).

    Red pixels in the title's box: 20% on SuperShop.png, 0 on Shop.png (tests/screens): one sample of each, so a Super
    Shop on another theme's background is unverified. Only a shop's main page is asked.
    """
    x, y, w, h = SHOP_TITLE
    b, g, r = (image[y:y + h, x:x + w, i].astype(int) for i in range(3))
    return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)


FUSION_TOP_TIER = 4  # a fusion gives tier IV at most
MAX_MATERIAL_TIER = FUSION_TOP_TIER  # so a tier V material is always a downgrade (user, #161)
MIN_FUSION = 3  # materials a fusion takes at least: the game takes 2, spec 03 section 13 (#10) groups of 3 and up


def fusion_tier(points, thresholds):
    """The tier a fusion gives for its materials' points (#77): thresholds are the most points of tiers 1-3."""
    return 1 + sum(points > t for t in thresholds)


def fusion_wanted(condition, tier, materials):
    """Whether a fusion giving tier is made (#263): any one is; upgrade, only over the highest of its materials' tiers
    (materials: [(key, tier)]); tier4, only a tier IV (FUSION_TOP_TIER)."""
    if condition == "upgrade":
        return tier > max(t for _, t in materials)
    return condition != "tier4" or tier >= FUSION_TOP_TIER


def pick_fusion(materials, slots, thresholds, points, first=(), condition="any", refused=()):
    """The fusions to make, best first: [([keys], the tier it gives)] (#77).

    materials: [(key, tier)]; slots: the page's material slots (3, a Super Shop's 5); thresholds: fusion_tier's for
    this shop; points: {tier: a material's points}. Each fusion takes 3 to slots materials: the group giving the
    highest tier, then holding the most of first (gifts the team avoids, #90), then worth the fewest points; then
    again from what is left, until fewer than 3 are. A tier V gift is never a material (MAX_MATERIAL_TIER).
    condition (the team's fusion_condition, #263) keeps out the groups fusion_wanted refuses: the best of the rest is
    made, and none when no group is left. "any" puts the groups that upgrade (user, 2026-10-23) ahead of that order.
    refused: [frozenset of keys] the groups the page's own forecast turned down (#285): never picked again.
    """
    def total(group):
        return sum(points[t] for _, t in group)

    def tier_of(group):
        return fusion_tier(total(group), thresholds)

    def rank(group):
        no_upgrade = condition == "any" and not fusion_wanted("upgrade", tier_of(group), group)
        return no_upgrade, -tier_of(group), -sum(k in first for k, _ in group), total(group), len(group)

    left, out = [m for m in materials if m[1] <= MAX_MATERIAL_TIER], []
    while len(left) >= MIN_FUSION:
        groups = [g for n in range(MIN_FUSION, slots + 1) for g in combinations(left, n)
                  if frozenset(k for k, _ in g) not in refused and fusion_wanted(condition, tier_of(g), g)]
        if not groups:
            break
        best = min(groups, key=rank)
        out.append(([k for k, _ in best], tier_of(best)))
        left = [m for m in left if m not in best]
    return out


# The fuse page's material slots by their centre (live 2026-10-16/18): a shop's 3 round its centre, a Super Shop's 5.
FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 262), (235, 367), (495, 367)]}


def fuse_slots(image):
    """3 or 5: a fuse page's material slots, read before a material is in (#77).

    Told by the Super Shop's top-left slot: an empty slot is black (live: brightness 1), where a shop's page shows
    the gears behind (40).
    """
    return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3


def placed(image, slots):
    """How many of the fuse page's slots hold a material: textured (spread 29-85 live), not an empty slot's flat black (0-1)."""
    return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUSE_SLOTS[slots])


def picked(image, x, y, bottom=720):
    """Whether the owned gift whose cell is centred at (x, y) is in the fusion: its frame turns orange (#77).

    The ring 34-40 px out from the centre, above bottom (the grid's lower edge cuts the third row): 17-23% orange
    pixels on a picked cell (11% under a tooltip's shade), 0-2% on the others (live 2026-10-16/18; rows 1-2 only).
    The cell does not move: the grid is not sorted again.
    """
    image = image[:bottom]
    ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y + 40, x - 30:x + 30].reshape(-1, 3),
                           image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].reshape(-1, 3)])
    b, g, r = (ring[:, i].astype(int) for i in range(3))
    return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08
