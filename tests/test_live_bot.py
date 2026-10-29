import json
import sys
from types import SimpleNamespace

from live import bot


def test_run_stamps_every_line_of_the_child_and_its_exit(tmp_path):
    log = tmp_path / "run.log"
    code = bot.stamped([sys.executable, "-c", "print('[maalc] hello'); print('x: 1, y: 2'); raise SystemExit(3)"], log,
                       clock=lambda: "12:00:00.000")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert code == 3
    assert lines[0].startswith("12:00:00.000 [run] child pid ")
    assert lines[1:] == ["12:00:00.000 [maalc] hello", "12:00:00.000 x: 1, y: 2", "12:00:00.000 [run] exit 3"]


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


def test_awake_holds_the_display_for_the_minutes():
    calls = []
    bot.awake(2, set_state=calls.append, sleep=calls.append)
    assert calls == [bot.ES_CONTINUOUS | bot.ES_SYSTEM_REQUIRED | bot.ES_DISPLAY_REQUIRED, 120, bot.ES_CONTINUOUS]


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

        def post_task(self, name):
            posted.append(name)
            return Job(name if name not in posted[:-1] else name + "2")

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
    assert bot.run_tasks(tasker, ["MirrorDungeon", "MirrorDungeon", "ExpLuxcavation"], lines.append, sleep) == [
        "succeeded", "pending", "none"]
    assert posted == ["MirrorDungeon", "MirrorDungeon", "ExpLuxcavation"]
    assert polls[:3] == ["MirrorDungeon"] * 3  # polled until its detail said done
    assert not tasker.running  # returned (the agent closes) only once the tasker had stopped
    assert [ln.split(" t=")[0] for ln in lines if "status=" in ln] == [
        "[run] MirrorDungeon status=succeeded", "[run] MirrorDungeon status=pending", "[run] ExpLuxcavation status=none"]
