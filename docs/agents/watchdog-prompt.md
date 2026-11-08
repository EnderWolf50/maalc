# Watchdog prompt

The prompt of the scheduled task "maalc agent watchdog" (every 30 minutes). The coordinator installs everything below the line with `schedule_task` (`scheduledTaskId` of the task, `prompt`), filling in `<schedule-id>` with that task's own id and changing nothing else (`<line-id>` in step 2 stands for each listed line's id, which the run fills in itself): `list_scheduled_tasks` tells a scheduled run not to call it to find its own task. A resumed agent's live-run rules are in its brief (`tools/live/brief.py` copies `.local/brief-rules.md` into it), so the prompt carries none.

---

Watchdog tick (maalc). Reply in 繁體中文. This scheduled task's id is `<schedule-id>`. Run every command in the main checkout.

1. **List.** `uv run python tools/live/watchdog.py list`. On `(empty)`, run `uv run python tools/live/queue.py status`: with no emulator holder, switch this task off (`schedule_task` with `scheduledTaskId` `<schedule-id>` and `enabled: false`) and end the turn with no text; with a holder, go on to step 2 with no `--status`.
2. **Tick.** Read each listed line with the tool its last column names, then run `uv run python tools/live/watchdog.py tick --status <line-id>=<state> ...`, one `--status` per line:
   - `task_status`: the state is `workState` exactly as it comes (`working`, `waiting_for_children`, `result_available`), never `status`: a turn that ended with child work still live is not finished.
   - `t3_thread_read` with `limit: 1`: the state is `thread.status`. For `completed`, read its last 8 activity items (`view: "activity"`, `afterPosition` = `itemCount` - 9, left out when that is below 0, `limit: 8`, `maxCharsPerItem: 200`) and add `--reported <line-id>` when one of them has `runId` equal to `latestRunId`, names `mcp__t3-code__t3_thread_send` and sends to this thread (`currentThreadId` of `t3_thread_list` with `limit: 1`): the thread reported to the main thread.

   A call that errors, the activity read included, leaves that line's `--status` out. An id goes in encoded or decoded. Done when `tick` has printed.
3. **Quiet.** `NOTHING NEW` ends the turn with no text and no other call.
4. **Act.** Do what each printed line says (relay a result, read an ended thread's last message and relay or answer its question, resume a task once, note a cancelled one, report a stranded holder, report main red or green). The reply is those lines and nothing else: `tick` prints an event once and remembers it, so a question already waiting on the user is not asked again. Done when every line is acted on.
5. **Done.** After relaying a finished task or thread, `uv run python tools/live/watchdog.py done <label>`; the CLI owns `agents.tsv`. When `done` prints that the list is empty, run step 1's off check.
