# Domain Docs

How the engineering skills consume this repo's domain documentation when exploring the codebase. The repo has one context: one `GLOSSARY.md` and one `docs/adr/`, both at the root.

## Before exploring, read these

- **`GLOSSARY.md`**: the project's terms, with the synonyms each one avoids.
- **`docs/adr/`**: the ADRs that touch the area you are about to work in (`0002-pipeline-hub-and-agent-decisions.md`, `0007-page-guard-before-each-tap.md`, ...).

The `domain-modeling` skill adds a term or an ADR when one gets resolved.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids; `tools/review_lint.py` flags an added Markdown line that uses one.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (page guard before each tap), but worth reopening because…_
