"""The shop node on the map, read by MaaFramework's own template matching (#146), on live captures; and fights by
their Cost where a drag brings them next to the bus (#238).

actions.node_at runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the
MapNodeShop and MapNodeShopIcon templates and their scores are the agent's on the device. The pytest process holds MaaFramework in
AgentServer mode, so the task runs in a child process: this file run as a script, as test_shop_cells.py does.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it
from test_shop import screen_with  # noqa: E402

# case: node centre. The crops sit where the live frames had them: the pre-boss shop at the left of a map panned
# toward the boss, a bus 260 px behind it.
PLUS_SHOPS = [f"map_shop_plus{n}" for n in range(6)] + ["map_shop_torn"]  # hard floors: a star and a "+", the plain template scores 0.33-0.39
NOT_SHOPS = [f"map_notshop{n}" for n in range(4)]  # the slots that scored highest on the "+" templates (0.41-0.42, 3) and on the torn one (0.33, 1) of 1187
CASES = {
    "map_shop_cyan": (330, 145),  # live 2026-10-18 floor 2, cyan theme: read as an event (#146)
    "map_shop_orange": (330, 145),  # floor 1, orange theme: read as an event too
    "map_event_orange": (326, 144),  # a "?" in the same theme and place must stay an event
    **{name: (330, 145) for name in PLUS_SHOPS + NOT_SHOPS},  # #287
}
# #238, live 2026-10-22 floor 4: column 3's Risky (120) and Abnormality (150), read from afar by their marks as
# Focused (MapFloor4.png, x 837), then two columns on, where a drag of read_on brings them (MapFloor4Panned.png).
# CODING_STANDARDS' sweep of MAP_NEAR: every slot up to it on the two frames with the bus at the far left (column 2's
# empty slots read as events; RouteMap reads only the linked ones). frame, slot centre: the type on screen.
FRAMES = {"MapFloor4 327 144": "event", "MapFloor4 327 357": "focused", "MapFloor4 327 570": "focused",
          "MapFloor4 582 144": "event", "MapFloor4 582 357": "battle", "MapFloor4 582 570": "event",
          "MapFloor4Panned 328 144": "battle", "MapFloor4Panned 328 357": "risky", "MapFloor4Panned 328 570": "abno",
          "MapFloor4Panned 583 144": "battle", "MapFloor4Panned 583 357": "event", "MapFloor4Panned 583 570": "event"}
# #268, live 2026-10-23 floor 4 (NORMAL): the boss' glow is a thin ring, mostly outside MapNodeBoss's 80 px box: 502 red pixels in it
# against its 1000 (741 in 92 px, 1448 in 120 px), so the dark boss is typed by its marks, as a fight. It is the boss all the same: the shop
# 255 px before it says so (map_route.boss_after_shop, #279). The shop at x 837 and the boss at x 1092, both middle row.
BOSS_SHOP, BOSS = (837, 357), (1092, 357)


def child():
    """Run every case through actions.node_at in a MaaFramework task; print {case: node type}."""
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
                for case, (cx, cy) in CASES.items():
                    out[case] = actions.node_at(context, screen_with(case), cx, cy, costs=False)
                actions.RUN.update(settings={}, difficulty="normal", floor_hard=False)
                for case in FRAMES:
                    name, cx, cy = case.split()
                    cx, cy = int(cx), int(cy)
                    image = np.asarray(Image.open(ROOT / "tests" / "screens" / f"{name}.png").convert("RGB"))[:, :, ::-1].copy()
                    out[case] = actions.node_at(context, image, cx, cy, costs=cx <= actions.MAP_NEAR)
                image = np.asarray(Image.open(ROOT / "tests" / "screens" / "MapBossDarkAfterShop.png").convert("RGB"))[:, :, ::-1].copy()
                x, y = BOSS
                out["boss glow"] = bool(actions.seen(context, image, "MapNodeBoss", (x - 40, y - 40, 80, 80)))
                out["boss shop"] = actions.node_at(context, image, *BOSS_SHOP, costs=False)
                ahead = actions.RouteMap.read_ahead(context, image, *BOSS_SHOP, {"mid": ("shop", {"mid"})}, first=5)
                out["boss ahead"] = [{row: [kind, sorted(src)] for row, (kind, src) in column.items()} for column in ahead]
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


@pytest.mark.parametrize("case, kind", [
    ("map_shop_cyan", "shop"),
    ("map_shop_orange", "shop"),
    ("map_event_orange", "event"),
])
def test_the_shop_node_is_a_shop_in_every_theme_pack_colour_and_a_question_mark_stays_an_event(read, case, kind):
    assert read[case] == kind


@pytest.mark.parametrize("case", PLUS_SHOPS)
def test_the_plus_variant_of_the_shop_is_a_shop(read, case):
    assert read[case] == "shop"


@pytest.mark.parametrize("case", NOT_SHOPS)
def test_the_slots_most_like_the_plus_variant_are_not_shops(read, case):
    assert read[case] != "shop"


@pytest.mark.parametrize(("case", "kind"), FRAMES.items())
def test_every_slot_up_to_map_near_is_typed_by_its_cost_on_the_far_left_frames(read, case, kind):
    assert read[case] == kind


def test_the_dark_boss_of_floor_4_is_missed_by_its_glow(read):
    # The premise of the next test, not a wish: the glow of this boss stays under MapNodeBoss's count.
    assert read["boss shop"] == "shop"
    assert read["boss glow"] is False


def test_a_dark_boss_whose_glow_misses_is_the_boss_because_the_shop_comes_before_it(read):
    assert read["boss ahead"] == [{"mid": ["boss", ["mid"]]}]


if __name__ == "__main__":
    child()
