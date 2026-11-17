"""The runner (runner/, #812) driven offline: a fake MaaFramework on a fake clock, and a real child process for the bot
that prints what a test needs and ends when the runner disconnects from it."""

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

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


class Job:
    def __init__(self, entry, override):
        self.entry, self.override, self.state, self.left = entry, override, "pending", 0

    def get(self):
        s = self.state
        status = SimpleNamespace(done=s in ("succeeded", "failed"), succeeded=s == "succeeded", failed=s == "failed",
                                 running=s == "running", pending=s == "pending")
        return SimpleNamespace(status=status, nodes=[SimpleNamespace(name=f"{self.entry}Hub", completed=s == "succeeded")])


class World:
    """A fake MaaFramework on a fake clock; a sleep of the runner is a tick. The tasker runs the posted tasks in turn,
    each for its plan's ticks, and ends it succeeded, failed, or halt: the bot's account-level stop, which fails it and
    stops the tasker with the rest unrun, once halt_when() holds (the bot's lines are in). post_stop clears the queue at
    once and ends the running task failed stop_ticks ticks later (None: never, until free()). at: {time: call}."""

    def __init__(self, plan, *, found=(MUMU0,), appear=None, stop_ticks=1, at=None, connects=True, halt_when=None):
        self.plan, self.found, self.appear, self.stop_ticks = plan, list(found), appear, stop_ticks
        self.at, self.connects, self.halt_when = dict(at or {}), connects, halt_when or (lambda: True)
        self.t, self.queue, self.current, self.stop_left = 1000.0, [], None, None
        self.posted, self.stops, self.roots, self.bundles, self.controllers = [], [], [], [], []
        self.disconnected = False

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
            return
        if self.current is not None:
            self.current.left -= 1
            outcome = self.plan[self.current.entry][1]
            if self.current.left > 0 or (outcome == "halt" and not self.halt_when()):
                return
            self.current.state = "failed" if outcome == "halt" else outcome
            self.current = None
            if outcome == "halt":
                self.queue.clear()

    def free(self):
        """The stop takes: the running task ends failed."""
        if self.current is not None:
            self.current.state, self.current = "failed", None
        self.stop_left = None

    # MaaFramework
    def __call__(self, root):  # Framework(root)
        self.roots.append(root)
        return self

    def devices(self):
        return list(self.found)

    def controller(self, d):
        self.controllers.append(d.address)
        return SimpleNamespace(post_connection=lambda: SimpleNamespace(wait=lambda: None), connected=self.connects)

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
                pass

            def post_task(self, entry, override):
                job = Job(entry, override)
                world.posted.append((entry, override))
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


def bot(bye, *lines, code=None):
    """The bot's command: print lines, then exit with code, or wait until the runner's disconnect writes bye."""
    script = "".join(f"print({line!r}, flush=True)\n" for line in lines)
    script += (f"raise SystemExit({code})\n" if code is not None else
               f"import os, time\nwhile not os.path.exists({str(bye)!r}): time.sleep(0.02)\n")
    return lambda root, identifier: [sys.executable, "-c", script]


class Run:
    """A runner session on a World, its events in order (marks of the keep-awake among them)."""

    def __init__(self, tmp_path, world, *bot_lines, code=None, launch=None):
        self.world, self.events, self.root = world, [], tmp_path / "install"
        world.bye = tmp_path / "bye"
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
                               agent_command=bot(world.bye, *bot_lines, code=code), launch=launch_mumu, awake=awake)

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

    def lines(self, source=None):
        return [e["line"] for e in self.of("log") if source in (None, e["source"])]


TWO = [{"entry": "MirrorDungeon", "override": [{"MirrorDungeon": {"attach": {"difficulty": "hard"}}}]},
       {"entry": "ExpLuxcavation"}]


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
    # each task goes with its own override, as it came: the runner passes it through
    assert world.posted == [("MirrorDungeon", [{"MirrorDungeon": {"attach": {"difficulty": "hard"}}}]), ("ExpLuxcavation", {})]
    assert world.roots == [run.root] and world.bundles == [str(run.root / "resource" / "base")]
    assert world.controllers == ["127.0.0.1:16384"] and world.disconnected
    assert "[maalc] task MirrorDungeon started" in run.lines("agent")  # the bot's line as it printed it
    runner = run.lines("runner")
    assert runner[0].startswith("[run] connected ") and runner[1].startswith("[run] start MirrorDungeon,ExpLuxcavation pid ")
    assert "[run] MirrorDungeon status=succeeded t=" in " ".join(runner) and runner[-1] == "[run] end succeeded"


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
    assert run.start(TWO[:1], mumu_index=0, mumu_manager="C:/MuMu/nx_main/MuMuManager.exe") == "stopped"
    assert run.states() == [(0, "pending"), (0, "cancelled")] and world.controllers == []


