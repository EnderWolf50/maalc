import json

import numpy as np
import pytest
from PIL import Image

from live import evidence as ev

# A run.log as `bot.py run` writes it: the bot's stdout, a wall time per line.
RUN = """\
15:52:51.591 [maalc] floor 1 packs, threshold 0: Flat-broke Gamblers (0), Nagel und Hammer (0), Automated Factory (-2, event)
15:52:51.700 [maalc] floor 1: pull Flat-broke Gamblers (0)
15:52:55.967 [maalc] map: node at 328, 357 reads Cost 75: battle
15:52:56.365 [maalc] map: column 1: mid battle (1 onward), up event (2 onward)
15:52:56.600 [maalc] map: node at 583, 357 reads Cost None: risky
15:52:56.916 [maalc] map: column 2: mid risky (from mid/up)
15:52:57.531 [maalc] map: column 3: up battle (from up)
15:52:58.000 x: 1600, y: 540, width: 1920, height: 1080, rotation: 90.000000, product_major: 0
15:52:58.000 after convert, x_point: 540, y_point: 1600
15:52:58.100 x: 1500, y: 540, width: 1920, height: 1080, rotation: 90.000000, product_major: 0
15:52:58.200 x: 1400, y: 540, width: 1920, height: 1080, rotation: 90.000000, product_major: 0
15:52:59.245 [maalc] map: dragged the map 510 px; reading on from column 3
15:52:59.477 [maalc] map: node at 327, 144 reads Cost 120: risky
15:52:59.693 [maalc] map: column 3: up event (from up)
15:53:00.344 [maalc] map: column 4: mid shop (from up)
15:53:03.523 [maalc] map: path up event > mid risky > up event > mid shop, score 22
15:53:04.000 x: 900, y: 300, width: 1920, height: 1080, rotation: 90.000000, product_major: 0
15:53:05.492 [maalc] map: take up event
"""


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "run.log"
    p.write_text(RUN, encoding="utf-8")
    return ev.read_log(p)


def test_read_log_takes_bot_py_and_mxu_stamps():
    lines = ["15:52:51.591 [maalc] hello", "2026-10-14 10:31:21 [stdout] [maalc] mxu", "no stamp"]
    assert [(round(t, 3), x) for t, x in ev.parse_log(lines)] == [(57171.591, "[maalc] hello"), (37881.0, "[maalc] mxu")]
    assert ev.hms(57171.591) == "15:52:51.591"


def test_events_join_a_touch_burst_into_one_swipe_and_keep_single_taps(log):
    doc = ev.touches(log, ev.secs("15:52:57"), ev.secs("15:53:10"))
    assert doc["space"] == [1920, 1080]
    assert doc["events"] == [
        {"t": "15:52:58.000", "kind": "swipe", "x": 1600, "y": 540, "x2": 1400, "y2": 540, "ms": 200},
        {"t": "15:53:04.000", "kind": "tap", "x": 900, "y": 300}]


def test_events_read_maafw_log_through_maafw_events(tmp_path):
    p = tmp_path / "maafw.log"
    p.write_text("[2026-10-18 14:30:14.710][DBG][Px1][Tx2][AgentClient.cpp][L2005][MaaNS::AgentNS::ClientNS::AgentClient::"
                 'handle_controller_post_click] [req={"contact":0,"x":1108,"y":494}] [ipc_addr_=x]\n', encoding="utf-8")
    out = tmp_path / "events.json"
    ev.main(["events", str(p), "-o", str(out)])
    assert json.loads(out.read_text())["events"] == [{"t": "14:30:14.710", "kind": "tap", "x": 1108, "y": 494}]


def test_steps_caption_each_maalc_line_until_the_next_or_hold(log):
    steps = ev.captions(log, ev.secs("15:53:00"), ev.secs("15:53:10"), "map: (path|take)", hold=1.5)
    assert steps == [
        {"from": "15:53:03.523", "to": "15:53:05.023", "title": "map: path up event > mid risky > up event > mid shop, score 22"},
        {"from": "15:53:05.492", "to": "15:53:06.992", "title": "map: take up event"}]


def test_footage_finds_the_piece_that_covers_a_time():
    f = ev.Footage(["a.mp4@10:00:00", "b.mp4@10:05:00.5"])
    assert f.locate(ev.secs("10:04:00")) == ("a.mp4", 240.0)
    assert f.locate(ev.secs("10:05:01")) == ("b.mp4", 0.5)
    with pytest.raises(SystemExit):
        f.locate(ev.secs("09:00:00"))


