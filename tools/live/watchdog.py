"""The list of delegated tasks and launched threads the scheduled watchdog watches, and its tick that reports only news.

  python tools/live/watchdog.py add <id> <task> <label>
  python tools/live/watchdog.py done <id|label>
  python tools/live/watchdog.py list
  python tools/live/watchdog.py tick [--status <id>=<state> ...] [--reported <id> ...]

The list is `agents.tsv` in `.local/scratch/` of the main checkout: one `id<TAB>live task or -<TAB>label` line per
`delegate_task` task id (`node:delegated-task:...`) or `t3_thread_launch` thread id (any other id). The CLI writes
it, so nobody types an id (they hold `%3A`) by hand: ids are stored as given and matched either way, encoded or
decoded. `list` adds a last column, the tool that reads the line: `task_status` or `t3_thread_read`. `add` to an
empty list and `done` on the last line print one line saying the watchdog schedule must be switched on or off (the
schedule is the coordinator's).

`tick` is what the scheduled prompt runs (`docs/agents/watchdog-prompt.md`). A script cannot call those tools, so the
agent passes the states it fetched, one `--status <id>=<state>` per list line, plus one `--reported <id>` per thread
whose latest run sent its report to the main thread: a thread whose turn ended without one may be waiting on a
question (ENDED). `tick` runs `queue.py status` and the latest CI run of `main` itself, compares them with
`agents.state.json` (beside `agents.tsv`: what it already reported) and prints one event per line, each with the
action to take, or exactly `NOTHING NEW`. An event prints once; the state file is what keeps a question already
waiting on the user from being posted again. A line seen working again can end or finish again, so it is reported
again.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import local_dir  # noqa: E402

REPO = "EnderWolf50/maalc"
HEADER = [
    "# Active delegated tasks and launched threads (watchdog list). One per line: id<TAB>live-task-name-or-dash<TAB>label",
    "# Written by tools/live/watchdog.py; do not edit by hand.",
]
NOTHING = "NOTHING NEW"
STRANDED_MIN = 60  # minutes a holder may sit after its bot ended before the tick calls it stranded
TASK_KEYS = ("done|", "ended|", "failed|", "cancelled|")  # the `reported` keys that belong to a listed line
READER = {"task": "task_status", "thread": "t3_thread_read"}
# Per kind, the raw state its reader gives -> what tick makes of it; a state missing here stays silent.
# `result_available` is task_status's workState for a task with a result and no live child work: a finished turn with
# live child work is `waiting_for_children`, still working. `cancelled` is a stop on purpose by the coordinator:
# reported once, never resumed.
FINISHED = "finished"
ENDED = "ended"
FAILED = "failed"
CANCELLED = "cancelled"
WORKING = "working"
OUTCOMES = {
    "task": {
        **dict.fromkeys(("result_available", "completed", "complete", "succeeded", "success", "done"), FINISHED),
        **dict.fromkeys(("failed", "error", "errored", "interrupted", "rate_limited", "overloaded"), FAILED),
        **dict.fromkeys(("cancelled", "canceled"), CANCELLED),
        **dict.fromkeys(("working", "waiting_for_children"), WORKING),
    },
    "thread": {
        **dict.fromkeys(("preparing", "queued", "starting", "running"), WORKING),
        **dict.fromkeys(("completed", "waiting", "idle"), ENDED),
        **dict.fromkeys(("interrupted", "failed"), FAILED),
        **dict.fromkeys(("cancelled", "rolled_back"), CANCELLED),
    },
}
RESUME_MSG = ("You were interrupted. Run `uv run python tools/live/queue.py resume --task {task}` and "
              "`queue.py status`, read .local/scratch/{task}/next.md, and continue from there; never start a second hold or bot.")


class Row:
    def __init__(self, task_id: str, task: str, label: str):
        self.task_id, self.task, self.label = task_id, task, label

    def key(self) -> str:
        return unquote(self.task_id)

    @property
    def kind(self) -> str:
        return "task" if self.key().startswith("node:delegated-task:") else "thread"

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
    return [f"{r.task_id}\t{r.task}\t{r.label}\t{READER[r.kind]}" for r in load(path)] or ["(empty)"]


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
         hour: str, reported_ids: Iterable[str] = ()) -> tuple[list[str], dict]:
    """(events, new state). An event prints once: its key is in `state["reported"]` afterwards."""
    reported = set(state.get("reported", []))
    events: list[str] = []

    def fire(key: str, text: str) -> None:
        if key not in reported:
            reported.add(key)
            events.append(text)

    live = {r.key() for r in rows}
    said = {unquote(i) for i in reported_ids}
    outcomes: dict[str, str | None] = {}
    for r in rows:
        s = statuses.get(r.key(), "").lower()
        o = OUTCOMES[r.kind].get(s)
        if o == ENDED and r.key() in said:
            o = FINISHED
        outcomes[r.key()] = o
        if o == FINISHED:
            fire(f"done|{r.key()}", f"FINISHED {r.label}: relay its result to the user, decisions first, then "
                                    f"`uv run python tools/live/watchdog.py done {r.label}`")
        elif o == ENDED:
            fire(f"ended|{r.key()}", f"ENDED {r.label} ({s}): its turn ended with no report to the main thread, so it "
                 "may be waiting: read its last message with t3_thread_read, relay its question to the user or answer "
                 f"it with t3_thread_send; when its work is done, `uv run python tools/live/watchdog.py done {r.label}`")
        elif o == CANCELLED:
            fire(f"cancelled|{r.key()}", f"CANCELLED {r.label}: stopped on purpose, not resumed; the coordinator decides, "
                                         f"and `uv run python tools/live/watchdog.py done {r.label}` drops the line")
        elif o == FAILED:
            fire(f"failed|{r.key()}|{hour}", f"FAILED {r.label} ({s}) with no result: resume it once with t3_thread_send "
                 f"(mode auto, clientRequestId resume-{r.label}-{hour}), message: "
                 + RESUME_MSG.format(task=r.task if r.task != "-" else r.label))
        elif o == WORKING:
            # sent more work, it can finish or end again; the hourly `failed|` key stays to throttle the resume
            reported.difference_update({f"done|{r.key()}", f"ended|{r.key()}"})
    for name, mins in stranded_holders(queue_text):
        if mins > STRANDED_MIN:
            owner = next((r for r in rows if r.task == name or r.label == name), None)
            if owner is None:
                who = "its owner is not in the list: report it to the user"
            elif outcomes.get(owner.key()) == CANCELLED:
                who = f"{owner.label} was cancelled on purpose, do not resume it: the coordinator releases the hold"
            else:
                who = f"tell {owner.label} to resume (as for FAILED)"
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
    reported = {k for k in reported if not k.startswith(TASK_KEYS) or k.split("|")[1] in live}
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
    sub.add_parser("done").add_argument("ref", help="an id (encoded or not) or a label")
    sub.add_parser("list")
    t = sub.add_parser("tick")
    t.add_argument("--status", action="append", default=[], metavar="ID=STATE")
    t.add_argument("--reported", action="append", default=[], metavar="ID",
                   help="a thread whose latest run sent its report to the main thread")
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
        state_file = folder / "agents.state.json"
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
        events, state = tick(load(path), parse_statuses(a.status), queue_status(), main_ci(), state,
                             time.strftime("%Y%m%d%H"), a.reported)
        state_file.write_text(json.dumps(state, indent=1), encoding="utf-8")
        out = events or [NOTHING]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
