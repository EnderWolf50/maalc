import json
import os
import signal
import sys
import shutil
import threading
from pathlib import Path

import pytest

import client_override
from client_options import TEAM_OPTIONS, override
from live import bot


def test_run_stamps_every_line_of_the_child_and_its_exit(tmp_path):
    log = tmp_path / "run.log"
    code = bot.stamped([sys.executable, "-c", "print('[maalc] hello'); print('x: 1, y: 2'); raise SystemExit(3)"], log,
                       clock=lambda: "12:00:00.000")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert code == 3
    assert lines[0].startswith("12:00:00.000 [run] child pid ")
    assert lines[1:] == ["12:00:00.000 [maalc] hello", "12:00:00.000 x: 1, y: 2", "12:00:00.000 [run] exit 3"]


def test_run_ends_when_the_child_exits_though_a_process_it_started_holds_its_output(tmp_path, monkeypatch):
    # #663: MaaFramework's `adb kill-server` then `adb connect` start an adb server that inherits the tasker's stdout
    # and outlives it, so the output never reaches end of file; the run ends with the child, not with the output
    monkeypatch.setattr(bot, "DRAIN", 0.5, raising=False)
    log = tmp_path / "run.log"
    server = "import time; time.sleep(60)"
    child = ("import subprocess, sys; s = subprocess.Popen([sys.executable, '-c', %r], close_fds=False); "
             "print('server', s.pid, flush=True)" % server)
    child += "; sys.stdout.write('a\\rb\\r\\nlast, no newline')"
    result = {}
    run = threading.Thread(target=lambda: result.update(code=bot.stamped([sys.executable, "-c", child], log,
                                                                          clock=lambda: "12:00:00.000")), daemon=True)
    run.start()
    run.join(20)
    lines = log.read_text(encoding="utf-8").splitlines()
    held = [int(line.split()[-1]) for line in lines if " server " in line]
    try:
        assert not run.is_alive(), "stamped still waits on the output the left-over process holds"
        assert result["code"] == 0
        assert lines[2:] == ["12:00:00.000 a", "12:00:00.000 b", "12:00:00.000 last, no newline",
                             "12:00:00.000 [run] output still open 0.5 s after the child exited: a process it started holds it",
                             "12:00:00.000 [run] exit 0"]
    finally:
        for pid in held:
            os.kill(pid, signal.SIGTERM)
        run.join(20)


def test_prep_copies_config_and_state_and_sets_keys(tmp_path):
    src, dst = tmp_path / "main", tmp_path / "test"
    (src / "config").mkdir(parents=True)
    (src / "state").mkdir()
    # the keys the agent still reads from the settings file: the teams and plans, not a task's options (#779-#781)
    (src / "config/settings.json").write_text(json.dumps({"language": "zh_tw", "teams": [{"id": "t3", "heal": "none"}]}))
    (src / "config/maa_option.json").write_text("{}")
    (src / "config/team_options.json").write_text('{"option": {}}')  # the settings GUI's (#780)
    (src / "state/progress.json").write_text("{}")
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "language=en_us", "--set", "teams.t3.heal=revive"])
    s = json.loads((dst / "config/settings.json").read_text())
    assert s == {"language": "en_us", "teams": [{"id": "t3", "heal": "revive"}]}
    assert (dst / "config/maa_option.json").exists() and (dst / "state/progress.json").exists()
    assert (dst / "config/team_options.json").read_text() == '{"option": {}}'  # bot.py run --option ExpTeam= picks from it
    assert json.loads((src / "config/settings.json").read_text())["language"] == "zh_tw"  # the source stays


