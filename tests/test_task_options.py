"""A task's options (#777, #813, agent/task_options.py): its entry action (TaskStart, LuxStart, ChargeStart) reads them
once, before any tap, from the settings file (run, luxcavation.<task>, charge_enkephalin), logs them on its options
line, and every reader takes them from there. A rule that crosses them with the teams ends the task at its start:
MirrorDungeon fails on a target floor its teams cannot play, a start team or a Luxcavation team it cannot play takes the
stop procedure.

In process on test_actions' fake Maa context, then the real tasks on MaaFramework in a child process (daily_child.py):
this file run as a script, as test_task_chain.py does.
"""

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from daily_child import GLOBAL_DEFAULTS, bind, game_class, load, result, run_child, run_task, screen
from test_settings import CASES, NOTE, apply_edits, older

VALID = CASES["valid"]  # team a (any, TEAMS #1, no guard turns) then team b (hard_only from floor 3, TEAMS #2, 3 guard turns)
LUX_KEYS = {"ExpLuxcavation": "exp", "ThreadLuxcavation": "thread"}
WHERE = "the options of the {} task in the settings GUI's task list"
HARD_FROM_1 = [{"set": "teams/1/hard_from_floor", "value": 1}]  # the valid file's team b starts HARD at floor 3
# Every option of MirrorDungeon and every global one off its default (target 15 needs every team HARD from floor 1),
# and what the task reads from them, in its options line's order.
NOT_DEFAULT = {"difficulty": "hard", "target_floor": 15, "runs": 3, "weekly_bonus_use": "none", "weekly_bonus_amount": "one",
               "stop_when_weekly_bonus_out": True, "starlight_unaffordable": "stop", "wipe_retries": 0, "after_retries": "stop",
               "webhook_url": "http://hook.invalid/x", "theme_pack_refresh": "once", "auto_accept_terms": False,
               "auto_download": False, "keep_dismissed_screens": False, "start_team": "b"}
NOT_DEFAULT_READ = {"webhook_url": "http://hook.invalid/x", "auto_accept_terms": False, "auto_download": False,
                    "keep_dismissed_screens": False, "difficulty": "hard", "target_floor": 15, "runs": 3,
                    "theme_pack_refresh": "once", "weekly_bonus_use": "none", "weekly_bonus_amount": "one",
                    "stop_when_weekly_bonus_out": True, "starlight_unaffordable": "stop", "wipe_retries": 0,
                    "after_retries": "stop", "start_team": "b"}
NOT_DEFAULT_LINE = ("options: webhook_url (set), auto_accept_terms=false, auto_download=false, keep_dismissed_screens=false, "
                    "difficulty=hard, target_floor=15, runs=3, theme_pack_refresh=once, weekly_bonus_use=none, "
                    "weekly_bonus_amount=one, stop_when_weekly_bonus_out=true, starlight_unaffordable=stop, wipe_retries=0, "
                    "after_retries=stop, start_team=b")
# The options lines of the valid file, whose options are the defaults; each Luxcavation task's with team b picked.
MIRROR_LINE = (f"options: {GLOBAL_DEFAULTS}, difficulty=auto, target_floor=5, runs=1, theme_pack_refresh=all, "
               "weekly_bonus_use=hard, weekly_bonus_amount=all, stop_when_weekly_bonus_out=false, starlight_unaffordable=skip, "
               "wipe_retries=2, after_retries=forfeit, start_team=null")
LUX_LINE = {"ExpLuxcavation": f"options: {GLOBAL_DEFAULTS}, mode=daily, count=1, team=b, retries=0, consecutive=true",
            "ThreadLuxcavation": f"options: {GLOBAL_DEFAULTS}, mode=daily, count=3, team=b, retries=0, consecutive=true"}
LINES = {"MirrorDungeon": MIRROR_LINE, **LUX_LINE, "ChargeEnkephalin": f"options: {GLOBAL_DEFAULTS}, count=0",
         "ClaimMail": f"options: {GLOBAL_DEFAULTS}"}
