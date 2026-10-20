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
    # The server's popups before the turn run no OCR on a battle round (live A/B: 3 OCR a round, ~130 ms): a
    # template comes first, and MaaFramework's And stops at the first part that misses.
    assert hud[0] == "NoBatchOCR" and hud[1:-2] == ["Connecting", "RetryPopup", "PopupButton"]
    assert all(template_first(nodes, nodes[n]) for n in hud[1:-2])
    # Connecting is a template: it waits in MirrorHub's list, ahead of HubText, as it does in BattleHUD's.
    assert hub.index("BattleHUD") < hub.index("Connecting") < hub.index("HubText")
    param = nodes["HubText"]["custom_recognition_param"]
    assert param["tail"] == hub[hub.index("HubText") + 1:]
    for name in param["entries"]:  # OCR HubText judges (hub_text.ocr_specs): OCR, And / Or of OCR, gates in an And
        kind, params = recognition(nodes[name])
        subs = [recognition(s)[0] for s in parts(nodes, params)]
        assert (kind == "OCR" or kind == "Or" and subs and all(s == "OCR" for s in subs)
                or kind == "And" and "OCR" in subs and all(s in ("OCR", "TemplateMatch", "Or") for s in subs)), name
    assert len(batch_plan(nodes, ["NoBatchOCR", *param["entries"], *param["tail"]])) == 1


def template_first(nodes, spec):
    """Whether a recognition matches a template before any OCR runs: a template, an Or of them, an And led by one."""
    kind, params = recognition(spec)
    subs = parts(nodes, params)
    return (kind == "TemplateMatch" or kind == "Or" and subs and all(template_first(nodes, s) for s in subs)
            or kind == "And" and template_first(nodes, subs[0]))


def parts(nodes, params):
    """The sub-recognitions of an And / Or, a node named by reference as its own spec."""
    return [s if isinstance(s, dict) else nodes[s] for s in params.get("all_of", []) + params.get("any_of", [])]


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


def test_the_screens_that_lift_a_held_finger_are_hub_nodes():
    # #150: hold_turn lifts on these; each is a MirrorHub screen (its list or HubText's entries, #157), so the hub
    # acts on it once the finger is up. BattlePause, which holds again, is reached from BattleHUD.
    import actions
    nodes = load_nodes()
    hub = [re.sub(r"^(\[\w+\])+", "", n) for n in nodes["MirrorHub"]["next"]]
    hub += nodes["HubText"]["custom_recognition_param"]["entries"]
    assert set(actions.BATTLE_LEFT) <= set(hub)
    assert nodes["BattlePause"]["custom_action"] == "HoldTurn" and "BattlePause" in nodes["BattleHUD"]["next"]
    # A popup over a playing turn lifts the finger; BattleHUD acts on it before BattlePause holds again.
    battle = nodes["BattleHUD"]["next"]
    assert all(battle.index(n) < battle.index("BattlePause") for n in actions.BATTLE_POPUPS)


def test_batch_plan_follows_maaframework():
    nodes = load_nodes()
    assert batch_plan(nodes, ["Connecting", "RetryPopup", "MaintenanceNotice"]) == [
        "RetryPopupText", "MaintenanceNoticeText", "MaintenanceNoticeClose"]
    assert batch_plan(nodes, ["NoBatchOCR", "Connecting", "RetryPopup"]) == ["NoBatchOCRModel"]


OPENING = ["MirrorEntryNewRun", "MirrorEnterDialog", "MirrorEntryPaused", "TeamSelect", "LevelWarning", "StarlightPage",
           "StarlightConfirm", "StartingGift", "GiftGet", "GiftSearch", "GiftSearchForgo", "ThemePack"]


def test_the_opening_waits_for_screens_not_for_delays():
    # #115: each opening action ends once the next screen is up, so MaaFramework's default 200 ms post_delay only
    # held MirrorHub back; GiftSearchForgo waited 2 s after its tap instead of for the loading screen.
    nodes = load_nodes()
    for name in OPENING:
        assert nodes[name].get("action") == "Custom" and nodes[name].get("post_delay") == 0, name
    assert nodes["GiftSearchForgo"]["custom_action"] == "TapUntil"
    # Nothing to act on: the hub's own rate_limit paces the looks at a loading screen.
    assert nodes["Loading"].get("pre_delay") == 0 and nodes["Loading"].get("post_delay") == 0
    # Live (2026-10-20): the last loading screen HubText picked was gone when its own OCR looked, and the hub waited
    # out HubText's 1 s timeout and HubTextLost's delays, 1.7 s, with the theme pack page up.
    assert nodes["HubText"]["timeout"] <= 500
    assert nodes["HubTextLost"].get("pre_delay") == 0 and nodes["HubTextLost"].get("post_delay") == 0
