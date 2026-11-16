import json
import os
import signal
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import client_override
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
    (src / "config/settings.json").write_text(json.dumps({"run": {"runs": 5, "difficulty": "hard"}}))
    (src / "config/maa_option.json").write_text("{}")
    (src / "state/progress.json").write_text("{}")
    bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "run.runs=1", "--set", "run.difficulty=normal",
              "--set", "run.weekly_bonus_use=none"])
    s = json.loads((dst / "config/settings.json").read_text())
    assert s["run"] == {"runs": 1, "difficulty": "normal", "weekly_bonus_use": "none"}
    assert (dst / "config/maa_option.json").exists() and (dst / "state/progress.json").exists()
    assert json.loads((src / "config/settings.json").read_text())["run"]["runs"] == 5  # the source stays


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
        bot.main(["prep", "--install", str(dst), "--source", str(src), "--set", "run.runs=1", "--set", f"{key}=1"])
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


def test_plan_sends_no_override_for_the_interface_as_it_is_without_options():
    # #778 lands before interface.json has options: every task posts as it did before, with nothing to override
    tasks = [t["name"] for t in client_override.load_interface(REPO / "assets/interface.json")["task"]]
    lines = []
    jobs = bot.plan(REPO / "assets", tasks, [], lines.append)
    assert len(tasks) == 7 and jobs == [(name, name, []) for name in tasks]
    assert lines == [f"[run] {name} options: none" for name in tasks]


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


def test_run_tasks_posts_the_list_up_front_and_follows_each_task_by_its_detail():
    # #364: a client queues its whole task list; an account-level stop (post_stop) leaves the rest pending, unrun.
    # G1: as MXU, a task is done when its detail says so, not when wait() returns, and the agent stays up until the
    # tasker has stopped.
    status = dict(done=False, succeeded=False, failed=False, running=False, pending=False)
    running = SimpleNamespace(**{**status, "running": True})
    details = {
        "MirrorDungeon": [running, running, SimpleNamespace(**{**status, "done": True, "succeeded": True})],
        "MirrorDungeon2": [SimpleNamespace(**{**status, "pending": True})],
        "ExpLuxcavation": [None],
    }
    posted, polls = [], []

    class Tasker:
        ticks = 0

        @property
        def running(self):  # the account-level stop: the first task ends it, the rest stay pending
            return self.ticks < 4

        def post_task(self, entry, override):
            posted.append((entry, override))
            return Job(entry if entry not in [e for e, _ in posted[:-1]] else entry + "2")

    class Job:
        def __init__(self, name):
            self.name = name

        def wait(self):
            raise AssertionError("wait() returns early once a task's runner id is gone")

        def get(self):
            polls.append(self.name)
            reads = details[self.name]
            s = reads.pop(0) if len(reads) > 1 else reads[0]
            return s and type("Detail", (), {"status": s, "nodes": []})()

    tasker = Tasker()

    def sleep(seconds):
        tasker.ticks += 1

    lines = []
    hard, normal = [{"MirrorDungeon": {"attach": {"difficulty": "hard"}}}], [{"MirrorDungeon": {"attach": {"difficulty": "normal"}}}]
    jobs = [("MirrorDungeon", "MirrorDungeon", hard), ("MirrorDungeon", "MirrorDungeon", normal), ("ExpLuxcavation", "ExpLuxcavation", [])]
    assert bot.run_tasks(tasker, jobs, lines.append, sleep) == ["succeeded", "pending", "none"]
    assert posted == [("MirrorDungeon", hard), ("MirrorDungeon", normal), ("ExpLuxcavation", [])]  # each its own override
    assert polls[:3] == ["MirrorDungeon"] * 3  # polled until its detail said done
    assert not tasker.running  # returned (the agent closes) only once the tasker had stopped
    assert [ln.split(" t=")[0] for ln in lines if "status=" in ln] == [
        "[run] MirrorDungeon status=succeeded", "[run] MirrorDungeon status=pending", "[run] ExpLuxcavation status=none"]
