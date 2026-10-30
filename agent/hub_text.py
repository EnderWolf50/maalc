"""MirrorHub's OCR screens read in one pass the Agent judges (#157).

MaaFramework 5.14.3 batches a next list's OCR: one pass over all their rois, then each OCR re-reads every box of
that pass crossing its roi edge (OCRer::handle_cached). A box 1 px into a roi is re-read as a 1 px sliver padded to
48 px x (width / height): a battle skill text 443 x 1 took 7.6 s and the Tasker from 4 to 12 GB, any sliver ~4.4 GB.
HubText runs that one pass itself (run_recognition_direct has no batch cache) and judges each screen from its boxes:
a box counts for a roi when at least half of it lies inside, so no sliver is ever read. The screens that pass then
check with their own OCR, unbatched, so a hit is what MaaFramework reads.

The det model shrinks an image wider than DET_SIDE to that width (MaaXYZ/MaaFramework#1531), and the rois of a hub
span 1210 px: shrunk, a button read "✓Confirm" and an event's SKIP read nothing, both screens left out though their
own OCR reads them. So the pass groups the rois left to right, each group at most DET_SIDE px wide, and stacks the
groups on one canvas for one det call; two windows took twice the det (the Luxcavation children's CI runs 247 ->
382 s). Where the stack is taller than DET_SIDE (MirrorHub's HubText) it runs in windows of at most DET_SIDE px
instead; for a 1210 px union two of them overlap by 710 px, and a box wider than the overlap may be cut.
A screen whose text only reads when det finds no box and the whole roi goes to rec (the battlefield's VICTORY) sits
in the tail, where it always checks.
"""

import json
import re

import numpy as np
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.pipeline import JOCR, JRecognitionType

INSIDE = 0.5  # share of a box's area inside a roi for the box to count there
DET_SIDE = 960  # the det model's max side (fastdeploy DBDetector's max_side_len)
GAP = 16  # black rows between two groups of rois on the det canvas, so det joins no text across them


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


def windows(rois):
    """The union of rois cut into as few windows of at most DET_SIDE px wide as cover it, spread evenly, so they
    overlap as much as they can (a 720 px screen is never taller than DET_SIDE)."""
    x, y, w, h = union(rois)
    n = -(-w // DET_SIDE)
    if n == 1:
        return [[x, y, w, h]]
    return [[x + round(i * (w - DET_SIDE) / (n - 1)), y, DET_SIDE, h] for i in range(n)]


def stack(rois):
    """The rois left to right in groups whose union is at most DET_SIDE px wide, each group's union stacked under the
    last on a canvas, GAP px apart: [(the union on the screen, its top on the canvas)] and the canvas (w, h). None
    when one group holds them all or the canvas is wider or taller than DET_SIDE."""
    groups = []
    for roi in sorted(rois):
        if groups and union(groups[-1] + [roi])[2] <= DET_SIDE:
            groups[-1].append(roi)
        else:
            groups.append([roi])
    placed, top = [], 0
    for group in groups:
        placed.append((union(group), top))
        top += placed[-1][0][3] + GAP
    size = max(u[2] for u, _ in placed), top - GAP
    return None if len(placed) == 1 or max(size) > DET_SIDE else (placed, size)


def ocr_pass(context, image, rois):
    """[(box, text, score)] of the text in rois, read with the rest of the image black: one det call on the stack of
    their groups when it holds them, else window by window."""
    masked = mask(image, rois)
    if not (stacked := stack(rois)):
        out = []
        for win in windows(rois):
            detail = context.run_recognition_direct(JRecognitionType.OCR, JOCR(roi=tuple(win), threshold=0), masked)
            out += [(tuple(r.box), r.text, r.score) for r in (detail.all_results if detail else [])]
        return out
    placed, (w, h) = stacked
    canvas = np.zeros((max(h, image.shape[0]), max(w, image.shape[1]), 3), image.dtype)
    for (x, y, gw, gh), top in placed:
        canvas[top:top + gh, :gw] = masked[y:y + gh, x:x + gw]
    detail = context.run_recognition_direct(JRecognitionType.OCR, JOCR(roi=(0, 0, w, h), threshold=0), canvas)
    out = []
    for r in detail.all_results if detail else []:
        bx, by, bw, bh = r.box
        for (x, y, _, gh), top in placed:  # the group whose band holds the box's middle
            if top <= by + bh / 2 < top + gh:
                out.append(((bx + x, by - top + y, bw, bh), r.text, r.score))
                break
    return out


def screens(context, name):
    """A HubText node's entries as (name, kind, specs), and the rois its pass reads."""
    names = entries(name, lambda n: context.get_node_data(n)["recognition"]["param"]["custom_recognition_param"])
    nodes = []
    for entry in names:
        reco = context.get_node_data(entry)["recognition"]
        nodes.append((entry, reco["type"], ocr_specs(reco)))
    return nodes, [s[0] for *_, specs in nodes for s in specs or []]


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
            self.lists[argv.node_name] = screens(context, argv.node_name)
        nodes, rois = self.lists[argv.node_name]
        if not (picked := pick(nodes, ocr_pass(context, argv.image, rois))):
            return None
        context.override_next(argv.node_name, ["NoBatchOCR", *picked, *param["tail"]])
        return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})
