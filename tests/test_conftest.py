"""The per-test timeout of a file that runs a MaaFramework child (conftest.py)."""

import functools
from types import SimpleNamespace

import conftest


def item(module):
    return SimpleNamespace(module=module)


def test_a_child_file_waits_for_the_child_and_a_minute():
    @functools.cache
    def run_child(path, timeout=600):
        return path

    assert conftest.child_timeout(item(SimpleNamespace(run_child=run_child))) == 660


def test_any_other_file_keeps_the_default():
    assert conftest.child_timeout(item(SimpleNamespace())) is None
    assert conftest.child_timeout(SimpleNamespace()) is None