@pytest.mark.parametrize("key, says", [
    ("run.runs=1", "bot.py run --option MirrorRunsLimit=Yes --option MirrorRuns=1"),
    ("run.runs=null", "bot.py run --option MirrorRunsLimit=No"),
    ("run.difficulty=normal", "bot.py run --option MirrorDifficulty=normal"),
    ("run.target_floor=10", "bot.py run --option MirrorTargetFloor=10"),
    ("run.auto_download=false", "bot.py run --option AutoDownload=No"),
    ("run.stop_when_weekly_bonus_out=true", "bot.py run --option MirrorStopWhenBonusOut=Yes"),
    ("run.nope=1", "the settings' run section is no longer read: set its options with bot.py run --option"),
    # #781: a daily task's own, a nested count after the case that sends it
    ("luxcavation.exp.mode=count", "bot.py run --option ExpMode=count"),
    ("luxcavation.thread.count=5", "bot.py run --option ThreadMode=count --option ThreadCount=5"),
    ("luxcavation.exp.retries=2", "bot.py run --option ExpRetries=2"),
    ("luxcavation.thread.consecutive=false", "bot.py run --option ThreadConsecutive=No"),
    ("charge_enkephalin.count=3", "bot.py run --option ChargeCount=3"),
    # a key under a moved section that is not an option, and a whole section, or one that holds one: all stop
    ("run.x.y=1", "the settings' run section is no longer read: set its options with bot.py run --option"),
    ("charge_enkephalin.nope=1", "the settings' charge_enkephalin section is no longer read: set its options with bot.py run --option"),
    ("luxcavation.exp.nope=1", "the settings' luxcavation.exp section is no longer read: set its options with bot.py run --option"),
    ("run={}", "the agent reads run's keys from the client's options: set them with bot.py run --option"),
    ("luxcavation.thread={}", "the agent reads luxcavation.thread's keys from the client's options: set them with bot.py "
     "run --option"),
    ("luxcavation={}", "the agent reads luxcavation.exp's keys from the client's options: set them with bot.py run --option"),
    # #780: a Luxcavation task's team is its dropdown, a case per team id; null is 「未選擇」
    ("luxcavation.exp.team=t3", "bot.py run --option ExpTeam=t3"),
    ("luxcavation.thread.team=null", "bot.py run --option ThreadTeam=none"),
    ("run.webhook_url=null", "bot.py run --option WebhookUrl=null"),  # none is a team's 「未選擇」 alone
])
def test_prep_stops_on_a_key_the_client_took_over_and_names_its_option(tmp_path, key, says):
    # #779, #780, #781: the agent no longer reads these keys of the settings file; a value set there would not happen
    src, dst = prep_source(tmp_path), tmp_path / "test"
    with pytest.raises(SystemExit) as e:
        bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "teams.t3.heal=revive", "--set", key])
    assert str(e.value) == f"prep: {key.split('=')[0]} is a task or global option of the client now: {says}"
    assert not dst.exists()


def test_every_key_prep_refuses_names_an_option_of_the_interface():
    # the option names come from the agent's schema titles: each is an option assets/interface.json has. The keys are
    # every one of the three sections settings version 21 dropped (#782), as a v0.1.0 file had them (settings_cases v20).
    options = client_override.load_interface(REPO / "assets/interface.json")["option"]
    v20 = json.loads((REPO / "tests/settings_cases.json").read_text(encoding="utf-8"))["v20"]
    keys = [*(f"run.{k}" for k in v20["run"]),
            *(f"luxcavation.{task}.{k}" for task in ("exp", "thread") for k in v20["luxcavation"][task]),
            *(f"charge_enkephalin.{k}" for k in v20["charge_enkephalin"])]
    assert len(keys) == 25
    for key in keys:
        where = bot.moved(key, "1")
        named = [w.split("=")[0] for w in where.split("--option ")[1:]]
        assert named and all(n in options for n in named), (key, where)


def prep_source(tmp_path):
    src = tmp_path / "main"
    (src / "config").mkdir(parents=True)
    teams = [{"id": "t1", "heal": "none"}, {"id": "t3", "heal": "none", "min_alive": 3}]
    (src / "config/settings.json").write_text(json.dumps({"teams": teams}))
    (src / "config/maa_option.json").write_text("{}")
    return src


def test_prep_goes_on_when_the_source_has_no_state(tmp_path):
    # #763: the bot's first start turns the old rotation cursor into the team queue's head (#501) and removes state/.
    # #780: nor a team options file, and one an earlier prep left goes: its teams may not be the source's
    src, dst = prep_source(tmp_path), tmp_path / "test"
    (dst / "config").mkdir(parents=True)
    (dst / "config/team_options.json").write_text("{}")
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "teams.t3.heal=revive"])
    assert not (dst / "config/team_options.json").exists()
    assert json.loads((dst / "config/settings.json").read_text())["teams"][1]["heal"] == "revive"
    assert (dst / "config/maa_option.json").exists() and not (dst / "state").exists()


def test_prep_sets_a_list_item_by_its_id(tmp_path):
    src, dst = prep_source(tmp_path), tmp_path / "test"
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "teams.t3.heal=revive", "--set", "teams.t3.min_alive=4"])
    s = json.loads((dst / "config/settings.json").read_text())
    assert s["teams"] == [{"id": "t1", "heal": "none"}, {"id": "t3", "heal": "revive", "min_alive": 4}]


