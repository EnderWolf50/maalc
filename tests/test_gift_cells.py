"""A shop grid cell's gift id (#297): the candidates a cell's tier and badge leave, and the one its icon picks."""

import json
import os
import subprocess
import sys
import time
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
    pytest.importorskip("cv2", reason="cv2 is in the unpack group: `uv sync --group unpack` to run this check")
    import gift_recipes  # noqa: PLC0415
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


def test_the_name_plate_of_a_cell_is_read_in_a_box_under_its_centre():
    # #329: 64 px under the centre, 152 wide and 26 high, relative to the centre: a scrolled grid has it just the same (#341).
    assert g.plate_roi(624, 265) == [548, 329, 152, 26]
    assert g.plate_roi(100, 50) == [24, 114, 152, 26]


def test_a_plate_names_the_gift_it_reads_and_a_non_gift_or_a_slip_names_none():
    ids = {e["en"]: e["id"] for e in g.load()}
    assert g.name_id("Arrested Hymn", ids) == 9106
    assert g.name_id("Arrested Hymm", ids) == 9106  # one letter off: 0.9 and 0.04 ahead pass
    assert g.name_id("Recollection of Certain", ids) == 9177  # a two-line name: only its first line fits the box
    assert g.name_id("Replace Gregor's Skill", ids) is None  # a skill slot is no gift
    assert g.name_id("", ids) is None


def test_the_icon_and_the_plate_each_vote_and_a_disagreement_is_unknown():
    assert g.vote(9053, 9053) == (9053, False)
    assert g.vote(9053, None) == (9053, False)  # one vote is enough
    assert g.vote(None, 9053) == (9053, False)  # a dimmed cell: the icon unread
    assert g.vote(None, None) == (None, False)
    assert g.vote(9053, 9009) == (None, True)  # two different gifts: neither is trusted


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


def test_a_misread_tier_is_made_up_by_matching_the_whole_keyword():
    import actions  # noqa: PLC0415
    grid = np.zeros((200, 200, 3), np.uint8)
    # Smokes and Wires is Bleed III, read as II (sell page, the tier numeral cut short): no Bleed II icon is on the cell.
    icons = {"GiftSearch/9042.png": 0.9}
    assert actions.cell_id(fake_context(icons), grid, (100, 100), "Bleed", 2) == (9042, 0.9)
    # still nothing when the keyword's other tiers do not show it either, or when no tier was read at all
    assert actions.cell_id(fake_context({}), grid, (100, 100), "Bleed", 2)[0] is None
    assert actions.cell_id(fake_context(icons), grid, (100, 100), "Bleed", None) == (None, 0.0)


def test_the_keyword_fallback_never_overrules_a_cell_its_tier_names():
    import actions  # noqa: PLC0415
    grid = np.zeros((200, 200, 3), np.uint8)
    # Dark (I) and Faint (II) Vestige are one jar, only the fill differs: the cell read as I is Dark even where Faint's icon scores more.
    seen = []
    assert actions.cell_id(fake_context({"GiftSearch/9991.png": 0.8, "GiftSearch/9992.png": 0.85}, seen), grid, (100, 100), "Keywordless", 1)[0] == 9991
    tier_one = {e["template"] for e in g.candidates(actions.GIFTS, "Keywordless", 1)}
    assert "GiftSearch/9992.png" not in seen and set(seen) <= tier_one  # the fallback was not consulted
    # a tier-III cell without a badge is not matched against the jars of the other tiers: Keywordless is no badge read
    assert actions.cell_id(fake_context({"GiftSearch/9991.png": 0.8, "GiftSearch/9992.png": 0.78}), grid, (100, 100), "Keywordless", 3)[0] is None
    # a read badge's other tiers all score: two as good as each other leave the cell unknown instead of picking one
    assert actions.cell_id(fake_context({"GiftSearch/9042.png": 0.8, "GiftSearch/9048.png": 0.78}), grid, (100, 100), "Bleed", 2)[0] is None


