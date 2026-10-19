import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# tools/live/queue.py shares its name with the stdlib module: load it by path under another name.
spec = importlib.util.spec_from_file_location("live_queue", Path(__file__).resolve().parent.parent / "tools/live/queue.py")
lq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lq)


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_dead_tickets_are_dropped_and_live_ones_keep_arrival_order(tmp_path):
    (tmp_path / f"3-{os.getpid()}-late.ticket").write_text("x")
    gone = tmp_path / f"1-{dead_pid()}-gone.ticket"
    gone.write_text("x")
    (tmp_path / f"2-{os.getpid()}-early.ticket").write_text("x")
    assert [p.name.split("-", 2)[2] for p in lq.tickets(tmp_path)] == ["early.ticket", "late.ticket"]
    assert not gone.exists()


def test_run_waits_for_the_ticket_ahead_then_leaves_no_ticket(tmp_path):
    ahead = tmp_path / f"1-{os.getpid()}-ahead.ticket"  # a live holder that arrived first
    ahead.write_text("x")
    done = {}
    t = threading.Thread(target=lambda: done.setdefault("rc", lq.run(tmp_path, "me", [sys.executable, "-c", "pass"], poll=0.05)))
    t.start()
    time.sleep(0.4)
    assert t.is_alive() and "rc" not in done  # still queued behind `ahead`
    ahead.unlink()
    t.join(5)
    assert done["rc"] == 0
    assert list(tmp_path.glob("*.ticket")) == []


def test_status_marks_the_holder_and_the_queue(tmp_path):
    (tmp_path / f"1-{os.getpid()}-first.ticket").write_text("cmd a")
    (tmp_path / f"2-{os.getpid()}-second.ticket").write_text("cmd b")
    assert [line.split(" (")[0] for line in lq.status(tmp_path)] == ["RUNNING first", "#1      second"]


class FakeKernel:
    """kernel32 stand-in: OpenProcess fails (or not) and the process has a given exit code and start time."""

    def __init__(self, handle, exit_code=259, start=111):
        self.handle, self.exit_code, self.start = handle, exit_code, start

    def OpenProcess(self, *_):
        return self.handle

    def GetExitCodeProcess(self, _h, ref):
        ref._obj.value = self.exit_code

    def GetProcessTimes(self, _h, created, *_):
        created._obj.value = self.start

    def CloseHandle(self, _h):
        pass


def test_access_denied_from_openprocess_means_alive_not_dead():
    assert lq.win_alive(FakeKernel(0), 4, None, last_error=lambda: 5)  # another user's process
    assert not lq.win_alive(FakeKernel(0), 4, None, last_error=lambda: 87)  # ERROR_INVALID_PARAMETER: no such pid


def test_a_reused_pid_is_not_the_holder_that_took_the_ticket():
    k = FakeKernel(1, start=111)
    assert lq.win_alive(k, 4, 111) and lq.win_alive(k, 4, None)
    assert not lq.win_alive(k, 4, 222)  # a later process now owns the pid
    assert not lq.win_alive(FakeKernel(1, exit_code=0), 4, 111)  # exited


@pytest.mark.skipif(lq.started(os.getpid()) is None, reason="no process start time on this platform")
def test_ticket_of_a_reused_pid_is_dropped_but_the_real_holder_stays(tmp_path):
    mine = lq.started(os.getpid())
    kept = tmp_path / f"1-{os.getpid()}-real.ticket"
    kept.write_text(json.dumps({"cmd": "a", "start": mine}))
    reused = tmp_path / f"2-{os.getpid()}-stale.ticket"
    reused.write_text(json.dumps({"cmd": "b", "start": mine + 1}))
    assert lq.tickets(tmp_path) == [kept] and not reused.exists()


def test_run_writes_the_start_time_of_its_own_process_into_the_ticket(tmp_path):
    seen = {}
    lq.run(tmp_path, "x", [sys.executable, "-c", "pass"], is_alive=lambda pid, start: seen.update(pid=pid, start=start) or True, poll=0.01)
    assert seen == {"pid": os.getpid(), "start": lq.started(os.getpid())}
    assert list(tmp_path.glob("*.ticket")) == []


QUEUE_PY = Path(__file__).resolve().parent.parent / "tools/live/queue.py"
HOLDER = """import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("lq", sys.argv[1])
lq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lq)
wait = "import os, time, sys\\nwhile not os.path.exists(sys.argv[1]): time.sleep(0.05)"
sys.exit(lq.run(Path(sys.argv[2]), "holder", [sys.executable, "-c", wait, sys.argv[3]], poll=0.05))
"""
# the agent harness's background command: it detaches the holder, then stays until the harness kills its tree
LAUNCHER = """import subprocess, sys, time
subprocess.run([sys.executable, *sys.argv[1:]], check=True)
time.sleep(120)
"""


def wait_for(cond, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def kill_tree(p: subprocess.Popen) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        os.killpg(p.pid, signal.SIGKILL)  # the launcher leads its own group, as a harness's shell would
    p.wait(10)


def test_a_detached_holder_survives_a_tree_kill_of_its_launcher_and_keeps_the_resource(tmp_path):
    # POSIX: fails without detach's own session. Windows: the exited `detach` already cuts the tree taskkill
    # walks; leaving the harness's job (CREATE_BREAKAWAY_FROM_JOB) was checked live, not here.
    qdir, done, log = tmp_path / "q", tmp_path / "done", tmp_path / "hold.log"
    (tmp_path / "holder.py").write_text(HOLDER)
    (tmp_path / "launcher.py").write_text(LAUNCHER)
    launcher = subprocess.Popen([sys.executable, str(tmp_path / "launcher.py"), str(QUEUE_PY), "detach", "--log", str(log), "--",
                                 sys.executable, str(tmp_path / "holder.py"), str(QUEUE_PY), str(qdir), str(done)],
                                start_new_session=sys.platform != "win32")
    try:
        wait_for(lambda: log.exists() and "[queue] start holder" in log.read_text())
        kill_tree(launcher)
        time.sleep(0.5)
        assert [line.split(" (")[0] for line in lq.status(qdir)] == ["RUNNING holder"]
        assert lq.detached_status(log)[0]
    finally:
        done.touch()
    wait_for(lambda: not lq.detached_status(log)[0])
    assert lq.status(qdir) == []


def test_detached_status_tells_running_from_ended(tmp_path):
    log = tmp_path / "x.log"
    assert lq.detached_status(log) == (False, f"nothing was started with --log {log}")
    lq.pid_file(log).write_text(json.dumps({"pid": os.getpid(), "start": lq.started(os.getpid()), "cmd": "me"}))
    assert lq.detached_status(log) == (True, f"running pid {os.getpid()}: me")
    lq.pid_file(log).write_text(json.dumps({"pid": dead_pid(), "start": None, "cmd": "gone"}))
    log.write_text("first\nlast line\n")
    running, text = lq.detached_status(log)
    assert not running and text.startswith("ended pid ") and text.endswith(": last line")
