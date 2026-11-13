"""The mirror's shop: reading its offer and owned gift grids, buying, selling, fusing, healing and replacing a skill."""

import re
import time

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import battle
import gift_cells
import rewards
import shop
from actions import (DIALOG_CANCEL, DIALOG_CONFIRM, DIALOG_TEXT, GET_CONFIRM, GET_TITLE, GIFTS, GIFT_IDS, GIFT_NAMES,
                     RUN, PageGone, avoided_gifts, current_run, data, hands_back, leave_shop, log, number, ocr, on_map,
                     owned_now, page_guard, run_packs, saturation, screen, scroll, seen, shows, still, stuck, tap,
                     tap_moved, tap_settled, tap_shown, tap_then, text, until)
from gifts import effective, purchases, recipe_fusion, state
from ocrtext import compact, digits, has, normalize
from settings import GIFT_KEYWORDS, gift_tables, vestige_ids


# Shop (spec 03 section 13). The Super Shop has the same layout with up to 10 offers.
SHOP_COST = [540, 112, 110, 45]
REFRESH = {"normal": ((997, 122), [960, 140, 80, 30]), "keyword": ((1140, 122), [1100, 140, 80, 30])}  # button, fee
OFFER_GRID = [545, 215, 620, 300]
DIALOG_TITLE = [360, 80, 560, 115]  # Purchase E.G.O Gifts, Shop - Keyword Refresh, Fuse / Sell E.G.O Gift
PURCHASE_PREVIEW = [780, 145, 140, 40]  # "2864 > 2612": the Cost before and after
PURCHASE, PURCHASE_CANCEL = (747, 482), (525, 482)
KEYWORD_LABELS = [270, 300, 740, 200]  # the 10 keyword cards of both keyword dialogs
KEYWORD_REFRESH, KEYWORD_CANCEL = (785, 560), (495, 560)
PAGE_CLOSE, PAGE_OK = (490, 585), (788, 585)  # Close, and Fuse / Sell, on the fuse and sell pages
SHOP_BUTTONS = {"fuse": (295, 390), "sell": (395, 390), "heal": (197, 474)}
FUSE_CENTRE, FUSE_KEYWORD_OK = (365, 340), (788, 566)
FUSE_DIALOG_CONFIRM = (788, 583)  # "Fuse the selected E.G.O Gifts?"'s Confirm
# Grid cells by their centre (live 2026-10-16/18). Each cell's tier numerals sit top left, its keyword badge
# bottom right (none on a keywordless gift). The owned grids' third row shows half, its badges cut off: they scroll (#205).
# page: (the first cell's centre with the grid at its top, the step to the next column and row, the px under a centre
# that must show for the cell to be read: its badge, on the sell page its price). Rows 92 and 107 px apart on captures;
# a sell price's digits 38-53 px under the centre, and a sell grid of 3 rows scrolls 31 px to show its last whole (live
# 2026-10-21, #205).
OWNED_GRID = {"fuse": ((678, 294), (96, 92), 40), "sell": ((683, 258), (92, 107), 52)}
FUSE_CELLS, SELL_CELLS = ([(x + dx * c, y + dy * r) for r in range(3) for c in range(5)]
                          for (x, y), (dx, dy), _ in OWNED_GRID.values())
OFFER_CELLS = [(624 + 154 * c, y) for y in (265, 418) for c in range(4)]  # a shop at rest; the price line is 52 px under
# A Super Shop's grid scrolls to show its third row (live 2026-10-15, SuperShop.png and its scrolled capture): by 150 px, the
# second row where the first was. A drag from between the first two columns, 250 px, goes to either end.
OFFER_DRAG_X, OFFER_DRAG_PX = 701, 250
OFFER_ABOVE, OFFER_UNDER = 90, 25  # px a price line has its icon's top over it and its name's foot under it: what must show in the grid's box


def offer_whole(y):
    """Whether the offer whose price line is at y shows whole in OFFER_GRID's box (#341)."""
    return OFFER_GRID[1] + OFFER_ABOVE <= y <= OFFER_GRID[1] + OFFER_GRID[3] - OFFER_UNDER
# The fuse page's list: sections over the owned gifts (a fixed recipe's Fusion Available, #103) push them down. Their
# "E.G.O Gifts Owned" label's centre sits 66 px over the first owned row's (live: 228 and 294).
FUSE_LIST, OWNED_LABEL = [630, 195, 480, 305], 66
GRID_DRAG_X = 728  # a drag of the owned grid starts between its first two columns
GRID_STROKE = 215  # px a drag stroke moves the owned grid at most: it starts and ends inside the grid
GRID_SCROLLS = 20  # drags at most to the owned grid's end: 2 rows each, fewer when the game takes less of one
GRID_MARGIN = 6  # px a drag stops short of putting a row at the first row's place: a few px too far does not hide it
GRID_SLIP = 12  # px a drag may move the grid past the finger, either way, and still be measured
# A cell's centre at its tap against its read (centre, matched): the same gift 0-3 px off, the grid moved by a fraction
# of a px (resampled to 720p), differs by 9.9 at most, two gifts by 15.2 at least (Faint and Dark Vestige's jars), 24.6
# for 95 in 100; tests/shop's 5 fuse and sell captures (test_shop_scroll).
GRID_SAME = 12.5
# page: (its icon size over the GiftSearch template's, the grid's lower edge on screen)
CELL_PAGES = {"fuse": (1.1, 493), "sell": (1.1, 495), "offer": (0.8, 530)}
BADGES = tuple(k for k in GIFT_KEYWORDS if k != "Keywordless")
# On scaled cells (CCOEFF): its own badge 0.54-0.99, another keyword's up to 0.60 (the cell's best wins), a keywordless
# cell's best 0.41; 160 cells of 60 live captures.
BADGE_MIN = 0.5
FUSION_IDS = {g["id"] for g in gift_tables()[1]}
GIFT_TIERS = {e["id"]: e["tier"] for e in GIFTS}
CELL_ICON_ROI = 70  # px square around a cell's centre on the scaled grid where its icon is looked for: the biggest icon (54 px) +-8
# An EX gift's tier in the game data (TIER_5 beside TIER_EX: 9799 A Certain Philosophy, 9800 Wealth); its cell shows "EX"
# where the numerals go, so a cell with no numeral read and that "EX" (#449) or the Unselectable tag (#378) is matched
# against that tier's gifts, and a fusion whose GET! popup shows it made that tier
EX_TIER = 5
FUSE_CONFIRM = [300, 150, 680, 380]  # "Selected E.G.O Gifts 3/5" over "Fuse the selected E.G.O Gifts?"
FUSE_COUNT = r"(\d)\s*/\s*\d"  # its "3/5": the materials in
FUSE_NEUTRAL = (815, 160)  # above the owned grid, between Recipes and Fusion Guide: closes a tooltip, selects nothing
FORECAST_CHANCE = [428, 455, 62, 28]  # "90%" at the Forecasts row's right: the keyword's chance (60 / 90 / 99, 100 on a recipe)
FUSE_TRIES = 3  # groups the fuse page's forecast may turn down between two fusions before the page is closed (#285)
FUSIONS_PER_PAGE = 10  # fusions one fuse page makes before it is closed (#378): Shop.run's next round opens it again
TOOLTIP_CLOSE = {"fuse": FUSE_NEUTRAL}  # per page: where a tap closes a gift's tooltip, which hides the cells under it (#331)
SELL_COST = [960, 80, 160, 45]
SELL_GRID = [630, 210, 480, 290]  # the sell page's gifts with their prices under them
HEAL_TITLE, HEAL_COST = [130, 30, 220, 45], [1100, 90, 110, 50]
HEAL_OPTIONS = {"full": (1020, 330), "revive": (1020, 455)}
SHOP_PORTRAIT_X = [98 + 77 * i for i in range(12)]  # the shop's sinner bar (step 77, not the event bar's)
BOTTOM_RIGHT = (1130, 647)  # Leave on the shop; Return, Select or Leave on the heal pages
BOTTOM_LABEL = [1040, 615, 180, 65]  # its label (the Shop node's ShopLeave roi)
OUTSIDE = (40, 400)  # left of every shop dialog, on nothing
LEAVE_DIALOG, LEAVE_CONFIRM, LEAVE_CANCEL = [440, 320, 400, 45], (765, 493), (515, 493)
# The Replace <sinner>'s Skill dialog (#455; spec 02 「技能替換對話框」), measured on tests/screens/ShopReplaceSkill*.png. Both
# layers (the three options, then "Spend N Cost to replace this Skill?") keep the counts, Cancel and Confirm in place.
REPLACE_TITLE = [200, 118, 380, 40]  # "Replace Don Quixote's Skill" x 213-568, "Replace Gregor's Skill" 247-534, y 124-151
REPLACE_OWNED = [600, 102, 250, 52]  # "Skills Owned" over "SKILL 1x3 SKILL 2x2 SKILL 3x1" (x 617-833, y 134-149)
REPLACE_COST = [1012, 118, 100, 42]  # the Cost, digits from x 1020 (the coin ends at 1011, Keyword Refresh's dim label from 1129)
REPLACE_PREVIEW = [980, 115, 130, 45]  # 2nd layer: "350 ▸ 305", the Cost before and after (x 985-1098)
REPLACE_PRICES = {"s1_s2": [408, 206, 51, 20], "s2_s3": [734, 206, 52, 20], "s1_s3": [1059, 206, 52, 20]}  # 45, 75, 120
REPLACE_FRAMES = {"s1_s2": (156, 196, 311, 310), "s2_s3": (482, 196, 311, 310), "s1_s3": (808, 196, 311, 310)}
REPLACE_OPTIONS = {"s1_s2": (312, 340), "s2_s3": (638, 340), "s1_s3": (963, 340)}  # the frames' centres (tapped live, #453)
REPLACE_CANCEL, REPLACE_CONFIRM = (507, 542), (790, 542)
REPLACE_ASK = [420, 486, 440, 28]  # 2nd layer only: "Spend 45 Cost to replace this Skill?" (y 493-508)
# What DIALOG_TITLE reads on both layers, the counts line lying inside it: to_main's tell, at no extra OCR.
REPLACE_MARK = ("Skills Owned", "SKILL1x", "SKILL2x")
REPLACE_SETTLE = 4  # s the final Confirm waits for the main page's new Cost: CONNECTING ~0.3 s, the page ~0.6 s later (#453)
# ID Skill Search (#456; spec 02 「ID Skill Search」), measured on tests/screens/ShopIdSkillSearch*.png. Its slot opens the
# select mode; a portrait there opens the Replace dialog above, at its own prices; its Return is BOTTOM_RIGHT.
SELECT_TITLE = [430, 15, 420, 35]  # select mode: "Select a Sinner for Skill Replacement." (also the Shop node's ShopSelectSinner)
PAY_SWITCH = (957, 140)  # the dialog's double arrow left of its Cost: Cost <-> the owned starlight (the Cost box shows it)


def cost_in(context, image, roi=SHOP_COST):
    """The Cost OCR reads in roi of image (digits), None without a digit."""
    return digits(text(context, image, roi))


def read_cost(context, roi=SHOP_COST):
    """The Cost in roi, read again on a fresh screenshot when OCR gives no digit; None when 3 reads give none (#82).

    None is never a Cost of 0: a caller that needs the Cost does nothing on None and logs it.
    """
    for _ in range(3):
        cost = cost_in(context, screen(context), roi)
        if cost is not None:
            return cost
        time.sleep(0.5)  # kept (#58): an OCR retry on a fresh screenshot, the Cost still fading in
    return None


# A portrait's mean saturation on the shop's main page: the dead 24-51 (over the old 30; by eye, the blue SP badge on a grey
# portrait), the living 83-158 (12 main-page captures of tests/screens, 144 portraits; test_shop_skill). Under a dialog or the
# fuse page the bar is shaded (62-92), and it is never read there.
BAR_GREY = 65


def bar_dead(image):
    """The sinners grey on the shop's sinner bar (SHOP_PORTRAIT_X, the game's order) of the main page: the dead, whose
    portrait takes no tap in ID Skill Search's select mode (#456 capture)."""
    return {sinner for x, sinner in zip(SHOP_PORTRAIT_X, battle.SINNERS)
            if saturation(image[630:680, x - 25:x + 25]).mean() < BAR_GREY}


def note_skills(sinner, owned):
    """RUN["skills"][sinner] = the counts (c1, c2, c3) read or made this run, or forgets them (owned None): the only writer
    (#264: a sinner read at the target is not opened again this run).

    It leaves with RUN (the claim, the give-up, a new run, a task change: the Mirror Dungeon left) and survives floors and
    hand-backs. A cache of the screen: the next dialog reads the counts again and overwrites it. A remembered deck never
    runs ahead of the game's (#455): an outcome not known is forgotten, which costs one more open at a later shop.
    """
    skills = RUN.setdefault("skills", {})
    if owned is None:
        skills.pop(sinner, None)
    else:
        skills[sinner] = list(owned)


