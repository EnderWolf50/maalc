---
name: pr.patch
description: "Patch for pr: maalc PR bodies end with a Verification section."
disable-model-invocation: true
user-invocable: false
---

When running `pr` in maalc, the body ends with **Verification**, every number copied from command output in this session:

- Tests: `<command>` → `<passed> passed, <failed> failed`
- Live: the paths run on the emulator, and the paths not run (each gets a follow-up issue, linked here)
- Acceptance: `<criterion from the issue>` → met / not met, with the count
- Fixtures: real captures, or synthetic (file name ends `.synthetic.png`)

The body names no local path, account name, UID or e-mail (AGENTS.md "Public repo"); evidence goes in with `--attach`.

Done: every "verified" in the body points at the command or clip that shows it.
