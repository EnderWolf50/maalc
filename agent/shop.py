"""Shop decisions, free of MaaFramework (docs/spec/03-decisions.md section 13).

actions.py reads the shop pages and taps; everything here is plain data in, plain data out.
"""

import re
from difflib import SequenceMatcher
from itertools import combinations

import numpy as np

from battle import SINNERS
from gift_search import _runs
from ocrtext import compact, has
from settings import vestige_ids

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


UNSELECTABLE_BAND = (44, 29, 44)  # px over a cell's centre the fuse page's "Unselectable" tag spans (from, to), px either side
UNSELECTABLE_MIN, UNSELECTABLE_SPAN, UNSELECTABLE_RUN = 300, 70, 20  # its letters' px, the columns they span, their longest run


def unselectable(image, x, y):
    """Whether the fuse page's cell centred at (x, y) carries the "Unselectable" tag over its top edge (#378).

    The game's combine_egogift_not_allow: a gift no fusion takes, drawn dim, its centre as flat as an empty cell's (spread
    9.6-9.9, under filled's 15). Live 2026-11-04: A Certain Philosophy (9799, EX), the gift a 99% fusion gives when it fails.
    The tag's dark red letters (live R 101-160, G and B 23 at most) are 439-502 px of the band, span 84 px, and run 7-11 px
    on a row (11 tagged cells, 7 distinct, of 90 fuse pages: the 2026-11-04 recordings' frames and tests/shop's crops); a
    tooltip's red head runs 288 px (tooltip). The other 1339 cells of those pages: 220 px at most. test_shop sweeps
    tests/screens.
    """
    over, under, side = UNSELECTABLE_BAND
    band = image[y - over:y - under, x - side:x + side].astype(int)
    b, g, r = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)
    cols = np.flatnonzero(letters.any(axis=0))
    if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:
        return False
    return max(n for row in letters for _, n in _runs(np.flatnonzero(row))) <= UNSELECTABLE_RUN


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


def numeral_place(cell):
    """The box of a cell (cell_crop) its tier numerals sit in, top left: rows inside every numeral on both scales."""
    mid = cell.shape[0] // 2
    return cell[mid - 36:mid - 8, mid - 36:mid - 16]


def tier(cell):
    """A cell's tier (1-5) from its yellow numerals top left (cell_crop), or None (no numerals: a skill, a dim page, EX)."""
    return numeral(yellow(numeral_place(cell)), 9, 19)


def green(box):
    """The green pixels of box (BGR) an EX gift's "EX" mark is drawn in, where other gifts show yellow numerals (#449).

    G over R by a fifth and over twice B. Live 2026-11-04, A Certain Philosophy (9799): on the GET! popup G up to 255, R up
    to 211, B up to 75 (its top edge turns yellow and fails); dimmed on the fuse page's Unselectable cell G 41-56, R 24-42,
    B 15 at most. A yellow numeral has more R than G.
    """
    b, g, r = (box[:, :, i].astype(int) for i in range(3))
    return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)


# Green px in a cell's numeral place (numeral_place) that make its "EX". Live 2026-11-04: the dimmed EX 39-52 (14 frames);
# the 15 other cells with no numeral read on the 50 archived 1280x720 frames with 5 numerals read on a grid, 1 at most.
EX_CELL_PX = 30


def ex_mark(cell):
    """Whether a cell (cell_crop) shows the green "EX" an EX gift has where the numerals go (#449)."""
    return int(green(numeral_place(cell)).sum()) >= EX_CELL_PX


GET_MARK = (338, 228, 50, 50)  # x, y, w, h: the GET! popup's icon corner, its gift's tier numeral or "EX" (#449)
# Green px there that make the "EX". Live: the EX's popup 966-974 (its 9 frames at 30 fps, 2026-11-04); the 1006 other
# popups of 34 archived 1280x720 recordings (2026-10-18 to 11-05, 10 fps) 39 at most (a green icon's art at the corner).
EX_GET_PX = 500


def ex_got(image):
    """Whether the E.G.O Gift GET! popup shows an EX gift: the green "EX" at its icon's top left, not a yellow numeral (#449)."""
    x, y, w, h = GET_MARK
    return int(green(image[y:y + h, x:x + w]).sum()) >= EX_GET_PX


FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fuse page, centred at x 315


def forecast_tier(image):
    """The tier (1-4) the fuse page's Forecasts row predicts, or None (no numeral: no material in, or the row is covered).

    The row's numeral is the cells' (numeral), 19 px tall, its top and bottom rows found from its own yellow. Live
    2026-10-23: I, II and IV on a shop's and a Super Shop's page, IV and III on a fixed recipe's (tests/shop, tests/screens ShopFuseRecipe, ShopFuseRecipeTwo).
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


# Skill replacement (#455, docs/spec/03-decisions.md section 13 「換技能」). A swap is a key of data/shop.yaml's
# skill_replacement ({"s1_s3": {"from": 1, "to": 3, "shop": 120, ...}, ...}): the functions take that table as `swaps`, as
# heal_plan takes heal_cost. Counts are (c1, c2, c3), the cards of skill 1, 2 and 3 in a sinner's deck: 6, or 5 with skill 3
# at 0 under Uptie 3 (#264). A team's entry is {"sinner", "target": {"s1", "s2", "s3"}, "s1_s3_first"}; the settings'
# cross-checks keep a target at a total of 6, S1 <= 3 and S3 >= 1, so it is trusted here.
DECK = {"s1": 3, "s2": 2, "s3": 1}  # the game's deck: a target equal to it asks for nothing (#264)


def counts_line(counts):
    """"3/2/1" for counts as a tuple or a target dict, for the log."""
    return "/".join(str(n) for n in ((counts["s1"], counts["s2"], counts["s3"]) if isinstance(counts, dict) else counts))


def any_change(listed):
    """Whether any listed sinner's target is off the game's 3/2/1: with none, the shop reads and taps nothing for skills
    (#264 User Story 3)."""
    return any(e["target"] != DECK for e in listed)


def sinner_named(text):
    """The sinner (battle.SINNERS) an OCR line names, or None when it names none or two: never a guess (#264).

    has() drops case, accents and spaces, so "REPLACE RYOSHU'S SKILL" and "ReplaceRyōshū'sSkill" name Ryōshū; no name is a
    part of another, and the title's other words hold none.
    """
    found = [n for n in SINNERS if has(text, n)]
    return found[0] if len(found) == 1 else None


# OCR clips the tail of a 130 px name: "Replace Meursault's Skil" and "Replace Gregor's Skil" (2026-11-06 run), so the stem
# is "Skil", not "Skill". The same clip hits "ID Skil Search"; the buy side and the Replace check both go through these.
SKILL_STEM = "Skil"


def id_skill_slot(name):
    """Whether a slot name is ID Skill Search (#456), clipped or whole."""
    return has(name, "ID " + SKILL_STEM)


def replace_slot(name):
    """Whether a slot name is a Replace <sinner>'s Skill slot: Replace and the Skill stem, and not ID Skill Search."""
    return has(name, "Replace") and has(name, SKILL_STEM) and not id_skill_slot(name)


def skill_slots(slots):
    """The Replace <sinner>'s Skill slots of a grid read (read_slots), each a copy with its "sinner" (or None).

    A name replace_slot() accepts (#264; the stem survives a clipped tail); bought ones stay, tagged purchased, so the plan logs them.
    ID Skill Search is #456's slot, not one of these. One slot read twice is one: SuperShop.png's "??" reads as a coin
    glyph and "7?", two price lines under one name (same_offer: the same column, price and name).
    """
    found = []
    for slot in slots:
        name = slot["name"]
        if replace_slot(name) and not any(same_offer(slot, s) for s in found):
            found.append({**slot, "sinner": sinner_named(name)})
    return found


def skills_owned(text):
    """(c1, c2, c3) from the dialog's "SKILL 1x3 SKILL 2x2 SKILL 3x1" line, or None unless all three read and they total 5
    or 6 (#264: anything else cancels). Matched compacted: OCR drops spaces, and a "×" drops out."""
    m = re.search(r"skill1x?(\d)skill2x?(\d)skill3x?(\d)", compact(text))
    if m is None:
        return None
    owned = tuple(int(d) for d in m.groups())
    return owned if sum(owned) in (5, 6) else None


def locked(owned):
    """Whether the sinner's skill 3 is locked (under Uptie 3): 5 cards, none of skill 3 (#264; Gregor, #453)."""
    return sum(owned) == 5 and owned[2] == 0


def swaps_wanted(target, owned, s1_s3_first, swaps):
    """The swaps that move owned toward target, in the order to try; [] at the target or when none helps (#264 換法的決策).

    A swap a_b counts when skill a is over its target and skill b under it, so it never overshoots. A locked skill 3 takes
    none (the game dims those options). At most two kinds count at once (s1_s2 needs c2 under its target, s2_s3 over it);
    s1_s3_first puts s1_s3 before the other or after it.
    """
    wanted = [k for k, sw in swaps.items()
              if owned[sw["from"] - 1] > target[f"s{sw['from']}"] and owned[sw["to"] - 1] < target[f"s{sw['to']}"]
              and not (sw["to"] == 3 and locked(owned))]
    return sorted(wanted, key=lambda k: (k != "s1_s3") if s1_s3_first else (k == "s1_s3"))


def after_swap(owned, swap, swaps):
    """The counts after one swap: a card of `from` fewer, one of `to` more."""
    sw = swaps[swap]
    return tuple(n - (i == sw["from"] - 1) + (i == sw["to"] - 1) for i, n in enumerate(owned))


def skill_choice(entry, owned, lit, prices, cost, reserve, swaps):
    """(swap, price) to buy in the dialog, or None: the first wanted swap whose price read, which is lit and whose price
    keeps the reserve (#264: closer to the target, priced, affordable, the game lets it be picked).

    owned, lit ({swap: bool}), prices ({swap: int or None}) and cost (None when unread: then nothing, #455) are what the
    dialog shows: the screen's price is the price, the data file's is not asked.
    """
    if cost is None:
        return None
    for k in swaps_wanted(entry["target"], owned, entry["s1_s3_first"], swaps):
        if prices.get(k) is not None and lit.get(k) and can_spend(cost, prices[k], reserve):
            return k, prices[k]
    return None


def skill_plan(listed, slots, known, handled, swaps):
    """[(slot, entry or None, why)] for every replacement slot of a grid read: the ones to open (entry set) first, in the
    list's order (#264: with Cost for one, the earlier sinner), then the skipped in the grid's order. `why` is the slot's
    log line (#264 log).

    listed: the team's skill_replacement.sinners; known: {sinner: counts} read this run; handled: the sinners tapped this
    visit. A sinner whose counts are unknown is opened: the dialog is where they show. Keyed by sinner: a second slot of
    one (never seen) waits for the next visit.
    """
    rank = {e["sinner"]: (n, e) for n, e in enumerate(listed)}
    opened, out = set(), []
    for at, slot in enumerate(skill_slots(slots)):
        sinner = slot["sinner"]
        n, entry = rank.get(sinner, (None, None))
        why, opens = None, False
        if slot["purchased"]:
            why = "replaced already (Purchased): skip"
        elif sinner is None:
            why = "the sinner's name is unread: skip"
        elif entry is None:
            why = f"{sinner!r} is not listed: skip"
        elif entry["target"] == DECK:
            why = f"{sinner!r} targets the game's 3/2/1: skip"
        elif sinner in handled:
            why = f"{sinner!r} handled this visit: skip"
        elif sinner in opened:
            why = f"{sinner!r} has another slot opened this visit: skip"
        else:
            why, opens = by_counts(entry, known, swaps, "open")
        if opens:
            opened.add(sinner)
        out.append(((0, n) if opens else (1, at), slot, entry if opens else None, why))
    return [(slot, entry, why) for _, slot, entry, why in sorted(out, key=lambda o: o[0])]


def by_counts(entry, known, swaps, verb):
    """(why, whether to go on) for a listed sinner by the counts read this run (known): at the target or with no swap left
    is a skip; unknown counts or a swap wanted go on (`verb` ends the line): the dialog is where the counts show."""
    sinner, target = entry["sinner"], entry["target"]
    if sinner not in known:
        return f"{sinner!r} counts not read this run, toward {counts_line(target)}: {verb}", True
    owned = known[sinner]
    if tuple(owned) == (target["s1"], target["s2"], target["s3"]):
        return f"{sinner!r} is at {counts_line(owned)} (read this run): skip", False
    if not swaps_wanted(target, owned, entry["s1_s3_first"], swaps):
        return (f"{sinner!r} at {counts_line(owned)} can make no swap toward {counts_line(target)}"
                f"{' (skill 3 locked)' if locked(owned) else ''}: skip"), False
    return f"{sinner!r} {counts_line(owned)} read this run, toward {counts_line(target)}: {verb}", True


def id_search_slot(slots):
    """The ID Skill Search slot of a grid read (read_slots), whole or clipped, or None (#456)."""
    return next((slot for slot in slots if id_skill_slot(slot["name"])), None)


def id_search_plan(listed, known, tried, dead, swaps):
    """[(entry or None, why)] for every listed sinner, in the list's order: the sinners ID Skill Search tries (entry set),
    each judged on its dialog, and the skipped (#456; #264: the first listed sinner with a feasible swap).

    A sinner is skipped at the game's 3/2/1, when tried this visit (`tried`, each at most once), dead (`dead`: grey on the
    shop's bar, a portrait that takes no tap), or when its counts read this run are at the target or allow no swap.
    """
    out = []
    for entry in listed:
        sinner = entry["sinner"]
        if entry["target"] == DECK:
            why, tries = f"{sinner!r} targets the game's 3/2/1: skip", False
        elif sinner in tried:
            why, tries = f"{sinner!r} tried this visit: skip", False
        elif sinner in dead:
            why, tries = f"{sinner!r} is dead (grey on the shop's bar): skip", False
        else:
            why, tries = by_counts(entry, known, swaps, "try")
        out.append((entry if tries else None, why))
    return out


def pay_mode(prices, swaps):
    """"cost" or "starlight": the ID Skill Search dialog's payment, told by its prices (#456: 90/150/240 for Cost, 25/50/75
    for starlight), or None. Every price that read must be that mode's, and one at least: a mix or none is never a guess."""
    read = {k: p for k, p in prices.items() if p is not None}
    modes = [m for m in ("cost", "starlight") if read and all(swaps[k]["id_search"][m] == p for k, p in read.items())]
    return modes[0] if len(modes) == 1 else None


def id_search_choice(entry, owned, lit, prices, funds, pay, reserve, swaps):
    """skill_choice for ID Skill Search (#456): funds is what the dialog's top right shows, the Cost or the owned starlight.
    Cost keeps the team's reserve; starlight is not under it, and too little of it is no swap (#264 價格)."""
    return skill_choice(entry, owned, lit, prices, funds, reserve if pay == "cost" else 0, swaps)


# Pixel readers of the dialog (#453), image BGR. Measured on tests/screens/ShopReplaceSkill*.png; test_shop_skill sweeps
# every tests/screens capture.
# A price box's bright px (max channel over 100), their median: lit orange RGB 191-196, 88-95, 14-17 (11 boxes), dimmed red
# 152-156, 30-51, 1-6 (4 boxes). Orange: G at least PRICE_LIT_G, R over G by PRICE_LIT_RG, B under PRICE_LIT_B (white text fails).
PRICE_LIT_G, PRICE_LIT_RG, PRICE_LIT_B = 70, 60, 60
PICKED_BAND, PICKED_MIN = 8, 0.2  # px just inside an option's frame; orange share 0.452-0.457 picked, 0.002 at most on 15 others


def option_lit(image, box):
    """Whether the option whose price sits in box (x, y, w, h) can be picked: its price orange, a dimmed one's red (#453:
    Gregor's 75 and 120 under Uptie 3). A box with no bright pixel is not lit."""
    x, y, w, h = box
    px = image[y:y + h, x:x + w].reshape(-1, 3)
    px = px[px.max(axis=1) > 100]
    if not len(px):
        return False
    b, g, r = np.median(px, axis=0)
    return bool(g >= PRICE_LIT_G and r - g >= PRICE_LIT_RG and b < PRICE_LIT_B)


def option_picked(image, frame):
    """Whether the option framed by frame (x, y, w, h) is picked: its orange glow (R over 120 and G + 40, G 31-139, B under
    60) fills PICKED_MIN of the PICKED_BAND px just inside the frame (#453: a 1-px 242/184/0 line on the edge, a halo
    about 178/78/6 inside it)."""
    x, y, w, h = frame
    d = PICKED_BAND
    band = np.concatenate([image[y:y + d, x:x + w].reshape(-1, 3), image[y + h - d:y + h, x:x + w].reshape(-1, 3),
                           image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].reshape(-1, 3)])
    b, g, r = (band[:, i].astype(int) for i in range(3))
    return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_MIN)


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
        if (h < 18 and sum(c.isdigit() for c in t) < 3) or has_letters(t):
            continue  # tier numerals on the icons read as short lines; a price read 17 px tall (Burning Intellect's 141, #341) has 3 digits
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


