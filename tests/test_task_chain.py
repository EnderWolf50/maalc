"""The task chain (#364, ADR 0010): a task with nothing left to do ends a success, so the client's list goes on.

MaaFramework 5.14.3 ends a task a success when it reaches a node with an empty next off any [JumpBack] (a stack
with nothing to go back to). maa-tools test runs recognitions only, with no task status, so this runs the real
MirrorDungeon task: the repo's resource bundle, a still black controller, the agent's own TaskStart, StuckFlag and
DoneFlag. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a child process: this file
run as a script, as test_map_cost.py does.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import traceback
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from agent_patch import patch_all

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it
UPDATE_GIFT = 9990001  # a gift the fake maalc-resource adds to data/gift_search.json

if __name__ != "__main__":  # pytest; the script (child) imports actions itself, under a stand-in AgentServer
    import build_resource_package as brp
    import actions
    import daily_actions
    import run_start_actions
    import lux_actions
    import recovery
    from test_actions import clock, context  # noqa: F401 (the fake Maa context the in-process tests use)
    from fake_resource import install, publish, tree


def child(work=None):
    """Run MirrorDungeon until TaskDone; print its status and nodes. With `work` (a folder update_scene made): the install
    in it is the bundle and the data folder, and two tasks run on it, each starting with an update from its fake remote."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.custom_recognition import CustomRecognition
    from maa.resource import Resource
    from maa.tasker import Tasker

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    if work:
        import event_actions
        import settings
        import shop_actions

        settings.ROOT = work / "root"  # data_dir() is the install's now; the swap writes there, never in the checkout

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # start_app, click, swipe, touch_*, keys, text, scroll: nothing moves
            return lambda *args: True

    out = {"error": None, "starts": 0, "seen": [], "nodes": [], "probe": 0}

    def seen():
        """What the agent holds of data/ at this moment."""
        return {"events": [e["id"] for e in event_actions.event_table() if e["id"] in (990001, 990002)],
                "gift": actions.GIFT_NAMES.get(UPDATE_GIFT), "tier": shop_actions.GIFT_TIERS.get(UPDATE_GIFT), "probe": out["probe"],
                "log": [line[9:] for line in actions.LOG if "resource" in line]}

    class HubText(CustomRecognition):
        """MirrorHub's first pass: an action found nothing left to do (PlanRun on the entry page); no screen hits."""

        def analyze(self, context, argv):
            try:
                out["done_was"] = actions.TASK["done"]  # TaskStart cleared the last task's
                if work:
                    out["seen"].append(seen())
                actions.done("nothing left to do")
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return None

    class TaskStart(actions.TaskStart):
        def run(self, context, argv):
            out["starts"] += 1
            return super().run(context, argv)

    class ReloadProbe(CustomAction):
        """A node only the fake maalc-resource's pipeline has: reached only when the task runs on the reloaded pipeline."""

        def run(self, context, argv):
            out["probe"] += 1
            return True

    resource.register_custom_action("TaskStart", TaskStart())
    resource.register_custom_action("ReloadProbe", ReloadProbe())
    resource.register_custom_recognition("StuckFlag", actions.StuckFlag())
    resource.register_custom_recognition("DoneFlag", actions.DoneFlag())
    resource.register_custom_recognition("HubText", HubText())
    resource.post_bundle(settings.ROOT / "resource" / "base" if work else ROOT / "assets" / "resource" / "base").wait()
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    if work:
        out["before"] = seen()  # the caches are warm: a task that sees the new data found them cleared
        for n in (1, 2):
            if n == 2:  # the next publish, between two tasks of the same agent
                shutil.copyfile(work / "next.json", work / "remote" / "main" / "manifest.json")
            detail = tasker.post_task("MirrorDungeon").wait().get()
            out["succeeded"] = detail.status.succeeded
            out["nodes"].append([node.name for node in detail.nodes])
        print(json.dumps(out))
        return
    actions.TASK["done"] = "left by the last task"
    detail = tasker.post_task("MirrorDungeon").wait().get()
    out.update(succeeded=detail.status.succeeded, nodes=[n.name for n in detail.nodes], first_starts=out["starts"])
    actions.STUCK["halted"] = "maintenance"  # D8: an account-level stop earlier this launch
    detail = tasker.post_task("MirrorDungeon").wait().get()
    out["after_halt"] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes]}
    print(json.dumps(out))


def test_a_task_with_nothing_left_to_do_ends_a_success_on_task_done():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["first_starts"] == 1 and out["done_was"] is None
    assert out["succeeded"] is True
    assert out["nodes"][0] == "MirrorDungeon" and out["nodes"][-1] == "TaskDone"


