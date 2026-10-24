"""Which gift a shop grid cell shows (#297, docs/spec/03-decisions.md section 13), free of MaaFramework.

actions.read_cells reads a cell's tier and keyword badge; the gifts of that keyword and tier are its candidates, and
their icons are matched on the cell. Everything here is plain data in, plain data out.
"""

from run_start import match_pack
from settings import extra_gifts, gift_tables, vestiges
# CCOEFF score of an icon on its own cell and on another's: the gifts of the table's cells score 0.51-0.96, a gift the table
# lacks 0.30-0.38, a lookalike 0.54 at most with the gift covered (#297, docs/spec/03-decisions.md section 13)
ICON_MIN = 0.5
ICON_MARGIN = 0.1  # the best icon over the second best: a tie is two lookalikes, not a gift
ICON_SURE = 0.75  # an icon this good ends the matching of a cell's candidates: its lookalikes scored 0.66 at most


def load():
    """Every gift a cell may show: [{"id", "keyword", "tier", "en", "template"}], the template under image/.

    The shop's gifts (gift_search.json), the fusion gifts, their materials and the other gifts of the game data
    (gift_recipes.json) and the five vestiges. A gift of a newer client the table lacks is no candidate: its cell stays unknown.
    """
    search, fusions, materials = gift_tables()
    table = [{**_entry(g), "template": f"GiftSearch/{g['id']}.png"} for g in search]
    table += [{**_entry(g), "template": f"GiftRecipe/{g['id']}.png"} for g in fusions + materials + extra_gifts()]
    table += [{**_entry(g), "template": f"GiftSearch/{g['id']}.png"} for g in vestiges()]
    return table


def _entry(g):
    return {"id": g["id"], "keyword": g["keyword"], "tier": g["tier"], "en": g["en"]}


def candidates(table, keyword, tier):
    """The table's gifts of the cell's keyword and tier; none when either is unread (None)."""
    if keyword is None or tier is None:
        return []
    return [e for e in table if e["keyword"] == keyword and e["tier"] == tier]


def of_keyword(table, keyword, tier):
    """The table's gifts of the cell's keyword at any tier (#330): where a misread tier hides the cell's gift.

    Empty when the tier is unread (see candidates), or the badge: "Keywordless" is no badge found, which is also what a covered
    badge or a screen that is no shop reads (BattleTurnFocused's cell scored 0.51 on a gift), so it names no keyword.
    """
    if keyword in (None, "Keywordless") or tier is None:
        return []
    return [e for e in table if e["keyword"] == keyword]


def best(scores):
    """The id of the best [(id, icon score)] when it reaches ICON_MIN and leads the next by ICON_MARGIN, else None.

    None: no candidate's icon is on the cell (a gift the table lacks, a cell covered by a tooltip), or two are as good.
    """
    ranked = sorted(scores, key=lambda s: -s[1])
    if not ranked or ranked[0][1] < ICON_MIN or (len(ranked) > 1 and ranked[0][1] - ranked[1][1] < ICON_MARGIN):
        return None
    return ranked[0][0]


# The English name plate under every cell of the shop's buy page, dimmed (Not Enough Cost) and Purchased cells too (#329):
# a box 64 px under the cell's centre, 152 px wide and 26 high, one line. Relative to the centre, so a scrolled grid has it.
PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26


def plate_roi(x, y):
    """The OCR box [x, y, w, h] of the name plate of the cell centred at (x, y)."""
    return [x + PLATE_DX, y + PLATE_DY, PLATE_W, PLATE_H]


def name_id(text, ids):
    """The id of the gift whose English name `text` (a plate's OCR) stands for, else None; ids: {English name: id}.

    run_start.match_pack's bar (0.9, 0.04 ahead). A two-line name shows its first line only; a skill slot ("Replace ...
    Skill") is no gift's name.
    """
    name = match_pack(text, ids) if text else None
    return ids.get(name)


def vote(icon, name):
    """(the cell's id, whether the two disagreed) from the icon's id and the plate's id (None: unread).

    Both read and different: neither is trusted, the cell is unknown. One read: that one (a dimmed cell has no readable icon).
    """
    if icon is not None and name is not None and icon != name:
        return None, True
    return (icon if icon is not None else name), False
