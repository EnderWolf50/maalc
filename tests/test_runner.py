"""The runner (runner/, #812) driven offline: a fake MaaFramework on a fake clock, and a real child process for the bot
that prints what a test needs and ends when the runner disconnects from it."""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import memlog
from agent_patch import patch_all
from runner import devices, protocol, runlog, session
from runner.session import Commands, Out, Session

REPO = Path(__file__).resolve().parent.parent


def device(address, mumu_index=None, name=None, adb="C:/MuMu/nx_main/adb.exe"):
    config = {"extras": {"mumu": {"enable": True, "path": "C:/MuMu", "index": mumu_index}}} if mumu_index is not None else {}
    return SimpleNamespace(name=name or f"dev-{address}", adb_path=Path(adb), address=address, screencap_methods=1,
                           input_methods=2, config=config)


MUMU0 = device("127.0.0.1:16384", 0, "MuMuPlayer-12.0-0-MuMuPlayer v5+")
MUMU1 = device("127.0.0.1:16416", 1, "MuMuPlayer-12.0-1-MuMuPlayer v5+")
OTHER = device("emulator-5554", None, "emulator-5554", adb="C:/adb/adb.exe")
MANAGER = "C:/MuMu/nx_main/MuMuManager.exe"  # beside MuMu's adb


class Job:
    def __init__(self, entry):
        self.entry, self.state, self.left = entry, "pending", 0

    def get(self):
        s = self.state
        status = SimpleNamespace(done=s in ("succeeded", "failed"), succeeded=s == "succeeded", failed=s == "failed",
                                 running=s == "running", pending=s == "pending")
        return SimpleNamespace(status=status, nodes=[SimpleNamespace(name=f"{self.entry}Hub", completed=s == "succeeded")])


class World:
    """A fake MaaFramework on a fake clock; a sleep of the runner is a tick. The tasker runs the posted tasks in turn,
    each for its plan's ticks, and ends it succeeded, failed, or halt: the bot's account-level stop, which ends it
    halt_ends (succeeded, as MaaFramework says of the action that posted the stop and returned, #870) and stops the
    tasker with the rest unrun, once halt_when() holds (the bot's lines are in). post_stop clears the queue at
    once and ends the running task stop_ends (failed, or succeeded as MaaFramework says when the agent's action returns
    normally after post_stop, #832) stop_ticks ticks later (None: never, until free()). at: {time: call}.
    adb says `offline` to the first `offline` looks at a device's state, and a connect fails while it does, as
    MaaFramework's does (its get-state); each look takes `asks` s; the first `refusals` connects fail besides.
    The PC client (#940, tests/test_pc.py): desk the windows (runner/pc.py's Win32Windows; none open by default),
    make_pc(hwnd, windows) the PC window controller; a task that runs takes a screencap each tick, as the bot's does."""

    def __init__(self, plan, *, found=(MUMU0,), appear=None, stop_ticks=1, at=None, connects=True, halt_when=None,
                 offline=0, asks=0.0, refusals=0, stop_ends="failed", halt_ends="succeeded", desk=None, make_pc=None):
        self.plan, self.found, self.appear, self.stop_ticks = plan, list(found), appear, stop_ticks
        self.stop_ends, self.halt_ends, self.asks = stop_ends, halt_ends, asks
        self.at, self.connects, self.halt_when = dict(at or {}), connects, halt_when or (lambda: True)
        self.offline, self.refusals = offline, refusals
        self.t, self.queue, self.current, self.stop_left = 1000.0, [], None, None
        self.posted, self.stops, self.roots, self.bundles, self.controllers = [], [], [], [], []
        self.looks, self.timeouts, self.connected_at = [], [], []
        self.disconnected = False
        self.ran = None  # a file the first task to run writes as it starts (Run sets it), for a bot that waits on it
        self.desk, self.make_pc, self.bound = desk or SimpleNamespace(find=lambda: []), make_pc, None

    # the clock
    def monotonic(self):
        return self.t

    def sleep(self, s):
        time.sleep(0.001)  # a test that waits on the bot's output spins on the fake clock: let its reader run
        self.t += s
        for when in sorted(k for k in self.at if k <= self.t):
            self.at.pop(when)()
        if self.appear and self.t >= self.appear[0]:
            self.found.append(self.appear[1])
            self.appear = None
        self.step()

    def step(self):
        if self.stop_left is not None:
            self.stop_left -= 1
            if self.stop_left <= 0:
                self.free()
            return
        if self.current is None and self.queue:
            self.current = self.queue.pop(0)
            self.current.state, self.current.left = "running", self.plan[self.current.entry][0]
            if self.ran is not None and not self.ran.exists():
                self.ran.write_text("")
            return
        if self.current is not None:
            if (shot := getattr(self.bound, "screencap", None)) is not None:
                shot()
            self.current.left -= 1
            outcome = self.plan[self.current.entry][1]
            if self.current.left > 0 or (outcome == "halt" and not self.halt_when()):
                return
            self.current.state = self.halt_ends if outcome == "halt" else outcome
            self.current = None
            if outcome == "halt":
                self.queue.clear()

    def free(self):
        """The stop takes: the running task ends as stop_ends."""
        if self.current is not None:
            self.current.state, self.current = self.stop_ends, None
        self.stop_left = None

    # MaaFramework
    def __call__(self, root):  # Framework(root)
        self.roots.append(root)
        return self

    def devices(self):
        return list(self.found)

    def controller(self, d):
        self.controllers.append(d.address)
        up = self.connects and self.offline <= 0 and len(self.controllers) > self.refusals
        if up:
            self.connected_at.append(self.t)
        return SimpleNamespace(post_connection=lambda: SimpleNamespace(wait=lambda: None), connected=up)

    def adb_state(self, d, timeout):  # devices.adb_state
        self.looks.append(self.t)
        self.timeouts.append(timeout)
        self.t += self.asks
        self.offline -= 1
        return "error: device offline" if self.offline >= 0 else "device"

    def pc_controller(self, hwnd, windows):
        return self.make_pc(hwnd, windows)

    def resource(self):
        def post_bundle(path):
            self.bundles.append(path)
            return SimpleNamespace(wait=lambda: SimpleNamespace(succeeded=True))
        return SimpleNamespace(post_bundle=post_bundle)

    def agent_client(self):
        world = self

        class Client:
            identifier = "agent-1"

            def bind(self, res):
                pass

            def connect(self):
                return True

            def disconnect(self):
                world.disconnected = True
                world.running_at_disconnect = world.current is not None or bool(world.queue)
                world.bye.write_text("")
        return Client()

    def tasker(self):
        world = self

        class Tasker:
            inited = True

            def bind(self, res, ctl):
                world.bound = ctl

            def post_task(self, entry):  # no pipeline override: each task reads the settings file (#813)
                job = Job(entry)
                world.posted.append(entry)
                world.queue.append(job)
                return job

            @property
            def running(self):
                return world.current is not None or bool(world.queue)

            def post_stop(self):
                world.stops.append(world.t)
                world.queue.clear()
                if world.stop_left is None and world.current is not None and world.stop_ticks is not None:
                    world.stop_left = world.stop_ticks
        return Tasker()