TEAM_B = [{"set": f"luxcavation/{key}/team", "value": "b"} for key in LUX_KEYS.values()]

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


def start(context, monkeypatch, task):
    """task's entry action on the settings file under ROOT, as at launch (no task before it): what it returned, the stop
    procedure's reasons (the procedure itself left out), and the log."""
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None})  # TaskStart starts afresh: TASK and STUCK come back after
    patch_all(monkeypatch, "STUCK", dict(actions.STUCK))
    stops = []
    patch_all(monkeypatch, "stop", lambda context, reason, **kw: stops.append(reason) or False)
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


def invalid(errors, what="task options"):
    """The words of an OptionsError (a SettingsError: what "settings") of errors."""
    return f"Invalid {what}:\n- " + "\n- ".join(errors)


def test_the_options_line_names_no_webhook():
    # #779: the webhook's address stays out of the log
    line = task_options.line({"webhook_url": "http://secret.invalid/", "auto_download": True})
    assert line == "options: webhook_url (set), auto_download=true" and "secret" not in line
    assert task_options.line({"webhook_url": ""}) == "options: webhook_url (not set)"


def test_mirror_dungeon_reads_every_option_of_the_settings_file_and_logs_them(context, monkeypatch):
    write(apply_edits({**VALID, "run": NOT_DEFAULT}, HARD_FROM_1))
    ok, stops, said = start(context, monkeypatch, "MirrorDungeon")
    assert ok is True and stops == []
    assert actions.TASK["options"] == NOT_DEFAULT_READ and actions.TASK["start_team"] == "b"
    assert options_line(said) == NOT_DEFAULT_LINE and "hook.invalid" not in "\n".join(said)  # the webhook only set or not
    context.tasker.controller.post_click.assert_not_called()


@pytest.mark.parametrize("task, edits, shown", [
    # one value of the file changed: the options line shows it, the rest as before (#813)
    ("MirrorDungeon", [{"set": "run/difficulty", "value": "hard"}], "difficulty=hard"),
    ("MirrorDungeon", [{"set": "run/target_floor", "value": 10}, *HARD_FROM_1], "target_floor=10"),
    ("MirrorDungeon", [{"set": "run/runs", "value": None}], "runs=null"),
    ("MirrorDungeon", [{"set": "run/runs", "value": 7}], "runs=7"),
    ("MirrorDungeon", [{"set": "run/theme_pack_refresh", "value": "none"}], "theme_pack_refresh=none"),
    ("MirrorDungeon", [{"set": "run/weekly_bonus_use", "value": "normal"}], "weekly_bonus_use=normal"),
    ("MirrorDungeon", [{"set": "run/weekly_bonus_amount", "value": "one"}], "weekly_bonus_amount=one"),
    ("MirrorDungeon", [{"set": "run/stop_when_weekly_bonus_out", "value": True}], "stop_when_weekly_bonus_out=true"),
    ("MirrorDungeon", [{"set": "run/starlight_unaffordable", "value": "stop"}], "starlight_unaffordable=stop"),
    ("MirrorDungeon", [{"set": "run/wipe_retries", "value": 5}], "wipe_retries=5"),
    ("MirrorDungeon", [{"set": "run/after_retries", "value": "stop"}], "after_retries=stop"),
    ("MirrorDungeon", [{"set": "run/start_team", "value": "a"}], "start_team=a"),
    ("MirrorDungeon", [{"set": "run/webhook_url", "value": "http://hook.invalid/"}], "webhook_url (set)"),
    ("MirrorDungeon", [{"set": "run/auto_accept_terms", "value": False}], "auto_accept_terms=false"),
    ("MirrorDungeon", [{"set": "run/auto_download", "value": False}], "auto_download=false"),
    ("MirrorDungeon", [{"set": "run/keep_dismissed_screens", "value": False}], "keep_dismissed_screens=false"),
    ("ClaimMail", [{"set": "run/auto_download", "value": False}], "auto_download=false"),
    *[(task, [{"set": f"luxcavation/{key}/{k}", "value": v}], shown) for task, key in LUX_KEYS.items()
      for k, v, shown in (("mode", "count", "mode=count"), ("count", 4, "count=4"), ("team", "a", "team=a"),
                          ("retries", 2, "retries=2"), ("consecutive", False, "consecutive=false"))],
    ("ChargeEnkephalin", [{"set": "charge_enkephalin/count", "value": 3}], "count=3"),
])
def test_each_option_is_the_settings_files_and_its_change_shows_on_the_options_line(context, monkeypatch, task, edits, shown):
    write(apply_edits(VALID, [*TEAM_B, *edits]))
    ok, stops, said = start(context, monkeypatch, task)
    key = shown.split("=")[0].split(" ")[0]
    before = next(part for part in LINES[task].removeprefix("options: ").split(", ") if part.split("=")[0].split(" ")[0] == key)
    assert ok is True and stops == [] and before != shown
    assert options_line(said) == LINES[task].replace(before, shown)


