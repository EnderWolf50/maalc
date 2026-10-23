"""Which gift a shop grid cell shows (#297, docs/spec/03-decisions.md section 13), free of MaaFramework.

actions.read_cells reads a cell's tier and keyword badge; the gifts of that keyword and tier are its candidates, and
their icons are matched on the cell. Everything here is plain data in, plain data out.
"""

import json
from pathlib import Path

from settings import SCHEMA

ROOT = Path(__file__).resolve().parent.parent
BASE = next(p for p in (ROOT / "resource" / "base", ROOT / "assets" / "resource" / "base") if p.is_dir())
TEMPLATES_DIR = BASE / "image"
VESTIGES = list(enumerate(SCHEMA["$defs"]["vestige"]["properties"]["name"]["enum"], 9991))  # [(id, name)], tier I-V
# CCOEFF score of an icon on its own cell and on another's: the gifts of the table's cells score 0.51-0.96, a gift the table
# lacks 0.30-0.38, a lookalike 0.54 at most with the gift covered (#297, docs/spec/03-decisions.md section 13)
ICON_MIN = 0.5
ICON_MARGIN = 0.1  # the best icon over the second best: a tie is two lookalikes, not a gift
ICON_SURE = 0.75  # an icon this good ends the matching of a cell's candidates: its lookalikes scored 0.66 at most


def load(data=BASE / "data"):
    """Every gift a cell may show: [{"id", "keyword", "tier", "en", "template"}], the template under image/.

    The shop's gifts (gift_search.json), the fusion gifts and their materials (gift_recipes.json) and the five vestiges.
    A gift the table lacks (a theme pack's exclusive one no recipe uses) is no candidate: its cell stays unknown.
    """
    search = json.loads((data / "gift_search.json").read_text(encoding="utf-8"))["gifts"]
    recipes = json.loads((data / "gift_recipes.json").read_text(encoding="utf-8"))
    table = [{**_entry(g), "template": f"GiftSearch/{g['id']}.png"} for g in search]
    table += [{**_entry(g), "template": f"GiftRecipe/{g['id']}.png"} for g in recipes["gifts"] + recipes["materials"]]
    table += [{"id": i, "keyword": "Keywordless", "tier": i - 9990, "en": n, "template": f"GiftSearch/{i}.png"} for i, n in VESTIGES]
    return table


def _entry(g):
    return {"id": g["id"], "keyword": g["keyword"], "tier": g["tier"], "en": g["en"]}


def candidates(table, keyword, tier):
    """The table's gifts of the cell's keyword and tier; none when either is unread (None)."""
    if keyword is None or tier is None:
        return []
    return [e for e in table if e["keyword"] == keyword and e["tier"] == tier]


def best(scores):
    """The id of the best [(id, icon score)] when it reaches ICON_MIN and leads the next by ICON_MARGIN, else None.

    None: no candidate's icon is on the cell (a gift the table lacks, a cell covered by a tooltip), or two are as good.
    """
    ranked = sorted(scores, key=lambda s: -s[1])
    if not ranked or ranked[0][1] < ICON_MIN or (len(ranked) > 1 and ranked[0][1] - ranked[1][1] < ICON_MARGIN):
        return None
    return ranked[0][0]