def same_offer(a, b):
    """Whether two reads of the offer grid are one offer: the same column and price, and a name that differs by a misread letter at most."""
    return (abs(a["x"] - b["x"]) < 30 and a["price"] == b["price"]
            and SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio() >= 0.8)


def on_sale(slot):
    """Whether a shop slot is a gift on sale for Cost, affordable or not: not bought, not a skill, not "??"."""
    name = slot["name"]
    return slot["price"] is not None and not slot["purchased"] and not has(name, "Replace") and not id_skill_slot(name)  # wider than replace_slot on purpose: any Replace name is no gift


def buy_plan(offers, cost, reserve, sold):
    """(grid indexes to buy, last first; the wanted price or None) for the offers on show the gift list wants (#298).

    offers: [(grid index, place in the buy queue, price)]. The queue's order, cheapest first for one gift on show twice,
    each only while the reserve stays. When the first choice is too dear and no sale has been tried for it, nothing is
    bought: wanted asks the next round to sell first. Bought from the back, a purchase (moved to the grid's
    end) leaves the offers before it in place, so the grid is read once.
    """
    order = sorted(offers, key=lambda o: o[1:])
    if order and not sold and not can_spend(cost, order[0][2], reserve):
        return [], order[0][2]
    picked = []
    for i, _, price in order:
        if can_spend(cost, price, reserve):
            picked.append(i)
            cost -= price
    return sorted(picked, reverse=True), None


