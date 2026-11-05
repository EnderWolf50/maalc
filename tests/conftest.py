"""CI shards the tests by file: SHARD=i of SHARDS=n keeps the files the greedy split below gives shard i. Unset, every
test runs."""

import inspect
import json
import os

import pytest

from shard_seconds import TABLE

# Seconds each file took on a CI runner, written by tools/shard_seconds.py; an unlisted file counts 0.15 s a test.
# CI's shard-balance job fails when a number no longer matches the run.
FILE_SECONDS = json.loads(TABLE.read_text(encoding="utf-8"))


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
