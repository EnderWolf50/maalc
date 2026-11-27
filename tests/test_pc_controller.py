"""The PC window controller (runner/pc_controller.py, #940) on the real MaaFramework 5.14.3, in a child process
(daily_child.py), wrapped around a game model of 1920x1080 as it wraps MaaFramework's Win32 controller of the game's
window: no real window is looked at or sent anything. This is the offline experiment of spec #922 F4 as a test: a
custom controller that calls another controller in its callbacks, the real ClaimMail task through it (the bot speaks to
it as to the emulator, spec D4), back as Esc, `dumpsys window` from the window, the minimize guard, and how long a
screencap takes through it."""

import json
import statistics
import sys
import time

import numpy as np
from daily_child import ROOT, bind, game_class, load, result, run_child, screen
from test_claim_mail import CLAIM_ALL, MAIL_ICON, MAILBOX_CLOSE, SCREENS, WINDOW_TAB

sys.path.insert(0, str(ROOT))  # the runner package, for the child run as a script
GAME = "com.ProjectMoon.LimbusCompany"
SCALE = 1.5  # 1920x1080 over the 1280x720 the bot sees
SHOTS = 20  # screencaps each timing takes


def mail_model():
    """test_claim_mail's game: the mailbox holds mail until Claim All. A tap in 1280x720 coordinates."""
    from daily_child import inside

    class Mail(game_class()):
        images = {name: screen(png) for name, png in SCREENS.items()}

        def set(self, start, mail=True):
            self.screen, self.mail, self.clicks, self.keys, self.raw, self.shots = start, mail, [], [], [], 0

        def on_tap(self, x, y):
            if self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif self.screen == "main" and inside(MAIL_ICON, x, y):
                self.screen = "mailbox" if self.mail else "empty"
            elif self.screen == "mailbox" and inside(CLAIM_ALL, x, y):
                self.screen, self.mail = "empty", False
            elif self.screen in ("mailbox", "empty") and inside(MAILBOX_CLOSE, x, y):
                self.screen = "main"
            return True
    return Mail


def child():
    """Print one JSON line: ClaimMail straight on the model and through the PC window controller, and what the
    controller's other answers were."""
    from maa.custom_action import CustomAction
    from PIL import Image

    from runner import pc
    from runner.pc_controller import PcController

    began = time.monotonic()
    actions, resource = load()
    Mail = mail_model()
    big = {name: np.ascontiguousarray(np.array(Image.fromarray(img[:, :, ::-1]).resize((1920, 1080)))[:, :, ::-1])
           for name, img in Mail.images.items()}

    class Window(Mail):
        """The same game as its 1920x1080 window: frames scaled up, a tap scaled back for the model; raw: the taps as
        the window got them."""

        def screencap(self):
            self.shots += 1
            return big[self.screen]

        def click(self, x, y):
            self.raw.append((x, y))
            return super().click(round(x / SCALE), round(y / SCALE))

    class Desk:
        """One game window, 1920x1080, that a test may minimize or close."""
        look = pc.Look(1920, 1080, rect=(0, 0, 1936, 1119))

        def find(self):
            return [(1, pc.CLASS, pc.TITLE)] if self.look else []

        def look_at(self, hwnd):
            return self.look

    desk = Desk()
    desk_view = type("View", (), {"find": lambda s: desk.find(), "look": lambda s, h: desk.look_at(h)})()
    out = {"error": None}

    straight = Mail()
    straight.set("main")
    out["straight"] = result(bind(resource, straight).post_task("ClaimMail", {"ClaimMailHub": {"timeout": 20000}}).wait().get(),
                             straight, actions)

    window = Window()
    window.set("main")
    made = []
    ctl = PcController(1, desk_view, inner=lambda h: made.append(h) or pc.win32_controller(h, make=lambda *a: window))
    tasker = bind(resource, ctl)  # connects it
    out["made"] = made
    out["pc"] = {**result(tasker.post_task("ClaimMail", {"ClaimMailHub": {"timeout": 20000}}).wait().get(), window, actions),
                 "raw": window.raw}

    said = {}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                window.keys = []
                actions.back(context)
                said["keys"] = list(window.keys)
                said["focus"] = actions.foreground(context)
                image = context.tasker.controller.post_screencap().wait().get()
                said["shape"] = list(image.shape)
            except Exception as e:
                said["error"] = repr(e)
            return True

    resource.register_custom_action("PcProbe", Probe())
    tasker.post_task("PcProbe", {"PcProbe": {"action": "Custom", "custom_action": "PcProbe"}}).wait()
    out["probe"], out["problem_after_probe"] = said, ctl.problem

    # how long a screencap takes through the controller (scaled to 720p) and of the model alone (raw)
    def median_ms(controller):
        times = []
        for _ in range(SHOTS):
            t = time.perf_counter()
            controller.post_screencap().wait().get()
            times.append((time.perf_counter() - t) * 1000)
        return statistics.median(times)
    out["ms"] = {"facade": median_ms(ctl), "inner": median_ms(window)}

    # minimized: no screencap of the model, a black frame, the problem held
    shots = window.shots
    desk.look = pc.Look(1920, 1080, minimized=True, rect=(0, 0, 1936, 1119))
    frame = ctl.post_screencap().wait().get()
    out["minimized"] = {"shots": window.shots - shots, "black": not frame.any(), "shape": list(frame.shape),
                        "problem": ctl.problem}

    # gone: dumpsys window says no window has the focus
    other = PcController(1, desk_view, inner=lambda h: pc.win32_controller(h, make=lambda *a: window))
    desk.look = pc.Look(1920, 1080, rect=(0, 0, 1936, 1119))
    other.post_connection().wait()
    desk.look = None
    out["gone"] = {"shell": other.post_shell("dumpsys window").wait().get(), "problem": other.problem}

    # the pipeline's StopApp (recovery.json RecoverRestart) and StartApp: refused, with their reason (#948 does them)
    third = PcController(1, desk_view, inner=lambda h: pc.win32_controller(h, make=lambda *a: window))
    desk.look = pc.Look(1920, 1080, rect=(0, 0, 1936, 1119))
    job = bind(resource, third).post_task("PcRestart", {"PcRestart": {"action": "StopApp", "package": GAME}}).wait()
    out["restart"] = {"succeeded": job.get().status.succeeded, "problem": third.problem}
    out["seconds"] = time.monotonic() - began
    print(json.dumps(out))