def refresh_choice(cost, reserve, used, limits, normal_fee, keyword_fee, margin):
    """"keyword", "normal" or None: the refresh to use now (spec 03 section 13).

    Keyword refresh first, then normal; either one only while it leaves margin plus the reserve to buy with, and only as
    many times per shop as its own count in `limits` allows ({"keyword": n, "normal": n}, the team's; `used` counts alike).
    """
    for kind, fee in (("keyword", keyword_fee), ("normal", normal_fee)):
        if used[kind] < limits[kind] and fee is not None and can_spend(cost, fee + margin, reserve):
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
    condition (the gift list's fusion_condition, #263) keeps out the groups fusion_wanted refuses: the best of the rest is
    made, and none when no group is left. "any" puts the groups that upgrade (user, 2026-10-23) ahead of that order.
    refused: [tuple of sorted tiers] the groups the page's own forecast turned down (#285): the result depends on the
    materials' tiers only, so no group of those tiers is picked again.
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
                  if tuple(sorted(t for _, t in g)) not in refused and fusion_wanted(condition, tier_of(g), g)]
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


def fusion_places(cells, gone, tier, geometry):
    """The fuse page's owned grid after a fusion, in the order the page keeps (#378): (the cells left and the gift made,
    each a copy with its new place "i" and centre "x", "y" with the grid at its top, the gift made's place), or None when
    the cells do not tell it.

    cells: the grid as read (each {"i", "tier", "id", ...}, i its place); gone: the places of the materials; tier: the gift
    made's; geometry: ((x0, y0), (dx, dy)), the first cell's centre and the step to the next column and row, 5 a row.
    The list goes by tier, highest first, with the vestiges ahead of the rest whatever their tier (in_tier_order); the
    materials go out, the rest keep their order, and the gift made goes after the vestiges and last of its tier's run,
    between the higher and the lower tiers when none of its tier is left (live: 29 of the 30 fusions read again in 57 logs of
    2026-10-20 to 11-04, 5 of them with a vestige on the page; the 30th failed and gave an EX gift, tier V where the page
    forecast IV: its GET! popup's "EX" makes tier V, #449, placed ahead of the IVs by the data's tier, unseen). It is
    {"i", "x", "y", "tier", "keyword": None, "id": None}:
    what it is shows only on screen. None: a place not read (the places are not 0 to n-1), a tier unread or out of that
    order, or a material not among them.
    """
    (x0, y0), (dx, dy) = geometry
    cells = sorted(cells, key=lambda c: c["i"])
    if [c["i"] for c in cells] != list(range(len(cells))) or not set(gone) <= {c["i"] for c in cells}:
        return None
    if tier is None or any(c["tier"] is None for c in cells) or not in_tier_order(cells):
        return None
    left = [c for c in cells if c["i"] not in set(gone)]
    k = sum(c["id"] in vestige_ids() or c["tier"] >= tier for c in left)
    order = left[:k] + [{"tier": tier, "keyword": None, "id": None}] + left[k:]
    return [{**c, "i": n, "x": x0 + dx * (n % 5), "y": y0 + dy * (n // 5)} for n, c in enumerate(order)], k


def in_tier_order(cells):
    """Whether cells (in their places' order, every tier read) keep the fuse page's By Tier order (#378): the vestiges first,
    highest tier first among them, then the rest highest tier first.

    The client's sort is SortByTierPieceFirst (a method name in its IL2CPP metadata); its "piece" gifts are the vestiges
    (pieceEgoGiftIds 9991-9995 of the md8 common data). Live: 86 of 86 reads of whole lists in 57 logs of 2026-10-20 to
    11-04 keep it (an EX gift counted where the recordings show it), 13 of them with a vestige (12 of those out of order by
    tier alone: a Dark Vestige ahead of tier IV and III gifts), two with vestiges of two tiers (III ahead of I, II ahead of
    I). A Certain Philosophy (EX, tier V in the data) showed after a Twinkling Vestige (III) and ahead of the IIIs, with no
    IV owned: ahead of a IV is the data's tier, unseen. A gift whose id is unread counts as no vestige.
    """
    n = sum(c["id"] in vestige_ids() for c in cells)
    head, rest = cells[:n], cells[n:]
    return all(c["id"] in vestige_ids() for c in head) and all(a["tier"] >= b["tier"] for run in (head, rest)
                                                               for a, b in zip(run, run[1:]))


TOOLTIP_AREA = (600, 200, 680, 330)  # x, y, w, h: where a fuse page tooltip's head shows, under its tapped cell's centre
TOOLTIP_HEAD = 120  # px of unbroken red on one row: a tooltip's head 288-290 (189 cut), the fuse page without one 45 at most


def tooltip(image):
    """Whether a gift's tooltip shows over the fuse page (#331, #378): its "E.G.O GIFT" head, a dark red bar.

    One row of TOOLTIP_AREA holds TOOLTIP_HEAD red px in a row (red: R over 120 and over twice G and B, plus 40). The head
    starts by its tapped cell's centre and is 330 px wide, shifted left at the screen's edge. Live: the 15 tooltips of the
    2026-11-04 recording's four fuse-page visits (4654 frames, 113 with a tooltip) 288-290 px, no other frame 120;
    tests/shop/fuse_tooltip's head, cut at the crop's edge, 189. Without one: 45 at most on the 6 fuse pages of tests/screens
    and the 10 fuse and sell crops of tests/shop, a gift's red art ending at its cell's frame. test_shop sweeps tests/screens.
    """
    x, y, w, h = TOOLTIP_AREA
    b, g, r = (image[y:y + h, x:x + w, i].astype(int) for i in range(3))
    red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)
    runs = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)  # a row's red px up to each column
    return bool((runs[:, TOOLTIP_HEAD:] - runs[:, :-TOOLTIP_HEAD] == TOOLTIP_HEAD).any())


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