@pytest.mark.parametrize("version", [20, 21, 22])
def test_an_older_file_says_where_the_options_come_from_at_each_start(context, monkeypatch, version):
    # #813: the file on disk stays as it was until the GUI writes it back, and each start says so; a version 20 file
    # keeps its own run (normal here), a later one takes the defaults
    write(older(version, [{"set": "run/difficulty", "value": "normal"}] if version == 20 else []))
    ok, _, said = start(context, monkeypatch, "MirrorDungeon")
    assert ok is True and said.count(NOTE) == 1
    assert actions.TASK["options"]["difficulty"] == ("normal" if version == 20 else "auto")
    assert start(context, monkeypatch, "MirrorDungeon")[2].count(NOTE) == 1  # the next start says it again


def test_an_older_file_says_so_also_when_it_then_fails_a_check(context, monkeypatch):
    # the line is what explains a value at its default: it comes before the check's failure
    write(older(22, [{"set": "teams/1/game_team", "value": 1}]))
    ok, stops, said = start(context, monkeypatch, "ExpLuxcavation")
    assert ok is False and NOTE in said and stops and stops[0].startswith("Invalid settings:")


def test_a_current_file_says_nothing_of_it(context, monkeypatch):
    write(VALID)
    assert not [line for line in start(context, monkeypatch, "ClaimMail")[2] if "settings older" in line]


def test_no_run_cap_is_null(context, monkeypatch):
    write(apply_edits(VALID, [{"set": "run/runs", "value": None}]))
    assert start(context, monkeypatch, "MirrorDungeon")[0] is True
    assert actions.TASK["options"]["runs"] is None  # settlement.runs_done: no cap


@pytest.mark.parametrize("task, edits, read", [
    ("ExpLuxcavation", [{"set": "luxcavation/exp/team", "value": "a"}],
     {"mode": "daily", "count": 1, "team": "a", "retries": 0, "consecutive": True}),
    ("ThreadLuxcavation", [{"set": "luxcavation/thread", "value": {"mode": "count", "count": 5, "team": "b", "retries": 2,
                                                                   "consecutive": False}}],
     {"mode": "count", "count": 5, "team": "b", "retries": 2, "consecutive": False}),
    ("ChargeEnkephalin", [{"set": "charge_enkephalin/count", "value": 10}], {"count": 10}),
])
def test_a_daily_task_reads_its_own_options_from_the_settings_file(context, monkeypatch, task, edits, read):
    write(apply_edits(VALID, edits))
    ok, stops, said = start(context, monkeypatch, task)
    own = {k: v for k, v in actions.TASK["options"].items() if k not in task_options.GLOBAL}
    assert ok is True and stops == [] and own == read
    assert options_line(said) == f"options: {GLOBAL_DEFAULTS}, " + ", ".join(
        f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in read.items())