def test_a_task_after_an_account_level_stop_fails_at_its_entry_node():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["after_halt"] == {"succeeded": False, "nodes": ["MirrorDungeon"]}


def test_each_task_starts_with_a_clean_slate_but_the_game_restarts_count_per_launch(context, monkeypatch):
    # #364, ADR 0010: a task list runs tasks on one agent; what one task left must not reach the next.
    actions.RUN.update(floor=3, guard=2)
    actions.TASK.update(runs=1, done="1 of 1 runs done")
    restarts = recovery.Restarts()
    for _ in range(recovery.L3_FAILED_IN_A_ROW):
        restarts.attempt("MirrorMap")
    for key, value in dict(restarts=restarts, updates=1, watch=recovery.Watchdog(), ladder=recovery.Ladder()).items():
        monkeypatch.setitem(actions.STUCK, key, value)  # restored afterwards: the later tests count from 0
    actions.STUCK.update(flag=(None, 1, "x"), kind="MirrorMap")
    actions.STUCK["watch"].hold(0.0, 600)
    actions.STUCK["ladder"].stuck("MirrorMap", 1, restarts)
    actions.SCREENS.append(np.zeros((720, 1280, 3), np.uint8))
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert actions.RUN == {} and actions.TASK == {"runs": 0, "done": None, "entry": "MirrorDungeon", "ended": False} and not actions.SCREENS
    assert (actions.STUCK["flag"], actions.STUCK["kind"]) == (None, None)
    assert actions.STUCK["ladder"].counts == recovery.Ladder().counts
    assert not actions.STUCK["watch"].held(1.0)
    assert actions.STUCK["restarts"].attempt("MailOpen") and actions.STUCK["updates"] == 1


def test_each_task_logs_the_resource_package_in_use(context, monkeypatch, tmp_path):
    # #766: version, client, format and template of the package; a checkout has no manifest and the task starts anyway.
    (tmp_path / "data").mkdir()
    patch_all(monkeypatch, "data_dir", lambda: tmp_path / "data")
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    assert "resource package: none (no manifest.json)" in logged
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"version": "2026.11.16", "client": "1.118.1", "format": 1, "template": 1, "sources": [], "files": {}}), encoding="utf-8")
    actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    assert "resource package: version 2026.11.16, client 1.118.1, format 1, template 1" in logged


def interrupted_run(context, how):
    """MirrorDungeon starts a run, then ends as how says; the next task's TaskStart runs. RUN afterwards."""
    actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon"))
    actions.RUN.update(settings={"run": {"webhook_url": ""}}, team={"id": "t1", "name": "A"}, planned=True, floor=3)
    actions.TASK["runs"] = 1
    how()
    return actions.TaskStart().run(context, SimpleNamespace(node_name=next_task)) and dict(actions.RUN)


next_task = "MirrorDungeon"


def test_a_task_the_client_interrupted_leaves_its_run_to_the_same_task(context):
    # D3 (#362): no done(), no stop(): the client stopped the task mid-run, so MirrorDungeon picks the same run up, as
    # before the task chain. Its own state still starts over: the task's runs, the ladder, the screens.
    run = interrupted_run(context, lambda: None)
    assert run["floor"] == 3 and run["team"]["id"] == "t1" and run["planned"]
    assert actions.TASK["runs"] == 0 and actions.STUCK["ladder"].counts == recovery.Ladder().counts


@pytest.mark.parametrize("how", [
    lambda: actions.done("1 of 1 runs done"),
    lambda: actions.stop(MagicMock(), "recovery used up"),
])
def test_a_task_that_ended_by_done_or_the_stop_procedure_leaves_no_run(context, monkeypatch, how):
    patch_all(monkeypatch, "screen", lambda context: np.zeros((720, 1280, 3), np.uint8))
    assert interrupted_run(context, how) == {}


def test_an_interrupted_run_does_not_reach_another_task(context, monkeypatch):
    # Not the same task: a daily task's stop would write the Mirror Dungeon run's runs.jsonl line.
    monkeypatch.setattr(sys.modules[__name__], "next_task", "ExpLuxcavation")
    assert interrupted_run(context, lambda: None) == {}


