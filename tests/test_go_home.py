"""GoHome (#365, spec 00 daily tasks): back to the main window from wherever the last task left the game.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen, taps and the back key
that move between them, and `dumpsys window` for the front package.
"""

import json
import time
from unittest.mock import MagicMock

import numpy as np
import pytest
from daily_child import (GAME, ROOT, bind, game_class, inside, interface as interface_json, load, result, run_child, run_task,
                         screen)
from agent_patch import rebind
import recovery
from recovery import L2_SCREENS
from test_pipeline import load_nodes, strip

HOLD = 0.5  # s: how long the child holds the stop task that an account-level stop queues behind its task
WINDOW_TAB = (790, 608, 70, 64)  # the bottom tab bar's Window tab
MAILBOX_CLOSE = (690, 530, 175, 45)
SETTINGS_RETURN = (500, 370, 280, 45)
TITLE_TAP = (540, 300, 200, 120)
# The mirror's map and its Dungeon Progress panel (#958), measured on tests/screens/MirrorMap.png, ProgressPanel.png
# and PauseExploration.png: the map's gear, the panel's To Window and Forfeit, Pause Exploration's Confirm.
MAP_GEAR = (1210, 22, 45, 45)
TO_WINDOW = (696, 373, 83, 125)
FORFEIT = (500, 373, 83, 125)
PAUSE_CONFIRM = (652, 470, 218, 38)
# Every capture of tests/screens the map template reads (HomeMirror, #958): the map, and what opens over it with the
# map's buttons still reading. MapNodePanel.png is not one: the node panel hides them.
MAP_SCREENS = {
    "MirrorMap.png", "MapBoss.png", "MapBossCost500.png", "MapBossDarkAfterShop.png", "MapCards.png", "MapCostFloor3.png",
    "MapCostFloor4.png", "MapCostHard85.png", "MapEvent.png", "MapFloor4.png", "MapFloor4Panned.png", "MapFloor5Shop.png",
    "MapFloor5ShopAgain.png", "MapFocused.png", "MapHardF5Warn.png", "MapHardRest.synthetic.png",
    "MapHardTwoColsMidDown.png", "MapHardTwoColsUp.png", "MapHardTwoColsUpOnly.png", "MapPanned.png", "MapRock.png",
    "MapShop.png", "MapZoomed.png",
    # over the map: Dungeon Progress (the back key, the gear), its Forfeit and Pause Exploration dialogs, a GET! window,
    # the Hidden Battle window and the prompts after floors 5 and 10
    "DungeonProgress.png", "DungeonProgressNormal.png", "ProgressPanel.png", "ForfeitDialog.png", "PauseExploration.png",
    "GiftGetOverMap.png", "HiddenBattleOverMap.synthetic.png", "ParallelModePromptOverMap.png",
    "ParallelModeExtremeOverMap.synthetic.png"}

# screen name -> tests/screens image (None: black, the game is not up)
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "sinners": "SinnersTab.png", "mailbox": "Mailbox.png",
           "settings": "SettingsMenu.png", "entry": "EntryNewRun.png", "title": "Title.png", "black": None,
           "battle": "LuxBattleTurn.png", "event": "LuxEventStory.png", "pressed": "WindowTabPressed.png",
           "rooted": "RootWarning.png", "map": "MirrorMap.png", "panel": "ProgressPanel.png",
           "pause": "PauseExploration.png"}
# where a tap moves: (screens it works on, its box, the screen it shows)
TAPS = [(("drive", "sinners"), WINDOW_TAB, "main"), (("mailbox",), MAILBOX_CLOSE, "main"),
        (("settings",), SETTINGS_RETURN, "main"), (("title",), TITLE_TAP, "main"), (("map",), MAP_GEAR, "panel"),
        (("panel",), TO_WINDOW, "pause"), (("pause",), PAUSE_CONFIRM, "main")]


class SleptClock:
    """The agent's time module during a GoHome scenario not in WALL (#677): its sleeps are real, so the agent keeps
    MaaFramework's pace, but its monotonic() moves only by what it slept. A screenshot or a recognition that a busy CI
    machine makes slow takes no time on this clock, so the waits the agent logs, how many looks a wait's timeout allows,
    and the model's back_lag read the same on any machine: a fixed 2 s sleep still shows 2 s, a wait for a screen that
    comes after 0.8 s of polling shows 0.8 s. A loop that reads monotonic() without sleeping would never end on it;
    the agent's waits (until()) sleep between looks. MaaFramework's own waits (a node's timeout) stay on the real clock."""

    def __init__(self):
        self.now = time.monotonic()  # from the real clock's reading: what the agent kept before compares as before

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        time.sleep(seconds)
        self.now += seconds

    def __getattr__(self, name):  # time(), strftime() ...: the real module's
        return getattr(time, name)


