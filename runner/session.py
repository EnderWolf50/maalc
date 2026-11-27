"""One command of the runner: a scan, or a start that runs a task list to its end and reports every step as events.

A start picks the device (starting MuMu when it is not running), connects, loads the install's resource, starts the
bot (agent/main.py) as a child, posts the whole task list up front, as a client queues its list (an account-level
stop's post_stop then leaves the rest unrun, #364), and follows each task by its detail until it is done or the tasker
has stopped (G1: wait() and status go through a runner id a clear_cache drops). It returns once the tasker has
stopped, so the bot is not closed under a task still running.

A task ends succeeded or failed as MaaFramework says; stopped when the caller's stop came while it ran, whatever
MaaFramework says of it (#832); failed, with the reason the bot logged, when the bot stopped the whole list while it
ran, whatever MaaFramework says of it (#870); cancelled when it never ran: after a stop, after the bot stopped the whole
list (the reason it logged comes with it), after the bot exited, or when the run failed before its first task.
A reason comes with its code (#881): the one the bot logged after its stop line, or the runner's own (OWN_CODES).

On the PC client (device kind pc, #940) the device is the game's window (runner/pc.py) and the controller the PC
window controller: the window found, its client area set to the start's pc_size and put back when the run ends, however
it ends. A problem the controller holds (the window gone, minimized, not 16:9, an input it did not take) stops the run
as the bot's exit does: the task it ran fails with that reason and code, the rest are cancelled with them.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from runner import devices, pc, protocol, runlog

ROOT = Path(__file__).resolve().parent.parent  # the install: runner/ sits beside agent/ and resource/

TICK = 0.5  # s between two looks at the running task and the commands
STOP_REPOST = 1.0  # s between two post_stop while the tasker still runs (MaaFramework takes one at a time)
STOP_LIMIT = 60.0  # s a stop may take before the runner reports it cannot stop; the caller then ends its tree
# s a started MuMu has to come up and connect: listed in the scan, adb says `device`, connected. A device up at the limit
# still gets its settle and one connect
LAUNCH_LIMIT = 120.0
SCAN_EVERY = 1.0  # s between two looks (the scan and adb, or a connect) while it boots
# s after adb says `device` before the runner connects: MaaFramework's connect keeps the fastest screencap method that
# works at that moment (source/MaaAdbControlUnit/Manager/ScreencapAgent.cpp init), for the whole run
SETTLE = 5.0
TAIL = 20  # last lines of the bot an exit report quotes
AGENT_END = 5.0  # s the bot has to end after the disconnect (its AgentServer shuts down) before it is killed
DRAIN = 2.0  # s the bot's output is read on after it exits: a process it started may hold the pipe (#663)
HALT_WAIT = 1.0  # s to wait for the bot's account-level stop line once the tasker stopped on its own
NODES = 10  # nodes of each task the run log lists when it ends
# agent/actions.py stop(): its first line names the reason; an account-level stop adds the second before post_stop
STOP_LINE = "[maalc] stop: "
HALT_LINE = "[maalc] account-level stop"
CODE_LINE = "[maalc] stop code: "  # agent/reasons.py code_line, right after its stop line: that stop's code (#881)
# the codes of agent/stop_reasons.json the runner's own reasons send, with their params
OWN_CODES = {"NoEmulator": (), "ConnectFailed": ("address",), "ResourceFailed": (), "BotNotStarted": (),
             "TaskerFailed": (), "RunnerFailed": ("error",), "BotExited": ("code",), "ListStopped": (),
             # the PC window's (#940, runner/pc.py)
             "PcNoWindow": (), "PcManyWindows": ("count",), "PcMinimized": (), "PcNot16By9": ("width", "height"),
             "PcWindowGone": (), "PcRestartOff": (), "PcInputFailed": ()}
ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2


def own(name: str, /, **params) -> tuple[str, dict]:
    """One of the runner's own reason codes (OWN_CODES), with its params."""
    assert set(params) == set(OWN_CODES[name]), (name, params)
    return name, params


