import json
import os
import stat
from pathlib import Path

import pytest

from PIL import Image

import local_migrate as lm


def test_plan_names_each_source_and_its_target(tmp_path):
    local = tmp_path / ".local"
    probe, unpack = tmp_path / "probe", tmp_path / "unpack"
    assert [(k, s.name, d.relative_to(local).as_posix()) for k, s, d in lm.plan(local, probe, unpack)] == [
        ("folder", "probe", "probe"), ("archive", "archive", "archive"),
        ("masks", "templates", "evidence"), ("folder", "unpack", "unpack")]
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

    def late_write(root):
        if root == lm.aside_of(src) and not (root / "late.png").exists():  # right after the rename aside
            (root / "late.png").write_bytes(b"new")
        return real(root)
    monkeypatch.setattr(lm, "file_stats", late_write)
    expect_error(lambda: lm.move_and_link(src, dst, local), "changed while it was copied")
    assert (src / "late.png").read_bytes() == b"new" and not lm.is_link(src)  # nothing lost
    assert not dst.exists() and lm.leftovers(src, dst) == []


def test_a_copy_with_different_bytes_stops_the_move(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    monkeypatch.setattr(lm, "same_drive", lambda a, b: False)
    real = lm.shutil.copytree

    def corrupt(a, b, *args, **k):
        out = real(a, b, *args, **k)  # copytree calls itself for subfolders: corrupt only at the top
        if Path(b) != lm.partial_of(dst):
            return out
        f = Path(b) / "sub/clip.mp4"
        st = f.stat()
        f.write_bytes(b"y" * 300)  # same size
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))  # same time
    monkeypatch.setattr(lm.shutil, "copytree", corrupt)
    expect_error(lambda: lm.move_and_link(src, dst, local), "not identical")
    assert (src / "sub/clip.mp4").read_bytes() == b"x" * 300 and not dst.exists()


