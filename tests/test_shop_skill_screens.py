"""Skill replacement (#455) read off the real captures (#453's, tests/screens/ShopReplaceSkill*.png): the slot's sinner, the
dialog's Skills Owned, Cost, prices and lit options, the second layer, and the way back to the shop's main page.

One MaaFramework child runs every read (the OCR model fetched by tools/fetch_ocr.py); the flow is test_shop_skill.
"""

import json
import os
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SLOTS = ["Shop", "SuperShop", "ShopReplaceSkillCancelled", "ShopReplaceSkillDone", "ShopReplaceSkillRefreshed",
         "ShopReplaceSkillClippedMeursault", "ShopReplaceSkillClippedGregor"]
FIRST_LAYER = ["ShopReplaceSkillAll", "ShopReplaceSkillDimmed", "ShopReplaceSkillPickedLeft", "ShopReplaceSkillPickedMiddle",
               "ShopReplaceSkillPickedRight"]
SECOND_LAYER = ["ShopReplaceSkillConfirm", "ShopReplaceSkillConnecting"]
WAY_OUT = [*FIRST_LAYER, *SECOND_LAYER, "ShopPurchase", "Shop", "ShopReplaceSkillDone"]


def child():
    """Print what the agent reads off each capture (the keys of `out`), every read by the production functions."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker
    from PIL import Image

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions
    import shop

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # click, swipe, touch_*: nothing moves
            return lambda *args: True

    def capture(name):
        return np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / f"{name}.png").convert("RGB"))[:, :, ::-1])

    out = {"error": None, "slots": {}, "dialog": {}, "texts": {}, "ask": {}, "way_out": {}, "shop_cost": {}, "nodes": {}, "mark_sweep": []}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for name in SLOTS:
                    slots = shop.skill_slots(shop.read_slots(actions.ocr(context, capture(name), actions.OFFER_GRID)))
                    out["slots"][name] = [[s["name"], s["sinner"], s["purchased"]] for s in slots]
                for name in FIRST_LAYER:
                    image = capture(name)
                    out["dialog"][name] = actions.Shop.read_replace_dialog(context, image)
                    out["texts"][name] = {roi: actions.text(context, image, getattr(actions, roi))
                                          for roi in ("REPLACE_TITLE", "REPLACE_OWNED", "DIALOG_TITLE")}
                for name in SECOND_LAYER:
                    image = capture(name)
                    out["ask"][name] = [actions.number(actions.text(context, image, actions.REPLACE_ASK)),
                                        shop.dialog_price(350, actions.text(context, image, actions.REPLACE_PREVIEW))]
                    out["texts"][name] = {"DIALOG_TITLE": actions.text(context, image, actions.DIALOG_TITLE)}
                for name in WAY_OUT:
                    at = actions.Shop.way_out(context, capture(name))
                    out["way_out"][name] = list(at) if isinstance(at, tuple) else at
                for name in FIRST_LAYER + SECOND_LAYER:
                    image = capture(name)
                    out["shop_cost"][name] = actions.cost_in(context, image)
                    out["nodes"][name] = [n for n in ("Shop", "Connecting") if actions.seen(context, image, n)]
                for path in sorted((ROOT / "tests" / "screens").glob("*.png")):
                    image = np.ascontiguousarray(np.array(Image.open(path).convert("RGB"))[:, :, ::-1])
                    if image.shape[:2] == (720, 1280) and actions.has(actions.text(context, image, actions.DIALOG_TITLE), *actions.REPLACE_MARK):
                        out["mark_sweep"].append(path.stem)
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return True

    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    resource.register_custom_action("Probe", Probe())
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    tasker.post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    print(json.dumps(out, ensure_ascii=False))


@pytest.fixture(scope="module")
def read():
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "agent"), str(ROOT / "tests")])}
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=ROOT, env=env)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_a_replacement_slot_names_its_sinner_and_whether_it_was_bought(read):
    # Shop.png (1.117.0): Ryōshū's slot first; #453's shop: Gregor's before the swap, Purchased after it and after the refresh;
    # SuperShop.png: two slots, Gregor's read once though its "??" reads as two lines, and ID Skill Search is none of them.
    assert read["slots"] == {"Shop": [["Replace Ryōshū's Skill", "Ryōshū", False]],
                             "SuperShop": [["Replace Gregor's Skill", "Gregor", False], ["Replace Don Quixote's Skill", "Don Quixote", False]],
                             "ShopReplaceSkillCancelled": [["Replace Gregor's Skill", "Gregor", False]],
                             "ShopReplaceSkillDone": [["Replace Gregor's Skill", "Gregor", True]],
                             "ShopReplaceSkillRefreshed": [["Replace Gregor's Skill", "Gregor", True]],
                             # the OCR clips the tail of the name ("Skil"): the slot is still found (#455 live acceptance, floors 1 and 5)
                             "ShopReplaceSkillClippedMeursault": [["Replace Meursault's Skil", "Meursault", False]],
                             "ShopReplaceSkillClippedGregor": [["Replace Gregor's Skil", "Gregor", False]]}


DON_QUIXOTE = {"sinner": "Don Quixote", "owned": [3, 2, 1], "cost": 534, "prices": {"s1_s2": 45, "s2_s3": 75, "s1_s3": 120},
               "lit": {"s1_s2": True, "s2_s3": True, "s1_s3": True}}
GREGOR = {"sinner": "Gregor", "owned": [3, 2, 0], "cost": 350, "prices": {"s1_s2": 45, "s2_s3": 75, "s1_s3": 120},
          "lit": {"s1_s2": True, "s2_s3": False, "s1_s3": False}}  # skill 3 locked under Uptie 3: 75 and 120 dim


@pytest.mark.parametrize("name, dialog", [
    ("ShopReplaceSkillAll", DON_QUIXOTE), ("ShopReplaceSkillDimmed", GREGOR), ("ShopReplaceSkillPickedLeft", GREGOR),
    ("ShopReplaceSkillPickedMiddle", DON_QUIXOTE), ("ShopReplaceSkillPickedRight", DON_QUIXOTE),
])
def test_the_dialog_reads_the_sinner_the_counts_the_cost_the_prices_and_which_are_lit(read, name, dialog):
    # The 15-px "SKILL 1x3 SKILL 2x2 SKILL 3x1" line reads (OCR gives "SKILL1x3  SKILL2x2  SKILL3x1"), as do the 3-digit Costs.
    assert read["dialog"][name] == dialog


def test_the_second_layer_asks_the_price_and_previews_the_cost_after_it(read):
    # Gregor's s1_s2: "Spend 45 Cost to replace this Skill?" and "350 ▸ 305", also under CONNECTING.
    assert read["ask"] == {"ShopReplaceSkillConfirm": [45, 45], "ShopReplaceSkillConnecting": [45, 45]}


def test_the_way_back_to_the_main_page_cancels_the_dialog_on_both_layers(read):
    cancel = list((507, 542))  # REPLACE_CANCEL
    assert read["way_out"] == {**{name: cancel for name in [*FIRST_LAYER, *SECOND_LAYER]}, "ShopPurchase": [525, 482],
                               "Shop": "main", "ShopReplaceSkillDone": "main"}


def test_the_dialog_is_told_by_its_counts_line_inside_the_dialog_title_box(read):
    # REPLACE_MARK: DIALOG_TITLE reads "Gregor's Skill Skills Owned SKILL1x3  SKILL2x2 SKILL3x0" on both layers. The sweep over
    # every 1280x720 capture of tests/screens (CODING_STANDARDS): only the 7 dialog captures read it, and #456's 6 captures of
    # the ID Skill Search dialog, the same dialog on both layers (its title also reads "Replace <sinner>'s Skill").
    id_skill_search = ["ShopIdSkillSearchAll", "ShopIdSkillSearchConfirm", "ShopIdSkillSearchConnecting", "ShopIdSkillSearchDialog",
                       "ShopIdSkillSearchPicked", "ShopIdSkillSearchStarlight"]
    assert read["mark_sweep"] == [*id_skill_search, "ShopReplaceSkillAll", "ShopReplaceSkillConfirm", "ShopReplaceSkillConnecting",
                                  "ShopReplaceSkillDimmed", "ShopReplaceSkillPickedLeft", "ShopReplaceSkillPickedMiddle",
                                  "ShopReplaceSkillPickedRight"]


def test_the_main_pages_cost_box_reads_no_digit_under_the_dialog(read):
    # The final Confirm waits for SHOP_COST to read a new number: under the dialog it reads none, so the wait ends on the
    # main page.
    assert read["shop_cost"] == {name: None for name in [*FIRST_LAYER, *SECOND_LAYER]}


def test_the_shop_node_reads_under_the_dialog_and_connecting_hits_after_the_final_confirm(read):
    # MirrorHub's Shop node (Leave) still reads under both layers, so a hand-back mid-dialog finds the shop and to_main
    # cancels it. CONNECTING after the final Confirm hits the global Connecting popup: page_guard would hand the shop back
    # there, which is why the payment's wait runs without it (#455).
    assert read["nodes"] == {**{name: ["Shop"] for name in [*FIRST_LAYER, "ShopReplaceSkillConfirm"]},
                             "ShopReplaceSkillConnecting": ["Shop", "Connecting"]}


if __name__ == "__main__":
    child()