@pytest.mark.parametrize("key, says", [("teams.t9.heal", "no item with id 't9'"), ("teams.t3", "names a list item")])
def test_prep_stops_on_a_key_it_cannot_set_before_the_install_is_touched(tmp_path, key, says):
    src, dst = prep_source(tmp_path), tmp_path / "test"
    with pytest.raises(SystemExit, match=says):
        bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "teams.t1.heal=revive", "--set", f"{key}=1"])
    assert not dst.exists()


def test_awake_holds_the_display_for_the_minutes():
    calls = []
    bot.awake(2, set_state=calls.append, sleep=calls.append)
    assert calls == [bot.ES_CONTINUOUS | bot.ES_SYSTEM_REQUIRED | bot.ES_DISPLAY_REQUIRED, 120, bot.ES_CONTINUOUS]


REPO = Path(__file__).resolve().parent.parent

INTERFACE = """{
    "interface_version": 2,
    // a whole-line comment, as assets/interface.json has
    "task": [{"name": "Mirror", "entry": "MirrorEntry", "option": ["Difficulty"]}],
    "option": {"Difficulty": {"cases": [
        {"name": "auto", "pipeline_override": {"MirrorEntry": {"attach": {"difficulty": "auto"}}}},
        {"name": "hard", "pipeline_override": {"MirrorEntry": {"attach": {"difficulty": "hard"}}}}]}}
}"""


def test_plan_posts_each_task_with_the_override_mxu_would_send_and_says_the_values(tmp_path):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    lines = []
    jobs = bot.plan(tmp_path, ["Mirror", "Mirror"], ["Difficulty=hard"], lines.append)
    assert jobs == [("Mirror", "MirrorEntry", [{"MirrorEntry": {"attach": {"difficulty": "hard"}}}])] * 2
    assert lines == ["[run] Mirror options: Difficulty=hard"] * 2


def test_plan_posts_every_task_of_the_interface_with_the_global_options_and_its_own():
    # #779: every task sends the four global options at their defaults, MirrorDungeon its own ten too. The repo's
    # assets/ has no team options file (#780): a line says so, as MXU warns, and the team dropdowns have no case.
    tasks = [t["name"] for t in client_override.load_interface(REPO / "assets/interface.json")["task"]]
    lines = []
    jobs = bot.plan(REPO / "assets", tasks, ["MirrorRuns=2"], lines.append)
    assert tasks and jobs == [(name, name, override(name, "MirrorRuns=2", teams=None)) for name in tasks]
    assert lines[0] == "[run] import config/team_options.json not read (FileNotFoundError): skipped"
    assert all(line.startswith(f"[run] {name} options: WebhookUrl=(not set) (default), AutoAcceptTerms=Yes (default)")
               for name, line in zip(tasks, lines[1:]))
    assert "MirrorRunsLimit=Yes (default), MirrorRuns=2, " in lines[1 + tasks.index("MirrorDungeon")]
    assert ", ExpTeam=(no case) (default), " in lines[1 + tasks.index("ExpLuxcavation")]


@pytest.mark.parametrize("task, option, key", [("ExpLuxcavation", "ExpTeam", "team"),
                                               ("MirrorDungeon", "MirrorStartTeam", "start_team")])
def test_run_option_picks_a_team_of_the_team_options_file_the_install_has(tmp_path, task, option, key):
    # #780, #805: --option <option>=<team id> sends the case of that team, which writes its id into the entry's attach
    shutil.copy(REPO / "assets/interface.json", tmp_path / "interface.json")
    (tmp_path / "config").mkdir()
    shutil.copy(TEAM_OPTIONS, tmp_path / "config/team_options.json")
    lines = []
    ((_, entry, array),) = bot.plan(tmp_path, [task], [f"{option}=b"], lines.append)
    assert entry == task and {task: {"attach": {key: "b"}}} in array
    assert f", {option}=b" in lines[0]
    with pytest.raises(SystemExit, match=f"{option} has no case t9"):
        bot.plan(tmp_path, [task], [f"{option}=t9"], lines.append)