def cell_state(cell, gift_list, owned=()):
    """What the list makes of the gift a cell shows, for the log (#299): "want", "keep", "locked" (a drop gift a wanted
    fusion not in `owned` needs), "drop", or "unknown" (the icon was not told)."""
    if cell["id"] is None:
        return "unknown"
    own = state(gift_list, cell["id"])
    return "locked" if own == "drop" and effective(gift_list, cell["id"], run_packs(), owned=owned) != "drop" else own


def note_owned(team, visit, cells):
    """The ids of the owned gifts `cells` show (an unknown one left out), kept as visit["owned"] for the visit's purchases
    (gifts.purchases). Each wanted fusion among them is logged once a visit: it locks and buys nothing more (the user,
    2026-10-30)."""
    visit["owned"] = owned = [c["id"] for c in cells if c["id"] is not None]
    visit.pop("bought", None)  # the page shows them
    told = visit.setdefault("owned_fusions", [])
    for i in owned:
        if i in FUSION_IDS and i not in told and state(team["list"], i) == "want":
            told.append(i)
            log(f"shop: wanted fusion {i} {GIFT_NAMES.get(i)} is owned: its materials are no longer bought or kept")
    return owned


def owned_change(visit, gone=(), got=()):
    """Take `gone` out of the gifts the visit counts as owned (owned_now) and add `got`, in place: a sale, a fusion, a
    purchase. Unread, `got` goes to visit["bought"] and `gone` is not looked for: the sale and the fusions read the owned
    gifts first, so only a purchase comes here then."""
    if visit.get("owned") is None:
        visit.setdefault("bought", []).extend(got)
        return
    for i in gone:
        visit["owned"].remove(i)
    visit["owned"].extend(got)


def buy_list(team, visit):
    """gifts.purchases for the team's list, the run's packs, the gifts the visit counts as owned (owned_now) and the floor's
    difficulty as set_difficulty read it (floor_hard; None when it was not read, #626: a HARD run plays NORMAL floors before
    hard_from_floor, so the run's difficulty does not stand in for it)."""
    return purchases(team["list"], run_packs(), owned_now(visit), hard=RUN.get("floor_hard"))


def cell_role(cell, team, page, avoid, owned=()):
    """"material" or "keep": what the shop may do with the owned gift a cell of page ("fuse" or "sell") shows (#299).

    Material only when the gift is known (its id was read, #297) and its effective state in the team's gift list is "drop"
    (not wanted, not kept, and no material of a wanted fusion not in `owned`: gifts.effective; a pack's exclusive fusion locks
    its materials only when the run pulled one of its packs, or run_packs is unknown, #306). A gift whose id is in `avoid` (White Gossypium for a team that does
    not hold it, #90) is material whatever the list says: the team's setting comes before the list's, as on the shelf. A
    vestige is never sold unless the team sells vestiges (sell_vestiges, #161), but still fuses. A cell the fuse page tags
    Unselectable (an EX gift, #378) is kept whatever the list says: the page does not take it in. The sell page has no such
    tag (read_cells): an EX gift there shows no numeral, so its id is unknown and it is kept as any unknown cell (unseen live).
    """
    if cell.get("unselectable"):
        return "keep"
    if cell["id"] in avoid:
        return "material"
    if cell["id"] is None or effective(team["list"], cell["id"], run_packs(), owned=owned) != "drop":
        return "keep"
    if page == "sell" and cell["id"] in vestige_ids() and not team.get("sell_vestiges", False):
        return "keep"
    return "material"


def template_hits(context, image, template, threshold):
    """[(score, (x, y))]: the centres where template matches on image (TemplateMatch CCOEFF, its green masked)."""
    h, w = image.shape[:2]
    node = {"recognition": "TemplateMatch", "template": template, "threshold": threshold, "method": 5,
            "green_mask": True, "roi": [0, 0, w, h]}
    detail = context.run_recognition("ShopCell", image, {"ShopCell": node})
    return [(r.score, (r.box[0] + r.box[2] / 2, r.box[1] + r.box[3] / 2)) for r in (detail.filtered_results if detail else [])]


