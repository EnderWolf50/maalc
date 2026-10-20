"""#194: the map zoomed in on the bus after backing out of a node's formation, reset before RouteMap reads it."""
from types import SimpleNamespace

import actions
import test_actions

clock, context = test_actions.clock, test_actions.context  # its fixtures

ZOOMED = (291, 216, 86, 76)  # MapBusZoomed's box on MapZoomed.png


def zoomed_map(context, back="resets"):
    """MapBus misses and MapBusZoomed hits until the node panel has been opened and closed.

    back: what the back key does on the panel: "resets" the map, "closes" it still zoomed, "nothing" at all.
    """
    state = {"panel": False, "reset": False}
    ctl = context.tasker.controller

    def click(x, y):
        bx, by, w, h = ZOOMED
        if not state["reset"] and bx <= x < bx + w and by <= y < by + h:
            state["panel"] = True
        return SimpleNamespace(wait=lambda: None)
    ctl.post_click.side_effect = click

    def close(*args):
        if state["panel"] and back != "nothing":
            state["panel"], state["reset"] = False, back == "resets"
        return SimpleNamespace(wait=lambda: None)
    ctl.post_click_key.side_effect = close

    def run_recognition(name, image, override=None):
        if name == "MapNodePanel":
            return SimpleNamespace(hit=True, box=[0, 0, 10, 10]) if state["panel"] else None
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[*actions.BUS_HOME, 48, 42]) if state["reset"] else None
        if name == "MapBusZoomed":
            return None if state["reset"] else SimpleNamespace(hit=True, box=list(ZOOMED))
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if state["reset"] and name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    return state


def test_a_zoomed_map_is_reset_through_the_bus_node_panel_and_read_as_usual(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True  # the node was entered, then its formation backed out of
    actions.RUN["map_plan"] = {"floor": None, "steps": [("mid", "battle")]}  # the step after that node
    zoomed_map(context)
    actions.RouteMap().run(context, None)
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    bx, by, w, h = ZOOMED
    assert taps[0] == (bx + w // 2, by + h // 2)  # the zoomed bus: its node panel zooms the same way
    bx, by = actions.BUS_HOME
    assert taps[1] == (bx + 22, by + 37)  # back at rest: the bus first, not the plan's next slot (#88)
    assert actions.STUCK["flag"] is None or actions.STUCK["flag"][1] == 1  # no L2


def test_a_zoomed_map_the_panel_does_not_reset_goes_to_l2_at_once(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    actions.RUN["map_entered"] = True
    zoomed_map(context, back="closes")
    actions.RouteMap().run(context, None)
    assert actions.STUCK["flag"][1] == 2
    assert len(context.tasker.controller.post_click.call_args_list) == 1  # no blind taps on a zoomed map


def test_a_node_panel_the_back_key_leaves_up_is_entered_not_handed_to_l2(context):
    # L2 starts from the map's gear; over the panel it would not go through and would climb to L3.
    actions.RUN["map_entered"] = True
    zoomed_map(context, back="nothing")
    actions.RouteMap().run(context, None)
    assert context.tasker.controller.post_click.call_args_list[-1].args == actions.ENTER
    assert actions.STUCK["flag"] is None or actions.STUCK["flag"][1] == 1


def test_a_map_at_rest_never_looks_for_the_zoomed_bus(context, monkeypatch):
    monkeypatch.setattr(actions, "map_weights", lambda context: {"battle": 2, "unknown": 9})
    looked = []

    def run_recognition(name, image, override=None):
        looked.append(name)
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[*actions.BUS_HOME, 48, 42])
        return SimpleNamespace(hit=True, box=[0, 0, 26, 24]) if name in ("MapLinkMid", "MapNodeCost") else None
    context.run_recognition.side_effect = run_recognition
    actions.RouteMap().run(context, None)
    assert "MapBusZoomed" not in looked
