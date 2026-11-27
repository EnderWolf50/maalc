"""The PC client (#940, spec #922 D3-D6, D10, D17) driven offline: the runner on its fake MaaFramework (test_runner's
World) with a fake desk of windows and a fake inner controller; no real window is looked at or sent anything. The PC
window controller on the real MaaFramework, wrapped around a game model, is tests/test_pc_controller.py."""

from types import SimpleNamespace

import numpy as np
import pytest
from maa.define import MaaWin32InputMethodEnum, MaaWin32ScreencapMethodEnum
from recovery import GAME, focused_package
from test_runner import TWO, Run, World

from runner import pc, protocol

HWND = 0x1234
FULL_HD = (0, 0, 1936, 1119)  # a window rect: the client area 1920x1080 and its frame (16 px wide, 39 px high)


class Desk:
    """The windows as Windows says (runner/pc.py Win32Windows): `windows` maps a handle to (class, title, Look). A
    resize keeps the frame and the top-left corner unless `fixed` (a window that will not change size); each resize and
    place is noted."""

    def __init__(self, *windows, fixed=False):
        self.windows = {hwnd: (cls, title, look) for hwnd, cls, title, look in windows}
        self.fixed, self.resized, self.placed = fixed, [], []

    def find(self):
        return [(hwnd, cls, title) for hwnd, (cls, title, _) in self.windows.items()]

    def look(self, hwnd):
        return self.windows[hwnd][2] if hwnd in self.windows else None

    def set(self, hwnd, **changes):
        cls, title, look = self.windows[hwnd]
        self.windows[hwnd] = (cls, title, pc.Look(**{**look.__dict__, **changes}))

    def gone(self, hwnd):
        self.windows.pop(hwnd)

    def resize_client(self, hwnd, width, height):
        self.resized.append((hwnd, width, height))
        look = self.look(hwnd)
        if not self.fixed:
            x, y, w, h = look.rect
            self.set(hwnd, width=width, height=height, rect=(x, y, w - look.width + width, h - look.height + height))
        return True

    def place(self, hwnd, rect):
        self.placed.append((hwnd, rect))
        if hwnd in self.windows:
            x, y, w, h = rect
            frame = self.look(hwnd)
            self.set(hwnd, rect=rect, width=w - (frame.rect[2] - frame.width), height=h - (frame.rect[3] - frame.height))
        return True


def game(width=1920, height=1080, rect=FULL_HD, **state):
    return HWND, pc.CLASS, pc.TITLE, pc.Look(width=width, height=height, rect=rect, **state)


class Done:
    """A MaaFramework job that is done: succeeded or not, with its result."""

    def __init__(self, succeeded=True, result=None):
        self.succeeded, self.result = succeeded, result

    def wait(self):
        return self

    def get(self):
        return self.result


class Inner:
    """The inner controller (MaaFramework's Win32 controller of the window): each call noted; `takes` whether it takes
    an input (False: it has no input unit, as with mouse and keyboard Null)."""

    def __init__(self, takes=True, size=(1080, 1920)):
        self.calls, self.takes, self.size = [], takes, size

    def post_connection(self):
        self.calls.append("connect")
        return Done()

    def post_screencap(self):
        self.calls.append("screencap")
        return Done(result=np.full((*self.size, 3), 128, np.uint8))

    def _input(self, *call):
        self.calls.append(call)
        return Done(self.takes)

    def post_click(self, x, y):
        return self._input("click", x, y)

    def post_swipe(self, x1, y1, x2, y2, duration):
        return self._input("swipe", x1, y1, x2, y2, duration)

    def post_touch_down(self, x, y, contact, pressure):
        return self._input("down", x, y)

    def post_touch_move(self, x, y, contact, pressure):
        return self._input("move", x, y)

    def post_touch_up(self, contact):
        return self._input("up")

    def post_click_key(self, key):
        return self._input("key", key)

    def post_key_down(self, key):
        return self._input("kd", key)

    def post_key_up(self, key):
        return self._input("ku", key)

    def post_inactive(self):
        return self._input("inactive")

    def inputs(self):
        return [c for c in self.calls if c not in ("connect", "screencap")]


class Pc(pc.Controller):
    """The PC window controller as the runner's fake MaaFramework hands it out: its connect as a job."""

    def post_connection(self):
        return Done(self.connect())


