import re
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image

from live import device as dv


class Job:
    def __init__(self, value=None):
        self.value = value

    def wait(self):
        return self

    def get(self):
        return self.value


class FakeCtl:
    """MaaFramework's controller: records the calls, screenshots are BGR like the real one's."""

    def __init__(self, frames=None):
        self.calls = []
        self.frames = list(frames or [])  # screenshots to hand out in turn, the last one repeating

    def post_screencap(self):
        if self.frames:
            return Job(self.frames.pop(0) if len(self.frames) > 1 else self.frames[0])
        img = np.zeros((720, 1280, 3), np.uint8)
        img[..., 0] = 255  # blue in BGR
        return Job(img)

    def post_click(self, x, y):
        self.calls.append(("click", x, y))
        return Job()

    def post_swipe(self, x1, y1, x2, y2, duration):
        self.calls.append(("swipe", x1, y1, x2, y2, duration))
        return Job()

    def post_click_key(self, key):
        self.calls.append(("key", key))
        return Job()

    def post_start_app(self, package):
        self.calls.append(("start", package))
        return Job()

    def post_stop_app(self, package):
        self.calls.append(("stop", package))
        return Job()


def test_pick_takes_the_device_on_the_port():
    devs = [SimpleNamespace(address="127.0.0.1:16416"), SimpleNamespace(address="127.0.0.1:16384")]
    assert dv.pick(devs, 16384).address == "127.0.0.1:16384"


def test_shot_saves_rgb(tmp_path):
    out = tmp_path / "s.png"
    dv.shot(FakeCtl(), out)
    assert Image.open(out).getpixel((0, 0)) == (0, 0, 255)


def test_tap_then_shot(tmp_path, monkeypatch):
    ctl = FakeCtl()
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    dv.main(["tap", "640", "360", "--wait", "0", "--shot", str(tmp_path / "after.png")])
    assert ctl.calls == [("click", 640, 360)] and (tmp_path / "after.png").exists()


def test_key_and_start(monkeypatch, tmp_path):
    ctl = FakeCtl()
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    dv.main(["key", "4"])
    dv.main(["start", "--shots", str(tmp_path), "--every", "0", "--count", "2"])
    assert ctl.calls == [("key", 4), ("start", dv.GAME)] and len(list(tmp_path.glob("boot-*.png"))) == 2


def test_press_holds_the_finger_in_place(monkeypatch):
    # #468: a long press, a swipe that does not move, held for --hold seconds.
    ctl = FakeCtl()
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    dv.main(["press", "640", "360", "--hold", "1.5"])
    assert ctl.calls == [("swipe", 640, 360, 640, 360, 1500)]


def test_wait_fire_needs_the_arm_line_first():
    lines = iter(["map: path a", "floor 2: pull x", "map: path b", "later"])
    assert dv.wait_fire(lines, re.compile("map: path"), re.compile("floor 2")) == "map: path b"


def test_commands_run_until_resume(tmp_path):
    ctl, cmd = FakeCtl(), tmp_path / "cmd.txt"
    cmd.write_text("tap 10 20\npress 30 40 0.8\npress 50 60\nkey 4\nshot map\nstart com.android.vending\nresume\n")
    dv.run_commands(ctl, cmd, tmp_path, deadline=float("inf"), poll=0)
    assert ctl.calls == [("click", 10, 20), ("swipe", 30, 40, 30, 40, 800), ("swipe", 50, 60, 50, 60, 1000), ("key", 4),
                         ("start", "com.android.vending")]
    assert [p.name.endswith("-map.png") for p in tmp_path.glob("*.png")] == [True]
    assert cmd.read_text() == ""


def test_freeze_suspends_the_bot_tree_and_resumes_it(tmp_path, monkeypatch):
    log = []
    procs = [SimpleNamespace(pid=n, suspend=lambda n=n: log.append(("suspend", n)), resume=lambda n=n: log.append(("resume", n)))
             for n in (1, 2)]
    ctl = FakeCtl()
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    monkeypatch.setattr(dv, "bot_tree", lambda pid: procs)
    monkeypatch.setattr(dv, "tail", lambda path: iter(["x", "[maalc] floor 1 packs, threshold 0: A (0)"]))
    (tmp_path / "cmd.txt").write_text("tap 1 1\n")  # left from an earlier freeze: cleared, not run
    dv.main(["freeze", "--log", "run.log", "--fire", "packs", "--pid", "9", "--cmd", str(tmp_path / "cmd.txt"), "--out", str(tmp_path),
             "--max", "0.1"])
    assert log == [("suspend", 1), ("suspend", 2), ("resume", 1), ("resume", 2)] and ctl.calls == []


def test_freeze_resumes_the_rest_when_one_process_ended(tmp_path, monkeypatch):
    log = []

    def gone():
        raise ProcessLookupError("ended")

    procs = [SimpleNamespace(pid=1, suspend=lambda: log.append("suspend 1"), resume=lambda: log.append("resume 1")),
             SimpleNamespace(pid=2, suspend=gone, resume=gone)]
    monkeypatch.setattr(dv, "connect", lambda port: FakeCtl())
    monkeypatch.setattr(dv, "bot_tree", lambda pid: procs)
    monkeypatch.setattr(dv, "tail", lambda path: iter(["packs"]))
    dv.main(["freeze", "--log", str(tmp_path / "run.log"), "--fire", "packs", "--pid", "9", "--max", "0.1"])
    assert log == ["suspend 1", "resume 1"]


