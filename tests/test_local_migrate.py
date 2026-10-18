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
