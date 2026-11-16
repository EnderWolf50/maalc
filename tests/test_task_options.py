"""A task's options (#777, #779, agent/task_options.py): its entry action (TaskStart, LuxStart, ChargeStart) reads them
once, before any tap, from the attach a client's override array leaves on the entry node and on GlobalOptions, and
every reader takes them from there. A value missing or wrong, or a rule that crosses them with the teams, ends the task
at its start: MirrorDungeon fails, a daily task takes the stop procedure.

Every override here is the one tools/client_override.py builds from assets/interface.json, as MXU does (client_options).
In process on test_actions' fake Maa context, then the real tasks on MaaFramework in a child process (daily_child.py):
this file run as a script, as test_task_chain.py does.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from client_options import override, send
from daily_child import bind, game_class, load, result, run_child, run_task, screen
from test_settings import VALID, apply_edits

CASES = json.loads((Path(__file__).parent / "settings_cases.json").read_text(encoding="utf-8"))
LUX_KEYS = {"ExpLuxcavation": "exp", "ThreadLuxcavation": "thread"}
MIRROR_WHERE = "set it in the options of the MirrorDungeon task in the client's task list"
GLOBAL_WHERE = "set it in the client's global options (MXU: Settings; MFAAvalonia: the global options item of the task list)"
# Every option of MirrorDungeon and every global one off its default (target 15 needs every team HARD from floor 1),
# and what the task reads from them.
NOT_DEFAULT = ("MirrorDifficulty=hard", "MirrorTargetFloor=15", "MirrorRunsLimit=Yes", "MirrorRuns=3",
               "MirrorThemePackRefresh=once", "MirrorWeeklyBonusUse=none", "MirrorWeeklyBonusAmount=one",
               "MirrorStopWhenBonusOut=Yes", "MirrorStarlightUnaffordable=stop", "MirrorWipeRetries=0",
               "MirrorAfterRetries=stop", "WebhookUrl=http://hook.invalid/x", "AutoAcceptTerms=No", "AutoDownload=No",
               "KeepDismissedScreens=No")
NOT_DEFAULT_READ = {"webhook_url": "http://hook.invalid/x", "auto_accept_terms": False, "auto_download": False,
                    "keep_dismissed_screens": False, "difficulty": "hard", "target_floor": 15, "runs": 3,
                    "theme_pack_refresh": "once", "weekly_bonus_use": "none", "weekly_bonus_amount": "one",
                    "stop_when_weekly_bonus_out": True, "starlight_unaffordable": "stop", "wipe_retries": 0,
                    "after_retries": "stop"}
NOT_DEFAULT_LINE = ("options: webhook_url (set), auto_accept_terms=false, auto_download=false, keep_dismissed_screens=false, "
                    "difficulty=hard, target_floor=15, runs_limited=true, runs=3, theme_pack_refresh=once, "
                    "weekly_bonus_use=none, weekly_bonus_amount=one, stop_when_weekly_bonus_out=true, "
                    "starlight_unaffordable=stop, wipe_retries=0, after_retries=stop")
HARD_FROM_1 = [{"set": "teams/1/hard_from_floor", "value": 1}]  # the valid file's team b starts HARD at floor 3

if __name__ != "__main__":  # pytest; the child imports the agent itself, under a stand-in AgentServer (daily_child.load)
    import actions
    import daily_actions
    import lux_actions
    import run_start_actions
    import task_options
    import test_actions
    from agent_patch import patch_all
    from settings import NO_TEAM
    from test_task_chain import entry_page

    clock, context = test_actions.clock, test_actions.context  # its fixtures: the fake Maa context


def write(data):
    """data as settings.json under the agent's ROOT."""
    (actions.ROOT / "config").mkdir(exist_ok=True)
    (actions.ROOT / "config" / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def start(context, monkeypatch, task, *options, drop=()):
    """task's entry action, posted by a client with these options (drop: attach keys it did not send), on the settings
    file under ROOT, as at launch (no task before it): what it returned, the stop procedure's reasons (the procedure
    itself left out), and the log."""
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # TaskStart starts afresh: TASK and STUCK come back after
    patch_all(monkeypatch, "STUCK", dict(actions.STUCK))
    stops = []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    send(context, task, *options, drop=drop)
    actions.LOG.clear()
    if task in LUX_KEYS:
        ok = lux_actions.LuxStart().run(context, SimpleNamespace(node_name=task, custom_action_param=json.dumps(LUX_KEYS[task])))
    elif task == "ChargeEnkephalin":
        ok = daily_actions.ChargeStart().run(context, SimpleNamespace(node_name=task, custom_action_param=None))
    else:
        ok = actions.TaskStart().run(context, SimpleNamespace(node_name=task))
    return ok, stops, [line.split(" ", 1)[1] for line in actions.LOG]


def test_the_options_line_names_no_webhook():
    # #779: the webhook's address stays out of the log, as the client keeps a password input out of its own
    line = task_options.line({"webhook_url": "http://secret.invalid/", "auto_download": True})
    assert line == "options: webhook_url (set), auto_download=true" and "secret" not in line
    assert task_options.line({"webhook_url": ""}) == "options: webhook_url (not set)"


def test_the_agent_reads_its_schema_from_its_own_folder():
    # install.py copies agent/ whole (its json files with it): the schema ships beside task_options.py
    assert (Path(task_options.__file__).parent / "task_options.schema.json").is_file()


def invalid(errors, what="task options"):
    """The words of an OptionsError (a SettingsError: what "settings") of errors."""
    return f"Invalid {what}:\n- " + "\n- ".join(errors)


def test_mirror_dungeon_reads_every_option_the_client_sent_and_logs_them(context, monkeypatch):
    write(apply_edits(VALID, HARD_FROM_1))
    ok, stops, said = start(context, monkeypatch, "MirrorDungeon", *NOT_DEFAULT)
    assert ok is True and stops == []
    assert actions.TASK["options"] == NOT_DEFAULT_READ
    assert said[1] == NOT_DEFAULT_LINE and "hook.invalid" not in "\n".join(said)  # the webhook only set or not
    context.tasker.controller.post_click.assert_not_called()


def test_the_settings_files_run_section_is_not_read(context, monkeypatch):
    # #779: the client's options are the only source; the file's run (every key off the client's default here) is left
    # as it is, for the GUI to write back (#782 drops it).
    data = copy.deepcopy(VALID)
    data["run"].update(difficulty="normal", target_floor=10, runs=None, wipe_retries=9, webhook_url="http://file.invalid/",
                       auto_download=False)
    data["teams"][1]["hard_from_floor"] = 1
    write(data)
    ok, _, _ = start(context, monkeypatch, "MirrorDungeon")
    opts = actions.TASK["options"]
    assert ok is True and (opts["difficulty"], opts["target_floor"], opts["runs"], opts["wipe_retries"]) == ("auto", 5, 1, 2)
    assert (opts["webhook_url"], actions.allowed("auto_download")) == ("", True)


def test_runs_limit_off_is_no_limit(context, monkeypatch):
    write(VALID)
    assert start(context, monkeypatch, "MirrorDungeon", "MirrorRunsLimit=No", "MirrorRuns=5")[0] is True
    assert actions.TASK["options"]["runs"] is None  # settlement.runs_done: no cap; MirrorRuns, not sent, is not read


def test_a_task_with_no_options_of_its_own_reads_the_global_ones(context, monkeypatch):
    write(VALID)
    ok, _, said = start(context, monkeypatch, "ClaimMail", "AutoAcceptTerms=No", "WebhookUrl=http://hook.invalid/")
    assert ok is True and actions.TASK["options"] == {"webhook_url": "http://hook.invalid/", "auto_accept_terms": False,
                                                       "auto_download": True, "keep_dismissed_screens": True}
    assert said[1] == ("options: webhook_url (set), auto_accept_terms=false, auto_download=true, "
                       "keep_dismissed_screens=true")


@pytest.mark.parametrize("task, options, drop, error", [
    ("MirrorDungeon", (), ("wipe_retries",), f"MirrorWipeRetries (wipe_retries): not sent; {MIRROR_WHERE}"),
    ("MirrorDungeon", ("MirrorRuns=0",), (), f"MirrorRuns (runs): 0 is less than the minimum of 1; {MIRROR_WHERE}"),
    # MXU sends an int input it cannot parse as nothing (client_override), so a typo is a value not sent
    ("MirrorDungeon", ("MirrorWipeRetries=x",), (), f"MirrorWipeRetries (wipe_retries): not sent; {MIRROR_WHERE}"),
    ("MirrorDungeon", (), ("runs",), f"MirrorRuns (runs): not sent; {MIRROR_WHERE}"),  # limited, no count
    ("MirrorDungeon", (), ("auto_download",), f"AutoDownload (auto_download): not sent; {GLOBAL_WHERE}"),
    ("ClaimMail", (), ("webhook_url",), f"WebhookUrl (webhook_url): not sent; {GLOBAL_WHERE}"),
    ("ExpLuxcavation", (), ("keep_dismissed_screens",), f"KeepDismissedScreens (keep_dismissed_screens): not sent; {GLOBAL_WHERE}"),
    ("ChargeEnkephalin", (), ("auto_accept_terms",), f"AutoAcceptTerms (auto_accept_terms): not sent; {GLOBAL_WHERE}"),
])
def test_an_option_not_sent_or_wrong_ends_the_task_at_its_start_naming_it(context, monkeypatch, task, options, drop, error):
    # #779: no fallback to the settings file or a default. MirrorDungeon fails, as on settings it cannot run on; a daily
    # task takes the stop procedure. Either way before any tap, GoHome included.
    write(VALID)
    ok, stops, said = start(context, monkeypatch, task, *options, drop=drop)
    assert ok is False and "options" not in actions.TASK
    if task == "MirrorDungeon":
        assert stops == [] and said[-1] == f"stop: {invalid([error])}"
    else:
        assert stops == [invalid([error])]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()


def test_a_value_of_the_wrong_type_is_named_with_what_came(context, monkeypatch):
    # An attach written by hand (or a client that sends a string for an int): the type is checked, not trusted.
    write(VALID)
    send(context, "MirrorDungeon")
    nodes = {"MirrorDungeon": context.get_node_data("MirrorDungeon")["attach"], "GlobalOptions": context.get_node_data("GlobalOptions")["attach"]}
    nodes["MirrorDungeon"].update(difficulty="extreme", wipe_retries="2")
    nodes["GlobalOptions"]["auto_download"] = "yes"
    context.get_node_data.side_effect = lambda name: {"attach": nodes[name]}
    with pytest.raises(task_options.OptionsError) as e:
        task_options.read(context, "MirrorDungeon")
    assert e.value.errors == [
        f"AutoDownload (auto_download): 'yes' is not of type 'boolean'; {GLOBAL_WHERE}",
        f"MirrorDifficulty (difficulty): 'extreme' is not one of ['auto', 'hard', 'normal']; {MIRROR_WHERE}",
        f"MirrorWipeRetries (wipe_retries): '2' is not of type 'integer'; {MIRROR_WHERE}",
    ]


@pytest.mark.parametrize("case", CASES["task_start"], ids=lambda c: c["name"])
def test_a_rule_that_crosses_a_tasks_options_with_the_teams_stops_it_at_its_start(context, monkeypatch, case):
    # #777: the target floor's rule (#385) and a Luxcavation task's team (#366) moved from the settings' load to the
    # task's start; #779: the target floor and the difficulty come from the client.
    write(apply_edits(CASES["valid"], case["edits"]))
    ok, stops, said = start(context, monkeypatch, case["task"], *case.get("options", []))
    if not case["cross"]:
        assert ok is True and stops == [] and not [line for line in said if line.startswith("stop:")]
    elif case["task"] == "MirrorDungeon":  # a failure, as PlanRun's on bad settings: no stop procedure
        assert ok is False and stops == [] and said[-1] == f"stop: {invalid(case['cross'])}"
    else:  # a Luxcavation task: the stop procedure, as for any settings it cannot run on
        assert ok is False and stops == [invalid(case["cross"], "settings")]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()  # not even GoHome


@pytest.mark.parametrize("target", [10, 15])
def test_a_disabled_team_does_not_hide_a_normal_only_team_behind_it_from_a_target_past_floor_5(context, monkeypatch, target):
    # #640 (once in settings.py): the check passed over a disabled team with `break`, so teams after it went unchecked.
    data = copy.deepcopy(VALID)
    data["teams"][0]["enabled"] = False
    data["teams"][1]["usage"] = "normal_only"
    write(data)
    ok, _, said = start(context, monkeypatch, "MirrorDungeon", f"MirrorTargetFloor={target}")
    got = said[-1].removeprefix("stop: Invalid task options:\n- ").split("\n- ")
    assert ok is False and [e for e in got if "teams/1/usage" in e and "normal_only" in e], got
    assert not [e for e in got if "teams/0/" in e]  # the disabled team itself is not asked


def test_a_rule_a_task_does_not_play_by_leaves_it_alone(context, monkeypatch):
    # Each task checks its own: a gone EXP team stops neither the mail nor the Thread task. Before #777 the settings'
    # load refused the file, which stopped every task that loaded it at its start (Thread) and left the mail on the defaults.
    write(apply_edits(CASES["valid"], [{"set": "luxcavation/exp/team", "value": "gone"}, {"set": "luxcavation/thread/team", "value": "a"}]))
    assert start(context, monkeypatch, "ClaimMail")[:2] == (True, [])
    assert start(context, monkeypatch, "ThreadLuxcavation")[:2] == (True, [])


def test_a_settings_file_saved_mid_task_changes_nothing_the_task_reads(context, monkeypatch):
    # #777: the task reads at its start once: the teams PlanRun reads afresh, the options not.
    entry_page(context, "MirrorRunsLimit=Yes", "MirrorRuns=1", "AutoDownload=No")  # MirrorDungeon starts on them
    send(context, "MirrorDungeon", "MirrorRuns=5", "AutoDownload=Yes", "WebhookUrl=")  # what a later task would get
    actions.TASK.update(runs=1, done=None)
    assert run_start_actions.PlanRun().run(context, None) is True and actions.TASK["done"] == "1 of 1 runs done"
    assert actions.allowed("auto_download") is False
    urlopen = MagicMock()
    monkeypatch.setattr(actions.urllib.request, "urlopen", urlopen)
    actions.stop(context, "recovery used up")
    assert urlopen.call_args.args[0].full_url == "http://hook.invalid/"  # entry_page's, which the start read


@pytest.mark.parametrize("task, stopped", [("MirrorDungeon", False), ("ClaimMail", False), ("ExpLuxcavation", True),
                                           ("ThreadLuxcavation", True), ("ChargeEnkephalin", True)])
def test_a_task_whose_settings_do_not_load_at_its_start_goes_on_or_stops_as_before(context, monkeypatch, task, stopped):
    # No settings file: MirrorDungeon goes on to PlanRun, which fails it and says why (test_settings.py); a task with no
    # options in the settings goes on with the client's; a Luxcavation task and ChargeEnkephalin stop, before any tap.
    ok, stops, _ = start(context, monkeypatch, task, "AutoDownload=No")
    assert ok is not stopped
    assert stops == ([f"Invalid settings:\n- {actions.ROOT / 'config' / 'settings.json'} not found. {NO_TEAM}"]
                     if stopped else [])
    context.tasker.controller.post_click.assert_not_called()
    assert actions.allowed("auto_download") is False  # the client's, the stop procedure's webhook too


def test_plan_run_checks_the_target_floor_against_the_teams_a_save_since_the_start_changed(context, monkeypatch):
    # The teams are not the task's options: PlanRun reads them afresh for each run, so it checks the start's target
    # floor against them again, as the settings' load did before #777. Team b starts HARD at floor 3 since the save.
    entry_page(context, "MirrorTargetFloor=15", teams=lambda teams: teams[1].update(hard_from_floor=1))
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["teams"][1]["hard_from_floor"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    assert run_start_actions.PlanRun().run(context, None) is False
    assert logged == ["stop: " + invalid(["teams/1/hard_from_floor: team 'Team b' starts HARD at floor 3, but MirrorTargetFloor 15 "
                                           "needs the whole run HARD (hard_from_floor 1)"])]
    context.tasker.controller.post_click.assert_not_called()


# The real tasks on MaaFramework (#777, #779), each posted with the override a client builds: (task, its options, the
# attach keys left out of the array, the settings file's edits).
SCENARIOS = {
    "values": ("MirrorDungeon", NOT_DEFAULT, (), HARD_FROM_1),
    "missing": ("MirrorDungeon", (), ("wipe_retries",), []),
    "runs_zero": ("MirrorDungeon", ("MirrorRunsLimit=Yes", "MirrorRuns=0"), (), []),
    "target_normal_only": ("MirrorDungeon", ("MirrorTargetFloor=10",), (), [{"set": "teams/0/usage", "value": "normal_only"}, *HARD_FROM_1]),
    "exp_team": ("ExpLuxcavation", (), (), [{"set": "luxcavation/exp/team", "value": "gone"}]),
    # GoHome's sub-task meets the game's download dialog (TitleDownload.png): with the client's AutoDownload off
    "download_off": ("ClaimMail", ("AutoDownload=No",), (), []),
}


def sent_without(task, options, drop):
    """The override a client posts task with, without the entries that write a key of drop."""
    return [o for o in override(task, *options)
            if not any(k in node.get("attach", {}) for node in o.values() for k in drop)]


def child():
    from maa.custom_action import CustomAction

    actions, resource = load()

    class Still(game_class()):
        images = {"main": screen("MainWindow.png"), "download": screen("TitleDownload.png")}

    class ReadBack(CustomAction):
        """MirrorHub's next, for "values": what a node after the entry reads, the task's options and the attach."""

        def run(self, context, argv):
            read_back.update(options=actions.TASK.get("options"),
                             attach=(context.get_node_data("MirrorDungeon") or {}).get("attach"))
            return True

    resource.register_custom_action("ReadBack", ReadBack())
    game = Still()
    tasker = bind(resource, game)
    out, read_back = {"error": None}, {}

    def evidence():
        """How many evidence folders the stop procedure has left."""
        folder = actions.ROOT / "logs" / "evidence"
        return len(list(folder.iterdir())) if folder.exists() else 0

    for name, (task, options, drop, edits) in SCENARIOS.items():
        (actions.ROOT / "config").mkdir(exist_ok=True)
        (actions.ROOT / "config" / "settings.json").write_text(json.dumps(apply_edits(CASES["valid"], edits)), encoding="utf-8")
        game.screen = "download" if name == "download_off" else "main"
        game.clicks, game.keys = [], []
        before = evidence()
        actions.LOG.clear()
        array = sent_without(task, options, drop)
        if name == "values":  # the hub's first pass is ReadBack, which ends the task
            array.append({"MirrorHub": {"next": ["ReadBack"]}, "ReadBack": {"action": "Custom", "custom_action": "ReadBack"}})
        out[name] = {**result(run_task(tasker, name, task, array), game, actions),
                     "stops": [line.split(" ", 1)[1] for line in actions.LOG if " stop: " in line],
                     "said": [line.split(" ", 1)[1] for line in actions.LOG], "evidence": evidence() - before,
                     "halted": actions.STUCK["halted"], "read_back": dict(read_back)}
        actions.STUCK["halted"] = None
        read_back.clear()
    print(json.dumps(out))


def test_the_real_mirror_dungeon_reads_the_values_the_client_sent():
    o = run_child(__file__)["values"]
    assert o["succeeded"] and (o["nodes"][0], o["nodes"][-1]) == ("MirrorDungeon", "ReadBack") and o["clicks"] == [], o
    assert o["read_back"]["options"] == NOT_DEFAULT_READ
    assert o["read_back"]["attach"]["runs"] == 3 and o["read_back"]["attach"]["runs_limited"] is True
    assert NOT_DEFAULT_LINE in o["said"] and not any("hook.invalid" in line for line in o["said"])


@pytest.mark.parametrize("name, error", [
    ("missing", f"MirrorWipeRetries (wipe_retries): not sent; {MIRROR_WHERE}"),
    ("runs_zero", f"MirrorRuns (runs): 0 is less than the minimum of 1; {MIRROR_WHERE}"),
    ("target_normal_only", "teams/0/usage: team 'Team a' is normal_only, but MirrorTargetFloor 10 needs the whole run HARD"),
])
def test_the_real_mirror_dungeon_ends_at_its_entry_node_on_an_option_it_cannot_run_on(name, error):
    # Before MirrorHub, before any tap: a failure (no stop procedure, no evidence), the line saying which option.
    o = run_child(__file__)[name]
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, ["MirrorDungeon"], [], []), o
    assert o["stops"] == [f"stop: {invalid([error])}"] and o["evidence"] == 0, o


def test_a_broken_rule_ends_the_real_luxcavation_task_at_its_entry_node_before_any_tap():
    task, _, _, edits = SCENARIOS["exp_team"]
    case = next(c for c in CASES["task_start"] if c["task"] == task and c["edits"] == edits)
    o = run_child(__file__)["exp_team"]
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, [task], [], [])
    assert o["stops"] == [f"stop: {invalid(case['cross'], 'settings')}"]
    assert o["evidence"] == 1  # the stop procedure


def test_the_global_options_reach_go_home_run_as_a_sub_task():
    # #779: ClaimMail's GoHome (context.run_task from MailHome) meets the download dialog: AutoDownload off, as the
    # client sent it, stops the task and the rest of the list there (the stop procedure, post_stop), with no tap. On,
    # the default, presses Confirm (test_title_dialogs.py).
    o = run_child(__file__)["download_off"]
    assert o["nodes"] == ["ClaimMail", "MailHome"] and (o["clicks"], o["keys"]) == ([], []), o
    assert o["stops"][0] == "stop: the game asks to download data: the global option AutoDownload is off", o
    assert o["halted"] and o["evidence"] == 1, o


if __name__ == "__main__":
    child()
