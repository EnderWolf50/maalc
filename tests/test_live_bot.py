import json
import os
import signal
import sys
import threading
from pathlib import Path

import pytest

from live import bot
from runner import protocol


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
    (src / "config/settings.json").write_text(json.dumps({"run": {"runs": 5, "difficulty": "hard"}}))
    (src / "config/maa_option.json").write_text("{}")
    (src / "state/progress.json").write_text("{}")
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "run.runs=1", "--set", "run.difficulty=normal",
              "--set", "run.weekly_bonus_use=none"])
    s = json.loads((dst / "config/settings.json").read_text())
    assert s["run"] == {"runs": 1, "difficulty": "normal", "weekly_bonus_use": "none"}
    assert (dst / "config/maa_option.json").exists() and (dst / "state/progress.json").exists()
    assert json.loads((src / "config/settings.json").read_text())["run"]["runs"] == 5  # the source stays


@pytest.mark.parametrize("key, value", [
    # #813: the task options are the settings file's again, every section of them
    ("run.runs", None), ("run.start_team", "t3"), ("run.auto_download", False), ("luxcavation.exp.team", "t3"),
    ("luxcavation.thread.mode", "count"), ("charge_enkephalin.count", 3),
])
def test_prep_sets_the_task_options(tmp_path, key, value):
    src, dst = prep_source(tmp_path), tmp_path / "test"
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", f"{key}={json.dumps(value)}"])
    node = json.loads((dst / "config/settings.json").read_text())
    for part in key.split("."):
        node = node[part]
    assert node == value


def prep_source(tmp_path):
    src = tmp_path / "main"
    (src / "config").mkdir(parents=True)
    teams = [{"id": "t1", "heal": "none"}, {"id": "t3", "heal": "none", "min_alive": 3}]
    (src / "config/settings.json").write_text(json.dumps({"teams": teams}))
    (src / "config/maa_option.json").write_text("{}")
    return src


def test_prep_goes_on_when_the_source_has_no_state(tmp_path):
    # #763: the bot's first start turns the old rotation cursor into the team queue's head (#501) and removes state/
    src, dst = prep_source(tmp_path), tmp_path / "test"
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "teams.t3.heal=revive"])
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
    "task": [{"name": "Mirror", "entry": "MirrorEntry"}]
}"""


def test_plan_names_each_tasks_entry_node(tmp_path):
    # #813: a task's options are the settings file's, so nothing else goes with the post
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    assert bot.plan(tmp_path, ["Mirror", "Mirror"]) == [("Mirror", "MirrorEntry")] * 2


def test_plan_takes_every_task_of_the_repos_interface():
    tasks = json.loads((REPO / "agent/settings.schema.json").read_text(encoding="utf-8"))["$defs"]["task"]["enum"]
    assert bot.plan(REPO / "assets", tasks) == [(name, name) for name in tasks]


def test_run_stops_before_posting_any_task_on_a_task_the_interface_lacks(tmp_path):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    log = tmp_path / "run.log"
    code = bot.main(["run", "--install", str(tmp_path), "--log", str(log), "--task", "Mirror,Nope"])
    lines = log.read_text(encoding="utf-8").splitlines()
    assert code != 0
    says = "[run] interface.json has no task Nope (tasks: Mirror): stopped before posting any task"
    assert any(line.endswith(says) for line in lines), lines
    assert not any("[run] start" in line for line in lines)  # no device, no task


def test_run_takes_no_option(tmp_path):
    # #813: the options are prep's, in the settings file
    with pytest.raises(SystemExit):
        bot.main(["run", "--install", str(tmp_path), "--log", str(tmp_path / "run.log"), "--option", "MirrorRuns=2"])


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


def test_run_goes_through_the_installs_runner_with_each_tasks_entry_and_logs_its_lines(tmp_path):
    # #812: the runner posts each task with the override it is given, as it came; #813: the options are the
    # settings file's, so bot.py gives none. run.log gets the runner's log lines at their own time, and nothing for
    # its other events
    root, log = fake_install(tmp_path), tmp_path / "run.log"
    code = bot.main(["run", "--install", str(root), "--log", str(log), "--task", "Mirror,Mirror", "--port", "16416"])
    assert code == 0
    start = json.loads((root / "runner/start.json").read_text(encoding="utf-8"))
    assert start == {"v": protocol.VERSION, "cmd": "start", "root": str(root.resolve()),
                     "device": {"address": "127.0.0.1:16416"}, "tasks": [{"entry": "MirrorEntry"}] * 2}
    # a start the runner takes, each task with no override
    assert protocol.command(json.dumps(start))["tasks"] == [{"entry": "MirrorEntry", "override": {}}] * 2
    lines = log.read_text(encoding="utf-8").splitlines()
    assert " [run] child pid " in lines[0]  # tools/live/preflight.py's BOT_START
    assert lines[1:3] == ["10:00:00.001 [maalc] 開始", "10:00:00.002 x: 960, y: 540, width: 1920, height: 1080"]
    assert lines[3].endswith(" [run] exit 0") and len(lines) == 4


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
