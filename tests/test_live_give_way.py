"""tools/live/give_way.py: a live run leaves the emulator to the daily task at a safe point of its Mirror Dungeon run (#853).

The probe runs MaaFramework, which the pytest process holds in AgentServer mode: `give_way.py look` runs in a child process,
once for every capture (as test_live_giveup.py).
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_pipeline import load_nodes

from live import give_way as gw
from live import queue as lq

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "tests/screens"

# capture -> the screen the probe must name: the map and its node panel, and what stands over the map and reads as it too
NAMED = {
    "MirrorMap.png": "MirrorMap",
    "MapFloor4Panned.png": "MirrorMap",
    "MapBoss.png": "MirrorMap",
    "MapHardTwoColsUp.png": "MirrorMap",
    "MapNodePanel.png": "MapNodePanel",
    "ParallelModePromptOverMap.png": "ParallelModePrompt",
    "ParallelModeExtremeOverMap.synthetic.png": "ExtremeModePrompt",
    "HiddenBattleOverMap.synthetic.png": "HiddenBattle",
    "GiftGetOverMap.png": "GiftGet",
    "DungeonProgress.png": "ProgressPanel",
    "ForfeitDialog.png": "ForfeitDialog",
    "MainWindow.png": "HomeReached",
    "BattleTurn.png": None,
    "Formation.png": None,
    "Shop.png": None,
}


def look_files(*options):
    done = subprocess.run([sys.executable, str(REPO / "tools/live/give_way.py"), "look", *options, "--json",
                           *(str(SCREENS / f) for f in NAMED)], capture_output=True, text=True, timeout=240, cwd=REPO)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def named():
    return look_files()


def test_a_glance_sees_the_map_and_the_panel_and_no_battle():
    # it reads through a window over the map; the whole look after the bot is suspended tells
    seen = look_files("--glance")
    assert {f: seen[f] for f in NAMED if NAMED[f] in (*gw.SAFE, None)} == {f: n for f, n in NAMED.items() if n in (*gw.SAFE, None)}
    assert seen["ParallelModePromptOverMap.png"] == "MirrorMap" and seen["MainWindow.png"] is None


@pytest.mark.parametrize("capture", list(NAMED))
def test_the_probe_tells_the_map_from_what_stands_over_it(named, capture):
    assert named[capture] == NAMED[capture]


def test_the_probe_names_only_screens_with_a_node_and_the_safe_ones_last_but_home():
    nodes = load_nodes()
    assert gw.PROBE not in nodes
    assert set(gw.SCREENS) - set(gw.giveup.DIALOG_NODES) <= set(nodes)
    assert gw.SCREENS[-3:] == (*gw.SAFE, gw.HOME)


def test_the_way_to_the_main_window_needs_no_agent():
    # the tool's own tasker runs RecoverL2, with no agent/main.py behind it
    nodes = load_nodes()
    way = ["RecoverL2", "RecoverGear", "RecoverToWindow", "RecoverPauseConfirm"]
    assert all(n in way for node in way for n in nodes[node].get("next", []))
    assert not any("custom_" in json.dumps(nodes[n]) for n in way)
    assert nodes["RecoverGear"]["any_of"] == ["MirrorMap"] and "custom_recognition" not in nodes["MirrorMap"]


def holder(name, first=False):
    return lq.Holder(name, "1", "hold", first, None)


class Game:
    """What a run shows, a clock the sleeps move, and what was done to it, in order."""

    def __init__(self, glances=(), looks=(), queue=None, runs=None, forfeit=lambda: False, to_window=True, queued=True, ends=True):
        self.glances, self.looks = list(glances), list(looks)
        self.queue = queue if queue is not None else [[holder("leg1"), holder("daily", True), holder("other")]]
        self.runs, self.forfeit, self.queued, self.ends = runs, forfeit, queued, ends
        self.did, self.said, self.now, self.ended = [], [], 0.0, False
        self.world = gw.World(
            holders=self.holders, bot_runs=self.bot_runs, forfeit_pending=forfeit, glance=lambda: self.next(self.glances),
            look=lambda: self.next(self.looks), suspend=self.suspend, end_bot=self.end_bot,
            lift_finger=lambda: self.did.append("lift"), back=lambda: self.did.append("back"),
            to_window=lambda: self.did.append("to window") or to_window, shot=lambda name: self.did.append(f"shot {name}"),
            pause=lambda minutes: self.did.append(f"pause {minutes}"), queue_next=self.queue_next,
            stop_recording=lambda: self.did.append("stop recording"), done=lambda: self.did.append("done"),
            say=self.said.append, sleep=self.sleep, clock=lambda: self.now)

    @staticmethod
    def next(values):
        return values.pop(0) if len(values) > 1 else values[0]

    def holders(self):
        return self.next(self.queue)

    def bot_runs(self):
        return not self.ended and (self.runs is None or self.now < self.runs)

    def suspend(self):
        self.did.append("suspend")
        return lambda: self.did.append("resume")

    def end_bot(self):
        self.did.append("end bot")
        if not self.ends:
            raise gw.Failed("the bot's processes [1] did not end")
        self.ended = True

    def queue_next(self):
        self.did.append("queue next")
        if self.queued:
            self.queue = [[holder("leg1"), holder("daily", True), holder("leg2", True), holder("other")]]

    def sleep(self, s):
        self.now += s

    def watch(self, next_task="leg2"):
        return gw.watch(self.world, "leg1", next_task)


def test_the_daily_gets_the_emulator_from_the_map_with_the_next_leg_right_behind_it():
    game = Game(glances=[None, None, "MirrorMap"], looks=["MirrorMap", "MirrorMap", None, "HomeReached"])
    assert game.watch() == 0
    # the pause before the bot ends, the next leg's ticket before the done file that lets the daily start
    assert game.did == ["suspend", "shot safe-point", "pause 120", "end bot", "lift", "to window", "shot main-window", "queue next",
                        "stop recording", "done", "pause None"]
    assert "gave way" in game.said[-1] and "leg2" in game.said[-1]


def test_it_waits_for_the_daily_and_leaves_the_bot_alone_until_then():
    alone = [holder("leg1"), holder("other")]
    game = Game(glances=["MirrorMap"], looks=["MirrorMap", "MirrorMap", "HomeReached"],
                queue=[alone, alone, alone, [holder("leg1"), holder("daily", True)]])
    assert game.watch() == 0
    assert game.did[0] == "suspend" and game.now >= 2 * gw.DUE_POLL


def test_a_window_over_the_map_resumes_the_bot_and_it_looks_again():
    # After floor 5 the prompt stands over the map, whose icons read through it: the glance hits, the whole look does not.
    game = Game(glances=["MirrorMap"], looks=["ParallelModePrompt", "MirrorMap", "MirrorMap", "HomeReached"])
    assert game.watch() == 0
    assert game.did[:4] == ["suspend", "resume", "suspend", "shot safe-point"]


def test_a_tap_already_sent_into_the_node_resumes_the_bot():
    game = Game(glances=["MapNodePanel"], looks=[None, "MirrorMap", "MirrorMap", "HomeReached"])
    assert game.watch() == 0
    assert game.did[:3] == ["suspend", "resume", "suspend"]


def test_an_open_node_panel_is_closed_before_to_window():
    game = Game(glances=["MapNodePanel"], looks=["MapNodePanel", "MapNodePanel", "MirrorMap", "HomeReached"])
    assert game.watch() == 0
    assert game.did[4:7] == ["lift", "back", "to window"]


def test_dungeon_progress_opened_by_a_back_too_many_goes_on_to_the_window():
    game = Game(glances=["MapNodePanel"], looks=["MapNodePanel", "MapNodePanel", "ProgressPanel", "HomeReached"])
    assert game.watch() == 0 and "to window" in game.did


def test_a_forfeit_under_way_is_no_safe_point():
    # The map is where the bot forfeits; a new bot would not know and play on.
    game = Game(glances=["MirrorMap"], looks=["MirrorMap"], forfeit=lambda: True, runs=60)
    assert game.watch() == 3 and game.did == []


def test_a_bot_that_ends_by_itself_ends_the_watch_and_the_hold_stays():
    game = Game(glances=[None], looks=[None], runs=60)
    assert game.watch() == 3 and game.did == [] and "by itself" in game.said[-1]
    waiting = Game(glances=[None], looks=[None], runs=60, queue=[[holder("leg1")]])
    assert waiting.watch() == 3 and waiting.did == [] and "no daily" in waiting.said[-1]


def test_without_the_hold_or_the_bot_it_does_not_start():
    for game in (Game(queue=[[holder("other"), holder("leg1")]]), Game(queue=[[]]), Game(runs=0)):
        assert game.watch() == 2 and game.did == []


@pytest.mark.parametrize("game, why", [
    (Game(glances=["MirrorMap"], looks=["MirrorMap", "BattleTurn"]), "the map"),
    (Game(glances=["MirrorMap"], looks=["MirrorMap"], to_window=False), "To Window"),
    (Game(glances=["MirrorMap"], looks=["MirrorMap"]), "main window"),
    (Game(glances=["MirrorMap"], looks=["MirrorMap", "MirrorMap", "HomeReached"], queued=False), "leg2"),
])
def test_a_step_that_fails_after_the_bot_ended_keeps_the_emulator(game, why):
    assert game.watch() == 1 and why in game.said[-1]
    assert "pause 120" in game.did and "done" not in game.did and "pause None" not in game.did and game.did[-1] == "shot failed"


def test_a_bot_that_does_not_end_stays_suspended():
    game = Game(glances=["MirrorMap"], looks=["MirrorMap"], ends=False)
    assert game.watch() == 1
    assert "resume" not in game.did and "lift" not in game.did and "done" not in game.did


def test_a_deliberate_break_needs_no_daily_and_keeps_the_hold():
    game = Game(glances=["MirrorMap"], looks=["MirrorMap", "MirrorMap", "HomeReached"], queue=[[holder("leg1")]])
    assert game.watch(next_task=None) == 0
    assert game.did == ["suspend", "shot safe-point", "pause 120", "end bot", "lift", "to window", "shot main-window", "pause None"]


def test_a_task_name_is_the_tickets():
    # the queue writes a name's other characters as _ (v2-853 -> v2_853)
    q = [holder("v2_853"), holder("daily", True), holder("v2_853_b", True), holder("x")]
    assert gw.daily_waits(q, "v2-853") is True and gw.daily_waits(q[:1], "v2-853") is False and gw.daily_waits(q, "x") is None
    assert gw.behind_the_daily(q, "v2-853-b") and not gw.behind_the_daily(q, "x") and not gw.behind_the_daily(q, "v2-853")
    assert not gw.behind_the_daily(q, "gone")


@pytest.mark.parametrize("log, pending", [
    ("", False),
    ("1 [maalc] 2 sinners alive, team 'A' needs 3: forfeit the run\n", True),
    ("1 [maalc] wipe: 2 of 2 retries used: forfeit\n", True),
    ("1 [maalc] wipe: 0 of 2 retries used: retry\n", False),
    ("1 [maalc] wipe: 2 of 2 retries used: forfeit\n2 [maalc] forfeited the run\n", False),
    ("1 [maalc] wipe: 2 of 2 retries used: forfeit\n2 [run] child pid 5\n", False),
])
def test_a_forfeit_is_under_way_from_its_line_until_it_is_done(tmp_path, log, pending):
    (tmp_path / "run.log").write_text(log, encoding="utf-8")
    assert gw.forfeit_pending(tmp_path / "run.log") is pending
    assert gw.forfeit_pending(tmp_path / "none.log") is False


def test_the_forfeit_lines_are_the_bots():
    battle = (REPO / "agent/battle_actions.py").read_text(encoding="utf-8")
    assert ': forfeit the run")' in battle and "retries used: " in battle
    assert 'log("forfeited the run")' in (REPO / "agent/map_actions.py").read_text(encoding="utf-8")


def test_the_next_leg_queues_behind_the_daily_for_real(tmp_path):
    # the command gives queue.py run --first and a hold with the step 1 options, on the task's own folder
    cmd = gw.next_leg_command("leg2", tmp_path, 7200, "default")
    assert cmd[1].endswith("queue.py") and cmd[2:9] == ["run", "--resource", "emulator", "--name", "leg2", "--first", "--"]
    rest = cmd[cmd.index("--") + 1:]
    assert rest[1].endswith("backup.py") and rest[2] == "hold"
    assert rest[rest.index("--guard") + 1] == str(tmp_path / "leg2" / "bot*.log") and rest[-2:] == ["--stop-recording", "default"]
    assert "--stop-recording" not in gw.next_leg_command("leg2", tmp_path, 7200, None)
    # and a --first ticket placed while the daily's waits lands right behind it
    qdir = tmp_path / "q"
    qdir.mkdir()
    for stamp, name, first in (("1000000000000000001", "leg1", False), ("1000000000000000002", "daily", True),
                               ("1000000000000000900", "other", False)):
        (qdir / f"{stamp}-{os.getpid()}-{name}.ticket").write_text(json.dumps({"cmd": "hold", "start": None, "first": first}))
    lq.place(qdir, "leg2", ["hold"], first=True)
    q = lq.holders(qdir)
    assert [h.name for h in q] == ["leg1", "daily", "leg2", "other"] and gw.behind_the_daily(q, "leg2")


def test_a_used_next_name_and_a_missing_bot_are_refused_before_the_emulator_is_touched(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gw, "main_checkout", lambda: tmp_path)
    scratch = tmp_path / ".local/scratch"
    (scratch / "leg2").mkdir(parents=True)
    (scratch / "leg2" / "done").write_text("")
    args = ["watch", "--task", "leg1", "--install", str(tmp_path)]
    assert gw.main([*args, "--next", "leg2"]) == 2 and "used before" in capsys.readouterr().out
    assert gw.main([*args, "--next", "leg3"]) == 2 and "no bot was started" in capsys.readouterr().out


needs_psutil = pytest.mark.skipif(importlib.util.find_spec("psutil") is None, reason="psutil is the probe group's")


@needs_psutil
def test_a_suspended_bot_is_resumed_or_ended():
    import psutil

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        procs = [psutil.Process(child.pid)]
        resume = gw.suspend(procs)
        assert procs[0].status() == psutil.STATUS_STOPPED
        resume()
        assert procs[0].status() != psutil.STATUS_STOPPED
        gw.suspend(procs)
        gw.end(procs)  # a suspended process ends
        assert child.wait(10) is not None
        gw.end(procs)  # one that ended meanwhile is fine
    finally:
        child.kill()


@needs_psutil
def test_a_process_that_does_not_end_is_a_failure(monkeypatch):
    import psutil

    stays = SimpleNamespace(pid=7, kill=lambda: None)
    monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout: ([], procs))
    with pytest.raises(gw.Failed, match="7"):
        gw.end([stays])


@needs_psutil
def test_the_bots_processes_leave_the_adb_server_out_and_have_the_root(monkeypatch):
    from live import device

    tree = [SimpleNamespace(pid=n, name=lambda name=name: name, children=lambda recursive: [])
            for n, name in ((1, "python.exe"), (2, "adb.exe"))]
    monkeypatch.setattr(device, "bot_tree", lambda pid: tree)
    assert [p.pid for p in gw.bot_processes(os.getpid())] == [1, os.getpid()]
