import datetime as dt
import re

import numpy as np
import pytest

import tap_waits as tw
from maafw_timeline import stamp

PRE = "[DBG][Px1][Tx2][X.cpp][L1]"


def _stamp(t: str) -> str:
    return t if " " in t else f"2026-11-08 09:38:{t}"


def enter(t, node, action):
    return (f"[{_stamp(t)}]{PRE}[MaaNS::TaskNS::CustomAction::run] [context.task_id()=200000001] "
            f"[node_name={node}] [session.action=true] [session.trans_arg=true] [param.name={action}] "
            "[param.custom_param=null] [reco_id=1] [rect=[1,2,3,4]] | enter \n")


def leave(t, node, action):
    return (f"[{_stamp(t)}]{PRE}[MaaNS::TaskNS::CustomAction::run] [node_name={node}] [param.name={action}] "
            "[session.action=true] [session.trans_arg=true] [ret=true] \n")


def click(t, x, y):
    ts = _stamp(t)
    return (f"[{ts}]{PRE}[MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_click] "
            f'[req={{"_ControllerPostClickReverseRequest":1,"contact":0,"controller_id":"0","pressure":1,"x":{x},"y":{y}}}] '
            "[ipc_addr_=ipc://x.sock] | enter \n"
            f"[{ts}]{PRE}[MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_click] | leave, 0ms \n")


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


def test_next_tap_waits_through_the_screenshots_of_a_polling_wait():
    # #567: a wait that polls (tap_then) takes a screenshot every 0.2 s until the page changes, so the next call is its
    # first screenshot, not where the bot went on: that is the next tap, or the action's end.
    lines = [enter("34.000", "Shop", "Shop"), click("34.100", 610, 230), shot("34.150"), shot("34.350"), shot("34.550"),
             click("34.690", 640, 400), shot("34.740"), leave("35.000", "Shop", "Shop")]
    waits = {until: [round(t.look - t.at, 3) for t in tw.taps(lines, {"Shop"}, until)] for until in ("next-call", "next-tap")}
    assert waits == {"next-call": [0.05, 0.05], "next-tap": [0.59, 0.31]}
    assert tw.taps(lines, {"Shop"}) == tw.taps(lines, {"Shop"}, "next-call")


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


BASE_TIME = dt.datetime(2026, 11, 8, 9, 38, 0)


