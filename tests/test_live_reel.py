import json

import pytest
from PIL import Image

from live import evidence, reel

GOOD = "第 1 層地圖：拖回一下就到位"  # 14 characters: shown at least 3 s


def write(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path.name


def manifest(tmp_path, steps, space=(1280, 720), cut=("10:00:00", "10:01:00"), box_space="space", **clip):
    events = write(tmp_path / "ev.json", {"space": list(space), "pointer": "touch", "events": []})
    steps_file = write(tmp_path / "steps.json", steps)
    grid = {} if box_space is None else {"box_space": list(space if box_space == "space" else box_space)}
    doc = {"title": "驗收總集", "chapters": [{"issue": "#490", "line": "地圖拖回一下就到位", "clips": [
        {"video": "rec.mp4", "start": "09:59:00.000", "from": cut[0], "to": cut[1], "events": events, "steps": steps_file, **grid, **clip}]}]}
    path = tmp_path / "reel.json"
    write(path, doc)
    return path


def step(start, end, title=GOOD, boxes=None, tag=None):
    return {"from": start, "to": end, "title": title, **({"boxes": boxes} if boxes else {}), **({"tag": tag} if tag else {})}


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


def test_boxes_with_no_declared_grid_are_refused(tmp_path):
    """The #94 chapter of the first reel: boxes written in 1280x720 game pixels on a 1920x1080 clip landed at 2/3."""
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[955, 405, 80, 125, "拉桿"]])], space=(1920, 1080),
                                 box_space=None))
    assert len(report.problems) == 1
    assert "box_space" in report.problems[0]
    zoomed = {**step("10:00:01", "10:00:05"), "zoom": [0, 0, 640, 360]}
    assert len(reel.check(manifest(tmp_path, [zoomed], box_space=None)).problems) == 1
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05")], box_space=None)).problems == []


def test_a_box_space_that_is_not_a_size_is_refused(tmp_path):
    for bad in ([1280], [0, 0], "1280x720"):
        report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[10, 10, 50, 50, "開關"]])], box_space=bad))
        assert len(report.problems) == 1, bad
        assert "box_space" in report.problems[0]


def test_a_box_outside_its_declared_grid_is_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[1200, 600, 120, 40, "開關"]])], space=(1920, 1080),
                                 box_space=(1280, 720)))
    assert len(report.problems) == 1
    assert "1280x720" in report.problems[0]
    zoomed = {**step("10:00:01", "10:00:05"), "zoom": [800, 400, 640, 360]}
    assert len(reel.check(manifest(tmp_path, [zoomed], space=(1920, 1080), box_space=(1280, 720))).problems) == 1


def test_game_pixel_boxes_are_drawn_on_the_touch_log_grid(tmp_path):
    path = manifest(tmp_path, [step("10:00:01", "10:00:05", boxes=[[955, 405, 80, 125, "拉桿"]])], space=(1920, 1080), box_space=(1280, 720))
    assert reel.check(path) == reel.Report([], [])
    clip = reel.load(path).chapters[0].clips[0]
    assert clip.annotation_steps()[0]["boxes"] == [[1432.5, 607.5, 120.0, 187.5, "拉桿"]]
    zoomed = {**step("10:00:01", "10:00:05"), "zoom": [640, 360, 640, 360]}
    clip = reel.load(manifest(tmp_path, [zoomed], space=(1920, 1080), box_space=(1280, 720))).chapters[0].clips[0]
    assert clip.annotation_steps()[0]["zoom"] == [960.0, 540.0, 960.0, 540.0]


def test_an_unwritten_draft_is_refused(tmp_path):
    draft = {"from": "10:00:01", "to": "10:00:05", "title": "", "note": "map: take up event"}
    report = reel.check(manifest(tmp_path, [draft, step("10:00:05", "10:00:09")]))
    assert len(report.problems) == 1
    assert "draft" in report.problems[0]


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
        reel.main(["build", str(path)])
    assert stop.value.code == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "bot started" in text and "1.0 s" in text
    assert not (tmp_path / "reel.mp4").exists()


def test_a_sheet_lays_the_recording_out_a_frame_per_step(tmp_path, monkeypatch):
    def frames(footage, t0, t1, every):
        return ((t0 + i * every, Image.new("RGB", (1280, 720))) for i in range(int((t1 - t0) / every) + 1))

    monkeypatch.setattr(reel, "sheet_frames", frames)
    out = tmp_path / "sheet.png"
    reel.sheet(evidence.Footage(["rec.mp4@10:00:00"]), evidence.secs("10:00:10"), evidence.secs("10:00:22"), 2.0, out, cols=3)
    w, h = Image.open(out).size
    assert (w, h) == (3 * 320, 3 * (180 + 22))  # 7 frames, 10 to 22 s every 2 s: three rows of three


def chapters(count):
    return tuple(reel.Chapter(f"#{500 + n}", f"第 {n} 章要看的事", f"短名 {n}", "", ()) for n in range(1, count + 1))


def test_the_opening_list_fills_the_whole_frame_with_no_strip(tmp_path, monkeypatch):
    # the user, 2026-11-09: 「目錄感覺不需要上方那條」
    encoded = []
    monkeypatch.setattr(reel.Builder, "file", lambda self, suffix: tmp_path / f"{len(encoded)}{suffix}")
    monkeypatch.setattr(reel.Builder, "segment", lambda self, picture, filters, bands, out: encoded.append((picture[-1], bands)))
    builder = object.__new__(reel.Builder)  # no work folder or masks: nothing is encoded
    builder.reel = reel.Reel("驗收總集", tmp_path, chapters(21))
    builder.opening([10.0 + 30 * i for i in range(21)])
    [(png, bands)] = encoded
    assert Image.open(png).size == (1280, 776)
    assert bands == []


def test_the_chapter_marks_name_a_chapter_by_its_number_alone():
    # the user, 2026-11-09: 「「第 xx/XX 章」不美觀，可能只顯示當前章節數字還比較好看」
    marks = reel.chapter_marks(chapters(21), [10.0 + 30 * i for i in range(21)], [30.0] * 21)
    assert marks[0] == (0.0, 10.0, "目錄")
    assert marks[8] == (220.0, 250.0, "08 #508 第 8 章要看的事")


# A before/after step names its side in the step's tag, which evidence-annotate shows in place of the step number
# (the user, 2026-11-09, on using the skill's step tag for 改前／改後: 「都跟進」).

def test_a_tag_with_no_chinese_character_is_refused(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", tag="before")]))
    assert len(report.problems) == 1
    assert "tag" in report.problems[0] and "Chinese" in report.problems[0]


def test_a_tag_counts_toward_the_reading_time(tmp_path):
    title = "等了 1.5 秒才重拖，地圖沒動了"  # 15 characters without spaces: 3 s alone; with 改前 it is 17, 3.4 s
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:04.1", title)])).problems == []
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:04.1", title, tag="改前")])).problems != []
    assert reel.check(manifest(tmp_path, [step("10:00:01", "10:00:04.4", title, tag="改前")])).problems == []


def test_a_title_opening_with_before_or_after_warns_to_use_the_tag(tmp_path):
    report = reel.check(manifest(tmp_path, [step("10:00:01", "10:00:05", "改前：等了 1.5 秒才重拖")]))
    assert report.problems == []
    assert len(report.warnings) == 1 and "tag" in report.warnings[0]
