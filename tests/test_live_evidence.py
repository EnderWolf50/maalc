import json
from pathlib import Path

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


def test_steps_caption_each_maalc_line_until_the_next_or_hold(log, tmp_path):
    steps = ev.captions(log, ev.secs("15:53:00"), ev.secs("15:53:10"), "map: (path|take)", hold=1.5)
    assert steps == [
        {"from": "15:53:03.523", "to": "15:53:05.023", "title": "map: path up event > mid risky > up event > mid shop, score 22"},
        {"from": "15:53:05.492", "to": "15:53:06.992", "title": "map: take up event"}]
    ev.main(["steps", str(tmp_path / "run.log"), "--from", "15:53:00", "--to", "15:53:10", "--grep", "map: (path|take)",
             "--hold", "1.5", "-o", str(tmp_path / "steps.json")])
    assert json.loads((tmp_path / "steps.json").read_text(encoding="utf-8")) == steps


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
    (masks := tmp_path / "masks.json").write_text("{}")
    monkeypatch.setattr(ev, "load_masks", lambda path: ("masks", path))
    masked = []
    monkeypatch.setattr(ev, "apply_masks", lambda im, found: (masked.append(found), im)[1])
    ev.main(["frames", "--video", "a.mp4@10:00:00", "--masks", str(masks), "-o", str(tmp_path), "10:00:02.5"])
    assert calls[0] == ("a.mp4", 2.5, None, None) and (tmp_path / "10-00-02.500.png").exists()
    assert masked == [("masks", masks)]  # a frame leaves masked
    monkeypatch.setattr(ev, "local_dir", lambda *parts: tmp_path)
    ev.main(["clip", "--video", "a.mp4@10:00:00", "--from", "10:00:01", "--to", "10:00:04", "-o", str(tmp_path / "c.mp4")])
    assert calls[1][calls[1].index("-ss") + 1] == "1.000" and calls[1][calls[1].index("-t") + 1] == "3.000"
    with pytest.raises(SystemExit):  # an unmasked cut stays in .local/
        ev.main(["clip", "--video", "a.mp4@10:00:00", "--from", "10:00:01", "--to", "10:00:04", "-o", str(tmp_path.parent / "c.mp4")])
    with pytest.raises(SystemExit) as e:  # clip takes no masks: annotate.py masks it
        ev.main(["clip", "--video", "a.mp4@10:00:00", "--masks", "m.json", "--from", "10:00:01", "--to", "10:00:04",
                 "-o", str(tmp_path / "c.mp4")])
    assert e.value.code == 2  # argparse's unknown option, not the .local/ check


def test_map_block_reads_columns_costs_drags_and_path(log):
    stages, drags, path = ev.parse_map(ev.floor_block(ev.maalc(log), 1))
    assert drags == [(ev.secs("15:52:59.245"), 510, 3)]
    assert path == ([("up", "event"), ("mid", "risky"), ("up", "event"), ("mid", "shop")], 22)
    nodes = ev.node_table(stages, drags)
    read = lambda key: {k: nodes[key][k] for k in ("type", "first", "cost", "stage")}  # noqa: E731
    assert read((1, "mid")) == {"type": "battle", "first": "battle", "cost": "75", "stage": 0}
    assert read((3, "up")) == {"type": "event", "first": "battle", "cost": "120", "stage": 1}  # read again after the drag
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
    assert Image.open(tmp_path / "route/stitched.png").size[0] == 1790  # 1280 + the 510 px drag: no frame to measure, the log's px stand
    assert route["path"]["score"] == 22 and len(route["nodes"]) == 5 and len(route["shots"]) == 2
    assert (tmp_path / "route/before-1.png").exists() and (tmp_path / "route/after-1.png").exists()


def test_map_clip_cuts_into_local_not_beside_the_output(tmp_path, footage, monkeypatch):
    (tmp_path / "run.log").write_text(RUN, encoding="utf-8")
    local, cuts, runs = tmp_path / "local", [], []
    local.mkdir()
    monkeypatch.setattr(ev, "local_dir", lambda *parts: local)
    monkeypatch.setattr(ev, "cut", lambda f, t0, t1, out: (cuts.append(Path(out)), Path(out).write_text("raw")))
    monkeypatch.setattr(ev.subprocess, "run", lambda cmd, check: runs.append(cmd))
    ev.main(["map", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "route"), "--clip", *footage])
    assert cuts[0].parent == local and not cuts[0].exists()  # the unmasked cut is gone once annotate.py ran
    assert runs[0][runs[0].index("-o") + 1] == str(tmp_path / "route/drag-clip.mp4")


def test_packs_command_measures_deal_to_still(tmp_path, footage):
    (tmp_path / "run.log").write_text(RUN, encoding="utf-8")
    ev.main(["packs", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "packs"), *footage])
    [r] = json.loads((tmp_path / "packs/packs.json").read_text(encoding="utf-8"))
    assert r["pull"] == "Flat-broke Gamblers" and r["settle_s"] == pytest.approx(2.0, abs=0.05)
    assert (tmp_path / "packs/pack-1.png").exists()


