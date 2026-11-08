# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Language**: titles, bodies and comments in Traditional Chinese, code and log lines as they are; `docs/agents/pr.md` "Language" says what stays English and how to rewrite an English issue.
- **Create an issue**: `gh issue create --title "..." --body "..." --milestone <v1|v2> --label <triage label>` (see **Keeping issues current**). A multi-line body: write it with the Write tool and pass `--body-file <absolute path>` (the form `.claude/hooks/public-text-guard.py` can read; it denies a heredoc, `$(...)` and stdin).
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>` afterwards (`gh` 2.94+). Older `gh`: `gh api --method POST repos/EnderWolf50/maalc/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>` (database id, as in **Blocking** below). Without sub-issues, put `Part of #<parent>` at the top of the child body.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`.
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (see **Make an issue a sub-issue of a parent**). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/EnderWolf50/maalc/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/EnderWolf50/maalc/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: as in **Keeping issues current** (Starting work on an issue), the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.

## Keeping issues current

Every open issue carries:

- **A milestone.** `v1` when #34's acceptance or AALC parity (#21) needs it; `v2` for #1's Deferred items and work beyond AALC parity. A sub-issue takes its parent's milestone; an issue split off another takes the milestone of the part it carries.
- **Exactly one triage label** from `triage-labels.md`. A new issue starts at `needs-triage` unless its body is already fully specified. An issue labelled `wontfix` is closed.

An issue in progress carries **an assignee**, its claim, and keeps it through the close: an issue closed as completed has one.

A map (`wayfinder:map`) or a long-running tracker (`tracking`, such as #203, #251, #252) carries none of these.

When to act:

- **Creating an issue:** pass `--milestone` and `--label` in the same `gh issue create`.
- **Starting work on an issue** (its branch or worktree): claim it first, `gh issue edit <n> --add-assignee @me`. A session that delegates an issue claims it before the hand-off. The session that claimed an issue drops the claim (`--remove-assignee @me`) when the work stops without a PR.
- **A PR finishes part of an issue it does not close:** in the same session, rewrite the issue body. Done items move to a `已完成` list with the PR or commit, and the `file:line` references the body cites are refreshed. A map or tracker that lists an issue the PR closes gets its box ticked.
- **A comment widens an issue's scope** (as #94 gained the 15-floor switch): split the new scope into its own issue with its own milestone instead.
- **Session start for issue or PR work, and after creating issues:** run `uv run python tools/issue_audit.py`. Exit 1 lists issues without a milestone or a single triage label, and issues without an assignee that an open PR closes or that were closed as completed; fix them. It also lists the open issues a PR merged in the last 14 days names, and those untouched for 14 days. Check each against `main`: close it, rewrite its body, or comment why it is still current.
