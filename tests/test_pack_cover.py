"""The theme pack cards told by their cover art (#274), and every read path on real pages.

The page tests run actions.pack_titles inside a MaaFramework task on the committed screenshots (a child process, as
test_shop_cells does: the pytest process holds MaaFramework in AgentServer mode), then run_start.rank_packs with
pack_cover.read_cover as the agent's PickThemePack does.
"""

import json
import shutil
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: pytest's pythonpath has it
import pack_cover as pc  # noqa: E402
import run_start as rs  # noqa: E402

DATA = ROOT / "assets/resource/base/data"
SCREENS = ROOT / "tests" / "screens"
YAML = yaml.safe_load((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
NAMES, ART = list(YAML["packs"]), YAML["title_art"]
PLAN = {"weights": YAML["default_plan"]["weights"], "unlisted": 0}

# page: [(pack, how)] left to right, what PickThemePack names on the committed screenshots
PAGES = {
    # NORMAL floor 1, five plain titles
    "ThemePackNormal": [("Automated Factory", "name"), ("The Outcast", "name"), ("The Unloving", "name"),
                        ("Nagel und Hammer", "name"), ("The Forgotten", "name")],
    # HARD floor 5: Line 1's art reads as the capitals MADNESS (#266); Four Houses and Greed's title splits in three boxes
    "ThemePackHardLine1": [("The Surrendered Witnessing", "name"), ("Line 1", "title_art"),
                           ("Four Houses and Greed", "name"), ("Tangling Lust", "name")],
    # HARD floor 5: Line 1 reads "Line" under the capitals MADNESS: with the lowercase rule only "Line" was left (#274)
    "ThemePackHardLineCover": [("Sinking Deluge", "name"), ("Abnormal Seismic Zone", "name"), ("Line 1", "title_art"),
                               ("Blade and Artwork", "name"), ("Thunder and Lightning", "name")],
    # HARD floor 5: the last card reads "Line" under noise and "ROLIND" (Merry-Go-Round, Line 5): Line 1 to 3 and 5 are alike
    # titles, the cover tells them apart (#274)
    "ThemePackHardLine5": [("Nocturnal Sweeping", "name"), ("Miracle in District 20", "name"), ("The Dream Ending", "name"),
                           ("Mountain of Corpses, Sea of Blood", "name"), ("Line 5", "cover")],
    # NORMAL floor 3: Miracle in District 20's art title reads "InDistrict" and "miiracle" over noise (#274: its keyword)
    "ThemePackMiracle": [("Miracle in District 20", "keyword"), ("Addicting Lust", "name"), ("Vain Pride", "name"),
                         ("Yield My Flesh to Claim Their Bones", "name"), ("Tearful Things", "name")],
    # cards swinging in: tilted and overlapping, no cover stands clear (the agent waits for them to stop, #246)
    "ThemePack": [("To be Crushed", "name"), ("Nagel und Hammer", "name"), ("To be Cleaved", "name")],
}
# page, card whose title read is lost to the logo's noise ("WOPIS"): [(pack, how)] left to right
BLANKED = {
    "ThemePackNormal/2": ("ThemePackNormal", 2, [("Automated Factory", "name"), ("The Outcast", "name"), ("The Unloving", "cover"),
                                                 ("Nagel und Hammer", "name"), ("The Forgotten", "name")]),
    # The Outcast's picture is The Dream Ending's: the title band tells them apart (with the picture alone it stayed unread)
    "ThemePackNormal/1": ("ThemePackNormal", 1, [("Automated Factory", "name"), ("The Outcast", "cover"), ("The Unloving", "name"),
                                                 ("Nagel und Hammer", "name"), ("The Forgotten", "name")]),
}


def read_pages():
    """Every page of PAGES through actions.pack_titles and run_start.rank_packs; print {page: [[pack, how], ...]}."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions  # noqa: PLC0415

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # clicks, swipes, keys: nothing moves
            return lambda *args: True

    out = {}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for key, (page, blank) in {**{p: (p, None) for p in PAGES}, **{k: v[:2] for k, v in BLANKED.items()}}.items():
                    image = np.ascontiguousarray(np.asarray(Image.open(SCREENS / f"{page}.png").convert("RGB"))[:, :, ::-1])
                    cards = actions.pack_titles(context, image)
                    if blank is not None:
                        cards[blank] = (cards[blank][0], ["WOPIS"])
                    ranked = rs.rank_packs([lines for _, lines in cards], NAMES, PLAN, ART,
                                           lambda i, allowed: pc.read_cover(image, cards[i][0], allowed))
                    out[key] = [[title, how.split()[0]] for title, _, how in ranked]
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
    return out


@pytest.mark.parametrize("page", list(PAGES))
def test_every_card_of_a_real_page_is_named_by_the_path_that_reads_it(read, page):
    # each path of rank_packs on a real capture: whole title, title art, keyword, cover; and what the old read gave
    assert read[page] == [list(p) for p in PAGES[page]]


@pytest.mark.parametrize("key", list(BLANKED))
def test_a_card_whose_title_is_lost_is_read_by_its_cover_or_left_unread(read, key):
    # real OCR on the other cards of a capture; one card's title replaced by the logo's noise. The cover names it where
    # it stands clear; where it does not, the card keeps its place, unread, rather than guessed.
    assert read[key] == [list(p) for p in BLANKED[key][2]]


def test_the_overlapped_cards_of_the_page_swinging_in_are_not_guessed_by_their_covers():
    # cards tilted and overlapping: the overlapped ones stand clear of no cover; the first, tilted but whole, reads right
    page = np.asarray(Image.open(SCREENS / "ThemePack.png").convert("RGB"))[:, :, ::-1]
    assert [(pc.read_cover(page, x) or [None])[0] for x in (310, 485, 684)] == ["To be Crushed", None, None]


def test_the_cover_alone_names_most_cards_of_a_real_page_and_never_a_wrong_one():
    # the cover path on pages whose titles all read: right where it speaks. Silent on the dark silhouette cards
    # (a boss not yet beaten shows as a black shape, the cover has the picture) and on look-alike covers.
    spoke = right = 0
    for page in ("ThemePackNormal", "ThemePackHardLine1", "ThemePackHardLineCover", "ThemePackHardLine5", "ThemePackMiracle"):
        image = np.asarray(Image.open(SCREENS / f"{page}.png").convert("RGB"))[:, :, ::-1]
        n = len(PAGES[page])
        for (name, _), x in zip(PAGES[page], [640 + (i - (n - 1) / 2) * pc.PITCH for i in range(n)]):
            found = pc.read_cover(image, x)
            spoke += found is not None
            right += found is not None and found[0] == name
    # of 24 cards; silent: the boss silhouette of Sinking Deluge, Miracle in District 20 and The Dream Ending on the HARD page.
    # The picture alone left 5 silent: Tangling Lust's silhouette and The Outcast and The Dream Ending (the same picture) too
    assert (spoke, right) == (21, 21)



def art_shift(page, x, name):
    """(dx, dy) in px from the art of `name`'s cover to the art of the card at x: phase correlation on the ART band."""
    import cv2  # noqa: PLC0415

    w, h = pc.CARD
    left, top, right, bottom = pc.ART
    band = (slice(int(top * h), int(bottom * h)), slice(int(left * w), int(right * w)))
    file = json.loads((DATA / "theme_pack_covers" / "index.json").read_text(encoding="utf-8"))[name]
    cover = Image.new("RGBA", pc.CARD, (0, 0, 0, 255))
    cover.alpha_composite(Image.open(DATA / "theme_pack_covers" / file).convert("RGBA").resize(pc.CARD))
    grey = [cv2.cvtColor(np.ascontiguousarray(im), cv2.COLOR_BGR2GRAY)[band].astype(np.float32)
            for im in (np.asarray(cover.convert("RGB"))[:, :, ::-1], pc.card_image(page, x))]
    window = cv2.createHanningWindow((grey[0].shape[1], grey[0].shape[0]), cv2.CV_32F)
    return cv2.phaseCorrelate(grey[0], grey[1], window)[0]


@pytest.mark.parametrize("page, i, name", [
    ("ThemePackHardLineCover", 4, "Thunder and Lightning"),  # boss packs: the boss sprite is tight-packed
    ("ThemePackHardLine5", 3, "Mountain of Corpses, Sea of Blood"),
    ("ThemePackMiracle", 2, "Vain Pride"),
    ("ThemePackNormal", 1, "The Outcast"),  # no boss
])
def test_the_cover_art_sits_where_the_live_card_has_it(page, i, name):
    # the boss picture drawn from its trimmed texture sat 5 to 14 px low on the 335 px card (and a few px aside)
    assert PAGES[page][i][0] == name
    n = len(PAGES[page])
    image = np.asarray(Image.open(SCREENS / f"{page}.png").convert("RGB"))[:, :, ::-1]
    dx, dy = art_shift(image, 640 + (i - (n - 1) / 2) * pc.PITCH, name)
    assert abs(dx) <= 2 and abs(dy) <= 2, (dx, dy)



@pytest.mark.parametrize("page, i, name", [
    ("ThemePackHardLine1", 1, "Line 1"),
    ("ThemePackHardLineCover", 2, "Line 1"),
    ("ThemePackHardLine5", 4, "Line 5"),
])
def test_the_long_battle_overlay_sits_where_the_live_card_has_it(page, i, name):
    # the Baton sprite is tight-packed like the boss pictures: drawn from its trimmed texture, the triangle and its label
    # stood off the live card's (pixel correlation of that band 0.65 on these cards; 0.78 with the whole rect)
    assert PAGES[page][i][0] == name
    n = len(PAGES[page])
    image = np.asarray(Image.open(SCREENS / f"{page}.png").convert("RGB"))[:, :, ::-1]
    card = pc.card_image(image, 640 + (i - (n - 1) / 2) * pc.PITCH)
    file = json.loads((DATA / "theme_pack_covers" / "index.json").read_text(encoding="utf-8"))[name]
    cover = Image.new("RGBA", pc.CARD, (0, 0, 0, 255))
    cover.alpha_composite(Image.open(DATA / "theme_pack_covers" / file).convert("RGBA").resize(pc.CARD))
    w, h = pc.CARD
    band = (slice(int(0.18 * h), int(0.36 * h)), slice(int(0.25 * w), int(0.75 * w)))  # the triangle and "Long Battle"
    assert pc.correlation(card[band], np.asarray(cover.convert("RGB"))[:, :, ::-1][band]) >= 0.72


def tiny_page(seed, x=640):
    """A 720p page whose card at x is noise of this seed: pack_cover reads the card art off it."""
    page = np.zeros((720, 1280, 3), np.uint8)
    left = int(x - pc.CARD[0] / 2)
    page[pc.CARD_TOP:pc.CARD_TOP + pc.CARD[1], left:left + pc.CARD[0]] = np.random.default_rng(seed).integers(0, 256, (pc.CARD[1], pc.CARD[0], 3))
    return page


@pytest.fixture
def three_covers(monkeypatch):
    sigs = {name: pc.signature(tiny_page(seed)[pc.CARD_TOP:pc.CARD_TOP + pc.CARD[1], 549:731]) for name, seed in (("A", 1), ("B", 2), ("C", 3))}
    sigs["A2"] = sigs["A"]  # a look-alike cover
    monkeypatch.setattr(pc, "covers", lambda: sigs)


def test_a_cover_is_read_when_it_stands_clear_of_the_rest(three_covers):
    name, score = pc.read_cover(tiny_page(2), 640)
    assert name == "B" and score > 0.99


def test_a_card_like_no_cover_is_not_read(three_covers):
    assert pc.read_cover(tiny_page(99), 640) is None  # the best correlation of noise to noise stays under MIN_SCORE


def test_look_alike_covers_are_not_told_apart(three_covers):
    assert pc.read_cover(tiny_page(1), 640) is None  # A and A2 tie: under MIN_LEAD


def test_covers_with_the_same_picture_are_told_apart_by_the_title_band(monkeypatch):
    # The Outcast and The Dream Ending: the picture alike, the title not
    page, other = tiny_page(1), tiny_page(2)
    top = pc.CARD_TOP + int(0.70 * pc.CARD[1])
    twin = page.copy()
    twin[top:pc.CARD_TOP + pc.CARD[1]] = other[top:pc.CARD_TOP + pc.CARD[1]]  # the same picture, another title
    monkeypatch.setattr(pc, "covers", lambda: {"A": pc.signature(pc.card_image(page, 640)), "A twin": pc.signature(pc.card_image(twin, 640))})
    assert pc.read_cover(page, 640)[0] == "A"
    assert pc.read_cover(twin, 640)[0] == "A twin"


def test_the_title_narrows_the_covers_a_card_can_be_read_as(three_covers):
    assert pc.read_cover(tiny_page(1), 640, {"A", "B"})[0] == "A"  # A2 is out: A leads
    assert pc.read_cover(tiny_page(1), 640, {"B", "C"}) is None  # the card is like neither: nothing in the set


@pytest.mark.parametrize("x", [200, 204, 215, 224])
def test_the_card_is_cut_on_the_half_pitch_grid_whatever_the_title_centre(x):
    # a title's centre is off its card's by a few px; the grid has 105 px steps around x = 640
    assert pc.card_image(np.zeros((720, 1280, 3), np.uint8), x).shape[:2] == (pc.CARD[1], pc.CARD[0])
    left = int(640 + round((x - 640) / (pc.PITCH / 2)) * pc.PITCH / 2 - pc.CARD[0] / 2)
    page = np.zeros((720, 1280, 3), np.uint8)
    page[:, left:left + 1] = 255
    assert pc.card_image(page, x)[:, 0].min() == 255  # the cut starts on that column


def test_every_cover_is_read_as_itself_but_look_alikes_and_none_as_another():
    # each cover pasted on a page at its own size: read as itself, or not at all where a look-alike stands as close
    index = json.loads((DATA / "theme_pack_covers" / "index.json").read_text(encoding="utf-8"))
    silent = []
    for name, file in index.items():
        cover = Image.open(DATA / "theme_pack_covers" / file).convert("RGB").resize(pc.CARD)
        page = np.zeros((720, 1280, 3), np.uint8)
        page[pc.CARD_TOP:pc.CARD_TOP + pc.CARD[1], 549:731] = np.asarray(cover)[:, :, ::-1]
        found = pc.read_cover(page, 640)
        assert found is None or found[0] == name
        silent += [name] * (found is None)
    # the look-alike pairs are silent; the others read, bar the odd one a decoder's rounding tips under MIN_LEAD (The Outcast and
    # The Dream Ending lead each other by 0.101)
    assert {"Line 4 - Section #3", "Line 4 - Section #4", "Repressed Wrath", "Unbound Wrath"} <= set(silent)
    assert len(silent) <= 6


def test_the_signatures_load_from_an_installed_tree(tmp_path):
    # tools/install.py puts assets/resource at <root>/resource, beside agent/ (#323); the repo has <root>/assets/resource
    shutil.copytree(ROOT / "agent", tmp_path / "agent", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "resource" / "base" / "data").mkdir(parents=True)
    shutil.copy2(pc.SIGNATURES, tmp_path / "resource" / "base" / "data")
    done = subprocess.run([sys.executable, "-c", "import pack_cover; print(len(pack_cover.covers()))"],
                          cwd=tmp_path / "agent", capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-500:]
    assert int(done.stdout) == len(json.loads(pc.SIGNATURES.read_text(encoding="utf-8")))


def test_the_signature_file_is_the_one_the_covers_make():
    # a new season's covers (tools/theme_pack_covers.py) need tools/theme_pack_signatures.py after them
    import theme_pack_signatures as tps
    assert tps.drift(pc.SIGNATURES.read_text(encoding="utf-8"), tps.build()) <= tps.TOLERANCE  # exact on one machine, one libwebp
    assert tps.drift(pc.SIGNATURES.read_text(encoding="utf-8"), tps.build().replace("A", "B", 3)) > 0  # a changed value shows
    assert set(json.loads(pc.SIGNATURES.read_text(encoding="utf-8"))) == set(NAMES)


if __name__ == "__main__":
    read_pages()
