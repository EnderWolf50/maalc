# Coding standards

Judgement rules for review; the machine-checkable ones live in ruff (`E9`, `F`), the tests (`tests/test_review_rules.py`), `tools/review_lint.py` (CI job `review-lint`: a test in the wrong file, a `GLOSSARY.md` `_Avoid_` term, a removed name still in use) and `.claude/hooks/public-text-guard.py` (the PR body's test line).

## Recognition

- A recognition holds across theme colours: a structural or colour-independent signal (position, shape, greyscale match), not one template per colour.
- A colour or threshold heuristic ships with a sweep over `tests/screens` that shows its false positives (zero, or each one listed).
- A threshold claim ("never fires on X", "separates A from B") states its sample size and is swept across all of `tests/screens/`, not one screenshot.
- A check proves the change: it fails on the old behaviour. START lighting up for any skill row is not proof that the right row was dragged. `uv run python tools/red_check.py <base>` lists the added or changed tests that pass on the base.

## Fixes

- A reference implementation (AALC, MaaLimbus) that fails here is diffed against ours to the first difference before it is replaced.
- A performance or memory fix states before/after for both speed and memory, each measured live (the same run, before and after the change); a regression on either is named in the PR.
- A workaround names the root-cause fix tried first, or why that fix could not be made.
- A node exempted from the watchdog carries its own bound (a timeout or a count) and a test of that bound.

## Claims

- An accuracy table is computed by the production function, not by a copy of its logic.
- A PR body that says "shared", "replaces" or "the only caller" has checked it with `rg`.

## Tests

- New tests go in the feature's own `tests/test_<feature>.py`; `tests/test_actions.py` takes only tests of `agent/actions.py` helpers that have no feature file.
- A fixture under `tests/screens/` is masked as AGENTS.md "Public repo" says; `tests/test_screens_privacy.py` lists the regions.
