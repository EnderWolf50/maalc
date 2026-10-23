"""A shop grid cell's gift id (#297): the candidates a cell's tier and badge leave, and the one its icon picks."""

import json
import os
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest

import gift_cells as g
import settings
from test_shop import screen_with

ROOT = Path(__file__).resolve().parent.parent


def test_a_cell_is_matched_against_the_gifts_of_its_keyword_and_tier():
    table = g.load()
    ids = lambda keyword, tier: {e["id"] for e in g.candidates(table, keyword, tier)}  # noqa: E731
    # Burn IV: the fusion gifts of data/gift_recipes.json and its fragment materials, none of Burn III's shop gifts.
    assert {9088, 9105} <= ids("Burn", 4) and 9053 not in ids("Burn", 4)
    assert 9053 in ids("Burn", 3)  # Dust to Dust, bought in the shop
    # the vestiges are Keywordless I-V, Lunar Memory the other Keywordless V
    assert ids("Keywordless", 5) == {9083, 9995, 9799, 9800}  # and two tier V gifts of the game data (#332)
    assert {9991} <= ids("Keywordless", 1)


def test_no_two_candidates_share_an_id_or_an_english_name():
    table = g.load()
    assert len({e["id"] for e in table}) == len(table)
    assert len({e["en"] for e in table}) == len(table)  # the name tag match (#329) needs a name to name one gift


def test_the_table_holds_every_named_gift_of_the_game_data_when_it_is_unpacked():
    # #332: ids 9000-9999 of the static data; only 9247 (no name, no icon sprite) is left out, so a new unnamed id fails here.
    from local_dir import local_dir  # noqa: PLC0415  # the pytest process only (the child below has no tools/ path)
    if not (unpack := local_dir("unpack")).joinpath("static").is_dir():
        pytest.skip("no unpacked game data")
    import gift_recipes  # noqa: PLC0415  # needs cv2, which CI's dev group lacks
    named = gift_recipes.english_names(unpack)
    ids = {i for i in gift_recipes.gift_table(unpack) if 9000 <= i <= 9999}
    assert ids - set(named) == {9247}
    assert {e["id"] for e in g.load()} == ids & set(named)


def test_a_cell_whose_tier_or_badge_is_unread_has_no_candidates():
    # Cut off by the grid's edge, or a skill: it is not a gift to name (kept as unknown).
    table = g.load()
    assert g.candidates(table, None, 2) == [] and g.candidates(table, "Burn", None) == []


def test_every_candidate_has_an_icon_template_in_the_bundle():
    assert all((settings.data_dir().parent / "image" / e["template"]).is_file() for e in g.load())


def test_the_best_icon_over_the_minimum_names_the_cell():
    scores = [(9042, 0.77), (9234, 0.30)]
    assert g.best(scores) == 9042
    assert g.best([(9128, g.ICON_MIN - 0.01)]) is None  # a gift the table lacks scores low on every candidate
    assert g.best([]) is None


def test_two_icons_that_both_match_leave_the_cell_unknown():
    # Hellterfly's Dream under a tooltip's banner, its badge covered (read Keywordless): Swift Command 0.54 and Late-bloomer's
    # Tattoo 0.53 are neither the gift; a tie is no answer.
    assert g.best([(9769, 0.54), (9026, 0.53)]) is None
    assert g.best([(9769, 0.62), (9026, 0.50)]) == 9769  # 0.12 ahead


def fake_context(scores, seen=None):
    """A context whose run_recognition scores each template by `scores` ({template: score}), 0 for any other; it
    appends the templates asked for to `seen`."""
    def run_recognition(name, image, override):
        node = override[name]
        if seen is not None:
            seen.append(node["template"])
        score = scores.get(node["template"], 0.0)
        return types.SimpleNamespace(best_result=types.SimpleNamespace(score=score))
    return types.SimpleNamespace(run_recognition=run_recognition)


