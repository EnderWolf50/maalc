import types

import numpy as np

import hub_text as ht


def ocr(roi, *expected, replace=()):
    return {"type": "OCR", "param": {"roi": roi, "expected": list(expected), "threshold": 0.3, "replace": list(replace),
                                     "only_rec": False, "color_filter": "", "model": ""}}


def node(name, reco):
    return name, reco["type"], ht.ocr_specs(reco)


ENTER_RECO = ocr([400, 325, 480, 45], "^Enter")
CLOSE_RECO = ocr([540, 430, 200, 70], "^(Close|Confirm|OK)$")
ENTER = node("MirrorEnterDialog", ENTER_RECO)
CLOSE = node("PopupButton", CLOSE_RECO)


def test_a_box_grazing_a_roi_is_not_read_there():
    # #157: a battle skill text whose box reaches 1 px into MirrorEnterDialog's roi; batched, MaaFramework re-read
    # that 443 x 1 sliver (7.6 s, 4 -> 12 GB). HubText leaves it to the roi holding most of it.
    grazing = ((437, 300, 443, 26), "Enter the stage again", 0.9)
    assert ht.pick([ENTER, CLOSE], [grazing]) == []
    assert ht.pick([ENTER, CLOSE], [((437, 330, 200, 26), "Enter", 0.9)]) == ["MirrorEnterDialog"]
    assert ht.inside((0, 0, 10, 10), (5, 0, 10, 10)) and not ht.inside((0, 0, 10, 10), (6, 0, 10, 10))


def test_pick_keeps_order_threshold_and_expected():
    boxes = [((560, 450, 80, 30), "Close", 0.9), ((440, 330, 100, 26), "Enter", 0.2)]
    assert ht.pick([ENTER, CLOSE], boxes) == ["PopupButton"]  # Enter below the threshold
    assert ht.pick([ENTER, CLOSE], [((560, 450, 80, 30), "Closed", 0.9)]) == []
    fixed = node("Fixed", ocr([540, 430, 200, 70], "^OK$", replace=[["0K", "OK"]]))
    assert ht.pick([fixed], [((560, 450, 80, 30), "0K", 0.9)]) == ["Fixed"]


def test_and_needs_every_part_or_any_and_others_always_check():
    both = node("Both", {"type": "And", "param": {"all_of": [{"recognition": ENTER_RECO}, {"recognition": CLOSE_RECO}]}})
    either = node("Either", {"type": "Or", "param": {"any_of": [{"recognition": ENTER_RECO}, {"recognition": CLOSE_RECO}]}})
    other = node("Template", {"type": "TemplateMatch", "param": {}})
    close = [((560, 450, 80, 30), "OK", 0.9)]
    assert ht.pick([both, either, other], close) == ["Either", "Template"]
    assert ht.pick([both], close + [((440, 330, 100, 26), "Enter", 0.9)]) == ["Both"]
    # A template gate in an And (#157, the battle popups) is left to the node's own check; HubText judges the text.
    gate = {"recognition": {"type": "TemplateMatch", "param": {}}}
    gated = node("Gated", {"type": "And", "param": {"all_of": [gate, {"recognition": CLOSE_RECO}]}})
    assert gated[2] == ht.ocr_specs(CLOSE_RECO)
    assert ht.pick([gated], close) == ["Gated"] and ht.pick([gated], []) == []
    assert ht.ocr_specs({"type": "Or", "param": {"any_of": [gate, {"recognition": CLOSE_RECO}]}}) is None
    assert ht.ocr_specs({"type": "And", "param": {"all_of": [gate]}}) is None
    own_model = ocr([0, 0, 10, 10], "x")
    own_model["param"]["model"] = "other"
    assert ht.ocr_specs(own_model) is None
    mixed = {"type": "And", "param": {"all_of": [{"recognition": own_model}, {"recognition": CLOSE_RECO}]}}
    assert ht.ocr_specs(mixed) == ht.ocr_specs(CLOSE_RECO)


def test_windows_stay_within_the_det_side_and_hold_any_box_whole():
    # The det model shrinks an image wider than 960 px; HubText's rois span 1210 px (40..1250), where the shrunk pass
    # read "✓Confirm" and no SKIP (tests/screens/FormationNoSinners.png, EventChoicesLitTop.png).
    rois = [[40, 30, 100, 50], [1150, 600, 100, 80]]
    side = ht.DET_SIDE
    assert ht.windows(rois) == [[40, 30, side, 650], [1250 - side, 30, side, 650]]  # 710 px overlap
    assert ht.windows([[0, 0, side, 20]]) == [[0, 0, side, 20]]
    wide = ht.windows([[0, 0, 2000, 20]])
    assert len(wide) == 3 and wide[0][0] == 0 and wide[-1][0] + side == 2000 and all(w[2] == side for w in wide)


class Det:
    """A context whose OCR finds each patch of one value in its roi (a 50 x 20 box a value: its text "v<value>") and
    records each call's roi."""

    def __init__(self):
        self.rois = []

    def run_recognition_direct(self, kind, param, image):
        x, y, w, h = param.roi
        self.rois.append(param.roi)
        part = image[y:y + h, x:x + w, 0]
        found = []
        for value in sorted(set(part.flat) - {0}):
            ys, xs = np.nonzero(part == value)
            box = [x + int(xs.min()), y + int(ys.min()), int(np.ptp(xs)) + 1, int(np.ptp(ys)) + 1]
            found.append(types.SimpleNamespace(box=box, text=f"v{value}", score=0.9))
        return types.SimpleNamespace(all_results=found)


def lit(*boxes):
    """A black screen with a patch of value 100, 110, ... in each box."""
    image = np.zeros((720, 1280, 3), np.uint8)
    for i, (x, y, w, h) in enumerate(boxes):
        image[y:y + h, x:x + w] = 100 + 10 * i
    return image


def test_rois_wider_than_the_det_side_read_in_one_det_call_at_full_size():
    # ExpText's rois (2026-10-30): Downloading at the left edge, Loading and Event at the right, 1210 px in all. Two
    # 960 px windows took two det calls a pass; stacked as groups of at most 960 px, one canvas holds them, none shrunk.
    rois = [[40, 600, 440, 36], [340, 380, 600, 180], [905, 510, 138, 34], [1060, 625, 190, 40]]
    left, right = (60, 605, 50, 20), (1100, 630, 50, 20)
    det = Det()
    out = ht.ocr_pass(det, lit(left, right), rois)
    assert len(det.rois) == 1 and max(det.rois[0][2:]) <= ht.DET_SIDE
    assert sorted(out) == [(left, "v100", 0.9), (right, "v110", 0.9)]  # on the screen, where the rois are


def test_rois_no_canvas_holds_read_in_windows():
    # Rois that stack taller than the det side, as MirrorHub's (HubText) do, read in the overlapping windows.
    rois = [[40, 30, 100, 650], [1150, 30, 100, 650]]
    box = (1160, 600, 50, 20)
    det = Det()
    out = ht.ocr_pass(det, lit(box), rois)
    assert [list(r) for r in det.rois] == ht.windows(rois) and out == [(box, "v100", 0.9)]


def test_mask_keeps_only_the_rois():
    image = np.full((720, 1280, 3), 255, np.uint8)
    out = ht.mask(image, [[10, 20, 30, 40], [100, 100, 5, 5]])
    assert out.sum() == 255 * 3 * (30 * 40 + 25) and out[20, 10].all() and not out[19, 10].any()
    assert ht.union([[10, 20, 30, 40], [100, 100, 5, 5]]) == [10, 20, 95, 85]