# The GoHome scenarios whose back key changes nothing keep the real clock: each of their waits runs out, and on a
# SleptClock it would last its timeout in sleeps alone, its screenshots on top. Their tests count keys, not seconds.
WALL = ("stuck", "restart", "restarts_used", "event", "rooted_restart")


def child():
    """Run GoHome from each start, and a daily task's own steps that run it (go_home, #514); print one JSON line
    {scenario: {succeeded, nodes, clicks, keys, starts ...}}."""
    from maa.custom_action import CustomAction
    from maa.event_sink import NotificationType
    from maa.tasker import TaskerEventSink

    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) if png else np.zeros((720, 1280, 3), np.uint8) for name, png in SCREENS.items()}

        def set(self, start, focus=GAME, lag=0, splash=0, press=0, back_lag=0.0):
            self.screen, self.focus, self.clicks, self.keys, self.starts, self.stops = start, focus, [], [], 0, 0
            self.lag, self.splash, self.pending = lag, splash, None  # lag: screenshots a tap's screen takes to show
            self.press = press  # screenshots the Drive page shows the tapped Window tab glowing before the main window
            self.back_lag, self.back_at = back_lag, None  # back_lag: s of black after the entry page's back key

        def screencap(self):
            if self.back_at is not None and actions.time.monotonic() >= self.back_at:
                self.screen, self.back_at = "drive", None
            if self.pending:
                self.pending[1] -= 1
                if self.pending[1] < 0:
                    self.screen, self.pending = self.pending[0], None
            if self.focus == GAME and self.screen == "title" and self.splash > 0:  # the game's start, before its title
                self.splash -= 1
                return self.images["black"]
            return self.images["black" if self.focus != GAME else self.screen]

        def on_tap(self, x, y):
            to = next((to for on, box, to in TAPS if self.screen in on and inside(box, x, y)), self.screen)
            if self.press and self.screen == "drive" and to == "main":
                self.screen, self.pending = "pressed", [to, self.press]
            elif self.lag and to != self.screen:
                self.pending = [to, self.lag]
            else:
                self.screen = to
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen in ("map", "panel"):  # live (spec 06): the map's back key opens and closes the panel
                self.screen = "panel" if self.screen == "map" else "map"
            if keycode == 4 and self.screen == "entry":  # the entry page's back: the Drive tab
                if self.back_lag:
                    self.screen, self.back_at = "black", actions.time.monotonic() + self.back_lag
                else:
                    self.screen = "drive"
            return True

        def start_app(self, intent):
            self.starts += 1
            self.focus, self.screen = GAME, "title"
            return True

        def stop_app(self, intent):
            self.stops += 1
            self.focus = "com.android.launcher"
            return True

    game = Game()
    game.set("main")
    # MaaFramework's Linux build (CI) does not pass post_shell to a custom controller ("Shell is not supported for this
    # controller type"), so foreground() reads None there and GameAway never hits: read the model's dumpsys directly.
    rebind("foreground", lambda context: recovery.focused_package(game.shell("dumpsys window", 0)))
    tasker = bind(resource, game)

    class HoldsTheStop(TaskerEventSink):
        """Holds the task Tasker::post_stop queues behind an account-level stop (MaaTaskerPostStop) for HOLD s: the
        tasker is still stopping when the next scenario comes, as on CI 2026-11-08 (#564)."""
        held = 0

        def on_tasker_task(self, tasker, noti_type, detail):
            if noti_type == NotificationType.Starting and detail.entry == "MaaTaskerPostStop":
                time.sleep(HOLD)
                self.held += 1

    holder = HoldsTheStop()
    tasker.add_sink(holder)
    out = {"error": None}
    def sweep(context):  # #958: every capture HomeMirror's recognition hits, read by MaaFramework itself
        shots = sorted(p.name for p in (ROOT / "tests" / "screens").glob("*.png"))
        return [name for name in shots if actions.seen(context, screen(name), "HomeMirror") is not None]

    calls = {"go_home": actions.go_home, "finish": lambda context: actions.finish(context, "nothing left"), "sweep": sweep}
    returned = {}

    class RunsGoHome(CustomAction):
        def run(self, context, argv):
            returned["value"] = calls[json.loads(argv.custom_action_param)](context)
            return True

    resource.register_custom_action("RunsGoHome", RunsGoHome())
    actions.RUN["lux"] = {"name": "Thread Luxcavation", "mode": "daily"}
    actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
    for scenario, (start, entry, call) in {
        "go_home_main": ("main", "RunsGoHome", "go_home"), "go_home_battle": ("battle", "RunsGoHome", "go_home"),
        "finish_battle": ("battle", "RunsGoHome", "finish"), "lux_home_battle": ("battle", "ThreadHome", None),
        "sweep": ("main", "RunsGoHome", "sweep"),
    }.items():
        game.set(start)
        returned.clear()
        actions.LOG.clear()
        stops = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        override = {"RunsGoHome": {"action": "Custom", "custom_action": "RunsGoHome", "custom_action_param": call},
                    "ThreadHome": {"next": []}}
        detail = run_task(tasker, scenario, entry, override)
        out[scenario] = {**result(detail, game, actions), "returned": returned.get("value"), "log": list(actions.LOG),
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stops,
                         "halted": actions.STUCK["halted"]}
        actions.STUCK["halted"] = None
    actions.RUN.clear()
    for scenario, (start, focus, *model) in {
        "drive": ("drive", GAME), "sinners": ("sinners", GAME), "main": ("main", GAME), "mailbox": ("mailbox", GAME),
        "settings": ("settings", GAME), "entry": ("entry", GAME), "closed": ("black", "com.android.launcher"),
        # the entry page's back key: 0.8 s of a screen GoHome knows nothing of before the Drive page (#58), on the
        # agent's SleptClock, so a busy CI machine's slow glances do not stretch it (#677)
        "entry_slow": ("entry", GAME, 0, 0, 0, 0.8),
        # the Window tab's page shows 4 screenshots after the tap; the game shows black for 15 before its title
        "drive_late": ("drive", GAME, 4), "closed_slow": ("black", "com.android.launcher", 0, 15),
        # the tapped Window tab glows on the Drive page for 2 screenshots before the main window (#496)
        "drive_pressed": ("drive", GAME, 0, 0, 2),
        # the Mailbox closes 3 screenshots after its Close (#258)
        "mailbox_late": ("mailbox", GAME, 3),
        # #958: the list stopped mid-run and started again on the mirror's map, or on its Dungeon Progress panel
        "mirror_map": ("map", GAME), "mirror_panel": ("panel", GAME),
        # these last: they change the model's methods
        "stuck": ("entry", GAME), "restart": ("entry", GAME), "restarts_used": ("entry", GAME), "event": ("event", GAME),
        # the Window tab shows its tap but the page never changes: tapped up to its limit (the taps stay ignored after it)
        "tab_stuck": ("drive", GAME),
        # the same, with a game restart left: the restarted game opens on the Drive page and takes the Window tab's tap again
        "tab_restart": ("drive", GAME),
        # #648: root on in the emulator. Each start of the game brings the Warning [50025] window: GoHome's own start, a
        # restart (L3) from a page the back key does not leave, and the window already up; each ends the list (post_stop)
        "rooted": ("black", "com.android.launcher"), "rooted_restart": ("entry", GAME), "rooted_up": ("rooted", GAME),
        # J2 (live 2026-10-28): the last task stopped mid-battle; it ends the task list (post_stop): last
        "battle": ("battle", GAME),
    }.items():
        game.set(start, focus, *model)
        if scenario in ("stuck", "restart", "restarts_used"):  # the back key does nothing: pressed up to its limit
            game.on_key = lambda keycode: True
        if scenario == "restart":  # the restarted game works again, and its title opens on a page with no tab bar
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "on_key", Game.on_key.__get__(game)))[0]
            game.on_tap = lambda x, y, game=game: (setattr(game, "screen", "entry") if game.screen == "title" else Game.on_tap(game, x, y)) or True
        # stuck: the restarts in a row that L3 allows were used up before; restart: none were.
        in_a_row = 0 if scenario in ("restart", "tab_restart", "rooted_restart") else recovery.L3_FAILED_IN_A_ROW
        actions.ROOT.joinpath("logs").mkdir(exist_ok=True)
        stops = len(list(actions.ROOT.joinpath("logs").rglob("agent.log")))
        override = {"GoHome": {"timeout": 4000}}
        if scenario in ("tab_stuck", "tab_restart"):  # the tab's tap is ignored; its wait cut short
            game.on_tap = lambda x, y: True
            override["GoHome"]["timeout"] = 8000
            override["HomeWindowTab"] = {"custom_action_param": {"until": "HomeReached", "timeout": 0.1}}
        if scenario in ("tab_restart", "restarts_used"):  # no title after the restart: its 180 s wait cut short
            override["RecoverStartApp"] = {"timeout": 3000}
        if scenario == "tab_restart":
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "screen", "drive"),
                                                        setattr(game, "on_tap", Game.on_tap.__get__(game)))[0]
        if scenario == "restarts_used":  # one restart left, and the restarted game is as stuck as before
            in_a_row = recovery.L3_FAILED_IN_A_ROW - 1
            game.start_app = lambda intent, game=game: (setattr(game, "focus", GAME), setattr(game, "screen", "entry"), True)[-1]
        if scenario.startswith("rooted"):  # the warning after every start; the back key does nothing
            game.on_key = lambda keycode: True
            game.start_app = lambda intent, game=game: (Game.start_app(game, intent), setattr(game, "screen", "rooted"))[0]
            override["RecoverStartApp"] = {"timeout": 3000}
        actions.STUCK["restarts"] = recovery.Restarts()
        for _ in range(in_a_row):
            actions.STUCK["restarts"].attempt(None)
        actions.LOG.clear()
        clock = time if scenario in WALL else SleptClock()
        rebind("time", clock)
        began = clock.monotonic()
        try:
            detail = run_task(tasker, scenario, "GoHome", override)
        finally:
            rebind("time", time)
        out[scenario] = {**result(detail, game, actions), "starts": game.starts,
                         "seconds": clock.monotonic() - began, "log": list(actions.LOG),
                         "stops": game.stops, "in_a_row": actions.STUCK["restarts"].in_a_row,
                         "stopped": len(list(actions.ROOT.joinpath("logs").rglob("agent.log"))) - stops,
                         "halted": actions.STUCK["halted"]}
        actions.STUCK["halted"] = None
    out["held"] = holder.held
    print(json.dumps(out))


