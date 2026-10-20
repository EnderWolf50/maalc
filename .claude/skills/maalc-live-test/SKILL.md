---
name: maalc-live-test
description: Run maalc against the MuMu emulator and report it with evidence. Use for a live test, an experiment, live verification of a PR, or an unattended run on the emulator.
---

A **live test** drives the user's real game account. It owns the emulator alone, starts from a known screen, and leaves the account, the game settings and `install/` as it found them. Emulator settings (resolution, window) stay the user's. Scripts live in `tools/live/`; machine-local state in `.local/` of the main checkout, never of your worktree (`docs/agents/local-dev.md`); `install/` is the main checkout's too.

Recording and annotation come from two global skills: `screen-record` and `evidence-annotate`. Read each before its step.

Resolve output paths through `tools/local_dir.py` before starting a process: `.local/` below means the main checkout's folder. New probe scripts and cache go in `.local/scratch/`; `.local/probe/` holds the migrated historical scripts, environments and captures. See `docs/agents/local-dev.md` before migrating or removing old compatibility paths; another task's recording must finish first.

## Steps

1. **Queue.** Take the emulator with the one non-interactive command: `uv run python tools/live/queue.py run --resource emulator --name <task> -- uv run python tools/live/backup.py hold --label <task> --done .local/scratch/<task>/done`, in the background. `hold` backs up `install/` (an md5 manifest and a copy of `settings.json`), waits until the `done` file exists, then verifies `install/` against the backup. The queue is first-come-first-served and drops dead holders; while another task holds the emulator you wait, so keep your turn open. Steps 2, 5, 6 and 8 are your own actions, taken while the command holds the emulator. Done: its output shows `[queue] start <task>` and `backed up <n> files`.
2. **Pre-flight.** Screenshot the emulator. Main screen with no resumable Mirror Dungeon run → go on. A resumable run, any other screen, an update or a download prompt → stop and ask; forfeiting a run is the user's call and never goes through Queue. Done: `00-start.png` shows the main screen.
3. **Scope.** Run the segment each check needs (a few decisions), not a whole dungeon, unless the brief names a full run. Done: every check in the brief names the segment that exercises it.
4. **Settings.** Write down every game setting you will change, with its value now. Done: the list exists in your notes.
5. **Record.** `screen-record`: `screenrec.py start --window <title substring> --out .local/archive/<date>-<topic>/ [--profile <name>] [--crop-top N]`. It refuses no visible window, a minimised one, a profile already recording, less than 30 GB free (`--min-free-gb`), a black first frame, and no frame within 10 seconds, which is what a sleeping display gives: with the monitor off, Windows draws nothing to capture, so a recording needs the user's screen awake. Pass the same `--profile` to `status` and `stop` as to `start`. Done: `screenrec.py status [--profile <name>]` prints `active True`.
6. **Run.** Start the bot the way the brief says and wait on its PID with one Monitor until-loop; your turn stays open until the run ends. Done: the run ended or hit the brief's time limit.
7. **Stop.** `pwsh tools/live/stop_run.ps1 -RunPid <pid>` takes the whole process tree; then `screenrec.py stop [--profile <name>]`. Done: `stop_run.ps1 -WhatIf` lists no process, and `stop` printed `saved <file>.mp4` with its `started` time, which is step 8's `--start`.
8. **Evidence.** `uv run python tools/live/maafw_events.py <main checkout>/install/debug/maafw.log -o <dir>/events.json` (the log is the main checkout's, not your worktree's), then `evidence-annotate`: `annotate.py VIDEO -o OUT --start <wall time of the first frame> --events events.json [--steps steps.json] --masks .local/evidence/masks.json [--from T --to T] [--frames T,…]`. `masks.json` blacks out the three identity regions: the player-number plate, the player name above the LV panel at the bottom left (36,626,98,20 in game pixels) and the account e-mail; without it nothing leaves `.local/`. Add one row to `.local/archive/INDEX.md`. Done: the annotated clip and the INDEX row exist.
9. **Restore.** Game settings back as written down in step 4, then create the `done` file of step 1 (the Write tool). `hold` verifies `install/` and the queue command ends. Done: its output says `install matches the backup (md5)` and its exit code is 0.
10. **Report.** Per check: pass / fail / not reached, with its clip. Acceptance numbers: met or not met. Upload clips and frames with `--attach` (AGENTS.md "Public repo"); a failure opens an issue with its evidence attached.

Done: every check has a verdict and a clip, the INDEX row exists, `hold` matched, and the queue holds no ticket of yours.

## Asks the user first

A game update, any download, Give Up on a battle, Claim (a reward), the weekly bonus, starlight beyond the configured graces. The answer covers that one action.
