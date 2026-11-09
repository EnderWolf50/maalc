import json

import pytest

from live import reel

GOOD = "第 1 層地圖：拖回一下就到位"  # 14 characters: shown at least 3 s


def write(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path.name


def manifest(tmp_path, steps, space=(1280, 720), cut=("10:00:00", "10:01:00"), **clip):
    events = write(tmp_path / "ev.json", {"space": list(space), "pointer": "touch", "events": []})
    steps_file = write(tmp_path / "steps.json", steps)
    doc = {"title": "驗收總集", "chapters": [{"issue": "#490", "line": "地圖拖回一下就到位", "clips": [
        {"video": "rec.mp4", "start": "09:59:00.000", "from": cut[0], "to": cut[1], "events": events, "steps": steps_file, **clip}]}]}
    path = tmp_path / "reel.json"
    write(path, doc)
    return path


def step(start, end, title=GOOD, boxes=None):
    return {"from": start, "to": end, "title": title, **({"boxes": boxes} if boxes else {})}


def test_a_clean_chapter_has_no_problem(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05"), step("10:00:05", "10:00:09", "入口頁：開關讀回 OFF 才按 Enter")]))
    assert report.problems == []
    assert report.warnings == []


def test_a_caption_with_no_chinese_character_is_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05"), step("10:00:05", "10:00:11", "bot started from the main window")]))
    assert len(report.problems) == 1
    assert "bot started from the main window" in report.problems[0]
    assert "Chinese" in report.problems[0]


def test_a_caption_shorter_than_three_seconds_is_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05"), step("10:00:05", "10:00:06.5")]))
    assert len(report.problems) == 1
    assert "1.5 s" in report.problems[0] and "3.0 s" in report.problems[0]


def test_a_long_caption_needs_a_second_per_five_characters(tmp_path):
    title = "第 5 層打完後按 Claim，不用每週獎勵，扣 5 個腦啡肽模組"  # 28 characters without spaces: 5.6 s
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:06.5", title)])).problems != []
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:06.6", title)])).problems == []


def test_a_caption_reading_like_a_log_line_warns(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:07", "暫停後 MirrorEntryPaused 按 Resume"),
                                            step("10:00:07", "10:00:11", "按下「GiveUpRewards」")]))
    assert report.problems == []
    assert len(report.warnings) == 1
    assert "MirrorEntryPaused" in report.warnings[0]


def test_a_box_outside_the_clip_grid_is_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[1200, 600, 120, 40, "開關"]])]))
    assert len(report.problems) == 1
    assert "1280x720" in report.problems[0]


def test_game_pixel_boxes_on_a_touch_log_grid_warn(tmp_path):
    """The #94 chapter of the first reel: boxes in 1280x720 game pixels on a 1920x1080 events grid landed at 2/3."""
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[955, 405, 80, 125, "拉桿"]])], space=(1920, 1080)))
    assert report.problems == []
    assert len(report.warnings) == 1
    assert "1920x1080" in report.warnings[0]
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[1430, 600, 120, 190, "拉桿"]])], space=(1920, 1080)))
    assert report.warnings == []


def test_a_speed_up_counts_against_the_caption_and_a_freeze_for_it(tmp_path):
    steps = [step("10:00:10", "10:00:14")]
    assert reel.check(manifest(tmp_path, steps, speed=[["10:00:08", "10:00:20", 4]])).problems != []
    assert reel.check(manifest(tmp_path, steps, speed=[["10:00:12", "10:00:20", 4]], freeze=[["10:00:11", 2.5]])).problems == []


def test_a_caption_cut_off_by_the_clip_end_counts_only_what_shows(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:58", "10:01:05")]))
    assert len(report.problems) == 1


def test_overlapping_captions_are_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:06"), step("10:00:05", "10:00:10")]))
    assert len(report.problems) == 1
    assert "overlaps" in report.problems[0]


def test_a_still_needs_a_chinese_caption(tmp_path):
    doc = {"title": "驗收總集", "chapters": [{"issue": "#385", "line": "目標層數的提示", "clips": [
        {"image": "a.png", "caption": "target floor hint"}, {"image": "b.png", "caption": "目標 10 層時的提示"}]}]}
    write(tmp_path / "reel.json", doc)
    report = reel.check(tmp_path / "reel.json")
    assert len(report.problems) == 1
    assert "target floor hint" in report.problems[0]


def test_the_played_clip_keeps_a_freeze_inside_a_slowed_stretch():
    tl = reel.Timeline(0.0, 10.0, speed=((2.0, 4.0, 0.5), (6.0, 10.0, 4.0)), freeze=((3.0, 1.5),))
    played = sum((p[2] - p[1]) / p[3] if p[0] == "play" else p[2] for p in tl.pieces())
    assert played == pytest.approx(2 + 4 + 1.5 + 2 + 1)
    assert [p for p in tl.pieces() if p[0] == "hold"] == [("hold", 3.0, 1.5)]


def test_overlapping_speed_stretches_are_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05")], speed=[["10:00:10", "10:00:20", 4], ["10:00:15", "10:00:25", 2]]))
    assert len(report.problems) == 1
    assert "overlaps" in report.problems[0]


def test_a_zero_speed_is_a_problem_not_a_crash(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:10", "10:00:14")], speed=[["10:00:08", "10:00:20", 0]]))
    assert len(report.problems) == 1
    assert "speed" in report.problems[0]


def test_build_refuses_and_lists_every_problem(tmp_path, capsys):
    path = manifest(tmp_path, [step("10:00:01", "10:00:02"), step("10:00:05", "10:00:09", "bot started")])
    with pytest.raises(SystemExit) as stop:
        reel.main([str(path)])
    assert stop.value.code == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "bot started" in text and "1.0 s" in text
    assert not (tmp_path / "reel.mp4").exists()
