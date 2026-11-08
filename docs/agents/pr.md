# PR bodies and comments

Every number is copied from command output in this session, and every "verified" points at the command or clip that shows it. Evidence follows AGENTS.md "Public repo": attach files with `--attach '<file>#<alt>'` (`gh pr create`, `gh pr comment`, `gh issue comment`). Alt text is for images only: a video attached with `#<alt>` fails with `cannot set alt text on video` (seen 2026-10-27), so attach a video without `#<alt>`.

## Language

Issues, PRs and every comment on them are written in Traditional Chinese, titles and bodies alike: the user reads them, and a body that switches language is hard to follow (the user, 2026-11-08). Commit messages stay English. What a reader copies, searches or a tool parses keeps its form:

- code names, file paths, `file:line`, commands, quoted log lines and dialog text, links, numbers;
- GitHub's keywords `Closes #<n>`, `Fixes #<n>`, `Refs #<n>`, `Part of #<n>`;
- a PR title's Conventional Commits prefix, followed by Chinese: `fix(map): 第 5 層商店不再重複點擊`;
- the Verification keys `public-text-guard.py` reads: `Tests:`, `Live:`, `Acceptance:`, `Fixtures:`, the counts `N passed, M failed`, `Tests: none (docs only)`, and `not run` with its issue on a line about a path that was skipped.

Section headings in Chinese: 為什麼, 摘要, 範圍, 取捨, 證據 (**之前：** / **之後：**), 合併風險 (**門：** 單向 / 雙向, **影響範圍：**), 驗證.

An open issue or PR found in English is rewritten in place, its meaning, links, tables and `file:line` unchanged: save the old body, write the new one, `gh issue edit <n>` or `gh pr edit <n>` with `--title` and `--body-file`. `uv run python tools/rewrite_check.py <old> <new>` names each code span, link, reference or number the rewrite dropped, and lists the English words left for you to judge. Done when it prints no `dropped` line.

## PR body

The `pr` skill's sections, then:

```markdown
## Verification

- Tests: `<command>` → `<passed> passed, <failed> failed`, plus `, <skipped> skipped` when some skipped (a PR that changes only docs says `Tests: none (docs only)` instead)
- Live: <paths run on the emulator>; not run: <paths>, each with its follow-up issue
- Acceptance: `<criterion from the issue>` → met / not met, with the count
- Fixtures: real captures, or synthetic (file name ends `.synthetic.png`)
```

An issue the PR finishes only in part gets its body rewritten in the same session (`docs/agents/issue-tracker.md` "Keeping issues current").

`public-text-guard.py` denies `gh pr create|edit --body-file` when the body has neither `N passed, M failed[, K skipped]` nor `Tests: none (docs only)`, or a line saying `not run` names no issue (`#<n>`; `not run: none` passes).

## Comments

Post with `gh pr comment <n>` or `gh issue comment <n>`; a multi-line body follows `docs/agents/issue-tracker.md` (Create an issue). An issue is referenced as `#<n>` or `Refs #<n>`.

Live-test evidence, with the verdicts of the `maalc-live-test` skill's Report step and each clip attached:

```markdown
**Live test** at <short SHA>: <what was run>

- <check>: pass / fail / not reached (<clip>)
- Acceptance: `<criterion>` → met / not met
```

Review-fix reply, one per finding, on its thread: `gh api repos/{owner}/{repo}/pulls/<n>/comments/<id>/replies -f body='<one line>'`, or `-F body=@<absolute path>` for more lines:

```markdown
Fixed in <short SHA>: <what changed, one line>
<or: Not changed: <reason>>
```

Status update; on an issue a PR covers in part, it names what remains:

```markdown
**Status**: <done / in progress / blocked>

- Done: <item> (#<PR>)
- Next: <item>
- Blocked on: <who or what>, since <date>
```
