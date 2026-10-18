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


def test_mirror_hub_reads_its_ocr_screens_through_hub_text():
    # #149, #157: batched, MaaFramework OCRs a next list's rois in one pass, and each OCR re-reads every box of that
    # pass crossing its roi edge (OCRer::handle_cached), slivers 1 px high padded to 48 px x (width / height): a
    # battle skill text 1 px into MirrorEnterDialog's roi, 443 x 1, took 7.6 s and the Tasker from 4 to 12 GB.
    # MirrorHub lists no OCR; HubText (agent/hub_text.py) reads its screens and lists the ones that may be up behind
    # NoBatchOCR. BattleHUD, two templates, comes before HubText, and its own list does not batch.
    nodes = load_nodes()
    hub = strip(nodes["MirrorHub"]["next"])
    assert [o for n in hub for o in batchable_ocr(nodes, n)] == []
    assert hub.index("BattleHUD") < hub.index("HubText")
    assert batchable_ocr(nodes, "BattleHUD") == [] and nodes["BattleHUD"]["any_of"] == ["BattleTurn", "BattlePause"]
    hud = strip(nodes["BattleHUD"]["next"])
    assert hud[-2:] == ["BattleTurn", "BattlePause"] and len(batch_plan(nodes, hud)) < 2
    param = nodes["HubText"]["custom_recognition_param"]
    assert param["tail"] == hub[hub.index("HubText") + 1:]
    for name in param["entries"]:  # all OCR, so HubText judges each (hub_text.ocr_specs)
        kind, params = recognition(nodes[name])
        subs = [s if isinstance(s, dict) else nodes[s] for s in params.get("all_of", []) + params.get("any_of", [])]
        assert kind == "OCR" or subs and all(recognition(s)[0] == "OCR" for s in subs), name
    assert len(batch_plan(nodes, ["NoBatchOCR", *param["entries"], *param["tail"]])) == 1


def test_no_next_list_batches_two_ocr_recognitions_under_one_name():
    # #149: the batch files its text boxes by recognition name. Two under one name (inline subs without a sub_name
    # are all "OCR") pool their boxes, and each re-reads every pooled box crossing its roi: 0.6 -> 7.4 GB.
    nodes = load_nodes()
    shared = {}
    for name, node in nodes.items():
        names = [o for n in strip(node.get("next", [])) if nodes[n].get("enabled", True) for o, _ in batchable_ocr(nodes, n)]
        if dupes := sorted(o for o, k in Counter(names).items() if k > 1):
            shared[name] = dupes
    assert shared == {}


def test_batch_plan_follows_maaframework():
    nodes = load_nodes()
    assert batch_plan(nodes, ["Connecting", "RetryPopup", "MaintenanceNotice"]) == [
        "Connecting", "RetryPopup", "MaintenanceNoticeText", "MaintenanceNoticeClose"]
    assert batch_plan(nodes, ["NoBatchOCR", "Connecting", "RetryPopup"]) == ["NoBatchOCRModel"]
