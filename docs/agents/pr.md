# PR bodies and comments

Every number is copied from command output in this session, and every "verified" points at the command or clip that shows it. Evidence follows AGENTS.md "Public repo": attach files with `--attach '<file>#<alt>'` (`gh pr create`, `gh pr comment`, `gh issue comment`). Alt text is for images only: a video attached with `#<alt>` fails with `cannot set alt text on video` (seen 2026-10-27), so attach a video without `#<alt>`.

## PR body

The `pr` skill's sections, then:

```markdown
## Verification

- Tests: `<command>` → `<passed> passed, <failed> failed`
- Live: <paths run on the emulator>; not run: <paths>, each with its follow-up issue
- Acceptance: `<criterion from the issue>` → met / not met, with the count
- Fixtures: real captures, or synthetic (file name ends `.synthetic.png`)
```

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