def bot(bye, *lines, code=None, after=None):
    """The bot's command: print lines, then exit with code (once the file after exists, when given), or wait until the
    runner's disconnect writes bye."""
    script = "".join(f"print({line!r}, flush=True)\n" for line in lines)
    if after is not None:
        script += f"import os, time\nwhile not os.path.exists({str(after)!r}): time.sleep(0.02)\n"
    script += (f"raise SystemExit({code})\n" if code is not None else
               f"import os, time\nwhile not os.path.exists({str(bye)!r}): time.sleep(0.02)\n")
    return lambda root, identifier: [sys.executable, "-c", script]


class Run:
    """A runner session on a World, its events in order (marks of the keep-awake among them). exits_in_task: the bot
    exits with code only once the first task runs, so the runner has seen it running whatever the machine's load
    (#976: a bot that exits at once may be gone by the runner's first look, before any task started)."""

    def __init__(self, tmp_path, world, *bot_lines, code=None, launch=None, exits_in_task=False):
        self.world, self.events, self.root = world, [], tmp_path / "install"
        world.bye = tmp_path / "bye"
        if exits_in_task:
            world.ran = tmp_path / "ran"
        self.out = Out(lambda text: self.events.append(json.loads(text)), clock=lambda: "12:00:00.000")
        self.commands, self.launched = Commands(), []

        @contextmanager
        def awake():
            self.events.append("awake on")
            yield
            self.events.append("awake off")

        def launch_mumu(manager, index):
            self.launched.append(devices.launch_command(manager, index))
            return launch(manager, index) if launch else (0, "")

        self.session = Session(self.out, world, self.commands, sleep=world.sleep, monotonic=world.monotonic,
                               agent_command=bot(world.bye, *bot_lines, code=code, after=world.ran),
                               launch=launch_mumu, awake=awake, adb_state=world.adb_state, windows=world.desk)

    def start(self, tasks, **device):
        line = {"v": 1, "cmd": "start", "root": str(self.root), "tasks": tasks,
                "device": {"address": "127.0.0.1:16384", **device}}
        self.result = self.session.start(protocol.command(json.dumps(line)))
        for e in self.events:
            if isinstance(e, dict):
                protocol.check_event(e)  # every event the runner sent follows the protocol
        return self.result

    def stop_at(self, t):
        self.world.at[t] = lambda: self.commands.put('{"v": 1, "cmd": "stop"}')

    def of(self, kind):
        return [e for e in self.events if isinstance(e, dict) and e["event"] == kind]

    def states(self):
        return [(e["index"], e["state"], *([e["reason"]] if "reason" in e else [])) for e in self.of("task")]

    def codes(self):
        """(index, state, reason_code, reason_params) of each task event that carries a code (#881)."""
        return [(e["index"], e["state"], e["reason_code"], e.get("reason_params", {})) for e in self.of("task")
                if "reason_code" in e]

    def lines(self, source=None):
        return [e["line"] for e in self.of("log") if source in (None, e["source"])]


TWO = [{"entry": "MirrorDungeon"}, {"entry": "ExpLuxcavation"}]


def test_a_start_connects_loads_starts_the_bot_and_reports_each_task_in_turn(tmp_path):
    world = World({"MirrorDungeon": (3, "succeeded"), "ExpLuxcavation": (2, "succeeded")})
    run = Run(tmp_path, world, "[maalc] task MirrorDungeon started")
    assert run.start(TWO) == "succeeded"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "succeeded"), (1, "running"),
                            (1, "succeeded")]
    kinds = [e if isinstance(e, str) else e["event"] for e in run.events if e == "awake on" or e == "awake off" or e["event"] != "log"]
    assert kinds == ["awake on", "task", "task", "connection", "connection", "resource", "resource", *["task"] * 4,
                     "awake off", "end"]
    assert [e["state"] for e in run.of("connection")] == ["connecting", "connected"]
    assert run.of("end") == [{"v": 1, "event": "end", "result": "succeeded"}]
    assert world.posted == ["MirrorDungeon", "ExpLuxcavation"]  # the whole list up front, in its order
    assert world.roots == [run.root] and world.bundles == [str(run.root / "resource" / "base")]
    assert world.controllers == ["127.0.0.1:16384"] and world.disconnected
    assert "[maalc] task MirrorDungeon started" in run.lines("agent")  # the bot's line as it printed it
    runner = run.lines("runner")
    assert runner[0].startswith("[run] connected ") and runner[1].startswith("[run] start MirrorDungeon,ExpLuxcavation pid ")
    assert "[run] MirrorDungeon status=succeeded t=" in " ".join(runner) and runner[-1] == "[run] end succeeded"


