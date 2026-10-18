---
name: maalc-live-test
description: Run maalc against the MuMu emulator and report it with evidence. Use for a live test, an experiment, live verification of a PR, or an unattended run on the emulator.
---

A **live test** drives the user's real game account. It owns the emulator alone, starts from a known screen, and leaves the account, the game settings and `install/` as it found them. Emulator settings (resolution, window) stay the user's. Scripts live in `tools/live/`; machine-local state in `.local/` of the main checkout, never of your worktree (`docs/agents/local-dev.md`); `install/` is the main checkout's too.

Recording and annotation come from two global skills: `screen-record` and `evidence-annotate`. Read each before its step.

## Steps

1. **Claim.** Put steps 2–8 in one script under `.local/scratch/<task>/` and run it as `uv run python tools/live/queue.py run --resource emulator --name <task> -- <script command>`, in the background. The queue is first-come-first-served and drops dead holders; while another task holds the emulator you wait, so keep your turn open. Done: `queue.py status` shows `RUNNING <task>`.
2. **Pre-flight.** Screenshot the emulator. Main screen with no resumable Mirror Dungeon run → go on. A resumable run, any other screen, an update or a download prompt → stop and ask; forfeiting a run is the user's call and never goes through Claim. Done: `00-start.png` shows the main screen.
3. **Scope.** Run the segment each check needs (a few decisions), not a whole dungeon, unless the brief names a full run. Done: every check in the brief names the segment that exercises it.
4. **Back up.** `uv run python tools/live/backup.py backup --label <task>` (md5 manifest of `install/`, a copy of `settings.json`). Write down every game setting you will change. Done: the command printed a file count.
5. **Record.** `screen-record`: `obsrec.py start --window <title substring> --profile <name> [--crop-top N] --out .local/archive/<date>-<topic>/`. It refuses a minimised window and a black 1-second test frame. Done: `obsrec.py status` shows it recording.
6. **Run.** Start the bot the way the brief says and wait on its PID with one Monitor until-loop; your turn stays open until the run ends. Done: the run ended or hit the brief's time limit.
7. **Stop.** `pwsh tools/live/stop_run.ps1 -RunPid <pid>` takes the whole process tree; then `obsrec.py stop`. Done: `stop_run.ps1 -WhatIf` lists no process.
8. **Evidence.** `uv run python tools/live/maafw_events.py install/debug/maafw.log -o <dir>/events.json`, then `evidence-annotate`: `annotate.py VIDEO -o OUT --start <wall time of the first frame> --events events.json [--steps steps.json] --masks .local/evidence/masks.json [--from T --to T] [--frames T,…]`. `masks.json` blacks out the player-number plate and the account e-mail; without it nothing leaves `.local/`. Add one row to `.local/archive/INDEX.md`. Done: the annotated clip and the INDEX row exist.
9. **Restore.** Game settings back as written down in step 4, then `uv run python tools/live/backup.py verify --label <task>`. Done: it reports the md5 match.
10. **Report.** Per check: pass / fail / not reached, with its clip. Acceptance numbers: met or not met. Upload clips and frames with `--attach` (AGENTS.md "Public repo"); a failure opens an issue with its evidence attached.

Done: every check has a verdict and a clip, the INDEX row exists, `verify` matched, and the queue holds no ticket of yours.

## Asks the user first

A game update, any download, Give Up on a battle, Claim, the weekly bonus, starlight beyond the configured graces. The answer covers that one action.