def entry_page(context, edit=lambda run, teams: None):
    """settings.json under the agent's ROOT (settings_cases' valid file, edited); the entry page reads no weekly bonus;
    GoHome ends on the main window."""
    data = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    edit(data["run"], data["teams"])
    data["run"]["webhook_url"] = "http://hook.invalid/"
    (actions.ROOT / "config").mkdir()
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    actions.RUN.clear()
    actions.TASK["modules"] = 20  # what OpenDrive read on this trip (#369)
    context.tasker.get_node_detail.return_value = SimpleNamespace(name="HomeReached")


@pytest.mark.parametrize("edit, done", [
    (lambda run, teams: run.update(runs=1), "1 of 1 runs done"),
    (lambda run, teams: run.update(stop_when_weekly_bonus_out=True), "weekly bonuses used up"),
    (lambda run, teams: teams[0].update(usage="hard_only"), "no enabled team may run normal"),
    (lambda run, teams: [t.update(enabled=False) for t in teams], "no enabled team"),  # review S3: no team at all
])
def test_a_mirror_dungeon_that_has_nothing_left_to_do_ends_a_success(context, monkeypatch, edit, done):
    # #364: the run count reached, the weekly bonuses out, no team for the difficulty: the task is done, not failed, so
    # the client's list goes on. No stop procedure: no runs.jsonl line, no webhook, no evidence; Enter is not pressed.
    entry_page(context, edit)
    actions.TASK.update(runs=1, done=None)
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    assert run_start_actions.PlanRun().run(context, None) is True
    assert done in actions.TASK["done"]
    assert not (actions.ROOT / "logs").exists() and not urlopen.called
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_called_once_with("GoHome")  # live-2 G4: the main window, not the entry page, for the next task


def test_plan_run_does_not_open_a_run_the_modules_cannot_claim(context):
    # #369: read 4 on the Drive page (< 5, one Claim): the task is done, Enter is not pressed.
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=4)
    assert run_start_actions.PlanRun().run(context, None) is True
    assert "Modules 4 < 5" in actions.TASK["done"]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_called_once_with("GoHome")


def test_plan_run_logs_modules_that_cover_a_claim(context, monkeypatch):
    # #369: a run the Modules cover says so too, not only one they do not.
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=118)
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    assert run_start_actions.PlanRun().run(context, None) is True and actions.RUN["planned"]
    assert "new run: Modules 118 >= 5" in logged


def test_plan_run_starts_when_the_modules_did_not_read(context):
    entry_page(context)
    actions.TASK.update(runs=0, done=None, modules=None)
    assert run_start_actions.PlanRun().run(context, None) is True
    assert actions.TASK["done"] is None and "modules" not in actions.TASK and actions.RUN["planned"]


def test_plan_run_backs_out_to_read_the_modules_when_the_trip_skipped_drive(context):
    # #369: the last run's Claim took 5, so an old value is none: the back key, twice at most, then the run starts.
    entry_page(context)
    actions.TASK.clear()
    actions.TASK.update(runs=0, done=None)
    for n in (1, 2):
        assert run_start_actions.PlanRun().run(context, None) is True
        context.tasker.controller.post_click_key.assert_called_with(actions.BACK_KEY)
        assert context.tasker.controller.post_click_key.call_count == n and not actions.RUN
    assert run_start_actions.PlanRun().run(context, None) is True and actions.RUN["planned"]
    assert context.tasker.controller.post_click_key.call_count == 2


@pytest.mark.parametrize("action, run", [
    ("Halt", {}),  # MaintenanceNotice, ClientOutdated
    ("ConfirmDownload", {"auto_download": False}),
    ("AcceptUpdate", {"auto_download": False}),
    ("AcceptTerms", {"auto_accept_terms": False}),
])
def test_an_account_level_stop_ends_the_whole_task_list(context, action, run):
    # #364: every task after this one would meet the same screen: after the stop procedure, post_stop empties the
    # client's queue.
    actions.RUN["settings"] = {"run": {"webhook_url": "", **run}}
    argv = SimpleNamespace(node_name="MaintenanceNotice", custom_action_param='"maintenance"', box=[0, 0, 10, 10])
    assert getattr(actions, action)().run(context, argv) is False
    context.tasker.post_stop.assert_called_once()
    assert list((actions.ROOT / "logs" / "evidence").iterdir())  # the stop procedure ran first


def test_an_update_that_keeps_coming_back_ends_the_whole_task_list(context, monkeypatch):
    # D1 (#362): the game asks for an update past its restarts with auto_download on: every later task would meet it.
    monkeypatch.setitem(actions.STUCK, "updates", actions.UPDATE_RESTARTS)
    actions.RUN["settings"] = {"run": {"webhook_url": "", "auto_download": True}}
    argv = SimpleNamespace(node_name="UpdateDialog", custom_action_param=None, box=[0, 0, 10, 10])
    assert actions.AcceptUpdate().run(context, argv) is False
    context.tasker.post_stop.assert_called_once()
    context.tasker.controller.post_click.assert_not_called()


