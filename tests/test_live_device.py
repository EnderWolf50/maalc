import re
from types import SimpleNamespace

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

    def __init__(self):
        self.calls = []

    def post_screencap(self):
        img = np.zeros((720, 1280, 3), np.uint8)
        img[..., 0] = 255  # blue in BGR
        return Job(img)

    def post_click(self, x, y):
        self.calls.append(("click", x, y))
        return Job()

    def post_click_key(self, key):
        self.calls.append(("key", key))
        return Job()

    def post_start_app(self, package):
        self.calls.append(("start", package))
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


def test_wait_fire_needs_the_arm_line_first():
    lines = iter(["map: path a", "floor 2: pull x", "map: path b", "later"])
    assert dv.wait_fire(lines, re.compile("map: path"), re.compile("floor 2")) == "map: path b"


def test_commands_run_until_resume(tmp_path):
    ctl, cmd = FakeCtl(), tmp_path / "cmd.txt"
    cmd.write_text("tap 10 20\nkey 4\nshot map\nstart com.android.vending\nresume\n")
    dv.run_commands(ctl, cmd, tmp_path, deadline=float("inf"), poll=0)
    assert ctl.calls == [("click", 10, 20), ("key", 4), ("start", "com.android.vending")]
    assert [p.name.endswith("-map.png") for p in tmp_path.glob("*.png")] == [True]
    assert cmd.read_text() == ""


def test_freeze_suspends_the_bot_tree_and_resumes_it(tmp_path, monkeypatch):
    log = []
    procs = [SimpleNamespace(pid=n, suspend=lambda n=n: log.append(("suspend", n)), resume=lambda n=n: log.append(("resume", n)))
             for n in (1, 2)]
    monkeypatch.setattr(dv, "connect", lambda port: FakeCtl())
    monkeypatch.setattr(dv, "bot_tree", lambda pid: procs)
    monkeypatch.setattr(dv, "tail", lambda path: iter(["x", "[maalc] floor 1 packs, threshold 0: A (0)"]))
    (tmp_path / "cmd.txt").write_text("tap 1 1\n")  # left from an earlier freeze: cleared, not run
    dv.main(["freeze", "--log", "run.log", "--fire", "packs", "--pid", "9", "--cmd", str(tmp_path / "cmd.txt"), "--out", str(tmp_path),
             "--max", "0.1"])
    assert log == [("suspend", 1), ("suspend", 2), ("resume", 1), ("resume", 2)]


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
