"""Shop decisions, free of MaaFramework (docs/spec/03-decisions.md section 13).

actions.py reads the shop pages and taps; everything here is plain data in, plain data out.
"""

from difflib import SequenceMatcher

ROUNDS = 10


LOOKALIKE = str.maketrans("OoDQIl|SsBZz", "000011155822")


def cost_value(text):
    """The Cost an OCR read stands for, look-alike letters taken as digits (33O2 -> 3302); None without a digit (#82)."""
    if not any(c.isdigit() for c in text):
        return None
    return int("".join(c for c in text.translate(LOOKALIKE) if c.isdigit()))


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
    name, price = slot["name"], slot["price"]
    if price is None or slot["purchased"] or slot.get("short") or "Replace" in name or "ID Skill" in name:
        return False
    return cost is None or price <= cost


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


def protected(name, names, min_ratio=0.85):
    """Whether an OCR'd gift name is one of names (fuzzy): a gift the shop must not fuse or sell (#103)."""
    key = _norm(name)
    return bool(key) and any(SequenceMatcher(None, key, _norm(n)).ratio() >= min_ratio for n in names)


def _norm(s):
    return "".join(c for c in s.lower() if c.isalnum())