def coded(problem: pc.Problem) -> tuple[str, dict]:
    """The PC window's problem as one of the runner's own codes."""
    return own(problem.code, **problem.params)


def stop_code(text: str) -> tuple[str, dict] | None:
    """(code, params) of a code line of the bot, its prefix off: the code, then its params as JSON when it has any. None
    for a line the protocol could not carry (not JSON, params not text or whole numbers): the reason then goes alone."""
    code, _, rest = text.partition(" ")
    try:
        params = json.loads(rest) if rest else {}
    except ValueError:
        return None
    return (code, params) if code and protocol.params_ok(params) else None


class Out:
    """Where events go: the protocol (write takes one line) and, during a start, the run log, under one lock so both
    keep one order. Nothing follows the end event. A write the reader no longer takes (it closed its end) stops the
    protocol; the run goes on and the run log keeps every line."""

    def __init__(self, write, clock=runlog.clock):
        self.write, self.clock, self.file, self.lock = write, clock, None, threading.Lock()
        self.before_end = None  # takes in what is still on its way (the console's last lines) before the end event

    def settle(self) -> None:
        if self.before_end is not None:
            self.before_end()

    def close_log(self) -> None:
        """Close the run log; a line a reader thread logs after it goes to the protocol only."""
        with self.lock:
            f, self.file = self.file, None
        if f is not None:
            f.close()

    def send(self, name: str, /, **fields) -> None:
        with self.lock:
            self._send(protocol.event(name, **fields))
            if name == "end":
                self.write = None

    def log(self, source: str, text: str) -> None:
        with self.lock:
            t = self.clock()
            if self.file:
                self.file.write(runlog.stamp(t, text))
            self._send(protocol.event("log", t=t, source=source, line=text))

    def _send(self, e: dict) -> None:
        if self.write is None:
            return
        try:
            self.write(protocol.line(e))
        except (OSError, ValueError):  # ValueError: the stream is closed
            self.write = None