def test_the_fallback_also_scores_the_candidates_an_early_stop_skipped():
    import actions  # noqa: PLC0415
    a, b, c = (e["template"] for e in g.candidates(actions.GIFTS, "Burn", 2)[:3])
    # a 0.70 and b 0.76 stop the first pass 0.06 apart (unknown); c, never reached there, is the 0.90 gift
    found = actions.cell_id(fake_context({a: 0.70, b: 0.76, c: 0.90}), np.zeros((200, 200, 3), np.uint8), (100, 100), "Burn", 2)
    assert found == (int(c.split("/")[1].split(".")[0]), 0.90)


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


PLATE_CASES = ["offers", "offers_super", "offers_red", "offers_short"]


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

    out = {"cases": {}, "sweep": {}, "plates": {}, "plate_sweep": {}, "plate_ms": [], "page_ms": [], "short_prices": {}}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for case, (crop, cells, page) in CASES.items():
                    found = actions.read_cells(context, screen_with(crop), cells if isinstance(cells, list) else getattr(actions, cells), page)
                    out["cases"][case] = [c["id"] for c in found]
                actions.ocr(context, screen_with("offers"), actions.OFFER_GRID)  # the agent's order: a det+rec pass reads before any plate
                first = actions.Shop.read_offers(context, screen_with("offers_super"), [])  # a Super Shop at rest, then scrolled (#341)
                more = actions.Shop.read_offers(context, screen_with("offers_super_scrolled"), [], first)
                out["super"] = [[[s["name"], s["price"], s["plate"]["id"], s["cell"]["id"] if "cell" in s else None] for s in page]
                                for page in (first, more)]
                for case in PLATE_CASES:  # the offers' name plates (#329), one per filled cell
                    image = screen_with(case)
                    cells = [(x, y) for x, y in actions.OFFER_CELLS if shop.filled(image, x, y)]
                    started = time.perf_counter()
                    actions.ocr(context, image, actions.OFFER_GRID)  # one det+rec pass over the page, for the bound of the plate time
                    out["page_ms"].append((time.perf_counter() - started) * 1000 / len(cells))
                    started = time.perf_counter()
                    plates = actions.read_plates(context, image, cells)
                    out["plate_ms"].append((time.perf_counter() - started) * 1000 / len(cells))
                    out["plates"][case] = [[i, p["text"], p["id"]] for i, p in enumerate(plates)]
                for path in sorted((ROOT / "tests" / "screens").glob("*.png")):
                    image = np.ascontiguousarray(np.array(Image.open(path).convert("RGB"))[:, :, ::-1])
                    cells = [(x, y) for x, y in actions.OFFER_CELLS if shop.filled(image, x, y)]
                    short = [t for t, (_, _, _, h) in actions.ocr(context, image, actions.OFFER_GRID)
                             if h < 18 and not shop.has_letters(t) and sum(c.isdigit() for c in t) >= 3]
                    if short:  # read_slots keeps a price line under 18 px tall that has 3 digits (#341): what else is one
                        out["short_prices"][path.stem] = short
                    named = [[i, p["id"]] for i, p in enumerate(actions.read_plates(context, image, cells)) if p["id"]]
                    if named:
                        out["plate_sweep"][path.stem] = named
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


@pytest.mark.parametrize("case", ["offers", "offers_super", "offers_red"])
def test_the_name_plate_names_what_the_icon_names(read, case):
    # #329: wherever the icon names a gift, the plate names the same one; a skill slot's plate names none.
    plates = [p[2] for p in read["plates"][case]]
    assert plates == read["cases"][case]


