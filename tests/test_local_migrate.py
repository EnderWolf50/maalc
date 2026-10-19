import json

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


def make_tree(root):
    (root / "sub").mkdir(parents=True)
    (root / "INDEX.md").write_text("index")
    (root / "sub/clip.mp4").write_bytes(b"x" * 300)


def test_move_and_link_puts_the_data_in_local_and_a_link_at_the_old_place(tmp_path):
    src, dst = tmp_path / "probe/archive", tmp_path / ".local/archive"
    make_tree(src)
    lm.move_and_link(src, dst)
    assert lm.is_link(src) and not lm.is_link(dst)  # the data lives in .local, the old path is the link
    assert (dst / "sub/clip.mp4").stat().st_size == 300
    assert (src / "INDEX.md").read_text() == "index"  # old path still works
    assert not (tmp_path / "probe/archive.migrating").exists()


def test_a_folder_in_use_keeps_the_original_and_drops_the_copy(tmp_path, monkeypatch):
    src, dst = tmp_path / "probe/archive", tmp_path / ".local/archive"
    make_tree(src)

    def busy(self, target):
        raise PermissionError(32, "in use")
    monkeypatch.setattr(type(src), "rename", busy)
    try:
        lm.move_and_link(src, dst)
    except RuntimeError as e:
        assert "in use" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
    assert not lm.is_link(src) and (src / "INDEX.md").read_text() == "index" and not dst.exists()


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
    assert json.loads((local / lm.LINKS).read_text()) == [str(probe / "archive"), str(unpack)]
    lm.migrate(local, probe, unpack, apply=True)  # a second run skips what is already a link
    lm.remove_links(local, apply=False)
    assert lm.is_link(unpack)
    lm.remove_links(local, apply=True)
    assert not (probe / "archive").exists() and not unpack.exists()  # the links are gone
    assert (local / "archive/INDEX.md").read_text() == "index" and (local / "unpack/sub/clip.mp4").exists()  # the data stays
    assert json.loads((local / lm.LINKS).read_text()) == []


def test_remove_links_leaves_a_real_folder_alone(tmp_path):
    local = tmp_path / ".local"
    local.mkdir()
    real = tmp_path / "real"
    make_tree(real)
    (local / lm.LINKS).write_text(json.dumps([str(real)]))
    lm.remove_links(local, apply=True)
    assert (real / "INDEX.md").exists()


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