def test_map_picks_the_still_map_each_reading_saw_not_the_drag_back():
    """Run 11, floor 1 (2026-10-24): two drags, then the bot drags the map back. The old pick took the last motion
    run that ended within a second of the second `dragged` line: the drag back, so after-2 showed the map of after-1."""
    grey = lambda v, n: [np.full((720, 1280), v, np.uint8)] * n  # noqa: E731
    grays = (grey(0, 10) + grey(99, 3) + grey(10, 12)  # still; drag 1 (frames 10-12); still 13-24
             + grey(150, 3) + grey(20, 12)  # drag 2 (25-27); still 28-39
             + grey(190, 3) + grey(30, 10))  # the drag back (40-42), the map as it was after drag 1
    times = [100 + i / 10 for i in range(len(grays))]
    # the readings: the floor's first (100.5), after drag 1 (log 101.9), after drag 2 (log 103.8, the drag back starts at 104.0)
    idx = ev.pick_shots(times, ev.motion(grays), [100.5, 101.9, 103.8])
    assert [int(grays[i][0, 0]) for i in idx] == [0, 10, 20]


def noise(w, seed=1):
    return np.random.default_rng(seed).integers(0, 255, (720, w), dtype=np.uint8)


def test_map_measures_the_slide_between_two_still_frames():
    world = noise(2000)
    prev, cur = world[:, 0:1280], world[:, 507:1787]
    shift, score = ev.measure_shift(prev, cur, 512)
    assert shift == 507 and score > 0.95
    assert ev.measure_shift(prev, noise(1280, 2), 512) is None  # unrelated frames: nothing to trust


def test_map_stitches_by_the_measured_slide_and_the_still_frames(tmp_path, monkeypatch):
    """Two drags the log calls 512 px each (the second really moved 480: the map's end), then a drag back."""
    world = noise(1280 + 512 + 480)
    moves = [(5.0, 512), (9.0, 992), (13.0, 512)]  # the map slides to this scroll over 0.4 s from this second

    def scroll(t):
        cur = 0
        for t0, to in moves:
            cur = to if t >= t0 + 0.4 else int(cur + (to - cur) * (t - t0) / 0.4) if t >= t0 else cur
        return cur

    base = ev.secs("12:00:00")
    stale = noise(1280, 3)  # the last floor's map, still up while the log waits for this floor's (until 0.9 s)
    frame = lambda t: stale if t - base < 0.9 else world[:, scroll(t - base):scroll(t - base) + 1280]  # noqa: E731

    def fake_frames(f, t0, t1, fps, gray=False):
        times = [t0 + i / fps for i in range(round((t1 - t0) * fps))]
        return times, np.array([frame(t) for t in times])

    monkeypatch.setattr(ev, "frames", fake_frames)
    monkeypatch.setattr(ev, "grab", lambda f, t: Image.fromarray(np.repeat(frame(t)[..., None], 3, axis=2)))
    monkeypatch.setattr(ev, "masks_path", lambda a: None)
    monkeypatch.setattr(ev, "load_masks", lambda path: ([1280, 720], []))
    (tmp_path / "run.log").write_text(MULTI_DRAG, encoding="utf-8")
    ev.main(["map", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "r"), "--video", "x.mp4@12:00:00"])
    route = json.loads((tmp_path / "r/route.json").read_text(encoding="utf-8"))
    assert [d["px"] for d in route["drags"]] == [512, 512] and [d["measured"] for d in route["drags"]] == [512, 480]
    stitched = np.asarray(Image.open(tmp_path / "r/stitched.png").convert("RGB"))
    assert stitched.shape[1] == world.shape[1]  # 1280 + 512 + 480
    assert (stitched[40:80, :, 0] == world[40:80]).all()  # the world seamless, rows between the banner and the boxes
    assert len(set(route["shots"])) == 3


MULTI_DRAG = """\
12:00:00.500 [maalc] floor 1: pull Pack (0)
12:00:00.600 [maalc] map: floor 0's map is up, floor 1 next; waiting for it
12:00:01.000 [maalc] map: column 1: mid battle (1 onward)
12:00:01.200 [maalc] map: column 4: mid battle (from mid)
12:00:06.200 [maalc] map: dragged the map 512 px; reading on from column 3
12:00:06.400 [maalc] map: column 6: mid event (from mid)
12:00:10.200 [maalc] map: dragged the map 512 px; reading on from column 5
12:00:10.400 [maalc] map: column 6: mid boss (from mid)
12:00:14.300 [maalc] map: path mid battle > mid event > mid boss, score 9
"""

