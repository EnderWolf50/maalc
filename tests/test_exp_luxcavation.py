"""ExpLuxcavation (#366): from wherever the last task left the game to the main window, Drive, Luxcavation's EXP tab
and the rightmost open stage's Enter; one battle later, back to the main window, a success. ThreadLuxcavation (#368):
the same to the Thread tab's open card, its Level Select and that list's bottom row.

The real task on the repo's resource bundle in MaaFramework 5.14.3, as test_go_home.py: a screenshot per screen, taps
and the back key that move between them. The pages after Enter (team, formation, battle, results) have no capture
yet: the model plays them as one unknown screen that gives way to the EXP tab again. The task runs in a child process
(this file run as a script): the pytest process holds MaaFramework in AgentServer mode.
"""

import functools
import json
import subprocess
import sys
import tempfile
import traceback
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

GAME = "com.ProjectMoon.LimbusCompany"
WINDOW_TAB = (790, 608, 70, 64)
DRIVE_TAB = (930, 600, 110, 80)
LUXCAVATION = (355, 97, 190, 125)  # Drive's Luxcavation button
EXP_TAB = (68, 234, 154, 60)
THREAD_TAB = (68, 304, 154, 60)
CARD_ENTER = (293, 462, 157, 36)  # the open card's Enter (LuxThread.png: Wrath's, at the left)
LEVEL_ENTERS = [(780, 243 + 101 * i, 100, 40) for i in range(3)]  # Lv40, Lv50, Lv60 of the Level Select; the last is the hardest
ENTERS = {"exp": (1000, 455, 240, 50), "locked": (660, 455, 240, 50)}  # stage 9's Enter: the rightmost, the middle card
FIGHT_SHOTS = 4  # screenshots the pages after Enter take before the EXP tab shows again: the first of them gray, the rest VICTORY

SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "exp": "LuxExp.png", "locked": "LuxExpLocked.png",
           "thread": "LuxThread.png", "scrolled": "LuxThreadScrolled.png", "levels": "LuxThreadLevels.png", "fight": None,
           "victory": "Victory.png"}


def inside(box, x, y):
    return box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]


