"""One command of the runner: a scan, or a start that runs a task list to its end and reports every step as events.

A start picks the device (starting MuMu when it is not running), connects, loads the install's resource, starts the
bot (agent/main.py) as a child, posts the whole task list up front, as a client queues its list (an account-level
stop's post_stop then leaves the rest unrun, #364), and follows each task by its detail until it is done or the tasker
has stopped (G1: wait() and status go through a runner id a clear_cache drops). It returns once the tasker has
stopped, so the bot is not closed under a task still running.

A task ends succeeded or failed as MaaFramework says; stopped when the caller's stop came while it ran; cancelled when
it never ran: after a stop, after the bot stopped the whole list (the reason it logged comes with it), after the bot
exited, or when the run failed before its first task.
"""
from __future__ import annotations

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

from runner import devices, protocol, runlog

ROOT = Path(__file__).resolve().parent.parent  # the install: runner/ sits beside agent/ and resource/

TICK = 0.5  # s between two looks at the running task and the commands
STOP_REPOST = 1.0  # s between two post_stop while the tasker still runs (MaaFramework takes one at a time)
STOP_LIMIT = 60.0  # s a stop may take before the runner reports it cannot stop; the caller then ends its tree
LAUNCH_LIMIT = 120.0  # s a started MuMu has to show up in the scan
SCAN_EVERY = 1.0  # s between two scans while it boots
SETTLE = 5.0  # s after it shows up before the runner connects: adb answers before the instance is ready
TAIL = 20  # last lines of the bot an exit report quotes
AGENT_END = 5.0  # s the bot has to end after the disconnect (its AgentServer shuts down) before it is killed
DRAIN = 2.0  # s the bot's output is read on after it exits: a process it started may hold the pipe (#663)
HALT_WAIT = 1.0  # s to wait for the bot's account-level stop line once the tasker stopped on its own
NODES = 10  # nodes of each task the run log lists when it ends
# agent/actions.py stop(): its first line names the reason; an account-level stop adds the second before post_stop
STOP_LINE = "[maalc] stop: "
HALT_LINE = "[maalc] account-level stop"
ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2


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


