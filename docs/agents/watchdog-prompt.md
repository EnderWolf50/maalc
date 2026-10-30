# Watchdog prompt

The prompt of the scheduled task "maalc agent watchdog" (every 30 minutes). The coordinator installs it into the schedule; the schedule keeps account-specific live-run reminders in its own copy, not here. Everything below the line is the prompt.

---

Watchdog tick (maalc). Quiet unless something is new. Reply in 繁體中文 only when `tick` prints something other than `NOTHING NEW`.

1. In the main checkout run `uv run python tools/live/watchdog.py list`. If it prints `(empty)`, also run `uv run python tools/live/queue.py status`; with no emulator holder, disable this scheduled task (`update_scheduled_task enabled=false`) and end the turn with no text.
2. Call `task_status` for the id of each line `list` printed. Run `uv run python tools/live/watchdog.py tick --status <taskId>=<state> ...`, one `--status` per line, pass its `workState` exactly as `task_status` gave it (`working`, `waiting_for_children`, `result_available`), not its `status`: a turn that ended with child work still live is not finished. A call that errors: omit that task's `--status`. An id may be passed encoded or decoded.
3. If `tick` printed `NOTHING NEW`, end the turn with no text. Do not call `t3_thread_list`, do not summarise, do not repeat anything.
4. Otherwise act on each printed line exactly as it says (relay a result, resume a task once, report a stranded holder, report main red or green) and reply with those lines only. `tick` prints an event once, so never re-list a question that is already waiting on the user, and never add one of your own.
5. A task finished and relayed: `uv run python tools/live/watchdog.py done <label>`. Never edit `agents.tsv` by hand. When `add` or `done` prints a line about the schedule, switch it on or off accordingly.
