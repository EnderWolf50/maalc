import json
import re
from collections import Counter
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent / "assets/resource/base/pipeline"


def load_nodes():
    nodes = {}
    for path in sorted(PIPELINE.glob("*.json")):
        lines = path.read_text(encoding="utf-8").splitlines()
        nodes |= json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))
    return nodes


def recognition(spec):
    """(type, params) of a node or an inline sub-recognition, v1 or v2 form."""
    reco = spec.get("recognition", "DirectHit")
    return (reco, spec) if isinstance(reco, str) else (reco["type"], reco.get("param", {}))


def batched_ocr_names(nodes, name, spec=None):
    """The names MaaFramework 5.14.3 files a node's OCR under in a next list's batch (PipelineTask::collect_ocr_from_reco)."""
    kind, params = recognition(spec if spec is not None else nodes[name])
    if kind == "OCR":
        return [] if params.get("only_rec") or params.get("color_filter") else [name]
    names = []
    for sub in params.get("all_of", []) + params.get("any_of", []):
        if isinstance(sub, str):
            names += batched_ocr_names(nodes, sub)
        else:  # an inline sub-recognition goes by its sub_name, which defaults to its type: "OCR"
            names += batched_ocr_names(nodes, sub.get("sub_name", recognition(sub)[0]), sub)
    return names


def test_no_next_list_batches_two_ocr_recognitions_under_one_name():
    # #149: MaaFramework OCRs a next list's OCR rois in one pass and files the text boxes by recognition name. Two
    # under one name (inline subs without a sub_name are all "OCR") pool their boxes, each copied once per roi it
    # touches; each then re-reads every pooled box that crosses its roi, slivers 1 px high batched at one width,
    # 48 px x (width / height) each: 1.5 s an OCR and the Tasker from 0.6 to 7.4 GB.
    nodes = load_nodes()
    shared = {}
    for name, node in nodes.items():
        listed = [re.sub(r"^(\[\w+\])+", "", n) for n in node.get("next", [])]
        names = [o for n in listed if nodes[n].get("enabled", True) for o in batched_ocr_names(nodes, n)]
        if dupes := sorted(o for o, k in Counter(names).items() if k > 1):
            shared[name] = dupes
    assert shared == {}
