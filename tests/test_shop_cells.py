"""The shop's grid cells read by MaaFramework's own template matching (#76, #112), on live captures.

Shop.read_cells runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the badge
and icon templates, the green mask and the scores are the agent's on the device. The pytest process holds
MaaFramework in AgentServer mode (actions registers its custom actions), so the task runs in a child process:
this file run as a script, with AgentServer stubbed before actions is imported.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: shop, as pytest's pythonpath has it
from test_shop import screen_with  # noqa: E402

# name: (crop, the page's cells, the page). The icons (which gift) are read and checked in test_gift_cells.
CASES = {
    "fuse": ("fuse", "FUSE_CELLS", "fuse"),
    "sell": ("sell", "SELL_CELLS", "sell"),
    "offers": ("offers", "OFFER_CELLS", "offer"),
    "offers_super": ("offers_super", "OFFER_CELLS", "offer"),
    "fuse_tier_unread": ("fuse", "FUSE_CELLS", "fuse"),  # cell 0's numerals dimmed (without_tier)
}


# tests/screens fuse pages: the first owned row's centre y (#103: the Fusion Available section pushes it down).
LABELS = {"ShopFuse": 294, "ShopFuseRecipe": 427, "ShopFuseAvailable": 427, "ShopFuseRecipeTwo": 427, "ShopFuseLocked": 427}


def without_tier(image, x, y):
    """image with the yellow tier numerals of the cell at (x, y) dimmed: its tier reads None."""
    box = image[y - 44:y - 5, x - 44:x - 14]
    b, g, r = (box[:, :, i].astype(int) for i in range(3))
    box[(r > 200) & (g > 140) & (b < 90)] = 40
    return image


def child():
    """Run every case through actions.read_cells in a MaaFramework task; print {case: [(tier, keyword)]}."""
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

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # start_app, click, swipe, touch_*, keys, text, scroll: nothing moves
            return lambda *args: True

    out = {}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for case, (crop, cells, page) in CASES.items():
                    image = screen_with(crop)
                    if case == "fuse_tier_unread":
                        image = without_tier(image, *actions.FUSE_CELLS[0])
                    found = actions.read_cells(context, image, getattr(actions, cells), page)
                    out[case] = [(c["tier"], c["keyword"]) for c in found]
                for name in LABELS:  # #205: the fuse page's owned gifts found by their label's OCR
                    screen = np.array(Image.open(ROOT / "tests" / "screens" / f"{name}.png").convert("RGB"))[:, :, ::-1]
                    out[name] = actions.owned_label(context, np.ascontiguousarray(screen))[0]
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
    print(json.dumps(out))


@pytest.fixture(scope="module")
def read():
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return {k: [tuple(c) for c in v] if isinstance(v, list) else v for k, v in out.items()}


OWNED = [  # ShopFuse.png's gifts: tier and badge (the third row's badges are cut off by the list's edge)
    (2, "Keywordless"), (1, "Keywordless"), (3, "Bleed"), (2, "Burn"), (2, "Tremor"), (2, "Keywordless"), (2, "Pierce"),
    (2, "Keywordless"), (2, "Bleed"), (2, "Keywordless"), (2, None), (2, None), (2, None), (1, None), (1, None),
]


def test_the_fuse_page_cells_read_tier_and_badge(read):
    assert read["fuse"] == OWNED


def test_the_sell_page_cells_read_like_the_fuse_pages(read):
    # The same gifts on the sell page (another layout).
    assert read["sell"] == OWNED


def test_a_cell_whose_tier_is_unread_reads_none(read):
    # #161: cell 0's numerals dimmed.
    assert read["fuse_tier_unread"][0] == (None, "Keywordless")
    assert read["fuse_tier_unread"][1] == (1, "Keywordless")


def test_the_offers_read_tier_and_badge(read):
    # Shop.png: Ryōshū's skill, Rags, Plume of Proof, Temporal Bridle, Reverberation.
    assert read["offers"] == [(None, "Keywordless"), (1, "Sinking"), (2, "Pierce"), (2, "Blunt"), (2, "Tremor")]
    # SuperShop.png: ID Skill Search, 2 skills, Special Catalogue; Fiery Down, Polarization, Pendant of Nostalgia,
    # Gemstone Oscillator.
    assert read["offers_super"] == [(None, "Keywordless")] * 3 + [
        (2, "Keywordless"), (2, "Burn"), (1, "Burn"), (1, "Poise"), (1, "Tremor")]


@pytest.mark.parametrize("name", LABELS)
def test_the_owned_gifts_are_found_under_their_label(read, name):
    # #205: "E.G.O Gifts Owned" read by OCR, OWNED_LABEL px over the first owned row, with a recipe's section over it or not.
    sys.path.insert(0, str(ROOT / "agent"))
    import actions  # noqa: PLC0415  # the pytest process's own import, for the constant
    assert abs(read[name] + actions.OWNED_LABEL - LABELS[name]) <= 3


if __name__ == "__main__":
    child()
