"""Write the standard header of a delegated task's brief, so no brief is copied from the last one.

  python tools/live/brief.py live --task <name> --difficulty normal|hard --exp-count N --thread-count N \\
      --weekly-bonus none|hard --recording yes|no [--runs N] [--force]
  python tools/live/brief.py code --task <name> [--force]

Writes `.local/scratch/<name>/brief.md` of the main checkout: the preamble pointer, the skills to load, the queue
and waiting rules, the report format, and (for `live`) a table of every run setting taken from the arguments.
Each setting is a required argument and nothing is read from an earlier brief: a count or a bonus carried over
from a copy is what cost Enkephalin Modules. The agent that creates the task writes only the `## Goal` section.
The weekly bonus has no `normal` choice; a brief that needs it for a NORMAL run says so, with the user's answer, in its goal.

`.local/brief-rules.md` (gitignored; override with `--rules`) holds the rules this public repo must not state,
such as account specifics. When it exists, its text is appended as "Machine-local rules".
An existing brief is kept unless `--force`, since its goal section is the agent's own text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import main_checkout  # noqa: E402

RULES_FILE = ("brief-rules.md",)  # under .local/ of the main checkout

COMMON = """# Brief: {task}

## Before anything else

- Read `docs/agents/subagent-preamble.md` and follow it; a delegated thread does not get it from the SubagentStart hook.
- Read `AGENTS.md`, `docs/agents/local-dev.md` "New worktree" (do its steps before the first test run) and `CODING_STANDARDS.md`.
- Work only in your own worktree; the main checkout stays on `main`.

## Skills to load

{skills}

## Queue and waiting

- The full `tools/check.py` goes through the bench queue, one ticket per run: `uv run python tools/live/queue.py run --resource bench --name {task}-check -- uv run python tools/check.py > <log> 2>&1`, started with `run_in_background` and waited on in the same turn.
- Do not poll in a loop. Keep your turn open while a queued, background or CI task runs; never end it on "I will be notified".
- Stop only processes you started, by pid: `taskkill /T /PID <pid>`.
{live_queue}
## Report

- Acceptance numbers: met / not met. Paths run live and paths not run (state "not run live" for what only a live run proves).
- Every decision you made that the brief did not make; every check or path you did not run.
- A PR: its URL, head SHA and `ci-ok` state; last line `PR <full URL>, head <SHA>, checks and reviews <state>`.
"""

LIVE_SKILLS = ("- `maalc-live-test` (every step; it owns the emulator, the account and `install/`).\n"
               "- `screen-record` and `evidence-annotate`, as that skill's steps 5 and 8 say.")
CODE_SKILLS = "- `tdd` for code; no live run: do not touch the emulator or the game account."

LIVE_QUEUE = """- The emulator only through the `maalc-live-test` skill's steps 0 to 10: `queue.py resume --task {task}` whenever your turn (re)starts, the emulator ticket with `queue.py detach`, the bot detached, one Monitor on `queue.py status --log`.
- Do all non-live work (code, tests, CI, review) before taking the emulator ticket and release it as soon as the live part ends.
"""

SETTINGS = """## Run settings

These are the settings of this run. Set each with `bot.py prep --set`; nothing is inherited from an earlier run or brief.

| setting | value |
| --- | --- |
| difficulty | {difficulty} |
| runs | {runs} |
| EXP Luxcavation count | {exp} |
| Thread Luxcavation count | {thread} |
| weekly bonus use | {bonus} |
| recording | {recording} |

{recording_text}
`bot.py prep --set run.difficulty={difficulty} --set run.runs={runs} --set run.weekly_bonus_use={bonus} --set luxcavation.exp.count={exp} --set luxcavation.thread.count={thread}`; check the keys against `agent/settings.schema.json` and confirm the effective values in `run.log` before the bot starts the run.
"""

RECORD_YES = "Record the run: `screen-record` with `--height 720` (skill step 5), and annotate it (step 8)."
RECORD_NO = "Do not record this run; step 8's route and pack stills come from device screenshots."

GOAL = "\n## Goal\n\n(The agent that creates this task writes the goal here: what to prove, the segment each check needs, the acceptance numbers.)\n"


def build(kind: str, a: argparse.Namespace, rules: str | None) -> str:
    live = kind == "live"
    text = COMMON.format(task=a.task, skills=LIVE_SKILLS if live else CODE_SKILLS,
                         live_queue=LIVE_QUEUE.format(task=a.task) if live else "")
    if live:
        text += "\n" + SETTINGS.format(difficulty=a.difficulty, runs=a.runs, exp=a.exp_count, thread=a.thread_count,
                                       bonus=a.weekly_bonus, recording=a.recording,
                                       recording_text=RECORD_YES if a.recording == "yes" else RECORD_NO)
    text += GOAL
    if rules:
        text += f"\n## Machine-local rules\n\n{rules.strip()}\n"
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", type=Path, help="the folder of the task folders (default .local/scratch/ of the main checkout)")
    ap.add_argument("--rules", type=Path, help="the machine-local rules file (default .local/brief-rules.md)")
    sub = ap.add_subparsers(dest="kind", required=True)
    live = sub.add_parser("live")
    live.add_argument("--difficulty", choices=("normal", "hard"), required=True)
    live.add_argument("--exp-count", type=int, required=True)
    live.add_argument("--thread-count", type=int, required=True)
    live.add_argument("--weekly-bonus", choices=("none", "hard"), required=True)
    live.add_argument("--recording", choices=("yes", "no"), required=True)
    live.add_argument("--runs", type=int, default=1)
    code = sub.add_parser("code")
    for p in (live, code):
        p.add_argument("--task", required=True)
        p.add_argument("--force", action="store_true", help="overwrite an existing brief")
    a = ap.parse_args(argv)
    # not local_dir(): it would create the folder of a mistyped task
    base = main_checkout() / ".local"
    scratch = a.scratch or base / "scratch"
    rules_path = a.rules or base.joinpath(*RULES_FILE)
    rules = rules_path.read_text(encoding="utf-8") if rules_path.exists() else None
    out = scratch / a.task / "brief.md"
    if out.exists() and not a.force:
        print(f"{out} exists: its goal section is the agent's; pass --force to overwrite")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(a.kind, a, rules), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
