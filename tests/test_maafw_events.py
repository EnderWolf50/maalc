import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("maafw_events", Path(__file__).resolve().parent.parent / "tools/live/maafw_events.py")
me = importlib.util.module_from_spec(spec)
spec.loader.exec_module(me)

AGENT = "[2026-10-18 {t}][DBG][Px1][Tx2][AgentClient.cpp][L2005][MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_{k}] [req={req}] [ipc_addr_=x]"
MUMU_DOWN = "[2026-10-18 {t}][INF][Px1][Tx3][MuMuPlayerExtras.cpp][L133][MaaNS::CtrlUnitNs::MuMuPlayerExtras::touch_down] [contact=0] [x={x}] [y={y}] [pressure=1] [display_id=0] "
MUMU_UP = "[2026-10-18 {t}][INF][Px1][Tx3][MuMuPlayerExtras.cpp][L180][MaaNS::CtrlUnitNs::MuMuPlayerExtras::touch_up] [contact=0] [display_id=0] "


def events(lines):
    doc = me.parse(lines)
    assert doc["space"] == [1280, 720]
    return doc["events"]


def test_agent_click_with_its_mumu_touch_is_one_tap_in_game_coords():
    assert events([
        AGENT.format(t="14:30:14.710", k="click", req='{"contact":0,"pressure":1,"x":1108,"y":494}'),
        MUMU_DOWN.format(t="14:30:14.710", x=1662, y=741),
        MUMU_UP.format(t="14:30:14.762"),
    ]) == [{"t": "14:30:14.710", "kind": "tap", "x": 1108, "y": 494}]


def test_pipeline_tap_seen_only_by_mumu_is_scaled_to_1280x720_with_its_hold_time():
    assert events([MUMU_DOWN.format(t="14:31:59.235", x=408, y=836), MUMU_UP.format(t="14:31:59.287")]) == [
        {"t": "14:31:59.235", "kind": "tap", "x": 272, "y": 557, "ms": 52}]


def test_touch_down_move_up_gives_down_and_up_at_the_last_point():
    assert events([
        AGENT.format(t="14:30:53.077", k="touch_down", req='{"contact":0,"x":852,"y":391}'),
        MUMU_DOWN.format(t="14:30:53.078", x=1278, y=586),
        AGENT.format(t="14:30:53.500", k="touch_move", req='{"contact":0,"x":600,"y":400}'),
        AGENT.format(t="14:30:53.950", k="touch_up", req='{"contact":0}'),
        MUMU_UP.format(t="14:30:53.951"),
    ]) == [{"t": "14:30:53.077", "kind": "down", "x": 852, "y": 391},
           {"t": "14:30:53.950", "kind": "up", "x": 600, "y": 400}]


def test_swipe_carries_its_end_point_and_duration():
    assert events([AGENT.format(t="14:30:50.340", k="swipe", req='{"duration":600,"x1":444,"x2":444,"y1":330,"y2":650}')]) == [
        {"t": "14:30:50.340", "kind": "swipe", "x": 444, "y": 330, "x2": 444, "y2": 650, "ms": 600}]


def test_two_pipeline_taps_within_250ms_at_one_point_stay_two():
    assert [e["t"] for e in events([
        MUMU_DOWN.format(t="14:31:59.000", x=408, y=836), MUMU_UP.format(t="14:31:59.040"),
        MUMU_DOWN.format(t="14:31:59.100", x=408, y=836), MUMU_UP.format(t="14:31:59.140"),
    ])] == ["14:31:59.000", "14:31:59.100"]
