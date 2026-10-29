## Working in maalc as a subagent

The SubagentStart hook (`.claude/hooks/subagent-preamble.py`) hands this file to every subagent.

- **Bash in an isolated worktree:** one plain command per call, no heredoc, loop, `$VAR`, `$(…)` or `cd X && …`: Claude Code's worktree guard refuses those as "too complex to verify". Multi-step logic goes in a script you write with the Write tool under `.local/scratch/` of the main checkout (`tools/local_dir.py` finds it) and run as `python <file>`. Git runs as `git -C <your worktree> …`.
- **Setup:** `docs/agents/local-dev.md` "New worktree" before the first test run.
- **Machine-local data:** resolve the main checkout with `tools/local_dir.py`, including when working in a worktree. New scripts/cache/output go directly to its `.local/scratch/`, evidence to `.local/archive/`, game data to `.local/unpack/`. The complete historical probe is `.local/probe/`; read it there rather than recreating a home-cache folder. A migration waits until both resource queues and independent source writers are idle.
- **Waiting:** start long work with `run_in_background`, or one Monitor until-loop on the PID, and keep your turn open until it ends. CI: `gh pr checks <n> --watch` with a 600000 ms timeout, once more on exit 143. TaskStop every background task before you report. A bench or emulator ticket: `uv run python tools/live/queue.py wait --resource <bench|emulator> --name <ticket>` blocks until it ends and exits with its code (75 = still running, run it again); never end the turn on "I will be notified".
- **GitHub reads:** `gh issue view <n> --json title,body,comments`; a truncated read says so in your report.
- **Premises:** a brief marks each fact `verified` or `unverified`. Check every unverified one first; when one does not hold, stop and report.
- **The emulator and the account:** only through the `maalc-live-test` skill. A game update, any download, Give Up, Claim, the weekly bonus and starlight beyond the configured graces wait for the user's answer, each time.
- **Public text:** AGENTS.md "Public repo". Write each issue, PR or commit body with the Write tool and pass its absolute Windows path (`--body-file`, `git commit -F`); the guard denies stdin, `$(…)`, a heredoc and a file it cannot find.
- **Report:** acceptance numbers met / not met; paths run live and paths not run; every decision you made that the user has not; commit trailers copied from your own session's attribution reminder, never a model name from the brief.
