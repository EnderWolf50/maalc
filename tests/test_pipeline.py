import json
import re
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


def batchable_ocr(nodes, name, spec=None):
    """(name, params) of a node's OCR MaaFramework 5.14.3 may batch (PipelineTask::collect_ocr_from_reco)."""
    kind, params = recognition(spec if spec is not None else nodes[name])
    if kind == "OCR":
        return [] if params.get("only_rec") or params.get("color_filter") else [(name, params)]
    found = []
    for sub in params.get("all_of", []) + params.get("any_of", []):
        if isinstance(sub, str):
            found += batchable_ocr(nodes, sub)
        else:  # an inline sub-recognition goes by its sub_name, which defaults to its type: "OCR"
            found += batchable_ocr(nodes, sub.get("sub_name", recognition(sub)[0]), sub)
    return found


def batch_plan(nodes, listed):
    """The OCR a next list batches (PipelineTask::prepare_batch_ocr / try_add_ocr_node); fewer than 2 is no batch."""
    plan, model = [], None
    for name, params in (o for n in listed if nodes[n].get("enabled", True) for o in batchable_ocr(nodes, n)):
        if isinstance(params.get("roi"), str) and params["roi"] in plan:
            continue
        model = params.get("model", "") if model is None else model
        if params.get("model", "") == model:  # the first one's model; the others are left out
            plan.append(name)
    return plan


def test_no_next_list_batches_its_ocr():
    # #149, #157: batched, MaaFramework OCRs a next list's rois in one pass, and each OCR re-reads every box of that
    # pass crossing its roi edge (OCRer::handle_cached), slivers 1 px high padded to 48 px x (width / height): a
    # battle skill text 1 px into MirrorEnterDialog's roi, 443 x 1, took 7.6 s and the Tasker from 4 to 12 GB.
    # NoBatchOCR's model keeps the batch to one.
    nodes = load_nodes()
    batched = {}
    for name, node in nodes.items():
        if len(plan := batch_plan(nodes, [re.sub(r"^(\[\w+\])+", "", n) for n in node.get("next", [])])) > 1:
            batched[name] = plan
    assert batched == {}


def test_batch_plan_follows_maaframework():
    nodes = load_nodes()
    assert batch_plan(nodes, ["Connecting", "RetryPopup", "MaintenanceNotice"]) == [
        "Connecting", "RetryPopup", "MaintenanceNoticeText", "MaintenanceNoticeClose"]
    assert batch_plan(nodes, ["NoBatchOCR", "Connecting", "RetryPopup"]) == ["NoBatchOCRModel"]