def child():
    """Run ExpLuxcavation from each start; print one JSON line {scenario: {succeeded, nodes, clicks, keys}}."""
    from maa.controller import CustomController
    from maa.resource import Resource
    from maa.tasker import Tasker
    from PIL import Image

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    actions.ROOT = Path(tempfile.mkdtemp())
    (actions.ROOT / "config").mkdir()
    settings = json.loads((ROOT / "tests" / "settings_cases.json").read_text(encoding="utf-8"))["valid"]
    images = {name: np.ascontiguousarray(np.array(Image.open(ROOT / "tests" / "screens" / png).convert("RGB"))[:, :, ::-1])
              if png else np.full((720, 1280, 3), 40, np.uint8) for name, png in SCREENS.items()}

    class Game(CustomController):
        """The screen the game shows and what a tap or the back key does there."""

        def set(self, screen, lux_tab="thread", after="thread"):
            self.screen, self.clicks, self.keys, self.shots, self.stage = screen, [], [], 0, "exp" if screen != "locked" else "locked"
            self.wins = True  # the battles end in VICTORY; False: they end with no victory screen
            self.lux_tab = lux_tab  # the tab Luxcavation opens on
            self.after = after  # the page a Thread battle ends on: "thread" or "levels"
            self.swipes = []

        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            if self.screen == "fight":
                self.shots += 1
                if self.shots > FIGHT_SHOTS:
                    self.screen = self.stage
                elif self.shots > 1 and self.wins:
                    return images["victory"]
            return images[self.screen]

        def click(self, x, y):
            self.clicks.append((x, y))
            s = self.screen
            if s == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif s == "main" and inside(DRIVE_TAB, x, y):
                self.screen = "drive"
            elif s == "drive" and inside(LUXCAVATION, x, y):
                self.screen = self.lux_tab  # the tab last left open
            elif s in ("thread", "scrolled") and inside(EXP_TAB, x, y):
                self.screen = self.stage
            elif s in ("exp", "locked") and inside(THREAD_TAB, x, y):
                self.screen = "thread"
            elif s == "thread" and inside(CARD_ENTER, x, y):
                self.screen = "levels"
            elif s == "levels" and inside(LEVEL_ENTERS[-1], x, y):
                self.screen, self.shots = "fight", 0
                self.stage = self.after
            elif s in ENTERS and inside(ENTERS[s], x, y):
                self.screen, self.shots = "fight", 0
            return True

        def touch_down(self, contact, x, y, pressure):
            self.down = self.last = (x, y)
            return True

        def touch_move(self, contact, x, y, pressure):
            self.last = (x, y)
            return True

        def touch_up(self, contact):
            if abs(self.last[0] - self.down[0]) < 30:
                return self.click(*self.down)
            self.swipes.append((self.down, self.last))
            if self.screen == "scrolled" and self.last[0] - self.down[0] > 300:  # the finger to the right: the left cards show
                self.screen = "thread"
            return True

        def key_down(self, keycode):
            return True

        def key_up(self, keycode):
            self.keys.append(keycode)
            if keycode == 4 and self.screen in ("exp", "locked", "thread"):
                self.screen = "drive"
            elif keycode == 4 and self.screen == "levels":  # live 2026-10-26: back closes the Level Select
                self.screen = "thread"
            return True

        def shell(self, cmd, timeout):
            return f"  mCurrentFocus=Window{{1a2b u0 {GAME}/com.unity3d.player.UnityPlayerActivity}}"

        def __getattr__(self, name):
            return lambda *args: True

    game = Game()
    game.set("main")
    game.post_connection().wait()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    for name in ("ExpStart", "ExpHome", "ExpEnter", "ThreadStart", "ThreadHome", "ThreadEnter", "ThreadLevel", "GoHomeRun", "StopTask", "DismissShot", "AcceptUpdate", "AcceptTerms", "ConfirmDownload",
                 "Halt", "TapUntil", "PlayTurn", "HoldTurn", "Victory"):
        resource.register_custom_action(name, getattr(actions, name)())
    for name in ("GameAway", "HomeText", "ExpText", "StuckFlag", "DoneFlag"):
        resource.register_custom_recognition(name, getattr(actions, name)())
    tasker = Tasker()
    tasker.bind(resource, game)

    out = {"error": None}
    # scenario: (task, start screen, team, count, battles that end in VICTORY, then for the Thread task the tab Luxcavation
    # opens on and the page a battle ends on); the main window shows 182 Modules, an EXP stage takes 3, a Thread level 2
    scenarios = {"drive": ("ExpLuxcavation", "drive", "b", 1, True), "locked": ("ExpLuxcavation", "locked", "b", 1, True),
                 "no_team": ("ExpLuxcavation", "drive", None, 1, True), "two": ("ExpLuxcavation", "drive", "b", 2, True),
                 "poor": ("ExpLuxcavation", "drive", "b", 61, True), "no_victory": ("ExpLuxcavation", "drive", "b", 1, False),
                 "thread": ("ThreadLuxcavation", "drive", "b", 1, True, "exp"),
                 "thread_on_thread": ("ThreadLuxcavation", "drive", "b", 1, True, "thread"),
                 "thread_scrolled": ("ThreadLuxcavation", "drive", "b", 1, True, "scrolled"),
                 "thread_two": ("ThreadLuxcavation", "drive", "b", 2, True, "exp"),
                 "thread_two_levels": ("ThreadLuxcavation", "drive", "b", 2, True, "exp", "levels"),
                 "thread_poor": ("ThreadLuxcavation", "drive", "b", 92, True, "exp"),
                 "thread_no_team": ("ThreadLuxcavation", "drive", None, 1, True, "exp"),
                 "thread_no_victory": ("ThreadLuxcavation", "drive", "b", 1, False, "exp")}
    for scenario, (task, screen, team, count, wins, *rest) in scenarios.items():
        opts = {"count": count, "team": team, "retries": 0}
        (actions.ROOT / "config" / "settings.json").write_text(
            json.dumps({**settings, "luxcavation": {"exp": opts, "thread": opts}}), encoding="utf-8")
        game.set(screen, *rest)
        game.wins = wins
        try:
            detail = tasker.post_task(task).wait().get()
            out[scenario] = {"succeeded": detail.status.succeeded, "nodes": [n.name for n in detail.nodes],
                             "clicks": game.clicks, "keys": game.keys, "swipes": game.swipes}
        except Exception:
            out["error"] = traceback.format_exc()
    print(json.dumps(out))


@functools.cache  # one child run (~40 s) for every test
def run_child():
    run = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def test_exp_luxcavation_goes_home_first_enters_the_rightmost_open_stage_and_ends_home():
    out = run_child()
    o = out["drive"]
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    # GoHome first (the Window tab), then Drive, Luxcavation, the EXP tab (Thread was open), stage 9's Enter
    assert [inside(box, *xy) for box, xy in zip((WINDOW_TAB, DRIVE_TAB, LUXCAVATION, EXP_TAB, ENTERS["exp"]), taps)] == [True] * 5
    assert taps.count(taps[4]) == 1  # one battle
    # Back on the EXP tab after it: done, and GoHome again (the back key, then the Window tab)
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 6
    assert o["nodes"][:3] == ["ExpLuxcavation", "ExpHome", "ExpHub"] and o["nodes"][-1] == "TaskDone"


def enters(o):
    return [xy for xy in o["clicks"] if inside(ENTERS["exp"], *xy)]


