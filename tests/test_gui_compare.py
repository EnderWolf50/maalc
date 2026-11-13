import io

from PIL import Image

import gui_compare as gc


def still(path, size=(8, 6), color=(10, 20, 30, 255), dots=()):
    im = Image.new("RGBA", size, color)
    for xy in dots:
        im.putpixel(xy, (200, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def test_the_same_stills_are_same_and_exit_0(tmp_path):
    for side in ("before", "after"):
        still(tmp_path / side / "light" / "run.png")
        still(tmp_path / side / "dark" / "run.png", color=(0, 0, 0, 255))
    out = io.StringIO()
    assert gc.run(tmp_path / "before", tmp_path / "after", out=out) == 0
    assert out.getvalue().splitlines() == ["dark/run.png: same", "light/run.png: same", "2 same, 0 differ"]
    assert gc.main([str(tmp_path / "before"), str(tmp_path / "after")]) == 0


def test_a_changed_pixel_is_counted_with_its_box_and_drawn_in_the_diff(tmp_path):
    still(tmp_path / "before" / "light" / "teams.png")
    still(tmp_path / "after" / "light" / "teams.png", dots=[(2, 1), (5, 4)])
    out = io.StringIO()
    assert gc.run(tmp_path / "before", tmp_path / "after", tmp_path / "diff", out=out) == 1
    assert out.getvalue().splitlines()[0] == "light/teams.png: 2 px differ, box (2, 1)-(5, 4)"
    diff = Image.open(tmp_path / "diff" / "light" / "teams.png").convert("RGB")
    assert diff.getpixel((2, 1)) == gc.MARK and diff.getpixel((5, 4)) == gc.MARK
    assert diff.getpixel((0, 0)) == (10 // 3, 20 // 3, 30 // 3)  # the rest dimmed
    assert gc.main([str(tmp_path / "before"), str(tmp_path / "after")]) == 1


def test_a_still_of_another_size_or_on_one_side_only_differs(tmp_path):
    still(tmp_path / "before" / "light" / "teams-full.png", size=(8, 6))
    still(tmp_path / "after" / "light" / "teams-full.png", size=(8, 9))
    still(tmp_path / "before" / "light" / "gone.png")
    still(tmp_path / "after" / "light" / "new.png")
    out = io.StringIO()
    assert gc.run(tmp_path / "before", tmp_path / "after", tmp_path / "diff", out=out) == 3
    assert out.getvalue().splitlines() == [
        "light/gone.png: only before", "light/new.png: only after", "light/teams-full.png: size 8x6 -> 8x9", "0 same, 3 differ",
    ]
    assert not (tmp_path / "diff").exists()  # no mask to draw for a size change