def test_every_task_after_an_account_level_stop_fails_at_its_entry_without_a_tap_or_a_webhook(context, monkeypatch):
    # D8 (#362): MFAAvalonia hands the tasker one task at a time, so post_stop does not reach the next: the agent
    # remembers the stop for this launch, and each later entry fails before anything (no evidence, no webhook).
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    actions.RUN["settings"] = {"run": {"webhook_url": "http://hook.invalid/"}}
    argv = SimpleNamespace(node_name="MaintenanceNotice", custom_action_param='"maintenance"', box=[0, 0, 10, 10])
    assert actions.Halt().run(context, argv) is False and urlopen.call_count == 1
    evidence = list((actions.ROOT / "logs" / "evidence").iterdir())
    context.reset_mock()
    for start, node, param in [(actions.TaskStart, "ClaimMail", None), (lux_actions.LuxStart, "ExpLuxcavation", '"exp"'),
                               (daily_actions.ChargeStart, "ChargeEnkephalin", None)]:
        assert start().run(context, SimpleNamespace(node_name=node, custom_action_param=param)) is False, node
    assert urlopen.call_count == 1 and list((actions.ROOT / "logs" / "evidence").iterdir()) == evidence
    assert not context.method_calls and not context.tasker.controller.method_calls  # no tap, no key, no screenshot
    assert any("skip: account-level stop earlier this launch" in line for line in actions.LOG)


def test_the_account_level_stop_is_remembered_for_the_whole_launch(context):
    actions.RUN["settings"] = {"run": {"webhook_url": ""}}
    actions.stop(context, "recovery used up")
    assert actions.STUCK["halted"] is None  # one task's stop: the next task runs
    actions.stop(context, "maintenance", whole_list=True)
    assert actions.STUCK["halted"] == "maintenance"


def test_a_stop_of_one_task_leaves_the_list_running(context):
    actions.RUN["settings"] = {"run": {"webhook_url": ""}}
    assert actions.stop(context, "recovery used up") is False
    context.tasker.post_stop.assert_not_called()



HUB_STUCK = {"Stuck": "MirrorHub", "ExpStuck": "ExpHub", "ThreadStuck": "ThreadHub", "AssembleStuck": "AssembleHub",
             "ChargeStuck": "ChargeHub", "ClaimMailStuck": "ClaimMailHub", "PassStuck": "PassHub"}


def test_the_watchdog_counts_screens_not_the_hubs():
    # Review M5: StuckFlag skipped MirrorHub by name; the hubs reached the watchdog as if they were screens. A hub is the
    # node whose next list names its Stuck node (spec 01), so each of the seven tasks needs one.
    from test_pipeline import load_nodes

    nodes = load_nodes()
    for stuck, hub in HUB_STUCK.items():
        assert stuck in [n.split("]")[-1] for n in nodes[hub]["next"]][:1], hub  # first, as spec 01 says
    context = MagicMock()
    context.get_node_data = lambda name: {"next": [{"name": n.split("]")[-1]} for n in nodes[name].get("next", [])]}
    seen = []
    see = actions.StuckFlag.see
    actions.StuckFlag.see = staticmethod(lambda kind, image: seen.append(kind))
    try:
        for stuck, hub in HUB_STUCK.items():
            for k, name in enumerate((hub, "LuxExpEnter", "ExpText", stuck)):
                actions.STUCK.update(node=None, flag=None)
                context.tasker.get_node_detail.return_value = SimpleNamespace(name=name)
                argv = SimpleNamespace(node_name=stuck, image=None, task_detail=SimpleNamespace(node_id_list=[k + 1]))
                actions.StuckFlag().analyze(context, argv)
    finally:
        actions.StuckFlag.see = see
    assert seen == ["LuxExpEnter"] * len(HUB_STUCK)


