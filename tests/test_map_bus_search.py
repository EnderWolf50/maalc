"""RouteMap finding the bus on the frames of a live run (#907).

tests/data/map_wedge_f5/ holds frames of the 2026-11-22 HARD run's recording, floor 5 (the event pack The Wedge in the
Wake of Dawnbreak), 1280x720 as the bot sees the screen:

- bus_home.png (18:37:37.6), bus_home_later.png (0.1 s later): the map with the bus at the far left (49, 320).
- stalled.png (18:36:08.9), stalled_later.png (0.1 s later): the bus at rest (446, 248), during the 0.5 s the game drew
  nothing (18:36:08.8-09.3); find_bus's first pan went down at 18:36:08.7 and its finger stopped at 09.08.
- flung.png (18:36:17.9): where that pan, lifted at once and made again, left the map: the bus ~900 px off the
  screen's left (search_bus's 400 px drag right brought the second column's event to x 35).
- right_end.png (18:36:27.9): 400 px further right, the map's right end showing.

MapBus is matched as the pipeline has it (map.json: TemplateMatch in its roi, at its threshold).
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np

import actions
import map_actions
import test_actions
from agent_patch import patch_all

clock, context = test_actions.clock, test_actions.context  # fixtures of the fake Maa context

ROOT = Path(__file__).resolve().parent.parent
WEDGE = ROOT / "tests" / "data" / "map_wedge_f5"
SCREENS = ROOT / "tests" / "screens"


def frame(path):
    return cv2.imread(str(path))  # BGR, as a screenshot


def pipeline_node(name):
    lines = (ROOT / "assets/resource/base/pipeline/map.json").read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))[name]


BUS = pipeline_node("MapBus")
BUS_TEMPLATE = frame(ROOT / "assets/resource/base/image" / BUS["template"])


def bus_seen(image):
    """MapBus's hit on image, None on a miss."""
    x, y, w, h = BUS["roi"]
    scores = cv2.matchTemplate(image[y:y + h, x:x + w], BUS_TEMPLATE, cv2.TM_CCOEFF_NORMED)
    _, score, _, (bx, by) = cv2.minMaxLoc(scores)
    if score < BUS["threshold"]:
        return None
    th, tw = BUS_TEMPLATE.shape[:2]
    return SimpleNamespace(hit=True, box=[x + bx, y + by, tw, th], best_result=SimpleNamespace(score=score))


def test_the_runs_frames_show_the_bus_where_the_log_read_it():
    assert bus_seen(frame(WEDGE / "bus_home.png")).box[:2] == [49, 320]
    assert bus_seen(frame(WEDGE / "stalled.png")).box[:2] == [446, 248]  # maafw.log: MapBus [446, 248] at 18:36:09.28
    assert bus_seen(frame(WEDGE / "flung.png")) is None and bus_seen(frame(WEDGE / "right_end.png")) is None


def wedge_world(context, camera):
    """Floor 5's map, 2630 px wide, made of the run's frames: bus_home.png from 0, flung.png from 950, right_end.png
    from 1350. The screen's left edge starts at camera and moves with the drags (across only, as test_actions.map_world)
    between the map's ends, 0 and 1350; every screen keeps bus_home.png's HUD. A tap on the slot next to the bus at the
    far left (its middle row, 328, 357) opens a node panel. Returns the screen's offsets after each drag."""
    home, flung, right = (frame(WEDGE / f"{n}.png") for n in ("bus_home", "flung", "right_end"))
    world = np.zeros((720, 1350 + 1280, 3), np.uint8)
    for image, at in ((home, 0), (flung, 950), (right, 1350)):
        world[:, at:at + 1280] = image
    off, start, offsets = [camera], [], []

    def shot():
        image = world[:, off[0]:off[0] + 1280].copy()
        for ys, xs in ((slice(0, 60), slice(None)), (slice(640, None), slice(None)), (slice(None), slice(1200, None)),
                       (slice(60, 210), slice(0, 300))):  # resource bar, sinner bar, buttons, floor title
            image[ys, xs] = home[ys, xs]
        return image

    def down(x, y):
        start[:] = [x, off[0]]
        return MagicMock()

    def move(x, y):
        off[0] = min(max(0, start[1] + start[0] - x), world.shape[1] - 1280)
        return MagicMock()

    def up():
        offsets.append(off[0])
        return MagicMock()
    ctl = context.tasker.controller
    ctl.post_touch_down.side_effect, ctl.post_touch_move.side_effect, ctl.post_touch_up.side_effect = down, move, up
    ctl.post_screencap.return_value.wait.return_value.get.side_effect = shot

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return bus_seen(image)
        if name == "MapNodePanel":
            taps = ctl.post_click.call_args_list
            return SimpleNamespace(hit=True) if taps and taps[-1].args == (328, 357) else None
        return None
    context.run_recognition.side_effect = run_recognition
    return offsets