def test_the_bot_is_handed_the_runners_pid_for_its_memory_lines(tmp_path):
    # #391: the agent logs the tasker's memory at each floor; the runner is the tasker, the bot's parent may be a venv launcher
    world = World({"MirrorDungeon": (2, "succeeded")})
    run = Run(tmp_path, world)
    # memlog.TASKER_PID, the name the agent reads: runner/ does not import agent/, so the two spellings meet here
    script = f"import os; print('[maalc] tasker ' + os.environ.get({memlog.TASKER_PID!r}, 'none'), flush=True)\n"
    script += f"import time\nwhile not os.path.exists({str(world.bye)!r}): time.sleep(0.02)\n"
    run.session.agent_command = lambda root, identifier: [sys.executable, "-c", script]
    run.start(TWO[:1])
    assert f"[maalc] tasker {os.getpid()}" in run.lines("agent")


def test_a_task_listed_twice_is_posted_twice_and_reports_each_entry_by_its_place(tmp_path):
    # #811: a list may run AssembleModules before and after the Luxcavations
    world = World({"AssembleModules": (1, "succeeded"), "ExpLuxcavation": (2, "failed")})
    run = Run(tmp_path, world)
    assert run.start([{"entry": "AssembleModules"}, {"entry": "ExpLuxcavation"}, {"entry": "AssembleModules"}]) == "failed"
    assert world.posted == ["AssembleModules", "ExpLuxcavation", "AssembleModules"]
    assert [(e["index"], e["entry"], e["state"]) for e in run.of("task") if e["state"] != "pending"] == [
        (0, "AssembleModules", "running"), (0, "AssembleModules", "succeeded"), (1, "ExpLuxcavation", "running"),
        (1, "ExpLuxcavation", "failed"), (2, "AssembleModules", "running"), (2, "AssembleModules", "succeeded")]


def test_the_run_log_holds_every_log_line_stamped_as_the_live_tools_write_it(tmp_path):
    world = World({"MirrorDungeon": (2, "succeeded")})
    run = Run(tmp_path, world, "[maalc] hello")
    run.start(TWO[:1])
    (log,) = (run.root / "logs" / "runner").glob("run-*.log")
    assert log.read_text(encoding="utf-8").splitlines() == [f"12:00:00.000 {line}" for line in run.lines()]


def test_the_run_log_folder_keeps_the_newest_30(tmp_path):
    folder = tmp_path / "logs" / "runner"
    folder.mkdir(parents=True)
    for i in range(31):
        (folder / f"run-20261101-0000{i:02}.log").write_text("")
        os.utime(folder / f"run-20261101-0000{i:02}.log", (1_000_000 + i, 1_000_000 + i))
    (folder / "notes.txt").write_text("")  # not a run log: left alone
    f = runlog.open_new(tmp_path)
    f.close()
    logs = sorted(p.name for p in folder.glob("run-*.log"))
    assert len(logs) == 30 and Path(f.name).name in logs
    assert "run-20261101-000000.log" not in logs and "run-20261101-000001.log" not in logs
    assert (folder / "notes.txt").exists()


def test_a_stop_ends_the_running_task_stopped_and_cancels_the_rest(tmp_path):
    world = World({"MirrorDungeon": (100, "succeeded"), "ExpLuxcavation": (2, "succeeded")})
    run = Run(tmp_path, world)
    run.stop_at(1003.0)
    assert run.start(TWO) == "stopped"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "stopped"), (1, "cancelled")]
    assert len(world.stops) == 1 and not run.of("error")
    assert "[run] stop requested" in run.lines("runner")
    assert run.of("end")[-1]["result"] == "stopped" and world.disconnected


def test_the_task_a_stop_cuts_short_ends_stopped_though_maaframework_says_succeeded(tmp_path):
    # #832: MaaFramework says succeeded of a task whose agent action returns normally after post_stop
    world = World({"MirrorDungeon": (100, "succeeded"), "ExpLuxcavation": (2, "succeeded")}, stop_ends="succeeded")
    run = Run(tmp_path, world)
    run.stop_at(1003.0)
    assert run.start(TWO) == "stopped"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "stopped"), (1, "cancelled")]
    assert "[run] MirrorDungeon status=stopped t=" in " ".join(run.lines("runner"))


def test_a_task_that_ends_before_the_runner_takes_the_stop_stays_succeeded(tmp_path):
    # MirrorDungeon ends in the half second the stop is on its way: no post_stop reached it, so it did its work
    world = World({"MirrorDungeon": (2, "succeeded"), "ExpLuxcavation": (100, "succeeded")}, stop_ends="succeeded")
    run = Run(tmp_path, world)
    run.stop_at(1001.5)  # the tick MirrorDungeon ends in (it starts at 1000.5 and runs 2 ticks)
    assert run.start(TWO) == "stopped"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "succeeded"), (1, "cancelled")]
    assert len(world.stops) == 1


def test_a_stop_that_does_not_take_is_posted_again_each_second_and_reported_after_60_s(tmp_path):
    # MaaFramework waits for a custom action to return; the runner says so after 60 s, and the caller ends its tree
    world = World({"MirrorDungeon": (1000, "succeeded"), "ExpLuxcavation": (2, "succeeded")}, stop_ticks=None)
    run = Run(tmp_path, world)
    run.stop_at(1003.0)
    world.at[1003.0 + 75] = world.free  # it takes after all, 75 s on
    assert run.start(TWO) == "stopped"
    (error,) = run.of("error")
    assert error["kind"] == "stop_timeout"
    gaps = np.diff(world.stops)
    assert 60 <= len(world.stops) <= 76 and gaps.min() >= 1.0 and gaps.max() <= 1.5  # about once a second
    timed_out = next(i for i, e in enumerate(run.events) if isinstance(e, dict) and e["event"] == "error")
    assert sum(1 for t in world.stops if t < 1063.0) <= 61 and run.events[timed_out]["message"].startswith(
        "MaaFramework did not stop in 60 s")
    assert run.states()[-2:] == [(0, "stopped"), (1, "cancelled")]
    assert world.disconnected and not world.running_at_disconnect  # the bot closes only once the tasker has stopped


def test_a_stop_while_mumu_boots_ends_the_run_before_it_connects(tmp_path):
    world = World({"MirrorDungeon": (2, "succeeded")}, found=())
    run = Run(tmp_path, world)
    run.stop_at(1005.0)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "stopped"
    assert run.states() == [(0, "pending"), (0, "cancelled")] and world.controllers == []