def test_a_page_gone_mid_action_names_the_hub_of_the_task_under_way():
    # live-1 F4: a daily task's battle logged "back to MirrorHub"; the hub is the first node down the entry's next chain
    # that lists TaskDone.
    from test_pipeline import load_nodes

    nodes = load_nodes()
    context = MagicMock()
    context.get_node_data = lambda name: {"next": [{"name": n.split("]")[-1]} for n in nodes[name].get("next", [])]}
    hubs = {}
    for entry in ("MirrorDungeon", "ExpLuxcavation", "ThreadLuxcavation", "AssembleModules", "ChargeEnkephalin", "ClaimPassMissions", "ClaimMail"):
        actions.TASK["entry"] = entry
        hubs[entry] = actions.hub_name(context)
    assert hubs == {"MirrorDungeon": "MirrorHub", "ExpLuxcavation": "ExpHub", "ThreadLuxcavation": "ThreadHub",
                    "AssembleModules": "AssembleHub", "ChargeEnkephalin": "ChargeHub", "ClaimPassMissions": "PassHub", "ClaimMail": "ClaimMailHub"}

    actions.TASK["entry"] = "ExpLuxcavation"

    class Gone:
        @actions.hands_back
        def run(self, context, argv):
            raise actions.PageGone("BattleTurn")

    assert Gone().run(context, None) is True and actions.LOG[-1].endswith("Gone: BattleTurn is gone: back to ExpHub")
    actions.TASK.pop("entry")


def probe_pipeline(base):
    """pipeline/mirror_dungeon.json with one node more between the entry and the hub, which the install's pipeline lacks."""
    text = (base / "pipeline" / "mirror_dungeon.json").read_text(encoding="utf-8")
    entry, node = '"next": [\n            "MirrorHub"\n        ]', '    "TaskDone": {'
    assert text.count(entry) == 1 and text.count(node) == 1
    probe = '    "ReloadProbe": {"action": "Custom", "custom_action": "ReloadProbe", "next": ["MirrorHub"]},\n'
    return text.replace(entry, entry.replace("MirrorHub", "ReloadProbe")).replace(node, probe + node).encode()


