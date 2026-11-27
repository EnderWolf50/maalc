"""tools/live/pc_shots.py offline (#941): a fake desk of windows (test_pc's Desk, with the state the tool compares) and a
FakeCtl for MaaFramework's Win32 controller; no real window is looked at or sent anything."""
import json

import numpy as np
import pytest
from PIL import Image
from test_pc import HWND, Desk, game

from live import pc_shots as ps
from live import queue
from runner import pc


class Job:
    def __init__(self, value=None, succeeded=True):
        self.value, self.succeeded = value, succeeded

    def wait(self):
        return self

    def get(self):
        return self.value


def frame(level, size=(1080, 1920)):
    return np.full((*size, 3), level, np.uint8)


class FakeCtl:
    """MaaFramework's Win32 controller: every call noted, input calls among them (any post_* it has no answer for);
    screenshots handed out in turn, the last one repeating; `during` runs inside each screencap (the window changing
    while it is taken)."""

    def __init__(self, frames=None, during=None):
        self.calls, self.frames, self.during = [], list(frames or [frame(100)]), during

    def set_screenshot_use_raw_size(self, on):
        self.calls.append(("raw", on))

    def post_connection(self):
        self.calls.append(("connection",))
        return Job()

    def post_screencap(self):
        self.calls.append(("screencap",))
        if self.during:
            self.during()
        return Job(self.frames.pop(0) if len(self.frames) > 1 else self.frames[0])

    def post_inactive(self):
        self.calls.append(("inactive",))
        return Job()

    def __getattr__(self, name):
        if name.startswith("post_"):
            return lambda *args: self.calls.append((name, *args)) or Job()
        raise AttributeError(name)


NOT_INPUT = {"raw", "connection", "screencap", "inactive"}


class PcDesk(Desk):
    """test_pc's Desk with what the tool reads besides: the foreground window, the cursor, the window's styles, its DPI."""

    def __init__(self, *windows, foreground=HWND, cursor=(500, 400), style=0x14CA0000, exstyle=0x100):
        super().__init__(*windows)
        self.foreground, self.cursor, self.style, self.exstyle = foreground, cursor, style, exstyle

    def state(self, hwnd):
        look = self.look(hwnd)
        return None if look is None else ps.State(self.foreground, self.cursor, look.rect, self.style, self.exstyle)

    def dpi(self, hwnd):
        return 96

    def hdr(self, hwnd):
        return {"monitor": "DISPLAY1", "advanced_color": False}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


def watch(tmp_path, desk, ctl, **kw):
    """A watch on desk through ctl; (what it said, the events it wrote, the shots it saved, what the inner was made with)."""
    clock, said, made = Clock(), [], []

    def make(*args):
        made.append(args)
        return ctl
    kw = {"max_shots": 500, "max_seconds": 1200, **kw}
    try:
        ps.watch(desk, tmp_path, pc.FRAME_POOL, make=make, clock=clock, sleep=clock.sleep, say=said.append, **kw)
    finally:
        events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()] \
            if (tmp_path / "events.jsonl").exists() else []
    return said, events, sorted(p.name for p in tmp_path.glob("shot-*.png")), made


def test_a_screen_that_did_not_change_is_not_saved_again(tmp_path):
    ctl = FakeCtl([frame(100), frame(100), frame(101), frame(200), frame(200), frame(30)])
    said, events, shots, _ = watch(tmp_path, PcDesk(game()), ctl, max_seconds=11)
    assert shots == ["shot-0001.png", "shot-0002.png", "shot-0003.png"]  # 100, 200, 30: a 1-level flicker is no change
    assert [e["saved"] for e in events if e["action"] == "screencap"] == [
        "shot-0001.png", None, None, "shot-0002.png", None, "shot-0003.png"]
    assert Image.open(tmp_path / "shot-0002.png").getpixel((0, 0)) == (200, 200, 200)


def test_a_shot_every_two_seconds_until_the_time_limit(tmp_path):
    said, events, _, _ = watch(tmp_path, PcDesk(game()), FakeCtl(), max_seconds=20)
    shots = [e for e in events if e["action"] == "screencap"]
    assert len(shots) == 10 and events[-1]["action"] == "end" and "20 s" in events[-1]["reason"]


def test_the_shot_limit_ends_the_watch(tmp_path):
    ctl = FakeCtl([frame(n * 40) for n in range(1, 6)])
    said, events, shots, _ = watch(tmp_path, PcDesk(game()), ctl, max_shots=3)
    assert shots == ["shot-0001.png", "shot-0002.png", "shot-0003.png"]
    assert events[-1]["action"] == "end" and "3 shots" in events[-1]["reason"]


