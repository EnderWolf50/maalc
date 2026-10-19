# Local development

## New worktree

1. `uv sync` and `pnpm install --frozen-lockfile`.
2. `uv run python tools/fetch_ocr.py`: the OCR model is gitignored, and `maa-tools test` misses every OCR node without it.
3. Scripts that need cv2, Pillow, numpy or psutil run as `uv run --group probe python <script>`.

Done: `uv run python tools/check.py` passes in the worktree.

Once per clone, `lefthook install` turns on the pre-commit hook (`lefthook.yml`): ruff on the staged Python files and the screenshot privacy test. `lefthook` is a global tool on the user's machines.

## Checks

`uv run python tools/check.py` runs ruff, pytest, `maa-tools check` and `maa-tools test` and prints one summary line each; a failing step adds the tail of its output. CI runs the same checks, and a PR merges on a green `ci-ok`.

## After landing a PR

Land with the `ship` skill's land task. Then, in the main checkout and unless `uv run python tools/live/queue.py status` shows a holder for `emulator` (a live run is using `install/`): `uv run python tools/after_land.py`. It builds the settings GUI, assembles `install/` and checks that `install/config/settings.json` still loads.

Done: `after_land.py` ends without a "failed" line.

## Claude Code hooks

`.claude/settings.json` starts both hooks in exec form (`"command": "uv"` plus an `args` list), which needs a Claude Code version that knows `args` (2.1.302 does; `claude --version`). An older version drops `args` and runs a bare `uv`, which exits 2, the code that blocks a tool call: every Bash call then fails with a hook error that shows `uv`'s usage text. Update Claude Code when you see it.

## `.local/`: machine-local state

Everything that belongs to one machine lives in `.local/` of the **main checkout** (gitignored). Every worktree reaches it through `tools/local_dir.py`, which resolves `git rev-parse --path-format=absolute --git-common-dir` to the main checkout; a tool takes its folders from `local_dir("<name>", …)`.

| Folder | Holds |
| --- | --- |
| `.local/scratch/` | throwaway scripts and output of a task, `install-backup/<label>/` |
| `.local/archive/` | evidence of every live test and experiment, with `INDEX.md` (one row per folder) |
| `.local/queue/<resource>/` | the tickets of `tools/live/queue.py` (`bench`, `emulator`) |
| `.local/unpack/` | unpacked game data |
| `.local/evidence/` | privacy-mask templates and `masks.json`; they can show the account, so they stay out of git |

Strings that must not reach public text (the game account's e-mail, local folder names) go in the repo-local git config, once per clone: `git config --local --add maalc.privateTerm <term>`. `.claude/hooks/public-text-guard.py` reads them with `git config --get-all maalc.privateTerm`.

The data itself lives in `.local/`. `uv run python tools/local_migrate.py --probe <old probe folder> --unpack <unpacked data>` shows the move (dry run); `--apply` moves each folder into `.local/` (a rename on the same drive; across drives a copy that is checked twice before the original is deleted), leaves a directory junction at the old place pointing into `.local/` (so a task still using the old path keeps working) and writes `.local/evidence/masks.json` from the old templates. A folder in use, or one written to during the copy, is left as it was; a `.partial` or `.migrating` folder from an interrupted run stops the tool until it is sorted out by hand. Once nothing uses the old paths, `local_migrate.py --remove-links --apply` deletes the junctions it recorded in `.local/links.json`; the data stays.

## Game data

`tools/live/dialogs.py` lists the confirm-style dialog strings of `.local/unpack/`, to diff against the pipeline's known dialogs; run it before an unattended run.

Look in `.local/unpack/` first (gift tables, prices, theme packs, every dialog string, under `raw/` and `static/`; its `NOTES.md` says what is where). The Simplified Chinese strings come from the Localize project, https://github.com/LocalizeLimbusCompany: clone it next to the other data, no Taiwan-usage rewrite needed. Reach for a wiki only when neither has it.
