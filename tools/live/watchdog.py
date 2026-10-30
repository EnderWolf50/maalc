"""The list of delegated tasks the scheduled watchdog watches, and its tick that reports only news.

  python tools/live/watchdog.py add <taskId> <task> <label>
  python tools/live/watchdog.py done <taskId|label>
  python tools/live/watchdog.py list
  python tools/live/watchdog.py tick [--status <taskId>=<state> ...]

The list is `agents.tsv` in `.local/scratch/` of the main checkout: one `taskId<TAB>live task or -<TAB>label`
line per delegated task. The CLI writes it, so nobody types a task id (they hold `%3A`) by hand: ids are stored
as given and matched either way, encoded or decoded. `add` to an empty list and `done` on the last line print
one line saying the watchdog schedule must be switched on or off (the schedule is the coordinator's).

`tick` is what the scheduled prompt runs (`docs/agents/watchdog-prompt.md`). A script cannot call `task_status`, so
the agent passes the states it fetched, one `--status <taskId>=<state>` per list line. `tick` runs `queue.py status`
and the latest CI run of `main` itself, compares them with `agents.state.json` (beside `agents.tsv`: what it
already reported) and prints one event per line, each with the action to take, or exactly `NOTHING NEW`. An event
prints once; the state file is what keeps a question already waiting on the user from being posted again.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import local_dir  # noqa: E402

REPO = "EnderWolf50/maalc"
HEADER = [
    "# Active delegated tasks (watchdog list). One per line: taskId<TAB>live-task-name-or-dash<TAB>label",
    "# Written by tools/live/watchdog.py; do not edit by hand.",
]
NOTHING = "NOTHING NEW"
STRANDED_MIN = 60  # minutes a holder may sit after its bot ended before the tick calls it stranded
# `result_available` is task_status's workState for a task with a result and no live child work; `working` and
# `waiting_for_children` are not listed on purpose: a finished turn with live child work is not done.
FINISHED = {"result_available", "completed", "complete", "succeeded", "success", "done"}
FAILED = {"failed", "error", "errored", "interrupted", "cancelled", "canceled", "rate_limited", "overloaded"}
RESUME_MSG = ("You were interrupted. Run `uv run python tools/live/queue.py resume --task {task}` and "
              "`queue.py status`, read .local/scratch/{task}/next.md, and continue from there; never start a second hold or bot.")


class Row:
    def __init__(self, task_id: str, task: str, label: str):
        self.task_id, self.task, self.label = task_id, task, label

    def key(self) -> str:
        return unquote(self.task_id)

    def matches(self, ref: str) -> bool:
        return ref in (self.task_id, self.label) or unquote(ref) == self.key()


def load(path: Path) -> list[Row]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append(Row(*parts))
    return rows


def save(path: Path, rows: list[Row]) -> None:
    lines = HEADER + [f"{r.task_id}\t{r.task}\t{r.label}" for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add(path: Path, task_id: str, task: str, label: str) -> list[str]:
    rows = load(path)
    if any(r.key() == unquote(task_id) for r in rows):
        return [f"{label}: already in the list ({len(rows)} line(s)); nothing written"]
    save(path, rows + [Row(task_id, task, label)])
    out = [f"added {label} ({len(rows) + 1} line(s))"]
    if not rows:
        out.append("the list was empty: switch the watchdog schedule ON")
    return out


def done(path: Path, ref: str) -> list[str]:
    rows = load(path)
    gone = [r for r in rows if r.matches(ref)]
    if not gone:
        return [f"{ref}: no such line; the list has {len(rows)}"]
    keep = [r for r in rows if r not in gone]
    save(path, keep)
    out = [f"removed {', '.join(r.label for r in gone)} ({len(keep)} line(s) left)"]
    if not keep:
        out.append("the list is empty: switch the watchdog schedule OFF once `queue.py status` shows no holder")
    return out


def listing(path: Path) -> list[str]:
    return [f"{r.task_id}\t{r.task}\t{r.label}" for r in load(path)] or ["(empty)"]


def sh(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else ""


def queue_status() -> str:
    return sh([sys.executable, str(Path(__file__).with_name("queue.py")), "status"])


def main_ci() -> str:
    return sh(["gh", "run", "list", "-R", REPO, "--branch", "main", "--limit", "1", "--json", "conclusion,headSha"])


STRANDED = re.compile(r"^\s*(?:RUNNING|#\d+)\s+(\S+) \(pid \d+\) — bot ended (\d+) min ago, waiting for the agent")


def stranded_holders(queue_text: str) -> list[tuple[str, int]]:
    out = []
    for line in queue_text.splitlines():
        if m := STRANDED.match(line):
            out.append((m.group(1), int(m.group(2))))
    return out


def tick(rows: list[Row], statuses: dict[str, str], queue_text: str, ci_json: str, state: dict,
         hour: str) -> tuple[list[str], dict]:
    """(events, new state). An event prints once: its key is in `state["reported"]` afterwards."""
    reported = set(state.get("reported", []))
    events: list[str] = []

    def fire(key: str, text: str) -> None:
        if key not in reported:
            reported.add(key)
            events.append(text)

    live = {r.key() for r in rows}
    for r in rows:
        s = statuses.get(r.key(), "").lower()
        if s in FINISHED:
            fire(f"done|{r.key()}", f"FINISHED {r.label}: relay its result to the user, decisions first, then "
                                    f"`uv run python tools/live/watchdog.py done {r.label}`")
        elif s in FAILED:
            fire(f"failed|{r.key()}|{hour}", f"FAILED {r.label} ({s}) with no result: resume it once with t3_thread_send "
                 f"(mode auto, clientRequestId resume-{r.label}-{hour}), message: "
                 + RESUME_MSG.format(task=r.task if r.task != "-" else r.label))
    for name, mins in stranded_holders(queue_text):
        if mins > STRANDED_MIN:
            owner = next((r for r in rows if r.task == name or r.label == name), None)
            who = f"tell {owner.label} to resume (as for FAILED)" if owner else "its owner is not in the list: report it to the user"
            fire(f"stranded:{name}", f"STRANDED holder {name}: bot ended {mins} min ago, no done file; {who}")
    try:
        runs = json.loads(ci_json) if ci_json.strip() else []
    except ValueError:
        runs = []
    if runs:
        sha, concl = runs[0].get("headSha", "")[:8], runs[0].get("conclusion", "")
        if concl == "failure":
            fixing = any("main" in r.label.lower() or "ci" in r.label.lower() for r in rows)
            fire(f"red:{sha}", f"MAIN RED at {sha}: " + ("a listed task may be fixing it; check its label" if fixing
                                                         else "no listed task is fixing it; tell the user once"))
            state["main_red"] = True
        elif concl == "success" and state.get("main_red"):
            events.append(f"MAIN GREEN again at {sha}")
            state["main_red"] = False
    # forget what belongs to tasks that left the list (an id can come back), keep holder and CI keys
    reported = {k for k in reported if not k.startswith(("done|", "failed|")) or k.split("|")[1] in live}
    state["reported"] = sorted(reported)
    return events, state


def parse_statuses(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        tid, _, st = item.rpartition("=")
        out[unquote(tid)] = st
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, help="the folder of agents.tsv (default .local/scratch/ of the main checkout)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    for n in ("task_id", "task", "label"):
        a_.add_argument(n)
    sub.add_parser("done").add_argument("ref", help="a task id (encoded or not) or a label")
    sub.add_parser("list")
    t = sub.add_parser("tick")
    t.add_argument("--status", action="append", default=[], metavar="TASKID=STATE")
    a = ap.parse_args(argv)
    folder = a.dir or local_dir("scratch")
    path = folder / "agents.tsv"
    if a.cmd == "add":
        out = add(path, a.task_id, a.task, a.label)
    elif a.cmd == "done":
        out = done(path, a.ref)
    elif a.cmd == "list":
        out = listing(path)
    else:
        state_path = folder / "agents.state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        events, state = tick(load(path), parse_statuses(a.status), queue_status(), main_ci(), state, time.strftime("%Y%m%d%H"))
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        out = events or [NOTHING]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
