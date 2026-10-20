# PR bodies and comments

Every number is copied from command output in this session, and every "verified" points at the command or clip that shows it. Evidence follows AGENTS.md "Public repo": attach files with `--attach '<file>#<alt>'` (`gh pr create`, `gh pr comment`, `gh issue comment`).

## PR body

The `pr` skill's sections, then:

```markdown
## Verification

- Tests: `<command>` → `<passed> passed, <failed> failed`
- Live: <paths run on the emulator>; not run: <paths>, each with its follow-up issue
- Acceptance: `<criterion from the issue>` → met / not met, with the count
- Fixtures: real captures, or synthetic (file name ends `.synthetic.png`)
```

Drop a line that does not apply.

## Comments

Post with `gh pr comment <n>` or `gh issue comment <n>`, `--body-file` for more than one line. An issue is referenced as `#<n>` or `Refs #<n>`; closing belongs to the PR body.

Live-test evidence, with each clip or still attached:

```markdown
**Live test** at <short SHA>: <what was run, on what>

- <path>: <expected> → <seen> (<clip or still>)
- Not run: <path>, <why>; follow-up #<n>

Result: <passed / failed at <step>>
```

Review-fix reply, one per finding, on its thread (`gh api repos/EnderWolf50/maalc/pulls/<n>/comments/<id>/replies -f body=...`):

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
