# Local development

## New worktree

1. `uv sync` and `pnpm install --frozen-lockfile`.
2. `uv run python tools/fetch_ocr.py`: the OCR model is gitignored, and `maa-tools test` misses every OCR node without it.
3. Scripts that need cv2, Pillow, numpy or psutil run as `uv run --group probe python <script>`; `tools/theme_pack_covers.py` (game files, Unity) needs `--group unpack`.
4. `python tools/slim_mcp.py` (from inside the new worktree; `--all` sweeps every worktree): writes the gitignored `.claude/settings.local.json` that keeps the rea, playwright, cua-driver and tempad-dev MCP servers out of agent sessions (each agent spawns its own copies, GBs of RAM). Claude Code reads that file per folder on Windows, so every new worktree needs it.

Done: `uv run python tools/check.py` passes in the worktree.

Once per clone, `lefthook install` turns on the pre-commit hook (`lefthook.yml`): ruff on the staged Python files and the screenshot privacy test. `lefthook` is a global tool on the user's machines.

## Checks

`uv run python tools/check.py` runs ruff, pytest, `maa-tools check` and `maa-tools test` and prints one summary line each; a failing step adds the tail of its output. CI runs the same checks, and a PR merges on a green `ci-ok`.

## After landing a PR

Land one PR at a time with `tools/ship.py`:

- `uv run python tools/ship.py ready <pr>...` prints head SHA, `ci-ok` state, mergeable, draft, base and the PRs stacked on each.
- `uv run python tools/ship.py land <pr> --go` merges (merge commit) only when `ci-ok` passed on the current head and the PR is mergeable, retargets the PRs stacked on its branch to the base before the branch is deleted, waits for the CI run of the merge commit on `main` and exits non-zero when it is red. A second `land` waits until the first returned green. Run the `code-review` skill before `--go`.
- `uv run python tools/ship.py into <integration-branch> <branch>` merges `<branch>` into the integration branch (`--no-ff`, in a worktree of it), runs `tools/check.py` through the bench queue and pushes only on green; a conflict or a red check pushes nothing. The first merge into an integration branch with no open PR opens a draft PR, so Linux CI runs from the first merge.
- `uv run python tools/review_pack.py <pr>` writes the diff, body, CI state and the issues the PR closes or names to `.local/scratch/review-<pr>/`, for a reviewer whose Bash tool does not run.

After a green `land`, `ship.py` runs `tools/after_land.py` in the main checkout unless `uv run python tools/live/queue.py status` shows a holder for `emulator` (a live run is using `install/`); then it prints the command to run later: `uv run python tools/after_land.py`. It first fetches and fast-forwards the checkout's `main` (refusing off main, with local changes, or when it cannot fast-forward), then builds the settings GUI, assembles `install/` and checks that `install/config/settings.json` still loads.

Done: `after_land.py` ends without a "failed" line.

## Claude Code hooks

`.claude/hooks/main-checkout-guard.py` (Bash and PowerShell) denies `git switch`, `git checkout -b` and `git checkout <branch>` in the main checkout, also through `git -C`; a linked worktree may switch.

`.claude/settings.json` starts both hooks in exec form (`"command": "uv"` plus an `args` list), which needs a Claude Code version that knows `args` (2.1.302 does; `claude --version`). An older version drops `args` and runs a bare `uv`, which exits 2, the code that blocks a tool call: every Bash call then fails with a hook error that shows `uv`'s usage text. Update Claude Code when you see it.

## `.local/`: machine-local state

Everything that belongs to one machine lives in `.local/` of the **main checkout** (gitignored). Every worktree reaches it through `tools/local_dir.py`, which resolves `git rev-parse --path-format=absolute --git-common-dir` to the main checkout; a tool takes its folders from `local_dir("<name>", …)`.