def test_a_task_with_no_options_of_its_own_reads_the_global_ones(context, monkeypatch):
    write(apply_edits(VALID, [{"set": "run/auto_accept_terms", "value": False},
                              {"set": "run/webhook_url", "value": "http://hook.invalid/"}]))
    ok, _, said = start(context, monkeypatch, "ClaimMail")
    assert ok is True and actions.TASK["options"] == {"webhook_url": "http://hook.invalid/", "auto_accept_terms": False,
                                                       "auto_download": True, "keep_dismissed_screens": True}
    assert options_line(said) == ("options: webhook_url (set), auto_accept_terms=false, auto_download=true, "
                                  "keep_dismissed_screens=true")


@pytest.mark.parametrize("case", CASES["task_start"], ids=lambda c: c["name"])
def test_a_rule_that_crosses_a_tasks_options_with_the_teams_stops_it_at_its_start(context, monkeypatch, case):
    # #777: the target floor's rule (#385), the start team (#805) and a Luxcavation task's team (#366) are the task's start's,
    # not the settings' load, in the words they had since #779 but for the settings path they name (#813).
    write(apply_edits(CASES["valid"], case["edits"]))
    ok, stops, said = start(context, monkeypatch, case["task"])
    target = next((e for e in case["edits"] if e["set"] == "run/target_floor"), None)
    if not case["cross"]:
        assert ok is True and stops == [] and not [line for line in said if line.startswith("stop:")]
    elif case["task"] == "MirrorDungeon" and target:  # the target floor: a failure, as PlanRun's on bad settings
        assert ok is False and stops == [] and said[-1] == f"stop: {invalid(case['cross'])}"
    else:  # the start team, a Luxcavation task's team: the stop procedure, as for any team it cannot play
        assert ok is False and stops == [invalid(case["cross"])]
    context.tasker.controller.post_click.assert_not_called()
    context.run_task.assert_not_called()  # not even GoHome


@pytest.mark.parametrize("target", [10, 15])
def test_a_disabled_team_does_not_hide_a_normal_only_team_behind_it_from_a_target_past_floor_5(context, monkeypatch, target):
    # #640 (once in settings.py): the check passed over a disabled team with `break`, so teams after it went unchecked.
    data = copy.deepcopy(VALID)
    data["teams"][0]["enabled"] = False
    data["teams"][1]["usage"] = "normal_only"
    data["run"]["target_floor"] = target
    write(data)
    ok, _, said = start(context, monkeypatch, "MirrorDungeon")
    got = said[-1].removeprefix("stop: Invalid task options:\n- ").split("\n- ")
    assert ok is False and [e for e in got if "teams/1/usage" in e and "normal_only" in e], got
    assert not [e for e in got if "teams/0/" in e]  # the disabled team itself is not asked


def test_a_rule_a_task_does_not_play_by_leaves_it_alone(context, monkeypatch):
    # Each task checks its own: no EXP team picked stops neither the mail nor the Thread task, which picked its own.
    write(apply_edits(VALID, [{"set": "luxcavation/thread/team", "value": "a"}, {"set": "run/start_team", "value": "gone"}]))
    assert start(context, monkeypatch, "ClaimMail")[:2] == (True, [])
    assert start(context, monkeypatch, "ThreadLuxcavation")[:2] == (True, [])


@pytest.mark.parametrize("task, name", [("ExpLuxcavation", "EXP Luxcavation"), ("ThreadLuxcavation", "Thread Luxcavation")])
def test_a_luxcavation_task_plays_the_team_its_options_name(context, monkeypatch, task, name):
    # team b's TEAMS #2 and guard turns, not team a's
    write(apply_edits(VALID, [{"set": f"luxcavation/{LUX_KEYS[task]}/team", "value": "b"}]))
    ok, stops, said = start(context, monkeypatch, task)
    assert ok is True and stops == []
    assert actions.TASK["options"]["team"] == "b" and ", team=b, " in options_line(said)
    assert (actions.RUN["team"]["id"], actions.RUN["team"]["game_team"], actions.RUN["guard"]) == ("b", 2, 3)
    assert said[-1].startswith(f"{name}: team 'Team b' (TEAMS #2), 3 guard turns, ")
    context.tasker.controller.post_click.assert_not_called()


