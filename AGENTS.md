## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (EnderWolf50/maalc) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Working here

### Goal

Feature parity with AALC is the target; a v1 simplification goes under **Deferred** in the map issue, not out of scope.

### Multi-issue work

A feature that needs more than one issue goes through the `to-spec`, `to-tickets` and `implement-spec` skills, in that order, before any sub-issue is published.

### Public repo

This repo is public. Issue, PR and commit text describes evidence by its content and attaches the files (`gh issue comment <n> --attach <file>`); it names no local path, account name, UID, e-mail or label of a local-only note (a file that exists only in `.local/`, or an item number in one), and that holds for the text of a committed test or comment too. A screenshot under `tests/screens/` has its three identity regions blacked out before it is committed: the UID plate, the account e-mail and the player name above the LV panel at the bottom left of the main window (36,626,98,20 in game pixels). `.claude/hooks/public-text-guard.py` checks the text, `tests/test_screens_privacy.py` the screenshots.

### Pointers

- Worktree setup, checks, post-land steps, `.local/` and the game data: `docs/agents/local-dev.md`.
- Anything on the emulator: the `maalc-live-test` skill. The emulator's resolution and window stay as the user set them; MaaFramework scales screenshots to 720p by itself.
- Subagents and delegated threads: `docs/agents/subagent-preamble.md`. The SubagentStart hook hands it to a subagent; a delegated thread (T3 `delegate_task`, Codex) starts as a session of its own, so it reads the file before its first step.
- Writing a PR body, or a PR or issue comment: `docs/agents/pr.md`.
- Review standards: `CODING_STANDARDS.md`.
- Pipeline JSON under `assets/resource/base/pipeline/` allows whole-line `//` comments, so `json.load` fails on it; drop those lines first, as `tests/test_pipeline.py` does.

### CI

A PR merges on a green `ci-ok`. When CI does not start, say so and wait; a local check does not replace it.

### Acceptance

When an acceptance run takes too long: verify what ran, report progress against the target, and let the user decide the next step. The bar stays where the issue put it.