def test_go_home_reaches_the_main_window_from_each_start():
    out = run_child(__file__)
    for name in ("drive", "sinners"):  # the tab bar is up with another tab open: tap Window, no back key
        o = out[name]
        assert o["succeeded"] and o["keys"] == [] and o["nodes"][-1] == "HomeReached", name
        assert len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]), name
    # Already home: nothing is pressed.
    assert out["main"]["succeeded"] and out["main"]["clicks"] == [] and out["main"]["keys"] == []
    # A popup over the main window comes first, even though the Window tab still shows lit under the settings menu.
    assert out["mailbox"]["succeeded"] and len(out["mailbox"]["clicks"]) == 1
    assert inside(MAILBOX_CLOSE, *out["mailbox"]["clicks"][0]) and out["mailbox"]["nodes"][-1] == "HomeReached"
    assert out["settings"]["succeeded"] and "SettingsMenu" in out["settings"]["nodes"]
    # A Mailbox slow to close is waited for until the main window shows (#258): a 1.5 s sleep took no screenshot, so the
    # look after it still saw the box and pressed Close again.
    o = out["mailbox_late"]
    assert o["succeeded"] and len(o["clicks"]) == 1 and o["keys"] == [] and o["nodes"][-1] == "HomeReached", o
    # A page with no tab bar: the back key, then the tab.
    assert out["entry"]["succeeded"] and out["entry"]["keys"] == [4] and len(out["entry"]["clicks"]) == 1


