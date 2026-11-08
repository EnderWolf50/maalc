"""The number beside a map node's Cost coin (#257, #284): read by MaaFramework's OCR on every labelled coin of the
map captures in tests/screens, as read, with no table to snap it to; and every node of those captures typed by it (#228).

actions.coin_text runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the OCR
is the agent's on the device. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a
child process: this file run as a script, as test_map_shop.py does.
"""

import json
import re
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

SCREENS = ROOT / "tests" / "screens"
COIN = (26, 24)  # the Cost coin template's size: the box node_at hands coin_text
# Labelled by eye: image -> [x, y, the number printed] of each lit or dimmed node coin (not the resource bar's).
# 2026-10-22 live, floor 3 (MapCostFloor3) and floor 4 (MapCostFloor4): a 100 read None, a 120 read 20.
# 2026-10-23 live, hard (#284): MapCostHard85, two 85s over a lit link's pale line (the left one read None live);
# MapBossCost500, floor 4's boss, its red glow unmatched (typed focused live).
COINS = json.loads((ROOT / "tests" / "data" / "map_costs.json").read_text(encoding="utf-8"))
# The coins that stay unread (None, and the marks decide): dim behind a popup at the right edge. Two coins:
# PauseExploration and ProgressPanel show the same one.
UNREAD = {("GiftGetOverMap.png", 1221, 438), ("PauseExploration.png", 1221, 438), ("ProgressPanel.png", 1221, 438)}
# Live crops of coins the pale link's arrow tip touched (#284), read as '7', '8', '.175' or nothing; the coin sits at (8, 8)
# in a crop. File name: <difficulty><number printed>-<tag>.
CROPS = sorted((ROOT / "tests" / "data" / "cost_crops").glob("*.png"))
CROP_COIN = (8, 8, *COIN)
# node_at end to end on every node of the map captures (#228), labelled by eye: image -> the floor's difficulty (null: not
# known, both are run) and [x, y, the Cost printed, or the kind on screen where no Cost shows] of each node centre. A
# battle with its Cost hidden is told by its coin, centred over the node: Focused and up carry theirs ~25 px right of
# centre, beside a gift box. MapHardRest.synthetic's top row, under the HUD, has the kinds of MapHardTwoColsUp, the
# capture it was made from. Left out: the node the bus stands on, which the bus hides; MapEvent's at 1235, 72 and
# MapFocused's at 980, 72, their kind unseen under the HUD; the captures of a popup over the map (DungeonProgress*,
# GiftGetOverMap, PauseExploration, ProgressPanel), each answered before the map is read, and of the map zoomed in
# on the bus (MapZoomed, MapNodePanel), which RouteMap.unzoom resets first. Among them, #268's (live 2026-10-23, HARD):
# MapBossCost500's boss, its glow unmatched, by its Cost; MapHardF5Warn's Focused 120, Risky 150 and Abnormality 180 by
# their Costs, not the ring that is often missed.
MAP_NODES = json.loads((ROOT / "tests" / "data" / "map_nodes.json").read_text(encoding="utf-8"))
NODE_CASES = [(name, x, y, difficulty) for name, shot in MAP_NODES.items() for x, y, _ in shot["nodes"]
              for difficulty in ([shot["difficulty"]] if shot["difficulty"] else ["normal", "hard"])]
TYPED_INSTEAD = {
    # Misread: in the bus's column, which RouteMap does not read. Its 120 under the floor's title read 'icli', and the
    # gift box unmatched, so a battle.
    ("MapHardTwoColsUpOnly.png", 73, 144): "battle",
    # Top-row nodes whose badges sit under the HUD: no mark at all, unknown by node_at's rule. MapPanned's 100 shows
    # below the resource bar, its coin cut by it.
    **{(name, x, y): "unknown" for name, x, y in [
        ("MapBoss.png", 215, 72), ("MapEvent.png", 725, 72), ("MapFocused.png", 215, 72), ("MapFocused.png", 470, 72),
        ("MapHardRest.synthetic.png", 723, 72), ("MapHardRest.synthetic.png", 978, 72), ("MapPanned.png", 725, 106),
        ("MapPanned.png", 980, 106), ("MapPanned.png", 1235, 106), ("MapRock.png", 725, 72), ("MirrorMap.png", 725, 72)]},
}
# Besides TYPED_INSTEAD's fights, the fights typed with no Cost read: the boss by its glow, before any Cost is read;
# a battle by its marks, its coin under the star panel read '1'; and a Risky by its ring and gift box, its coin and
# number under the star panel (#522: HARD, the map at rest).
UNCOSTED = {("MapBoss.png", 725, 285), ("MapFloor4Panned.png", 1093, 357), ("MapShop.png", 980, 498),
            ("MapRock.png", 980, 72), ("MapCards.png", 980, 72)}


