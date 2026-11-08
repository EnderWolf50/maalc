import numpy as np

import tap_waits as tw
from maafw_timeline import stamp

PRE = "[DBG][Px1][Tx2][X.cpp][L1]"


def enter(t, node, action):
    return (f"[2026-11-08 09:38:{t}]{PRE}[MaaNS::TaskNS::CustomAction::run] [context.task_id()=200000001] "
            f"[node_name={node}] [session.action=true] [session.trans_arg=true] [param.name={action}] "
            "[param.custom_param=null] [reco_id=1] [rect=[1,2,3,4]] | enter \n")


def leave(t, node, action):
    return (f"[2026-11-08 09:38:{t}]{PRE}[MaaNS::TaskNS::CustomAction::run] [node_name={node}] [param.name={action}] "
            "[session.action=true] [session.trans_arg=true] [ret=true] \n")


def click(t, x, y):
    return (f"[2026-11-08 09:38:{t}]{PRE}[MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_click] "
            f'[req={{"_ControllerPostClickReverseRequest":1,"contact":0,"controller_id":"0","pressure":1,"x":{x},"y":{y}}}] '
            "[ipc_addr_=ipc://x.sock] | enter \n"
            f"[2026-11-08 09:38:{t}]{PRE}[MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_click] | leave, 0ms \n")


def shot(t):
    return (f"[2026-11-08 09:38:{t}]{PRE}[MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_screencap] "
            '[req={"_ControllerPostScreencapReverseRequest":1,"controller_id":"0"}] [ipc_addr_=ipc://x.sock] \n')


def at(t):
    return stamp(f"2026-11-08 09:38:{t}")


def test_a_tap_looks_again_at_the_next_call_or_the_action_end():
    lines = [enter("34.000", "WipeDialog", "Wipe"), shot("34.100"), click("34.507", 790, 354), click("35.761", 645, 527),
             shot("38.311"), click("38.400", 1, 1), leave("38.500", "WipeDialog", "Wipe"),
             enter("39.000", "BattleTurn", "PlayTurn"), click("39.100", 5, 5), leave("39.200", "BattleTurn", "PlayTurn")]
    got = tw.taps(lines, {"Wipe"})
    assert [(t.node, t.x, t.y, round(t.look - t.at, 3)) for t in got] == [
        ("WipeDialog", 790, 354, 1.254), ("WipeDialog", 645, 527, 2.55), ("WipeDialog", 1, 1, 0.1)]
    assert got[0].at == at("34.507")


def frames(spec):
    """Log times every 1/30 s from -0.5 s, and a thumbnail per frame: spec(t) is its brightness, all blocks alike."""
    lt = np.arange(-0.5, 3.0, 1 / 30)
    return lt, [np.full((18, 32), float(spec(t))) for t in lt]


def tap(look=2.5):
    return tw.Tap(0.0, "Wipe", "WipeDialog", 1, 1, look)


def test_moved_is_the_first_change_and_settled_the_start_of_the_screen_at_the_look():
    # the old page until 0.3 s, a fade to 0.9 s, the new page from there
    lt, thumbs = frames(lambda t: 100 if t < 0.3 else 200 if t >= 0.9 else 100 + 100 * (t - 0.3) / 0.6)
    moved, settled = tw.measure(tap(), lt, thumbs)
    assert 0.33 <= moved <= 0.4  # the first frame a block is more than 8 levels off: 8/100 of the fade in
    assert 0.85 <= settled <= 0.9  # the first frame within 8 levels of the new page: 92/100 of the fade in


def test_a_tap_with_no_change_has_no_moved_and_settled_0():
    lt, thumbs = frames(lambda t: 100)
    assert tw.measure(tap(), lt, thumbs) == (None, 0.0)


def test_a_tap_the_aligned_video_does_not_cover_is_none():
    lt, thumbs = frames(lambda t: 100)
    lt = lt.copy()
    lt[40] = np.nan  # a frame of an unaligned chunk
    assert tw.measure(tap(), lt, thumbs) is None
    assert tw.measure(tw.Tap(10.0, "Wipe", "WipeDialog", 1, 1, 11.0), *frames(lambda t: 100)) is None


def test_table_counts_taps_that_never_moved():
    rows = [{"action": "Wipe", "node": "WipeDialog", "x": 1, "y": 1, "wait": 2.5, "moved": m, "settled": s}
            for m, s in [(0.2, 0.8), ("", 0.0), (0.4, 1.2)]]
    assert tw.table(rows).splitlines()[-1] == "| Wipe | WipeDialog | 1,1 | 3 | 2.50 | 0.30, 0.40 | 0.80, 1.20 | 1 |"
