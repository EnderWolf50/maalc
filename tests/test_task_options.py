"""A task's options (#777, #779, #781, agent/task_options.py): its entry action (TaskStart, LuxStart, ChargeStart) reads them
once, before any tap, from the attach a client's override array leaves on the entry node and on GlobalOptions, and
every reader takes them from there. A value missing or wrong, or a rule that crosses them with the teams, ends the task
at its start: MirrorDungeon fails, a daily task takes the stop procedure.

Every override here is the one tools/client_override.py builds from assets/interface.json, as MXU does (client_options),
its ExpTeam and ThreadTeam from the team options file the settings GUI writes (tests/team_options.json, #780).
In process on test_actions' fake Maa context, then the real tasks on MaaFramework in a child process (daily_child.py):
this file run as a script, as test_task_chain.py does.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from client_options import GLOBAL_DEFAULTS, TEAM_OPTIONS, TEAM_PICK, override, send
from daily_child import bind, game_class, load, result, run_child, run_task, screen
from test_settings import CASES, V20_NOTE, VALID, apply_edits, v20

LUX_KEYS = {"ExpLuxcavation": "exp", "ThreadLuxcavation": "thread"}
MIRROR_WHERE = "set it in the options of the MirrorDungeon task in the client's task list"
WHERE = "set it in the options of the {} task in the client's task list"
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
LUX_WHERE = "the options of the {task} task in the client's task list"
# A Luxcavation task's team option (#780) with no team picked: 「未選擇」, or a list with no team in it.
NO_PICK = ("{option} (team): no team picked; pick one in " + LUX_WHERE
           + " (an empty list: create the team in the settings GUI, save, then reopen the client)")

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


def start(context, monkeypatch, task, *options, drop=(), teams=TEAM_OPTIONS):
    """task's entry action, posted by a client with these options (drop: attach keys it did not send; teams: the team
    options file it found, None for none), on the settings file under ROOT, as at launch (no task before it): what it
    returned, the stop procedure's reasons (the procedure itself left out), and the log."""
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # TaskStart starts afresh: TASK and STUCK come back after
    patch_all(monkeypatch, "STUCK", dict(actions.STUCK))
    stops = []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
    send(context, task, *options, drop=drop, teams=teams)
    actions.LOG.clear()
    if task in LUX_KEYS:
        ok = lux_actions.LuxStart().run(context, SimpleNamespace(node_name=task, custom_action_param=json.dumps(LUX_KEYS[task])))
    elif task == "ChargeEnkephalin":
        ok = daily_actions.ChargeStart().run(context, SimpleNamespace(node_name=task, custom_action_param=None))
    else:
        ok = actions.TaskStart().run(context, SimpleNamespace(node_name=task))
    return ok, stops, [line.split(" ", 1)[1] for line in actions.LOG]


def options_line(said):
    """The options line among what a task's start logged (the resource update's and the package's lines come first)."""
    lines = [line for line in said if line.startswith("options: ")]
    assert len(lines) == 1, said
    return lines[0]


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
    assert options_line(said) == NOT_DEFAULT_LINE and "hook.invalid" not in "\n".join(said)  # the webhook only set or not
    context.tasker.controller.post_click.assert_not_called()


def test_a_version_20_files_run_section_is_not_read_and_each_start_says_so(context, monkeypatch):
    # #779: the client's options are the only source; #782: a file the GUI has not written back as version 21 still has
    # run (every key off the client's default here), which the migration drops, and the start logs where it went.
    write(apply_edits(v20([{"set": "run/difficulty", "value": "normal"}, {"set": "run/target_floor", "value": 10},
                           {"set": "run/runs", "value": None}, {"set": "run/wipe_retries", "value": 9},
                           {"set": "run/webhook_url", "value": "http://file.invalid/"},
                           {"set": "run/auto_download", "value": False}]), HARD_FROM_1))
    ok, _, said = start(context, monkeypatch, "MirrorDungeon")
    opts = actions.TASK["options"]
    assert ok is True and (opts["difficulty"], opts["target_floor"], opts["runs"], opts["wipe_retries"]) == ("auto", 5, 1, 2)
    assert (opts["webhook_url"], actions.allowed("auto_download")) == ("", True)
    assert said.count(V20_NOTE) == 1
    assert start(context, monkeypatch, "MirrorDungeon")[2].count(V20_NOTE) == 1  # the next start says it again