def child():
    """Read every labelled coin through actions.coin_text in a MaaFramework task; print {image x y: number read}."""
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

    def load(path):
        return np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1].copy()

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for name, coins in COINS.items():
                    image = load(SCREENS / name)
                    for x, y, _ in coins:
                        out[f"{name} {x} {y}"] = actions.coin_number(actions.coin_text(context, image, (x, y, *COIN)))
                for crop in CROPS:
                    out[f"crop {crop.name}"] = actions.coin_number(actions.coin_text(context, load(crop), CROP_COIN))
                lines = []
                actions.log = lines.append
                with tempfile.TemporaryDirectory() as logs:
                    actions.ROOT = Path(logs)  # a miss keeps its crop under logs/cost
                    for name, cx, cy, difficulty in NODE_CASES:
                        actions.RUN.update(settings={}, difficulty=difficulty, floor_hard=difficulty == "hard")
                        lines.clear()
                        kind = actions.node_at(context, load(SCREENS / name), cx, cy)
                        cost = next((m[1] for line in lines if (m := re.match(r"map: node at .* reads Cost (\d+)", line))), None)
                        out[f"node {name} {cx} {cy} {difficulty}"] = [kind, cost and int(cost)]
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


CASES = [(name, x, y, cost) for name, coins in COINS.items() for x, y, cost in coins]


@pytest.mark.parametrize(("name", "x", "y", "cost"), [pytest.param(*c, id=f"{c[0]}-{c[1]}-{c[2]}") for c in CASES])
def test_every_labelled_coin_reads_as_its_number_or_stays_unread(read, name, x, y, cost):
    got = read[f"{name} {x} {y}"]
    if (name, x, y) in UNREAD:
        assert got in (None, cost)
    else:
        assert got == cost


def test_the_live_misreads_read_right(read):
    # #257: floor 3, the Focused node in column 2: None, with the old crop cutting the 1 of 100
    assert read["MapCostFloor3.png 595 297"] == 100
    # #257: floor 4, the Risky node in column 2: 20, the 1 of 120 cut
    assert read["MapCostFloor4.png 593 297"] == 120
    # #284: hard, an 85 over a lit link's pale line: None (the line in the mask, the 8 lost or read B)
    assert read["MapCostHard85.png 313 510"] == 85
    assert read["MirrorMap.png 709 438"] == 85


@pytest.mark.parametrize("crop", [pytest.param(c, id=c.stem) for c in CROPS])
def test_a_coin_under_a_link_arrow_reads_whole(read, crop):
    # #284: the arrow's tip, as cream as the digits, touched the 5 and the OCR read '7' or '8' (7 + 3 distinct live misses)
    assert read[f"crop {crop.name}"] == int(re.search(r"\d+", crop.stem)[0])


def test_the_sweep_has_no_unlisted_miss(read):
    missed = {tuple(k.split()[:3]) for k, v in read.items() if v is None and not k.startswith(("node ", "crop "))}
    assert missed <= {(n, str(x), str(y)) for n, x, y in UNREAD}


def label(name, x, y):
    return next(shown for nx, ny, shown in MAP_NODES[name]["nodes"] if (nx, ny) == (x, y))


def is_fight(name, x, y):
    return label(name, x, y) not in ("event", "shop")


@pytest.mark.parametrize(("name", "x", "y", "difficulty"), [pytest.param(*c, id=f"{c[0]}-{c[1]}-{c[2]}-{c[3]}") for c in NODE_CASES])
def test_every_map_node_is_typed_as_the_capture_shows_or_as_listed(read, name, x, y, difficulty):
    import actions
    shown = label(name, x, y)
    if isinstance(shown, int):
        shown = actions.map_data()["node_costs"][difficulty][shown]
    assert read[f"node {name} {x} {y} {difficulty}"][0] == TYPED_INSTEAD.get((name, x, y), shown)


def test_the_fights_typed_with_no_cost_read_are_the_listed_ones(read):
    unread = {(name, x, y) for name, x, y, difficulty in NODE_CASES
              if is_fight(name, x, y) and read[f"node {name} {x} {y} {difficulty}"][1] is None}
    assert unread == UNCOSTED | {node for node in TYPED_INSTEAD if is_fight(*node)}


@pytest.mark.parametrize(("found", "number"), [
    ("75", 75), (".85", 85), ("120", 120), ("500", 500),
    ("", None), ("8", None), ("00", None), ("05", None),  # no digits, one, a leading 0: part reads
])
def test_coin_number_takes_two_digits_or_more_and_no_leading_zero(found, number):
    import actions
    assert actions.coin_number(found) == number


if __name__ == "__main__":
    child()