def test_a_plate_costs_no_more_per_cell_than_the_det_rec_pass_over_the_page(read):
    # #329: a plate line is about 31 ms on DirectML once a det+rec pass has used the shared instance (the 40 ms of the issue; a
    # CPU runner reads it in 8 ms and is slower overall), so no absolute bound: only_rec over one fixed box must cost less per
    # cell than the det+rec pass over the whole page, else it reads more than a line. First case left out: it pays the model's load.
    plate, page = (sorted(read[k][1:])[len(read[k][1:]) // 2] for k in ("plate_ms", "page_ms"))
    assert plate < page * 4, read


def test_a_plate_is_read_one_line_by_the_default_ocr_instance():
    # #329: only_rec in the plate's box under the cell's centre, on the shared OCR instance (no "model" folder of its own).
    import actions  # noqa: PLC0415
    asked = []

    def run_recognition(name, image, override):
        asked.append(override[name])
        return types.SimpleNamespace(all_results=[types.SimpleNamespace(text="Arrested Hymn", box=(0, 0, 10, 10))])
    context = types.SimpleNamespace(run_recognition=run_recognition)
    assert actions.read_plates(context, None, [(778, 265)]) == [{"text": "Arrested Hymn", "id": 9106}]
    assert asked == [{"recognition": "OCR", "roi": [702, 329, 152, 26], "only_rec": True}]


def test_the_name_plate_names_dimmed_and_purchased_cells(read):
    # #329, live 2026-10-18 (106 Cost): three Not Enough Cost offers (Emerald Elytra, Lithograph, Reverberation) show no tier,
    # so no icon id; a Purchased one (Ornamental Horseshoe) shows its name just the same. The skill slot names none.
    assert read["plates"]["offers_short"] == [[0, "Replace Meursault's Skill", None], [1, "Emerald Elytra", 9128],
                                              [2, "Lithograph", 9017], [3, "Reverberation", 9086], [4, "Ornamental Horseshoe", 9097]]


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
        # #330: Cask Spirits (IV), the Fusion Available cell of ShopFuseRecipe, read as II: found by its Poise badge alone.
        "ShopFuseRecipe fuse": [[0, 9180]],
        "ShopFuseRecipeTwo fuse": [[0, 9179]],
        "SuperShop offer": [[3, 9187], [4, 9009], [5, 9102], [6, 9063], [7, 9163]],
    }


def test_no_capture_but_the_shops_has_a_name_plate_that_names_a_gift(read):
    # #329: the plates of every tests/screens capture's offer cells (a false id on a screen with no shop would fail here).
    # ShopPurchase: the dialog covers the shop but Lowest Star's plate (the filled cell at index 3) still shows, dimmed, and is read right.
    assert read["plate_sweep"] == {"Shop": [[1, 9123], [2, 9198], [3, 9150], [4, 9086]], "ShopPurchase": [[3, 9027]],
                                   "SuperShop": [[3, 9187], [4, 9009], [5, 9102], [6, 9063], [7, 9163]]}


def test_a_scrolled_super_shop_adds_its_last_two_offers_to_the_eight_at_rest(read):
    # #341: SuperShop.png and its capture scrolled 150 px (live 2026-10-15): the second row shows where the first was, the third
    # under it. The scrolled read leaves out the 4 offers the first one had and adds the 2 new, whose icons and plates (cells
    # 150 px up, the plate's box relative to the cell) name Uncapped Defibrilator (the game's spelling) and Burning Intellect.
    first, more = read["super"]
    assert [(n, p) for n, p, _, _ in first] == [("ID Skill Search", None), ("Replace Gregor's Skill", None), ("Replace Don Quixote's Skill", None),
                                                 ("Special Catalogue", 200), ("Fiery Down", 203), ("Polarization", 158),
                                                 ("Pendant of Nostalgia", 145), ("Gemstone Oscillator", 153)]
    assert more == [["Uncapped Defibrilator", 147, 9133, 9133], ["Burning Intellect", 141, 9087, 9087]]  # a price read 17 px tall too


def test_no_shop_capture_has_a_short_line_of_digits_that_is_not_a_price(read):
    # #341: read_slots takes a digits-only line under 18 px tall for a price when it has 3 digits. Over every tests/screens capture
    # the OFFER_GRID box reads such lines only on battle, map and settings screens (a turn counter, a date), which no shop page is.
    assert [k for k in read["short_prices"] if "Shop" in k] == []


if __name__ == "__main__":
    child()