def cell_id(context, grid, at, keyword, tier):
    """(the id of the gift whose icon is on the cell centred at `at` of the scaled grid, its score): None when unknown (#297).

    The icons of the gifts of the cell's keyword and tier (gift_cells.candidates) are matched in turn, CCOEFF with its
    green masked, within CELL_ICON_ROI of the centre; the best is the cell's gift when gift_cells.best accepts it. The
    matching stops at an icon of gift_cells.ICON_SURE: another candidate cannot tie it (a cell's lookalikes score 0.66 at most).
    When none of them is accepted, the keyword's other gifts are matched too (gift_cells.of_keyword: the tier numeral may be
    misread, #330), the earlier scores kept for the lead; there is no early stop, the twin of another tier (Dark and Faint
    Vestige) scores as high. A cell with no tier or badge read, or none of whose candidates match, is unknown: shops treat it as a gift to keep.
    """
    cx, cy = round(at[0]), round(at[1])
    h, w = grid.shape[:2]
    x, y = max(0, cx - CELL_ICON_ROI // 2), max(0, cy - CELL_ICON_ROI // 2)
    roi = [x, y, min(CELL_ICON_ROI, w - x), min(CELL_ICON_ROI, h - y)]
    scores = []

    def match_icons(pool, stop_when_sure):
        for e in pool:
            node = {"recognition": "TemplateMatch", "template": e["template"], "threshold": 0.0, "method": 5, "green_mask": True, "roi": roi}
            detail = context.run_recognition("ShopCellIcon", grid, {"ShopCellIcon": node})
            scores.append((e["id"], detail.best_result.score if detail and detail.best_result else 0.0))
            if stop_when_sure and scores[-1][1] >= gift_cells.ICON_SURE:
                break

    match_icons(gift_cells.candidates(GIFTS, keyword, tier), stop_when_sure=True)
    found = gift_cells.best(scores)
    if found is None:  # #330
        tried = {i for i, _ in scores}
        match_icons([e for e in gift_cells.of_keyword(GIFTS, keyword, tier) if e["id"] not in tried], stop_when_sure=False)
        found = gift_cells.best(scores)
    return found, max((s for _, s in scores), default=0.0)


def held(image, x, y, page):
    """Whether the cell of page centred at (x, y) holds a gift: textured (shop.filled), or on the fuse page tagged
    Unselectable (shop.unselectable: a gift drawn dim, flat as an empty cell, #378)."""
    return shop.filled(image, x, y) or (page == "fuse" and shop.unselectable(image, x, y))


def read_cells(context, image, cells, page):
    """The cells holding a gift of a shop grid read off one screenshot (#76, #112): [{"i", "x", "y", "tier", "keyword",
    "id", "score", "unselectable", "ex"}].

    The grid is scaled so gift icons are at their GiftSearch template's size, then each keyword's badge is matched once
    over it. keyword: the cell's best badge, "Keywordless" with none, None when the badge is below the grid's edge. An
    empty cell is flat (live: spread 1-2, a gift 41-84), unless the fuse page tags it Unselectable (held).
    id: the data's id of the gift the cell shows (cell_id), None when unknown, score the best icon's; tier is then that gift's.
    unselectable: the fuse page's tag (#378); ex: on the owned gifts' pages (fuse, sell) no numeral read, the green "EX" there
    instead (shop.ex_mark, #449). With either and no numeral, the cell's candidates are EX_TIER's.
    """
    scale, bottom = CELL_PAGES[page]
    half = shop.CELL_HALF
    tagged = {i for i, (x, y) in enumerate(cells) if page == "fuse" and shop.unselectable(image, x, y)}
    filled = [(i, x, y) for i, (x, y) in enumerate(cells) if i in tagged or shop.filled(image, x, y)]  # held
    if not filled:
        return []
    x0, y0 = min(x for _, x, _ in filled) - half, min(y for _, _, y in filled) - half
    x1, y1 = max(x for _, x, _ in filled) + half, min(bottom, max(y for _, _, y in filled) + half)
    grid = shop.rescale(image[y0:y1, x0:x1], 1 / scale)
    crops = {i: shop.cell_crop(image, x, y, scale) for i, x, y in filled}
    out = [{"i": i, "x": x, "y": y, "tier": shop.tier(crops[i]),
            "keyword": "Keywordless" if y + 40 <= bottom else None, "unselectable": i in tagged,
            "at": ((x - x0) / scale, (y - y0) / scale)} for i, x, y in filled]
    for c in out:
        c["ex"] = c["tier"] is None and page in OWNED_GRID and shop.ex_mark(crops[c["i"]])
    best = {}
    for keyword in BADGES:
        for score, (bx, by) in template_hits(context, grid, f"Shop/Badge{keyword}.png", BADGE_MIN):
            for c in out:  # a badge sits 12-40 px right of and below its cell's centre, on the scaled grid
                cx, cy = c["at"]
                if c["keyword"] and 12 <= bx - cx <= 40 and 12 <= by - cy <= 40 and score > best.get(c["i"], 0):
                    best[c["i"]], c["keyword"] = score, keyword
    for c in out:
        tier = EX_TIER if c["tier"] is None and (c["unselectable"] or c["ex"]) else c["tier"]
        c["id"], c["score"] = cell_id(context, grid, c.pop("at"), c["keyword"], tier)
        if c["id"] is not None:
            c["tier"] = GIFT_TIERS[c["id"]]  # the numeral may be misread (#330): the gift's own tier decides
    return out


def read_plates(context, image, centres):
    """The name plate under each offer cell centred at a (x, y) of centres: [{"text", "id"}], id None when it names no gift (#329).

    One OCR line per plate (only_rec) in the box gift_cells.plate_roi gives, dimmed and Purchased cells included. The box
    is relative to the cell's centre, so a grid dragged to another row reads just the same. On DirectML a line takes about
    31 ms once a det+rec pass has used the OCR instance; a plate-only instance read in 5 ms but cost 150 MB and 31 MB of
    package, so the plates share the default one (#329).
    """
    plates = []
    for x, y in centres:
        t = text(context, image, gift_cells.plate_roi(x, y), only_rec=True)
        plates.append({"text": t, "id": gift_cells.name_id(t, GIFT_IDS)})
    return plates


def offer_cell(slot):
    """The icon centre of an offer read by shop.read_slots: its column's, 52 px over its price line."""
    return min((x for x, _ in OFFER_CELLS[:4]), key=lambda x: abs(x - slot["x"])), slot["y"] - 52


def cell_line(cell, role):
    """One cell read for the log: "2 III Bleed 9042 Smokes and Wires (0.77): keep", an unknown gift "unknown (best 0.38)" (#297),
    a cell the fuse page tags Unselectable "... (0.78) unselectable: keep" (#378), a cell showing the green "EX" for its
    numerals "1 EX Keywordless 9799 A Certain Philosophy (0.78): keep" (#449)."""
    tier = "EX" if cell.get("ex") else "I II III IV V".split()[cell["tier"] - 1] if cell["tier"] else "?"
    tag = " unselectable" if cell.get("unselectable") else ""
    return f"{cell['i']} {tier} {cell['keyword'] or 'badge unread'} {gift_shown(cell)}{tag}: {role}"


def gift_shown(cell):
    """The gift a read cell was taken for, for the log: "9042 Smokes and Wires (0.77)", or "unknown (best 0.38)" (#297)."""
    named = GIFT_NAMES.get(cell["id"])
    if named and cell.get("by_plate"):  # told by its name plate alone (a dimmed cell, #329)
        return f"{cell['id']} {named} (plate)"
    return f"{cell['id']} {named} ({cell['score']:.2f})" if named else f"unknown (best {cell['score']:.2f})"


def close_tooltip(context, page, force=False):
    """A screenshot of page with no gift tooltip over its grid, the page checked (page_guard), #331.

    A tooltip comes up over a cell tapped and hides the cells under it. With one on show (shop.tooltip), or force (a cell
    was just tapped), the page's TOOLTIP_CLOSE spot is tapped and the screen waited on to move and stop. The tap comes
    first and the guard after it (ADR 0007): a tooltip over the fuse page hides Leave, so the page node reads nothing until
    it is closed. With none on show nothing is tapped or waited for (#378: 1.5 s a read, live), unless the guard does not
    find the page on that screenshot: a tooltip shop.tooltip missed may hide Leave, so it is tapped as with one.
    A page without a TOOLTIP_CLOSE spot: as it is.
    """
    image = screen(context)
    if page not in TOOLTIP_CLOSE:
        return page_guard(context, "Shop", image=image)
    if not force and not shop.tooltip(image):
        try:
            return page_guard(context, "Shop", image=image)
        except PageGone:
            pass
    tap_settled(context, *TOOLTIP_CLOSE[page], timeout=1.0)
    return page_guard(context, "Shop")


def read_clear(context, image, spots, page):
    """read_cells of spots on image, the cells that read unknown read again on a screenshot taken after one more tap
    on the page's TOOLTIP_CLOSE spot (#331): ([cell], [the screenshot each was read from]). The tap is made whether a
    tooltip shows or not: one shop.tooltip missed may be what hid them."""
    cells = read_cells(context, image, spots, page)
    shots = [image] * len(cells)
    unknown = [k for k, c in enumerate(cells) if c["id"] is None]
    if unknown and page in TOOLTIP_CLOSE:
        again = close_tooltip(context, page, force=True)
        for c in read_cells(context, again, [(cells[k]["x"], cells[k]["y"]) for k in unknown], page):
            k = unknown[c["i"]]
            cells[k], shots[k] = {**c, "i": cells[k]["i"]}, again
    return cells, shots


def owned_cells(context, page, grid=None):
    """Every gift of the fuse or sell page's owned grid, each read once where it shows whole (#205): ([cells], grid).

    The grid is read on show (read_cells, and the prices on the sell page), then dragged to bring its first cut-off
    row up to the first row's place (with none, the row under a full last row), until no cut-off cell holds a gift or a
    drag moves it no more. A cell is {"i", "x", "y", "tier", "keyword", "id", "score", "price", "look"}: i its place in the
    grid's order, y with the grid at its top, look its centre as read (cell_at finds it again by both); grid is
    {"page", "at": px scrolled, "top": at with the list at its top, "whole": the read went to the grid's end, "placed":
    False, the cells read (fused_cells places them), "missed": a cell not where the grid put it (cell_at)}. The list goes
    to its top first (owned_top).
    """
    (x0, y0), (dx, dy), under = OWNED_GRID[page]
    bottom = CELL_PAGES[page][1]
    out, done = [], set()
    grid, image = owned_top(context, page, grid)
    grid.update(whole=False, placed=False, missed=False)
    if image is None:
        log("shop: no E.G.O Gifts Owned on the fuse page: nothing read")
        return [], grid
    for _ in range(GRID_SCROLLS):
        image = close_tooltip(context, page)
        rows = range(max(0, grid["at"] // dy), grid["at"] // dy + 5)  # the last one all under the edge
        shown = [(5 * r + c, x0 + dx * c, y0 + dy * r - grid["at"]) for r in rows for c in range(5)]
        fresh = [(i, x, y) for i, x, y in shown if i not in done and whole(page, y)]
        done |= {i for i, _, _ in fresh}
        spots = [(x, y) for _, x, y in fresh]
        prices = shop.cell_prices(ocr(context, image, SELL_GRID), spots) if page == "sell" and spots else {}
        cells, shots = read_clear(context, image, spots, page)
        for c, shot in zip(cells, shots):
            i, _, y = fresh[c["i"]]
            out.append({**c, "i": i, "y": y + grid["at"], "price": prices.get(c["i"]), "look": centre(shot, c["x"], y)})
        cut = [y for _, x, y in shown if y + under > bottom and y - 25 < bottom and held(image[:bottom], x, y, page)]
        hidden = min(y for _, _, y in shown if y - 25 >= bottom)
        # A full row over the edge and the next one all under it (a drag the game took less of, or the grid's end): one
        # drag more tells them apart.
        full = not cut and all(held(image[:bottom], x0 + dx * c, hidden - dy, page) for c in range(5))
        if not cut and not full:
            grid["whole"] = True
            break
        moved, image = drag_grid(context, page, (min(cut) if cut else hidden) - y0 - GRID_MARGIN)
        grid["at"] += moved
        if abs(moved) <= 3:
            grid["whole"] = full
            log(f"shop: the {page} grid does not move: " + ("at its end" if full else "its cut-off cells stay unread"))
            break
    else:
        log(f"shop: the {page} grid still has cut-off cells after {GRID_SCROLLS} drags: they stay unread")
    log(f"shop: {page} grid read down {grid['at']} px")
    return out, grid


def owned_top(context, page, grid=None):
    """(grid, the screenshot) with page's list dragged to its top; on the fuse page the owned gifts placed by their label
    (owned_label), the screenshot None when it does not show.

    A page opens where its list was left (live 2026-10-21: the fuse page after a fusion), so a new grid's list goes to its
    top stroke by stroke (grid_top). A grid an earlier read of the page still open left (the fuse page after a fusion,
    #378) goes back by its top in one drag, and to its top stroke by stroke only when the label does not show then. The
    owned gifts are placed by their label whatever that drag measured: sections over them come and go with a fusion (#304).
    """
    (_, y0), _, _ = OWNED_GRID[page]
    kept = grid is not None
    close_tooltip(context, page)
    if kept:
        moved, image = drag_grid(context, page, grid["top"] - grid["at"])
        grid["at"] += moved
    else:
        grid, image = {"page": page, "at": 0, "top": 0}, grid_top(context, page)
    if page != "fuse":
        return grid, image
    label, image, up = owned_label(context, image)
    if label is None and kept:  # the drag back stopped short (a stroke the game took less of): owned_label looks only up
        log("shop: the owned gifts' label is not on show after the drag back: the fuse list goes to its top")
        label, image, up = owned_label(context, grid_top(context, page))
    if label is None:
        return grid, None
    grid["at"] = y0 - label - OWNED_LABEL  # negative: sections over the owned gifts push them down
    grid["top"] = grid["at"] - up
    if not whole(page, y0 - grid["at"]):
        log(f"shop: the owned gifts start at y {y0 - grid['at']}, under the sections over them")
        moved, image = drag_grid(context, page, -grid["at"] - GRID_MARGIN)
        grid["at"] += moved
    return grid, image


def owned_label(context, image):
    """(the centre y of the fuse page's "E.G.O Gifts Owned" label, the screenshot it shows on, the px the list was dragged
    up to show it). From the list's top, up a stroke at a time until it shows: a fixed recipe's section (#103, #78) or a
    limited fusion's sits over it, neither used (#205). (None, the last screenshot, px) when the list ends without it."""
    up = 0
    for _ in range(GRID_SCROLLS):
        box = next((b for t, b in ocr(context, image, FUSE_LIST) if has(t, "Gifts Owned")), None)
        if box:
            return box[1] + box[3] // 2, image, up
        moved, image = drag_grid(context, "fuse", GRID_STROKE)
        up += moved
        if abs(moved) <= 3:
            break
    return None, image, up


def grid_top(context, page):
    """The screenshot of page's list dragged down to its top, a stroke at a time until one moves it no more."""
    for _ in range(GRID_SCROLLS):
        moved, image = drag_grid(context, page, -GRID_STROKE)
        if abs(moved) <= 3:
            return image
    return image


def whole(page, y):
    """Whether a cell of page's owned grid centred at y on screen shows whole: its top and what must show under it."""
    (_, y0), _, under = OWNED_GRID[page]
    return y >= y0 - 3 and y + under <= CELL_PAGES[page][1]


def grid_shift(before, after, page, most):
    """How many px page's owned grid moved up from before to after (down: negative), 0 to most give or take GRID_SLIP:
    the shift under which the two screenshots' grids differ least."""
    (x0, y0), (dx, _), _ = OWNED_GRID[page]
    rows, cols = slice(y0 - 45, CELL_PAGES[page][1]), slice(x0 - 40, x0 + 4 * dx + 40, 3)
    a, b = (im[rows, cols].astype(np.int16).sum(axis=2) for im in (before, after))
    n = len(a)

    def diff(s):
        return np.abs(a[s:] - b[:n - s]).mean() if s >= 0 else np.abs(a[:n + s] - b[-s:]).mean()
    return min(range(min(0, most) - GRID_SLIP, max(0, most) + GRID_SLIP + 1), key=diff)


def drag_grid(context, page, d):
    """Drag page's owned grid up by d px (down when negative) in strokes inside it, each measured (grid_shift): the
    px it moved and the last screenshot. Dragged past an end the grid springs back: the stroke moved it less, and the
    drag stops there."""
    (_, y0), _, _ = OWNED_GRID[page]
    bottom = CELL_PAGES[page][1]
    image, moved = screen(context), 0
    n = -(-abs(d) // GRID_STROKE)
    for k in range(n):
        step = round(d * (k + 1) / n) - round(d * k / n)
        before = page_guard(context, "Shop", image=image)
        scroll(context, GRID_DRAG_X, bottom - 15 if step > 0 else y0 - 30, 0, -step)
        image = still(context, timeout=1.0)
        image = screen(context) if image is None else image
        s = grid_shift(before, image, page, step)
        moved += s
        if abs(s) < abs(step) - 3:
            break
    log(f"shop: {page} grid dragged {d} px, moved {moved}")
    return moved, image


def centre(image, x, y):
    """The grey centre of the grid cell at (x, y) in 4 px blocks, inside its frame (a picked cell's orange stays out):
    a fraction of a px moved blurs edges the blocks average out."""
    return image[y - 20:y + 20, x - 20:x + 20].astype(np.float32).mean(axis=2).reshape(10, 4, 10, 4).mean(axis=(1, 3))


def matched(image, x, y, look):
    """(difference, dy): where within 3 px of (x, y) the cell's centre is likeliest the one look was read from."""
    return min(((np.abs(centre(image, x, y + k) - look).mean(), k) for k in range(-3, 4)), key=lambda m: (m[0], abs(m[1])))


def into_view(context, grid, cell, rows_over=0):
    """Drag the grid to bring cell (owned_cells) whole into view, its row to the first row's place, or rows_over rows
    under it (the rows over it on show too) when it has as many over it: its y on screen."""
    (_, y0), (_, dy), _ = OWNED_GRID[grid["page"]]
    over = min(rows_over, (cell["y"] - y0) // dy) * dy
    for _ in range(3):  # a drag stopped short (an end, a stroke the game took less of) is followed by another
        y = cell["y"] - grid["at"]
        if whole(grid["page"], y):
            break
        grid["at"] += drag_grid(context, grid["page"], y - over - y0 - GRID_MARGIN)[0]
    return cell["y"] - grid["at"]


def cell_at(context, grid, cell):
    """Where cell (owned_cells) shows now: (x, y) on screen, the grid dragged first to bring it whole into view; None
    when its centre there is not the one read (the grid is not where it was measured to be): nothing is tapped, and
    grid["missed"] says so."""
    x, y = cell["x"], into_view(context, grid, cell)
    diff, k = matched(screen(context), x, y, cell["look"])
    if diff > GRID_SAME:
        log(f"shop: cell {cell['i']} is not where the grid puts it ({grid['page']} grid at {grid['at']} px, {diff:.1f})")
        grid["missed"] = True
        return None
    return x, y + k


def fused_cells(context, cells, grid, fusion):
    """The fuse page's owned gifts after `fusion` (Shop.fuse_ordinary's or fuse_recipe's), on the page kept open (#378):
    placed by it instead of read again ([cell], as owned_cells gives them), or None when they are to be read again (the
    reason logged).

    shop.fusion_places puts the gifts left and the gift made in the grid's new order: only when the last read went to the
    grid's end and gave every place a tier, in the page's order (the vestiges first, then highest tier first). After a
    recipe the owned gifts are placed by their label first (owned_top): its Fusion Available section may have gone, the
    list moved up (#304). The gift made's cell is dragged into view, a row over it on show too, and read: it is placed
    (fused_check) when its tier is the fusion's (a recipe's: its id; an ordinary one's, the tier its GET! popup showed,
    #451, tier V for an EX gift, #449),
    its id is read and no gift listed with that id or an unread one looks like it, every other cell on show looks as it was
    read (matched within GRID_SAME) and the places after the last hold no gift. A check that fails places the owned gifts
    by their label once (the list may have sprung back from its end, a section come or gone) and checks again. Each tap
    after it still checks its cell (cell_at).
    """
    (x0, y0), (dx, dy), _ = OWNED_GRID["fuse"]
    placed = grid.get("whole") and shop.fusion_places(cells, [c["i"] for c in fusion["gone"]], fusion["tier"], ((x0, y0), (dx, dy)))
    if not placed:
        log("shop: fuse page kept: " + ("the last read stopped short of the grid's end" if not grid.get("whole") else
                                        "the cells read give no order by tier") + ", owned gifts read again")
        return None
    new, k = placed
    recipe = fusion["gift"] is not None
    if recipe and owned_top(context, "fuse", grid)[1] is None:
        problem, cell = "no E.G.O Gifts Owned label after the recipe", None
    else:
        problem, cell = fused_check(context, new, k, grid, fusion)
    if problem is not None and not recipe:
        log(f"shop: fuse page kept: {problem}, the owned gifts are placed by their label")
        if owned_top(context, "fuse", grid)[1] is None:
            problem = "no E.G.O Gifts Owned label"
        else:
            problem, cell = fused_check(context, new, k, grid, fusion)
    if problem is not None:
        log(f"shop: fuse page kept: {problem}, owned gifts read again")
        return None
    new[k] = cell
    grid.update(placed=True, missed=False)
    log(f"shop: fuse page kept: owned gifts placed by the fusion (new gift read at cell {k})")
    return new


def misplaced(grid):
    """Whether a cell of the grid placed by a fusion (fused_cells) did not show where it was put (cell_at)."""
    return bool(grid.get("placed") and grid.get("missed"))


def fused_check(context, new, k, grid, fusion):
    """(None, the gift made's cell as read) when the screen shows the owned gifts as fused_cells placed them, else (what
    does not hold, None): the gift made's cell `new[k]` dragged into view and read, the other cells on show compared."""
    (x0, y0), (dx, dy), _ = OWNED_GRID["fuse"]
    y = into_view(context, grid, new[k], rows_over=1)
    image = close_tooltip(context, "fuse")
    for c in new:
        at = c["y"] - grid["at"]
        diff = matched(image, c["x"], at, c["look"])[0] if c["i"] != k and whole("fuse", at) else 0
        if diff > GRID_SAME:
            return f"cell {c['i']} is not where the fusion puts it ({diff:.1f})", None
    for j in range(len(new), len(new) + 10):
        at = y0 + dy * (j // 5) - grid["at"]
        if whole("fuse", at) and held(image, x0 + dx * (j % 5), at, "fuse"):
            return f"cell {j} holds a gift, after the last", None
    if not whole("fuse", y):
        return f"cell {k}, the gift made, is not on show", None
    read, shots = read_clear(context, image, [(new[k]["x"], y)], "fuse")
    if not read or read[0]["id"] is None:
        return f"the gift made reads {'unknown' if read else 'no gift'} at cell {k}", None
    cell = {**read[0], "i": k, "x": new[k]["x"], "y": new[k]["y"], "price": None, "look": centre(shots[0], new[k]["x"], y)}
    if cell["tier"] != fusion["tier"] or fusion["gift"] not in (None, cell["id"]):
        made = f"tier {fusion['tier']}" + (f" {fusion['gift']}" if fusion["gift"] else "")
        return f"cell {k} reads tier {cell['tier']} {gift_shown(cell)}, not the {made} made", None
    # A cell listed that looks like it and is not told apart by its id (the same id, or one unread): the gift made may be
    # that one still. Another id read is another gift: live, Old Wooden Doll (II) looked like Finifugality (III), #378.
    twin = next((c["i"] for c in new if c["i"] != k and c["id"] in (None, cell["id"])
                 and matched(shots[0], cell["x"], y, c["look"])[0] <= GRID_SAME), None)
    if twin is not None:
        return f"cell {k}, the gift made, looks like cell {twin}", None
    return None, cell


def fusions(cells, roles, slots, avoid, condition="any", refused=()):
    """shop.pick_fusion over the cells whose role is material and whose tier is read: [([cell index], tier)] (#77).

    The thresholds are the Super Shop's when the page has its 5 slots; a gift whose id is in avoid goes in first (#90);
    condition is the gift list's fusion_condition (#263); refused, the tiers (sorted) of the groups the page's forecast
    turned down (#285).
    """
    d = data("shop.yaml")
    materials = [(c["i"], c["tier"]) for c, r in zip(cells, roles) if r == "material" and c["tier"]]
    tiers = d["fusion_tiers"]["super_shop" if slots == 5 else "shop"]
    return shop.pick_fusion(materials, slots, tiers, d["fusion_points"], {c["i"] for c in cells if c["id"] in avoid},
                            condition, refused)


def read_forecast(context):
    """(the tier the fuse page's Forecasts row predicts, the keyword's chance in %), each None when unread (#285).

    The row shows once a material is in: waited for a second, not longer (a page whose row never reads is no loss).
    """
    image = until(context, shop.forecast_tier, timeout=1.0)
    if image is None:
        return None, None
    return shop.forecast_tier(image), number(text(context, image, FORECAST_CHANCE, only_rec=True))


def tap_keyword(context, keyword):
    """Tap the keyword's card in an open keyword dialog; False when its label is not read."""
    label = next((b for t, b in ocr(context, screen(context), KEYWORD_LABELS) if compact(t) == compact(keyword)), None)
    if label:
        x, y, w, h = label
        tap_moved(context, x + w // 2, y - 40)  # the card lights up
    return bool(label)


def gift_get(context):
    """Confirm the E.G.O Gift GET! popup after a purchase or a fusion: the screenshot its title was read on, None when none
    comes up in 4.5 s. Its gift's mark is on that screenshot already (#449: the 2026-11-04 recording at 30 fps shows the
    title and the "EX" from the popup's first frame, 0.3 s before the tap took it away)."""
    def title(image):
        return has(text(context, image, GET_TITLE), "GET")
    image = until(context, title, timeout=4.5)
    if image is None:
        return None
    for _ in range(3):  # a tap while the popup zooms in is lost
        if tap_then(context, *GET_CONFIRM, lambda im: not title(im), timeout=1.5) is not None:
            still(context, timeout=1.0)  # the popup fades out over the Cost
            break
    return image


def pick_cells(cells, materials):
    """One cell of `cells` per gift id of `materials` (repeats take another cell each)."""
    left, picked = list(cells), []
    for gift_id in materials:
        picked.append(left.pop(next(n for n, c in enumerate(left) if c["id"] == gift_id)))
    return picked


def recipe_places(team, cells, slots):
    """The places (`i`) of the cells the fuse page will make wanted fusions from (#300): every fusion the owned cells hold
    the materials of, one after another. A sale leaves them, and they are no ordinary fusion's materials."""
    left, held = list(cells), set()
    while recipe := recipe_fusion(team["list"], [c["id"] for c in left if c["id"] is not None], slots=slots):
        group = pick_cells(left, recipe["materials"])
        held |= {c["i"] for c in group}
        left = [c for c in left if c["i"] not in held]
    return held


@AgentServer.custom_action("Shop")
class Shop(CustomAction):
    """Heal, replace skills, then sell -> buy and refresh -> fuse until a round does nothing, then leave (spec 03 section 13).

    The visit's state (healed, refreshes used, the gift wanted and whether a sale was tried for it, whether the
    owned gifts were scanned for a fusion, the sinners whose Replace slot was tapped (skill_tapped), the sinners ID Skill
    Search tried (id_tried) and whether it was used (id_searched)) lives in RUN["shop"], so a re-entry from MirrorHub
    carries on; leaving drops it, and a recovery drops the fusion scan (forget_game_state, #459). Every spend keeps the
    team's reserve_cost.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        if not self.to_main(context):
            return True  # a page fading in or out: let MirrorHub look again
        RUN["after_shop"] = True  # #279: the next map's only node is the boss; cleared by the next node entered
        visit = RUN.setdefault("shop", {"healed": False, "refreshes": {"keyword": 0, "normal": 0}, "wanted": None, "sold": False})
        # The sale groups by the fuse page's slots and thresholds before that page was read: a Super Shop's red title tells (#263).
        if "slots" not in visit:
            visit["slots"] = 5 if shop.is_super(screen(context)) else 3
        if not visit["healed"]:
            visit["healed"] = True  # first: a heal handed back mid-way (#118) is not paid twice
            self.heal(context, team)
        self.skill_step(context, team, visit)  # after the heal, before the rounds (#264 時機)
        for _ in range(shop.ROUNDS):
            if not self.to_main(context):
                break  # left already: the leave below finds the map
            acted = self.sell(context, team, visit)
            acted = self.buy(context, team, visit) or acted
            acted = self.fuse(context, team, visit) or acted
            if not acted:
                break
        else:
            log(f"shop: still acting after {shop.ROUNDS} rounds")
        for _ in range(3):
            image = screen(context)
            if on_map(context, image):
                log("shop: already out of the shop")
                leave_shop()
                return True
            # The dialog slides down; Confirm takes no tap before it stops.
            page_guard(context, "Shop", image=image)
            if tap_shown(context, *BOTTOM_RIGHT, lambda im: has(text(context, im, LEAVE_DIALOG), "Leave the shop"),
                         timeout=1.5) is not None:
                log(f"shop: leave with {read_cost(context)} Cost")
                # Up to the old 2 s for the map: MirrorHub must not find the shop fading out and start a new visit.
                tap_then(context, *LEAVE_CONFIRM, lambda im: on_map(context, im), timeout=2)
                leave_shop()
                return True
        return stuck("Leave did not bring up `Leave the shop?`")

    @staticmethod
    def to_main(context):
        """Back out of any shop page or dialog; True once the main shop (its Refresh fee) shows.

        False at once on the map: the shop was left (live 2026-10-18, by hand mid-visit), and a tap
        meant for a shop page lands on a map node.
        """
        for _ in range(5):
            image = screen(context)
            at = Shop.way_out(context, image)
            if at in ("map", "main"):
                return at == "main"
            if at is None:
                page_guard(context, "Shop", image=image)  # not a shop page MirrorHub knows: hand it back
                still(context, timeout=1.5)  # a page fading in or out
            else:
                tap_settled(context, *at)
        return False

    @staticmethod
    def way_out(context, image):
        """What image asks of to_main: "map" (the shop was left), "main" (the main page: its Refresh fee shows), the point to
        tap to close a page or dialog (a heal page's Return or Leave too), or None (a page the shop does not know)."""
        if on_map(context, image):
            return "map"
        title = text(context, image, DIALOG_TITLE)
        if has(text(context, image, GET_TITLE), "GET"):
            return GET_CONFIRM
        if has(title, "Purchase"):
            return PURCHASE_CANCEL
        # Before the Refresh fee: the dialog's Cost digits (x 1020-1061) overlap REFRESH["normal"]'s box (#455).
        if has(title, *REPLACE_MARK):
            return REPLACE_CANCEL
        if has(title, "Keyword Refresh"):
            return KEYWORD_CANCEL
        if has(title, "Keyword Selection"):
            return (490, 566)  # its Cancel
        if has(title, "Gift Info"):  # a bought offer tapped: only a tap outside it closes it
            return OUTSIDE
        if has(title, "E.G.O Gift"):  # the fuse or sell page, a keyword picked or not (#214)
            log(f"shop: {title!r} closed")
            return PAGE_CLOSE
        if has(text(context, image, LEAVE_DIALOG), "Leave the shop"):
            return LEAVE_CANCEL
        if has(text(context, image, HEAL_TITLE), "Heal"):
            return BOTTOM_RIGHT
        # Before the Refresh fee too: it still reads in ID Skill Search's select mode (#456), whose Return leaves it.
        if has(text(context, image, SELECT_TITLE), "Select a Sinner"):
            return BOTTOM_RIGHT
        if number(text(context, image, REFRESH["normal"][1])) is not None:
            return "main"
        return None

    @staticmethod
    def heal(context, team):
        """Heal everyone once, or revive the dead, per the team's heal setting.

        The dead are the grey portraits on the shop's sinner bar; the count from the last formation
        (RUN["alive"]) is only checked against them, as the shop shows deaths since then too.
        """
        if team["heal"] == "none":
            return  # nothing to decide: skip the Cost and portrait reads
        cost = read_cost(context)
        if cost is None:
            log("shop: the Cost reads nothing: no heal")
            return
        grey = bar_dead(screen(context))
        dead = [x for x, sinner in zip(SHOP_PORTRAIT_X, battle.SINNERS) if sinner in grey]
        if "alive" in RUN and 12 - RUN["alive"] != len(dead):
            log(f"shop: {12 - RUN['alive']} dead at the last formation, {len(dead)} grey portraits")
        plan = shop.heal_plan(team["heal"], cost, team["reserve_cost"], len(dead), data("shop.yaml")["heal_cost"])
        log(f"shop: {cost} Cost, {len(dead)} dead, heal {team['heal']}: {plan or 'nothing'}")
        if not plan:
            return
        kind, n = plan
        for x in dead[:n] if kind == "revive" else [None]:
            page_guard(context, "Shop")
            if tap_shown(context, *SHOP_BUTTONS["heal"], lambda im: has(text(context, im, HEAL_TITLE), "Heal"), timeout=2) is None:
                log("shop: the heal page did not open")
                break
            before = read_cost(context, HEAL_COST)

            def paid(im):
                return cost_in(context, im, HEAL_COST) not in (None, before)
            if x is None:
                tap_shown(context, *HEAL_OPTIONS[kind], paid, timeout=1.5)
            else:
                tap_settled(context, *HEAL_OPTIONS[kind], timeout=1.5)
                # only a dead sinner takes the tap; then Select shows
                tap_shown(context, x, 655, lambda im: has(text(context, im, BOTTOM_LABEL), "Select"), timeout=1.2)
                tap_shown(context, *BOTTOM_RIGHT, paid, timeout=2)
            after = read_cost(context, HEAL_COST)
            log(f"shop: {kind}: {before} -> {after} Cost")
            if after == before:
                break
            if kind == "revive" and "alive" in RUN:
                RUN["alive"] += 1
            # the result's Leave: back to the shop
            tap_then(context, *BOTTOM_RIGHT, lambda im: not has(text(context, im, HEAL_TITLE), "Heal"), timeout=2)
            Shop.to_main(context)
        Shop.to_main(context)

    @staticmethod
    def skill_step(context, team, visit):
        """Replace skills (#264 時機, 先後): the listed sinners one by one in the list's order (shop.skill_walk), each
        finished before the next: their own Replace <sinner>'s Skill slot on this page first (#455; half ID Skill Search's
        price for the same swap), then, while they still want a swap by the run's counts (shop.search_turn), ID Skill Search
        on them (#456); how many swaps went through. Called after the heal and after each refresh that took; it never refreshes.

        visit["skill_tapped"] names the sinners whose Replace slot was tapped this visit, added before the tap as the heal's
        flag is (ADR 0007): a visit handed back mid-dialog and entered again does not pay twice. A sinner leaves it again only
        when the bot itself cancelled the dialog before any Confirm because no swap was lit, priced and affordable: the step
        after the next refresh judges it again. With every target at 3/2/1, or no sinner listed, nothing is read and nothing
        tapped. After a slot or a search that tapped, the grid is read again and the next slot found by its sinner (#264:
        whether a swapped slot moves is unseen); one gone is not tapped. ID Skill Search opened on a sinner whose dialog has
        no swap goes on down the list from them, past the sinners whose own Replace slot on this page is still to come.
        """
        listed = team["skill_replacement"]["sinners"]
        if not shop.any_change(listed):
            return 0
        conf, swaps = team["skill_replacement"]["id_skill_search"], data("shop.yaml")["skill_replacement"]
        tapped = visit.setdefault("skill_tapped", [])
        offers = Shop.skill_offers(context)
        plan = shop.skill_plan(listed, offers, RUN.get("skills", {}), tapped, swaps)
        for slot, _, why in plan:
            log(f"shop: {slot['name']!r}: {why}")
        waiting = {entry["sinner"] for _, entry, _ in plan if entry}  # the Replace slots still to come
        made, fresh = 0, True  # fresh: offers is the grid as it stands
        for kind, n in shop.skill_walk(listed, waiting):
            entry = listed[n]
            sinner = entry["sinner"]
            if kind == "replace":
                waiting.discard(sinner)
            elif not (conf["enabled"] and not visit.get("id_searched")
                      and shop.search_turn(entry, RUN.get("skills", {}), visit.get("id_tried", ()), swaps)):
                continue
            if not fresh:
                offers, fresh = Shop.skill_offers(context), True
            if kind == "replace":
                slot = next((s for s in shop.skill_slots(offers) if s["sinner"] == sinner and not s["purchased"]), None)
                if slot is None:
                    log(f"shop: {sinner!r}'s slot is no longer on the grid: skip")
                    continue
                tapped.append(sinner)  # first: a hand-back mid-dialog (#118) is not paid twice
                outcome = Shop.replace_skill(context, slot, entry, team["reserve_cost"], swaps)
                made += outcome == "replaced"
                if outcome == "unchosen":
                    tapped.remove(sinner)
            else:
                outcome = Shop.id_skill_search(context, team, visit, listed[n:], waiting, offers)
                if outcome is None:
                    continue  # nothing tapped: the grid read still stands
                made += outcome
            fresh = False
            if not Shop.to_main(context):
                break  # on the map: the shop was left
        return made

    @staticmethod
    def id_skill_search(context, team, visit, listed=None, waiting=(), offers=None):
        """ID Skill Search (#456): with the team's switch on, tap the Super Shop's slot, try the listed sinners in the list's
        order (shop.id_search_plan) on their dialog and make one swap, paid the team's way; 1 on a swap, 0 when the slot was
        opened for none, None when it was not tapped. skill_step calls it on a sinner's turn (#264 先後) with listed from
        that sinner on and `waiting`, the sinners whose own Replace slot on this page is still to come (skipped: half the
        price); offers is its grid read. Without them it tries the team's whole list on a grid it reads itself.

        A dialog's Cancel lands on the main page (#456 capture), so each next sinner taps the slot again; a portrait that
        opens nothing leaves the select mode up for the next one, and the last such leaves by Return. Each sinner is tried
        once a visit (visit["id_tried"], marked before its portrait's tap); visit["id_searched"] is set before the paying tap
        (the heal's rule) and when the slot shows Purchased: after either, the slot is never opened again this visit.
        """
        conf, team_list = team["skill_replacement"]["id_skill_search"], team["skill_replacement"]["sinners"]
        if not conf["enabled"] or not shop.any_change(team_list) or visit.get("id_searched"):
            return None
        slot = shop.id_search_slot(Shop.skill_offers(context) if offers is None else offers)
        if slot is None:
            return None
        if slot["purchased"]:
            log("shop: ID Skill Search: used already (Purchased): skip")
            visit["id_searched"] = True
            return None
        swaps, tried = data("shop.yaml")["skill_replacement"], visit.setdefault("id_tried", [])
        image = page_guard(context, "Shop")
        plan = shop.id_search_plan(team_list if listed is None else listed, RUN.get("skills", {}), tried, bar_dead(image),
                                   swaps, waiting)
        for _, why in plan:
            log(f"shop: ID Skill Search: {why}")
        entries = [entry for entry, _ in plan if entry]
        if not entries:
            log("shop: ID Skill Search: nobody to try: not opened")
            return None
        before, selecting = read_cost(context), False
        for entry in entries:
            if not selecting:
                if Shop.open_offer(context, slot, "Select a Sinner", SELECT_TITLE) is None:
                    visit["id_searched"] = True  # #264: a slot that opens nothing counts as handled
                    break
                selecting = True
            tried.append(entry["sinner"])  # first: a hand-back mid-dialog (#118) does not try it again
            outcome = Shop.id_search_swap(context, entry, conf["pay"], team["reserve_cost"], before, swaps, visit)
            if outcome == "replaced":
                return 1
            selecting = outcome == "no dialog"
            if visit.get("id_searched") or not (selecting or Shop.to_main(context)):
                return 0  # paid without proof, or on the map
        if selecting:
            log("shop: ID Skill Search: no listed sinner has a feasible swap: Return")
        Shop.to_main(context)  # select mode's Return (way_out)
        return 0

    @staticmethod
    def id_search_swap(context, entry, pay, reserve, before, swaps, visit):
        """One sinner in ID Skill Search's select mode: tap the portrait, read its dialog, put the payment on `pay`, make the
        swap shop.id_search_choice gives. "replaced"; "no dialog" (the select mode is still up); "unchosen" when cancelled
        before any Confirm; "handled" otherwise. before: the main page's Cost, which starlight must leave as it was.
        """
        sinner, head = entry["sinner"], "shop: ID Skill Search: "
        page_guard(context, "Shop")  # the Shop node reads the select mode's title
        image = tap_shown(context, SHOP_PORTRAIT_X[battle.SINNERS.index(sinner)], 655, shows(context, REPLACE_TITLE, "Replace"),
                          timeout=1.5, rest=1.0)
        if image is None:
            log(f"{head}{sinner!r}'s portrait opened no dialog")
            return "no dialog"
        if (read := Shop.read_own_dialog(context, head, sinner, image)) is None:
            return "handled"
        # Never assumed to carry over: the dialog opened on Cost in the capture (tests/screens/ShopIdSkillSearchDialog.png);
        # whether the game keeps the payment mode is unverified (#456). The prices tell it; a switch must show the other prices.
        # With no price read the payment is unknown, and a switch could flip the wanted one away: cancel.
        mode = shop.pay_mode(read["lit"], read["prices"], swaps)
        if mode is None:
            log(f"{head}{sinner!r}: prices {Shop.price_line(read)}: the payment is unknown: cancel")
            Shop.cancel_replace(context)
            return "handled"
        if mode != pay:
            page_guard(context, "Shop")
            switched = tap_shown(context, *PAY_SWITCH,
                                 lambda im: shop.pay_mode(Shop.dialog_lit(im), Shop.dialog_prices(context, im), swaps) == pay,
                                 timeout=1.5, rest=1.0)
            if switched is None:
                log(f"{head}{sinner!r}: prices {Shop.price_line(read)}: the payment does not show {pay}: cancel")
                Shop.cancel_replace(context)
                return "handled"
            read = Shop.read_replace_dialog(context, switched)
        unit, budget = ("Cost", f", reserve {reserve}") if pay == "cost" else ("starlight", " (no reserve)")
        choice = Shop.judge_replace(
            context, head, sinner, entry, read, unit, budget, swaps, f" in {unit}",
            lambda owned, funds: shop.id_search_choice(entry, owned, read["lit"], read["prices"], funds, pay, reserve, swaps))
        if isinstance(choice, str):
            return choice
        (swap, price), owned, funds = choice, read["owned"], read["cost"]
        if not Shop.pay_swap(context, head, sinner, swap, price, funds, unit.capitalize(),
                             paying=lambda: visit.__setitem__("id_searched", True)):
            return "handled"
        if pay == "cost":
            return Shop.cost_paid(context, head, sinner, swap, price, funds, owned, swaps)
        # Starlight: the top right that showed it is gone with the dialog, and the slot no longer opens. The swap is proven by
        # the slot's Purchased and by the Cost left as it was; anything else forgets the counts (#455 graft 2).
        after = read_cost(context)
        bought = shop.id_search_slot(Shop.skill_offers(context))
        if after != before or not (bought and bought["purchased"]):
            log(f"{head}{sinner!r} {swap} for {price} starlight: the slot reads {'Purchased' if bought and bought['purchased'] else 'no Purchased'}, "
                f"the Cost {before} -> {after}: the counts are not known")
            note_skills(sinner, None)
            return "handled"
        sw = swaps[swap]
        log(f"{head}replaced {sinner!r} {swap} (skill {sw['from']} -> {sw['to']}) for {price} starlight: {funds} -> {funds - price} "
            f"starlight (unread after the dialog), the slot reads Purchased, the Cost stays {after}")
        note_skills(sinner, shop.after_swap(owned, swap, swaps))
        return "replaced"

    @staticmethod
    def dialog_prices(context, image):
        """The Replace dialog's three prices off image, each None when unread."""
        return {k: digits(text(context, image, box)) for k, box in REPLACE_PRICES.items()}

    @staticmethod
    def dialog_lit(image):
        """Whether each of the Replace dialog's three options is lit (its price orange) on image."""
        return {k: shop.option_lit(image, box) for k, box in REPLACE_PRICES.items()}

    @staticmethod
    def price_line(read):
        """"s1_s2 45, s2_s3 75 dim, s1_s3 120 dim": a dialog read's prices for the log."""
        return ", ".join(f"{k} {read['prices'][k]}{'' if read['lit'][k] else ' dim'}" for k in REPLACE_PRICES)

    @staticmethod
    def skill_offers(context):
        """The grid's slots as shop.read_slots gives them, one OCR pass (not read_offers' cells and plates). A Super Shop's
        grid is read at its top and after a drag down, as buy_offers reads it (#341), each slot with its "page"."""
        image = page_guard(context, "Shop")
        if not shop.is_super(image):
            return shop.read_slots(ocr(context, image, OFFER_GRID))
        top = [{**s, "page": 0} for s in shop.read_slots(ocr(context, Shop.drag_offers(context, down=False), OFFER_GRID))]
        lower = shop.read_slots(ocr(context, Shop.drag_offers(context, down=True), OFFER_GRID))
        return top + [{**s, "page": 1} for s in lower if offer_whole(s["y"]) and not any(shop.same_offer(s, k) for k in top)]

    @staticmethod
    def read_replace_dialog(context, image):
        """{"sinner", "owned", "cost", "prices", "lit"} off the dialog's screenshot: the title's sinner, the Skills Owned
        counts (None unless 5 or 6 cards), the Cost (None when 3 reads give no digit), each option's price (None when
        unread) and whether it is lit."""
        cost = cost_in(context, image, REPLACE_COST)
        return {"sinner": shop.sinner_named(text(context, image, REPLACE_TITLE)),
                "owned": shop.skills_owned(text(context, image, REPLACE_OWNED)),
                "cost": read_cost(context, REPLACE_COST) if cost is None else cost,
                "prices": Shop.dialog_prices(context, image),
                "lit": Shop.dialog_lit(image)}

    @staticmethod
    def cancel_replace(context):
        """The dialog's Cancel, on either layer: the first goes back to the shop, the second to the first; the Cost stays (#453)."""
        tap_settled(context, *REPLACE_CANCEL)

    @staticmethod
    def read_own_dialog(context, head, sinner, image):
        """The Replace dialog's read off image (a slot's or ID Skill Search's) when it is sinner's, whose Skills Owned it
        notes when they read: the counts are real whatever follows. None, cancelled with a line starting with head, when
        the dialog is another sinner's."""
        read = Shop.read_replace_dialog(context, image)
        if read["sinner"] != sinner:
            log(f"{head}the dialog is {read['sinner']!r}'s, not {sinner!r}'s: cancel")
            Shop.cancel_replace(context)
            return None
        if read["owned"] is not None:
            note_skills(sinner, read["owned"])
        return read

    @staticmethod
    def judge_replace(context, head, sinner, entry, read, unit, budget, swaps, in_unit, choose):
        """sinner's open Replace dialog, read: a line of what it shows and the swaps wanted, then #264's cancels, each
        with a line starting with head: the Skills Owned unread, the funds (read["cost"], in unit, "Cost" or "starlight";
        budget: the reserve's words) unread, or no swap from choose(owned, funds) (in_unit: that line's words on the unit,
        " in starlight", or "" for a slot's). The swap and its price; else, after the cancel, what the caller returns:
        "unchosen" when no swap was chosen, "handled" otherwise."""
        owned, funds = read["owned"], read["cost"]
        wanted = [] if owned is None else shop.swaps_wanted(entry["target"], owned, entry["s1_s3_first"], swaps)
        log(f"{head}{sinner!r}: Skills Owned {'unread' if owned is None else shop.counts_line(owned)}, {Shop.price_line(read)}, "
            f"{'unread' if funds is None else funds} {unit}{budget}: try {', '.join(wanted) or 'nothing'}")
        if owned is None:
            log(f"{head}{sinner!r}: Skills Owned unread or not 5-6 cards: cancel")
            Shop.cancel_replace(context)
            return "handled"
        if funds is None:
            log(f"{head}the {unit} reads nothing: cancel")
            Shop.cancel_replace(context)
            return "handled"
        choice = choose(owned, funds)
        if choice is None:
            log(f"{head}{sinner!r}: no swap toward {shop.counts_line(entry['target'])} is lit, priced and affordable{in_unit}: cancel")
            Shop.cancel_replace(context)
            return "unchosen"
        return choice

    @staticmethod
    def replace_skill(context, slot, entry, reserve, swaps):
        """One dialog: open the slot, read it, pick the swap shop.skill_choice gives, Confirm twice, check the Cost.

        "replaced" on a swap; "unchosen" when the bot cancelled before any Confirm because no swap was lit, priced and
        affordable; "handled" otherwise. Each failure of #264's table writes one line; the caller's to_main closes whatever
        is left open. The run's memory of the counts (note_skills) never runs ahead of the game's.
        """
        sinner = slot["sinner"]
        image = Shop.open_offer(context, slot, "Replace", REPLACE_TITLE)
        if image is None:
            return "handled"
        if (read := Shop.read_own_dialog(context, "shop: ", sinner, image)) is None:
            return "handled"
        choice = Shop.judge_replace(
            context, "shop: ", sinner, entry, read, "Cost", f", reserve {reserve}", swaps, "",
            lambda owned, cost: shop.skill_choice(entry, owned, read["lit"], read["prices"], cost, reserve, swaps))
        if isinstance(choice, str):
            return choice
        (swap, price), owned, cost = choice, read["owned"], read["cost"]
        if not Shop.pay_swap(context, "shop: ", sinner, swap, price, cost, "Cost"):
            return "handled"
        return Shop.cost_paid(context, "shop: ", sinner, swap, price, cost, owned, swaps)

    @staticmethod
    def pay_swap(context, head, sinner, swap, price, funds, unit, paying=None):
        """In an open Replace dialog (a slot's or ID Skill Search's): pick swap, Confirm, check the second layer, Confirm again
        and wait for the main page; True when the dialog left after the paying tap, False otherwise (each failure logs one
        line starting with head; the caller's to_main closes what is left open).

        funds: the top right's number (the Cost, or the owned starlight, #456); unit: what the second layer asks, "Cost" or
        "Starlight". paying(), when given, runs just before the paying tap: a visit marked there is not paid twice.
        """
        page_guard(context, "Shop")
        tap(context, *REPLACE_OPTIONS[swap], wait=0)
        if until(context, lambda im: shop.option_picked(im, REPLACE_FRAMES[swap]), timeout=1.0) is None:
            log(f"{head}{sinner!r}: {swap} did not light up: cancel")
            Shop.cancel_replace(context)
            return False
        page_guard(context, "Shop")
        ask = tap_shown(context, *REPLACE_CONFIRM, shows(context, REPLACE_ASK, rf"spend\s*\d+\s*{unit}"), timeout=2, rest=1.0)
        if ask is None:
            log(f"{head}{sinner!r}: no second confirm asking {unit}: back to the shop")
            return False
        # The second layer is checked twice before the paying tap: its "Spend N Cost" and its "350 ▸ 305" preview, which also
        # catches a Cost misread too high (that would spend into the reserve).
        asked, previewed = number(text(context, ask, REPLACE_ASK)), shop.dialog_price(funds, text(context, ask, REPLACE_PREVIEW))
        if asked != price or previewed != price:
            log(f"{head}{sinner!r}: the dialog asks {asked} and previews {previewed} off {funds}, not {price}: cancel")
            Shop.cancel_replace(context)
            return False
        page_guard(context, "Shop")
        if paying:
            paying()
        tap(context, *REPLACE_CONFIRM, wait=0)
        # No page_guard from here until the dialog is gone: CONNECTING shows (#453) where the global Connecting popup is
        # matched, and a guarded read would hand the shop back in the middle of the payment. Only the Cost is polled; under the
        # dialog SHOP_COST reads no digit, so the wait ends on the main page's number (a new one for Cost).
        landed = until(context, lambda im: cost_in(context, im) not in (None, funds), timeout=REPLACE_SETTLE)
        if landed is None and has(text(context, screen(context), DIALOG_TITLE), *REPLACE_MARK):
            log(f"{head}{sinner!r}: the dialog is still up {REPLACE_SETTLE} s after Confirm: the swap is not known")
            note_skills(sinner, None)
            page_guard(context, "Shop")  # a real Connecting popup: MirrorHub waits it out
            return False
        still(context, timeout=1.5)
        return True

    @staticmethod
    def cost_paid(context, head, sinner, swap, price, cost, owned, swaps):
        """After a swap paid in Cost: "replaced" when the main page's Cost dropped by the price, else "handled"; the run's
        counts follow only what the Cost proves (#455 graft 2)."""
        after = read_cost(context)
        if after == cost:
            log(f"{head}{sinner!r} {swap} for {price}: {cost} -> {after} Cost: the Cost did not change; taking it as not replaced")
            return "handled"
        if after is None or cost - after != price:
            log(f"{head}{sinner!r} {swap} for {price}: {cost} -> {after} Cost: the Cost "
                f"{'reads nothing' if after is None else f'dropped by {cost - after}'}, not the price: the counts are not known")
            note_skills(sinner, None)
            return "handled"
        sw = swaps[swap]
        log(f"{head}replaced {sinner!r} {swap} (skill {sw['from']} -> {sw['to']}) for {price}: {cost} -> {after} Cost")
        note_skills(sinner, shop.after_swap(owned, swap, swaps))
        return "replaced"

    @staticmethod
    def buy(context, team, visit):
        """Buy the gifts of the team's list on show (buy_offers), then refresh while the rules allow; True on any spend.

        A first choice too dear for the reserve becomes visit["wanted"] for the next round's sell, and
        holds the purchases and the refresh back until that sell has been tried. A list with nothing to buy (gifts.purchases:
        it wants nothing the shop sells, and no wanted fusion lacks a gift the shop sells) buys nothing and never refreshes
        (#298). What a wanted fusion lacks depends on the owned gifts: a visit that has not read them reads the sell page first.
        Each refresh asks again with what was bought since: none once the list buys nothing more.
        """
        keyword, reserve, acted = team["keyword"], team["reserve_cost"], False
        to_buy = buy_list(team, visit)
        if visit.get("owned") is None and any(f for _, f in to_buy):
            Shop.read_owned(context, team, visit)
            to_buy = buy_list(team, visit)
        if not to_buy:
            log("shop: the gift list buys nothing the shop sells (no wanted gift, no wanted fusion's material): nothing bought, no refresh")
            return False
        while True:
            if Shop.buy_offers(context, team, visit):
                acted = True
                visit["fuse_scanned"] = False  # a new gift: the fusion grid has changed
            if visit["wanted"] and not visit["sold"]:
                return True  # sell first, next round
            if not buy_list(team, visit):
                log("shop: what was bought meets the gift list (no wanted gift, no wanted fusion's material left): no refresh")
                return acted
            cost = read_cost(context)
            if cost is None:
                log("shop: the Cost reads nothing: no refresh")
                return acted
            image = screen(context)
            fees = {k: number(text(context, image, roi)) for k, (_, roi) in REFRESH.items()}
            limits = {"keyword": team["shop_refresh_keyword"], "normal": team["shop_refresh_normal"]}
            choice = shop.refresh_choice(cost, reserve, visit["refreshes"], limits,
                                         fees["normal"], fees["keyword"], data("shop.yaml")["refresh_margin"])
            if not choice:
                return acted
            page_guard(context, "Shop")
            if choice == "keyword":
                tap_settled(context, *REFRESH[choice][0])  # the keyword dialog zooms in
                if not tap_keyword(context, keyword):
                    log("shop: no keyword dialog on the refresh")
                    Shop.to_main(context)
                    return acted
                page_guard(context, "Shop")
                tap(context, *KEYWORD_REFRESH, wait=0)
            else:
                tap(context, *REFRESH[choice][0], wait=0)
            # The Cost drops, then the offers reload (CONNECTING): read them once both are done.
            until(context, lambda im: cost_in(context, im) not in (None, cost), timeout=3)
            still(context, timeout=1.5)
            after = read_cost(context)
            log(f"shop: {choice} refresh for {fees[choice]}: {cost} -> {after} Cost")
            if after == cost:
                Shop.to_main(context)
                return acted
            visit["refreshes"][choice] += 1
            visit["sold"] = False
            acted = True
            Shop.skill_step(context, team, visit)  # a refresh can put another sinner's slot up (#264 時機)

    @staticmethod
    def read_owned(context, team, visit):
        """Read the owned gifts off the sell page into visit["owned"] (note_owned); nothing is tapped but the page's button.
        It stays unknown when the page does not open."""
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["sell"], shows(context, DIALOG_TITLE, "Sell"), timeout=2) is not None:
            note_owned(team, visit, owned_cells(context, "sell")[0])
        Shop.to_main(context)

    @staticmethod
    def buy_offers(context, team, visit):
        """Read the offers once, then buy the ones of the team's list shop.buy_plan picks, last cell first; how many bought.

        A gift is told by its icon (read_cells, #297) and by its name plate (read_plates, #329): one vote is enough, two that
        differ leave the cell unknown. Only an offer whose id is known and that gifts.purchases names (the list wants it, or a
        wanted fusion lacks it: buy_list) is bought, in that order (#298); one bought for a fusion is logged with it. Each
        gift bought counts as owned (owned_change) for the next and after a refresh, unread owned gifts or not, so a fusion is
        bought no more than it lacks. A Not
        Enough Cost offer is dimmed (no icon read) but its plate reads: with its id it may be the first choice, so the shop
        sells for it; it is never bought. Every cell, Purchased ones too, is logged with its id. Each purchase is checked on
        the Cost.
        """
        gift_list, reserve = team["list"], team["reserve_cost"]
        to_buy = buy_list(team, visit)
        place, reason = {i: n for n, (i, _) in enumerate(to_buy)}, dict(to_buy)

        def why(i):
            return f" for fusion {reason[i]} {GIFT_NAMES.get(reason[i])}" if reason.get(i) else ""
        visit["wanted"] = None
        cost = read_cost(context)
        if cost is None:
            log("shop: the Cost reads nothing: nothing bought")
            return 0
        avoided = avoided_gifts(team)
        image = screen(context)
        scrolls = shop.is_super(image)  # a Super Shop's third row shows after a scroll (#341)
        if scrolls:
            image = Shop.drag_offers(context, down=False)
        shown = Shop.read_offers(context, image)
        if scrolls:
            for slot in shown:
                slot["page"] = 0
            lower = Shop.read_offers(context, Shop.drag_offers(context, down=True), shown)
            log(f"shop: Super Shop scrolled: {len(lower)} more offers")
            for slot in lower:
                slot["page"] = 1
            shown += lower
        slots = [s for s in shown if shop.on_sale(s)]
        avoid = [g["name"] for g in avoided]
        avoid_ids = [g["id"] for g in avoided]
        offers, ids = [], {}
        for i, slot in enumerate(slots):
            cell, plate = slot["cell"], slot["plate"]
            icon, (named, split) = cell["id"], gift_cells.vote(cell["id"], plate["id"])
            if split:
                log(f"shop: {slot['name']!r}: the icon says {icon} {GIFT_NAMES.get(icon)}, the plate {plate['text']!r} says "
                    f"{plate['id']} {GIFT_NAMES.get(plate['id'])}: unknown")
            cell = {**cell, "id": named, "by_plate": icon is None and named is not None}
            if cell["id"] in avoid_ids or any(rewards.names_gift(slot["name"], n) for n in avoid):
                log(f"shop: {slot['name']!r} {slot['price']}: {gift_shown(cell)}, the team does not hold it (#90)")
                continue
            if slot["short"] and slot["price"] <= cost:
                log(f"shop: {slot['name']!r} {gift_shown(cell)} is tagged Not Enough Cost: its price {slot['price']} is a misread")
                continue
            rank = place.get(cell["id"])
            listed = cell_state(cell, gift_list, owned_now(visit))
            log(f"shop: {slot['name']!r} {slot['price']}: tier {cell['tier']} {cell['keyword']} {gift_shown(cell)}, plate {plate['text']!r}, {listed}"
                f"{'' if rank is None else f', place {rank}{why(cell['id'])}'}")
            if rank is not None:
                offers.append((i, rank, slot["price"]))
                ids[i] = cell["id"]
        plan, visit["wanted"] = shop.buy_plan(offers, cost, reserve, visit["sold"])
        if visit["wanted"]:
            log(f"shop: the first choice costs {visit['wanted']}, {cost} Cost is short: sell first")
        bought = 0
        for i in plan:
            slot = slots[i]
            if ids[i] not in dict(buy_list(team, visit)):
                log(f"shop: {slot['name']!r} {ids[i]}: no longer needed, what was bought meets its fusion")
                continue
            image = Shop.open_offer(context, slot)
            if image is None:
                if not Shop.to_main(context):
                    return bought
                continue
            price = shop.dialog_price(cost, text(context, image, PURCHASE_PREVIEW)) or slot["price"]
            if not shop.can_spend(cost, price, reserve):
                tap_settled(context, *PURCHASE_CANCEL, timeout=1.0)
                log(f"shop: {slot['name']!r} costs {price}, {cost} Cost is short")
                continue
            page_guard(context, "Shop")
            tap(context, *PURCHASE, wait=0)
            gift_get(context)
            after = read_cost(context)
            log(f"shop: bought {slot['name']!r} for {price}{why(ids[i])}: {cost} -> {after} Cost")
            if after is None or after == cost:
                log("shop: the Cost did not change; taking it as not bought")
                Shop.to_main(context)
                continue
            cost, bought = after, bought + 1
            owned_change(visit, got=[ids[i]])
        return bought

    @staticmethod
    def drag_offers(context, down):
        """Drag the offer grid to its last rows (down) or back to its top; the screenshot once it rests (#341)."""
        top, height = OFFER_GRID[1], OFFER_GRID[3]
        scroll(context, OFFER_DRAG_X, top + height - 15 if down else top + 15, 0, -OFFER_DRAG_PX if down else OFFER_DRAG_PX)
        image = still(context, timeout=1.0)
        return screen(context) if image is None else image

    @staticmethod
    def read_offers(context, image, known=None):
        """The offers of the grid on image as slots (shop.read_slots) with their "plate", and on-sale ones their "cell" and "short".

        known: the offers read off the grid before it was scrolled (#341): those are left out, and so is a cut-off one.
        Bought ones, skills and "??" log their plate (#329).
        """
        shown = shop.read_slots(ocr(context, image, OFFER_GRID))
        if known is not None:
            shown = [s for s in shown if offer_whole(s["y"]) and not any(shop.same_offer(s, k) for k in known)]
        for slot, plate in zip(shown, read_plates(context, image, [offer_cell(s) for s in shown]), strict=True):
            slot["plate"] = plate
            if not shop.on_sale(slot):  # bought, a skill or "??": never bought, its plate logged (#329)
                log(f"shop: {slot['name']!r}: {'Purchased' if slot['purchased'] else 'not on sale'}, plate {plate['text']!r} "
                    + (gift_shown({"id": plate["id"], "by_plate": True, "score": 0.0}) if plate["id"] else "unknown"))
        on_sale = [s for s in shown if shop.on_sale(s)]
        cells = {c["i"]: c for c in read_cells(context, image, [offer_cell(s) for s in on_sale], "offer")}
        for i, slot in enumerate(on_sale):
            slot["cell"] = cells.get(i, {"tier": None, "keyword": None, "id": None, "score": 0.0})
            slot["short"] = slot["short"] or shop.short_cell(image, *offer_cell(slot))
        return shown

    @staticmethod
    def find_offer(context, slot):
        """slot as the grid shows it now, whole in the grid's box; None when it is not found there (#341).

        A Super Shop's grid may be anywhere (a purchase can put it back): the offer is looked for by its column, price and name,
        and the grid is dragged to the end its page is at (slot["page"]: 1 the last rows) until it shows whole.
        """
        for _ in range(3):
            found = next((s for s in shop.read_slots(ocr(context, screen(context), OFFER_GRID))
                          if shop.same_offer(s, slot) and offer_whole(s["y"])), None)
            if found:
                return {**slot, "x": found["x"], "y": found["y"]}
            Shop.drag_offers(context, down=slot["page"] == 1)
        log(f"shop: {slot['name']!r} {slot['price']} not found in the grid")
        return None

    @staticmethod
    def open_offer(context, slot, title="Purchase", roi=DIALOG_TITLE):
        """Tap an offer; the screenshot of the dialog it opens (title read in roi: a purchase's, or a skill replacement's), or
        None when none opened."""
        # Its text and Cost preview are read once it stops.
        page_guard(context, "Shop")
        if "page" in slot:  # a Super Shop's grid scrolls: the offer is brought into view and read back first (#341)
            slot = Shop.find_offer(context, slot)
            if slot is None:
                return None
        image = tap_shown(context, slot["x"], slot["y"] - 50, shows(context, roi, title), timeout=1.5, rest=1.0)
        if image is not None:
            return image
        log(f"shop: {slot['name']!r} opened no {title.lower()} dialog")
        return None

    @staticmethod
    def sell(context, team, visit):
        """Sell the materials no fusion uses (fusions' leftovers, #79) when a wanted gift is too dear.

        Only a gift the team's list lets go is sold (owned_cells, cell_role, #299): one it wants, keeps, a wanted fusion
        locks or whose icon is unknown stays. No cell is tapped but to sell it: the grid is scrolled for the cut-off rows (#205).
        """
        wanted = visit["wanted"]
        if not wanted or visit["sold"]:
            return False
        visit["sold"] = True
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["sell"], shows(context, DIALOG_TITLE, "Sell"), timeout=2) is None:  # the grid slides in
            Shop.to_main(context)
            return False
        cost = read_cost(context, SELL_COST)
        if cost is None:
            log("shop: the sell page's Cost reads nothing: nothing sold")
            Shop.to_main(context)
            return False
        # The grid decides (#112, #205): each cell's tier, badge and icon (its id), its price under it.
        avoid = [g["id"] for g in avoided_gifts(team)]
        cells, grid = owned_cells(context, "sell")
        owned = note_owned(team, visit, cells)
        roles = [cell_role(c, team, "sell", avoid, owned) for c in cells]
        # A pack-exclusive fusion the run did not pull does not lock its materials (#306), but the fuse page still makes it
        # (#300): what a held recipe takes is not sold, which runs before the fusion.
        held = recipe_places(team, cells, visit.get("slots", 3))
        roles = ["keep" if c["i"] in held else r for c, r in zip(cells, roles)]
        log("shop: sell cells " + "; ".join(f"{cell_line(c, f'{r}, {cell_state(c, team['list'], owned)}')} {c['price']}" for c, r in zip(cells, roles)))
        gifts = [(c["i"], c["price"]) for c, r in zip(cells, roles) if r == "material" and c["price"]]
        avoided = {c["i"] for c in cells if c["id"] in avoid}  # sold first (#90)
        # The fusion still uses what may not be sold (#79): a vestige the team does not sell (kept on the sell page, material
        # on the fuse page, #161), and a material whose price is unread.
        fuse_only = [c["i"] for c, r in zip(cells, roles) if c["i"] not in held
                     and ((r == "keep" and cell_role(c, team, "fuse", avoid, owned) == "material") or (r == "material" and not c["price"]))]
        # The fusion is grouped without the avoided gifts, which are sold first (#90): a sale then breaks no group.
        materials = [c for c in cells if (c["i"] in dict(gifts) or c["i"] in fuse_only) and c["i"] not in avoided]
        condition = team["list"]["fusion_condition"]  # a group the condition refuses makes no fusion: its gifts are spare
        fused = {i for group, _ in fusions(materials, ["material"] * len(materials), visit.get("slots", 3), (), condition) for i in group}
        # Up to the team's sell_max_tier only (#161); an unread tier may be a V: not sold.
        tiers, top = {c["i"]: c["tier"] for c in cells}, team.get("sell_max_tier", 4)
        spare = [g for g in gifts if g[0] not in fused and (tiers[g[0]] or 9) <= top]
        picked = shop.to_sell(spare, wanted, cost, team["reserve_cost"], avoided)
        visit["fuse_scanned"] = visit.get("fuse_scanned") and not picked
        log(f"shop: {wanted} wanted, {cost} Cost, materials (cell, price) {gifts}, {sorted(fused)} fuse: sell {picked}")
        # The Cost read before any cell was picked: a picked cell shows "51 > 146", read as 51146 (#174).
        before, by_i = cost, {c["i"]: c for c in cells}
        for i in picked or []:
            price = dict(gifts)[i]
            asked = Shop.ask_sale(context, grid, by_i[i], before)
            if asked is False:
                break
            if asked is not None:
                if not re.search(rf"(?<!\d){price}(?!\d)", normalize(text(context, asked, DIALOG_TEXT))):
                    log(f"shop: the sale of cell {i} asks another price than {price}: cancelled")  # another cell picked
                    tap_settled(context, *DIALOG_CANCEL, timeout=1.0)
                    break
                tap(context, *DIALOG_CONFIRM, wait=0)
            # Only before + price is a sale: the preview of an unconfirmed one reads as 51146 (#174).
            sold = until(context, lambda im: cost_in(context, im, SELL_COST) == before + price, timeout=2)
            if sold is None:
                log(f"shop: sell cell {i} for {price}: not sold, {before} -> {read_cost(context, SELL_COST)} Cost")
                break
            log(f"shop: sold cell {i} for {price}: {before} -> {before + price} Cost")
            owned_change(visit, gone=[by_i[i]["id"]])
            before += price
            still(context, timeout=1.5)  # the dialog goes as the Cost turns: the next cell's tap waits for it
            if grid["at"]:  # the grid lost a cell, and may have moved up from its end: from its top again
                grid_top(context, "sell")
                grid["at"] = 0
        Shop.to_main(context)
        return bool(picked)

    @staticmethod
    def ask_sale(context, grid, cell, before):
        """Tap cell (owned_cells) on the sell page, then Sell: the screenshot of the dialog that asks "Sell [<gift>] for
        <price> Cost?", None when none came, False when the cell is not where the grid puts it (cell_at).

        No dialog and the Cost still reads `before` with no dialog up: nothing was picked (a picked cell previews the Cost as
        "51 > 146", #174), so the cell tap was not taken (#611): the cell is found again and tapped once more, then Sell.
        A Cost that reads anything else may be a pick whose Sell tap was lost: a second cell tap would unpick it.
        """
        asks = shows(context, DIALOG_TEXT, r"Sell.*Cost")
        for again in (False, True):
            at = cell_at(context, grid, cell)
            if at is None:
                return False
            page_guard(context, "Shop")
            tap_settled(context, *at, timeout=1.2)
            # Sell's dialog slides down from the top before Confirm takes a tap (#174).
            page_guard(context, "Shop")
            asked = tap_shown(context, *PAGE_OK, asks, timeout=2)
            if asked is not None or again:
                return asked
            image = screen(context)
            if cost_in(context, image, SELL_COST) != before or asks(image):
                return None
            log(f"shop: sell cell {cell['i']} tapped: nothing picked, tapped again")

    @staticmethod
    def fuse(context, team, visit):
        """Fuse the materials shop.pick_fusion picks into the main keyword, Wishmaking left unticked; True when one fused.

        The cells are read off the grid, scrolled for the cut-off rows (owned_cells, #112, #205): the gifts the team's list
        lets go and whose icon is known are the materials, the rest stay (cell_role, #299). No cell is tapped but to put it in. Each material
        tapped in is read back (place); one that does not show closes the page unfused. The page stays open after a fusion
        (#378, as AALC's fuse_useless_gifts): the owned gifts are placed by the fusion (fused_cells: only the gift made is
        read), else read again there, and the next fusion made, a wanted one first, until none is left or FUSIONS_PER_PAGE
        were made; then the page is closed. A cell placed by the fusion that does not show where it was put (cell_at) closes
        the page and opens it again, its owned gifts read from the top: materials may be in.
        A grid that made none is not read again until a purchase or a sale changes the owned gifts (#62), or a recovery
        (forget_game_state, #459).
        """
        if visit.get("fuse_scanned"):
            return False
        keyword = team["keyword"]
        # The page zooms in: a tap before it stops is lost.
        page_guard(context, "Shop")
        if tap_shown(context, *SHOP_BUTTONS["fuse"], shows(context, DIALOG_TITLE, "Fuse"), timeout=2) is None:
            Shop.to_main(context)
            return False
        tap_settled(context, *FUSE_CENTRE)
        if not tap_keyword(context, keyword):
            log("shop: no keyword dialog on the fusion")
            Shop.to_main(context)
            return False
        tap_settled(context, *FUSE_KEYWORD_OK)
        image = screen(context)
        if image[495:515, 263:283].max(axis=2).mean() > 60:  # unticked: V ~30
            log("shop: Wishmaking is ticked (it spends owned Starlight): no fusion")
            Shop.to_main(context)
            return False
        visit["slots"] = slots = shop.fuse_slots(image)  # the sale needs it too
        if seen(context, image, "ShopFusionAvailable"):
            log("shop: the fuse page shows Fusion Available: the owned gifts are read under it")
        avoid = [g["id"] for g in avoided_gifts(team)]
        grid, cells, fusion, fused_any = None, None, None, False
        for _ in range(FUSIONS_PER_PAGE):
            cells = fused_cells(context, cells, grid, fusion) if fusion else None
            if cells is None:
                cells, grid = owned_cells(context, "fuse", grid)
            owned = note_owned(team, visit, cells)
            roles = [cell_role(c, team, "fuse", avoid, owned) for c in cells]
            log(f"shop: fuse cells ({slots} slots) " + "; ".join(cell_line(c, f"{r}, {cell_state(c, team['list'], owned)}") for c, r in zip(cells, roles)))
            made = Shop.fuse_recipe(context, team, cells, grid, slots, visit)  # a wanted fusion comes before the ordinary one (#300)
            fusion = made if made is False else made or Shop.fuse_ordinary(context, team, visit, cells, roles, slots, grid, avoid)
            if not fusion and misplaced(grid):
                log("shop: a cell placed by the fusion is not where it was put: the fuse page is opened again")
                Shop.to_main(context)
                return Shop.fuse(context, team, visit) or fused_any
            if made is False:  # the page did not take the recipe, and may hold some of its materials: close it, then the ordinary fusion
                Shop.to_main(context)
                return Shop.fuse(context, team, visit) or fused_any  # fuse_recipe put the recipe in visit["recipes_failed"]: it is not tried again
            # Nothing to fuse, unconfirmed, refused or not read back: not the same scan again until the owned gifts change (#103).
            visit["fuse_scanned"] = not fusion
            if not fusion:
                break
            fused_any = True
        else:
            log(f"shop: {FUSIONS_PER_PAGE} fusions on one fuse page: it is closed, the next round opens it again")
        Shop.to_main(context)
        return fused_any

    @staticmethod
    def fuse_ordinary(context, team, visit, cells, roles, slots, grid, avoid):
        """The ordinary fusion of the cells read, fusions' first group put in (place): the fusion made, {"gone": its cells,
        "tier": the GET! popup's numeral (shop.got_tier, #451; EX_TIER when it shows an EX gift, shop.ex_got, #449; the
        page's forecast's when unread, the points' when that is unread too), "gift": None}, for fused_cells. A group the
        page's forecast turns down comes out again and the next is tried, FUSE_TRIES at most (#285); False on none left."""
        condition = team["list"]["fusion_condition"]
        refused = []
        while True:
            picks = fusions(cells, roles, slots, avoid, condition, refused)
            if not picks:
                log(f"shop: {roles.count('material')} materials on show, a fusion takes {shop.MIN_FUSION}"
                    + ("" if condition == "any" else f", and none meets the condition {condition}")
                    + (f", {len(refused)} turned down by the page's forecast" if refused else ""))
                return False
            group, tier = picks[0]
            group = sorted((next(c for c in cells if c["i"] == i) for i in group), key=lambda c: -c["y"])  # the grid's end first
            materials = ", ".join(cell_line(c, "material").rsplit(":", 1)[0] for c in group)
            if not Shop.place(context, group, slots, grid):
                return False
            # The page's own forecast beats the points (#285): a tier the condition refuses is not fused, whichever table
            # the game used. An unread row falls back to the points tier, which pick_fusion already checked.
            page_tier, chance = read_forecast(context)
            wanted = page_tier is None or shop.fusion_wanted(condition, page_tier, [(c["i"], c["tier"]) for c in group])
            act = ("fuse on the points tier" if page_tier is None else "fuse") if wanted else "turned down"
            log(f"shop: fuse forecast {materials}: points tier {tier}, page tier {page_tier or 'unread'}, chance "
                f"{f'{chance}%' if chance else 'unread'}, condition {condition}: {act}")
            if wanted:
                popup = Shop.press_fuse(context, len(group))
                log(f"shop: fuse {materials} into a tier {page_tier or tier} {team['keyword']} gift (condition {condition}): {'not confirmed' if popup is None else 'done'}")
                if popup is None:
                    return False
                owned_change(visit, gone=[c["id"] for c in group])
                if shop.ex_got(popup):  # #449: a fusion short of its 99% gives an EX gift
                    log("shop: the GET! popup shows an EX gift (green EX): the gift made is placed as tier V")
                    return {"gone": group, "tier": EX_TIER, "gift": None}
                # #451: the tier's gifts all taken, the game may give another tier than the table's
                made, expected = shop.got_tier(popup), page_tier or tier
                forecast = ("the forecast's" if page_tier else "the points'") + f" tier {expected}"
                if made is None:
                    log(f"shop: the GET! popup shows no tier numeral: the gift made is placed as {forecast}")
                elif made != expected:
                    log(f"shop: the GET! popup shows tier {made}, not {forecast}: the gift made is placed as tier {made}")
                return {"gone": group, "tier": made or expected, "gift": None}
            refused.append(tuple(sorted(c["tier"] for c in group)))
            if len(refused) >= FUSE_TRIES or not Shop.place(context, group, slots, grid, out=True):
                return False  # the page is closed, which empties it too

    @staticmethod
    def press_fuse(context, count):
        """Press Fuse with `count` materials in and confirm it when the dialog counts as many: the GET! popup's screenshot
        (gift_get), None when it did not come."""
        # Read again on the still screenshot: the one that matched was taken while the dialog zoomed in.
        page_guard(context, "Shop")
        image = tap_shown(context, *PAGE_OK, shows(context, FUSE_CONFIRM, FUSE_COUNT), timeout=2)
        m = image is not None and re.search(FUSE_COUNT, text(context, image, FUSE_CONFIRM))
        if not (m and int(m[1]) == count):
            return None
        tap(context, *FUSE_DIALOG_CONFIRM, wait=0)  # gift_get waits for its GET!
        return gift_get(context)

    @staticmethod
    def fuse_recipe(context, team, cells, grid, slots, visit):
        """Fuse the wanted fusion the owned cells hold the materials of (gifts.recipe_fusion, #300): the fusion made when made
        ({"gone": its cells, "tier": the recipe's, "gift": its id}, for fused_cells), False when tried and not (the recipe is
        added to visit["recipes_failed"], so this visit does not try it again; not when a cell placed by the last fusion was
        not where it was put, cell_at: the page is opened again), None when the list has none to make (or the page cannot hold it).

        The page needs a keyword picked before it unlocks, but a recipe's result does not depend on it (#304): the page's
        keyword stays, and the materials go in as for an ordinary fusion, each read back (place). The page recognises the
        recipe by itself once they are in (its Forecasts row reads III Guaranteed 100%, logged). A tier other than the recipe's
        cancels the fusion unpressed: the materials come back out and the ordinary fusion goes on (#300). The dialog's count must
        be theirs. A recipe the page cannot hold (a Lunar Memory's 5 materials on 3 slots) is passed over for the next wanted one.
        """
        failed = visit.setdefault("recipes_failed", [])
        cells = [c for c in cells if not c.get("unselectable")]  # the page takes none of them in (#378)
        recipe = recipe_fusion(team["list"], [c["id"] for c in cells if c["id"] is not None], slots=slots, skip=failed)
        if recipe is None:
            return None
        group = pick_cells(cells, recipe["materials"])
        group.sort(key=lambda c: -c["y"])  # the grid's end first, as an ordinary fusion's
        names = ", ".join(cell_line(c, "material").rsplit(":", 1)[0] for c in group)
        if not Shop.place(context, group, slots, grid):
            if not misplaced(grid):
                failed.append(recipe["gift"])
            return False
        tier, chance = read_forecast(context)
        recipe_tier = GIFT_TIERS.get(recipe["gift"])
        # The row's tier must be the recipe's own (a recipe's result is fixed, #304): else the page did not take these materials
        # as the recipe, and Fuse is not pressed. Only the tier is compared: the row shows no product name to read. Unread, or
        # a recipe of tier V (shop.forecast_tier never reads one), it goes on: a recipe has no points tier to fall back on.
        cancel = tier is not None and recipe_tier is not None and recipe_tier <= shop.FUSION_TOP_TIER and tier != recipe_tier
        made = not cancel and Shop.press_fuse(context, len(group)) is not None
        if made:
            owned_change(visit, gone=recipe["materials"], got=[recipe["gift"]])
        if not made:
            failed.append(recipe["gift"])
        if cancel:
            Shop.place(context, group, slots, grid, out=True)  # the materials back out; if one stays, the caller closes the page
        log(f"shop: recipe fusion {recipe['gift']} {GIFT_NAMES.get(recipe['gift'])} from {names}: page tier {tier or 'unread'}, chance "
            f"{f'{chance}%' if chance else 'unread'}: "
            + (f"cancelled, the recipe is tier {recipe_tier}" if cancel else "done" if made else "not confirmed"))
        return made and {"gone": group, "tier": recipe_tier, "gift": recipe["gift"]}

    @staticmethod
    def place(context, cells, slots, grid, out=False):
        """Tap cells into the fusion, each read back (#77); False at the first that does not show, nothing put in before.

        Each is dragged into view first (cell_at). After a tap one slot more holds a material and the tapped cell's
        frame turns orange: the gift went in, and it is the one meant (cell_at found it, the grid is not sorted again).
        out: the other way round (#285), the materials in taken out again: one slot fewer, the frame gone.
        A tap that changed nothing (the slots and the cell's frame as before it) was not taken (#611: the game kept the cell
        pressed, 1 tap in 147 live, its touch_up sent 53 ms after touch_down; the release is lost in the game or the emulator,
        out of the bot's reach): once the screen stops it is read again, and still unchanged, the cell is found again and
        tapped once more. Any other read-back gives up at once: that tap may have been taken, and another would undo it.
        """
        def reads(image, x, y):  # the slots holding a material, and whether the cell at (x, y) is framed
            return shop.placed(image, slots), shop.picked(image, x, y, CELL_PAGES["fuse"][1])
        filled = shop.placed(screen(context), slots)
        if filled != (len(cells) if out else 0):
            log(f"shop: {filled} materials in before any tap: " + ("not the group to take out" if out else "no fusion"))
            return False
        for n, c in enumerate(cells, 1):
            meant, unchanged = (len(cells) - n, len(cells) - n + 1) if out else (n, n - 1)
            for again in (False, True):
                at = cell_at(context, grid, c)
                if at is None:
                    return False
                x, y = at
                page_guard(context, "Shop")
                tap_moved(context, x, y, timeout=0.5)
                filled, framed = reads(close_tooltip(context, "fuse", force=True), x, y)  # its tooltip shades the grid, still fading in maybe
                if filled == unchanged and framed == out and not again:
                    still(context, timeout=1.0)  # a tap taken late shows now: no second tap then
                    filled, framed = reads(close_tooltip(context, "fuse"), x, y)
                    if filled == unchanged and framed == out:
                        log(f"shop: cell {c['i']} tapped: nothing changed, tapped again")
                        continue
                if filled != meant or framed == out:
                    log(f"shop: cell {c['i']} tapped: {filled} materials in, {'framed' if framed else 'not framed'}: "
                        + ("not taken out" if out else "no fusion"))
                    return False
                break
        return True
