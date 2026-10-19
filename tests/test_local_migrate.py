import json
import stat
from pathlib import Path

import pytest

from PIL import Image

import local_migrate as lm


def test_plan_names_each_source_and_its_target(tmp_path):
    local = tmp_path / ".local"
    probe, unpack = tmp_path / "probe", tmp_path / "unpack"
    assert [(k, s.name, d.relative_to(local).as_posix()) for k, s, d in lm.plan(local, probe, unpack)] == [
        ("folder", "archive", "archive"), ("masks", "templates", "evidence"), ("folder", "unpack", "unpack")]
    assert lm.plan(local, None, None) == []


def test_masks_json_points_at_cropped_templates_next_to_it(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    for name in ("MainWindow.png", "Title.png"):
        Image.new("RGB", (1280, 720), "gray").save(templates / name)
    lm.write_masks(templates, tmp_path / "evidence")
    doc = json.loads((tmp_path / "evidence/masks.json").read_text())
    assert doc["space"] == [1280, 720] and len(doc["masks"]) == 3
    for m in doc["masks"]:
        assert Image.open(tmp_path / "evidence" / m["template"]).size[0] > 20
        assert m["threshold"] == 0.8 and m["boxes"]


def make_tree(root, read_only=False):
    (root / "sub").mkdir(parents=True)
    (root / "INDEX.md").write_text("index")
    (root / "sub/clip.mp4").write_bytes(b"x" * 300)
    if read_only:
        (root / "sub/clip.mp4").chmod(stat.S_IREAD)  # Windows refuses to delete it until the flag is cleared


def expect_error(fn, text):
    try:
        fn()
    except (RuntimeError, OSError) as e:
        assert text in str(e), e
    else:
        raise AssertionError(f"expected an error with {text!r}")


@pytest.fixture
def dirs(tmp_path):
    local = tmp_path / "repo/.local"
    local.mkdir(parents=True)
    return tmp_path / "probe/archive", local / "archive", local


@pytest.fixture(params=["same drive", "across drives"])
def drive(request, monkeypatch):
    if request.param == "across drives":
        monkeypatch.setattr(lm, "same_drive", lambda a, b: False)
    return request.param


def test_move_and_link_puts_the_data_in_local_and_a_link_at_the_old_place(dirs, drive):
    src, dst, local = dirs
    make_tree(src, read_only=True)
    lm.move_and_link(src, dst, local)
    assert lm.is_link(src) and not lm.is_link(dst)  # the data lives in .local, the old path is the link
    assert (dst / "sub/clip.mp4").stat().st_size == 300
    assert (src / "INDEX.md").read_text() == "index"  # the old path still works
    assert lm.leftovers(src, dst) == [] and json.loads((local / lm.LINKS).read_text()) == [str(src)]


def test_a_folder_in_use_keeps_the_original_and_drops_the_copy(dirs, drive, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    real = type(src).rename

    def busy(self, target):
        if self == src:
            raise PermissionError(32, "in use")
        return real(self, target)
    monkeypatch.setattr(type(src), "rename", busy)
    expect_error(lambda: lm.move_and_link(src, dst, local), "in use")
    assert not lm.is_link(src) and (src / "INDEX.md").read_text() == "index"
    assert not dst.exists() and lm.leftovers(src, dst) == []


def test_a_failed_copy_leaves_no_partial_target(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    monkeypatch.setattr(lm, "same_drive", lambda a, b: False)

    def disk_full(a, b, **k):
        Path(b).mkdir(parents=True)
        (Path(b) / "half.bin").write_bytes(b"x")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(lm.shutil, "copytree", disk_full)
    expect_error(lambda: lm.move_and_link(src, dst, local), "No space")
    assert (src / "INDEX.md").exists() and not dst.exists() and lm.leftovers(src, dst) == []


def test_a_file_written_during_the_copy_stops_the_move(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    monkeypatch.setattr(lm, "same_drive", lambda a, b: False)
    real = lm.file_stats
    calls = []

    def late_write(root):
        calls.append(root)
        if len(calls) == 3:  # the check after the original was renamed aside
            (root / "late.png").write_bytes(b"new")
        return real(root)
    monkeypatch.setattr(lm, "file_stats", late_write)
    expect_error(lambda: lm.move_and_link(src, dst, local), "changed while it was copied")
    assert (src / "late.png").read_bytes() == b"new" and not lm.is_link(src)  # nothing lost
    assert not dst.exists() and lm.leftovers(src, dst) == []


def test_a_failed_link_puts_the_original_back(dirs, drive, monkeypatch):
    src, dst, local = dirs
    make_tree(src)

    def no_link(a, b):
        raise OSError("mklink failed")
    monkeypatch.setattr(lm, "link", no_link)
    expect_error(lambda: lm.move_and_link(src, dst, local), "mklink failed")
    assert not lm.is_link(src) and (src / "INDEX.md").read_text() == "index" and not dst.exists()
    assert lm.read_links(local) == []


def test_leftovers_of_an_interrupted_run_stop_the_tool(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src.with_name("archive.migrating"))
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    with pytest.raises(SystemExit, match="interrupted run"):
        lm.migrate(local, src.parent, None, apply=True)


def test_migrate_records_links_and_remove_links_drops_only_those(tmp_path, monkeypatch):
    local = tmp_path / "repo/.local"
    local.mkdir(parents=True)
    probe, unpack = tmp_path / "probe", tmp_path / "unpack"
    make_tree(probe / "archive")
    make_tree(unpack)
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    lm.migrate(local, probe, unpack, apply=False)  # dry run changes nothing
    assert not lm.is_link(probe / "archive") and not (local / lm.LINKS).exists()
    lm.migrate(local, probe, unpack, apply=True)
    assert lm.is_link(probe / "archive") and lm.is_link(unpack)
    assert lm.read_links(local) == [str(probe / "archive"), str(unpack)]
    lm.migrate(local, probe, unpack, apply=True)  # a second run skips what is already a link
    lm.remove_links(local, apply=False)
    assert lm.is_link(unpack)
    lm.remove_links(local, apply=True)
    assert not (probe / "archive").exists() and not unpack.exists()  # the links are gone
    assert (local / "archive/INDEX.md").read_text() == "index" and (local / "unpack/sub/clip.mp4").exists()  # the data stays
    assert lm.read_links(local) == []


def test_remove_links_leaves_a_real_folder_alone_and_keeps_it_on_record(tmp_path):
    local = tmp_path / ".local"
    local.mkdir()
    real = tmp_path / "real"
    make_tree(real)
    (local / lm.LINKS).write_text(json.dumps([str(real)]))
    lm.remove_links(local, apply=True)
    assert (real / "INDEX.md").exists() and lm.read_links(local) == [str(real)]


def test_a_dry_run_creates_no_local_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "main_checkout", lambda: tmp_path / "repo")
    lm.main([])
    assert not (tmp_path / "repo/.local").exists()


def test_link_makes_the_target_readable_through_the_new_path(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real/INDEX.md").write_text("x")
    lm.link(tmp_path / "real", tmp_path / "sub/archive")
    assert (tmp_path / "sub/archive/INDEX.md").read_text() == "x"


def test_the_player_name_mask_is_bound_to_the_lv_label_and_covers_the_name_plate():
    from test_screens_privacy import NAME_PLATE

    (_, screen, crop, boxes), = [m for m in lm.MASKS if m[0] == "main-lv.png"]
    nx, ny, nw, nh = NAME_PLATE
    assert any(x <= nx and y <= ny and x + w >= nx + nw and y + h >= ny + nh for x, y, w, h in boxes)
    assert crop[0] <= nx + 2 and crop[1] >= ny + nh  # the template is the label below the plate, which Drive and SinnersTab show too