def test_count_wins_are_fought_before_it_is_done():
    o = run_child()["two"]  # #367: a win counts, and the next battle starts from the same tab
    assert o["succeeded"], o["nodes"]
    assert len(enters(o)) == 2 and o["keys"] == [4]  # two Enters, one trip home at the end


def test_modules_short_of_count_times_the_cost_skip_the_task_a_success_before_any_battle():
    # 61 x 3 = 183 > the 182 the main window shows: no Enter, only the way home
    o = run_child()["poor"]
    assert o["succeeded"] and enters(o) == [] and o["nodes"][-1] == "TaskDone"


def test_a_battle_with_no_victory_stops_the_task_instead_of_counting():
    # TODO(#367): a defeat sets no result yet (no capture of its screen)
    o = run_child()["no_victory"]
    assert o["succeeded"] is False and len(enters(o)) == 1


def test_exp_luxcavation_skips_a_locked_stage_on_the_right():
    o = run_child()["locked"]
    assert o["succeeded"]
    enters = [xy for xy in o["clicks"] if 440 <= xy[1] < 510]
    assert len(enters) == 1 and inside(ENTERS["locked"], *enters[0])


def test_exp_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child()["no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ExpLuxcavation"]


def test_exp_luxcavation_is_a_task_of_the_interface():
    interface = json.loads("\n".join(ln for ln in (ROOT / "assets/interface.json").read_text(encoding="utf-8").splitlines()
                                     if not ln.strip().startswith("//")))
    assert {"name": "ExpLuxcavation", "label": "$ExpLuxcavation", "entry": "ExpLuxcavation"} in interface["task"]
    assert {"name": "ThreadLuxcavation", "label": "$ThreadLuxcavation", "entry": "ThreadLuxcavation"} in interface["task"]


def level_enters(o):
    return [xy for xy in o["clicks"] if any(inside(box, *xy) for box in LEVEL_ENTERS)]


def test_thread_luxcavation_goes_home_first_taps_thread_the_open_card_and_the_bottom_level_then_ends_home():
    o = run_child()["thread"]  # #368: Luxcavation opened on the EXP tab
    assert o["succeeded"], o["nodes"]
    taps = o["clicks"]
    boxes = (WINDOW_TAB, DRIVE_TAB, LUXCAVATION, THREAD_TAB, CARD_ENTER, LEVEL_ENTERS[-1])
    assert [inside(box, *xy) for box, xy in zip(boxes, taps)] == [True] * 6
    assert len(level_enters(o)) == 1  # the hardest level only, one battle: not Lv40 or Lv50
    assert o["keys"] == [4] and inside(WINDOW_TAB, *taps[-1]) and len(taps) == 7  # GoHome again: the back key, the Window tab
    assert o["nodes"][:3] == ["ThreadLuxcavation", "ThreadHome", "ThreadHub"] and o["nodes"][-1] == "TaskDone"


def test_thread_luxcavation_on_the_thread_tab_does_not_tap_it():
    o = run_child()["thread_on_thread"]
    assert o["succeeded"], o["nodes"]
    assert not any(inside(THREAD_TAB, *xy) for xy in o["clicks"]) and len(level_enters(o)) == 1


def test_thread_luxcavation_swipes_a_tab_scrolled_away_from_its_open_card():
    o = run_child()["thread_scrolled"]  # LuxThreadScrolled.png: no Enter lit on show
    assert o["succeeded"], o["nodes"]
    assert len(o["swipes"]) == 1 and o["swipes"][0][1][0] - o["swipes"][0][0][0] > 300 and len(level_enters(o)) == 1


def test_thread_luxcavation_fights_count_wins_from_the_card_each_time():
    o = run_child()["thread_two"]
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 2 and o["keys"] == [4]


def test_thread_luxcavation_counts_a_battle_that_ends_on_the_level_select():
    o = run_child()["thread_two_levels"]  # the Level Select shows after the battle: counted once, the next battle from it
    assert o["succeeded"], o["nodes"]
    assert len(level_enters(o)) == 2 and len([xy for xy in o["clicks"] if inside(CARD_ENTER, *xy)]) == 1


def test_thread_luxcavation_skips_when_the_modules_do_not_cover_count_levels_at_2_each():
    o = run_child()["thread_poor"]  # 92 x 2 = 184 > the 182 the main window shows
    assert o["succeeded"] and level_enters(o) == [] and not any(inside(CARD_ENTER, *xy) for xy in o["clicks"])
    assert o["nodes"][-1] == "TaskDone"


def test_thread_luxcavation_with_no_team_picked_fails_before_it_taps():
    o = run_child()["thread_no_team"]
    assert o["succeeded"] is False and o["clicks"] == [] and o["nodes"] == ["ThreadLuxcavation"]


def test_a_thread_battle_with_no_victory_stops_the_task_instead_of_counting():
    o = run_child()["thread_no_victory"]
    assert o["succeeded"] is False and len(level_enters(o)) == 1


if __name__ == "__main__":
    child()