def pc_world(plan, desk, inner=None):
    """A World on desk whose PC window controller speaks through inner (a new Inner when None); world.pc the controller."""
    inner = inner or Inner()

    def make(hwnd, windows):
        world.pc = Pc(hwnd, windows, inner=lambda h: inner)
        return world.pc
    world = World(plan, desk=desk, make_pc=make)
    world.inner = inner
    return world


ONE = {"MirrorDungeon": (3, "succeeded"), "ExpLuxcavation": (2, "succeeded")}


def start(tmp_path, world, size="keep", *bot_lines, code=None):
    run = Run(tmp_path, world, *bot_lines, code=code)
    run.result = run.start(TWO, kind="pc", address=None, **({"pc_size": size} if size != "keep" else {}))
    return run


# finding the window and connecting (D3)
def test_a_pc_start_connects_to_the_one_game_window_and_runs_the_list_on_it(tmp_path):
    world = pc_world(ONE, Desk(game(), (0x99, "Notepad", "LimbusCompany", pc.Look(800, 600)),
                               (0x98, pc.CLASS, "Other", pc.Look(1920, 1080))))
    run = start(tmp_path, world)
    assert run.result == "succeeded"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "succeeded"), (1, "running"),
                            (1, "succeeded")]
    assert [(e["state"], e["address"]) for e in run.of("connection")] == [("connecting", pc.TITLE), ("connected", pc.TITLE)]
    assert world.pc.hwnd == HWND and world.inner.calls[0] == "connect"
    assert "[run] connected the LimbusCompany window 1920x1080" in run.lines("runner")
    assert world.posted == ["MirrorDungeon", "ExpLuxcavation"] and world.controllers == [] and run.launched == []
    assert not run.of("error")


@pytest.mark.parametrize("desk, kind, code, params, message", [
    (Desk(), "device_missing", "PcNoWindow", {}, "no LimbusCompany window is open"),
    (Desk(game(), (0x5678, pc.CLASS, pc.TITLE, pc.Look(1920, 1080))), "connect_failed", "PcManyWindows", {"count": 2},
     "2 LimbusCompany windows are open"),
    (Desk(game(minimized=True)), "connect_failed", "PcMinimized", {}, "the game's window is minimized"),
    (Desk(game(2904, 1677)), "connect_failed", "PcNot16By9", {"width": 2904, "height": 1677},
     "the game's client area is 2904x1677, not 16:9"),
], ids=["no window", "two windows", "minimized", "not 16:9"])
def test_a_window_the_runner_cannot_use_cancels_every_task_with_its_coded_reason(tmp_path, desk, kind, code, params, message):
    world = pc_world(ONE, desk)
    run = start(tmp_path, world)
    assert run.result == "failed"
    (error,) = run.of("error")
    assert (error["kind"], error["message"]) == (kind, message)
    assert run.states()[2:] == [(0, "cancelled", message), (1, "cancelled", message)]
    assert run.codes() == [(0, "cancelled", code, params), (1, "cancelled", code, params)]
    assert world.posted == [] and not hasattr(world, "pc")  # no controller was made, nothing was posted


def test_a_connect_that_fails_on_the_window_says_why(tmp_path):
    # minimized between the runner's look and the controller's connect: the controller's problem is the reason
    desk = Desk(game())
    world = pc_world(ONE, desk)

    def make(hwnd, windows):
        desk.set(HWND, minimized=True)
        world.pc = Pc(hwnd, windows, inner=lambda h: world.inner)
        return world.pc
    world.make_pc = make
    run = start(tmp_path, world)
    assert run.result == "failed" and run.codes()[-1] == (1, "cancelled", "PcMinimized", {})
    assert world.inner.calls == []  # the inner controller was never made to connect


# the problem the controller holds stops the run (D10)
@pytest.mark.parametrize("change, code, params, message", [
    (lambda desk: desk.gone(HWND), "PcWindowGone", {}, "the game's window is gone"),
    (lambda desk: desk.set(HWND, minimized=True), "PcMinimized", {}, "the game's window is minimized"),
    (lambda desk: desk.set(HWND, width=1600, height=1000), "PcNot16By9", {"width": 1600, "height": 1000},
     "the game's client area is 1600x1000, not 16:9"),
], ids=["gone", "minimized", "not 16:9"])
def test_a_window_that_turns_unusable_mid_run_stops_it_and_cancels_the_rest_with_its_code(tmp_path, change, code, params,
                                                                                          message):
    desk = Desk(game())
    world = pc_world({"MirrorDungeon": (100, "succeeded"), "ExpLuxcavation": (2, "succeeded")}, desk)
    world.at[1003.0] = lambda: change(desk)
    run = start(tmp_path, world)
    assert run.result == "failed"
    (error,) = run.of("error")
    assert (error["kind"], error["message"]) == ("device_lost", message)
    assert run.states()[2:] == [(0, "running"), (0, "failed", message), (1, "cancelled", message)]
    assert run.codes() == [(0, "failed", code, params), (1, "cancelled", code, params)]
    assert len(world.stops) == 1 and world.disconnected  # the runner stopped MaaFramework once, and closed the bot