class Commands:
    """The commands of a stream of lines, parsed as they come: a dict, a ProtocolError, or EOF once it ends."""
    EOF = "eof"

    def __init__(self, lines=None):
        self.q = queue.Queue()
        if lines is not None:
            threading.Thread(target=self._read, args=(lines,), daemon=True).start()

    def _read(self, lines) -> None:
        for raw in lines:
            if raw.strip():
                self.put(raw.strip())
        self.q.put(self.EOF)

    def put(self, text: str) -> None:
        try:
            self.q.put(protocol.command(text))
        except protocol.ProtocolError as e:
            self.q.put(e)

    def get(self):
        return self.q.get()

    def poll(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None


def split_lines(chunk: bytes, rest: bytearray) -> list[str]:
    """The whole lines of rest + chunk, decoded; what follows the last newline stays in rest. A lone \\r ends a line too,
    as text mode did (tools/live/bot.py stamped)."""
    *lines, last = (bytes(rest) + chunk).split(b"\n")
    rest[:] = last
    return [part.decode("utf-8", "replace").rstrip() for raw in lines for part in raw.rstrip(b"\r").split(b"\r")]


def read_lines(fd: int):
    """Each line read from fd, until its end. os.read, not a file object: the reader may still be blocked in it when
    the process exits, and a buffered file's lock held by a daemon thread is fatal at interpreter shutdown."""
    rest = bytearray()
    while chunk := os.read(fd, 65536):
        yield from split_lines(chunk, rest)
    if rest:
        yield bytes(rest).decode("utf-8", "replace").rstrip()


def pump(fd: int, each) -> None:
    """Hand each line read from fd to each (read_lines), until its end."""
    for text in read_lines(fd):
        each(text)


@contextmanager
def keep_awake(set_state=None):
    """The machine and the display stay on while it lasts (SetThreadExecutionState, this thread's; a no-op off
    Windows): an emulator needs the screen awake."""
    if set_state is None:
        if sys.platform != "win32":
            yield
            return
        import ctypes

        set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    try:
        yield
    finally:
        set_state(ES_CONTINUOUS)


def agent_command(root: Path, identifier: str) -> list[str]:
    """The bot, on the Python this runner runs on (the zip's python/, or the venv in development)."""
    return [sys.executable, "-u", str(root / "agent" / "main.py"), identifier]


class Session:
    """framework(root) gives MaaFramework (runner/framework.py, or a test's fake); sleep and monotonic its clock;
    launch(manager, index) starts a MuMu instance (devices.launch); adb_state(device, timeout) says what adb says of
    it (devices.adb_state); awake() keeps the machine on (keep_awake); windows says what Windows says of its windows, for
    the PC client (runner/pc.py Win32Windows)."""

    def __init__(self, out: Out, framework, commands: Commands, *, sleep=time.sleep, monotonic=time.monotonic,
                 agent_command=agent_command, launch=devices.launch, awake=keep_awake, adb_state=devices.adb_state,
                 windows=None):
        self.out, self.framework, self.commands = out, framework, commands
        self.sleep, self.now, self.agent_command, self.launch, self.awake = sleep, monotonic, agent_command, launch, awake
        self.adb_state = adb_state
        self.windows = windows if windows is not None else pc.Win32Windows()
        self.tasker = self.client = self.agent = self.reader = None
        # stop_at: when the caller's stop came; stop_posted, reposted: the first post_stop (the caller's or the
        # runner's own once the bot exited) and the last one
        self.stop_at = self.stop_posted = self.reposted = self.crash = self.halt = self.last_stop = None
        # the codes of crash, halt and last_stop (#881): (code, params), or None for a reason with none
        self.crash_code = self.halt_code = self.last_code = None
        # the PC window controller, whose problem stops the run, that problem's reason and code, and what puts the
        # window back as it was (#940)
        self.pc_ctl = self.pc_reason = self.pc_code = self.put_back = None
        self.timed_out = self.halt_awaited = False
        self.halted = threading.Event()
        self.tail = deque(maxlen=TAIL)
        self.tasks, self.states = [], []

    # what the caller sees
    def say(self, text: str) -> None:
        self.out.log("runner", f"[run] {text}")

    def error(self, kind: str, message: str, **fields) -> None:
        self.say(f"error {kind}: {message}")
        self.out.send("error", kind=kind, message=message, **fields)

    def task(self, i: int, state: str, reason: str | None = None, coded: tuple[str, dict] | None = None) -> None:
        """The task's state, with its reason and the reason's code when there is one."""
        self.states[i] = state
        code = {"reason_code": coded[0], **({"reason_params": coded[1]} if coded[1] else {})} if reason and coded else {}
        self.out.send("task", index=i, entry=self.tasks[i]["entry"], state=state,
                      **({"reason": reason} if reason is not None else {}), **code)

    # scan
    def scan(self) -> str:
        fw = self.framework(ROOT)
        found = devices.ordered(fw.devices())
        self.out.send("devices", devices=[devices.describe(d) for d in found], windows=pc.listed(self.windows))
        self.out.settle()
        self.out.send("end", result="succeeded")
        return "succeeded"

    # start
    def start(self, cmd: dict) -> str:
        root = Path(cmd["root"]) if cmd["root"] else ROOT
        self.tasks, self.states = cmd["tasks"], [None] * len(cmd["tasks"])
        self.out.file = runlog.open_new(root)
        try:
            with self.awake():
                for i in range(len(self.tasks)):
                    self.task(i, "pending")
                try:
                    result = self.run(root, cmd["device"])
                except Exception as e:
                    lines = traceback.format_exc().splitlines()
                    self.error("internal", f"{type(e).__name__}: {e}", tail=lines[-TAIL:])
                    result = self.cancel_rest("failed", f"the runner failed: {type(e).__name__}",
                                              own("RunnerFailed", error=type(e).__name__))
                finally:
                    self.close_agent()
                    self.restore_window()
            self.out.settle()
            self.say(f"end {result}")
            self.out.send("end", result=result)
        finally:
            self.out.close_log()
        return result

    def cancel_rest(self, result: str, reason: str | None, coded: tuple[str, dict] | None = None) -> str:
        """Every task not yet ended is cancelled (with the reason and its code, unless the caller stopped the run): the
        result."""
        for i, state in enumerate(self.states):
            if state in ("pending", "running"):
                self.cancel(i, reason, coded)
        return "stopped" if self.stop_at is not None else result

    def cancel(self, i: int, reason: str | None, coded: tuple[str, dict] | None = None) -> None:
        self.task(i, "cancelled", None if self.stop_at is not None else reason, coded)

    def fail(self, kind: str, message: str, reason: str | None = None, coded: tuple[str, dict] | None = None,
             **fields) -> str:
        """The run fails before its first task: the error, then the tasks cancelled (reason, else the message, with
        its code)."""
        self.error(kind, message, **fields)
        return self.cancel_rest("failed", reason or message, coded)

    def run(self, root: Path, want: dict) -> str:
        fw = self.framework(root)
        ctl = self.pc(fw, want) if want.get("kind") == "pc" else self.emulator(fw, want)
        if isinstance(ctl, str):  # the run ended before it connected: its result
            return ctl
        self.poll()
        if self.stop_at is not None:
            return self.cancel_rest("stopped", None)
        self.out.send("resource", state="loading")
        res = fw.resource()
        if not res.post_bundle(str(root / "resource" / "base")).wait().succeeded:
            return self.fail("resource_failed", f"could not load {root / 'resource' / 'base'}", "the resource did not load",
                             own("ResourceFailed"))
        self.out.send("resource", state="loaded")
        self.client = fw.agent_client()
        self.client.bind(res)
        self.start_agent(root, self.client.identifier)
        if not self.client.connect():
            code = self.agent.poll()
            return self.fail("agent_failed", "the bot did not connect" + (f": it exited with code {code}" if code is not None else ""),
                             "the bot did not start", own("BotNotStarted"), **({"code": code} if code is not None else {}),
                             tail=list(self.tail))
        t = fw.tasker()
        t.bind(res, ctl)
        if not t.inited:
            return self.fail("internal", "the tasker did not initialise", coded=own("TaskerFailed"))
        self.say(f"start {','.join(task['entry'] for task in self.tasks)} pid {os.getpid()} agent {self.agent.pid} "
                 f"install {root}")
        self.tasker = t
        jobs = [t.post_task(task["entry"]) for task in self.tasks]
        if self.stop_at is not None:  # a stop that came before the list was posted
            self.post_stop()
        self.follow(jobs)
        if self.stop_at is not None:
            return "stopped"
        return "succeeded" if set(self.states) == {"succeeded"} else "failed"

    # the device
    def emulator(self, fw, want: dict):
        """A controller connected to the emulator the start asks for, or the run's result when there is none."""
        device, until = self.device(fw, want)
        if device is None:
            return self.cancel_rest("failed", "no emulator to run on", own("NoEmulator"))
        self.out.send("connection", state="connecting", address=device.address)
        ctl = self.connect(fw, device, until)
        if ctl is None:
            if self.stop_at is not None:
                return self.cancel_rest("stopped", None)
            return self.fail("connect_failed", f"could not connect to {device.address}",
                             coded=own("ConnectFailed", address=device.address))
        self.out.send("connection", state="connected", address=device.address)
        self.say(f"connected {device.name} {device.address}")
        return ctl

    def pc(self, fw, want: dict):
        """The PC window controller connected to the game's window, its client area set to the start's pc_size (the
        window put back at the run's end, restore_window), or the run's result when it cannot be: no window, more than
        one, minimized, not 16:9 once the size is set, or a connect that fails."""
        windows = self.windows
        found = pc.games(windows)
        if not found:
            return self.fail("device_missing", f"no {pc.TITLE} window is open", coded=own("PcNoWindow"))
        if len(found) > 1:
            return self.fail("connect_failed", f"{len(found)} {pc.TITLE} windows are open",
                             coded=own("PcManyWindows", count=len(found)))
        hwnd = found[0]
        if (p := pc.trouble(windows.look(hwnd), aspect=False)) is None:
            self.put_back = pc.resize(windows, hwnd, want.get("pc_size", "keep"), self.say)
            p = pc.trouble(look := windows.look(hwnd))
        if p is not None:
            return self.fail("connect_failed", p.message, coded=coded(p))
        self.out.send("connection", state="connecting", address=pc.TITLE)
        ctl = fw.pc_controller(hwnd, windows)
        # .succeeded, not .connected: a custom controller's connected is a method (maa/controller.py CustomController)
        if not ctl.post_connection().wait().succeeded:
            if (p := ctl.problem) is not None:
                return self.fail("connect_failed", p.message, coded=coded(p))
            return self.fail("connect_failed", f"could not connect to the {pc.TITLE} window",
                             coded=own("ConnectFailed", address=pc.TITLE))
        self.pc_ctl = ctl
        self.out.send("connection", state="connected", address=pc.TITLE)
        self.say(f"connected the {pc.TITLE} window {look.width}x{look.height}")
        return ctl

    def restore_window(self) -> None:
        """The PC window back where and as large as it was before the run, when the run changed it."""
        if self.put_back is None:
            return
        try:
            self.put_back()
        except Exception as e:  # the run is over either way
            self.say(f"the game's window was not put back: {type(e).__name__}: {e}")

    def device(self, fw, want: dict):
        """The device to run on, MuMu started first when it is not running and the start names its instance, and when
        the connect to a MuMu it started must be done by (None for one that was running); (None, None) when there is
        none (an error says why) or the caller stopped meanwhile."""
        found = devices.ordered(fw.devices())
        address = want["address"]
        if address is None:
            if not found:
                self.error("device_missing", "no emulator is running")
            return (found[0] if found else None), None
        if (d := devices.find(found, address)) is not None:
            return d, None
        if want["mumu_index"] is None or not want["mumu_manager"]:
            self.error("device_missing", f"no device at {address}: found {', '.join(x.address for x in found) or 'none'}")
            return None, None
        self.out.send("connection", state="launching", address=address)
        self.say(f"no device at {address}: starting MuMu instance {want['mumu_index']}")
        code, said = self.launch(want["mumu_manager"], want["mumu_index"])
        if code is None:
            self.error("launch_failed", f"MuMuManager did not run: {said}")
            return None, None
        self.say(f"MuMuManager exit {code}" + (f": {said[:300]}" if said else ""))
        self.out.send("connection", state="waiting", address=address)
        start = self.now()
        end, adb_said = start + LAUNCH_LIMIT, None
        while self.now() < end:
            if not self.waited(SCAN_EVERY):
                return None, None
            if (d := devices.find(fw.devices(), address)) is None:
                continue
            # the scan lists MuMu seconds before its adb answers, and MaaFramework's connect needs `device` (#831); each
            # line says how long that look took (#839)
            asked = self.now()
            state = self.adb_state(d, end - asked)
            said = f"adb says {state} (in {self.now() - asked:.1f} s)"
            if state != "device":
                if state != adb_said:
                    self.say(f"{address} after {self.now() - start:.0f} s: {said}")
                adb_said = state
                continue
            self.say(f"{address} is up after {self.now() - start:.0f} s: {said}; connecting in {SETTLE:g} s")
            return (d, end) if self.waited(SETTLE) else (None, None)
        self.error("device_timeout", f"MuMu instance {want['mumu_index']} did not come up at {address} in {LAUNCH_LIMIT:g} s"
                   + (f": adb says {adb_said}" if adb_said else ""))
        return None, None

    def connect(self, fw, device, until):
        """A controller connected to device, or None (the caller may have stopped meanwhile). A MuMu the runner started
        gets another try each second until `until`; a device that was running gets one."""
        def attempt():
            ctl = fw.controller(device)
            ctl.post_connection().wait()
            return ctl if ctl.connected else None
        ctl = attempt()
        if ctl is not None or until is None or self.now() >= until:
            return ctl
        self.say(f"could not connect to {device.address} yet: trying each second for {until - self.now():.0f} s")
        while self.now() < until and self.waited(SCAN_EVERY):
            if (ctl := attempt()) is not None:
                return ctl
        return None

    def waited(self, seconds: float) -> bool:
        """seconds on the clock, the commands taken each TICK; False as soon as the caller stopped."""
        end = self.now() + seconds
        while True:
            self.poll()
            if self.stop_at is not None:
                return False
            if self.now() >= end:
                return True
            self.sleep(min(TICK, end - self.now()))

    # the bot
    def start_agent(self, root: Path, identifier: str) -> None:
        # MAALC_TASKER_PID: this process recognises, so the bot logs its memory at each floor (agent/memlog.py, #391)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "MAALC_TASKER_PID": str(os.getpid())}
        self.agent = subprocess.Popen(self.agent_command(root, identifier), stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=pump, args=(self.agent.stdout.fileno(), self.agent_line), daemon=True)
        self.reader.start()

    def agent_line(self, text: str) -> None:
        self.tail.append(text)
        if text.startswith(STOP_LINE):
            self.last_stop, self.last_code = text.removeprefix(STOP_LINE), None
        elif text.startswith(CODE_LINE):
            self.last_code = stop_code(text.removeprefix(CODE_LINE))
        elif text.startswith(HALT_LINE):
            self.halt = self.last_stop or text.removeprefix("[maalc] ")
            self.halt_code = self.last_code if self.last_stop else None
            self.halted.set()
        self.out.log("agent", text)

    def close_agent(self) -> None:
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception as e:  # the run is over either way
                self.say(f"disconnect failed: {e}")
        if self.agent is not None and self.agent.poll() is None:
            try:
                self.agent.wait(AGENT_END)
            except subprocess.TimeoutExpired:
                self.say(f"the bot did not end {AGENT_END:g} s after the disconnect: killed")
                self.agent.kill()
                self.agent.wait()
        if self.reader is not None:
            self.reader.join(DRAIN)

    # following the list
    def poll(self) -> None:
        """Take the commands that came: a stop, or a line the protocol refuses (reported; the run goes on). A closed
        stdin changes nothing: the run goes on and its log keeps it."""
        while (c := self.commands.poll()) is not None:
            if isinstance(c, protocol.ProtocolError):
                self.error("protocol", str(c))
            elif c == Commands.EOF:
                continue
            elif c["cmd"] == "stop":
                if self.stop_at is None:
                    self.stop_at = self.now()
                    self.say("stop requested")
                    if self.tasker is not None:
                        self.post_stop()
            else:
                self.error("protocol", f"{c['cmd']}: a run is under way, only stop is taken")

    def post_stop(self) -> None:
        self.stop_posted = self.stop_posted if self.stop_posted is not None else self.now()
        self.reposted = self.now()
        self.tasker.post_stop()

    def tick(self) -> None:
        """One look between two sleeps: the commands, a stop's re-posts and its limit, the bot still alive."""
        self.poll()
        if self.stop_posted is not None and self.tasker.running:
            if self.now() - self.reposted >= STOP_REPOST:
                self.post_stop()
            if not self.timed_out and self.now() - self.stop_posted >= STOP_LIMIT:
                self.timed_out = True
                self.error("stop_timeout", f"MaaFramework did not stop in {STOP_LIMIT:g} s: end the runner's process tree")
        self.take_pc_problem()
        if self.crash is None and self.agent.poll() is not None:
            self.reader.join(DRAIN)  # its last lines first
            code = self.agent.returncode
            self.crash, self.crash_code = f"the bot exited with code {code}", own("BotExited", code=code)
            self.error("agent_exit", self.crash, code=code, tail=list(self.tail))
            if self.stop_posted is None:
                self.post_stop()

    def take_pc_problem(self) -> None:
        """The PC window controller's problem, the first time it is seen: its error, and MaaFramework stopped while it
        still runs, so the rest of the list is cancelled with it."""
        if self.pc_reason is None and self.pc_ctl is not None and (p := self.pc_ctl.problem) is not None:
            self.pc_reason, self.pc_code = p.message, coded(p)
            self.error("device_lost", p.message)
            if self.stop_posted is None and self.tasker.running:
                self.post_stop()

    def follow(self, jobs: list) -> None:
        """Each task to its end. A task's state is read before the commands are taken, so a task found ended has
        ended before the runner took a stop: finish() then holds a stop against the task it follows only."""
        for i, job in enumerate(jobs):
            t0 = self.now()
            while True:
                detail = job.get()
                status = detail and detail.status
                if (status and status.done) or not self.tasker.running:
                    break
                if status and status.running and self.states[i] == "pending":
                    self.task(i, "running")
                self.tick()
                self.sleep(TICK)
            self.finish(i, job.get(), self.now() - t0, jobs[i + 1] if i + 1 < len(jobs) else None)
        while self.tasker.running:
            self.tick()
            self.sleep(TICK)

    def finish(self, i: int, detail, seconds: float, after=None) -> None:
        """A task that ran ends as MaaFramework says; stopped when the caller's stop came first; failed, with the bot's
        reason, when the bot stopped the whole list in it. MaaFramework says succeeded of a task whose agent action
        returns normally after post_stop (#832), the bot's own post_stop too (#870). The runner decides it, not the
        actions: a stop is no failure of theirs, and their waits end on it as on a timeout (agent/actions.py until).
        after: the job of the task that follows it in the list, None for the last."""
        status = detail and detail.status
        ran = self.states[i] == "running" or bool(status and status.done)
        self.take_pc_problem()  # held in the task's last tick, after the runner's last look (a refused StopApp)
        if ran and self.stop_at is None and self.pc_reason is not None:
            self.task(i, "failed", self.pc_reason, self.pc_code)
        elif ran and self.stop_at is None and (halt := self.halt_reason(after)) is not None:
            self.task(i, "failed", halt, self.halt_code)
        elif self.stop_at is None and status and status.succeeded:
            self.task(i, "succeeded")
        elif ran:
            self.task(i, "stopped" if self.stop_at is not None else "failed")
        else:
            self.cancel(i, *((None, None) if self.stop_at is not None else self.why_unrun()))
        self.say(f"{self.tasks[i]['entry']} status={self.states[i]} t={seconds:.0f}s")
        for n in (detail.nodes[-NODES:] if detail else []):
            self.say(f"node {n.name} {n.completed}")

    def halt_reason(self, after) -> str | None:
        """The bot's reason when it stopped the whole list in the task that just ended, else None. Not in it when the
        task after it ran: the runner looks every TICK, and that one may start and stop the list in between. The
        account-level stop line comes through a pipe the bot's post_stop does not wait for, so after a stop line of
        the bot (logged before its evidence, seconds ahead of the post_stop) it is waited for (await_halt)."""
        status = after is not None and (detail := after.get()) and detail.status
        if status and (status.done or status.running):
            return None
        return self.await_halt() if self.last_stop is not None else self.halt

    def await_halt(self) -> str | None:
        """The bot's account-level stop reason, waited for HALT_WAIT once a run: the next task has the same answer."""
        if self.halt is None and not self.halt_awaited:
            self.halt_awaited = True
            self.halted.wait(HALT_WAIT)
        return self.halt

    def why_unrun(self) -> tuple[str, tuple[str, dict] | None]:
        """Why a task never ran though nobody stopped the run, with the reason's code: the bot exited, or it stopped the
        whole list (its reason, which it logged before the post_stop that the tasker's stop came from), or the PC window
        controller held a problem."""
        if self.pc_reason:
            return self.pc_reason, self.pc_code
        if self.crash:
            return self.crash, self.crash_code
        if halt := self.await_halt():
            return halt, self.halt_code
        return "MaaFramework stopped the task list", own("ListStopped")
