"""The per-test timeout of a file that runs a MaaFramework child (conftest.py), and the child run it waits for."""

import subprocess
from types import SimpleNamespace

import pytest

import conftest
import daily_child


def item(module):
    return SimpleNamespace(module=module)


def test_a_child_file_waits_for_the_child_and_a_minute():
    assert conftest.child_timeout(item(SimpleNamespace(run_child=daily_child.run_child))) == 660


def test_any_other_file_keeps_the_default():
    assert conftest.child_timeout(item(SimpleNamespace())) is None
    assert conftest.child_timeout(SimpleNamespace()) is None


def test_a_child_that_timed_out_fails_the_files_other_tests_at_once(monkeypatch, tmp_path):
    runs = []

    def hang(*args, timeout, **kwargs):
        runs.append(args)
        raise subprocess.TimeoutExpired(args[0], timeout)

    monkeypatch.setattr(daily_child.subprocess, "run", hang)
    path = tmp_path / "test_hangs.py"
    for _ in range(2):
        with pytest.raises(subprocess.TimeoutExpired):
            daily_child.run_child(path)
    assert len(runs) == 1