def test_a_problem_after_the_first_task_leaves_that_task_as_it_ended(tmp_path):
    desk = Desk(game())
    world = pc_world({"MirrorDungeon": (2, "succeeded"), "ExpLuxcavation": (100, "succeeded")}, desk)
    world.at[1004.0] = lambda: desk.gone(HWND)
    run = start(tmp_path, world)
    assert run.states()[2:] == [(0, "running"), (0, "succeeded"), (1, "running"), (1, "failed", "the game's window is gone")]


def test_a_stop_of_the_caller_ends_a_pc_run_stopped_with_no_reason(tmp_path):
    world = pc_world({"MirrorDungeon": (100, "succeeded"), "ExpLuxcavation": (2, "succeeded")}, Desk(game()))
    run = Run(tmp_path, world)
    run.stop_at(1003.0)
    assert run.start(TWO, kind="pc") == "stopped"
    assert run.states()[2:] == [(0, "running"), (0, "stopped"), (1, "cancelled")] and run.codes() == []


# the guard (D5): no call of the inner controller on a window that cannot be used
def connected(desk, inner=None):
    ctl = Pc(HWND, desk, inner=lambda h: inner or Inner())
    assert ctl.connect() and ctl.problem is None
    return ctl


def test_a_minimized_window_gets_no_screencap_of_the_inner_controller_and_a_black_frame():
    desk, inner = Desk(game()), Inner()
    ctl = connected(desk, inner)
    assert ctl.screencap().mean() == 128 and inner.calls == ["connect", "screencap"]
    desk.set(HWND, minimized=True)
    frame = ctl.screencap()
    assert inner.calls.count("screencap") == 1  # none while minimized
    assert frame.shape == (1080, 1920, 3) and not frame.any()
    assert ctl.problem == pc.Problem("PcMinimized", {}, "the game's window is minimized")


@pytest.mark.parametrize("change", [lambda d: d.set(HWND, minimized=True), lambda d: d.gone(HWND),
                                    lambda d: d.set(HWND, width=1280, height=1024)], ids=["minimized", "gone", "5:4"])
def test_a_window_that_cannot_be_used_gets_no_input_of_the_inner_controller(change):
    desk, inner = Desk(game()), Inner()
    ctl = connected(desk, inner)
    change(desk)
    calls = [ctl.touch_down(0, 10, 10, 1), ctl.touch_move(0, 12, 12, 1), ctl.touch_up(0), ctl.click(1, 1),
             ctl.swipe(1, 1, 5, 5, 200), ctl.key_down(4), ctl.key_up(4), ctl.click_key(4)]
    assert calls == [False] * 8 and inner.inputs() == [] and ctl.problem is not None


def test_the_first_problem_is_the_one_held():
    desk = Desk(game())
    ctl = connected(desk)
    desk.set(HWND, minimized=True)
    ctl.screencap()
    desk.gone(HWND)
    ctl.screencap()
    assert ctl.problem.code == "PcMinimized"


# what MaaFramework says, and what the inner controller gets (D4)
def test_touches_go_to_the_inner_controller_at_the_same_coordinates():
    inner = Inner()
    ctl = connected(Desk(game()), inner)
    assert ctl.touch_down(0, 960, 540, 1) and ctl.touch_move(0, 1000, 560, 1) and ctl.touch_up(0)
    assert ctl.click(10, 20) and ctl.swipe(1, 2, 3, 4, 300)
    assert inner.inputs() == [("down", 960, 540), ("move", 1000, 560), ("up",), ("click", 10, 20), ("swipe", 1, 2, 3, 4, 300)]


def test_back_is_esc_and_another_key_is_refused():
    inner = Inner()
    ctl = connected(Desk(game()), inner)
    assert ctl.key_down(4) and ctl.key_up(4) and ctl.click_key(4)
    assert not ctl.key_down(66) and not ctl.click_key(3) and not ctl.input_text("hello")
    assert inner.inputs() == [("kd", 27), ("ku", 27), ("key", 27)] and ctl.problem is None


