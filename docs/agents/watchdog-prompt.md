# Watchdog prompt

The prompt of the scheduled task "maalc agent watchdog" (every 30 minutes). The coordinator installs everything below the line with `schedule_task` (`scheduledTaskId` of the task, `prompt`), filling in `<id>` with that task's own id: a scheduled run cannot look it up. The live-run rules a resumed agent needs are in its brief (`.local/brief-rules.md`), so the prompt carries none.

---

Watchdog tick (maalc). Quiet: a tick with no news ends with no text. Reply in 繁體中文. This scheduled task's id is `<id>`. Run every command in the main checkout.

1. **List.** `uv run python tools/live/watchdog.py list`. On `(empty)`, run `uv run python tools/live/queue.py status`; with no emulator holder, switch this task off (`schedule_task` with `scheduledTaskId` `<id>` and `enabled: false`) and end the turn with no text.
2. **Tick.** `task_status` for each listed id, then `uv run python tools/live/watchdog.py tick --status <taskId>=<workState> ...`, one `--status` per line. Pass `workState` exactly as `task_status` gives it (`working`, `waiting_for_children`, `result_available`), never `status`: a turn that ended with child work still live is not finished. A `task_status` call that errors leaves its `--status` out. An id goes in encoded or decoded.
3. **Quiet.** `NOTHING NEW` ends the turn with no text and no other call.
4. **Act.** Otherwise do what each printed line says (relay a result, resume a task once, note a cancelled one, report a stranded holder, report main red or green) and reply with those lines only. `tick` prints each event once, so the reply holds only its lines: a question already waiting on the user stays where it is.
5. **Done.** After relaying a finished task, `uv run python tools/live/watchdog.py done <label>`; the CLI owns `agents.tsv`. When `done` prints that the list is empty, run step 1's off check.