def test_a_version_20_file_says_so_also_when_the_client_sent_an_option_wrong(context, monkeypatch):
    # The line is what explains an option the client has at its default: it comes before the options are read.
    write(v20())
    ok, _, said = start(context, monkeypatch, "MirrorDungeon", drop=("wipe_retries",))
    assert ok is False and V20_NOTE in said


def test_a_version_21_file_says_nothing_of_it(context, monkeypatch):
    write(VALID)
    assert not [line for line in start(context, monkeypatch, "ClaimMail")[2] if "settings version" in line]


def test_runs_limit_off_is_no_limit(context, monkeypatch):
    write(VALID)
    assert start(context, monkeypatch, "MirrorDungeon", "MirrorRunsLimit=No", "MirrorRuns=5")[0] is True
    assert actions.TASK["options"]["runs"] is None  # settlement.runs_done: no cap; MirrorRuns, not sent, is not read


@pytest.mark.parametrize("task, options, read, line", [
    # #781: daily mode sends no count (the client sends a nested input only under its case), count mode does; #780: a
    # Luxcavation task's team is its option too, on the options line
    ("ExpLuxcavation", ("ExpTeam=a",), {"mode": "daily", "retries": 0, "consecutive": True, "team": "a"},
     "mode=daily, retries=0, consecutive=true, team=a"),
    ("ThreadLuxcavation", ("ThreadMode=count", "ThreadCount=5", "ThreadRetries=2", "ThreadConsecutive=No", "ThreadTeam=b"),
     {"mode": "count", "count": 5, "retries": 2, "consecutive": False, "team": "b"},
     "mode=count, count=5, retries=2, consecutive=false, team=b"),
    ("ChargeEnkephalin", ("ChargeCount=10",), {"count": 10}, "count=10"),
])
def test_a_daily_task_reads_its_own_options_the_client_sent(context, monkeypatch, task, options, read, line):
    write(VALID)
    ok, stops, said = start(context, monkeypatch, task, *options)
    own = {k: v for k, v in actions.TASK["options"].items() if k not in task_options.GLOBAL}
    assert ok is True and stops == [] and own == read
    assert options_line(said) == f"options: {GLOBAL_DEFAULTS}, {line}"


def test_a_version_20_files_daily_sections_are_not_read(context, monkeypatch):
    # #781, #780: the client's options are the only source; a version 20 file's luxcavation and charge_enkephalin, every
    # key off the client's default here (team a, the client's b), go in the migration (#782).
    edits = [{"set": f"luxcavation/{key}/{k}", "value": v} for key in ("exp", "thread")
             for k, v in (("mode", "count"), ("count", 7), ("retries", 5), ("consecutive", False), ("team", "a"))]
    write(v20([*edits, {"set": "charge_enkephalin/count", "value": 9}]))
    assert start(context, monkeypatch, "ExpLuxcavation", "ExpTeam=b")[0] is True
    assert {k: actions.TASK["options"][k] for k in ("mode", "retries", "consecutive", "team")} == {
        "mode": "daily", "retries": 0, "consecutive": True, "team": "b"}
    assert "count" not in actions.TASK["options"]
    ok, _, said = start(context, monkeypatch, "ChargeEnkephalin")
    assert ok is True and actions.TASK["options"]["count"] == 0 and said[-1] == "done: ChargeCount is 0: Lunacy left alone"


