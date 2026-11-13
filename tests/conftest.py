"""CI shards the tests by file: SHARD=i of SHARDS=n keeps the files the greedy split below gives shard i. Unset, every
test runs. The run also notes the docs and gui files the tests open, and fails when the CI `read` filter lacks one
(tests/ci_filter.py)."""

import inspect
import json
import os

import pytest

import ci_filter
from live.queue import TICKET_ENV
from shard_seconds import TABLE

# Seconds each file took on a CI runner, written by tools/shard_seconds.py; an unlisted file counts 0.15 s a test.
# CI's shard-balance job reports (does not block) when a number no longer matches the run.
FILE_SECONDS = json.loads(TABLE.read_text(encoding="utf-8"))

# A run under a bench ticket (tools/check.py through tools/live/queue.py) inherits that ticket: a test hold must not
# publish its state beside the real one (tools/live/hold.py).
os.environ.pop(TICKET_ENV, None)


ci_filter.install()  # from here on, every file the tests open is noted (#684)


def pytest_sessionfinish(session, exitstatus):
    """A run that opened a docs, gui or root *.md file the CI `read` filter lacks fails: a change to that file alone would
    skip the tests that read it (tests/ci_filter.py)."""
    missing = ci_filter.unlisted(ci_filter.all_opened())
    ci_filter.forget_log()
    if missing:
        print(f"\nopened, but missing from the `read` filter of the changes job in .github/workflows/ci.yml: {missing}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def child_timeout(item):
    """Seconds a test of a file that runs a MaaFramework child may take: `run_child`'s own timeout and a minute. The
    file's first test pays for the whole child run (about 380 s on CI on 2026-10-30), over the 300 s default, and the
    child's TimeoutExpired names the file where pytest-timeout would end the whole shard. A file is one when its module
    holds the name `run_child` (`from daily_child import run_child`); the marker also outranks `--timeout` given on the
    command line."""
    run_child = getattr(getattr(item, "module", None), "run_child", None)
    return inspect.signature(run_child).parameters["timeout"].default + 60 if run_child else None


def pytest_collection_modifyitems(config, items):
    for item in items:
        if seconds := child_timeout(item):
            item.add_marker(pytest.mark.timeout(seconds))
    shards = int(os.environ.get("SHARDS", 1))
    if shards < 2:
        return
    files = {}
    for item in items:
        files.setdefault(item.path.name, []).append(item)
    cost = {name: FILE_SECONDS.get(name, 0.15 * len(tests)) for name, tests in files.items()}
    load, mine = [0.0] * shards, set()
    for name in sorted(cost, key=lambda n: (-cost[n], n)):
        shard = load.index(min(load))
        load[shard] += cost[name]
        if shard == int(os.environ.get("SHARD", 0)):
            mine.add(name)
    config.hook.pytest_deselected(items=[i for i in items if i.path.name not in mine])
    items[:] = [i for i in items if i.path.name in mine]