def test_a_minimized_window_stops_the_watch_with_why_and_gets_no_screencap(tmp_path):
    desk = PcDesk(game())
    ctl = FakeCtl()
    clock = Clock()

    def sleep(s):
        clock.sleep(s)
        desk.set(HWND, minimized=True)  # the user minimizes the game after the first shot
    with pytest.raises(ps.Stop, match="minimized") as stop:
        ps.watch(desk, tmp_path, pc.FRAME_POOL, make=lambda *a: ctl, clock=clock, sleep=sleep, say=print)
    assert "transparent" in str(stop.value) and "restore" in str(stop.value)
    assert ctl.calls.count(("screencap",)) == 1  # the minimized window got none
    last = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert last["action"] == "stop" and "minimized" in last["reason"]


def test_a_window_minimized_at_the_start_is_not_connected_to(tmp_path):
    ctl = FakeCtl()
    with pytest.raises(ps.Stop, match="minimized"):
        watch(tmp_path, PcDesk(game(minimized=True)), ctl)
    assert ctl.calls == []


def test_the_watch_makes_no_input_call_and_its_controller_has_no_input(tmp_path):
    ctl = FakeCtl([frame(n * 40) for n in range(1, 6)])
    _, _, _, made = watch(tmp_path, PcDesk(game()), ctl, max_seconds=14)
    assert {c[0] for c in ctl.calls} <= NOT_INPUT and ("screencap",) in ctl.calls
    assert made == [(HWND, pc.FRAME_POOL, pc.NULL, pc.NULL)]  # mouse and keyboard Null: no input unit (D6)


@pytest.mark.parametrize("change, field", [
    (lambda d: setattr(d, "foreground", 0x999), "foreground"),
    (lambda d: setattr(d, "cursor", (501, 400)), "cursor"),
    (lambda d: d.set(HWND, rect=(5, 0, 1936, 1119)), "rect"),
    (lambda d: setattr(d, "style", 0x14CA0001), "style"),
    (lambda d: setattr(d, "exstyle", 0x80020), "exstyle"),  # WS_EX_LAYERED | WS_EX_TRANSPARENT: a pseudo-minimize
])
def test_a_state_that_differs_after_a_screencap_from_before_it_stops_the_watch(tmp_path, change, field):
    desk = PcDesk(game())
    ctl = FakeCtl(during=lambda: change(desk))
    with pytest.raises(ps.Stop, match=f"changed during the screencap: {field}"):
        watch(tmp_path, desk, ctl)
    stop = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stop["action"] == "stop" and stop["before"] != stop["after"] and stop["differs"] == [field]


def test_each_shot_logs_the_state_before_and_after_it_and_how_long_it_took(tmp_path):
    _, events, _, _ = watch(tmp_path, PcDesk(game()), FakeCtl(), max_seconds=2)
    shot = events[0]
    assert shot["action"] == "screencap" and shot["method"] == "FramePool" and shot["ms"] >= 0
    assert shot["before"] == shot["after"] == {"foreground": HWND, "cursor": [500, 400], "rect": [0, 0, 1936, 1119],
                                               "style": 0x14CA0000, "exstyle": 0x100}


def test_a_black_shot_stops_the_watch(tmp_path):
    with pytest.raises(ps.Stop, match="black"):
        watch(tmp_path, PcDesk(game()), FakeCtl([frame(0)]))


def test_a_shot_that_is_not_16_9_stops_the_watch(tmp_path):
    with pytest.raises(ps.Stop, match="1000x1000, not 16:9"):
        watch(tmp_path, PcDesk(game()), FakeCtl([frame(100, size=(1000, 1000))]))


@pytest.mark.parametrize("desk, why", [(PcDesk(), "no game window"),
                                       (PcDesk(game(), (0x77, pc.CLASS, pc.TITLE, pc.Look(1920, 1080))), "2 game windows")])
def test_none_or_two_game_windows_stop_before_anything(tmp_path, desk, why):
    ctl = FakeCtl()
    with pytest.raises(ps.Stop, match=why):
        watch(tmp_path, desk, ctl)
    assert ctl.calls == []


def test_the_user_stopping_it_ends_the_watch_as_a_stop_of_theirs(tmp_path):
    clock = Clock()

    def sleep(s):
        raise KeyboardInterrupt
    ps.watch(PcDesk(game()), tmp_path, pc.FRAME_POOL, make=lambda *a: FakeCtl(), clock=clock, sleep=sleep, say=print)
    last = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert last == {**last, "action": "end", "reason": "stopped by the user"}