def test_dumpsys_window_says_the_game_has_the_focus_while_its_window_is_there_and_none_once_it_is_gone():
    desk = Desk(game(minimized=True))
    ctl = Pc(HWND, desk, inner=lambda h: Inner())
    assert focused_package(ctl.shell("dumpsys window", 20000)) == GAME  # minimized is still there
    desk.gone(HWND)
    assert focused_package(ctl.shell("dumpsys window", 20000)) == ""
    assert ctl.problem.code == "PcWindowGone"
    assert ctl.shell("getprop ro.build.version.sdk", 20000) is None


def test_an_input_the_inner_controller_does_not_take_holds_the_input_problem():
    # mouse and keyboard Null: MaaFramework builds no input unit, so the inner controller takes no input (D6)
    ctl = connected(Desk(game()), Inner(takes=False))
    assert not ctl.touch_down(0, 960, 540, 1)
    assert ctl.problem == pc.Problem("PcInputFailed", {}, "the game's window did not take an input")


def test_starting_or_stopping_the_game_is_refused_with_its_reason():
    for call in ("start_app", "stop_app"):
        inner = Inner()
        ctl = connected(Desk(game()), inner)
        assert getattr(ctl, call)(GAME) is False
        assert ctl.problem.code == "PcRestartOff" and inner.inputs() == []


def test_the_controller_says_it_is_the_pc():
    assert Pc(HWND, Desk(game())).get_custom_info() == {"device": "pc"}


# no input (D6)
def test_the_inner_controller_is_the_background_win32_controller_with_mouse_and_keyboard_null():
    made = []

    def make(*args):
        made.append(args)
        return SimpleNamespace(set_screenshot_use_raw_size=lambda on: made.append(("raw", on)))
    pc.win32_controller(HWND, make=make)
    assert made == [(HWND, MaaWin32ScreencapMethodEnum.Background, MaaWin32InputMethodEnum.Null,
                     MaaWin32InputMethodEnum.Null), ("raw", True)]


@pytest.mark.parametrize("name", list(pc.FORBIDDEN))
@pytest.mark.parametrize("which", ["mouse", "keyboard"])
def test_each_forbidden_input_method_is_refused_before_a_controller_is_made(name, which):
    made = []
    with pytest.raises(ValueError, match=f"the {which} method {name} is forbidden"):
        pc.win32_controller(HWND, **{which: getattr(MaaWin32InputMethodEnum, name)}, make=lambda *a: made.append(a))
    assert made == []


def test_the_forbidden_methods_are_the_frameworks_by_name_and_value():
    assert pc.FORBIDDEN == {n: int(getattr(MaaWin32InputMethodEnum, n)) for n in pc.FORBIDDEN}
    assert set(pc.FORBIDDEN) == {"Seize", "LegacyEvent", "PostThreadMessage", "SendMessageWithCursorPos",
                                 "PostMessageWithCursorPos", "Interception"}
    assert pc.BACKGROUND == MaaWin32ScreencapMethodEnum.Background and pc.NULL == MaaWin32InputMethodEnum.Null


# the window's size (D17)
@pytest.mark.parametrize("size, client", [("720", (1280, 720)), ("900", (1600, 900)), ("1080", (1920, 1080)),
                                          ("1440", (2560, 1440))])
def test_a_size_sets_the_client_area_for_the_run_and_the_window_goes_back_after(tmp_path, size, client):
    rect = (100, 50, 2920, 1716)  # a 2904x1677 client area, its top-left corner at 100,50
    desk = Desk(game(2904, 1677, rect=rect))
    world = pc_world(ONE, desk)
    seen = []
    world.at[1003.0] = lambda: seen.append(desk.look(HWND))
    run = start(tmp_path, world, size)
    assert run.result == "succeeded"
    assert desk.resized == [(HWND, *client)]
    assert (seen[0].width, seen[0].height) == client and seen[0].rect[:2] == rect[:2]  # the top-left corner stayed
    assert desk.placed == [(HWND, rect)] and desk.look(HWND).rect == rect
    lines = run.lines("runner")
    assert f"[run] the game's client area 2904x1677 -> {client[0]}x{client[1]} for the run" in lines
    assert lines.index("[run] the game's window put back at 100,50 2920x1716") < lines.index("[run] end succeeded")


