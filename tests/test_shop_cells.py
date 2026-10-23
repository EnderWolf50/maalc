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
SPIDERWEB = {"name": "Spiderweb Entangled in Red", "keyword": "Keywordless", "tier": 3}
HELLTERFLY = {"name": "Hellterfly's Dream", "keyword": "Burn", "tier": 2}

# name: (crop, the page's cells, the page, observed gifts[, the team holds White Gossypium])
CASES = {
    "fuse_spiderweb": ("fuse_spiderweb", "FUSE_CELLS", "fuse", [SPIDERWEB]),
    "fuse": ("fuse", "FUSE_CELLS", "fuse", [SPIDERWEB, HELLTERFLY]),
    "sell": ("sell", "SELL_CELLS", "sell", []),
    "offers": ("offers", "OFFER_CELLS", "offer", []),
    "offers_super": ("offers_super", "OFFER_CELLS", "offer", []),
    "fuse_no_gossypium": ("fuse", "FUSE_CELLS", "fuse", [], False),
    "sell_no_gossypium": ("sell", "SELL_CELLS", "sell", [], False),
    "fuse_tier_unread": ("fuse", "FUSE_CELLS", "fuse", []),  # cell 0's numerals dimmed (without_tier)
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
    """Run every case through actions.read_cells in a MaaFramework task; print {case: [(tier, keyword, gift)]}."""
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
                for case, (crop, cells, page, gifts, *allow) in CASES.items():
                    team = {"allow_white_gossypium": (allow or [True])[0]}
                    # The observed gifts', the vestiges' and White Gossypium's icons on every case (#161): on the offers too,
                    # where none is, as a sweep for false hits.
                    table = actions.gift_data()
                    observed = [{**g, "id": next(e["id"] for e in table if e["keyword"] == g["keyword"] and e["tier"] == g["tier"]
                                                 and e["en"] == g["name"])} for g in gifts]
                    vestiges = [{"name": n, "keyword": "Keywordless", "tier": t, "id": 9990 + t} for t, n in enumerate(actions.VESTIGES, 1)]
                    image = screen_with(crop)
                    if case == "fuse_tier_unread":
                        image = without_tier(image, *actions.FUSE_CELLS[0])
                    found = actions.read_cells(context, image, getattr(actions, cells), page,
                                               observed + actions.avoided_gifts(team) + vestiges)
                    out[case] = [(c["tier"], c["keyword"], c["gift"]) for c in found]
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


def test_spiderweb_is_kept_off_its_icon_with_no_tooltip(read):
    # #112, live 2026-10-18: the observed Spiderweb Entangled in Red (keywordless, III) first; its tooltip read no name.
    # Only 5 gifts owned: the empty cells are not read.
    assert read["fuse_spiderweb"] == [(3, "Keywordless", SPIDERWEB["name"]), (2, "Poise", None), (2, "Keywordless", None),
                                      (1, "Keywordless", None), (1, "Poise", None)]


OWNED = [  # ShopFuse.png's gifts, by the game data of the names their tooltips give
    (2, "Keywordless", "Faint Vestige"), (1, "Keywordless", "Dark Vestige"), (3, "Bleed", None),  # Smokes and Wires
    (2, "Burn", HELLTERFLY["name"]), (2, "Tremor", None),  # Hellterfly's Dream (observed), Sour Liquor Aroma
    (2, "Keywordless", None), (2, "Pierce", None), (2, "Keywordless", None),  # New Release Pamphlet, Gathering Skulls, Milepost
    (2, "Bleed", None), (2, "Keywordless", None),  # White Gossypium, Twinkling Scrap
    (2, None, None), (2, None, None), (2, None, None), (1, None, None), (1, None, None),  # the third row's badges are cut off
]


def test_the_fuse_page_cells_read_tier_badge_and_observed_icon(read):
    assert read["fuse"] == OWNED


def test_the_sell_page_cells_read_like_the_fuse_pages(read):
    # The same gifts on the sell page (another layout): the observed gift is not looked for here, the vestiges are.
    assert read["sell"] == [(t, k, g if g and "Vestige" in g else None) for t, k, g in OWNED]


def test_vestiges_are_told_by_their_icon_and_tier(read):
    # #161: the 5 vestige jars differ only in their fill (CCOEFF 0.5-0.86 on each other's), so the tier read off the
    # cell decides which; each scores 0.80-0.90 on its own. No other cell of these captures matches one (0.38 at most).
    assert [c[2] for c in read["fuse"][:2]] == ["Faint Vestige", "Dark Vestige"]
    assert not [c for case in ("fuse_spiderweb", "offers", "offers_super") for c in read[case] if c[2] and "Vestige" in c[2]]


def test_a_vestige_whose_tier_is_unread_is_not_named(read):
    # #161: every vestige's icon matches the Faint Vestige's cell (0.69-0.80); with no tier read none is taken.
    assert read["fuse_tier_unread"][0] == (None, "Keywordless", None)
    assert read["fuse_tier_unread"][1] == (1, "Keywordless", "Dark Vestige")


def test_white_gossypium_is_told_by_its_icon_for_a_team_that_does_not_hold_it(read):
    # #90: the 9th owned gift on both pages; no other cell takes its name.
    for case in ("fuse_no_gossypium", "sell_no_gossypium"):
        assert [c[2] for c in read[case]] == ["Faint Vestige", "Dark Vestige"] + [None] * 6 + ["White Gossypium"] + [None] * 6


def test_the_offers_read_tier_and_badge(read):
    # Shop.png: Ryōshū's skill, Rags, Plume of Proof, Temporal Bridle, Reverberation.
    assert read["offers"] == [(None, "Keywordless", None), (1, "Sinking", None), (2, "Pierce", None), (2, "Blunt", None),
                              (2, "Tremor", None)]
    # SuperShop.png: ID Skill Search, 2 skills, Special Catalogue; Fiery Down, Polarization, Pendant of Nostalgia,
    # Gemstone Oscillator.
    assert read["offers_super"] == [(None, "Keywordless", None)] * 3 + [
        (2, "Keywordless", None), (2, "Burn", None), (1, "Burn", None), (1, "Poise", None), (1, "Tremor", None)]


@pytest.mark.parametrize("name", LABELS)
def test_the_owned_gifts_are_found_under_their_label(read, name):
    # #205: "E.G.O Gifts Owned" read by OCR, OWNED_LABEL px over the first owned row, with a recipe's section over it or not.
    sys.path.insert(0, str(ROOT / "agent"))
    import actions  # noqa: PLC0415  # the pytest process's own import, for the constant
    assert abs(read[name] + actions.OWNED_LABEL - LABELS[name]) <= 3


if __name__ == "__main__":
    child()