def test_restart_stops_the_game_and_starts_it_as_the_pipelines_l3_does(monkeypatch, tmp_path):
    # The daily task restarts the game before the bot (2026-11-07). RecoverL3 stops the app, waits its post_delay, and
    # RecoverStartApp starts it; the screenshot comes --wait seconds after the start.
    from test_pipeline import load_nodes

    ctl, slept = FakeCtl(), []
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    monkeypatch.setattr(dv.time, "sleep", slept.append)
    dv.main(["restart", "--wait", "20", "--shot", str(tmp_path / "boot.png")])
    assert ctl.calls == [("stop", dv.GAME), ("start", dv.GAME)]
    assert slept == [load_nodes()["RecoverL3"]["post_delay"] / 1000, 20] and (tmp_path / "boot.png").exists()


def test_restart_takes_another_package_and_no_shot_without_one(monkeypatch):
    ctl, slept = FakeCtl(), []
    monkeypatch.setattr(dv, "connect", lambda port: ctl)
    monkeypatch.setattr(dv.time, "sleep", slept.append)
    dv.main(["restart", "com.android.vending"])
    assert ctl.calls == [("stop", "com.android.vending"), ("start", "com.android.vending")] and len(slept) == 1


SCREENS = Path(__file__).resolve().parent / "screens"


def screen(name):
    return cv2.imread(str(SCREENS / name))  # BGR, as MaaFramework hands it out


def plan_run(tmp_path, monkeypatch, frames, line="plan 5", deadline=float("inf")):
    """run_commands on one `plan` line; the pause between shots is 0, so the frames follow at once."""
    ctl, cmd = FakeCtl(frames), tmp_path / "cmd.txt"
    cmd.write_text(f"{line}\nresume\n")
    monkeypatch.setattr(dv, "PLAN_EVERY", 0)
    dv.run_commands(ctl, cmd, tmp_path, deadline=deadline, poll=0)
    return ctl, sorted(p.name for p in tmp_path.glob("*.png"))


def test_plan_stops_at_the_planning_phase(tmp_path, monkeypatch, capsys):
    # The game plays on while the bot is frozen: two shots of something else, then the Win Rate label is up.
    frames = [screen("EnterDialog.png"), screen("EnterDialog.png"), screen("BattleTurn.png")]
    ctl, shots = plan_run(tmp_path, monkeypatch, frames)
    out = capsys.readouterr().out
    assert [n.split("-", 1)[1] for n in shots] == ["plan-00.png", "plan-01.png", "plan-02.png"]
    assert f"PLANNING {tmp_path / shots[-1]}" in out and "timeout" not in out


def test_plan_stops_at_an_ego_card(tmp_path, monkeypatch, capsys):
    ctl, shots = plan_run(tmp_path, monkeypatch, [screen("BattleEgoCard.png")])
    assert len(shots) == 1 and f"CARD {tmp_path / shots[0]}" in capsys.readouterr().out


def test_plan_times_out_on_a_screen_that_is_neither(tmp_path, monkeypatch, capsys):
    clock = iter(range(1000))
    monkeypatch.setattr(dv.time, "time", lambda: next(clock))
    ctl, shots = plan_run(tmp_path, monkeypatch, [screen("EnterDialog.png")], line="plan 5")
    out = capsys.readouterr().out
    assert shots and "PLAN timeout after 5 s" in out and "PLANNING" not in out and "CARD" not in out


def test_plan_without_a_time_waits_120_s(tmp_path, monkeypatch, capsys):
    clock = iter(range(0, 10000, 30))  # each look at the clock is 30 s later
    monkeypatch.setattr(dv.time, "time", lambda: next(clock))
    plan_run(tmp_path, monkeypatch, [screen("EnterDialog.png")], line="plan")
    assert "PLAN timeout after 120 s" in capsys.readouterr().out


def test_plan_ends_with_the_freeze_when_max_runs_out_first(tmp_path, monkeypatch, capsys):
    # plan 100 in a freeze with 3 s left: the freeze resumes the bot then, so plan stops there and says which limit hit.
    clock = iter(range(1000))
    monkeypatch.setattr(dv.time, "time", lambda: next(clock))
    plan_run(tmp_path, monkeypatch, [screen("EnterDialog.png")], line="plan 100", deadline=3)
    out = capsys.readouterr().out
    assert "PLAN cut by the freeze's --max" in out and "timeout" not in out


def test_lines_after_a_cut_plan_do_not_run(tmp_path, monkeypatch):
    # The freeze is over when plan is cut by --max: a tap written after it would hit a bot that has resumed.
    clock = iter(range(1000))
    monkeypatch.setattr(dv.time, "time", lambda: next(clock))
    ctl, cmd = FakeCtl([screen("EnterDialog.png")]), tmp_path / "cmd.txt"
    cmd.write_text("plan 100\ntap 10 20\n")
    monkeypatch.setattr(dv, "PLAN_EVERY", 0)
    dv.run_commands(ctl, cmd, tmp_path, deadline=3, poll=0)
    assert ctl.calls == []


def test_plan_does_not_sleep_past_its_end(tmp_path, monkeypatch):
    slept = []
    clock = iter(range(1000))
    monkeypatch.setattr(dv.time, "time", lambda: next(clock))
    monkeypatch.setattr(dv.time, "sleep", slept.append)
    monkeypatch.setattr(dv, "PLAN_EVERY", 3)
    dv.plan(FakeCtl([screen("EnterDialog.png")]), tmp_path, 4, float("inf"))
    assert slept and all(s <= 3 for s in slept) and slept[-1] < 3


def test_commands_after_plan_run_once_it_ends(tmp_path, monkeypatch):
    ctl, cmd = FakeCtl([screen("BattleTurn.png")]), tmp_path / "cmd.txt"
    cmd.write_text("plan 5\ntap 10 20\nresume\n")
    monkeypatch.setattr(dv, "PLAN_EVERY", 0)
    dv.run_commands(ctl, cmd, tmp_path, deadline=float("inf"), poll=0)
    assert ctl.calls == [("click", 10, 20)]
