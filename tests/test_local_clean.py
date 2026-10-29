import os
import time
from pathlib import Path

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
    assert [d for _, d, _ in dry] == [b]
    assert a.stat().st_ino != b.stat().st_ino  # dry run changes nothing

    lc.dedupe(tmp_path, min_bytes=1, apply=True)
    assert a.stat().st_ino == b.stat().st_ino == already.stat().st_ino
    assert b.read_bytes() == a.read_bytes() == b"same" * 10
    assert other.stat().st_ino != a.stat().st_ino
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
    (archive / "INDEX.md").write_text(
        "# index\n\n| 日期 | 主題 | issue | 位置 | 內容 |\n|---|---|---|---|---|\n"
        "| 2026-10-01 | a | #1 | `old-done/` | x |\n"
        "| 2026-10-02 | b | #2 #3 | `old-open/` | x |\n"
        "| 2026-10-28 | c | #1 | `new-done/` | x |\n"
        "| 2026-10-03 | d | #1 | `recordings/old-done.mp4` | x |\n", encoding="utf-8")
    return archive


STATES = {1: "closed", 2: "closed", 3: "open"}


def test_prune_dry_run_touches_nothing(tmp_path):
    archive = make_archive(tmp_path)
    before = (archive / "INDEX.md").read_text(encoding="utf-8")
    doomed = lc.prune(archive, days=7, states=lambda: STATES)
    assert {f.name for f in doomed} == {"old-done", "old-unlisted"}
    assert all((archive / n).is_dir() for n in ("old-done", "old-open", "new-done", "recordings", "old-unlisted"))
    assert (archive / "INDEX.md").read_text(encoding="utf-8") == before


def test_prune_apply_deletes_only_matching_folders_and_marks_index(tmp_path):
    archive = make_archive(tmp_path)
    lc.prune(archive, days=7, apply=True, states=lambda: STATES)
    assert not (archive / "old-done").exists()
    assert not (archive / "old-unlisted").exists()
    for kept in ("old-open", "new-done", "recordings"):
        assert (archive / kept).is_dir()
    rows = {ln.split("|")[4].strip(): ln for ln in (archive / "INDEX.md").read_text(encoding="utf-8").splitlines()
            if ln.startswith("| 2026")}
    assert "已刪除" in rows["`old-done/`"]
    assert "已刪除" not in rows["`old-open/`"]
    assert "已刪除" not in rows["`new-done/`"]
    assert "已刪除" not in rows["`recordings/old-done.mp4`"]


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


def test_shrink_keep_matches_any_folder_part():
    paths = [Path("archive/2026-10-29-topic/rec.mp4"), Path("archive/recordings/a.mp4")]
    assert lc.is_kept(paths, ["topic"])
    assert not lc.is_kept(paths, ["other"])
    assert not lc.is_kept(paths, [])