def iso(sec: float) -> str:
    return (BASE_TIME + dt.timedelta(seconds=sec)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def score_line(sec: float, node: str, score: float) -> str:
    return (f"[{iso(sec)}]{PRE}[MaaNS::VisionNS::TemplateMatcher::analyze] {node} "
            f'[all_results_=[{{"box":[0,0,40,40],"score":{score:.6f}}}]]\n')


def action_tap_lines(at_s: float, look_s: float, node: str = "WipeDialog", action: str = "Wipe") -> list[str]:
    return [enter(iso(at_s - 0.1), node, action), click(iso(at_s), 640, 360), leave(iso(look_s), node, action)]


def make_clip(tmp_path, duration: float, fps: int, up_fn, bright_fn=None):
    """Write a small synthetic MJPG video and a 40x40 template that matches at (0,0,80,80) when up_fn(pts) is true."""
    import cv2

    tpl = np.zeros((40, 40, 3), np.uint8)
    tpl[::4, :, :] = 220
    tpl[:, ::4, :] = 180
    tpl_path = tmp_path / "marker.png"
    cv2.imwrite(str(tpl_path), tpl)

    # Video is 320x180 (1/4 of 1280x720); draw the scaled template at (0,0,10,10) so 1280x720 resize places it in (0,0,80,80).
    small_tpl = cv2.resize(tpl, (10, 10))
    vid_path = tmp_path / "rec.avi"
    out = cv2.VideoWriter(str(vid_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 180))
    for i in range(int(duration * fps)):
        pts = i / fps
        bg = int(bright_fn(pts)) if bright_fn else 40
        frame = np.full((180, 320, 3), bg, np.uint8)
        if up_fn(pts):
            frame[2:12, 2:12] = small_tpl
        out.write(frame)
    out.release()
    return vid_path, tpl_path


def count_video_grabs(monkeypatch):
    import cv2

    counts = {"grabs": 0}
    real_cap = cv2.VideoCapture

    class CountingCap:
        def __init__(self, *args, **kwargs):
            self._cap = real_cap(*args, **kwargs)

        def grab(self):
            counts["grabs"] += 1
            return self._cap.grab()

        def __getattr__(self, name):
            return getattr(self._cap, name)

    monkeypatch.setattr(cv2, "VideoCapture", CountingCap)
    return counts


def test_from_to_only_decodes_and_scores_that_slice(tmp_path, monkeypatch, capsys):
    pulses = [(2, 4), (9, 11), (17, 19), (22, 24), (27, 29), (34, 36)]
    offset = 1.0

    def up(pts):
        return any(a <= pts <= b for a, b in pulses)

    # Tap at log 24.0 s (= video 23.0 s), screen jumps from 40 to 200 at video 23.5 s (moved/settled = 0.5 s).
    vid, tpl = make_clip(tmp_path, duration=40.0, fps=10, up_fn=up,
                         bright_fn=lambda pts: 200 if pts >= 23.5 else 40)
    log_path = tmp_path / "maafw.log"
    lines = [score_line(t, "Marker", 0.9 if up(t - offset) else 0.1) for t in np.arange(0.0, 41.0, 0.3)]
    lines += action_tap_lines(6.0, 8.0)    # outside --from/--to
    lines += action_tap_lines(24.0, 26.0)  # inside --from/--to
    lines.sort()
    log_path.write_text("".join(lines), encoding="utf-8")

    counts = count_video_grabs(monkeypatch)
    tw.main([str(vid), "--started", iso(0.0), "--log", str(log_path),
             "--node", "Marker", str(tpl), "0,0,80,80", "0.7",
             "--actions", "Wipe", "--from", iso(20.0), "--to", iso(28.0), "--fps", "10"])
    out, err = capsys.readouterr()

    assert counts["grabs"] < 200  # 40 s * 10 fps = 400 frames total; only the ~14.5 s padded slice should decode
    m = re.search(r"video (\d\d:\d\d:\d\d\.\d{3})-(\d\d:\d\d:\d\d\.\d{3})\s+offset ([+-]\d+\.\d+) s", err)
    assert m, err
    assert m[1] >= "09:38:15.000" and m[2] <= "09:38:33.000", err
    assert abs(float(m[3]) - offset) <= 0.25, err
    assert "1 taps on the video, 0 not" in out, out
    row = re.search(r"\| Wipe \| WipeDialog \| 640,360 \| 1 \| 2\.00 \| ([\d.]+), [\d.]+ \| ([\d.]+), [\d.]+ \| 0 \|", out)
    assert row and 0.3 <= float(row[1]) <= 0.7 and 0.3 <= float(row[2]) <= 0.7, out


def test_partial_log_aligns_to_true_offset_not_earlier_matching_video(tmp_path, monkeypatch, capsys):
    # Two identical 30 s halves of video; only the second half's log is passed (true offset +1.0 s).
    # With the old --max-lost 7200 and full-video scan, chunk 0 locked onto the second half at +31.0 s.
    pulses_30 = [(2, 4), (7, 9), (16, 18), (23, 25)]
    offset = 1.0

    def up(pts):
        return any(a <= pts % 30 <= b for a, b in pulses_30)

    vid, tpl = make_clip(tmp_path, duration=60.0, fps=5, up_fn=up,
                         bright_fn=lambda pts: 200 if pts >= 44.4 else 40)
    log_path = tmp_path / "partial.log"
    lines = [score_line(t, "Marker", 0.9 if up(t - offset) else 0.1) for t in np.arange(31.0, 61.0, 0.3)]
    lines += action_tap_lines(45.0, 47.0)  # video 44.0 s -> 46.0 s
    lines.sort()
    log_path.write_text("".join(lines), encoding="utf-8")

    counts = count_video_grabs(monkeypatch)
    tw.main([str(vid), "--started", iso(0.0), "--log", str(log_path),
             "--node", "Marker", str(tpl), "0,0,80,80", "0.7",
             "--actions", "Wipe", "--fps", "5", "--chunk", "15"])
    out, err = capsys.readouterr()

    assert counts["grabs"] < 200  # 60 s * 5 fps = 300 frames total; seeks near the partial log instead of starting at 0
    offsets = [float(x) for x in re.findall(r"offset ([+-]\d+\.\d+) s", err)]
    assert offsets and all(abs(o - offset) <= 0.25 for o in offsets), err
    assert "1 taps on the video, 0 not" in out, out


def test_ambiguous_or_unaligned_partial_log_exits_with_error(tmp_path):
    # Periodic pulses every 5 s with --max-lost 10 make +1 s and +6 s tie over the full slice: must exit with an error.
    def up(pts):
        return (pts % 5.0) < 1.5

    vid, tpl = make_clip(tmp_path, duration=30.0, fps=5, up_fn=up)
    log_path = tmp_path / "periodic.log"
    lines = [score_line(t, "Marker", 0.9 if up(t - 1.0) else 0.1) for t in np.arange(11.0, 35.0, 0.3)]
    lines += action_tap_lines(18.0, 20.0)
    lines.sort()
    log_path.write_text("".join(lines), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        tw.main([str(vid), "--started", iso(0.0), "--log", str(log_path),
                 "--node", "Marker", str(tpl), "0,0,80,80", "0.7",
                 "--actions", "Wipe", "--from", iso(14.0), "--to", iso(22.0),
                 "--fps", "5", "--chunk", "20", "--max-lost", "10"])
    assert exc.value.code != 0 and "align" in str(exc.value).lower()


def test_partial_log_beyond_default_max_lost_exits_with_error(tmp_path):
    # Video and partial log shifted by +15 s (past default --max-lost): must report failure, not silently lock wrong.
    pulses = [(1, 3), (6, 8), (15, 17), (20, 22), (31, 33), (39, 41)]

    def up(pts):
        return any(a <= pts <= b for a, b in pulses)

    vid, tpl = make_clip(tmp_path, duration=45.0, fps=5, up_fn=up)
    log_path = tmp_path / "shifted.log"
    lines = [score_line(t, "Marker", 0.9 if up(t - 15.0) else 0.1) for t in np.arange(20.0, 45.0, 0.3)]
    lines += action_tap_lines(25.0, 27.0)
    lines.sort()
    log_path.write_text("".join(lines), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        tw.main([str(vid), "--started", iso(0.0), "--log", str(log_path),
                 "--node", "Marker", str(tpl), "0,0,80,80", "0.7",
                 "--actions", "Wipe", "--fps", "5", "--chunk", "15"])
    assert exc.value.code != 0 and "align" in str(exc.value).lower()
