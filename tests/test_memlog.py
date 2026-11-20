import os
import sys

import pytest

import memlog


def test_a_floor_line_names_the_floor_both_processes_in_mb_and_the_minutes_into_the_run():
    # #391: one line a floor; working set (what the 2026-10 runs called RSS) first, private bytes (the commit charge) beside it
    line = memlog.floor_line(6, 7512.0, memlog.Mem(1834.4, 1920.6), memlog.Mem(540.2, 509.8))
    assert line == "floor 6 memory: tasker 1834 MB (private 1921 MB), agent 540 MB (private 510 MB), 125 min into the run"


def test_a_floor_line_marks_what_was_not_read():
    # a resumed run has no start time; a tasker whose pid the agent was not handed (an older client) reads nothing
    line = memlog.floor_line(11, None, None, memlog.Mem(512.0, 500.0))
    assert line == "floor 11 memory: tasker ?, agent 512 MB (private 500 MB), ? min into the run"


@pytest.mark.parametrize("start, now, seconds", [
    ("2026-11-20T01:00:00.000Z", "2026-11-20T03:05:30.000Z", 7530.0),
    (None, "2026-11-20T03:05:30.000Z", None),  # an agent restarted mid-run does not know when the run began
    ("not a time", "2026-11-20T03:05:30.000Z", None),
])
def test_the_time_into_the_run_is_from_its_start(start, now, seconds):
    assert memlog.seconds_since(start, now) == seconds


@pytest.mark.parametrize("environ, pid", [({"MAALC_TASKER_PID": "4120"}, 4120), ({}, None), ({"MAALC_TASKER_PID": "x"}, None)])
def test_the_tasker_is_the_pid_the_runner_hands_the_agent(environ, pid):
    assert memlog.tasker_pid(environ) == pid


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows' process counters")
def test_this_process_and_another_are_read_and_a_pid_that_runs_nothing_is_not():
    me = memlog.process_memory()
    assert me is not None and me.working_set > 1 and me.private > 1
    by_pid = memlog.process_memory(os.getpid())
    assert by_pid is not None and abs(by_pid.working_set - me.working_set) < 200
    assert memlog.process_memory(2**31 - 4) is None  # no such process: the line shows "?"


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows' process counters")
def test_a_read_that_fails_in_windows_reads_as_unknown_and_does_not_raise(monkeypatch):
    # the line is only a record (#391): a failed read must not fail PickThemePack, which sets the floor's difficulty after it
    def broken(name):
        raise OSError("kernel32 not loaded")
    monkeypatch.setattr(memlog.ctypes, "WinDLL", broken)
    monkeypatch.setenv(memlog.TASKER_PID, "4120")
    assert memlog.floor_memory(3, None, "2026-11-20T03:05:30.000Z") == "floor 3 memory: tasker ?, agent ?, ? min into the run"
