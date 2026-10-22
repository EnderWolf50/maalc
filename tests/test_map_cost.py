"""The number beside a map node's Cost coin (#257): read by MaaFramework's OCR on every labelled coin of the
map captures in tests/screens, and the retry and snap of actions.coin_cost on scripted reads.

actions.coin_cost runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the OCR
is the agent's on the device. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a
child process: this file run as a script, as test_map_shop.py does.
"""

import json
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
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

COIN = (26, 24)  # the Cost coin template's size: the box node_at hands coin_cost
NODE_COSTS = yaml.safe_load((ROOT / "assets" / "resource" / "base" / "data" / "map_weights.yaml").read_text(encoding="utf-8"))["node_costs"]
NORMAL, HARD = NODE_COSTS["normal"], NODE_COSTS["hard"]
# Labelled by eye: image -> [x, y, the number printed] of each lit or dimmed node coin (not the boss's, not the
# resource bar's). 2026-10-22 live, floor 3 (MapCostFloor3) and floor 4 (MapCostFloor4): a 100 read None, a 120 read 20.
COINS = json.loads((ROOT / "tests" / "data" / "map_costs.json").read_text(encoding="utf-8"))
# The coins that stay unread (None, and the marks decide): never one read as another cost. Dim behind a popup
# (the right edge), or an 85 on a pale chevron (hard floor, columns the bus is not yet next to).
UNREAD = {("GiftGetOverMap.png", 1221, 438), ("PauseExploration.png", 1221, 438), ("ProgressPanel.png", 1221, 438),
          ("MapCards.png", 709, 225), ("MapShop.png", 197, 438), ("MirrorMap.png", 709, 438), ("MirrorMap.png", 965, 438),
          ("MirrorMap.png", 965, 225)}


def tables(cost):
    return [t for t in (NORMAL, HARD) if cost in t]


def child():
    """Read every labelled coin through actions.coin_cost in a MaaFramework task; print {image x y table: cost read}."""
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

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for name, coins in COINS.items():
                    image = np.asarray(Image.open(ROOT / "tests" / "screens" / name).convert("RGB"))[:, :, ::-1].copy()
                    for x, y, cost in coins:
                        for table in tables(cost):
                            out[f"{name} {x} {y} {min(table)}"] = actions.coin_cost(context, image, (x, y, *COIN), table)
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


CASES = [(name, x, y, cost, table) for name, coins in COINS.items() for x, y, cost in coins for table in tables(cost)]


@pytest.mark.parametrize(("name", "x", "y", "cost", "table"), [pytest.param(*c, id=f"{c[0]}-{c[1]}-{c[2]}-{min(c[4])}") for c in CASES])
def test_every_labelled_coin_reads_as_its_cost_or_stays_unread(read, name, x, y, cost, table):
    got = read[f"{name} {x} {y} {min(table)}"]
    if (name, x, y) in UNREAD:
        assert got in (None, cost)
    else:
        assert got == cost


def test_the_two_live_misreads_read_right(read):
    # floor 3, the Focused node in column 2 (595, 297): None, with the old crop cutting the 1 of 100
    assert read["MapCostFloor3.png 595 297 75"] == 100
    # floor 4, the Risky node in column 2 (593, 297): 20, the 1 of 120 cut
    assert read["MapCostFloor4.png 593 297 75"] == 120


def test_the_sweep_has_no_unlisted_miss(read):
    missed = {tuple(k.split()[:3]) for k, v in read.items() if v is None}
    assert missed == {(n, str(x), str(y)) for n, x, y in UNREAD}


class Reads:
    """actions.coin_number scripted: one read per mask tried, in order."""

    def __init__(self, *reads):
        self.reads, self.masks = list(reads), []

    def __call__(self, context, image, box, bright, sat):
        self.masks.append((bright, sat))
        return self.reads.pop(0)


@pytest.mark.parametrize(("reads", "table", "cost"), [
    ([20], NORMAL, 120),  # the 1 lost: the last two digits
    ([0], NORMAL, 100),  # "00" read as the int 0
    ([50], NORMAL, 150),
    ([80], HARD, 180),
    ([75], NORMAL, 75),
    ([None, 100], NORMAL, 100),  # the first mask reads one digit: the second tries
    ([25, 75], NORMAL, 75),  # noise, then the number
    ([15, 15], NORMAL, None),  # a 7 read as a 1 on both: not 150
    ([None, None], NORMAL, None),
    ([85], NORMAL, None),  # a hard floor's battle is no normal cost
    ([85], HARD, 85),
])
def test_coin_cost_snaps_to_the_floors_costs_and_reads_again_when_none_fits(monkeypatch, reads, table, cost):
    import actions
    script = Reads(*reads, *[None] * 2)
    monkeypatch.setattr(actions, "coin_number", script)
    assert actions.coin_cost(None, None, (0, 0, 26, 24), table) == cost


def test_a_first_read_that_fits_is_not_read_again(monkeypatch):
    import actions
    script = Reads(120)
    monkeypatch.setattr(actions, "coin_number", script)
    assert actions.coin_cost(None, None, (0, 0, 26, 24), NORMAL) == 120
    assert script.masks == [actions.COIN_MASKS[0]]


@pytest.mark.parametrize(("run", "hard"), [
    ({}, False),  # no difficulty yet: normal, as "auto" (None) is
    ({"difficulty": None}, False),
    ({"difficulty": "hard"}, True),
    ({"difficulty": "hard", "floor_hard": False}, False),  # the floor's own difficulty wins
    ({"difficulty": "normal", "floor_hard": True}, True),
])
def test_is_hard_reads_the_floors_difficulty_then_the_runs_and_a_missing_one_as_normal(monkeypatch, run, hard):
    import actions
    monkeypatch.setattr(actions, "current_run", lambda context: run)
    assert actions.is_hard(None) is hard


if __name__ == "__main__":
    child()