NOTES = """\
15:00:00.100 [maalc] map: node at 328, 357 reads Cost None: battle
15:00:00.200 [maalc] map: Cost miss at 328, 570 (normal): one digit, OCR '7', crop logs/cost/a.png
15:00:00.300 [maalc] map: node at 328, 570 reads Cost None: battle
15:00:00.400 [maalc] map: column 1: mid battle (1 onward), down battle (2 onward), up event (2 onward)
15:00:00.500 [maalc] map: node at 583, 357 reads Cost 200: boss
15:00:00.600 [maalc] map: column 2: the boss' glow without a shop before it
15:00:00.700 [maalc] map: column 2: mid boss (from mid)
15:00:00.800 [maalc] map: column 3: after the shop, so the boss; up event read as something else
15:00:00.900 [maalc] map: column 3: up boss (from mid)
15:00:01.000 [maalc] map: dragged the map 512 px; reading on from column 3
15:00:01.100 [maalc] map: column 3: up battle (from mid)
15:00:01.200 [maalc] map: path mid battle > mid boss > up battle, score 1
"""


def test_map_notes_come_from_the_log():
    nodes = ev.node_table(*ev.parse_map(ev.floor_block(ev.maalc(ev.parse_log(NOTES.splitlines())), 1, 0.0))[:2])
    notes = lambda key: sorted(tag for tag, _ in nodes[key]["notes"])  # noqa: E731
    assert notes((1, "mid")) == ["cost_none"]  # a coin seen, no number read
    assert notes((1, "down")) == ["cost_miss", "cost_none"]  # the OCR's reason is kept
    assert dict(nodes[(1, "down")]["notes"])["cost_miss"] == "one digit, OCR '7'"
    assert notes((1, "up")) == []  # no mark, no note
    assert notes((2, "mid")) == ["boss_by_cost", "boss_glow"]
    assert notes((3, "up")) == ["retyped"]  # read as a boss from afar, a battle once near: the later read wins


def test_map_draw_boxes_every_read_node_and_marks_a_fix():
    shots = [Image.new("RGB", (1280, 720)), Image.new("RGB", (1280, 720), (40, 40, 40))]
    nodes = {(1, "mid"): {"type": "battle", "first": "battle", "cost": "75", "stage": 0, "notes": []},
             (2, "down"): {"type": "risky", "first": "event", "cost": "20", "stage": 1, "notes": []}}
    fix = {"c2/down": ["cost", "讀成 20（畫面是 120）"], "c3/up": ["missed", "沒讀到的 event"]}
    im = ev.draw_map(shots, [0, 510], [(0, 510, 3)], nodes, ([("mid", "battle"), ("down", "risky")], 7), fix, 1)
    assert im.size[0] == 1790 and im.size[1] > 720  # the legend strip is below the map
    px = np.asarray(im)
    assert tuple(px[357 - 52, 328]) == ev.GREEN  # read right
    assert tuple(px[570 - 52, 583]) == ev.ORANGE  # Cost read wrong
    assert tuple(px[144 - 52, 838]) == ev.ORANGE  # a node the bot did not list


def test_map_draw_puts_a_missed_node_where_the_shot_that_shows_its_column_has_it():
    shots = [Image.new("RGB", (1280, 720)), Image.new("RGB", (1280, 720))]
    im = ev.draw_map(shots, [0, 480], [(0, 512, 3)], {}, None, {"c5/mid": ["missed", "x"]}, 1)  # the drag moved 480, not 512
    assert tuple(np.asarray(im)[357 - 52, ev.COLX(5) - 512 + 480]) == ev.ORANGE


def test_map_command_survives_a_floor_block_with_no_reading(tmp_path, footage):
    (tmp_path / "run.log").write_text(
        "15:52:51.700 [maalc] floor 1: pull Pack (0)\n15:52:56.000 [maalc] map: path mid battle, score 1\n", encoding="utf-8")
    ev.main(["map", str(tmp_path / "run.log"), "--floor", "1", "-o", str(tmp_path / "route"), *footage])
    assert (tmp_path / "route/stitched.png").exists()


def test_map_draw_gives_each_special_read_its_own_colour_and_a_legend():
    shots = [Image.new("RGB", (1280, 720)), Image.new("RGB", (1280, 720))]
    kinds = {"retyped": ev.VIOLET, "cost_none": ev.MAGENTA, "cost_miss": ev.MAGENTA, "boss_by_cost": ev.WHITE,
             "boss_glow": ev.CYAN, "boss_shop": ev.CYAN}
    nodes = {(k, row): {"type": "battle", "first": "battle", "cost": None, "stage": 0, "notes": [(tag, "x")]}
             for k, (tag, row) in enumerate(zip(kinds, ["up", "mid", "down", "up", "mid", "down"]), 1)}
    im = np.asarray(ev.draw_map(shots, [0, 512], [(0, 512, 3)], nodes, None, {}, 1))
    for (k, row), n in nodes.items():
        assert tuple(im[ev.ROWY[row] - 52, ev.COLX(k)]) == kinds[n["notes"][0][0]]
    legend = im[720:]
    colours = {tuple(c) for c in legend.reshape(-1, 3)}
    assert {ev.GREEN, ev.RED, ev.ORANGE, ev.VIOLET, ev.MAGENTA, ev.WHITE, ev.CYAN} <= colours


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
