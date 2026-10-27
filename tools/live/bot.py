"""Run maalc headless from an install, and the chores around a live run.

    uv run python tools/live/bot.py run --install DIR --log run.log [--task MirrorDungeon[,ExpLuxcavation...]] [--port 16384]
    uv run python tools/live/bot.py prep --install DIR [--source INSTALL] [--set KEY=VALUE ...]
    uv run python tools/live/bot.py awake [--minutes 240]

**run** starts the task the way MXU does (the install's resource/base, agent/main.py and maafw/, so its
patched MaaFramework.dll) on the MuMu instance at `--port`, and writes every line the tasker and the agent
print to `--log`, each with its wall time (`HH:MM:SS.fff <line>`): the `[maalc]` lines and the controller's
touch lines that `tools/live/evidence.py` reads. `--task A,B` posts several tasks up front, as a client queues its
task list, and runs them in turn (#364). It exits 0 when every task succeeded. Start it detached
(`tools/live/queue.py detach`), as the maalc-live-test skill says.

**prep** copies `config/settings.json`, `config/maa_option.json` and `state/` from `--source` (default the
main checkout's install/) into DIR, then sets each dotted KEY to VALUE (JSON, else a string):
`--set run.runs=1 --set run.difficulty=normal --set run.weekly_bonus_use=none`. DIR comes from
`tools/install.py` (a worktree's install/) or a copy of one under `.local/scratch/<task>/`.

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
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import main_checkout  # noqa: E402

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2


def clock() -> str:
    return f"{datetime.datetime.now():%H:%M:%S.%f}"[:-3]


def stamped(cmd, log: Path, clock=clock) -> int:
    """Run cmd, appending each line it prints to log with the wall time; its exit code."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with open(log, "a", encoding="utf-8", buffering=1) as f:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", env=env)
        f.write(f"{clock()} [run] child pid {p.pid}\n")
        for line in p.stdout:
            f.write(f"{clock()} {line.rstrip()}\n")
        code = p.wait()
        f.write(f"{clock()} [run] exit {code}\n")
    return code


def run_tasks(t, tasks: list[str], say=print, sleep=time.sleep) -> list[str]:
    """Post the whole list up front, as a client queues its task list (an account-level stop's post_stop leaves the
    rest pending, unrun), then follow each in turn by its detail until it is done or the tasker has stopped, as MXU
    does (G1: wait() and status go through a runner id a clear_cache drops), and return only once the tasker has
    stopped, so the agent is not closed under a task still running: their states."""
    states = []
    for name, job in [(name, t.post_task(name)) for name in tasks]:
        t0 = time.time()
        while (detail := job.get()) and not detail.status.done and t.running:
            sleep(1)
        detail = job.get()  # read again: the tasker may have stopped after the read above
        s = detail and detail.status
        state = "none" if not s else "succeeded" if s.succeeded else "failed" if s.failed else "running" if s.running else "pending"
        say(f"[run] {name} status={state} t={time.time() - t0:.0f}s")
        for n in (detail.nodes[-10:] if detail else []):
            say(f"[run] node {n.name} {n.completed}")
        states.append(state)
    while t.running:
        sleep(1)
    return states


def tasker(root: Path, tasks: list[str], port: int) -> int:
    """The tasks, run in this process in turn: MaaFramework from root/maafw, the agent as a child."""
    os.environ["MAAFW_BINARY_PATH"] = str(root / "maafw")
    from maa.agent_client import AgentClient
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit

    from live.device import connect

    Toolkit.init_option(str(root / "debug"))
    Tasker.set_save_on_error(True)
    ctl = connect(port)
    res = Resource()
    res.post_bundle(str(root / "resource/base")).wait()
    client = AgentClient()
    client.bind(res)
    agent = subprocess.Popen([sys.executable, "-u", str(root / "agent/main.py"), client.identifier])
    client.connect()
    t = Tasker()
    t.bind(res, ctl)
    print(f"[run] start {','.join(tasks)} pid {os.getpid()} agent {agent.pid} install {root}", flush=True)
    states = run_tasks(t, tasks, lambda line: print(line, flush=True))
    client.disconnect()
    agent.terminate()
    return 0 if set(states) == {"succeeded"} else 1


def prep(install: Path, source: Path, sets: list[str]) -> dict:
    (install / "config").mkdir(parents=True, exist_ok=True)
    for name in ("settings.json", "maa_option.json"):
        shutil.copy2(source / "config" / name, install / "config" / name)
    shutil.copytree(source / "state", install / "state", dirs_exist_ok=True)
    path = install / "config/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    for item in sets:
        key, value = item.split("=", 1)
        *parents, last = key.split(".")
        node = settings
        for k in parents:
            node = node.setdefault(k, {})
        try:
            node[last] = json.loads(value)
        except ValueError:
            node[last] = value
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
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
    for name in ("run", "tasker"):
        p = sub.add_parser(name)
        p.add_argument("--install", type=Path, required=True)
        p.add_argument("--task", default="MirrorDungeon", help="a PI task, or several, comma-separated, run in turn")
        p.add_argument("--port", type=int, default=16384)
        if name == "run":
            p.add_argument("--log", type=Path, required=True)
    p = sub.add_parser("prep")
    p.add_argument("--install", type=Path, required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--set", action="append", default=[])
    sub.add_parser("awake").add_argument("--minutes", type=float, default=240)
    a = ap.parse_args(argv)

    if a.command == "run":
        root = a.install.resolve()
        return stamped([sys.executable, "-u", __file__, "tasker", "--install", str(root), "--task", a.task, "--port", str(a.port)], a.log)
    if a.command == "tasker":
        return tasker(a.install, a.task.split(","), a.port)
    if a.command == "prep":
        print(prep(a.install, a.source or main_checkout() / "install", a.set).get("run"))
    elif a.command == "awake":
        print(f"awake for {a.minutes:g} min", flush=True)
        awake(a.minutes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
