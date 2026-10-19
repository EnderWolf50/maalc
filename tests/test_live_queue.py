import importlib.util
import json
import os
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
HOLDER = """import importlib.util, os, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("lq", sys.argv[1])
lq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lq)
done = sys.argv[3]
wait = "import os, time, sys\\nwhile not os.path.exists(sys.argv[1]): time.sleep(0.05)"
sys.exit(lq.run(Path(sys.argv[2]), "holder", [sys.executable, "-c", wait, done], poll=0.05))
"""


def wait_for(cond, timeout=15.0):
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_a_detached_holder_outlives_its_launcher_and_keeps_the_resource(tmp_path):
    qdir, done, log, holder = tmp_path / "q", tmp_path / "done", tmp_path / "hold.log", tmp_path / "holder.py"
    holder.write_text(HOLDER)
    launcher = subprocess.run([sys.executable, str(QUEUE_PY), "detach", "--log", str(log), "--",
                               sys.executable, str(holder), str(QUEUE_PY), str(qdir), str(done)],
                              capture_output=True, text=True, timeout=30)
    assert launcher.returncode == 0, launcher.stderr  # the launcher is gone: killing it now kills nothing
    wait_for(lambda: log.exists() and "[queue] start holder" in log.read_text())
    assert [line.split(" (")[0] for line in lq.status(qdir)] == ["RUNNING holder"]
    assert lq.detached_status(log).startswith("running pid ")
    done.touch()
    wait_for(lambda: lq.detached_status(log).startswith("ended"))
    assert lq.status(qdir) == []


def test_detached_status_tells_running_from_ended(tmp_path):
    log = tmp_path / "x.log"
    assert lq.detached_status(log) == f"nothing was started with --log {log}"
    lq.pid_file(log).write_text(json.dumps({"pid": os.getpid(), "start": lq.started(os.getpid()), "cmd": "me"}))
    assert lq.detached_status(log) == f"running pid {os.getpid()}: me"
    lq.pid_file(log).write_text(json.dumps({"pid": dead_pid(), "start": None, "cmd": "gone"}))
    log.write_text("first\nlast line\n")
    assert lq.detached_status(log).startswith("ended pid ") and lq.detached_status(log).endswith(": last line")