def test_a_cell_takes_only_an_icon_of_its_own_keyword_and_tier():
    import actions  # noqa: PLC0415  # the pytest process's own import
    grid = np.zeros((200, 200, 3), np.uint8)
    icons = {"GiftSearch/9001.png": 0.9, "GiftSearch/9156.png": 0.4}  # Hellterfly's Dream, Decamillennial Heart: Burn II
    assert actions.cell_id(fake_context(icons), grid, (100, 100), "Burn", 2) == (9001, 0.9)
    # the same icon on a Pierce II cell is a lookalike, not a Burn gift: the cell is unknown
    assert actions.cell_id(fake_context(icons), grid, (100, 100), "Pierce", 2)[0] is None
    assert actions.cell_id(fake_context({"GiftSearch/9001.png": 0.9}), grid, (100, 100), "Burn", None) == (None, 0.0)


def test_matching_stops_at_an_icon_that_cannot_be_a_lookalike():
    import actions  # noqa: PLC0415
    seen = []
    context = fake_context({"GiftSearch/9001.png": 0.9}, seen)
    assert actions.cell_id(context, np.zeros((200, 200, 3), np.uint8), (100, 100), "Burn", 2) == (9001, 0.9)
    burn_ii = [e["template"] for e in g.candidates(actions.GIFTS, "Burn", 2)]
    assert seen == burn_ii[:burn_ii.index("GiftSearch/9001.png") + 1] and len(seen) < len(burn_ii)


def test_a_cell_log_line_names_the_gift_or_says_unknown():
    import actions  # noqa: PLC0415
    cell = {"i": 2, "tier": 3, "keyword": "Bleed", "gift": None, "id": 9042, "score": 0.77}
    assert actions.cell_line(cell, "keep") == "2 III Bleed 9042 Smokes and Wires (0.77): keep"
    assert actions.cell_line({**cell, "id": None, "score": 0.38}, "keep") == "2 III Bleed unknown (best 0.38): keep"


# --- The ids on live captures, read by MaaFramework itself (the setup of test_shop_cells.py) -------------------------

FUSE, SELL, OFFER = "FUSE_CELLS", "SELL_CELLS", "OFFER_CELLS"
RECIPE_CELLS = [(678 + 96 * c, 427) for c in range(5)] + [(678, 293)]  # a fuse page with a recipe on offer: owned gifts at y 427
CASES = {  # name: (crop under tests/shop, the page's cells, the page)
    "fuse": ("fuse", FUSE, "fuse"), "fuse_spiderweb": ("fuse_spiderweb", FUSE, "fuse"), "fuse_recipe": ("fuse_recipe", RECIPE_CELLS, "fuse"),
    "fuse_tooltip": ("fuse_tooltip", FUSE, "fuse"),
    "sell": ("sell", SELL, "sell"), "offers": ("offers", OFFER, "offer"), "offers_super": ("offers_super", OFFER, "offer"),
    "offers_red": ("offers_red", OFFER, "offer"), "offers_short": ("offers_short", OFFER, "offer"),
}


def child():
    """Print {"cases": {case: [id]}, "sweep": {"<capture> <page>": [[cell, id]]}}: read_cells on the crops, and on every
    tests/screens capture at the three layouts (a capture whose cells show no tier cannot name a gift: not read)."""
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

        def __getattr__(self, name):  # start_app, click, swipe, touch_*, keys, text, scroll: nothing moves
            return lambda *args: True

    out = {"cases": {}, "sweep": {}}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for case, (crop, cells, page) in CASES.items():
                    found = actions.read_cells(context, screen_with(crop), cells if isinstance(cells, list) else getattr(actions, cells), page)
                    out["cases"][case] = [c["id"] for c in found]
                for path in sorted((ROOT / "tests" / "screens").glob("*.png")):
                    image = np.ascontiguousarray(np.array(Image.open(path).convert("RGB"))[:, :, ::-1])
                    for cells, page in ((FUSE, "fuse"), (SELL, "sell"), (OFFER, "offer")):
                        cells, scale = getattr(actions, cells), actions.CELL_PAGES[page][0]
                        if not any(shop.filled(image, x, y) and shop.tier(shop.cell_crop(image, x, y, scale)) for x, y in cells):
                            continue
                        found = actions.read_cells(context, image, cells, page)
                        if any(c["id"] for c in found):
                            out["sweep"][f"{path.stem} {page}"] = [[c["i"], c["id"]] for c in found if c["id"]]
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
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "agent"), str(ROOT / "tests")])}
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT, env=env)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