def pump(fd: int, each, stop=None) -> None:
    """Hand each line read from fd to each, until its end (or stop is set). os.read, not a file object: the reader may
    still be blocked in it when the process exits, and a buffered file's lock held by a daemon thread is fatal at
    interpreter shutdown."""
    rest = bytearray()
    while chunk := os.read(fd, 65536):
        for text in split_lines(chunk, rest):
            each(text)
        if stop is not None and stop.is_set():
            return
    if rest:
        each(bytes(rest).decode("utf-8", "replace").rstrip())


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
    launch(manager, index) starts a MuMu instance (devices.launch); awake() keeps the machine on (keep_awake)."""

    def __init__(self, out: Out, framework, commands: Commands, *, sleep=time.sleep, monotonic=time.monotonic,
                 agent_command=agent_command, launch=devices.launch, awake=keep_awake):
        self.out, self.framework, self.commands = out, framework, commands
        self.sleep, self.now, self.agent_command, self.launch, self.awake = sleep, monotonic, agent_command, launch, awake
        self.tasker = self.client = self.agent = self.reader = None
        # stop_at: when the caller's stop came; stop_posted, reposted: the first post_stop (the caller's or the
        # runner's own once the bot exited) and the last one
        self.stop_at = self.stop_posted = self.reposted = self.crash = self.halt = self.last_stop = None
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

    def task(self, i: int, state: str, reason: str | None = None) -> None:
        self.states[i] = state
        self.out.send("task", index=i, entry=self.tasks[i]["entry"], state=state,
                      **({"reason": reason} if reason is not None else {}))

    # scan
    def scan(self) -> str:
        found = devices.ordered(self.framework(ROOT).devices())
        self.out.send("devices", devices=[devices.describe(d) for d in found])
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
                    result = self.cancel_rest("failed", f"the runner failed: {type(e).__name__}")
                finally:
                    self.close_agent()
            self.out.settle()
            self.say(f"end {result}")
            self.out.send("end", result=result)
        finally:
            self.out.close_log()
        return result

    def cancel_rest(self, result: str, reason: str | None) -> str:
        """Every task not yet ended is cancelled (with the reason, unless the caller stopped the run): the result."""
        for i, state in enumerate(self.states):
            if state in ("pending", "running"):
                self.cancel(i, reason)
        return "stopped" if self.stop_at is not None else result

    def cancel(self, i: int, reason: str | None) -> None:
        self.task(i, "cancelled", None if self.stop_at is not None else reason)

    def fail(self, kind: str, message: str, reason: str | None = None, **fields) -> str:
        """The run fails before its first task: the error, then the tasks cancelled (reason, else the message)."""
        self.error(kind, message, **fields)
        return self.cancel_rest("failed", reason or message)

    def run(self, root: Path, want: dict) -> str:
        fw = self.framework(root)
        device = self.device(fw, want)
        if device is None:
            return self.cancel_rest("failed", "no emulator to run on")
        self.out.send("connection", state="connecting", address=device.address)
        ctl = fw.controller(device)
        ctl.post_connection().wait()
        if not ctl.connected:
            return self.fail("connect_failed", f"could not connect to {device.address}")
        self.out.send("connection", state="connected", address=device.address)
        self.say(f"connected {device.name} {device.address}")
        self.poll()
        if self.stop_at is not None:
            return self.cancel_rest("stopped", None)
        self.out.send("resource", state="loading")
        res = fw.resource()
        if not res.post_bundle(str(root / "resource" / "base")).wait().succeeded:
            return self.fail("resource_failed", f"could not load {root / 'resource' / 'base'}", "the resource did not load")
        self.out.send("resource", state="loaded")
        self.client = fw.agent_client()
        self.client.bind(res)
        self.start_agent(root, self.client.identifier)
        if not self.client.connect():
            code = self.agent.poll()
            return self.fail("agent_failed", "the bot did not connect" + (f": it exited with code {code}" if code is not None else ""),
                             "the bot did not start", **({"code": code} if code is not None else {}), tail=list(self.tail))
        t = fw.tasker()
        t.bind(res, ctl)
        if not t.inited:
            return self.fail("internal", "the tasker did not initialise")
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
    def device(self, fw, want: dict):
        """The device to run on, MuMu started first when it is not running and the start names its instance; None
        when there is none (an error says why) or the caller stopped meanwhile."""
        found = devices.ordered(fw.devices())
        address = want["address"]
        if address is None:
            if not found:
                self.error("device_missing", "no emulator is running")
            return found[0] if found else None
        if (d := devices.find(found, address)) is not None:
            return d
        if want["mumu_index"] is None or not want["mumu_manager"]:
            self.error("device_missing", f"no device at {address}: found {', '.join(x.address for x in found) or 'none'}")
            return None
        self.out.send("connection", state="launching", address=address)
        self.say(f"no device at {address}: starting MuMu instance {want['mumu_index']}")
        code, said = self.launch(want["mumu_manager"], want["mumu_index"])
        if code is None:
            self.error("launch_failed", f"MuMuManager did not run: {said}")
            return None
        self.say(f"MuMuManager exit {code}" + (f": {said[:300]}" if said else ""))
        self.out.send("connection", state="waiting", address=address)
        end = self.now() + LAUNCH_LIMIT
        while self.now() < end:
            self.poll()
            if self.stop_at is not None:
                return None
            self.sleep(SCAN_EVERY)
            if (d := devices.find(fw.devices(), address)) is not None:
                self.say(f"{address} is up after {LAUNCH_LIMIT - (end - self.now()):.0f} s; connecting in {SETTLE:g} s")
                settle = self.now() + SETTLE
                while self.now() < settle:
                    self.poll()
                    if self.stop_at is not None:
                        return None
                    self.sleep(min(TICK, settle - self.now()))
                return d
        self.error("device_timeout", f"MuMu instance {want['mumu_index']} did not come up at {address} in {LAUNCH_LIMIT:g} s")
        return None

    # the bot
    def start_agent(self, root: Path, identifier: str) -> None:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        self.agent = subprocess.Popen(self.agent_command(root, identifier), stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=pump, args=(self.agent.stdout.fileno(), self.agent_line), daemon=True)
        self.reader.start()

    def agent_line(self, text: str) -> None:
        self.tail.append(text)
        if text.startswith(STOP_LINE):
            self.last_stop = text.removeprefix(STOP_LINE)
        elif text.startswith(HALT_LINE):
            self.halt = self.last_stop or text.removeprefix("[maalc] ")
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
        if self.crash is None and self.agent.poll() is not None:
            self.reader.join(DRAIN)  # its last lines first
            code = self.agent.returncode
            self.crash = f"the bot exited with code {code}"
            self.error("agent_exit", self.crash, code=code, tail=list(self.tail))
            if self.stop_posted is None:
                self.post_stop()

    def follow(self, jobs: list) -> None:
        for i, job in enumerate(jobs):
            t0 = self.now()
            while True:
                self.tick()
                detail = job.get()
                status = detail and detail.status
                if (status and status.done) or not self.tasker.running:
                    break
                if status and status.running and self.states[i] == "pending":
                    self.task(i, "running")
                self.sleep(TICK)
            self.finish(i, job.get(), self.now() - t0)
        while self.tasker.running:
            self.tick()
            self.sleep(TICK)

    def finish(self, i: int, detail, seconds: float) -> None:
        status = detail and detail.status
        ran = self.states[i] == "running" or bool(status and status.done)
        if status and status.succeeded:
            self.task(i, "succeeded")
        elif ran:
            self.task(i, "stopped" if self.stop_at is not None else "failed")
        else:
            self.cancel(i, None if self.stop_at is not None else self.why_unrun())
        self.say(f"{self.tasks[i]['entry']} status={self.states[i]} t={seconds:.0f}s")
        for n in (detail.nodes[-NODES:] if detail else []):
            self.say(f"node {n.name} {n.completed}")

    def why_unrun(self) -> str:
        """Why a task never ran though nobody stopped the run: the bot exited, or it stopped the whole list (its
        reason, which it logged before the post_stop that the tasker's stop came from)."""
        if self.crash:
            return self.crash
        if self.halt is None and not self.halt_awaited:  # once: the next unrun task has the same answer
            self.halt_awaited = True
            self.halted.wait(HALT_WAIT)
        return self.halt or "MaaFramework stopped the task list"