def test_a_task_with_no_options_of_its_own_reads_the_global_ones(context, monkeypatch):
    write(VALID)
    ok, _, said = start(context, monkeypatch, "ClaimMail", "AutoAcceptTerms=No", "WebhookUrl=http://hook.invalid/")
    assert ok is True and actions.TASK["options"] == {"webhook_url": "http://hook.invalid/", "auto_accept_terms": False,
                                                       "auto_download": True, "keep_dismissed_screens": True}
    assert options_line(said) == ("options: webhook_url (set), auto_accept_terms=false, auto_download=true, "
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
    # #781: a daily task's own; count mode with no count, a typo that MXU sends as nothing, past the game's 10 a day
    ("ExpLuxcavation", ("ExpMode=count",), ("count",), f"ExpCount (count): not sent; {WHERE.format('ExpLuxcavation')}"),
    ("ThreadLuxcavation", ("ThreadRetries=x",), (), f"ThreadRetries (retries): not sent; {WHERE.format('ThreadLuxcavation')}"),
    ("ExpLuxcavation", (), ("consecutive",), f"ExpConsecutive (consecutive): not sent; {WHERE.format('ExpLuxcavation')}"),
    ("ChargeEnkephalin", ("ChargeCount=11",), (),
     f"ChargeCount (count): 11 is greater than the maximum of 10; {WHERE.format('ChargeEnkephalin')}"),
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
    # task's start; #779: the target floor and the difficulty come from the client; #780: the team too.
    write(apply_edits(CASES["valid"], case["edits"]))
    ok, stops, said = start(context, monkeypatch, case["task"], *case.get("options", []))
    if not case["cross"]:
        assert ok is True and stops == [] and not [line for line in said if line.startswith("stop:")]
    elif case["task"] == "MirrorDungeon":  # a failure, as PlanRun's on bad settings: no stop procedure
        assert ok is False and stops == [] and said[-1] == f"stop: {invalid(case['cross'])}"
    else:  # a Luxcavation task: the stop procedure, as for any option it cannot run on
        assert ok is False and stops == [invalid(case["cross"])]
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
    # Each task checks its own: no EXP team picked stops neither the mail nor the Thread task, which picked its own.
    # Before #777 the settings' load refused a gone EXP team, which stopped every task that loaded the file at its start
    # (Thread) and left the mail on the defaults.
    write(VALID)
    assert start(context, monkeypatch, "ClaimMail")[:2] == (True, [])
    assert start(context, monkeypatch, "ThreadLuxcavation", "ThreadTeam=a")[:2] == (True, [])


@pytest.mark.parametrize("task, option, name", [("ExpLuxcavation", "ExpTeam", "EXP Luxcavation"),
                                                ("ThreadLuxcavation", "ThreadTeam", "Thread Luxcavation")])
def test_a_luxcavation_task_plays_the_team_its_option_picked(context, monkeypatch, task, option, name):
    # #780: the team is the client's dropdown, its case the team's id: team b's TEAMS #2 and guard turns, not team a's;
    # a version 20 file's luxcavation team (a) is not read.
    write(v20([{"set": f"luxcavation/{LUX_KEYS[task]}/team", "value": "a"}]))
    ok, stops, said = start(context, monkeypatch, task, f"{option}=b")
    assert ok is True and stops == []
    assert actions.TASK["options"]["team"] == "b" and options_line(said).endswith(", team=b")
    assert (actions.RUN["team"]["id"], actions.RUN["team"]["game_team"], actions.RUN["guard"]) == ("b", 2, 3)
    assert said[-1].startswith(f"{name}: team 'Team b' (TEAMS #2), 3 guard turns, ")
    context.tasker.controller.post_click.assert_not_called()


@pytest.mark.parametrize("task, option", TEAM_PICK.items())
def test_a_client_that_found_no_team_options_file_sends_no_team_and_the_task_stops(context, monkeypatch, task, option):
    # #780: the placeholder's dropdown is empty (no team in the settings GUI yet, or the client not reopened since): the
    # stop procedure before any tap, the line saying how to fill the list.
    write(VALID)
    ok, stops, _ = start(context, monkeypatch, task, teams=None)
    assert ok is False and stops == [invalid([NO_PICK.format(option=option, task=task)])]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()


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
                                           ("ThreadLuxcavation", True), ("ChargeEnkephalin", False)])