@pytest.mark.parametrize("halt_ends", ["succeeded", "failed"])
def test_the_bots_own_stop_of_the_whole_list_fails_its_task_and_cancels_the_rest_with_its_reason(tmp_path, halt_ends):
    # #364: an account-level stop (maintenance) posts post_stop from the bot; the rest of the list never runs. #870: the
    # task it stopped in failed, whatever MaaFramework says of it (succeeded: the action that posted the stop returned)
    run = None
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded")}, halt_ends=halt_ends,
                  halt_when=lambda: any(line.startswith("[maalc] account-level stop") for line in run.lines("agent")))
    run = Run(tmp_path, world, "[maalc] stop: maintenance", "[maalc] account-level stop: the rest of the task list is cancelled")
    assert run.start(TWO) == "failed"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "failed", "maintenance"),
                            (1, "cancelled", "maintenance")]
    assert "[run] MirrorDungeon status=failed t=" in " ".join(run.lines("runner"))
    assert not run.of("error") and world.stops == []  # the bot stopped it; the runner had nothing to stop


def test_a_halt_line_that_comes_after_the_tasker_stopped_still_fails_the_task(tmp_path):
    # the bot's lines come through a pipe its post_stop does not wait for: the tasker may stop before the runner reads
    # them. Its stop line comes first (it saves the evidence before the post_stop), so the task it stopped in waits once
    run = None
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded")},
                  halt_when=lambda: any(line.startswith("[maalc] stop") for line in run.lines("agent")))
    run = Run(tmp_path, world, "[maalc] stop: maintenance", "[maalc] account-level stop: the rest of the task list is cancelled")
    take = run.session.agent_line

    def late(text):  # the account-level stop line read 0.2 s after the tasker stopped
        if "account-level" in text:
            time.sleep(0.2)
        take(text)
    run.session.agent_line = late
    assert run.start(TWO) == "failed"
    assert run.states()[-2:] == [(0, "failed", "maintenance"), (1, "cancelled", "maintenance")]


def test_a_halt_in_the_next_task_leaves_the_task_before_it_as_maaframework_says(tmp_path):
    # the runner looks at a task every 0.5 s: the next one may start and stop the whole list before it saw this one end
    run = Run(tmp_path, World({}))
    s = run.session
    s.tasks, s.states = list(TWO), ["running", "pending"]
    s.last_stop = s.halt = "ClientOutdated: the game client is out of date"
    first, second = Job("MirrorDungeon"), Job("ExpLuxcavation")
    first.state = second.state = "succeeded"
    s.finish(0, first.get(), 3.0, second)
    s.finish(1, second.get(), 1.0, None)
    assert run.states() == [(0, "succeeded"), (1, "failed", "ClientOutdated: the game client is out of date")]


def test_a_tasker_that_stops_with_no_reason_from_the_bot_waits_for_one_once(tmp_path):
    # no account-level stop line comes: each unrun task says MaaFramework stopped the list, after one wait in all
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded"), "ClaimMail": (2, "succeeded")})
    run = Run(tmp_path, world)
    began = time.monotonic()
    assert run.start([*TWO, {"entry": "ClaimMail"}]) == "failed"
    assert time.monotonic() - began < session.HALT_WAIT * 2
    assert run.states()[-2:] == [(1, "cancelled", "MaaFramework stopped the task list"),
                                 (2, "cancelled", "MaaFramework stopped the task list")]


HALT = "[maalc] account-level stop: the rest of the task list is cancelled"


def halting(tmp_path, *lines):
    """A run whose first task logs lines, then the account-level stop line, and stops the whole list there."""
    run = None
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded")},
                  halt_when=lambda: any(line.startswith("[maalc] account-level stop") for line in run.lines("agent")))
    run = Run(tmp_path, world, *lines, HALT)
    assert run.start(TWO) == "failed"
    return run


def test_the_code_of_the_bots_stop_goes_with_its_reason_to_the_task_it_failed_and_the_ones_it_cancelled(tmp_path):
    # #881: the bot logs its stop's code after the stop line; the window says the reason in its own language by it
    run = halting(tmp_path, "[maalc] stop: ClientOutdated: the game client is out of date", "[maalc] stop code: ClientOutdated")
    assert run.states()[-2:] == [(0, "failed", "ClientOutdated: the game client is out of date"),
                                 (1, "cancelled", "ClientOutdated: the game client is out of date")]
    assert run.codes() == [(0, "failed", "ClientOutdated", {}), (1, "cancelled", "ClientOutdated", {})]


def test_a_code_with_params_comes_with_them(tmp_path):
    run = halting(tmp_path, "[maalc] stop: the game asked for an update 3 times since the bot started",
                  '[maalc] stop code: UpdateRepeats {"times":3}')
    assert run.codes() == [(0, "failed", "UpdateRepeats", {"times": 3}), (1, "cancelled", "UpdateRepeats", {"times": 3})]


@pytest.mark.parametrize("lines", [
    ["[maalc] stop: maintenance"],  # an older bot: no code line
    ["[maalc] stop: a", "[maalc] stop code: Stuck", "[maalc] stop: maintenance"],  # the code was the stop before's
    ["[maalc] stop: maintenance", "[maalc] stop code: Stuck {not json"],  # a line the runner cannot read
    ["[maalc] stop: maintenance", '[maalc] stop code: Stuck {"why":[1]}'],  # params the protocol does not carry
], ids=["no code", "an earlier stop's", "not json", "a list param"])
def test_a_stop_with_no_code_the_runner_can_read_sends_its_reason_alone(tmp_path, lines):
    run = halting(tmp_path, *lines)
    assert run.states()[-2:] == [(0, "failed", "maintenance"), (1, "cancelled", "maintenance")] and run.codes() == []


