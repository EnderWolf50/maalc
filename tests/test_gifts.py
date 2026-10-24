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
    packs = args.get("run_packs")
    match case["fn"]:
        case "main_keyword":
            return gifts.main_keyword(gift_list)
        case "state":
            return {str(i): gifts.state(gift_list, i) for i in args["ids"]}
        case "effective":
            return {str(i): gifts.effective(gift_list, i, packs, tables) for i in args["ids"]}
        case "lockers":
            return {str(i): gifts.lockers(gift_list, i, packs, tables) for i in args["ids"]}
        case "queue":
            return gifts.queue(gift_list, tables)
        case "queue_summary":
            queue = gifts.queue(gift_list, tables)
            return {"first": queue[:3], "has_9083": 9083 in queue}
        case "recipe_fusion":
            return gifts.recipe_fusion(gift_list, args["owned"], tables, args.get("slots"))
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