def touch_times(context):
    """[(kind, t)] of each touch down, move and lift on the fake clock."""
    ctl, events = context.tasker.controller, []
    for kind, fake in (("down", ctl.post_touch_down), ("move", ctl.post_touch_move), ("up", ctl.post_touch_up)):
        fake.side_effect = lambda *a, kind=kind: events.append((kind, actions.time.monotonic())) or MagicMock()
    return events


def test_a_pan_on_a_screen_the_game_does_not_draw_rests_before_its_lift(context):
    # #907, live 2026-11-22 HARD floor 5: as find_bus's first pan stopped, the screenshot still showed the bus at rest;
    # the game had drawn nothing for 0.3 s and took the drag late. Taken for a pan the map ignored (#486), the finger
    # lifted at once and flung the map, and the pan made again flung it further: the bus ended ~900 px off the left.
    events = touch_times(context)
    stalled, home = ([frame(WEDGE / f"{n}.png") for n in names] for names in (("stalled", "stalled_later"), ("bus_home", "bus_home_later")))
    shots = iter(range(10 ** 6))
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: (home if any(k == "up" for k, _ in events) else stalled)[next(shots) % 2]  # the drag shows once lifted
    context.run_recognition.side_effect = lambda name, image, override=None: bus_seen(image) if name == "MapBus" else None
    image, bus = map_actions.RouteMap.find_bus(context)
    assert bus == (49, 320)
    assert [k for k, _ in events].count("down") == 1
    lift = next(t for k, t in events if k == "up")
    assert lift - max(t for k, t in events if k == "move") >= actions.SCROLL_HOLD  # no fling


def test_a_prompt_over_the_map_that_hides_the_bus_goes_back_to_mirror_hub_at_the_first_look(context, monkeypatch):
    # #907, live 2026-11-22: MirrorHub's first read missed the floor 5 prompt as it faded in over the map and handed the
    # map to RouteMap (18:47:15.4), which looked for the bus once a second, then started search_bus, whose guard saw the
    # prompt: 7.7 s with no tap. The prompt dims the map: no MapBus on it.
    patch_all(monkeypatch, "page_guard", test_actions.REAL_GUARD)
    actions.RUN.update(floor=5, floor_hard=True)
    over_map = frame(SCREENS / "ParallelModePromptOverMap.png")
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: over_map.copy()
    shown = {"MirrorMap", "ParallelModePrompt"}  # tests/screens/ParallelModePromptOverMap.png in maatools.config.mts

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return bus_seen(image)
        return SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name in shown else None
    context.run_recognition.side_effect = run_recognition
    t0 = actions.time.monotonic()
    assert map_actions.RouteMap().run(context, None)
    assert actions.time.monotonic() - t0 < 2  # the first look, and the guard's 1 s look again
    context.tasker.controller.post_touch_down.assert_not_called()
    context.tasker.controller.post_click.assert_not_called()
    assert actions.STUCK["flag"] is None


def test_a_bus_flung_far_off_the_screens_left_is_found_without_l2(context):
    # #907, live 2026-11-22 HARD floor 5: find_bus's pans flung the map ~950 px, the bus ~900 px off the screen's left;
    # search_bus dragged it 250 px down and up and 400 px right and left, found no bus, and RouteMap stopped at
    # "stuck: no bus on the map, even after dragging it about" until L2 put the map back (55 s).
    actions.RUN.update(floor=5, floor_hard=True)
    wedge_world(context, camera=950)
    map_actions.RouteMap().run(context, None)
    assert actions.STUCK["flag"] is None
    assert (328, 357) in [c.args for c in context.tasker.controller.post_click.call_args_list]  # column 1's event