def test_the_runners_own_reasons_have_codes(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(MUMU1,))
    run = Run(tmp_path / "a", world)
    assert run.start(TWO[:1]) == "failed"
    assert run.codes() == [(0, "cancelled", "NoEmulator", {})]

    world = World({"MirrorDungeon": (1, "succeeded")}, connects=False)
    run = Run(tmp_path / "b", world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "failed"
    assert run.codes() == [(0, "cancelled", "ConnectFailed", {"address": "127.0.0.1:16384"})]

    world = World({"MirrorDungeon": (100_000, "succeeded"), "ExpLuxcavation": (2, "succeeded")})  # until the bot exits
    run = Run(tmp_path / "c", world, "[maalc] task MirrorDungeon started", code=3, exits_in_task=True)
    assert run.start(TWO) == "failed"
    assert run.codes() == [(1, "cancelled", "BotExited", {"code": 3})]

    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded")})
    run = Run(tmp_path / "d", world)
    assert run.start(TWO) == "failed"
    assert run.codes() == [(1, "cancelled", "ListStopped", {})]


def test_each_code_the_runner_sends_has_its_sentences():
    # agent/stop_reasons.json, which the window reads: the runner's own codes are there with the params it sends
    import reasons
    for code, params in session.OWN_CODES.items():
        assert code in reasons.CODES and set(params) == set(reasons.CODES[code]["en_us"].replace("}", "{").split("{")[1::2])


def test_nothing_follows_the_end_event_and_a_line_after_the_run_log_closed_goes_out_only(tmp_path):
    # a reader thread (the console, a bot's last line) may log while the run log closes, or after the end
    sent = []
    out = Out(lambda text: sent.append(json.loads(text)), clock=lambda: "12:00:00.000")
    out.file = open(tmp_path / "run.log", "w", encoding="utf-8")
    out.log("agent", "[maalc] a")
    out.close_log()
    out.log("console", "b")
    out.send("end", result="succeeded")
    out.log("console", "c")
    assert [e.get("line", e["event"]) for e in sent] == ["[maalc] a", "b", "end"]
    assert (tmp_path / "run.log").read_text(encoding="utf-8") == "12:00:00.000 [maalc] a\n"


def test_the_bot_exiting_mid_run_fails_the_run_with_its_code_and_last_lines(tmp_path):
    world = World({"MirrorDungeon": (100_000, "succeeded"), "ExpLuxcavation": (2, "succeeded")})  # until the bot exits
    run = Run(tmp_path, world, "[maalc] task MirrorDungeon started", "Traceback (most recent call last):",
              "RuntimeError: boom", code=3, exits_in_task=True)
    assert run.start(TWO) == "failed"
    (error,) = run.of("error")
    assert (error["kind"], error["code"], error["message"]) == ("agent_exit", 3, "the bot exited with code 3")
    assert error["tail"][-2:] == ["Traceback (most recent call last):", "RuntimeError: boom"]
    assert run.states()[-2:] == [(0, "failed"), (1, "cancelled", "the bot exited with code 3")]
    assert len(world.stops) == 1  # the runner stopped MaaFramework, and ran nothing again


def test_a_scan_lists_the_devices_mumu_first_with_its_instance_and_manager(tmp_path):
    world = World({}, found=(OTHER, MUMU1, MUMU0))
    run = Run(tmp_path, world)
    assert run.session.scan() == "succeeded"
    (listed,) = run.of("devices")
    protocol.check_event(listed)
    assert [d["address"] for d in listed["devices"]] == ["127.0.0.1:16416", "127.0.0.1:16384", "emulator-5554"]
    assert listed["devices"][0]["mumu"] == {"index": 1, "manager": str(Path(MANAGER)),
                                            "path": "C:/MuMu"}
    assert listed["devices"][2]["mumu"] is None and run.of("end")[-1]["result"] == "succeeded"


def test_a_start_picks_the_device_at_its_address(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(MUMU0, MUMU1))
    run = Run(tmp_path, world)
    line = {"v": 1, "cmd": "start", "root": str(run.root), "tasks": TWO[:1], "device": {"address": "localhost:16416"}}
    assert run.session.start(protocol.command(json.dumps(line))) == "succeeded"
    assert world.controllers == ["127.0.0.1:16416"] and run.launched == []


def test_a_start_without_an_address_takes_the_first_device_mumu_first(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(OTHER, MUMU1))
    run = Run(tmp_path, world)
    run.session.start(protocol.command(json.dumps({"v": 1, "cmd": "start", "root": str(run.root), "tasks": TWO[:1]})))
    assert world.controllers == ["127.0.0.1:16416"]


def masked_events(run):
    """The run's events with what differs between two runs of one test masked: the install's folder and the bot's pid."""
    def masked(e):
        if not (isinstance(e, dict) and e["event"] == "log"):
            return e
        return {**e, "line": re.sub(r" agent \d+ ", " agent <pid> ", e["line"].replace(str(run.root), "<root>"))}
    return [masked(e) for e in run.events]


# (World, the bot's lines, the start's device besides its address): a run to its end, no device, a MuMu started
EMULATOR_RUNS = {
    "to its end": (lambda: World({"MirrorDungeon": (3, "succeeded"), "ExpLuxcavation": (2, "succeeded")}),
                   ("[maalc] task MirrorDungeon started",), {}),
    "no device": (lambda: World({"MirrorDungeon": (1, "succeeded")}, found=(MUMU1,)), (), {}),
    "mumu started": (lambda: World({"MirrorDungeon": (1, "succeeded")}, found=(OTHER,), appear=(1010.0, MUMU0)), (),
                     {"mumu_index": 0, "mumu_manager": MANAGER}),
}


@pytest.mark.parametrize("name", EMULATOR_RUNS)
def test_a_start_that_names_the_emulator_sends_the_same_events_as_one_that_names_no_kind(tmp_path, name):
    # #939: an omitted kind is the emulator, and naming it changes nothing the runner does or says
    make, lines, more = EMULATOR_RUNS[name]
    runs = []
    for folder, kind in (("omitted", {}), ("named", {"kind": "emulator"})):
        world = make()
        run = Run(tmp_path / folder, world, *lines)
        result = run.start(TWO, **more, **kind)
        runs.append({"result": result, "events": masked_events(run), "posted": world.posted,
                     "controllers": world.controllers, "bundles": len(world.bundles), "launched": run.launched})
    omitted, named = runs
    assert omitted == named
    assert len(omitted["events"]) > 6  # the run said something to compare


def test_a_mumu_not_running_is_started_and_waited_for_then_connected_after_it_settles(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(OTHER,), appear=(1010.0, MUMU0))
    connected_at = []
    controller = world.controller
    world.controller = lambda d: connected_at.append(world.t) or controller(d)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "succeeded"
    assert run.launched == [[MANAGER, "control", "--vmindex", "0", "launch"]]
    assert [e["state"] for e in run.of("connection")] == ["launching", "waiting", "connecting", "connected"]
    assert world.controllers == ["127.0.0.1:16384"] and 1015.0 <= connected_at[0] <= 1016.0  # up at 1010, then 5 s


def test_a_started_mumu_is_connected_once_adb_says_device_not_when_the_scan_lists_it(tmp_path):
    # #831: MuMuManager lists the instance 2 s into its boot, while its adb says `device offline` for 12 s more
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), offline=12)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "succeeded"
    assert world.looks[0] == 1002.0 and len(world.looks) == 13  # each second from when the scan lists it
    assert world.controllers == ["127.0.0.1:16384"] and world.connected_at == [1019.0]  # device at 1014, then 5 s
    runner = run.lines("runner")
    assert "[run] 127.0.0.1:16384 after 2 s: adb says error: device offline (in 0.0 s)" in runner
    assert "[run] 127.0.0.1:16384 is up after 14 s: adb says device (in 0.0 s); connecting in 5 s" in runner