@pytest.mark.parametrize("tasks, option, says", [
    ("Mirror", "Nope=1", "--option Nope=1: interface.json has no option Nope"),
    ("Mirror", "Difficulty=extreme", "--option Difficulty=extreme: Difficulty has no case extreme (cases: auto, hard)"),
    ("Mirror,Nope", "Difficulty=hard", "interface.json has no task Nope (tasks: Mirror)"),
])
def test_run_stops_before_posting_any_task_on_an_option_case_or_task_the_interface_lacks(tmp_path, tasks, option, says):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    log = tmp_path / "run.log"
    code = bot.main(["run", "--install", str(tmp_path), "--log", str(log), "--task", tasks, "--option", option])
    lines = log.read_text(encoding="utf-8").splitlines()
    assert code != 0
    assert any(line.endswith(f"[run] {says}: stopped before posting any task") for line in lines), lines
    assert not any("[run] start" in line or " options: " in line for line in lines)  # no device, no task, no values


FAKE_RUNNER = """
import json, os, sys
from pathlib import Path
start = sys.stdin.readline()
Path(__file__).with_name("start.json").write_text(start, encoding="utf-8")
for e in [{"event": "ready", "pid": os.getpid()}, {"event": "task", "index": 0, "entry": "MirrorEntry", "state": "running"},
          {"event": "log", "t": "10:00:00.001", "source": "agent", "line": "[maalc] 開始"},
          {"event": "log", "t": "10:00:00.002", "source": "console", "line": "x: 960, y: 540, width: 1920, height: 1080"},
          {"event": "end", "result": "succeeded"}]:
    print(json.dumps({"v": 1, **e}), flush=True)
raise SystemExit({code})
"""


def fake_install(tmp_path, code=0):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    (tmp_path / "runner").mkdir()
    (tmp_path / "runner/__main__.py").write_text(FAKE_RUNNER.replace("{code}", str(code)), encoding="utf-8")
    return tmp_path


def test_run_goes_through_the_installs_runner_with_each_tasks_override_and_logs_its_lines(tmp_path):
    # #812: the runner posts each task with the override bot.py built from --option (#778), as it came; run.log gets
    # the runner's log lines at their own time, and nothing for its other events
    root, log = fake_install(tmp_path), tmp_path / "run.log"
    code = bot.main(["run", "--install", str(root), "--log", str(log), "--task", "Mirror,Mirror", "--port", "16416",
                     "--option", "Difficulty=hard"])
    assert code == 0
    start = json.loads((root / "runner/start.json").read_text(encoding="utf-8"))
    hard = [{"MirrorEntry": {"attach": {"difficulty": "hard"}}}]
    assert start == {"v": 1, "cmd": "start", "root": str(root.resolve()), "device": {"address": "127.0.0.1:16416"},
                     "tasks": [{"entry": "MirrorEntry", "override": hard}] * 2}
    lines = log.read_text(encoding="utf-8").splitlines()
    assert [ln.split(" ", 1)[1] for ln in lines[:2]] == ["[run] Mirror options: Difficulty=hard"] * 2
    assert " [run] child pid " in lines[2]  # tools/live/preflight.py's BOT_START
    assert lines[3:5] == ["10:00:00.001 [maalc] 開始", "10:00:00.002 x: 960, y: 540, width: 1920, height: 1080"]
    assert lines[5].endswith(" [run] exit 0") and len(lines) == 6


@pytest.mark.parametrize("code", [1, 2])
def test_run_exits_with_the_runners_code_when_a_task_did_not_succeed(tmp_path, code):
    root, log = fake_install(tmp_path, code), tmp_path / "run.log"
    assert bot.main(["run", "--install", str(root), "--log", str(log), "--task", "Mirror"]) == code


def test_run_stops_before_any_child_when_the_install_has_no_runner(tmp_path):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    log = tmp_path / "run.log"
    assert bot.main(["run", "--install", str(tmp_path), "--log", str(log), "--task", "Mirror"]) == 1
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[-1].endswith("has no runner/: assemble the install with tools/install.py")
    assert not any("child pid" in line for line in lines)


def test_a_runner_that_cannot_stop_has_its_process_tree_ended():
    # the bot exited mid-run and MaaFramework does not stop (#812): the runner says so, its caller ends its tree
    killed = []
    events = bot.RunnerEvents(clock=lambda: "12:00:00.000", kill=killed.append)
    assert events('{"v": 1, "event": "ready", "pid": 4242}') is None
    assert events('{"v": 1, "event": "error", "kind": "agent_exit", "message": "the bot exited with code 3"}') is None
    assert events('{"v": 1, "event": "error", "kind": "stop_timeout", "message": "MaaFramework did not stop"}') == (
        "12:00:00.000", "[run] the runner cannot stop MaaFramework: its process tree 4242 ended")
    assert killed == [4242]
    assert events("Fatal Python error: not the protocol") == ("12:00:00.000", "Fatal Python error: not the protocol")