def test_keep_leaves_the_window_as_it_is(tmp_path):
    desk = Desk(game())
    run = start(tmp_path, pc_world(ONE, desk), "keep")
    assert run.result == "succeeded" and desk.resized == [] and desk.placed == []


def test_a_window_already_at_the_size_is_not_touched(tmp_path):
    desk = Desk(game())
    run = start(tmp_path, pc_world(ONE, desk), "1080")
    assert run.result == "succeeded" and desk.resized == [] and desk.placed == []


@pytest.mark.parametrize("state", ["fullscreen", "maximized"])
def test_a_fullscreen_or_maximized_window_keeps_its_size_and_the_log_says_why(tmp_path, state):
    desk = Desk(game(2560, 1440, rect=(0, 0, 2560, 1440), **{state: True}))
    run = start(tmp_path, pc_world(ONE, desk), "1080")
    assert run.result == "succeeded" and desk.resized == [] and desk.placed == []
    assert f"[run] the game's window is {state}: its size stays 2560x1440" in run.lines("runner")


@pytest.mark.parametrize("how", ["stopped", "failed", "bot exit"])
def test_the_window_goes_back_however_the_run_ends(tmp_path, how):
    rect = (100, 50, 2920, 1716)
    desk = Desk(game(2904, 1677, rect=rect))
    world = pc_world({"MirrorDungeon": (100, "succeeded") if how != "failed" else (2, "failed"),
                      "ExpLuxcavation": (2, "succeeded")}, desk)
    run = Run(tmp_path, world, code=3 if how == "bot exit" else None)
    if how == "stopped":
        run.stop_at(1003.0)
    result = run.start(TWO, kind="pc", pc_size="1080")
    assert result == ("stopped" if how == "stopped" else "failed")
    assert desk.placed == [(HWND, rect)] and desk.look(HWND).rect == rect


def test_a_window_that_is_not_16_9_after_the_resize_stops_the_run_and_goes_back(tmp_path):
    rect = (100, 50, 2920, 1716)
    desk = Desk(game(2904, 1677, rect=rect), fixed=True)  # the window will not change size
    world = pc_world(ONE, desk)
    run = start(tmp_path, world, "1440")
    assert run.result == "failed" and desk.resized == [(HWND, 2560, 1440)]
    assert run.codes() == [(0, "cancelled", "PcNot16By9", {"width": 2904, "height": 1677}),
                           (1, "cancelled", "PcNot16By9", {"width": 2904, "height": 1677})]
    assert desk.placed == [(HWND, rect)] and world.posted == []


def test_a_window_gone_by_the_runs_end_is_not_put_back_and_the_run_ends(tmp_path):
    desk = Desk(game(2904, 1677, rect=(100, 50, 2920, 1716)))
    world = pc_world({"MirrorDungeon": (100, "succeeded"), "ExpLuxcavation": (2, "succeeded")}, desk)
    world.at[1003.0] = lambda: desk.gone(HWND)
    run = start(tmp_path, world, "1080")
    assert run.result == "failed" and run.of("end")[-1]["result"] == "failed"


# the scan
def test_a_scan_lists_the_game_windows_beside_the_emulators(tmp_path):
    desk = Desk(game(), (0x5678, pc.CLASS, pc.TITLE, pc.Look(160, 28, minimized=True)),
                (0x99, "Notepad", "notes", pc.Look(800, 600)))
    run = Run(tmp_path, World({}, desk=desk))
    assert run.session.scan() == "succeeded"
    (listed,) = run.of("devices")
    protocol.check_event(listed)
    assert listed["windows"] == [{"title": pc.TITLE, "width": 1920, "height": 1080, "minimized": False},
                                 {"title": pc.TITLE, "width": 160, "height": 28, "minimized": True}]


def test_the_real_windows_object_finds_no_window_at_a_handle_that_is_not_one():
    # Win32Windows reads user32 (IsWindow first): a handle no window has is gone, and nothing is sent to it
    windows = pc.Win32Windows()
    assert windows.look(0x7FFFFFF0) is None
    assert windows.resize_client(0x7FFFFFF0, 1280, 720) is False and windows.place(0x7FFFFFF0, (0, 0, 1, 1)) is False


def test_16_9_is_exact():
    assert pc.trouble(pc.Look(1920, 1080)) is None and pc.trouble(pc.Look(2560, 1440)) is None
    assert pc.trouble(pc.Look(1920, 1081)).code == "PcNot16By9" and pc.trouble(pc.Look(0, 0)).code == "PcNot16By9"