def test_the_back_key_waits_for_a_screen_go_home_knows_not_a_fixed_2_s():
    # #58: HomeBack slept 2 s after the key whatever came. It waits for the next screen GoHome knows now, at most those
    # 2 s; one that comes within them gets no second back key, and the wait ends when it comes. The waits read on the
    # agent's SleptClock (#677): the Drive page comes 0.8 s after the key, and the next look, 0.2 s on at most, sees it.
    o = run_child(__file__)["entry_slow"]
    assert o["succeeded"] and o["keys"] == [4] and len(o["clicks"]) == 1 and o["nodes"][-1] == "HomeReached", json.dumps(o)
    waits = [float(line.split("after ")[1].split(" s")[0]) for line in o["log"] if "HomeBack: screen changed after" in line]
    assert len(waits) == 1 and 0.8 <= waits[0] <= 1.0, json.dumps(o)
    o = run_child(__file__)["entry"]
    assert any("HomeBack: screen changed after" in line for line in o["log"]), json.dumps(o)  # within the 2 s


def test_go_home_starts_the_game_when_it_is_not_in_front_and_taps_through_the_title():
    o = run_child(__file__)["closed"]
    assert o["succeeded"] and o["starts"] == 1 and o["keys"] == []
    assert "HomeGameAway" in o["nodes"] and "NavTitle" in o["nodes"] and o["nodes"][-1] == "HomeReached"


