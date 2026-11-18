import os
import time
from pathlib import Path

import dir_link
import local_clean as lc


def write(path: Path, data: bytes, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))
    return path


def test_dedupe_links_identical_files_and_skips_existing_links(tmp_path):
    a = write(tmp_path / "a" / "x.bin", b"same" * 10)
    b = write(tmp_path / "b" / "longer-name.bin", b"same" * 10)
    other = write(tmp_path / "c.bin", b"diff" * 10)
    already = tmp_path / "a" / "linked.bin"
    os.link(a, already)

    dry = lc.dedupe(tmp_path, min_bytes=1)
    assert [d for _, d, _ in dry] == [[b]]
    assert a.stat().st_ino != b.stat().st_ino  # dry run changes nothing

    lc.dedupe(tmp_path, min_bytes=1, apply=True)
    assert a.stat().st_ino == b.stat().st_ino == already.stat().st_ino
    assert b.read_bytes() == a.read_bytes() == b"same" * 10
    assert other.stat().st_ino != a.stat().st_ino
    assert lc.dedupe(tmp_path, min_bytes=1) == []


def test_dedupe_relinks_every_path_of_a_duplicate_inode(tmp_path):
    a = write(tmp_path / "a.bin", b"same" * 10)
    b1 = write(tmp_path / "dir" / "b1.bin", b"same" * 10)
    b2 = tmp_path / "dir" / "b2.bin"
    os.link(b1, b2)

    lc.dedupe(tmp_path, min_bytes=1, apply=True)
    assert a.stat().st_ino == b1.stat().st_ino == b2.stat().st_ino
    assert lc.dedupe(tmp_path, min_bytes=1) == []


def test_dedupe_ignores_files_below_the_minimum(tmp_path):
    write(tmp_path / "a", b"tiny")
    write(tmp_path / "b", b"tiny")
    assert lc.dedupe(tmp_path, min_bytes=1e6) == []


def make_archive(tmp_path):
    archive = tmp_path / "archive"
    write(archive / "old-done" / "f.bin", b"1" * 100, age_days=30)
    write(archive / "old-open" / "f.bin", b"2" * 100, age_days=30)
    write(archive / "new-done" / "f.bin", b"3" * 100, age_days=1)
    write(archive / "recordings" / "f.bin", b"4" * 100, age_days=30)
    write(archive / "old-unlisted" / "f.bin", b"5" * 100, age_days=30)
    write(archive / "old-unknown" / "f.bin", b"6" * 100, age_days=30)
    (archive / "INDEX.md").write_text(
        "# index\n\n| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n"
        "| 2026-10-01 | a | #1 | `old-done/` | x |\n"
        "| 2026-10-02 | b | #2 #3 | `old-open/` | x |\n"
        "| 2026-10-28 | c | #1 | `new-done/` | x |\n"
        "| 2026-10-03 | d | #1 | `recordings/old-done.mp4` | x |\n"
        "| 2026-10-04 | e | #9 | `old-unknown/` | x |\n", encoding="utf-8")
    return archive


STATES = {1: "closed", 2: "merged", 3: "open"}
ALL = ("old-done", "old-open", "new-done", "recordings", "old-unlisted", "old-unknown")


def test_prune_dry_run_touches_nothing(tmp_path):
    archive = make_archive(tmp_path)
    before = (archive / "INDEX.md").read_text(encoding="utf-8")
    doomed = lc.prune(archive, days=7, states=lambda: STATES)
    assert {f.name for f in doomed} == {"old-done"}
    assert all((archive / n).is_dir() for n in ALL)
    assert (archive / "INDEX.md").read_text(encoding="utf-8") == before