def test_each_line_of_the_wait_for_adb_says_how_long_that_look_took(tmp_path):
    # #839: a look that waited out its timeout showed only as a later line; the live check reads it off the log
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), offline=2, asks=1.2)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "succeeded"
    runner = [line for line in run.lines("runner") if "adb says" in line]  # looks at 1002, 1004.2, 1006.4
    assert runner == ["[run] 127.0.0.1:16384 after 3 s: adb says error: device offline (in 1.2 s)",
                      "[run] 127.0.0.1:16384 is up after 8 s: adb says device (in 1.2 s); connecting in 5 s"]


def test_a_started_mumu_whose_adb_stays_offline_fails_the_run_after_120_s_with_what_adb_said(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), offline=10**6)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "failed"
    (error,) = run.of("error")
    assert error["kind"] == "device_timeout" and error["message"] == (
        "MuMu instance 0 did not come up at 127.0.0.1:16384 in 120 s: adb says error: device offline")
    assert 1120.0 <= world.t <= 1122.0 and world.controllers == []
    assert run.lines("runner").count("[run] 127.0.0.1:16384 after 2 s: adb says error: device offline (in 0.0 s)") == 1


def test_a_started_mumu_that_refuses_the_first_connects_is_connected_on_a_try_a_second_later(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), refusals=2)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "succeeded"
    assert world.controllers == ["127.0.0.1:16384"] * 3 and world.connected_at == [1009.0]  # 1007, 1008, 1009
    assert not run.of("error")


def test_a_connect_that_never_takes_is_tried_until_120_s_after_the_launch_and_once_on_a_running_device(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), connects=False)
    run = Run(tmp_path / "a", world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "failed"
    assert [e["kind"] for e in run.of("error")] == ["connect_failed"]
    assert 1120.0 <= world.t <= 1122.0 and 100 <= len(world.controllers) <= 115  # each second from 1007

    world = World({"MirrorDungeon": (1, "succeeded")}, connects=False)  # MuMu was running: no wait, one try
    run = Run(tmp_path / "b", world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "failed"
    assert [e["kind"] for e in run.of("error")] == ["connect_failed"]
    assert world.controllers == ["127.0.0.1:16384"] and world.looks == [] and world.t == 1000.0


def test_a_stop_while_the_runner_tries_to_connect_a_started_mumu_ends_the_run_stopped(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), connects=False)
    run = Run(tmp_path, world)
    run.stop_at(1010.0)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER) == "stopped"
    assert run.states() == [(0, "pending"), (0, "cancelled")] and not run.of("error")
    assert world.t <= 1012.0


def test_adb_state_asks_as_maaframeworks_connect_does_with_the_devices_own_adb():
    calls = []

    def answer(said, code=0):
        def run(cmd, stdout, **kw):
            calls.append(cmd)
            stdout.write(said if cmd[-1] == "get-state" else b"already connected to 127.0.0.1:16384\r\n")
            return SimpleNamespace(returncode=code if cmd[-1] == "get-state" else 0)
        return run
    adb = str(MUMU0.adb_path)
    assert devices.adb_state(MUMU0, run=answer(b"device\r\n")) == "device"
    assert calls == [[adb, "start-server"], [adb, "connect", "127.0.0.1:16384"],
                     [adb, "-s", "127.0.0.1:16384", "get-state"]]
    assert devices.adb_state(MUMU0, run=answer(b"error: device offline\r\n", 1)) == "error: device offline"
    calls.clear()
    assert devices.adb_state(OTHER, run=answer(b"device\n")) == "device"
    assert calls == [[str(OTHER.adb_path), "-s", "emulator-5554", "get-state"]]  # a local serial needs no connect

    def missing(cmd, **kw):
        raise FileNotFoundError(2, "not found")
    assert devices.adb_state(MUMU0, run=missing).startswith("FileNotFoundError")


