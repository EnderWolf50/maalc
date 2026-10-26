"""MirrorHub's OCR screens read in one pass the Agent judges (#157).

MaaFramework 5.14.3 batches a next list's OCR: one pass over all their rois, then each OCR re-reads every box of
that pass crossing its roi edge (OCRer::handle_cached). A box 1 px into a roi is re-read as a 1 px sliver padded to
48 px x (width / height): a battle skill text 443 x 1 took 7.6 s and the Tasker from 4 to 12 GB, any sliver ~4.4 GB.
HubText runs that one pass itself (run_recognition_direct has no batch cache) and judges each screen from its boxes:
a box counts for a roi when at least half of it lies inside, so no sliver is ever read. The screens that pass then
check with their own OCR, unbatched, so a hit is what MaaFramework reads.
"""

import json
import re

from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.pipeline import JOCR, JRecognitionType

INSIDE = 0.5  # share of a box's area inside a roi for the box to count there


def ocr_specs(reco):
    """[(roi, expected, threshold, replace)] of an OCR or an And/Or of OCRs (get_node_data form); None when a part is
    anything else or reads differently (only_rec, color_filter, its own model, a roi from another node). In an And,
    every part HubText cannot judge (a template gate, an OCR that reads differently) is left to the node's own
    check, as long as one part is an OCR it can judge: each part of an And is necessary on its own."""
    kind, param = reco["type"], reco["param"]
    if kind == "OCR":
        if param["only_rec"] or param["color_filter"] or param["model"] or not isinstance(param["roi"], list):
            return None
        return [(param["roi"], [re.compile(e) for e in param["expected"]], param["threshold"], param["replace"])]
    if kind in ("And", "Or"):
        subs = [ocr_specs(s["recognition"]) for s in param.get("all_of", []) + param.get("any_of", [])]
        judged = [s for s in subs if s is not None]
        if kind == "And" and judged:
            subs = judged
        return None if any(s is None for s in subs) else [x for s in subs for x in s]
    return None


def inside(box, roi):
    x, y, w, h = box
    rx, ry, rw, rh = roi
    iw = max(0, min(x + w, rx + rw) - max(x, rx))
    ih = max(0, min(y + h, ry + rh) - max(y, ry))
    return w * h > 0 and iw * ih >= INSIDE * w * h


def reads(spec, results):
    """Whether one OCR's expected text is among results [(box, text, score)] counting for its roi."""
    roi, expected, threshold, replace = spec
    for box, text, score in results:
        if score < threshold or not inside(box, roi):
            continue
        for old, new in replace:
            text = text.replace(old, new)
        if not expected or any(e.search(text) for e in expected):
            return True
    return False


def pick(nodes, results):
    """The nodes [(name, kind, specs)] that may be up, in order; a node HubText cannot judge (specs None) always may."""
    return [name for name, kind, specs in nodes
            if specs is None or (any if kind == "Or" else all)(reads(s, results) for s in specs)]


def entries(name, params):
    """A HubText node's entries: those of its base first (custom_recognition_param "base", another HubText node, so the
    popups every hub reads are listed once), then its own. params(name) is that node's custom_recognition_param."""
    param = params(name)
    return (entries(param["base"], params) if "base" in param else []) + param["entries"]


def mask(image, rois):
    """The image black outside rois, as MaaFramework's batch reads it."""
    out = image * 0
    for x, y, w, h in rois:
        out[y:y + h, x:x + w] = image[y:y + h, x:x + w]
    return out


def union(rois):
    x0, y0 = min(r[0] for r in rois), min(r[1] for r in rois)
    return [x0, y0, max(r[0] + r[2] for r in rois) - x0, max(r[1] + r[3] for r in rois) - y0]


class HubText(CustomRecognition):
    """A hub's OCR screens (custom_recognition_param: entries in hub order, after its base's, then tail) in one unbatched
    OCR; every hub's text node (MirrorHub's HubText, GoHome's HomeText, ...) uses it.

    The entries that may be up become this node's next list behind NoBatchOCR, then the tail: each checks with its
    own OCR, unbatched. None may be up: no hit, and the hub goes on to the tail itself.
    """

    def __init__(self):
        super().__init__()
        self.lists = {}  # node name -> (its entries as (name, kind, specs), their rois): read once

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        param = argv.custom_recognition_param
        param = json.loads(param) if isinstance(param, str) else param
        if argv.node_name not in self.lists:
            names = entries(argv.node_name, lambda name: context.get_node_data(name)["recognition"]["param"]["custom_recognition_param"])
            nodes = []
            for name in names:
                reco = context.get_node_data(name)["recognition"]
                nodes.append((name, reco["type"], ocr_specs(reco)))
            self.lists[argv.node_name] = nodes, [s[0] for *_, specs in nodes for s in specs or []]
        nodes, rois = self.lists[argv.node_name]
        detail = context.run_recognition_direct(JRecognitionType.OCR, JOCR(roi=tuple(union(rois)), threshold=0), mask(argv.image, rois))
        results = [(tuple(r.box), r.text, r.score) for r in (detail.all_results if detail else [])]
        if not (picked := pick(nodes, results)):
            return None
        context.override_next(argv.node_name, ["NoBatchOCR", *picked, *param["tail"]])
        return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})
