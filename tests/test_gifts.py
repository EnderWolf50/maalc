import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import gifts

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((Path(__file__).parent / "gift_list_cases.json").read_text(encoding="utf-8"))


def run(case):
    """The call format of tests/gift_list_cases.json; gui/src/gifts.test.ts reads it the same way."""
    lists = [{"id": name, "name": name, **body} for name, body in CASES["lists"].items()]
    gift_list = gifts.resolve_list(case["list"], lists)
    if gift_list is None:
        return None
    args = case["args"]
    tables = None if args.get("data") == "real" else CASES["data"]
    packs, owned = args.get("run_packs"), args.get("owned", [])
    match case["fn"]:
        case "main_keyword":
            return gifts.main_keyword(gift_list)
        case "state":
            return {str(i): gifts.state(gift_list, i) for i in args["ids"]}
        case "effective":
            return {str(i): gifts.effective(gift_list, i, packs, owned, tables) for i in args["ids"]}
        case "lockers":
            return {str(i): gifts.lockers(gift_list, i, packs, owned, tables) for i in args["ids"]}
        case "queue":
            return gifts.queue(gift_list, tables)
        case "queue_summary":
            queue = gifts.queue(gift_list, tables)
            return {"first": queue[:3], "has_9083": 9083 in queue}
        case "purchases":
            return [list(p) for p in gifts.purchases(gift_list, packs, owned, tables)]
        case "fusion_purchases":
            return [list(p) for p in gifts.purchases(gift_list, packs, owned, tables) if p[1] is not None]
        case "purchases_summary":
            bought = gifts.purchases(gift_list, packs, owned, tables)
            ids = [i for i, _ in bought]
            return {"count": len(bought), "for_fusion": sum(f is not None for _, f in bought), "has": [i for i in args["ids"] if i in ids]}
        case "want_kind":
            return {str(i): gifts.want_kind(gift_list, i, packs, owned, tables) for i in args["ids"]}
        case "recipe_fusion":
            return gifts.recipe_fusion(gift_list, owned, tables, args.get("slots"))
    raise AssertionError(case["fn"])


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_shared_cases(case):
    """The GUI runs the same cases; both sides must agree on what a list makes of a gift."""
    assert run(case) == case["expect"]


def test_gifts_needs_no_maafw():
    """The shop, the other actions and the GUI's tests use it without the framework (#294)."""
    code = "import sys, gifts; assert not any(m == 'maa' or m.startswith('maa.') for m in sys.modules)"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "agent")}
    subprocess.run([sys.executable, "-c", code], env=env, check=True, capture_output=True)




def plain_list(**fields):
    import settings

    return {"order": list(settings.GIFT_KEYWORDS), "want": [], "keep": [], "gorder": settings.default_gorder(), **fields}


def test_a_tier_iv_gift_the_shop_sells_is_bought_when_wanted():
    # #626: Clear Mirror, Calm Water (9070, Poise IV) is not on the Gift Search page, but shops sell it.
    assert (9070, None) in gifts.purchases(plain_list(want=[9070]))
    assert (9070, None) in gifts.purchases(plain_list(want=[9070]), hard=False)


def test_a_gift_the_normal_floors_never_sell_is_bought_on_hard_only():
    # 9156 Decamillennial Hearthflame is in the drop pool's excludeEgoGifts: no NORMAL floor's shop shows it.
    wanted = plain_list(want=[9156])
    assert (9156, None) in gifts.purchases(wanted, hard=True)
    assert (9156, None) in gifts.purchases(wanted)  # the floor's difficulty unknown: any shop may
    assert gifts.purchases(wanted, hard=False) == []


def test_a_fusion_gift_and_a_globally_excluded_gift_are_never_bought():
    assert gifts.purchases(plain_list(want=[9207])) == []  # globalExcludeEgoGifts
    assert all(f is not None for _, f in gifts.purchases(plain_list(want=[9083])))  # Lunar Memory: only its materials, if any