def test_frames_and_clip_seek_into_the_right_piece(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ev, "decode", lambda path, ss, dur, fps, gray=False: (calls.append((path, ss, dur, fps)),
                                                                              np.zeros((1, 720, 1280, 3), np.uint8))[1])
    monkeypatch.setattr(ev.subprocess, "run", lambda cmd, check: calls.append(cmd))
    monkeypatch.setattr(ev, "masks_path", lambda a: "masks.json")
    monkeypatch.setattr(ev, "load_masks", lambda path: ("masks", path))
    masked = []
    monkeypatch.setattr(ev, "apply_masks", lambda im, masks: (masked.append(masks), im)[1])
    ev.main(["frames", "--video", "a.mp4@10:00:00", "-o", str(tmp_path), "10:00:02.5"])
    assert calls[0] == ("a.mp4", 2.5, None, None) and (tmp_path / "10-00-02.500.png").exists()
    assert masked == [("masks", "masks.json")]  # a frame leaves masked
    ev.main(["clip", "--video", "a.mp4@10:00:00", "--from", "10:00:01", "--to", "10:00:04", "-o", "c.mp4"])
    assert calls[1][calls[1].index("-ss") + 1] == "1.000" and calls[1][calls[1].index("-t") + 1] == "3.000"


def test_map_block_reads_columns_costs_drags_and_path(log):
    stages, drags, path = ev.parse_map(ev.floor_block(ev.maalc(log), 1))
    assert drags == [(ev.secs("15:52:59.245"), 510, 3)]
    assert path == ([("up", "event"), ("mid", "risky"), ("up", "event"), ("mid", "shop")], 22)
    nodes = ev.node_table(stages, drags)
    assert nodes[(1, "mid")] == {"type": "battle", "first": "battle", "cost": "75"}
    assert nodes[(3, "up")] == {"type": "event", "first": "battle", "cost": "120"}  # read again after the drag
    assert nodes[(2, "mid")]["cost"] == "None"  # a coin with no number read: labelled "Cost 沒讀到"
    assert nodes[(4, "mid")]["cost"] is None  # no Cost line at all


@pytest.fixture
def footage(monkeypatch):
    """A recording of the fixture's floor: the map slides 15:52:58.5-59.0, the pack cards deal 15:52:48.6-50.6."""
    drag, deal, still = ev.secs("15:52:58.5"), ev.secs("15:52:48.6"), ev.secs("15:52:50.6")

    def fake_frames(f, t0, t1, fps, gray=False):
        times = [t0 + i / fps for i in range(round((t1 - t0) * fps))]
        out = []
        for i, t in enumerate(times):
            if t0 > ev.secs("15:52:55"):  # the map
                v = 40 * min(5, max(0, int((t - drag) * 10)))
            else:  # the pack page: empty, dealing (every frame differs), standing still
                v = 0 if t < deal else 30 + 10 * (i % 2) if t < still else 40
            out.append(np.full((720, 1280), v, np.uint8))
        return times, np.array(out)

    monkeypatch.setattr(ev, "frames", fake_frames)
    monkeypatch.setattr(ev, "grab", lambda f, t: Image.new("RGB", (1280, 720), (20, 20, 20)))
    monkeypatch.setattr(ev, "masks_path", lambda a: None)
    monkeypatch.setattr(ev, "load_masks", lambda path: ([1280, 720], []))
    return ["--video", "rec.mp4@15:50:00"]


def test_map_command_writes_the_stitched_floor_and_its_nodes(tmp_path, footage):
    (tmp_path / "run.log").write_text(RUN, encoding="utf-8")
    ev.main(["map", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "route"), *footage])
    route = json.loads((tmp_path / "route/route.json").read_text(encoding="utf-8"))
    assert Image.open(tmp_path / "route/stitched.png").size == (1790, 720)
    assert route["path"]["score"] == 22 and len(route["nodes"]) == 5 and len(route["shots"]) == 2
    assert (tmp_path / "route/before-1.png").exists() and (tmp_path / "route/after-1.png").exists()


def test_packs_command_measures_deal_to_still(tmp_path, footage):
    (tmp_path / "run.log").write_text(RUN, encoding="utf-8")
    ev.main(["packs", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "packs"), *footage])
    [r] = json.loads((tmp_path / "packs/packs.json").read_text(encoding="utf-8"))
    assert r["pull"] == "Flat-broke Gamblers" and r["settle_s"] == pytest.approx(2.0, abs=0.05)
    assert (tmp_path / "packs/pack-1.png").exists()