def test_go_home_waits_for_the_screens_not_for_fixed_delays():
    # #362: the Window tab's tap waits until the main window shows (#496), so a page that comes late is not tapped twice;
    # the game's start waits for its title, not 10 s.
    o = run_child(__file__)["drive_late"]
    assert o["succeeded"] and len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]) and o["keys"] == []
    o = run_child(__file__)["closed_slow"]
    assert o["succeeded"] and o["starts"] == 1 and "GoHomeLost" not in o["nodes"] and "HomeGameUp" in o["nodes"]
    assert "NavTitle" in o["nodes"] and o["nodes"][-1] == "HomeReached"
    # A fixed wait in the agent's own steps, on its SleptClock (#677): what it slept, not how slow the machine is. The
    # child runs every node's post_delay at 0 (#480), so HomeGameAway's old 10 s one is test_pipeline.py's to catch.
    assert run_child(__file__)["closed"]["seconds"] < 10


def test_go_home_presses_no_back_key_while_the_tapped_window_tab_glows_on_the_old_page():
    # #496: 13 of 18 live Window tab taps since #375 were followed by a back key and its 2 s. The tapped tab glows on
    # the Drive page before the main window shows, 0.23 and 0.37 s on the 2 taps of a daily task's recording
    # (WindowTabPressed.png is a frame of it); neither tab template reads the glow, so GoHome's next look found nothing
    # it knew.
    o = run_child(__file__)["drive_pressed"]
    assert o["succeeded"] and o["keys"] == [] and o["nodes"][-1] == "HomeReached", o
    assert len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]), o