def test_a_settings_file_saved_mid_task_changes_nothing_the_task_reads(context, monkeypatch):
    # #777: the task reads at its start once: the teams PlanRun reads afresh, the options not.
    entry_page(context, runs=1, auto_download=False)  # MirrorDungeon starts on them
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["run"].update(runs=5, auto_download=True, webhook_url="")  # a save while the task runs
    path.write_text(json.dumps(data), encoding="utf-8")
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
    # options of its own takes the defaults; a Luxcavation task (its team) and ChargeEnkephalin (its count) stop before
    # any tap.
    ok, stops, _ = start(context, monkeypatch, task)
    unread = f"Invalid settings:\n- {actions.ROOT / 'config' / 'settings.json'} not found. {NO_TEAM}"
    assert ok is not stopped and "options" not in actions.TASK
    assert stops == ([unread] if stopped else [])
    context.tasker.controller.post_click.assert_not_called()
    assert actions.allowed("auto_download") is True  # the default, no webhook


def test_plan_run_checks_the_target_floor_against_the_teams_a_save_since_the_start_changed(context, monkeypatch):
    # The teams are not the task's options: PlanRun reads them afresh for each run, so it checks the start's target
    # floor against them again, as the settings' load did before #777. Team b starts HARD at floor 3 since the save.
    entry_page(context, teams=lambda teams: teams[1].update(hard_from_floor=1), target_floor=15)
    path = actions.ROOT / "config" / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["teams"][1]["hard_from_floor"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    logged = []
    patch_all(monkeypatch, "log", logged.append)
    assert run_start_actions.PlanRun().run(context, None) is False
    assert logged == ["stop: " + invalid(["teams/1/hard_from_floor: team 'Team b' starts HARD at floor 3, but run/target_floor 15 "
                                           "needs the whole run HARD (hard_from_floor 1)"])]
    context.tasker.controller.post_click.assert_not_called()


# The real tasks on MaaFramework (#777, #813), each on a settings file: (task, the valid file's edits).
SCENARIOS = {
    "values": ("MirrorDungeon", [{"set": "run", "value": NOT_DEFAULT}, *HARD_FROM_1]),
    "target_normal_only": ("MirrorDungeon", [{"set": "run/target_floor", "value": 10}, {"set": "teams/0/usage", "value": "normal_only"},
                                             *HARD_FROM_1]),
    "exp_team_picked": ("ExpLuxcavation", [{"set": "luxcavation/exp/team", "value": "b"}]),
    "exp_team_gone": ("ExpLuxcavation", [{"set": "luxcavation/exp/team", "value": "gone"}]),
    "exp_team_none": ("ExpLuxcavation", []),
    # GoHome's sub-task meets the game's download dialog (TitleDownload.png): with run.auto_download off
    "download_off": ("ClaimMail", [{"set": "run/auto_download", "value": False}]),
}
READ_BACK = {"values": "MirrorHub", "exp_team_picked": "ExpLuxcavation"}  # whose next is ReadBack, which ends the task


def child():
    from maa.custom_action import CustomAction

    actions, resource = load()

    class Still(game_class()):
        images = {"main": screen("MainWindow.png"), "download": screen("TitleDownload.png")}

    class ReadBack(CustomAction):
        """The next of a READ_BACK node: what a node after the entry reads, the task's options, and the team and guard
        turns a Luxcavation task's start set."""

        def run(self, context, argv):
            team = actions.RUN.get("team") or {}
            read_back.update(options=actions.TASK.get("options"), team=[team.get("id"), team.get("game_team"), actions.RUN.get("guard")])
            return True

    resource.register_custom_action("ReadBack", ReadBack())
    game = Still()
    tasker = bind(resource, game)
    out, read_back = {"error": None}, {}

    def evidence():
        """How many evidence folders the stop procedure has left."""
        folder = actions.ROOT / "logs" / "evidence"
        return len(list(folder.iterdir())) if folder.exists() else 0

    for name, (task, edits) in SCENARIOS.items():
        (actions.ROOT / "config").mkdir(exist_ok=True)
        (actions.ROOT / "config" / "settings.json").write_text(json.dumps(apply_edits(CASES["valid"], edits)), encoding="utf-8")
        game.screen = "download" if name == "download_off" else "main"
        game.clicks, game.keys = [], []
        before = evidence()
        actions.LOG.clear()
        override = ({READ_BACK[name]: {"next": ["ReadBack"]}, "ReadBack": {"action": "Custom", "custom_action": "ReadBack"}}
                    if name in READ_BACK else None)
        out[name] = {**result(run_task(tasker, name, task, override), game, actions),
                     "stops": [line.split(" ", 1)[1] for line in actions.LOG if " stop: " in line],
                     "said": [line.split(" ", 1)[1] for line in actions.LOG], "evidence": evidence() - before,
                     "halted": actions.STUCK["halted"], "read_back": dict(read_back)}
        actions.STUCK["halted"] = None
        read_back.clear()
    print(json.dumps(out))


def test_the_real_mirror_dungeon_reads_the_values_of_the_settings_file():
    o = run_child(__file__)["values"]
    assert o["succeeded"] and (o["nodes"][0], o["nodes"][-1]) == ("MirrorDungeon", "ReadBack") and o["clicks"] == [], o
    assert o["read_back"]["options"] == NOT_DEFAULT_READ
    assert NOT_DEFAULT_LINE in o["said"] and not any("hook.invalid" in line for line in o["said"])


def test_the_real_mirror_dungeon_ends_at_its_entry_node_on_a_target_floor_its_teams_cannot_play():
    # Before MirrorHub, before any tap: a failure (no stop procedure, no evidence), the line saying which team.
    o = run_child(__file__)["target_normal_only"]
    error = "teams/0/usage: team 'Team a' is normal_only, but run/target_floor 10 needs the whole run HARD"
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, ["MirrorDungeon"], [], []), o
    assert o["stops"] == [f"stop: {invalid([error])}"] and o["evidence"] == 0, o


