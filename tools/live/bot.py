"""Run maalc headless from an install, and the chores around a live run.

    uv run python tools/live/bot.py run --install DIR --log run.log [--task MirrorDungeon[,ExpLuxcavation...]] [--port 16384]
    uv run python tools/live/bot.py prep --install DIR [--source INSTALL] [--set KEY=VALUE ...]
    uv run python tools/live/bot.py awake [--minutes 240]

**run** runs the tasks through the install's runner (`DIR/runner/`, #812), the one the settings window and the
daily use: the install's resource/base, agent/main.py and maafw/ (its patched MaaFramework.dll), on the MuMu instance
at `--port`. It writes every log line the runner sends to `--log` at the line's own wall time (`HH:MM:SS.fff <line>`):
the runner's `[run]` lines, the bot's `[maalc]` lines and the controller's touch lines that `tools/live/evidence.py`
reads; the runner keeps the same lines in DIR/logs/runner/. `--task A,B` posts several tasks up front, as a client
queues its task list, and runs them in turn (#364). It exits 0 when every task succeeded. Start it detached
(`tools/live/queue.py detach`), as the maalc-live-test skill says. Each task reads its options from DIR's
`config/settings.json` at its start (#813): `prep --set` sets them; the runner gets each task with no override. A task
DIR's interface.json lacks stops it, exit 1, before the runner starts. A runner that reports it cannot stop
MaaFramework (after the bot exited mid-run) has its process tree ended.

**prep** copies `config/settings.json`, `config/maa_option.json` and, when the source still has one, `state/`
from `--source` (default the main checkout's install/) into DIR; the bot's first start turns the old rotation cursor
into the team queue's head and removes the state files with `state/` (#501). Then it sets each dotted KEY to VALUE
(JSON, else a string):
`--set run.runs=1 --set run.difficulty=normal --set run.weekly_bonus_use=none`, `--set run.start_team=t3`,
`--set luxcavation.exp.team=t3`; a list's item goes by its id, `--set teams.t3.heal=revive`. A key it cannot set stops
it before DIR is touched. DIR comes from `tools/install.py` (a worktree's install/) or a copy of one under
`.local/scratch/<task>/`.

**awake** keeps the display and the machine on for that many minutes: a recording needs the screen awake
(screen-record). Windows only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import main_checkout  # noqa: E402

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2


def clock() -> str:
    return f"{datetime.datetime.now():%H:%M:%S.%f}"[:-3]


# s the output is still read once the child has exited: what it printed is in the pipe by then and reads in
# milliseconds (the exit line came 0.05 s after the last one in the 2026-11-13 runs, #663)
DRAIN = 5.0


def stamped(cmd, log: Path, clock=clock, send: str | None = None, line=None) -> int:
    """Run cmd, appending each line it prints to log with the wall time; its exit code. send: a line written to its
    stdin once it started (the runner's start command), which stays open until it exits. line(text): the (time, text)
    log gets for one line it printed, or None for none (the runner's events, RunnerEvents); by default the line as it
    came, at clock(). The run ends with the child, not with the end of its output: a process the child started can
    inherit the output and outlive it, as the adb server that MaaFramework's `adb kill-server` and `adb connect` start
    does (#663), and it never closes it. That server is meant to outlive the run, so it is left running; the run stops
    reading instead."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    line = line or (lambda text: (clock(), text))
    read, write = os.pipe()
    with open(log, "a", encoding="utf-8", buffering=1) as f:
        try:
            p = subprocess.Popen(cmd, stdout=write, stderr=subprocess.STDOUT, env=env,
                                 stdin=subprocess.PIPE if send is not None else None)
        except BaseException:
            os.close(read)
            raise
        finally:
            os.close(write)
        f.write(f"{clock()} [run] child pid {p.pid}\n")
        if send is not None:
            p.stdin.write(send.encode("utf-8") + b"\n")
            p.stdin.flush()
        lock, done, tail = threading.Lock(), threading.Event(), bytearray()  # tail: what follows the last newline

        def write_lines(raw: bytes):
            # a lone \r ends a line too, as it did when the output was read in text mode
            for part in raw.rstrip(b"\r").split(b"\r"):
                if stamp := line(part.decode("utf-8", "replace").rstrip()):
                    f.write(f"{stamp[0]} {stamp[1]}\n")

        def pump():
            # os.read, not a file object: the reader may still be blocked in it when this process exits, and a
            # buffered file's lock held by a daemon thread is fatal at interpreter shutdown
            while chunk := os.read(read, 65536):
                with lock:
                    if done.is_set():
                        return
                    *lines, rest = (tail + chunk).split(b"\n")
                    tail[:] = rest
                    for raw in lines:
                        write_lines(raw)
            os.close(read)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            code = p.wait()
            reader.join(DRAIN)
        finally:
            with lock:
                done.set()
                if tail:
                    write_lines(bytes(tail))
        if reader.is_alive():
            f.write(f"{clock()} [run] output still open {DRAIN:g} s after the child exited: a process it started holds it\n")
        f.write(f"{clock()} [run] exit {code}\n")
        if p.stdin:
            try:
                p.stdin.close()
            except OSError:  # the child is gone and its end with it
                pass
    return code


def kill_tree(pid: int) -> None:
    """End pid and every process under it (taskkill /T; the live tools run on Windows, elsewhere pid alone ends)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        os.kill(pid, 9)


class RunnerEvents:
    """The runner's events (runner/protocol.py) as run.log lines: a log event at its own time, the rest none (the
    runner logs its errors and task states too). Its pid comes with ready; a stop_timeout (MaaFramework does not stop,
    after the bot exited mid-run) ends its process tree, as the window would."""

    def __init__(self, clock=clock, kill=kill_tree):
        self.clock, self.kill, self.pid, self.result = clock, kill, None, None

    def __call__(self, text: str):
        try:
            e = json.loads(text)
        except ValueError:
            return self.clock(), text  # not the protocol: kept as it came
        if not isinstance(e, dict):
            return self.clock(), text
        kind = e.get("event")
        if kind == "log":
            return e.get("t", self.clock()), e.get("line", "")
        if kind == "ready":
            self.pid = e.get("pid")
        elif kind == "end":
            self.result = e.get("result")
        elif kind == "error" and e.get("kind") == "stop_timeout" and self.pid:
            self.kill(self.pid)
            return self.clock(), f"[run] the runner cannot stop MaaFramework: its process tree {self.pid} ended"
        return None


def run(root: Path, tasks: list[str], port: int, log: Path) -> int:
    """The tasks through root's runner, its log lines in log; the runner's exit code (0: every task succeeded)."""
    said = []
    try:
        jobs = plan(root, tasks)
    except SystemExit as e:
        said.append(str(e))
        jobs = None
    runner = root / "runner" / "__main__.py"
    if jobs is not None and not runner.is_file():
        said.append(f"[run] {root} has no runner/: assemble the install with tools/install.py")
        jobs = None
    with open(log, "a", encoding="utf-8") as f:
        f.writelines(f"{clock()} {line}\n" for line in said)
    if jobs is None:
        return 1
    # v: runner/protocol.py VERSION (tests/test_live_bot.py ties the two)
    start = {"v": 1, "cmd": "start", "root": str(root), "device": {"address": f"127.0.0.1:{port}"},
             "tasks": [{"entry": entry, "override": override} for _, entry, override in jobs]}
    return stamped([sys.executable, "-u", str(runner)], log, send=json.dumps(start, ensure_ascii=False),
                   line=RunnerEvents())


def plan(root: Path, tasks: list[str]) -> list[tuple[str, str, dict]]:
    """(task, entry, override) of each task: its entry node from root's interface.json (whole-line // comments dropped),
    no override. A task the interface lacks stops it before any task is posted."""
    lines = (root / "interface.json").read_text(encoding="utf-8").splitlines()
    entries = {t["name"]: t["entry"] for t in json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))["task"]}
    for name in tasks:
        if name not in entries:
            raise SystemExit(f"[run] interface.json has no task {name} (tasks: {', '.join(entries)}): stopped before posting any task")
    return [(name, entries[name], {}) for name in tasks]


def prep(install: Path, source: Path, sets: list[str]) -> dict:
    """Copy source's config (and state/) into install, with each KEY=VALUE of sets set; SystemExit before install is
    touched on a key it cannot set."""
    settings = json.loads((source / "config/settings.json").read_text(encoding="utf-8"))
    for item in sets:
        key, value = item.split("=", 1)
        *parents, last = key.split(".")
        node = settings
        for k in parents:
            if isinstance(node, list):
                node = next((i for i in node if isinstance(i, dict) and i.get("id") == k), None)
                if node is None:
                    raise SystemExit(f"prep: {key}: no item with id {k!r}")
            else:
                node = node.setdefault(k, {})
        if isinstance(node, list):
            raise SystemExit(f"prep: {key}: {last!r} names a list item, not a key")
        try:
            node[last] = json.loads(value)
        except ValueError:
            node[last] = value
    (install / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "config/maa_option.json", install / "config/maa_option.json")
    if (source / "state").is_dir():
        shutil.copytree(source / "state", install / "state", dirs_exist_ok=True)
    (install / "config/settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def awake(minutes: float, set_state=None, sleep=time.sleep) -> None:
    if set_state is None:
        import ctypes

        set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    try:
        sleep(minutes * 60)
    finally:
        set_state(ES_CONTINUOUS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--install", type=Path, required=True)
    p.add_argument("--task", default="MirrorDungeon", help="a PI task, or several, comma-separated, run in turn")
    p.add_argument("--port", type=int, default=16384)
    p.add_argument("--log", type=Path, required=True)
    p = sub.add_parser("prep")
    p.add_argument("--install", type=Path, required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--set", action="append", default=[])
    sub.add_parser("awake").add_argument("--minutes", type=float, default=240)
    a = ap.parse_args(argv)

    if a.command == "run":
        return run(a.install.resolve(), a.task.split(","), a.port, a.log)
    if a.command == "prep":
        prep(a.install, a.source or main_checkout() / "install", a.set)
        print(f"prep: {a.install / 'config/settings.json'} written, {len(a.set)} key(s) set", flush=True)
    elif a.command == "awake":
        print(f"awake for {a.minutes:g} min", flush=True)
        awake(a.minutes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