def test_go_home_fails_after_a_limited_number_of_back_keys_when_the_game_restarts_are_used_up():
    o = run_child(__file__)["stuck"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5 and o["stops"] == 0
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1  # the stop procedure ran: evidence and its log


def test_go_home_that_cannot_reach_the_main_window_restarts_the_game_and_goes_again():
    # D4 (#362): L3 within its limit per bot launch, then GoHome from the title. The back key's limit starts over:
    # the restarted game's page with no tab bar takes one more.
    o = run_child(__file__)["restart"]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and o["stopped"] == 0
    assert (o["stops"], o["starts"], o["in_a_row"]) == (1, 1, 1)
    assert o["keys"] == [4] * 6 and "GoHomeLost" in o["nodes"] and "NavTitle" in o["nodes"]


def test_go_home_stops_once_the_last_restart_did_not_help():
    o = run_child(__file__)["restarts_used"]
    assert o["succeeded"] is False and o["stops"] == 1 and o["in_a_row"] == 3 and o["stopped"] == 1
    assert o["nodes"].count("GoHomeLost") == 2


def test_go_home_in_a_battle_ends_the_task_list_without_a_back_key():
    # J2 (live 2026-10-28): in a battle the back key opens the pause menu, Give Up one tap away. Nothing is pressed: the
    # stop procedure, and the rest of the list goes, as after an account-level stop, for the user to end it by hand.
    o = run_child(__file__)["battle"]
    # MaaFramework ends a task that stopped its tasker as succeeded; without the stop, Halt's False fails it (#461). A red
    # prints the whole outcome (a string message: pytest cuts a dict short).
    assert o["succeeded"] is True and o["nodes"][-1] == "HomeInBattle" and o["keys"] == [] and o["clicks"] == [], json.dumps(o)
    assert o["stopped"] == 1 and o["halted"].startswith("HomeInBattle: "), json.dumps(o)


def test_go_home_into_the_root_warning_ends_the_task_list_and_restarts_nothing_more():
    # #648: live, three L3 in a row ran and failed. The first look at the window stops: after GoHome's own start of the
    # game, inside an L3, and with the window already up (GoHome's HomeText).
    for name, starts, stops in (("rooted", 1, 0), ("rooted_restart", 1, 1), ("rooted_up", 0, 0)):
        o = run_child(__file__)[name]
        assert (o["starts"], o["stops"], o["stopped"], o["clicks"]) == (starts, stops, 1, []), f"{name}: {json.dumps(o)}"
        assert (o["halted"] or "").startswith("DeviceRooted: ") and "root" in o["halted"], f"{name}: {json.dumps(o)}"
        assert any("stop code: DeviceRooted" in line for line in o["log"]), f"{name}: {json.dumps(o)}"


def test_a_task_step_that_runs_go_home_hears_whether_the_main_window_was_reached():
    # #514: MaaFramework ends a sub-task that stopped its tasker as succeeded, so GoHome halted in a battle read as home.
    o = run_child(__file__)["go_home_main"]
    assert o["returned"] is True and o["keys"] == [] and o["clicks"] == [] and o["stopped"] == 0, json.dumps(o)
    o = run_child(__file__)["go_home_battle"]
    assert o["returned"] is False and o["halted"].startswith("HomeInBattle: ") and o["stopped"] == 1, json.dumps(o)


def test_a_scenario_after_an_account_level_stop_posts_once_the_tasker_has_stopped():
    # #564: MaaFramework ignores a post while the tasker still stops (task id 0, no detail); on CI 2026-11-08 the
    # scenario after finish_battle posted while its stop task still ran, and the child died on the missing detail.
    # go_home_battle, finish_battle, lux_home_battle, the three rooted ones and battle each end in an account-level stop
    # whose stop task the child holds, and the scenario after each but the last ran.
    out = run_child(__file__)
    assert out["held"] == 7, out["held"]
    assert out["finish_battle"]["nodes"] and out["lux_home_battle"]["nodes"] and out["drive"]["nodes"], json.dumps(out)


def test_finish_on_a_battle_records_no_done_after_the_stop():
    o = run_child(__file__)["finish_battle"]
    assert o["returned"] is False and o["done"] is None and o["stopped"] == 1, json.dumps(o)


def test_lux_home_on_a_battle_stops_once_and_reads_no_modules():
    o = run_child(__file__)["lux_home_battle"]
    assert o["nodes"] == ["ThreadHome"] and o["stopped"] == 1 and o["halted"].startswith("HomeInBattle: "), json.dumps(o)
    assert not any("Modules" in line for line in o["log"]), json.dumps(o)


def test_go_home_on_an_event_page_presses_back_then_restarts_the_game():
    # The user (2026-10-28): the event screens of Luxcavation and the mirror look the same, so no screen reading tells
    # them apart; an event page gets the old way, the back key (5 times, live: the story page did not change), then L3.
    # The restarts are used up here: L3 runs the stop procedure, and the list is not ended.
    o = run_child(__file__)["event"]
    assert o["succeeded"] is False and o["keys"] == [4] * 5 and o["clicks"] == []
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1 and o["halted"] is None, o


def test_a_back_key_that_brings_no_screen_go_home_knows_says_so():
    # #958: the log said `HomeBack: no change after 2.4 s` while the map's back key opened and closed the panel: the
    # screen changed, only into none GoHome knows.
    lines = [line for line in run_child(__file__)["event"]["log"] if " HomeBack: " in line and " after " in line]
    assert len(lines) == 5 and all("no screen GoHome knows after" in line for line in lines), lines


def test_go_home_taps_a_window_tab_that_does_not_open_its_page_only_a_limited_number_of_times():
    # Review of #375: HomeWindowTab had no limit, so a tab that showed its tap but never changed the page was tapped
    # until the end of time (a JumpBack gives GoHome a fresh timeout each time). 10 taps, then GoHomeLost's L3.
    o = run_child(__file__)["tab_stuck"]
    assert o["succeeded"] is False and len(o["clicks"]) == 10 and all(inside(WINDOW_TAB, *c) for c in o["clicks"]), o
    assert o["nodes"][-1] == "GoHomeLost" and o["stopped"] == 1, o


def test_go_home_taps_the_window_tab_again_after_the_game_restarted():
    # Review of #375: L3 cleared HomeBack's and HomeGameAway's hit counts but not HomeWindowTab's, so a task that used its
    # 10 taps could not tap the restarted game's Window tab at all.
    o = run_child(__file__)["tab_restart"]
    assert o["succeeded"] and o["in_a_row"] == 1 and "GoHomeLost" in o["nodes"], o
    assert len(o["clicks"]) == 11 and all(inside(WINDOW_TAB, *c) for c in o["clicks"]), o


@pytest.mark.parametrize("name, taps", [("mirror_map", [MAP_GEAR, TO_WINDOW, PAUSE_CONFIRM]),
                                         ("mirror_panel", [TO_WINDOW, PAUSE_CONFIRM])])
def test_go_home_on_the_mirrors_map_pauses_the_run_without_a_restart(name, taps):
    # #958 (live 2026-11-25): the list stopped mid-run and started again on the map. The map's back key only opens and
    # closes Dungeon Progress (spec 06), so GoHome's 5 back keys went open, close, open, close, open, then its L3. Now
    # L2's way out: the gear (on the map), To Window, Pause Exploration's Confirm, and the main window with the run paused
    # for the list's MirrorDungeon task to Resume. No back key, no restart, never Forfeit. The restarts in a row are used
    # up here (as in every scenario but the restart ones): an L3 would have run the stop procedure.
    o = run_child(__file__)[name]
    assert o["succeeded"] and o["nodes"][-1] == "HomeReached" and "HomeMirror" in o["nodes"], json.dumps(o)
    assert (o["keys"], o["starts"], o["stops"], o["stopped"]) == ([], 0, 0, 0), json.dumps(o)
    assert len(o["clicks"]) == len(taps) and all(inside(box, *c) for box, c in zip(taps, o["clicks"])), json.dumps(o)
    assert not any(inside(FORFEIT, *c) for c in o["clicks"]), json.dumps(o)
    assert any("HomeMirror: run paused" in line for line in o["log"]), json.dumps(o)


def test_go_home_pauses_the_run_the_way_l2_does_and_reads_no_ocr_of_its_own():
    # #958: one way out of the map, L2's (RecoverL2), not a second one. The map template alone: it reads under the open
    # panel too (maatools.config.mts: DungeonProgress.png, ProgressPanel.png), and GoHome's next lists no OCR (#365).
    nodes = load_nodes()
    node = nodes["HomeMirror"]
    assert node["recognition"] == "Or" and node["any_of"] == ["MirrorMap"] and set(node["any_of"]) <= L2_SCREENS
    assert nodes["MirrorMap"]["recognition"] == "TemplateMatch"
    assert node["custom_action"] == "HomeMirror" and node["max_hit"] == 2
    hub = strip(nodes["GoHome"]["next"])
    assert hub.index("HomeInBattle") < hub.index("HomeMirror") < hub.index("HomeBack")


def test_home_mirror_hits_the_map_and_what_opens_over_it_and_nothing_else():
    # #958: every capture of tests/screens (247 on 2026-11-27) through MaaFramework and the agent's seen(): 32 hits, the
    # map and what opens over it (MAP_SCREENS); no page of the main window, the entry page, a battle, an event, the shop
    # or the theme packs.
    hits = run_child(__file__)["sweep"]["returned"]
    assert set(hits) == MAP_SCREENS, f"hits not listed: {set(hits) - MAP_SCREENS}; listed, missed: {MAP_SCREENS - set(hits)}"


def test_a_restart_lets_go_home_use_each_of_its_limited_nodes_afresh(monkeypatch):
    # Review of #375: L3 clears the hit counts of GoHome's nodes that have a max_hit, or the restarted game could not use
    # them; HomeMirror (#958) is one of them.
    import actions

    nodes = load_nodes()
    limited = {n for n in strip(nodes["GoHome"]["next"]) if "max_hit" in nodes[n]}
    context = MagicMock()
    context.run_task.return_value.status.succeeded = True
    monkeypatch.setitem(actions.STUCK, "restarts", recovery.Restarts())
    monkeypatch.setitem(actions.STUCK, "halted", None)
    monkeypatch.setattr(actions, "TASK", {})
    monkeypatch.setattr(actions, "forget_game_state", lambda: None)
    assert actions.restart_game(context, "test")
    assert {c.args[0] for c in context.clear_hit_count.call_args_list} == limited


def test_go_home_is_not_a_task_of_the_interface():  # the daily tasks run it themselves (#365); no PI entry of its own
    interface = interface_json()
    assert "GoHome" not in [t["name"] for t in interface["task"]]


if __name__ == "__main__":
    child()