def test_prune_apply_deletes_only_old_folders_whose_rows_are_all_closed(tmp_path):
    archive = make_archive(tmp_path)
    lc.prune(archive, days=7, apply=True, states=lambda: STATES)
    assert not (archive / "old-done").exists()
    for kept in ALL[1:]:
        assert (archive / kept).is_dir(), kept
    rows = {ln.split("|")[4].strip(): ln for ln in (archive / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if ln.startswith("| 2026")}
    done = rows["`old-done/`"]
    assert done.split("|")[5].strip().startswith("x （") and "已刪除 old-done" in done.split("|")[5]
    assert done.endswith("|") and done.count("|") == 6
    for name in ("`old-open/`", "`new-done/`", "`recordings/old-done.mp4`", "`old-unknown/`"):
        assert "已刪除" not in rows[name]


def test_prune_lets_an_old_folder_go_when_only_a_tracking_issue_holds_it(tmp_path):
    archive = tmp_path / "archive"
    write(archive / "old-tracked" / "f.bin", b"1" * 100, age_days=30)
    write(archive / "mid-tracked" / "f.bin", b"2" * 100, age_days=10)
    write(archive / "old-tracked-open" / "f.bin", b"3" * 100, age_days=30)
    (archive / "INDEX.md").write_text(
        "| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n"
        "| 2026-10-01 | a | #1 #4 | `old-tracked/` | x |\n"
        "| 2026-10-02 | b | #4 | `mid-tracked/` | x |\n"
        "| 2026-10-03 | c | #3 #4 | `old-tracked-open/` | x |\n", encoding="utf-8")
    states = {1: "closed", 3: "open", 4: "tracking"}
    doomed = lc.prune(archive, days=7, tracking_days=14, apply=True, states=lambda: states)
    assert [f.name for f in doomed] == ["old-tracked"]
    assert not (archive / "old-tracked").exists()
    assert (archive / "mid-tracked").is_dir() and (archive / "old-tracked-open").is_dir()


def test_prune_deletes_old_recordings_no_folder_links_any_more(tmp_path):
    archive = tmp_path / "archive"
    rec = archive / "recordings"
    kept_folder = write(archive / "live" / "run.mp4", b"1" * 100, age_days=30)
    rec.mkdir(parents=True)
    os.link(kept_folder, rec / "linked.mp4")
    orphan = write(rec / "orphan.mp4", b"2" * 100, age_days=30)
    fresh = write(rec / "fresh.mp4", b"3" * 100, age_days=1)
    held = write(rec / "held.mp4", b"4" * 100, age_days=30)
    nested = write(rec / "sub" / "orphan2.mp4", b"5" * 100, age_days=30)
    (archive / "INDEX.md").write_text(
        "| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n"
        "| 2026-10-01 | a | #3 | `live/`、`recordings/linked.mp4` | x |\n"
        "| 2026-10-02 | b | #3 | `recordings/held.mp4` | x |\n"
        "| 2026-10-03 | c | #1 | `recordings/orphan.mp4` | x |\n", encoding="utf-8")
    states = {1: "closed", 3: "open"}

    lc.prune(archive, days=7, states=lambda: states)
    assert orphan.exists() and nested.exists()  # dry run

    lc.prune(archive, days=7, apply=True, states=lambda: states)
    assert not orphan.exists() and not nested.exists()
    assert (rec / "linked.mp4").exists() and fresh.exists() and held.exists()
    assert (archive / "live").is_dir()
    index = (archive / "INDEX.md").read_text(encoding="utf-8")
    assert "已刪除 orphan.mp4" in index and "已刪除 held.mp4" not in index


def test_prune_counts_a_recording_whose_only_other_link_is_in_a_doomed_folder(tmp_path):
    archive = tmp_path / "archive"
    src = write(archive / "old-done" / "run.mp4", b"1" * 100, age_days=30)
    (archive / "recordings").mkdir()
    os.link(src, archive / "recordings" / "old-done-run.mp4")
    (archive / "INDEX.md").write_text(
        "| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n"
        "| 2026-10-01 | a | #1 | `old-done/` | x |\n", encoding="utf-8")
    lc.prune(archive, days=7, apply=True, states=lambda: {1: "closed"})
    assert not (archive / "old-done").exists()
    assert not (archive / "recordings" / "old-done-run.mp4").exists()


def test_item_state_marks_only_an_open_tracking_issue():
    tracked = {"state": "OPEN", "labels": [{"name": "tracking"}]}
    assert lc.item_state("issue", tracked) == "tracking"
    assert lc.item_state("pr", tracked) == "open"
    assert lc.item_state("issue", {"state": "CLOSED", "labels": [{"name": "tracking"}]}) == "closed"
    assert lc.item_state("issue", {"state": "OPEN", "labels": [{"name": "bug"}]}) == "open"


def test_prune_cli_takes_tracking_days():
    a = lc.build_parser().parse_args(["prune", "x", "--tracking-days", "30"])
    assert a.tracking_days == 30
    assert lc.build_parser().parse_args(["prune", "x"]).tracking_days == lc.TRACKING_DAYS


def rec_archive(tmp_path, rows: str):
    archive = tmp_path / "archive"
    (archive / "recordings").mkdir(parents=True)
    (archive / "INDEX.md").write_text(
        "| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n" + rows, encoding="utf-8")
    return archive


def test_a_tracking_issue_holds_an_orphan_recording_only_until_tracking_days(tmp_path):
    archive = rec_archive(tmp_path, "| 2026-10-01 | a | #4 | `recordings/young.mp4`、`recordings/old.mp4` | x |\n")
    young = write(archive / "recordings" / "young.mp4", b"1", age_days=10)
    old = write(archive / "recordings" / "old.mp4", b"2", age_days=30)
    lc.prune(archive, days=7, tracking_days=14, apply=True, states=lambda: {4: "tracking"})
    assert young.exists() and not old.exists()


def test_a_row_naming_the_same_file_name_in_another_folder_neither_holds_nor_gets_marked(tmp_path):
    archive = rec_archive(tmp_path, "| 2026-10-01 | a | #3 | `fresh/run.mp4` | x |\n")
    write(archive / "fresh" / "run.mp4", b"other", age_days=1)
    orphan = write(archive / "recordings" / "run.mp4", b"1", age_days=30)
    lc.prune(archive, days=7, apply=True, states=lambda: {3: "open"})
    assert not orphan.exists()
    assert "已刪除" not in (archive / "INDEX.md").read_text(encoding="utf-8")


def test_prune_does_not_follow_a_folder_link_inside_recordings(tmp_path):
    archive = rec_archive(tmp_path, "| 2026-10-01 | a | #3 | `held/` | x |\n")
    held = write(archive / "held" / "x.bin", b"1", age_days=30)
    dir_link.link(archive / "recordings" / "j", archive / "held")
    lc.prune(archive, days=7, apply=True, states=lambda: {3: "open"})
    assert held.exists()


def test_prune_keeps_a_recording_whose_folder_could_not_be_deleted(tmp_path, monkeypatch):
    archive = rec_archive(tmp_path, "| 2026-10-01 | a | #1 | `old-done/` | x |\n")
    src = write(archive / "old-done" / "run.mp4", b"1", age_days=30)
    os.link(src, archive / "recordings" / "run.mp4")

    def refuse(path, *a, **k):
        raise OSError("in use")
    monkeypatch.setattr(lc.shutil, "rmtree", refuse)
    lc.prune(archive, days=7, apply=True, states=lambda: {1: "closed"})
    assert src.exists() and (archive / "recordings" / "run.mp4").exists()


def test_shrink_filter_needs_taller_than_720p_and_over_2_mbps():
    mb = 1_000_000
    assert lc.qualifies(1400, 600, 800 * mb)  # ~10.7 Mbps
    assert not lc.qualifies(720, 600, 800 * mb)  # already 720p
    assert not lc.qualifies(1400, 600, 100 * mb)  # ~1.3 Mbps
    assert not lc.qualifies(1400, 0, 800 * mb)


def test_shrink_replaces_only_a_smaller_file_of_the_same_length():
    assert lc.should_replace(600, 800, 600.9, 300)
    assert not lc.should_replace(600, 800, 602, 300)  # duration drifted
    assert not lc.should_replace(600, 800, 600, 800)  # not smaller


def test_shrink_keep_matches_a_whole_folder_name():
    paths = [Path("archive/2026-10-29-topic/rec.mp4"), Path("archive/recordings/a.mp4")]
    assert lc.is_kept(paths, ["2026-10-29-topic"])
    assert not lc.is_kept(paths, ["topic"])
    assert not lc.is_kept(paths, ["a"])
    assert not lc.is_kept(paths, [])