def test_claim_mail_runs_through_the_pc_window_controller_as_it_runs_on_the_model():
    # the bot speaks to the PC window controller as to the emulator: the same task, the same nodes and taps (spec D4)
    out = run_child(__file__)
    straight, through = out["straight"], out["pc"]
    assert straight["succeeded"] and through["succeeded"] and through["done"] == "mail claimed"
    assert through["nodes"] == straight["nodes"] and through["screen"] == "main"
    # MaaFramework taps a random point of a node's box: the same boxes, in the same order
    assert [box(c) for c in through["clicks"]] == [box(c) for c in straight["clicks"]] == ["mail icon", "claim all",
                                                                                           "close"]
    assert out["made"] == [1]  # the inner controller made once, at the connect


def box(click):
    from daily_child import inside

    boxes = {"window tab": WINDOW_TAB, "mail icon": MAIL_ICON, "claim all": CLAIM_ALL, "close": MAILBOX_CLOSE}
    return next((name for name, b in boxes.items() if inside(b, *click)), tuple(click))


def test_a_tap_reaches_the_inner_controller_in_the_windows_own_pixels():
    # the controller scales the 1920x1080 frame to 1280x720 for the bot, and a tap back: the window gets it 1:1 in its
    # own pixels (spec F4: 1920x1080 coordinates 1:1)
    through = run_child(__file__)["pc"]
    assert len(through["raw"]) == len(through["clicks"])
    for (rx, ry), (x, y) in zip(through["raw"], through["clicks"]):
        assert abs(rx - x * SCALE) <= 2 and abs(ry - y * SCALE) <= 2, (rx, ry, x, y)


def test_back_reaches_the_window_as_esc_and_dumpsys_window_names_the_game_while_its_window_is_there():
    out = run_child(__file__)
    assert out["probe"] == {"keys": [27], "focus": GAME, "shape": [720, 1280, 3]}
    assert out["problem_after_probe"] is None


def test_a_minimized_window_gets_no_screencap_through_maaframework_either():
    m = run_child(__file__)["minimized"]
    assert m["shots"] == 0 and m["black"] and m["shape"] == [720, 1280, 3]
    assert m["problem"][0] == "PcMinimized"


def test_dumpsys_window_says_no_focus_once_the_window_is_gone():
    gone = run_child(__file__)["gone"]
    assert "mCurrentFocus=null" in gone["shell"] and gone["problem"][0] == "PcWindowGone"


def test_the_pipelines_stop_of_the_game_is_refused_with_its_reason():
    restart = run_child(__file__)["restart"]
    assert not restart["succeeded"] and restart["problem"][0] == "PcRestartOff"


def test_how_long_a_screencap_takes_through_the_controller(capsys):
    # spec F4 measured about 10 ms through it and 1.8 ms for the inner one alone; printed for the PR, bounded loosely
    out = run_child(__file__)
    with capsys.disabled():
        print(f"\nPC window controller: screencap median {out['ms']['facade']:.1f} ms through it, "
              f"{out['ms']['inner']:.1f} ms inner alone ({SHOTS} each); child run {out['seconds']:.1f} s")
    assert out["ms"]["facade"] < 1000


if __name__ == "__main__":
    child()
