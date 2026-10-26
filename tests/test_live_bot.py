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


def test_run_tasks_posts_the_list_up_front_and_reports_each_task():
    # #364: a client queues its whole task list; an account-level stop (post_stop) leaves the rest pending, unrun.
    status = dict(succeeded=False, failed=False, running=False)
    states = iter([SimpleNamespace(**{**status, "succeeded": True}), SimpleNamespace(**status), None])
    posted = []

    class Job:
        def __init__(self, name):
            posted.append(name)
            self.name = name

        def wait(self):
            return self

        def get(self):
            s = next(states)
            return s and type("Detail", (), {"status": s, "nodes": []})()

    tasker = type("Tasker", (), {"post_task": lambda self, name: Job(name)})()
    lines = []
    assert bot.run_tasks(tasker, ["MirrorDungeon", "MirrorDungeon", "ExpLuxcavation"], lines.append) == [
        "succeeded", "pending", "none"]
    assert posted == ["MirrorDungeon", "MirrorDungeon", "ExpLuxcavation"]
    assert [ln.split(" t=")[0] for ln in lines if "status=" in ln] == [
        "[run] MirrorDungeon status=succeeded", "[run] MirrorDungeon status=pending", "[run] ExpLuxcavation status=none"]
