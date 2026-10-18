# Coding standards

Judgement rules for review; the machine-checkable ones live in ruff (`E9`, `F`) and the tests.

## Recognition

- A recognition holds across theme colours: a structural or colour-independent signal (position, shape, greyscale match), not one template per colour.
- A colour or threshold heuristic ships with a sweep over `tests/screens` that shows its false positives (zero, or each one listed).
- A check proves the change: it fails on the old behaviour. START lighting up for any skill row is not proof that the right row was dragged.

## Fixes

- A reference implementation (AALC, MaaLimbus) that fails here is diffed against ours to the first difference before it is replaced.
- A performance or memory fix states before/after for both speed and memory; a regression on either is named in the PR.

## Tests

- New tests go in the feature's own `tests/test_<feature>.py`; `tests/test_actions.py` takes only tests of `agent/actions.py` helpers that have no feature file.
- A fixture under `tests/screens/` has the account's regions blacked out; `tests/test_screens_privacy.py` lists them.