def update_scene(work, pipeline=None):
    """An install of the repo's data/, image/ and pipeline/ under `work`, and a fake maalc-resource beside it that publishes
    2026.11.16 (an event and a gift more) and, in next.json, 2026.11.17 (the gift renamed, another event): the folder layout
    of the real one, as the install's manifest lists it as its source."""
    base, remote = work / "root" / "resource" / "base", work / "remote"
    for part in brp.rp.PARTS:
        shutil.copytree(ROOT / "assets" / "resource" / "base" / part, base / part)
    installed = brp.write_manifest(base, "2026.11.01", [str(remote)])
    manifests = []
    for version, event, gift in (("2026.11.16", 990001, "Gift One"), ("2026.11.17", 990002, "Gift Two")):
        files = {"pipeline/mirror_dungeon.json": pipeline or probe_pipeline(base), "image/probe.png": b"a template the install lacks"}
        # the files this publish changes: the rest of the package is the installed one, unchanged
        events = json.loads((base / "data" / "event_table.json").read_text(encoding="utf-8"))
        events["events"].append({"id": event, "key": "update", "options": []})
        files["data/event_table.json"] = json.dumps(events).encode()
        gifts = json.loads((base / "data" / "gift_search.json").read_text(encoding="utf-8"))
        gifts["gifts"].append({"id": UPDATE_GIFT, "keyword": "Burn", "tier": 2, "en": gift, "zh": gift})
        files["data/gift_search.json"] = json.dumps(gifts).encode()
        entries = dict(installed["files"])
        for name, data in files.items():
            (remote / version / name).parent.mkdir(parents=True, exist_ok=True)
            (remote / version / name).write_bytes(data)
            entries[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        manifests.append({**installed, "version": version, "sources": [], "files": entries})
    (remote / "main").mkdir()
    brp.dump(manifests[0], remote / "main" / "manifest.json")
    brp.dump(manifests[1], work / "next.json")
    return base, remote


def test_new_data_is_the_data_of_the_task_that_found_it_and_of_the_next_task_of_the_same_agent(tmp_path):
    # #771: the agent updates data/ at TaskStart and forgets what it read of the old files (every cache, and the gift
    # tables the modules built when they were imported). Both tasks run in one process whose caches were warm.
    update_scene(tmp_path)
    run = subprocess.run([sys.executable, __file__, "update", str(tmp_path)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["before"]["events"] == [] and out["before"]["gift"] is None and out["before"]["tier"] is None
    first, second = out["seen"]
    assert (first["events"], first["gift"], first["tier"]) == ([990001], "Gift One", 2)
    assert (second["events"], second["gift"], second["tier"]) == ([990002], "Gift Two", 2)
    assert any("2026.11.01 -> 2026.11.16" in line for line in first["log"])
    assert any("version 2026.11.16" in line for line in first["log"]) and any("version 2026.11.17" in line for line in second["log"])
    assert out["succeeded"] is True


def test_a_bundle_that_does_not_load_puts_the_old_files_back_and_the_task_runs_on_them(tmp_path):
    # #772: the pipeline the fake remote published is not JSON, so the reload fails: the install is the old one again, the
    # old bundle is loaded again, and the task, which cannot tell, ends a success without the node the new pipeline has.
    base, _ = update_scene(tmp_path, pipeline=b"{ not a pipeline")
    before = (base / "pipeline" / "mirror_dungeon.json").read_bytes()
    run = subprocess.run([sys.executable, __file__, "update", str(tmp_path)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    assert out["succeeded"] is True and all("ReloadProbe" not in nodes and nodes[-1] == "TaskDone" for nodes in out["nodes"])
    assert (base / "pipeline" / "mirror_dungeon.json").read_bytes() == before and not (base / "image" / "probe.png").exists()
    assert [s["events"] for s in out["seen"]] == [[], []]  # data/ went back with it
    assert any("reload" in line and "previous files are back" in line for line in out["seen"][0]["log"])


def test_the_pipeline_a_task_found_is_the_pipeline_it_runs(tmp_path):
    # #772: TaskStart swaps image/ and pipeline/ and reloads the bundle, so the node the fake remote's pipeline added is
    # reached by the very task that found it; the custom actions and recognitions registered before the reload still answer.
    base, _ = update_scene(tmp_path)
    run = subprocess.run([sys.executable, __file__, "update", str(tmp_path)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    first, second = out["nodes"]
    assert first[:3] == ["MirrorDungeon", "ReloadProbe", "MirrorHub"] and first[-1] == "TaskDone"
    assert second[:3] == ["MirrorDungeon", "ReloadProbe", "MirrorHub"]
    assert [s["probe"] for s in out["seen"]] == [1, 2]
    assert (base / "image" / "probe.png").read_bytes() == b"a template the install lacks"


def update_install(monkeypatch, tmp_path, remote_files, **fields):
    """An install of one data file and a fake remote publishing remote_files; TaskStart logs into the list returned."""
    base, remote = tmp_path / "resource" / "base", tmp_path / "remote"
    install(base, {"data/a.json": b"old"}, "2026.11.01", [str(remote)])
    publish(remote, remote_files, "2026.11.16", **fields)
    patch_all(monkeypatch, "data_dir", lambda: base / "data")
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    return base, remote, logged


def test_a_task_starts_on_the_files_it_had_when_the_update_fails(context, monkeypatch, tmp_path):
    # #771: a wrong sha256, a cut download, a source that is gone: the task runs, the files stay
    base, remote, logged = update_install(monkeypatch, tmp_path, {"data/a.json": b"new"})
    before = tree(base)
    (remote / "2026.11.16" / "data" / "a.json").write_bytes(b"NEW")  # not what the manifest says
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert tree(base) == before and any("sha256" in line and "kept the current files" in line for line in logged)
    logged.clear()
    (remote / "2026.11.16" / "data" / "a.json").write_bytes(b"ne")  # cut off
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert tree(base) == before and any("interrupted" in line for line in logged)
    logged.clear()
    shutil.rmtree(remote)
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True  # the source is gone
    assert tree(base) == before and any("kept the current files" in line for line in logged)


def test_a_task_starts_on_the_files_it_had_when_the_format_is_not_the_one_the_program_knows(context, monkeypatch, tmp_path):
    base, remote, logged = update_install(monkeypatch, tmp_path, {"data/a.json": b"new"}, format=brp.rp.FORMAT + 1)
    before = tree(base)
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert tree(base) == before and any(f"format {brp.rp.FORMAT + 1}" in line and "skipped" in line for line in logged)


def test_a_task_starts_after_its_update_and_names_the_package_it_runs_on(context, monkeypatch, tmp_path):
    base, remote, logged = update_install(monkeypatch, tmp_path, {"data/a.json": b"new"})
    assert actions.TaskStart().run(context, SimpleNamespace(node_name="MirrorDungeon")) is True
    assert (base / "data" / "a.json").read_bytes() == b"new"
    update = next(i for i, line in enumerate(logged) if "2026.11.01 -> 2026.11.16" in line)
    assert "resource package: version 2026.11.16" in logged[update + 1]  # the update, then the package it made


if __name__ == "__main__":
    child(Path(sys.argv[2]) if sys.argv[1:2] == ["update"] else None)