# step 1-1 and 1-2
def test_info_names_the_one_game_window_and_what_windows_says_of_it(tmp_path):
    doc = ps.info(PcDesk(game()), tmp_path, steam=lambda: {"buildid": "26652290"})
    assert doc == {**doc, "title": pc.TITLE, "class": pc.CLASS, "client": [1920, 1080], "rect": [0, 0, 1936, 1119],
                   "minimized": False, "dpi": 96, "style": "0x14ca0000", "exstyle": "0x100",
                   "hdr": {"monitor": "DISPLAY1", "advanced_color": False}, "steam": {"buildid": "26652290"}}
    assert json.loads((tmp_path / "info.json").read_text(encoding="utf-8")) == doc


def test_info_of_a_minimized_window_stops(tmp_path):
    with pytest.raises(ps.Stop, match="minimized"):
        ps.info(PcDesk(game(minimized=True)), tmp_path, steam=dict)


def test_compare_takes_each_background_method_and_says_how_long_each_took(tmp_path):
    made = []

    def make(*args):
        made.append(args)
        return FakeCtl([frame(100 if args[1] == pc.FRAME_POOL else 104)])
    doc = ps.compare(PcDesk(game()), tmp_path, make=make, count=3, say=print)
    assert [m[1:] for m in made] == [(pc.FRAME_POOL, pc.NULL, pc.NULL), (pc.PRINT_WINDOW, pc.NULL, pc.NULL)]
    assert set(doc["methods"]) == {"FramePool", "PrintWindow"}
    assert all(len(m["ms"]) == 3 for m in doc["methods"].values())
    assert doc["mean_difference"] == 4.0
    assert sorted(p.name for p in tmp_path.glob("*.png")) == ["compare-FramePool.png", "compare-PrintWindow.png"]


# the lane (D14)
def ticket_in(qdir, name, pid=None):
    qdir.mkdir(parents=True, exist_ok=True)
    p = queue.Ticket(str(len(list(qdir.glob("*.ticket"))) + 1).zfill(3), str(pid or 1), name).path(qdir)
    p.write_text(json.dumps({"cmd": "x", "start": None}), encoding="utf-8")
    return p


def test_the_tool_runs_only_under_the_ticket_that_holds_the_emulator_lane(tmp_path):
    emulator = tmp_path / "emulator"
    mine = ticket_in(emulator, "pc-shots")
    assert ps.lane_trouble({queue.TICKET_ENV: str(mine)}, emulator, is_alive=lambda pid, start: True) is None


@pytest.mark.parametrize("setup, why", [
    (lambda tmp: {}, "not run under"),
    (lambda tmp: {queue.TICKET_ENV: str(ticket_in(tmp / "bench", "pc-shots"))}, "not the emulator lane's"),
    (lambda tmp: (ticket_in(tmp / "emulator", "live-test"),
                  {queue.TICKET_ENV: str(ticket_in(tmp / "emulator", "pc-shots"))})[1], "does not hold"),
])
def test_without_the_emulator_lane_the_tool_says_why_and_does_nothing(tmp_path, setup, why):
    env = setup(tmp_path)
    assert why in ps.lane_trouble(env, tmp_path / "emulator", is_alive=lambda pid, start: True)


def test_a_command_on_the_window_without_the_lane_touches_no_window(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(queue.TICKET_ENV, raising=False)
    monkeypatch.setattr(ps, "Win32Desk", lambda: pytest.fail("a window was looked at"))
    assert ps.main(["watch", "--method", "framepool", "--out", str(tmp_path)]) == 1
    assert "emulator lane" in capsys.readouterr().out


# the identity masks (D15)
def test_masking_is_refused_while_the_pc_identity_regions_are_not_measured(tmp_path, capsys):
    assert ps.IDENTITY is None  # measured on the first PC shots of stage 1; nothing guesses them
    Image.new("RGB", (1920, 1080), (200, 200, 200)).save(tmp_path / "shot-0001.png")
    assert ps.main(["mask", str(tmp_path), str(tmp_path / "masked")]) == 1
    assert "not measured" in capsys.readouterr().out and not (tmp_path / "masked").exists()


def test_once_measured_every_region_is_blacked_out_at_the_shots_own_size(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "IDENTITY", {"uid": (100, 200, 300, 40)})  # at 1920x1080
    Image.new("RGB", (1280, 720), (200, 200, 200)).save(tmp_path / "shot-0001.png")
    assert ps.main(["mask", str(tmp_path), str(tmp_path / "masked")]) == 0
    out = np.asarray(Image.open(tmp_path / "masked" / "shot-0001.png"))
    assert out[134:160, 67:266].max() == 0 and out[132, 67].min() == 200 and out[134, 267].min() == 200
