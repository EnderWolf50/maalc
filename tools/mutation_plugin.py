"""pytest plugin of tools/mutation.py.

MAALC_MUTANT=<module>:<index>: importing agent/<module>.py runs that mutant's tree instead of the file. The module keeps
its real `__file__`, so the data it finds next to itself still loads. Nothing on disk changes.

MAALC_COVER=<json path>: the lines of the swept modules the run executes, written to that file as {module: [line, ...]}
when the session ends (sys.monitoring, Python 3.12).
"""

import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path

from mutation import AGENT, MODULES, mutant


class MutantLoader(importlib.abc.Loader):
    def __init__(self, module, index):
        self.module, self.index = module, index

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        tree, _ = mutant(self.module, self.index)
        exec(compile(tree, str(AGENT / f"{self.module}.py"), "exec"), module.__dict__)


class MutantFinder(importlib.abc.MetaPathFinder):
    def __init__(self, module, index):
        self.loader = MutantLoader(module, index)

    def find_spec(self, name, path=None, target=None):
        if name != self.loader.module:
            return None
        return importlib.util.spec_from_file_location(name, AGENT / f"{name}.py", loader=self.loader)


if spec := os.environ.get("MAALC_MUTANT"):
    name, index = spec.split(":")
    sys.modules.pop(name, None)
    sys.meta_path.insert(0, MutantFinder(name, int(index)))

COVER = os.environ.get("MAALC_COVER")
IMPORT = "(import)"  # the lines run while no test runs: imports at collection
FILES = {os.path.normcase(str(AGENT / f"{m}.py")): m for m in MODULES}
LINES = {m: {} for m in MODULES}  # module -> line -> the test ids that ran it
CURRENT = [IMPORT]

if COVER:
    TOOL = sys.monitoring.COVERAGE_ID
    sys.monitoring.use_tool_id(TOOL, "mutation")

    def on_line(code, line, files=FILES, lines=LINES, now=CURRENT, disable=sys.monitoring.DISABLE,
                normcase=os.path.normcase):
        # Each place reports once a test (restart_events between tests); the names are bound here as module globals
        # are gone at interpreter shutdown.
        module = files.get(normcase(code.co_filename))
        if module is not None:
            lines[module].setdefault(line, set()).add(now[0])
        return disable

    sys.monitoring.register_callback(TOOL, sys.monitoring.events.LINE, on_line)
    sys.monitoring.set_events(TOOL, sys.monitoring.events.LINE)

ONLY = os.environ.get("MAALC_TESTS")  # a file of test ids, one a line: only those run


def pytest_configure(config):
    """A test that runs a MaaFramework child skips: a child takes minutes and imports the file from disk, not the mutant."""
    import functools

    import daily_child
    import pytest

    @functools.wraps(daily_child.run_child)  # tests/conftest.py reads its timeout default
    def no_child(*args, **kwargs):
        pytest.skip("MaaFramework child: left out of the mutation sweep")

    daily_child.run_child = no_child


def pytest_collection_modifyitems(config, items):
    """The tests that compare committed tables with this machine's unpacked game data go: CI skips them, they run no
    agent code, and a game update the tables have not caught up with fails them whatever the mutant."""
    only = set(Path(ONLY).read_text(encoding="utf-8").splitlines()) if ONLY else None
    gone = [i for i in items if "when_it_is_unpacked" in i.name or (only is not None and i.nodeid not in only)]
    if gone:
        config.hook.pytest_deselected(items=gone)
        items[:] = [i for i in items if i not in gone]


if COVER:
    import pytest

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(item, nextitem):
        CURRENT[0] = item.nodeid
        sys.monitoring.restart_events()
        try:
            return (yield)
        finally:
            CURRENT[0] = IMPORT

    SECONDS = {}

    def pytest_runtest_logreport(report):
        SECONDS[report.nodeid] = SECONDS.get(report.nodeid, 0) + report.duration


def pytest_sessionfinish(session):
    if COVER:
        found = {m: {str(n): sorted(ids) for n, ids in sorted(lines.items())} for m, lines in LINES.items() if lines}
        Path(COVER).write_text(json.dumps({"lines": found, "seconds": SECONDS}), encoding="utf-8")
