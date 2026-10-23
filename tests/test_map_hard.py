"""A HARD floor's two columns, read by RouteMap on live captures (#129).

HARD shows two columns past the bus. Live 2026-10-18 the map stood where it rests, the top row at y 72, and the right-hand HUD
covered column 2's top node (c2 up): it was read as no node at all (the link into it too, #136). Since #111 the bus is dragged to the
far left first, which puts the top row at y 144, the whole node and its badges clear of the resource bar, so c2 up is read where
there is one. A column with a node missing is a map with no node there: the six HARD reads the data sweep listed with
column 2 short by one (2026-10-22 and 23, three rounds) show an empty slot on the capture, not a covered one.

RouteMap.read_slots and read_ahead run inside a real MaaFramework task (resource bundle loaded, a still controller), so the marks
and the Cost OCR are the agent's on the device. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a
child process: this file run as a script, as test_map_cost.py does.
"""

import json
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

# frame -> (column 1, column 2): row -> [type, the rows it is linked from]. The bus at the far left (50, 320); every frame is a live
# HARD map read, its rows as the bot logged them, checked by eye on the capture.
FRAMES = {
    # floor 3: c2 up is a battle (85) with its coin and badge under the resource bar's end, read; c2 down is empty
    "MapHardTwoColsUp": ({"mid": ["abno", None], "up": ["battle", None], "down": ["focused", None]},
                         {"mid": ["event", ["down", "mid"]], "up": ["battle", ["mid", "up"]]}),
    # floor 3: c2 up is empty (c1 up links down to c2 mid), c2 mid and down are events
    "MapHardTwoColsMidDown": ({"mid": ["battle", None], "up": ["event", None], "down": ["abno", None]},
                              {"mid": ["event", ["down", "mid", "up"]], "down": ["event", ["down"]]}),
    # floor 2: only c2 up exists; c2 mid and down are empty
    "MapHardTwoColsUpOnly": ({"mid": ["event", None], "up": ["battle", None]}, {"up": ["event", ["mid", "up"]]}),
}
# The map left where it rests (bus at 446, 248: the top row at y 72), which the drag to the far left is there to avoid and cannot be
# counted on (a HARD map is dragged by the same find_bus, held for 3 drags at most). MapHardRest.synthetic.png is MapHardTwoColsUp with its
# map moved (+396, -72) under the HUD, which stays put (the title and relic bar, resource bar, star panel and party strip pasted back; the
# strip the move left behind painted out): c1 up sits under the resource bar, c2 up under the star panel, its coin and badge out of
# sight. Each is read, as a node of no known type: "unknown" ranks after every fight (map_weights.yaml), it is not left out.
# Limits of the frame: the real 2026-10-18 capture only lost c2 up (c1 up was clear), a badge half under the HUD is not covered, and the HUD's
# edges are pasted. With map_route.line_contrast's top back at y 70 (before #136) c2 up loses its link from c1 up and this test fails.
REST = ({"mid": ["abno", None], "up": ["unknown", None], "down": ["focused", None]},
        {"mid": ["event", ["down", "mid"]], "up": ["unknown", ["mid", "up"]]})


def child():
    """Read every frame through RouteMap in a MaaFramework task; print {frame: [column 1, column 2]}."""
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
                with tempfile.TemporaryDirectory() as logs:
                    actions.ROOT = Path(logs)  # a Cost miss keeps its crop under logs/cost
                    actions.RUN.update(settings={}, difficulty="hard", floor_hard=True)
                    for name in (*FRAMES, "MapHardRest.synthetic"):
                        image = np.asarray(Image.open(ROOT / "tests" / "screens" / f"{name}.png").convert("RGB"))[:, :, ::-1].copy()
                        bus = actions.seen(context, image, "MapBus")
                        bx, by = bus.box[0], bus.box[1]
                        slots = actions.RouteMap.read_slots(context, image, bx, by)
                        ahead = actions.RouteMap.read_ahead(context, image, bx + actions.SLOT[0], by + actions.SLOT[1], slots)
                        out[name] = [{"bus": [bx, by]}, {row: [kind, None] for row, (kind, _) in slots.items()},
                                     *({row: [kind, sorted(src)] for row, (kind, src) in column.items()} for column in ahead)]
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


@pytest.mark.parametrize("name", FRAMES)
def test_the_bus_stands_at_the_far_left_so_the_top_row_is_clear_of_the_hud(read, name):
    bx, by = read[name][0]["bus"]
    assert abs(bx - 50) <= 30 and abs(by - 320) <= 25  # RouteMap.find_bus's own tolerance


@pytest.mark.parametrize("name", FRAMES)
def test_a_hard_floor_reads_column_2_slot_for_slot(read, name):
    column_1, column_2 = FRAMES[name]
    assert read[name][1:] == [column_1, column_2]


def test_with_the_map_at_rest_the_nodes_under_the_hud_are_read_as_unknown_not_left_out(read):
    bus, *columns = read["MapHardRest.synthetic"]
    assert abs(bus["bus"][0] - 446) <= 5 and abs(bus["bus"][1] - 248) <= 5  # MapBus matches within a pixel or two
    assert columns == list(REST)


if __name__ == "__main__":
    child()