| Folder | Holds |
| --- | --- |
| `.local/scratch/` | throwaway scripts and output of a task, `install-backup/<label>/` |
| `.local/archive/` | evidence of every live test and experiment, with `INDEX.md` (one row per folder) |
| `.local/queue/<resource>/` | the tickets of `tools/live/queue.py` (`bench`, `emulator`) |
| `.local/unpack/` | unpacked game data |
| `.local/llc/` | the Localize Limbus Company release zips `tools/llc_text.py` downloads |
| `.local/evidence/` | privacy-mask templates and `masks.json`; they can show the account, so they stay out of git |
| `.local/probe/` | the complete migrated probe: loose files, scripts, environments, caches, captures and experiments, preserving their relative paths |
| (disk space) | `uv run python tools/local_clean.py <command>` frees it; each command is a dry run until `--apply`. `usage <dir>` lists the sizes of a folder's items; `dedupe <root>` turns byte-identical files into hard links; `shrink <root>` re-encodes mp4 above 720p and 2 Mbps to 720p HEVC (NVENC); `prune <archive>` deletes archive folders past `--days` whose `INDEX.md` rows name only closed issues and PRs. See "Keeping disk space" below |

Strings that must not reach public text (the game account's e-mail, local folder names) go in the repo-local git config, once per clone: `git config --local --add maalc.privateTerm <term>`. `.claude/hooks/public-text-guard.py` reads them with `git config --get-all maalc.privateTerm`.

A doc's evidence ships with the repo, since `.local/` stays on one machine: small data the doc's numbers come from goes under `docs/perf/data/<doc>/`, an analysis worth rerunning becomes a script in `tools/` (as `tools/maafw_timeline.py`), and the doc says what stayed local (recordings, raw logs, unmasked screenshots, one-off probe scripts) instead of naming a `.local/` path the reader cannot open. Scan anything copied out with the repo's private terms first.

The data itself lives in `.local/`. `uv run python tools/local_migrate.py --probe <old probe folder> --unpack <unpacked data>` shows the move (dry run); `--probe` covers the **whole** probe folder, including hidden files, loose scripts, caches, virtual environments and experimental output. `--apply` moves it to `.local/probe/`, leaves a junction at the old root, makes `.local/archive/` point to its archive and generates `.local/evidence/masks.json`. An archive migrated by the older tool stays where it is, with a link from `.local/probe/archive/`. Nested links are preserved, not copied as duplicate data. The old root keeps scripts with hardcoded legacy paths working; new work uses `local_dir("scratch", …)` or `local_dir("archive", …)` directly. Historical evidence is under `.local/probe/`; it remains private until masked.

Before applying, `uv run python tools/live/queue.py status` must show no holder or waiting task for `emulator` or `bench`; check for independent writers/recordings using the source too. Wait for them to finish, rather than stopping another task. On the same drive the move is a rename; across drives it is copied and checked twice, including byte comparison, before deletion. A folder in use or written to during copying stays as it was. A destination conflict stops instead of silently claiming success. After an interrupt, rerun: the tool completes states it can prove safe and stops with the original named otherwise. Once old consumers have been updated and no running process uses the old root, `local_migrate.py --remove-links --apply` removes only recorded external compatibility links; `.local/archive/`, nested links and data remain. If an internal link still targets an old external root, removal stops and names that dependency; update it first.

## Keeping disk space

Three links tie the evidence folders together; they are junctions, so a size listing that follows links counts the data twice (`local_clean.py usage` skips them):

- `.local/archive` points to `.local/probe/archive`.
- The old probe root that `local_migrate.py --apply` left behind points to `.local/probe`.
- The old unpacked-data folder it left behind points to `.local/unpack`.

`local_migrate.py` records where those two old roots are.

Retention: an archive folder older than 7 days whose `INDEX.md` rows name only closed issues and PRs can be deleted with `prune`; a folder with no `INDEX.md` row, or with a number gh does not return, stays. A recording above 720p can be re-encoded with `shrink`. `recordings/` is never pruned. Before deleting or re-encoding, ask the chat that runs the live tests and owns the open issues which folders keep their original files (`shrink --keep <folder>`), and read the dry run first. `recordings/` holds hard links, not copies, so one file counts once.

## Game data

`tools/live/dialogs.py` lists the confirm-style dialog strings of `.local/unpack/`, to diff against the pipeline's known dialogs; run it before an unattended run.

Look in `.local/unpack/` first (gift tables, prices, theme packs, every dialog string, under `raw/` and `static/`; its `NOTES.md` says what is where). The Simplified Chinese strings come from the Localize project, https://github.com/LocalizeLimbusCompany: clone it next to the other data to read them. The Chinese names the data files ship come from its release zip through `tools/llc_text.py`, which converts them to Traditional (OpenCC `s2twp` plus a few fixes). Reach for a wiki only when neither has it.
