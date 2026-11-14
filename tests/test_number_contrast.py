"""tools/number_contrast.py: what a test can hold without the settings window (the ring's pixels, the glyph, the ratios and
their percentiles, the summary, the command line). The page side runs on the real window: #756's PR names that run."""

import numpy as np
import pytest

import number_contrast as nc

ORANGE = (255, 185, 4)


def offsets(mask: np.ndarray, centre: tuple[int, int]) -> set[tuple[int, int]]:
    ys, xs = np.nonzero(mask)
    return {(int(y) - centre[0], int(x) - centre[1]) for y, x in zip(ys, xs)}


def test_the_ring_is_the_pixels_more_than_one_and_at_most_two_css_px_from_the_glyph():
    glyph = np.zeros((9, 9), bool)
    glyph[4, 4] = True
    assert offsets(nc.ring(glyph, 1), (4, 4)) == {(-1, -1), (-1, 1), (1, -1), (1, 1), (-2, 0), (2, 0), (0, -2), (0, 2)}
    # at 2 device px a CSS px the ring is more than 2 and at most 4 px out; at 1.5 (a display at 150 %) more than 1.5, at most 3
    far = offsets(nc.ring(np.pad(glyph, 4), 2), (8, 8))
    assert (0, 4) in far and (0, 2) not in far and (0, 5) not in far and (3, 3) not in far
    assert offsets(nc.ring(np.pad(glyph, 4), 1.5), (8, 8)) == {
        (dy, dx) for dy in range(-3, 4) for dx in range(-3, 4) if 2.25 < dy * dy + dx * dx <= 9}


def test_the_glyph_is_the_pixels_of_the_numbers_ink_not_its_soft_edge():
    region = np.zeros((6, 6, 3), np.uint8)
    region[2:4, 2:4] = ORANGE
    region[1, 2] = (200, 140, 10)  # an edge pixel half way to the rim
    region[4, 3] = (250, 180, 0)  # within the tolerance: ink
    glyph = nc.glyph(region, ORANGE)
    assert glyph.sum() == 5 and not glyph[1, 2] and glyph[4, 3]


@pytest.mark.parametrize("ink, ring, expected", [((255, 255, 255), (0, 0, 0), 21.0), ((0x76, 0x76, 0x76), (255, 255, 255), 4.54)])
def test_the_ratio_is_wcags(ink, ring, expected):
    assert nc.ratio(nc.luminance(np.array(ink)), nc.luminance(np.array(ring))) == pytest.approx(expected, abs=0.01)


def test_the_median_and_the_lighter_end_of_the_ring():
    """The ink is lighter than the rim, so the ring's lightest pixels are the worst: its 90th percentile of luminance."""
    ring = np.array([(0, 0, 0)] * 8 + [(255, 255, 255)] * 2)
    median, p90 = nc.ring_ratios(np.array((0x76, 0x76, 0x76)), ring)
    assert median == pytest.approx(4.62, abs=0.01)  # against black
    assert p90 == pytest.approx(4.54, abs=0.01)  # against white


def test_a_number_on_a_uniform_rim_reads_the_rims_contrast():
    region = np.zeros((40, 30, 3), np.uint8)
    region[5:35, 3:27] = (0x76, 0x76, 0x76)  # the rim round the digit, 3 px and more wide
    region[10:30, 10:20] = (255, 255, 255)  # the digit: white ink
    m = nc.measure(region, (255, 255, 255), 1)
    assert m["ink_px"] == 200
    assert m["median"] == pytest.approx(4.54, abs=0.01) and m["p90"] == pytest.approx(4.54, abs=0.01)


def test_no_ink_in_the_box_is_no_number():
    assert nc.measure(np.zeros((20, 20, 3), np.uint8), ORANGE, 2) is None


def test_a_css_colour_is_read():
    assert nc.css_rgb("rgb(255, 185, 4)") == (255, 185, 4)
    assert nc.css_rgb("rgba(34, 253, 227, 1)") == (34, 253, 227)


def test_the_summary_is_the_lowest_per_view_and_kind_and_flags_a_number_under_the_bar():
    rows = [
        {"view": "1500x860 dark", "kind": "deployed", "text": "1", "median": 3.9, "p90": 3.6},
        {"view": "1500x860 dark", "kind": "deployed", "text": "2", "median": 3.7, "p90": 3.5},
        {"view": "1500x860 dark", "kind": "backup", "text": "8", "median": 5.2, "p90": 5.1},
        {"view": "800x480 light", "kind": "deployed", "text": "1", "median": 3.2, "p90": 2.9},
    ]
    lines, low = nc.summary(rows, 3.0)
    assert "1500x860 dark: deployed n=2 median>=3.70 p90>=3.50; backup n=1 median>=5.20 p90>=5.10" in lines
    assert "all deployed: n=3 median>=3.20 p90>=2.90" in lines
    assert "all backup: n=1 median>=5.20 p90>=5.10" in lines
    assert low == [rows[3]]


@pytest.mark.parametrize("argv, error", [(["--sizes", "1500"], "WIDTHxHEIGHT"), (["--schemes", "dim"], "dark or light"), ([], "--port")])
def test_the_command_line_refuses_what_it_cannot_measure(argv, error, capsys):
    with pytest.raises(SystemExit) as e:
        nc.parse(argv)
    assert e.value.code == 2 and error in capsys.readouterr().err


def test_the_command_line_defaults_to_the_three_window_sizes_and_both_schemes():
    a = nc.parse(["--port", "9318"])
    assert a.sizes == [(1500, 860), (1280, 720), (800, 480)] and a.schemes == ["dark", "light"] and a.min == 3.0
    assert a.scale == 2  # as #744 and #754 measured, whatever the display's scale