def test_adb_state_takes_no_longer_than_its_timeout_for_every_call(monkeypatch):
    # the runner hands it the time left until 120 s after the launch: a hung adb does not hold the start past it.
    # A fake clock that only the fake adb moves (#908): a busy machine's stalls cannot change what each call is given.
    now = [100.0]
    monkeypatch.setattr(devices, "time", SimpleNamespace(monotonic=lambda: now[0]))
    timeouts = []

    def run(cmd, stdout, timeout, **kw):
        timeouts.append(timeout)
        now[0] += 0.05
        stdout.write(b"device\n")
        return SimpleNamespace(returncode=0)
    assert devices.adb_state(MUMU0, timeout=3.0, run=run) == "device"
    # each call gets what the ones before left (50 ms each), the connect CONNECT_WAIT at most; start-server
    # gets it all: a connect cut while it starts the server leaves none, and the next look would start it again
    # (measured on adb 1.0.41, #839)
    assert len(timeouts) == 3 and timeouts[0] == pytest.approx(3.0) and timeouts[1] == pytest.approx(devices.CONNECT_WAIT)
    assert timeouts[2] == pytest.approx(3.0 - 0.1)
    assert devices.adb_state(MUMU0, timeout=60.0, run=run) == "device" and max(timeouts[3:]) <= devices.ADB_TIMEOUT
    timeouts.clear()
    assert devices.adb_state(MUMU0, timeout=0.0, run=run).startswith("TimeoutExpired") and timeouts == []


def stuck_adb(spent, handshake=10.0):
    """subprocess.run of a MuMu adb whose port takes the connection before the instance's adbd is up, as measured on
    adb 1.0.41 (platform-tools 36, the one in MuMu's folder) against a port that accepts and never answers: `connect`
    waits handshake s for the device's answer, then says "failed to connect"; its server keeps the address meanwhile,
    and `get-state` says "error: device offline" at once, also after a client cut short. spent collects the seconds each
    call takes."""
    def run(cmd, stdout, timeout, **kw):
        if cmd[-2] == "connect":
            if timeout < handshake:
                spent.append(timeout)
                raise subprocess.TimeoutExpired(cmd, timeout)
            spent.append(handshake)
            stdout.write(f"failed to connect to {cmd[-1]}\r\n".encode())
            return SimpleNamespace(returncode=0)
        spent.append(0.05)
        stdout.write(b"error: device offline\r\n" if cmd[-1] == "get-state" else b"")
        return SimpleNamespace(returncode=1 if cmd[-1] == "get-state" else 0)
    return run


def test_a_connect_that_waits_for_a_handshake_does_not_hold_the_look_at_adb():
    # #839: the first look after MuMu's start took the full 10 s, its `adb connect` waiting for an adbd not yet up
    spent = []
    assert devices.adb_state(MUMU0, timeout=100.0, run=stuck_adb(spent)) == "error: device offline"
    assert len(spent) == 3 and sum(spent) <= devices.CONNECT_WAIT + 0.2 < devices.ADB_TIMEOUT


def test_the_runner_gives_each_look_at_adb_only_the_time_left_until_120_s_after_the_launch(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(), appear=(1002.0, MUMU0), offline=10**6)
    run = Run(tmp_path, world)
    run.start(TWO[:1], mumu_index=0, mumu_manager=MANAGER)
    assert len(world.looks) > 100 and max(t + timeout for t, timeout in zip(world.looks, world.timeouts)) <= 1120.0


def test_a_mumu_that_does_not_come_up_in_120_s_fails_the_run(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=())
    run = Run(tmp_path, world)
    assert run.start(TWO, mumu_index=1, mumu_manager=MANAGER) == "failed"
    (error,) = run.of("error")
    assert error["kind"] == "device_timeout" and "120 s" in error["message"]
    assert 1120.0 <= world.t <= 1122.0 and world.controllers == []
    assert run.states()[-2:] == [(0, "cancelled", "no emulator to run on"), (1, "cancelled", "no emulator to run on")]


def test_a_start_without_the_device_or_its_mumu_instance_fails_at_once(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(MUMU1,))
    run = Run(tmp_path, world)
    assert run.start(TWO[:1]) == "failed"
    (error,) = run.of("error")
    assert error == {"v": 1, "event": "error", "kind": "device_missing",
                     "message": "no device at 127.0.0.1:16384: found 127.0.0.1:16416"}
    assert run.launched == [] and world.t == 1000.0


def test_a_launch_that_cannot_run_fails_the_run(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=())
    run = Run(tmp_path, world, launch=lambda manager, index: (None, "FileNotFoundError: no MuMuManager.exe"))
    assert run.start(TWO[:1], mumu_index=0, mumu_manager="C:/nope/MuMuManager.exe") == "failed"
    assert [e["kind"] for e in run.of("error")] == ["launch_failed"]


def test_launch_runs_mumumanager_and_returns_its_code_and_output():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=b'{"errcode": 0}\r\n', stderr=b"")
    assert devices.launch(MANAGER, 1, run=run) == (0, '{"errcode": 0}')
    assert calls == [[MANAGER, "control", "--vmindex", "1", "launch"]]

    def missing(cmd, **kw):
        raise FileNotFoundError(2, "not found")
    code, said = devices.launch("C:/nope/MuMuManager.exe", 0, run=missing)
    assert code is None and said.startswith("FileNotFoundError")


@pytest.mark.skipif(sys.platform != "win32", reason="a Job Object is Windows'")
def test_launch_starts_mumumanager_out_of_the_windows_job_so_the_emulator_outlives_the_run():
    # the window ends its job's processes at each run's end (runner.rs Job): MuMu, and what MuMuManager starts for it,
    # must not be among them. A job that allows no breakaway refuses the flag, and the launch then runs inside it.
    flags = []

    def run(cmd, creationflags=0, **kw):
        flags.append(creationflags)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    assert devices.launch(MANAGER, 0, run=run) == (0, "")
    assert len(flags) == 1 and flags[0] & devices.CREATE_BREAKAWAY_FROM_JOB

    flags.clear()

    def refused(cmd, creationflags=0, **kw):
        flags.append(creationflags)
        if creationflags & devices.CREATE_BREAKAWAY_FROM_JOB:
            raise PermissionError(13, "Access is denied")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    code, said = devices.launch(MANAGER, 0, run=refused)
    assert code == 0 and [bool(f & devices.CREATE_BREAKAWAY_FROM_JOB) for f in flags] == [True, False]
    # the run log says so: this MuMu ends with the run
    assert said.startswith("inside the caller's job (breakaway refused: PermissionError: ") and "MuMu ends with the run" in said


