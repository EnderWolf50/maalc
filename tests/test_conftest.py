"""The per-test timeout of a file that runs a MaaFramework child (conftest.py), and the child run it waits for."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

import conftest
import daily_child


def item(module):
    return SimpleNamespace(module=module)


def test_a_child_file_waits_for_the_child_and_a_minute():
    assert conftest.child_timeout(item(SimpleNamespace(run_child=daily_child.run_child))) == 660
    assert conftest.child_timeout(item(SimpleNamespace(run_script=daily_child.run_script))) == 660  # test_gift_cells.py


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
        with pytest.raises(AssertionError, match="the child did not end in 600 s"):
            daily_child.run_child(path)
    assert len(runs) == 1


def test_a_child_that_outlasts_its_timeout_fails_with_what_it_printed():
    # #964: the stage the child was in, not only pytest-timeout's stack of the waiting test
    script = "import sys, time\nprint('[child 0.0 s] sweep Shop', file=sys.stderr, flush=True)\ntime.sleep(60)\n"
    with pytest.raises(AssertionError, match=r"did not end in 2 s\nstdout ends: \nstderr ends: \[child 0\.0 s\] sweep Shop"):
        daily_child.run_script([sys.executable, "-c", script], 2)
