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


def strip(listed):
    return [re.sub(r"^(\[\w+\])+", "", n) for n in listed]


def test_no_next_list_batches_its_ocr():
    # #149, #157: batched, MaaFramework OCRs a next list's rois in one pass, and each OCR re-reads every box of that
    # pass crossing its roi edge (OCRer::handle_cached), slivers 1 px high padded to 48 px x (width / height): a
    # battle skill text 1 px into MirrorEnterDialog's roi, 443 x 1, took 7.6 s and the Tasker from 4 to 12 GB.
    # NoBatchOCR's model keeps the batch to one.
    nodes = load_nodes()
    batched = {}
    for name, node in nodes.items():
        if len(plan := batch_plan(nodes, strip(node.get("next", [])))) > 1:
            batched[name] = plan
    assert batched == {}


def test_batch_plan_follows_maaframework():
    nodes = load_nodes()
    assert batch_plan(nodes, ["Connecting", "RetryPopup", "MaintenanceNotice", "PopupButton"]) == [
        "RetryPopupText", "MaintenanceNoticeText", "PopupButtonText"]
    assert batch_plan(nodes, ["NoBatchOCR", "RetryPopup", "PopupButton"]) == ["NoBatchOCRModel"]


def ungated_ocr(nodes, name, spec=None):
    """OCR of a node that can run with no TemplateMatch hit before it: a bare OCR, or one in an Or, or in an And
    whose first sub-recognition is no TemplateMatch."""
    kind, params = recognition(spec if spec is not None else nodes[name])
    subs = [(s, None) if isinstance(s, str) else (s.get("sub_name", recognition(s)[0]), s)
            for s in params.get("all_of", []) + params.get("any_of", [])]
    if kind == "OCR":
        return [name]
    if kind == "And" and subs and recognition(subs[0][1] if subs[0][1] is not None else nodes[subs[0][0]])[0] == "TemplateMatch":
        return []
    return [o for s, sp in subs for o in ungated_ocr(nodes, s, sp)]


def test_screen_checks_read_no_text_until_their_screen_is_up():
    # #157: the hub told its screens apart by 37 OCR, each a det + rec pass (~45 ms) when NoBatchOCR keeps them apart,
    # 0.5 -> 1.2 s a pass. Fixed screen labels are TemplateMatch now (green-masked where the ground varies); text that
    # varies or has no live capture stays OCR behind a template of its screen (a popup button's end, MirrorEntryPage),
    # so a battle reads no text.
    nodes = load_nodes()
    for entry in ("MirrorHub", "RecoverStartApp"):
        listed = [n for n in strip(nodes[entry]["next"]) if n != "NoBatchOCR"]
        assert [o for n in listed for o in ungated_ocr(nodes, n)] == [], entry