def test_keep_awake_holds_the_machine_and_the_display_and_lets_go_after():
    calls = []
    with session.keep_awake(calls.append):
        assert calls == [session.ES_CONTINUOUS | session.ES_SYSTEM_REQUIRED | session.ES_DISPLAY_REQUIRED]
    assert calls[1:] == [session.ES_CONTINUOUS]


def test_the_bots_account_level_stop_names_the_reason_the_runner_reads(tmp_path, monkeypatch, capsys):
    # the runner reads the reason from agent/actions.py stop()'s lines; an account-level stop's comes with its cancel
    import actions
    from unittest.mock import MagicMock

    patch_all(monkeypatch, "ROOT", tmp_path)
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None, "entry": "ClaimMail"})
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    monkeypatch.setitem(actions.STUCK, "halted", None)
    actions.stop(ctx, "the game is under maintenance", whole_list=True)
    ctx.tasker.post_stop.assert_called_once()
    s = Session(Out(lambda text: None), None, Commands())
    for line in capsys.readouterr().out.splitlines():
        s.agent_line(line)
    assert s.halted.is_set() and s.halt == "the game is under maintenance"


def test_the_code_of_the_bots_stop_reads_back_in_the_runner(tmp_path, monkeypatch, capsys):
    # #881: the line agent/reasons.py code_line writes is the one the runner reads
    import actions
    from unittest.mock import MagicMock
    from reasons import Reason

    patch_all(monkeypatch, "ROOT", tmp_path)
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None, "entry": "ExpLuxcavation"})
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    monkeypatch.setitem(actions.STUCK, "halted", None)
    actions.stop(ctx, Reason("EXP: defeated with the 2 retries used up", "LuxDefeated", retries=2), whole_list=True)
    s = Session(Out(lambda text: None), None, Commands())
    for line in capsys.readouterr().out.splitlines():
        s.agent_line(line)
    assert s.halt == "EXP: defeated with the 2 retries used up" and s.halt_code == ("LuxDefeated", {"retries": 2})


SCRIPT = """
import os, sys
sys.path.insert(0, {repo!r})
from runner import cli

class Fake:
    def __init__(self, root):
        os.write(1, b"x: 960, y: 540, width: 1920, height: 1080\\n")  # as MaaFramework's native code prints a tap
        print("a print of the runner's own")
    def devices(self):
        return []

sys.exit(cli.main(framework=Fake))
"""


def test_the_runners_process_keeps_its_stdout_for_the_protocol_and_logs_what_else_is_printed(tmp_path):
    # fds 1 and 2 go to the console pipe: a native print never breaks the protocol, and comes back as a console line
    p = subprocess.run([sys.executable, "-c", SCRIPT.format(repo=str(REPO))], input='{"v": 1, "cmd": "scan"}\n',
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    events = [json.loads(line) for line in p.stdout.splitlines()]
    for e in events:
        protocol.check_event(e)
    assert p.returncode == 0, p.stderr
    assert [e["event"] for e in events if e["event"] != "log"] == ["ready", "devices", "end"]
    console = [e["line"] for e in events if e["event"] == "log" and e["source"] == "console"]
    assert console == ["x: 960, y: 540, width: 1920, height: 1080", "a print of the runner's own"]
    assert events.index(next(e for e in events if e["event"] == "end")) == len(events) - 1  # nothing after the end
    assert p.stderr == ""


@pytest.mark.parametrize("line, says", [("", "stdin ended before a command"), ('{"v": 1, "cmd": "stop"}', "stop: no run"),
                                        ("{", "not JSON")])
def test_a_runner_whose_first_line_breaks_the_protocol_ends_with_code_2(line, says):
    p = subprocess.run([sys.executable, "-c", SCRIPT.format(repo=str(REPO))], input=line + "\n" if line else "",
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    events = [json.loads(x) for x in p.stdout.splitlines()]
    assert p.returncode == 2
    (error,) = [e for e in events if e["event"] == "error"]
    assert error["kind"] == "protocol" and says in error["message"]
    assert events[-1] == {"v": 1, "event": "end", "result": "failed"}


@contextmanager
def scan_with_stdin_open(cmd, **popen):
    """cmd started on a scan, its stdin held open as the window and tools/live/bot.py hold it (#829) until the block
    ends; still running then, it is killed (a runner stuck before MaaFramework loaded has started no process)."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, **popen)
    try:
        p.stdin.write(b'{"v": 1, "cmd": "scan"}\n')
        p.stdin.flush()
        yield p
    finally:
        if p.poll() is None:
            p.kill()
        p.stdin.close()
        p.wait(10)


def test_a_runner_ends_with_its_code_while_its_stdin_stays_open():
    # the reader still blocked on stdin at the exit is no buffered file: sys.stdin's ended the process with an access
    # violation (0xC0000005) instead of its code
    with scan_with_stdin_open([sys.executable, "-c", SCRIPT.format(repo=str(REPO))], stdout=subprocess.DEVNULL) as p:
        assert p.wait(60) == 0


def test_the_real_runner_loads_maaframework_and_ends_a_scan_while_its_stdin_stays_open(tmp_path):
    # the real `import maa` waited for the next command while the reader held stdin's pipe (cli.take_stdin). The runner
    # sits in tmp_path as an install lays it out, so its debug/ lands there
    shutil.copytree(REPO / "runner", tmp_path / "runner", ignore=shutil.ignore_patterns("__pycache__"))
    events, ended = [], threading.Event()
    with scan_with_stdin_open([sys.executable, str(tmp_path / "runner" / "__main__.py")], stdout=subprocess.PIPE) as p:

        def read():
            for line in p.stdout:
                events.append(json.loads(line))
                if events[-1]["event"] == "end":
                    ended.set()

        threading.Thread(target=read, daemon=True).start()
        assert ended.wait(60), f"no end event in 60 s with stdin open: {[e['event'] for e in events]}"
        assert p.wait(10) == 0
    for e in events:
        protocol.check_event(e)
    assert [e["event"] for e in events if e["event"] != "log"] == ["ready", "devices", "end"]
    assert events[-1]["result"] == "succeeded"