def test_the_real_exp_luxcavation_plays_the_team_of_the_settings_file():
    # team b: its TEAMS #2 and 3 guard turns, not team a's #1 and 0
    o = run_child(__file__)["exp_team_picked"]
    assert o["succeeded"] and o["nodes"] == ["ExpLuxcavation", "ReadBack"] and (o["clicks"], o["keys"]) == ([], []), o
    assert o["read_back"]["options"]["team"] == "b" and o["read_back"]["team"] == ["b", 2, 3]
    assert "EXP Luxcavation: team 'Team b' (TEAMS #2), 3 guard turns, mode daily, 0 retries, consecutive on" in o["said"], o["said"]


@pytest.mark.parametrize("name, error", [
    ("exp_team_gone", "luxcavation/exp/team: team 'gone' was deleted in the settings GUI; pick another in "
                      + WHERE.format("ExpLuxcavation")),
    ("exp_team_none", "luxcavation/exp/team: no team picked; pick one in " + WHERE.format("ExpLuxcavation")),
])
def test_the_real_exp_luxcavation_ends_at_its_entry_node_on_a_team_it_cannot_play(name, error):
    # The stop procedure (its evidence) before any tap.
    o = run_child(__file__)[name]
    assert (o["succeeded"], o["nodes"], o["clicks"], o["keys"]) == (False, ["ExpLuxcavation"], [], []), o
    assert o["stops"] == [f"stop: {invalid([error])}"], o
    assert o["evidence"] == 1


def test_the_global_options_reach_go_home_run_as_a_sub_task():
    # ClaimMail's GoHome (context.run_task from MailHome) meets the download dialog: run.auto_download off stops the task
    # and the rest of the list there (the stop procedure, post_stop), with no tap. On, the default, presses Confirm
    # (test_title_dialogs.py).
    o = run_child(__file__)["download_off"]
    assert o["nodes"] == ["ClaimMail", "MailHome"] and (o["clicks"], o["keys"]) == ([], []), o
    assert o["stops"][0] == "stop: the game asks to download data: run.auto_download is off", o
    assert o["halted"] and o["evidence"] == 1, o


if __name__ == "__main__":
    child()