def test_the_bots_own_stop_of_the_whole_list_cancels_the_rest_with_its_reason(tmp_path):
    # #364: an account-level stop (maintenance) posts post_stop from the bot; the rest of the list never runs
    run = None
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded")},
                  halt_when=lambda: any(line.startswith("[maalc] account-level stop") for line in run.lines("agent")))
    run = Run(tmp_path, world, "[maalc] stop: maintenance", "[maalc] account-level stop: the rest of the task list is cancelled")
    assert run.start(TWO) == "failed"
    assert run.states() == [(0, "pending"), (1, "pending"), (0, "running"), (0, "failed"), (1, "cancelled", "maintenance")]
    assert not run.of("error") and world.stops == []  # the bot stopped it; the runner had nothing to stop


def test_a_tasker_that_stops_with_no_reason_from_the_bot_waits_for_one_once(tmp_path):
    # no account-level stop line comes: each unrun task says MaaFramework stopped the list, after one wait in all
    world = World({"MirrorDungeon": (2, "halt"), "ExpLuxcavation": (2, "succeeded"), "ClaimMail": (2, "succeeded")})
    run = Run(tmp_path, world)
    began = time.monotonic()
    assert run.start([*TWO, {"entry": "ClaimMail"}]) == "failed"
    assert time.monotonic() - began < session.HALT_WAIT * 2
    assert run.states()[-2:] == [(1, "cancelled", "MaaFramework stopped the task list"),
                                 (2, "cancelled", "MaaFramework stopped the task list")]


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
    world = World({"MirrorDungeon": (1000, "succeeded"), "ExpLuxcavation": (2, "succeeded")})
    run = Run(tmp_path, world, "[maalc] task MirrorDungeon started", "Traceback (most recent call last):",
              "RuntimeError: boom", code=3)
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
    assert listed["devices"][0]["mumu"] == {"index": 1, "manager": str(Path("C:/MuMu/nx_main/MuMuManager.exe")),
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


def test_a_mumu_not_running_is_started_and_waited_for_then_connected_after_it_settles(tmp_path):
    manager = "C:/MuMu/nx_main/MuMuManager.exe"
    world = World({"MirrorDungeon": (1, "succeeded")}, found=(OTHER,), appear=(1010.0, MUMU0))
    connected_at = []
    controller = world.controller
    world.controller = lambda d: connected_at.append(world.t) or controller(d)
    run = Run(tmp_path, world)
    assert run.start(TWO[:1], mumu_index=0, mumu_manager=manager) == "succeeded"
    assert run.launched == [[manager, "control", "--vmindex", "0", "launch"]]
    assert [e["state"] for e in run.of("connection")] == ["launching", "waiting", "connecting", "connected"]
    assert world.controllers == ["127.0.0.1:16384"] and 1015.0 <= connected_at[0] <= 1016.0  # up at 1010, then 5 s


def test_a_mumu_that_does_not_come_up_in_120_s_fails_the_run(tmp_path):
    world = World({"MirrorDungeon": (1, "succeeded")}, found=())
    run = Run(tmp_path, world)
    assert run.start(TWO, mumu_index=1, mumu_manager="C:/MuMu/nx_main/MuMuManager.exe") == "failed"
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
    assert devices.launch("C:/MuMu/nx_main/MuMuManager.exe", 1, run=run) == (0, '{"errcode": 0}')
    assert calls == [["C:/MuMu/nx_main/MuMuManager.exe", "control", "--vmindex", "1", "launch"]]

    def missing(cmd, **kw):
        raise FileNotFoundError(2, "not found")
    code, said = devices.launch("C:/nope/MuMuManager.exe", 0, run=missing)
    assert code is None and said.startswith("FileNotFoundError")


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