def test_map_picks_the_still_frame_before_and_after_each_drag():
    still = np.zeros((720, 1280), np.uint8)
    sliding = [np.full((720, 1280), 40 * k, np.uint8) for k in range(1, 6)]
    grays = [still] * 10 + sliding + [still] * 10  # the map slides from frame 10 to 14
    times = [100 + i / 10 for i in range(len(grays))]
    mov = ev.motion(grays)
    assert ev.runs(mov) == [(10, 15)]
    assert ev.pick_shots(times, mov, [(101.6, 510, 3)]) == [8, 18]


def test_map_draw_boxes_every_read_node_and_marks_a_fix():
    shots = [Image.new("RGB", (1280, 720)), Image.new("RGB", (1280, 720), (40, 40, 40))]
    nodes = {(1, "mid"): {"type": "battle", "first": "battle", "cost": "75"},
             (2, "down"): {"type": "risky", "first": "event", "cost": "20"}}
    fix = {"c2/down": ["cost", "讀成 20（畫面是 120）"], "c3/up": ["missed", "沒讀到的 event"]}
    im = ev.draw_map(shots, [(0, 510, 3)], nodes, ([("mid", "battle"), ("down", "risky")], 7), fix, 1)
    assert im.size == (1790, 720)
    px = np.asarray(im)
    assert tuple(px[357 - 52, 328]) == ev.GREEN  # read right
    assert tuple(px[570 - 52, 583]) == ev.ORANGE  # Cost read wrong
    assert tuple(px[144 - 52, 838]) == ev.ORANGE  # a node the bot did not list


def test_packs_reading_names_weights_event_and_pull(log):
    [r] = ev.pack_readings(ev.maalc(log), 1)
    assert r["cards"] == [("Flat-broke Gamblers", 0, False), ("Nagel und Hammer", 0, False), ("Automated Factory", -2, True)]
    assert (r["threshold"], r["pull"]) == (0, "Flat-broke Gamblers")


def test_packs_settle_runs_from_the_deal_to_eight_still_frames():
    rows = [(0, 0)] * 5 + [(30, 9)] * 20 + [(40, 1)] * 20  # empty, dealing and swinging, standing still
    assert ev.settle(rows, k_log=30) == (5, 25, False)
    assert ev.settle([(40, 1)] * 20, k_log=5) == (0, 0, True)  # the deal started before the footage
    # floor 1 of 2026-10-22: the screen fades in, then the cards leave a starfield of mean 6.7 before the deal
    rows = [(0.4, 0)] * 3 + [(35, 3)] * 10 + [(6.7, 9)] * 4 + [(30, 9)] * 20 + [(40, 1)] * 20
    assert ev.settle(rows, k_log=50)[0] == 17


def test_packs_draw_puts_a_thick_border_on_the_pulled_card():
    r = {"cards": [("A", 0, False), ("B", 3, True)], "pull": "B"}
    px = np.asarray(ev.draw_packs(Image.new("RGB", (1280, 720)), r, "banner"))
    x_b = int(ev.centres(2)[1])
    assert tuple(px[300, x_b - 105 + 6]) == ev.GREEN and tuple(px[300, int(ev.centres(2)[0]) - 105 + 6]) != ev.YELLOW


def test_mask_blacks_out_boxes_where_the_template_matches(tmp_path):
    pytest.importorskip("cv2")
    rng = np.random.default_rng(0)
    screen = rng.integers(0, 255, (720, 1280, 3), np.uint8)
    Image.fromarray(screen[100:140, 50:250]).save(tmp_path / "tpl.png")
    (tmp_path / "masks.json").write_text(json.dumps(
        {"space": [1280, 720], "masks": [{"template": "tpl.png", "threshold": 0.8, "boxes": [[300, 600, 50, 20]]},
                                         {"template": "tpl.png", "threshold": 1.01, "boxes": [[0, 0, 10, 10]]}]}))
    shot = tmp_path / "shot.png"
    Image.fromarray(screen).save(shot)
    ev.main(["mask", "--masks", str(tmp_path / "masks.json"), str(shot)])
    px = np.asarray(Image.open(shot))
    assert px[600:620, 300:350].max() == 0 and px[0:10, 0:10].max() > 0
