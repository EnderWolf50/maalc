# Local development

## New worktree

1. `uv sync` and `pnpm install --frozen-lockfile`.
2. `uv run python tools/fetch_ocr.py`: the OCR model is gitignored, and `maa-tools test` misses every OCR node without it.
3. Scripts that need cv2, Pillow, numpy or psutil run as `uv run --group probe python <script>`; `tools/theme_pack_covers.py` (game files, Unity) needs `--group unpack`.
4. `python tools/slim_mcp.py` (from inside the new worktree; `--all` sweeps every worktree): writes the gitignored `.claude/settings.local.json` that keeps the rea, playwright, cua-driver and tempad-dev MCP servers out of agent sessions (each agent spawns its own copies, GBs of RAM). Claude Code reads that file per folder on Windows, so every new worktree needs it.

Done: `uv run pytest tests/test_conftest.py` passes in the worktree.

Once per clone, `lefthook install` turns on the pre-commit hook (`lefthook.yml`): ruff on the staged Python files and the screenshot privacy test. Install `lefthook` itself once per machine (`pnpm add -g lefthook`); the project's dependencies leave it out.

## Checks

CI runs every check, its test jobs on Windows (`.github/workflows/ci.yml`, #636); the flow around it is AGENTS.md "Review and CI".

`tools/check.py` is for when CI cannot run (quota, a GitHub outage), through the bench queue (`docs/agents/subagent-preamble.md` "Checks"); the bench queue is otherwise only for timing, memory measurement and mutation testing. `uv run python tools/check.py` runs ruff, `tools/review_lint.py` against `origin/main`, pytest, `maa-tools check` and `maa-tools test` and prints one summary line each, with its exit code and seconds; a failing step adds the tail of its output. pytest runs as 4 shards at once, split as CI's agent shards are (#484). `review_lint` is skipped, with the reason printed, when the checkout has no `origin/main` (`git fetch origin main`); with it, a GLOSSARY `_Avoid_` term in a doc fails locally as CI's `review-lint` job would (#628). The `pipeline` job (`maa-tools`) runs only when the PR changes a file the bot reads: `assets/`, `agent/`, `tests/screens/`, `maatools.config.mts`, `package.json`, `pnpm-lock.yaml`, `tools/fetch_ocr.py` or `ci.yml`; otherwise it is skipped and `ci-ok` stays green. A push to `main` skips them when a PR run already passed every job on the same file tree. The trees match when `main` did not move between that PR run and the merge.

### The run log (#633)

Every `check.py` run appends one JSON line to `.local/check-runs.jsonl` of the main checkout (`tools/local_dir.py`, so a worktree's run lands in the same file). A log that cannot be written prints `check log not written: …` and the run goes on; the exit code stays the number of failed steps. A run that is interrupted (Ctrl-C) leaves no line. The line holds:

| Key | Value |
| --- | --- |
| `v` | format version, 1 |
| `started`, `seconds` | start time (ISO, local offset) and the whole run's seconds |
| `worktree`, `branch`, `base`, `head`, `dirty` | the checkout, its branch, the point it left `origin/main` (null without `origin/main`), HEAD, and whether anything is uncommitted |
| `files` | `{path: blob id}` of every file the working tree (committed or not, untracked included, ignored left out) has different from the point the branch left `origin/main` (HEAD when there is no `origin/main`). The same change has the same blob ids in the next run, so the summary tells what changed between two runs without the commits |
| `steps` | `[{name, exit, seconds}]` for `ruff`, `review_lint` (absent when skipped), `pytest`, `maa-tools check`, `maa-tools test` |
| `failed_tests` | pytest node ids that failed or errored (from the shards' junit XML, the way CI's `shard-balance` reads its artifacts) |
| `failed_maa` | `maa-tools test` cases that went red, as `<image> <node>: <reason>` |
| `test_seconds` | `{test file: seconds}` summed over the shards (empty when pytest wrote no junit) |

The log costs one junit XML per pytest shard (written by pytest as in CI), its parse, and a few `git` calls that build the `files` map in a throwaway index: about 1 s per run, against the 9 minutes of the check (the git calls measured at 0.8 s on 2026-11-11).

`uv run python tools/check_stats.py` summarises the last 14 days (`--days N`, `--since YYYY-MM-DD`, `--log <file>`, `--top N`): runs, red runs, the tests that went red, and the slowest steps and test files. Each red run followed by a green run of the same branch in the same worktree (several reds in a row count once, from the last one) is put in one of three classes by the files that differ between the two (a fourth, `rebased`, when `base` moved between them or, with no base, HEAD did, because the files are then measured from a new base and say nothing):

- **code**: a file other than a test changed (a doc too: `review_lint` reads the docs). The check stopped a real error (an estimate: the change may be unrelated to the failure).
- **test**: only test files changed (`tests/`, `test_*.py`, `conftest.py`). The test's own problem.
- **flaky**: nothing changed and the run went green. Without `origin/main` (`base` null) the files show uncommitted changes only, so two runs at different HEADs count as `rebased`.

A red branch that never ran green in the period is counted apart. The log is machine-local: it covers the runs of this machine only.

CI splits pytest over the `agent` shards by each file's seconds on a Windows CI runner, from `tests/shard_seconds.json`. A PR that adds a slow test file, or makes one much slower or faster, makes the `shard-balance` job report it (a warning and the job summary; `ci-ok` does not wait for it, #628); its report names the command that rewrites the table (`uv run python tools/shard_seconds.py update --run <run id>`). A fast or slow runner does not report it: a file passes when its time is within double the table's, as measured or at its shard's pace, the median of its files' time over the table's (#536). A file not in the table fails from 30 s both as measured and at its shard's pace, and from 15 s on a PR, so a new file a PR lets through stays under main's limit on a slower or faster runner (#544). Each file gets the median of that run and the 4 CI runs before it whose agent shards all passed on `windows-latest` (`shard_seconds.RUNNER`; a run from before #636 ran them on Linux and does not count), so one fast or slow runner does not set the table; a file whose time in that run is more than double off the median, as measured and at its shard's pace, takes that run's time. Commit the new table in the same PR.

## After landing a PR

Land PRs with `tools/ship.py`; one call takes several and lands them one at a time:

- `uv run python tools/ship.py ready <pr>...` prints head SHA, `ci-ok` state, mergeable, draft, base and the PRs stacked on each.
- `uv run python tools/ship.py land <pr>... --go` lands the PRs in the given order. Each merges (merge commit) only when `ci-ok` passed on its current head and it is mergeable (an `UNKNOWN` mergeable, which GitHub reports for a few seconds after a merge into the base or a retarget, is read again every 5 s for up to a minute), and a PR into `main` only once the CI run of `main`'s head is green: `land` waits for a run that is still going, and a red one stops the call before that PR merges. A `main` red from an outside failure (a GitHub 504) gets a rerun of its CI; `--onto-red <pr>` skips the check for that one PR, only for the PR that fixes a red `main`. Each PR retargets the PRs stacked on its branch to the base before the branch is deleted, and waits for the CI run of the merge commit on `main`. The wait is short when that run skips its jobs (see "Checks"). A PR whose base is not `main` merges without either wait (`ci.yml` runs on pushes to `main` only). The first PR that is not ready, finds `main`'s head red, fails to merge or turns `main` red stops the call: it exits non-zero and, for several PRs, prints `stopped at #<pr>; not started: ...`. Two `land --go` calls take turns in the land lane (`.local/queue/land/` of the main checkout, a `tools/live/queue.py` queue), in the order they started: a call holds its turn for its whole batch, `after_land.py` included, and one that has to wait prints `ship: waiting for pid <pid> (ship.py land #<pr>...) to end before landing #<pr>...` once, then starts when that call ends, landed or stopped. A call whose process is gone (killed, or ended by the agent harness) loses its turn, and the next one takes over. A call whose own ticket is removed while it waits (a cleared queue folder) exits 1, says so and lands nothing: start it again. A dry run (no `--go`) never waits for a turn. `land` runs no review (AGENTS.md "Review and CI").
- `uv run python tools/ship.py into <integration-branch> <branch>` merges `<branch>` into the integration branch (`--no-ff`, in a worktree of it) and pushes it; a conflict pushes nothing. The checks run in CI on the integration branch's draft PR, not on this machine (#636): the first merge into an integration branch with no open PR opens it, and each `into` prints the PR whose `ci-ok` to wait for. A red one is fixed on the branch and merged in with another `into`. A worktree `into` adds gets no packages: a `check.py` there (CI down) needs "New worktree" step 1 first.
- `uv run python tools/review_pack.py <pr>` writes the diff, body, CI state and the issues the PR closes or names to `.local/scratch/review-<pr>/`, for a reviewer whose Bash tool does not run. Before the push there is no PR yet: save `git diff origin/<base>...HEAD` to a file under `.local/scratch/` instead.

`ship.py` runs `tools/after_land.py` in the main checkout once per `land` call, after the last PR landed or the batch stopped, when at least one PR landed green on `main` and the call did not leave `main` red. When `uv run python tools/live/queue.py status` shows a holder for `emulator` (a live run is using `install/`), it prints the command to run later instead: `uv run python tools/after_land.py`. `after_land.py` first fetches and fast-forwards the checkout's `main` (refusing off main, with local changes, or when it cannot fast-forward), then builds the settings GUI, assembles `install/` and checks that `install/config/settings.json` still loads.

Done: `after_land.py` ends without a "failed" line.

When to run it, and when not:

- Run it as `uv run python tools/after_land.py`, after the PR has landed on `origin/main`. A bare `python` lacks the `maa` package (2026-10-21).
- Not inside a `queue.py run --resource emulator` ticket: the script then reads its own ticket as a held `emulator` lane, and a `bench` ticket does not trip it (2026-10-21).

## Claude Code hooks

`.claude/hooks/main-checkout-guard.py` (Bash and PowerShell) denies `git switch`, `git checkout -b` and `git checkout <branch>` in the main checkout, also through `git -C`; a linked worktree may switch.

`.claude/settings.json` starts its hooks in exec form (`"command": "uv"` plus an `args` list), which needs a Claude Code version that knows `args` (2.1.302 does; `claude --version`). An older version drops `args` and runs a bare `uv`, which exits 2, the code that blocks a tool call: every Bash call then fails with a hook error that shows `uv`'s usage text. Update Claude Code when you see it.

## `.local/`: machine-local state

Everything that belongs to one machine lives in `.local/` of the **main checkout** (gitignored). Every worktree reaches it through `tools/local_dir.py`, which resolves `git rev-parse --path-format=absolute --git-common-dir` to the main checkout; a tool takes its folders from `local_dir("<name>", …)`.

| Folder | Holds |
| --- | --- |
| `.local/scratch/` | throwaway scripts and output of a task, `install-backup/<label>/` |
| `.local/archive/` | evidence of every live test and experiment, with `INDEX.md` (one row per folder) |
| `.local/check-runs.jsonl` | the run log of `tools/check.py` ("Checks") |
| `.local/queue/<resource>/` | the tickets of `tools/live/queue.py` (`bench`, `emulator`) and of `tools/ship.py land --go` (`land`); beside a ticket that runs `backup.py hold`, the hold's `<ticket>.hold.json` (`tools/live/hold.py`) |
| `.local/unpack/` | unpacked game data |
| `.local/llc/` | the Localize Limbus Company release zips `tools/llc_text.py` downloads |
| `.local/evidence/` | privacy-mask templates and `masks.json`; they can show the account, so they stay out of git |
| `.local/probe/` | the complete migrated probe: loose files, scripts, environments, caches, captures and experiments, preserving their relative paths |
| (disk space) | `uv run python tools/local_clean.py <command>` frees it; each command is a dry run until `--apply`. `usage <dir>` lists the sizes of a folder's items; `dedupe <root>` turns byte-identical files into hard links; `shrink <root>` re-encodes mp4 above 720p and 2 Mbps to 720p HEVC (NVENC); `prune <archive>` deletes archive folders past `--days` whose `INDEX.md` rows name only closed issues and PRs. See "Keeping disk space" below |

Strings that must not reach public text (the game account's e-mail, local folder names) go in the repo-local git config, once per clone: `git config --local --add maalc.privateTerm <term>`. `.claude/hooks/public-text-guard.py` reads them with `git config --get-all maalc.privateTerm`.

A doc's evidence ships with the repo, since `.local/` stays on one machine: small data the doc's numbers come from goes under `docs/perf/data/<doc>/`, an analysis worth rerunning becomes a script in `tools/` (as `tools/maafw_timeline.py`), and the doc says what stayed local (recordings, raw logs, unmasked screenshots, one-off probe scripts) instead of naming a `.local/` path the reader cannot open. Scan anything copied out with the repo's private terms first.

The data itself lives in `.local/`. The probe folder and the unpacked game data that once lived outside the repo were moved into `.local/probe/` and `.local/unpack/` (2026-10-19), and the links left at their old roots were removed (2026-11-12), so a script that still names an old root no longer finds it; work uses `local_dir("scratch", …)` or `local_dir("archive", …)`. Historical evidence is under `.local/probe/`; it remains private until masked. `.local/evidence/masks.json` and its templates were made once, during that move; they are kept, not regenerated.

## Keeping disk space

One link ties the evidence folders together: `.local/archive` is a junction to `.local/probe/archive`, so a size listing that follows links counts the data twice (`local_clean.py usage` skips it).

Retention: an archive folder older than 7 days whose `INDEX.md` rows name only closed issues and PRs can be deleted with `prune`; a folder with no `INDEX.md` row, or with a number gh does not return, stays. A recording above 720p can be re-encoded with `shrink`. `recordings/` is never pruned. Before deleting or re-encoding, ask the chat that runs the live tests and owns the open issues which folders keep their original files (`shrink --keep <folder>`), and read the dry run first. `recordings/` holds hard links, not copies, so one file counts once.

## Orchestration tools

- `tools/live/watchdog.py add|done|list|tick` owns `agents.tsv` (and `agents.state.json`, what `tick` already reported) in `.local/scratch/`: nobody edits the file by hand. `tick` prints only news or `NOTHING NEW`; the scheduled prompt is `docs/agents/watchdog-prompt.md`.
- `tools/live/brief.py live|code --task <name> ...` writes the standard header of `.local/scratch/<name>/brief.md`; every run setting is a required argument. Rules the public repo must not state go in `.local/brief-rules.md` (gitignored), which the script appends to the brief as "Machine-local rules".

The main thread dispatches work in these steps:

1. **Register.** After `t3_thread_launch` or `delegate_task`, `uv run python tools/live/watchdog.py add <id> <live-task|-> <label>` with the thread or task id it returned. Done when it prints `added <label>` or `already in the list`.
2. **Switch on.** When `add` prints `switch the watchdog schedule ON`, call `schedule_task` with `enabled: true` and the `scheduledTaskId` of the task "maalc agent watchdog" (`list_scheduled_tasks` names it). Done when `schedule_task` returns its next run time.
3. **Stay awake.** For a run left unattended at night, start `uv run python tools/live/bot.py awake --minutes 118` as a background command and start it again each time it ends: a background command lasts at most 2 hours. Done when the last registered line has left the list.

## The emulator lane

The MuMu instances the live tests use all log in to one game account, and starting the game on one instance kicks the others out (the user, 2026-10-20). So the `emulator` resource covers all instances: `tools/live/queue.py` describes it as the user's game account on the emulator. Take an `emulator` ticket before you drive any instance.

## Game data

`tools/live/dialogs.py` lists the confirm-style dialog strings of `.local/unpack/`, to diff against the pipeline's known dialogs; run it before an unattended run.

`.local/unpack/client.json` names the client version `.local/unpack/` holds; `tools/game_data.py` pulls a new client from the emulator (read-only `adb pull`, no emulator ticket), regenerates every data file and prints the diff (docs/spec/05-game-data.md section 8, step 0).

Look in `.local/unpack/` first (gift tables, prices, theme packs, every dialog string, under `raw/` and `static/`; its `NOTES.md` says what is where). The Simplified Chinese strings come from the Localize project, https://github.com/LocalizeLimbusCompany: clone it next to the other data to read them. The Chinese names the data files ship come from its release zip through `tools/llc_text.py`, which converts them to Traditional (OpenCC `s2twp` plus a few fixes). Reach for a wiki only when neither has it.

To query it, search the unpacked tree with `rg`: `rg -l "<text>" <main checkout>/.local/unpack/raw/Localize/en` finds a dialog or a name, and `rg -l "<key>" .local/unpack/static` finds a table (`static/` holds about 2200 JSON files, counted 2026-10-30). Mounting Trial names are in `raw/Localize/en/EN_Bufs_Mirror5.json`, and the mirror node data for the `-hard`, `-extreme` and `-infinite` variants is `static/Assets/Resources_moved/StaticData/static-data/mirrordungeon/mirrordungeon-08-*.json`.

The Huiji wiki (`limbuscompany.huijiwiki.com`) is behind Cloudflare: `curl` got 403 on 2026-10-30, and WebFetch got 403 on 2026-10-16. Use the unpacked data first; a wiki answer means a browser session.

The game data gives every personality a skill deck of S1 ×3, S2 ×2, S3 ×1: `attributeList[].number` of every `personality-*.json` under `static/.../StaticData/static-data/personality/` is 3, 2, 1 (202 personalities, counted 2026-10-30). Below Uptie 3 skill 3 is locked, so the shop's skill replacement dialog shows `SKILL 3x0` (#264).

The AALC source, the bot that AGENTS.md "Goal" sets feature parity with, is upstream `KIYI671/AhabAssistantLimbusCompany`. `docs/research/aalc/` is the written reading of it, pinned to commit `b0f4393` (its README): start there, and open the source only for what it lacks. Read one file with `gh api repos/KIYI671/AhabAssistantLimbusCompany/contents/<path>`, or clone it once into `.local/aalc/` of the main checkout (resolve it with `tools/local_dir.py`) and search it with `rg`. A fork on your machine can be stale, so compare a file with upstream before you rely on it.
