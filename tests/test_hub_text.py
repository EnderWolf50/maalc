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


def test_mask_keeps_only_the_rois():
    image = np.full((720, 1280, 3), 255, np.uint8)
    out = ht.mask(image, [[10, 20, 30, 40], [100, 100, 5, 5]])
    assert out.sum() == 255 * 3 * (30 * 40 + 25) and out[20, 10].all() and not out[19, 10].any()
    assert ht.union([[10, 20, 30, 40], [100, 100, 5, 5]]) == [10, 20, 95, 85]