# Each gift is named by its tooltip, its shop line or the game's icon (read by eye against image/GiftSearch and GiftRecipe).
OWNED = [9992, 9991, 9042, 9001, 9113, 9186, 9030, 9080, 9020, 9707]  # Faint and Dark Vestige, Smokes and Wires, Hellterfly's
# Dream, Sour Liquor Aroma, New Release Pamphlet, Gathering Skulls, Milepost of Survival, White Gossypium, Twinkling Scrap
# The third row's badges are cut off by the list's edge: it is read after a drag (owned_cells), not here.
NO_BADGE = [None] * 5


@pytest.mark.parametrize("case, ids", [
    ("fuse", OWNED + NO_BADGE),
    ("sell", OWNED + NO_BADGE),  # the same gifts, the sell page's layout
    ("fuse_spiderweb", [9273, 9046, 9007, 9017, 9128]),  # Spiderweb Entangled in Red (thin lines: 0.54-0.64), Cigarette Holder, ...
    ("offers", [None, 9123, 9198, 9150, 9086]),  # a skill, Rags, Plume of Proof, Temporal Bridle, Reverberation
    ("offers_super", [None, None, None, 9187, 9009, 9102, 9063, 9163]),  # Special Catalogue, Fiery Down, Polarization, Pendant ...
    ("offers_red", [None, 9125, 9105, 9040, 9140]),  # Distant Star, Fragment of Hellfire (IV), Tomorrow's Fortune, Resolution
])
def test_a_cell_is_named_by_its_icon_on_each_page(read, case, ids):
    assert read["cases"][case] == ids


def test_a_pack_exclusive_gift_is_named_and_a_cell_with_no_tier_read_is_unknown(read):
    # Fuse page with a recipe on offer: a tier IV Poise globe (Clear Mirror, Calm Water) and a tier IV Keywordless paper
    # (Non-disclosure Agreement) were unknown until #332 listed every gift of the game data; the Fusion Available cell is Cask Spirits (IV).
    assert read["cases"]["fuse_recipe"] == [9991, 9070, 9085, 9073, 9109, 9180]
    # Offers dimmed by Not Enough Cost show no tier (the numerals fade): nothing is named, all are kept.
    assert read["cases"]["offers_short"] == [None] * 5


def test_a_cell_under_a_tooltip_is_unknown_and_its_neighbours_are_not_taken_for_it(read):
    # Hellterfly's Dream (cell 3) and Sour Liquor Aroma (4) under a tooltip's banner, their badges covered (read as no badge:
    # Keywordless): the icons of Keywordless gifts score 0.54 and 0.36 on them, a lookalike pair 0.54 and 0.53 (Swift Command,
    # Late-bloomer's Tattoo). The cells the banner leaves alone are named: Gathering Skulls (6) at 0.78 under its edge.
    assert read["cases"]["fuse_tooltip"][:8] == [9992, 9991, 9042, None, None, 9186, 9030, 9080]


def test_no_other_capture_names_a_gift(read):
    # Every tests/screens capture at the three layouts (a false id on a gift-less screen would fail here).
    assert read["sweep"] == {
        "Shop offer": [[1, 9123], [2, 9198], [3, 9150], [4, 9086]],
        "ShopFuse fuse": [[i, gift] for i, gift in enumerate(OWNED)],
        # #304: the Fusion Available cell (cell 0) is Reminiscence (III) on both, the real captures of a fixed recipe on offer.
        "ShopFuseAvailable fuse": [[0, 9179]],
        "ShopFuseRecipeTwo fuse": [[0, 9179]],
        "SuperShop offer": [[3, 9187], [4, 9009], [5, 9102], [6, 9063], [7, 9163]],
    }


if __name__ == "__main__":
    child()