def test_a_task_whose_settings_do_not_load_at_its_start_goes_on_or_stops_as_before(context, monkeypatch, task, stopped):
    # No settings file: MirrorDungeon goes on to PlanRun, which fails it and says why (test_settings.py); a task with no
    # options in the settings goes on with the client's, ChargeEnkephalin too since its count is the client's (#781); a
    # Luxcavation task, whose team the file holds, stops before any tap.
    ok, stops, said = start(context, monkeypatch, task, "AutoDownload=No")
    unread = f"Invalid settings:\n- {actions.ROOT / 'config' / 'settings.json'} not found. {NO_TEAM}"
    assert ok is not stopped
    assert stops == ([unread] if stopped else [])
    if task == "ChargeEnkephalin":  # a task that spends Lunacy says so when it goes on without the file
        assert f"settings not read, ChargeEnkephalin needs none of them: {unread}" in said
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
    # #780: the EXP task's team, picked; deleted in the settings GUI since; 「未選擇」; a client with no team options file
    "exp_team_picked": ("ExpLuxcavation", ("ExpTeam=b",), (), []),
    "exp_team_gone": ("ExpLuxcavation", ("ExpTeam=gone",), (), []),
    "exp_team_none": ("ExpLuxcavation", ("ExpTeam=none",), (), []),
    "exp_team_unsent": ("ExpLuxcavation", (), (), []),
    # GoHome's sub-task meets the game's download dialog (TitleDownload.png): with the client's AutoDownload off
    "download_off": ("ClaimMail", ("AutoDownload=No",), (), []),
}


NO_TEAM_FILE = {"exp_team_unsent"}  # the scenarios a client posts that found no team options file
READ_BACK = {"values": "MirrorHub", "exp_team_picked": "ExpLuxcavation"}  # whose next is ReadBack, which ends the task


def sent_without(task, options, drop, teams=TEAM_OPTIONS):
    """The override a client posts task with, without the entries that write a key of drop."""
    return [o for o in override(task, *options, teams=teams)
            if not any(k in node.get("attach", {}) for node in o.values() for k in drop)]


def child():
    from maa.custom_action import CustomAction

    actions, resource = load()

    class Still(game_class()):
        images = {"main": screen("MainWindow.png"), "download": screen("TitleDownload.png")}

    class ReadBack(CustomAction):
        """The next of a READ_BACK node: what a node after the entry reads, the task's options, the entry's attach, and
        the team and guard turns a Luxcavation task's start set."""

        def run(self, context, argv):
            team = actions.RUN.get("team") or {}
            read_back.update(options=actions.TASK.get("options"),
                             attach=(context.get_node_data(actions.TASK["entry"]) or {}).get("attach"),
                             team=[team.get("id"), team.get("game_team"), actions.RUN.get("guard")])
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
        array = sent_without(task, options, drop, None if name in NO_TEAM_FILE else TEAM_OPTIONS)
        if name in READ_BACK:
            array.append({READ_BACK[name]: {"next": ["ReadBack"]}, "ReadBack": {"action": "Custom", "custom_action": "ReadBack"}})
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


def test_the_real_exp_luxcavation_plays_the_team_the_client_picked():
    # #780: the dropdown's case for team b sends its id: its TEAMS #2 and 3 guard turns, not team a's #1 and 0
    o = run_child(__file__)["exp_team_picked"]
    assert o["succeeded"] and o["nodes"] == ["ExpLuxcavation", "ReadBack"] and (o["clicks"], o["keys"]) == ([], []), o
    assert o["read_back"]["attach"]["team"] == "b" and o["read_back"]["options"]["team"] == "b"
    assert o["read_back"]["team"] == ["b", 2, 3]
    assert "EXP Luxcavation: team 'Team b' (TEAMS #2), 3 guard turns, mode daily, 0 retries, consecutive on" in o["said"], o["said"]


@pytest.mark.parametrize("name, error", [
    ("exp_team_gone", "ExpTeam (team): team 'gone' was deleted in the settings GUI; pick another in "
                      + LUX_WHERE.format(task="ExpLuxcavation")),
    ("exp_team_none", NO_PICK.format(option="ExpTeam", task="ExpLuxcavation")),
    ("exp_team_unsent", NO_PICK.format(option="ExpTeam", task="ExpLuxcavation")),
])
def test_the_real_exp_luxcavation_ends_at_its_entry_node_on_a_team_it_cannot_play(name, error):
    # #780: a deleted team keeps its case, which still sends its id; 「未選擇」 and an empty list send nothing. The stop
    # procedure (its evidence) before any tap.
    o = run_child(__file__)[name]
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, ["ExpLuxcavation"], [], []), o
    assert o["stops"] == [f"stop: {invalid([error])}"], o
    assert o["evidence"] == 1


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