def test_a_failed_final_rename_puts_the_original_back(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    monkeypatch.setattr(lm, "same_drive", lambda a, b: False)
    real = type(src).rename

    def refuse(self, target):
        if self == lm.partial_of(dst):
            raise PermissionError(5, "denied")
        return real(self, target)
    monkeypatch.setattr(type(src), "rename", refuse)
    expect_error(lambda: lm.move_and_link(src, dst, local), "denied")
    assert (src / "INDEX.md").exists() and not lm.is_link(src) and lm.leftovers(src, dst) == [] and not dst.exists()


def test_a_rerun_finishes_deleting_the_original_once_the_copy_is_final(dirs):
    src, dst, local = dirs
    make_tree(dst)
    lm.link(dst, src)
    lm.record_link(local, src)
    make_tree(lm.deleting_of(src))  # an interrupted delete of the original
    lm.migrate_folder(local, src, dst, apply=True)
    assert not lm.deleting_of(src).exists() and (dst / "INDEX.md").exists() and lm.is_link(src)


def test_a_rerun_relinks_and_records_what_an_interrupted_run_left(dirs, monkeypatch):
    src, dst, local = dirs
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    lm.record_link(local, src)  # recorded first, renamed into .local, then the run stopped before the link
    make_tree(dst)
    lm.migrate_folder(local, src, dst, apply=True)
    assert lm.points_to(src, dst) and lm.read_links(local) == [str(src)]


def test_a_failed_link_puts_the_original_back(dirs, drive, monkeypatch):
    src, dst, local = dirs
    make_tree(src)

    def no_link(a, b):
        raise OSError("mklink failed")
    monkeypatch.setattr(lm, "link", no_link)
    expect_error(lambda: lm.move_and_link(src, dst, local), "mklink failed")
    assert not lm.is_link(src) and (src / "INDEX.md").read_text() == "index" and not dst.exists()
    assert lm.read_links(local) == []


def test_an_original_set_aside_without_a_link_stops_the_tool(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(lm.aside_of(src))
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    with pytest.raises(SystemExit, match="is the original"):
        lm.migrate_folder(local, src, dst, apply=True)


def test_an_unchecked_copy_stops_the_tool(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    make_tree(lm.partial_of(dst))
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    with pytest.raises(SystemExit, match="unchecked copy"):
        lm.migrate_folder(local, src, dst, apply=True)
    assert (src / "INDEX.md").exists()


def test_a_link_left_by_the_old_tool_is_removed_and_the_data_moved_in(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    lm.link(src, dst)  # the old tool linked .local/ to the outside folder
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    lm.migrate_folder(local, src, dst, apply=True)
    assert not lm.is_link(dst) and (dst / "INDEX.md").exists() and lm.points_to(src, dst)


def test_a_link_in_local_to_some_other_folder_stops_the_tool(dirs, tmp_path, monkeypatch):
    src, dst, local = dirs
    make_tree(src)
    make_tree(tmp_path / "elsewhere")
    lm.link(tmp_path / "elsewhere", dst)
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    with pytest.raises(SystemExit, match="rmdir"):
        lm.migrate_folder(local, src, dst, apply=True)
    assert (src / "INDEX.md").exists() and (tmp_path / "elsewhere/INDEX.md").exists()


def test_a_checked_copy_whose_link_is_missing_is_finished_on_a_rerun(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(dst)
    make_tree(lm.aside_of(src))  # stopped after the copy took its name, before the link
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    lm.migrate_folder(local, src, dst, apply=True)
    assert lm.points_to(src, dst) and lm.leftovers(src, dst) == [] and lm.read_links(local) == [str(src)]


def test_a_checked_copy_that_differs_from_the_original_stops_the_tool(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(dst)
    make_tree(lm.aside_of(src))
    (dst / "INDEX.md").write_text("other")
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    with pytest.raises(SystemExit, match="differ"):
        lm.migrate_folder(local, src, dst, apply=True)
    assert lm.aside_of(src).exists() and (dst / "INDEX.md").exists()


def test_an_original_set_aside_behind_a_working_link_is_deleted_on_a_rerun(dirs, monkeypatch):
    src, dst, local = dirs
    make_tree(dst)
    lm.link(dst, src)
    lm.record_link(local, src)
    make_tree(lm.aside_of(src))  # stopped between the link and the rename to .deleting
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    lm.migrate_folder(local, src, dst, apply=True)
    assert lm.leftovers(src, dst) == [] and (dst / "INDEX.md").exists() and lm.points_to(src, dst)


def test_a_mistyped_path_is_never_linked(dirs, tmp_path, monkeypatch):
    src, dst, local = dirs
    make_tree(dst)  # .local/archive already holds data
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    typo = tmp_path / "prbe"
    lm.migrate(local, typo, None, apply=True)
    assert not (typo / "archive").exists() and lm.read_links(local) == []


def test_a_relative_path_is_recorded_absolute(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".local").mkdir(parents=True)
    make_tree(tmp_path / "work/probe/archive")
    monkeypatch.setattr(lm, "main_checkout", lambda: repo)
    monkeypatch.setattr(lm, "write_masks", lambda *a: None)
    monkeypatch.chdir(tmp_path / "work")
    lm.main(["--probe", "probe", "--apply"])
    assert lm.read_links(repo / ".local") == [str(tmp_path / "work/probe")]


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
    assert lm.is_link(probe) and lm.is_link(unpack)
    assert lm.read_links(local) == [str(probe), str(unpack)]
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


def test_complete_probe_moves_loose_files_caches_scripts_and_experiments(tmp_path, drive):
    local, probe = tmp_path / '.local', tmp_path / 'old-probe'
    local.mkdir()
    contents = ['script.py', '.venv/pyvenv.cfg', '__pycache__/script.pyc', 'exp/log.txt',
                'captures/screen.png', 'archive/INDEX.md', 'tools/helper.py']
    for name in contents:
        p = probe / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(name.encode())
    templates = probe / 'tools/templates'
    templates.mkdir()
    for name in ('MainWindow.png', 'Title.png'):
        Image.new('RGB', (1280, 720), 'gray').save(templates / name)
    lm.migrate(local, probe, None, apply=True)
    assert lm.points_to(probe, local / 'probe')
    for name in contents:
        assert (local / 'probe' / name).read_bytes() == name.encode()
        assert (probe / name).read_bytes() == name.encode()
    assert lm.points_to(local / 'archive', local / 'probe/archive')
    assert (local / 'evidence/masks.json').exists()
    lm.migrate(local, probe, None, apply=True)
    lm.remove_links(local, apply=True)
    assert not probe.exists()
    assert (local / 'archive/INDEX.md').read_bytes() == b'archive/INDEX.md'
    assert (local / 'probe/script.py').exists()


def test_existing_probe_destination_is_not_silently_treated_as_migrated(tmp_path):
    local, probe = tmp_path / '.local', tmp_path / 'old-probe'
    make_tree(local / 'probe')
    make_tree(probe)
    with pytest.raises(SystemExit, match='already exists'):
        lm.migrate(local, probe, None, apply=True)
    assert not lm.is_link(probe)


def test_previously_migrated_archive_is_preserved_when_the_rest_moves(tmp_path, drive, monkeypatch):
    local, probe = tmp_path / '.local', tmp_path / 'old-probe'
    make_tree(local / 'archive')
    probe.mkdir()
    (probe / 'script.py').write_text('script')
    lm.link(local / 'archive', probe / 'archive')
    lm.record_link(local, probe / 'archive')
    monkeypatch.setattr(lm, 'write_masks', lambda *args: None)
    lm.migrate(local, probe, None, apply=True)
    assert lm.points_to(local / 'probe/archive', local / 'archive')
    assert lm.read_links(local) == [str(probe)]
    lm.remove_links(local, apply=True)
    assert (local / 'archive/sub/clip.mp4').stat().st_size == 300
    assert (local / 'probe/archive/sub/clip.mp4').stat().st_size == 300


def test_source_containing_the_destination_is_rejected(tmp_path):
    local = tmp_path / '.local'
    local.mkdir()
    with pytest.raises(SystemExit, match='overlaps'):
        lm.migrate(local, tmp_path, None, apply=True)
    assert not (local / lm.LINKS).exists()


@pytest.mark.parametrize('parent_first', [False, True])
def test_remove_links_after_interruption_keeps_nested_archive_alias(tmp_path, parent_first):
    local, probe = tmp_path / '.local', tmp_path / 'old-probe'
    make_tree(local / 'archive')
    (local / 'probe').mkdir()
    lm.link(local / 'archive', local / 'probe/archive')
    lm.link(local / 'probe', probe)
    records = [str(probe / 'archive'), str(probe)]
    lm.write_links(local, records[::-1] if parent_first else records)
    lm.remove_links(local, apply=True)
    assert not probe.exists()
    assert lm.points_to(local / 'probe/archive', local / 'archive')
    assert lm.read_links(local) == []


def test_remove_links_refuses_to_break_an_absolute_internal_link(tmp_path):
    local, probe = tmp_path / '.local', tmp_path / 'old-probe'
    make_tree(local / 'probe')
    lm.link(local / 'probe', probe)
    lm.link(probe / 'sub', local / 'probe/cache-link')
    lm.record_link(local, probe)
    with pytest.raises(SystemExit, match='depends on'):
        lm.remove_links(local, apply=True)
    assert lm.is_link(probe) and (local / 'probe/cache-link/clip.mp4').is_file()
