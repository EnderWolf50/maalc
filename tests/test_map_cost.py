"""The number beside a map node's Cost coin (#257, #284): read by MaaFramework's OCR on every labelled coin of the
map captures in tests/screens, as read, with no table to snap it to.

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
# node_at end to end on a floor of the given difficulty: (image, node centre, hard) -> type
# #268, live 2026-10-23 HARD floor 5 (MapHardF5Warn): the WARNING rings read from the Cost, not the ring that is often missed (the
# first HARD round read a Risky and an Abnormality as Focused): column 1 down Focused 120, column 2 mid Risky 150, down Abnormality 180.
NODES = {("MapBossCost500.png", 583, 357, True): "boss", ("MapHardF5Warn.png", 328, 570, True): "focused",
         ("MapHardF5Warn.png", 583, 357, True): "risky", ("MapHardF5Warn.png", 583, 570, True): "abno"}


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
                with tempfile.TemporaryDirectory() as logs:
                    actions.ROOT = Path(logs)  # a miss keeps its crop under logs/cost
                    for name, cx, cy, hard in NODES:
                        actions.RUN.update(settings={}, difficulty="hard" if hard else "normal", floor_hard=hard)
                        out[f"node {name} {cx} {cy}"] = actions.node_at(context, load(SCREENS / name), cx, cy)
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


@pytest.mark.parametrize(("name", "cx", "cy", "hard"), list(NODES))
def test_node_at_types_by_the_cost_as_read(read, name, cx, cy, hard):
    # MapBossCost500: the boss' glow went unmatched; its Cost (hard floor 4: 250 x 2) says boss.
    assert read[f"node {name} {cx} {cy}"] == NODES[name, cx, cy, hard]


@pytest.mark.parametrize(("found", "number"), [
    ("75", 75), (".85", 85), ("120", 120), ("500", 500),
    ("", None), ("8", None), ("00", None), ("05", None),  # no digits, one, a leading 0: part reads
])
def test_coin_number_takes_two_digits_or_more_and_no_leading_zero(found, number):
    import actions
    assert actions.coin_number(found) == number


if __name__ == "__main__":
    child()
