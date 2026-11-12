import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from live import queue as lq


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


@pytest.mark.parametrize("second", [1_800_000_000_000_000_000, 1_799_999_999_999_000_000], ids=["same-tick", "clock-back"])
def test_a_ticket_of_the_same_process_and_name_sorts_after_the_one_already_there(tmp_path, monkeypatch, second):
    # #636: Python 3.12's wall clock on Windows ticks every 15.6 ms, so two `ship.py land` threads of one test got the
    # same stamp, pid and name: the second ticket overwrote the first and landed at once on the Windows CI runner.
    clock = iter([1_800_000_000_000_000_000, second])
    monkeypatch.setattr(lq.time, "time_ns", lambda: next(clock))
    one = lq.place(tmp_path, "land", ["a"], False)
    two = lq.place(tmp_path, "land", ["b"], False)
    assert one != two and lq.tickets(tmp_path) == [one, two]
    assert lq.read(one)[0] == "a"


def test_a_placed_ticket_names_its_stamp_pid_and_task(tmp_path, monkeypatch):
    monkeypatch.setattr(lq.time, "time_ns", lambda: 1_800_000_000_000_000_000)
    me = lq.place(tmp_path, "live1", ["a"], False)
    assert lq.Ticket.of(me) == ("1800000000000000000", str(os.getpid()), "live1")
    assert lq.Ticket.of(me).path(tmp_path) == me


def test_a_first_ticket_whose_place_is_taken_by_one_of_its_own_process_goes_behind_it(tmp_path):
    # #636: a plain ticket of this process and name just behind the holder holds the name a first ticket would take.
    alive = lambda pid, start: True  # noqa: E731
    holder = ticket(tmp_path, "1000000000000000001", "holder", 111)
    plain = tmp_path / f"1000000000000000002-{os.getpid()}-land.ticket"
    plain.write_text(json.dumps({"cmd": "plain", "start": None, "first": False}))
    first = lq.place(tmp_path, "land", ["urgent"], True, alive)
    assert first != plain and lq.read(plain)[0] == "plain" and lq.read(first)[0] == "urgent"
    assert lq.tickets(tmp_path, alive) == [holder, plain, first]


def test_a_first_ticket_goes_ahead_of_a_plain_one_placed_in_the_holders_clock_tick(tmp_path, monkeypatch):
    # #636: a plain ticket of the holder's tick sits FIRST_GAP behind it, so a first ticket placed later still goes ahead.
    alive = lambda pid, start: True  # noqa: E731
    holder = ticket(tmp_path, "1800000000000000000", "holder", 111)
    monkeypatch.setattr(lq.time, "time_ns", lambda: 1_800_000_000_000_000_000)
    plain = lq.place(tmp_path, "plain", ["plain"], False, alive)
    first = lq.place(tmp_path, "urgent", ["urgent"], True, alive)
    assert lq.tickets(tmp_path, alive) == [holder, first, plain]


def ticket(qdir: Path, stamp: str, name: str, start: int, first: bool = False, cmd: str = "hold") -> Path:
    p = qdir / f"{stamp}-{os.getpid()}-{name}.ticket"
    p.write_text(json.dumps({"cmd": cmd, "start": start, "first": first}))
    return p


def ends_on_check(start: int, gone: Path):
    """An is_alive under which every process lives, and checking the one that started at `start` deletes `gone`: a run
    that ends after the listing globbed its ticket and before the ticket is read (#577)."""
    def is_alive(_pid, s):
        if s == start:
            gone.unlink(missing_ok=True)
        return True
    return is_alive


def test_a_ticket_that_leaves_before_the_listing_reads_it_is_skipped(tmp_path):
    kept = ticket(tmp_path, "1000000000000000001", "kept", 111)
    left = ticket(tmp_path, "1000000000000000002", "left", 222)
    assert lq.tickets(tmp_path, ends_on_check(111, left)) == [kept]


def test_status_leaves_out_a_ticket_that_left_after_the_listing(tmp_path):
    ticket(tmp_path, "1000000000000000001", "holder", 111)
    left = ticket(tmp_path, "1000000000000000002", "left", 222)
    ticket(tmp_path, "1000000000000000003", "other", 333)
    lines = lq.status(tmp_path, ends_on_check(222, left))
    assert [line.split(" (")[0] for line in lines] == ["RUNNING holder", "#1      other"]


def test_a_first_ticket_still_goes_behind_the_first_ones_when_one_of_them_leaves_as_it_is_placed(tmp_path):
    ticket(tmp_path, "1000000000000000001", "holder", 111)
    left = ticket(tmp_path, "1000000000000000002", "left", 222, first=True)
    ticket(tmp_path, "1000000000000000003", "daily1", 333, first=True)
    ticket(tmp_path, "1000000000000000009", "waiting", 444)
    lq.place(tmp_path, "daily2", ["hold"], first=True, is_alive=ends_on_check(222, left))
    assert [p.name.split("-", 2)[2] for p in sorted(tmp_path.glob("*.ticket"))] == [
        "holder.ticket", "daily1.ticket", "daily2.ticket", "waiting.ticket"]


def test_turn_names_only_the_tickets_ahead_still_there_when_it_says_it_waits(tmp_path):
    left = ticket(tmp_path, "1000000000000000001", "holder", 111, cmd="holder run")
    ahead = ticket(tmp_path, "1000000000000000002", "next", 222, cmd="next run")
    said = []

    def on_wait(calls):
        said.append(calls)
        ahead.unlink()

    with lq.turn(tmp_path, "me", ["hold"], is_alive=ends_on_check(111, left), sleep=lambda s: None, on_wait=on_wait):
        assert said == [[(str(os.getpid()), "next run")]]


def test_turn_says_nothing_when_every_ticket_ahead_left_before_it_names_them(tmp_path):
    left = ticket(tmp_path, "1000000000000000001", "holder", 111)
    said = []
    with lq.turn(tmp_path, "me", ["hold"], is_alive=ends_on_check(111, left), sleep=lambda s: None, on_wait=said.append):
        assert said == []


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


def all_live(_pid, _start):
    return True


def remove_own_and_holder(mine: dict[Path, str], own: list[Path], holder: Path) -> None:
    """Delete the waiter's own ticket, then the holder's; `mine` keeps the own one's text to let the waiter go again."""
    for p in own:
        mine[p] = p.read_text()
        p.unlink()
    holder.unlink()


def ends_soon(t: threading.Thread, mine: dict[Path, str], what: str) -> None:
    t.join(2)
    if t.is_alive():
        for p, text in mine.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        t.join(5)
        pytest.fail(f"{what} still waits after its ticket was removed")


def test_turn_does_not_run_the_block_when_its_ticket_is_removed_while_it_waits(tmp_path):
    holder = ticket(tmp_path, "1000000000000000001", "holder", 111)
    mine, ran, ended = {}, [], {}

    def waits():
        try:
            with lq.turn(tmp_path, "me", ["hold"], is_alive=all_live, sleep=lambda s: time.sleep(0.01),
                         on_wait=lambda ahead: remove_own_and_holder(mine, list(tmp_path.glob("*-me.ticket")), holder)):
                ran.append("block")
        except SystemExit as e:
            ended["exit"] = e

    t = threading.Thread(target=waits, daemon=True)
    t.start()
    ends_soon(t, mine, "turn()")
    (me,) = mine
    assert isinstance(ended.get("exit"), lq.TicketGone) and me.name in str(ended["exit"])
    assert ran == []


def clears_when_it_waits(qdir: Path, holder: Path, holder_start: int, mine: dict[Path, str], folder: bool):
    """An is_alive under which every process lives. Its second look at the holder comes after the waiter queued behind
    it and said it waits: it removes the waiter's ticket and the holder's, or the whole queue folder."""
    looks = []

    def is_alive(_pid, start):
        if start == holder_start:
            looks.append(start)
            if len(looks) == 2:
                own = list(qdir.glob("*-me.ticket"))
                if folder:
                    mine.update((p, p.read_text()) for p in own)
                    shutil.rmtree(qdir)
                else:
                    remove_own_and_holder(mine, own, holder)
        return True
    return is_alive


@pytest.mark.parametrize("folder", [False, True], ids=["tickets-removed", "folder-removed"])
def test_run_does_not_start_its_command_when_its_ticket_is_removed_while_it_waits(tmp_path, capsys, folder):
    qdir = tmp_path / "bench"
    qdir.mkdir()
    holder = ticket(qdir, "1000000000000000001", "holder", 111)
    marker, mine, done = tmp_path / "ran", {}, {}
    touch = [sys.executable, "-c", "import pathlib, sys; pathlib.Path(sys.argv[1]).touch()", str(marker)]
    is_alive = clears_when_it_waits(qdir, holder, 111, mine, folder)
    t = threading.Thread(target=lambda: done.setdefault("rc", lq.run(qdir, "me", touch, is_alive=is_alive, poll=0.01)),
                         daemon=True)
    t.start()
    ends_soon(t, mine, "run()")
    (me,) = mine
    assert done["rc"] == 1 and not marker.exists()
    result = json.loads(lq.result_path(qdir, "me").read_text())
    assert result["exit"] == 1 and me.name in result["not_started"]
    assert me.name in capsys.readouterr().out


def test_a_first_ticket_runs_right_after_the_holder_ahead_of_the_waiting_ones(tmp_path):
    # #465: the daily task, due before the 05:00 reset, waited behind every run another agent had queued. With --first
    # it goes after the run that holds the resource, which is not cut short, and before the ones waiting.
    holder = tmp_path / f"1000000000000000001-{os.getpid()}-holder.ticket"
    waiting = tmp_path / f"1000000000000000005-{os.getpid()}-waiting.ticket"
    holder.write_text("x")
    waiting.write_text("x")
    done = {}
    t = threading.Thread(target=lambda: done.setdefault(
        "rc", lq.run(tmp_path, "daily", [sys.executable, "-c", "pass"], poll=0.05, first=True)))
    t.start()
    wait_for(lambda: len(list(tmp_path.glob("*.ticket"))) == 3)
    assert [p.name.split("-", 2)[2] for p in lq.tickets(tmp_path)] == ["holder.ticket", "daily.ticket", "waiting.ticket"]
    assert t.is_alive()  # the holder's run is not cut short
    holder.unlink()
    t.join(5)
    assert done["rc"] == 0 and waiting.exists()  # it ran while the waiting ticket still waits


def test_a_first_ticket_is_placed_again_when_the_holder_leaves_before_it_is_written(tmp_path, monkeypatch):
    # Review of #465: between reading the queue and writing the ticket, the holder ended and the next run started; a
    # ticket just behind the old holder would sort ahead of that run and start a second command.
    holder = tmp_path / f"1000000000000000001-{os.getpid()}-holder.ticket"
    taken = tmp_path / f"1000000000000000005-{os.getpid()}-taken.ticket"
    holder.write_text("x")
    taken.write_text("x")
    real = lq.tickets

    def holder_leaves_after_the_read(qdir, is_alive=lq.alive):
        q = real(qdir, is_alive)
        holder.unlink(missing_ok=True)  # it ends right after this read; `taken` is first now and starts
        return q
    monkeypatch.setattr(lq, "tickets", holder_leaves_after_the_read)
    me = lq.place(tmp_path, "daily", ["hold"], first=True)
    assert [p.name.split("-", 2)[2] for p in real(tmp_path)] == ["taken.ticket", "daily.ticket"]
    assert me.exists()


def test_a_second_first_ticket_goes_behind_the_first_one(tmp_path):
    holder = tmp_path / f"1000000000000000001-{os.getpid()}-holder.ticket"
    holder.write_text(json.dumps({"cmd": "hold", "start": None}))
    (tmp_path / f"1000000000000000002-{os.getpid()}-daily1.ticket").write_text(json.dumps({"cmd": "hold", "start": None, "first": True}))
    (tmp_path / f"1000000000000000009-{os.getpid()}-waiting.ticket").write_text(json.dumps({"cmd": "hold", "start": None}))
    lq.place(tmp_path, "daily2", ["hold"], first=True)
    assert [p.name.split("-", 2)[2] for p in lq.tickets(tmp_path)] == [
        "holder.ticket", "daily1.ticket", "daily2.ticket", "waiting.ticket"]


def test_status_marks_a_waiting_first_ticket_for_the_holder_to_let_in(tmp_path):
    # A live-test hold spans several bot runs: its agent reads status before the next one and ends the hold for it.
    (tmp_path / f"1-{os.getpid()}-holder.ticket").write_text(json.dumps({"cmd": "hold", "start": None}))
    (tmp_path / f"2-{os.getpid()}-daily.ticket").write_text(json.dumps({"cmd": "hold", "start": None, "first": True}))
    (tmp_path / f"3-{os.getpid()}-other.ticket").write_text(json.dumps({"cmd": "hold", "start": None, "first": False}))
    holder, daily, other = lq.status(tmp_path)
    assert "FIRST" in daily and "FIRST" not in holder and "FIRST" not in other


def test_a_first_ticket_with_no_holder_runs_at_once(tmp_path):
    assert lq.run(tmp_path, "daily", [sys.executable, "-c", "pass"], poll=0.05, first=True) == 0


def test_the_cli_passes_first_to_run(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(lq, "local_dir", lambda *parts: tmp_path)
    monkeypatch.setattr(lq, "run", lambda qdir, name, cmd, log=None, first=False: seen.update(cmd=cmd, first=first) or 0)
    assert lq.main(["run", "--resource", "emulator", "--name", "daily", "--first", "--", "hold"]) == 0
    assert seen == {"cmd": ["hold"], "first": True}


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
    lq.pid_file(log).write_text('{"pid": 1')  # detach is still writing it
    assert lq.detached_status(log)[0] is False and not lq.detached_running(log)
    lq.pid_file(log).write_text(json.dumps({"pid": os.getpid(), "start": lq.started(os.getpid()), "cmd": "me"}))
    assert lq.detached_status(log) == (True, f"running pid {os.getpid()}: me") and lq.detached_running(log)
    lq.pid_file(log).write_text(json.dumps({"pid": dead_pid(), "start": None, "cmd": "gone"}))
    log.write_text("first\nlast line\n")
    running, text = lq.detached_status(log)
    assert not running and text.startswith("ended pid ") and text.endswith(": last line")
    assert not lq.detached_running(log)


def test_resume_says_a_bot_that_ended_unwatched_needs_step_7(tmp_path):
    task = tmp_path / "t"
    task.mkdir()
    pid = lambda log, doc: lq.pid_file(log).write_text(json.dumps(doc))  # noqa: E731
    pid(task / "hold.log", {"pid": os.getpid(), "start": lq.started(os.getpid()), "cmd": "hold"})
    pid(task / "bot.log", {"pid": dead_pid(), "start": None, "cmd": "bot"})
    (task / "bot.log").write_text("[maalc] victory\n[maalc] claimed with 0 weekly bonus(es)\n[maalc] noise\n")
    (task / "hold.log").write_text("[queue] start t\n[hold] bot ended 2020-01-01T10:00:00\n")
    out = "\n".join(lq.resume(task, now=datetime.fromisoformat("2020-01-01T10:25:00").timestamp()))
    assert "bot ended at 10:00:00 (25 min ago)" in out and "claimed with 0" in out and "  [maalc] noise" not in out
    assert "done file: absent" in out and "next: bot ended while you were away: step 7" in out
    (task / "done").touch()
    assert "step 10" in lq.resume(task)[-1]


def test_status_marks_a_holder_whose_bot_ended_long_ago_without_a_done_file(tmp_path):
    bot, done = tmp_path / "bot.log", tmp_path / "done"
    bot.write_text("x")
    lq.pid_file(bot).write_text(json.dumps({"pid": dead_pid(), "start": None, "cmd": "bot"}))
    (tmp_path / f"1-{os.getpid()}-t.ticket").write_text(f"hold --done {done} --guard {bot}")
    later = bot.stat().st_mtime
    assert "bot ended 25 min ago, waiting for the agent" in lq.status(tmp_path, now=later + 1500)[0]
    assert "bot ended" not in lq.status(tmp_path, now=later + 60)[0]  # still within the 10 min
    done.touch()
    assert "bot ended" not in lq.status(tmp_path, now=later + 1500)[0]


def test_status_with_a_glob_guard_counts_from_the_last_bot_and_not_while_one_runs(tmp_path):
    # live-1 T-live: `--guard bot*.log` follows every bot run of one hold.
    done, first, second = tmp_path / "done", tmp_path / "bot.log", tmp_path / "bot-b.log"
    for log in (first, second):
        log.write_text("x")
        lq.pid_file(log).write_text(json.dumps({"pid": dead_pid(), "start": None, "cmd": "bot"}))
    os.utime(first, (0, second.stat().st_mtime - 1200))  # the first run ended 20 min before the second
    (tmp_path / f"1-{os.getpid()}-t.ticket").write_text(f"hold --done {done} --guard {tmp_path / 'bot*.log'}")
    later = second.stat().st_mtime
    assert "bot ended" not in lq.status(tmp_path, now=later + 60)[0]
    assert "bot ended 25 min ago" in lq.status(tmp_path, now=later + 1500)[0]
    lq.pid_file(second).write_text(json.dumps({"pid": os.getpid(), "start": None, "cmd": "bot"}))  # runs again
    assert "bot ended" not in lq.status(tmp_path, now=later + 1500, is_alive=lambda pid, start: pid == os.getpid())[0]


def test_resume_next_step_while_queued_or_when_nothing_started(tmp_path):
    task = tmp_path / "t"
    task.mkdir()
    assert "nothing was started" in lq.resume(task)[-1]
    lq.pid_file(task / "hold.log").write_text(json.dumps({"pid": os.getpid(), "start": lq.started(os.getpid()), "cmd": "hold"}))
    (task / "hold.log").write_text("[queue] waiting, 1 ahead\n")
    assert "still queued" in lq.resume(task)[-1]
    (task / "hold.log").write_text("[queue] start t\n")
    assert "no bot started" in lq.resume(task)[-1]


class Clock:
    """A fake monotonic clock: sleep moves it, nothing waits."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def waiting(tmp_path, name, timeout_s, ticket=True):
    clock, said = Clock(), []
    if ticket:
        (tmp_path / f"1-{os.getpid()}-{lq.ticket_name(name)}.ticket").write_text("cmd")  # as run() names it
    code = lq.wait(tmp_path, name, timeout_s, poll=5, say=said.append, clock=clock.now, sleep=clock.sleep)
    return code, said, clock


def test_run_leaves_a_result_with_the_exit_code_and_log(tmp_path):
    assert lq.run(tmp_path, "chk", [sys.executable, "-c", "raise SystemExit(7)"], log="out.log") == 7
    assert json.loads(lq.result_path(tmp_path, "chk").read_text())["exit"] == 7
    assert lq.run(tmp_path, "chk", [sys.executable, "-c", "pass"]) == 0  # the earlier result is replaced
    assert json.loads(lq.result_path(tmp_path, "chk").read_text())["exit"] == 0


def test_wait_times_out_with_a_distinct_code_while_the_ticket_runs(tmp_path):
    code, said, clock = waiting(tmp_path, "bench-check", 60)
    assert code == lq.WAIT_TIMEOUT == 75 and clock.t >= 60
    assert "still running, run wait again" in said[-1]


def test_wait_returns_the_exit_code_and_log_once_the_ticket_ended(tmp_path):
    lq.result_path(tmp_path, "chk").write_text(json.dumps({"exit": 3, "log": "x.log", "ended": "2026-10-30T10:00:00"}))
    code, said, _ = waiting(tmp_path, "chk", 60, ticket=False)
    assert code == 3 and "exit code 3" in said[-1] and "x.log" in said[-1]


def test_wait_follows_a_ticket_that_ends_while_it_waits(tmp_path):
    ticket = tmp_path / f"1-{os.getpid()}-chk.ticket"
    ticket.write_text("cmd")
    clock, said = Clock(), []

    def sleep(s):
        clock.sleep(s)
        if clock.t >= 10:  # the command ends: result first, then the ticket goes
            lq.result_path(tmp_path, "chk").write_text(json.dumps({"exit": 0, "log": None, "ended": "t"}))
            ticket.unlink(missing_ok=True)

    assert lq.wait(tmp_path, "chk", 60, poll=5, say=said.append, clock=clock.now, sleep=sleep) == 0
    assert clock.t == 10


def test_wait_gives_a_starting_run_time_to_queue_before_it_trusts_an_old_result(tmp_path):
    lq.result_path(tmp_path, "chk").write_text(json.dumps({"exit": 0, "log": None, "ended": "earlier"}))  # the previous run under this name
    ticket = tmp_path / f"1-{os.getpid()}-chk.ticket"
    clock, said = Clock(), []

    def sleep(s):
        clock.sleep(s)
        if clock.t == 5:  # uv has started: the new run drops the old result and queues
            lq.result_path(tmp_path, "chk").unlink()
            ticket.write_text("cmd")
        if clock.t == 15:
            lq.result_path(tmp_path, "chk").write_text(json.dumps({"exit": 4, "log": None, "ended": "later"}))
            ticket.unlink()

    assert lq.wait(tmp_path, "chk", 60, poll=5, say=said.append, clock=clock.now, sleep=sleep) == 4


def test_wait_names_an_unknown_ticket_and_a_run_that_died(tmp_path):
    code, said, _ = waiting(tmp_path, "nobody", 60, ticket=False)
    assert code == lq.WAIT_UNKNOWN and "no such ticket" in said[-1]
    ticket = tmp_path / f"1-{os.getpid()}-dead.ticket"
    ticket.write_text("cmd")
    said = []
    assert lq.wait(tmp_path, "dead", 60, poll=5, say=said.append, clock=Clock().now,
                   sleep=lambda s: ticket.unlink(missing_ok=True)) == lq.WAIT_DIED
    assert "died" in said[-1]  # the ticket went with no result


def test_wait_reports_a_run_whose_ticket_was_removed_once_it_leaves_its_result(tmp_path):
    ticket = tmp_path / f"1-{os.getpid()}-chk.ticket"
    ticket.write_text("cmd")
    sleeps, said = [], []
    gone = "[queue] the ticket 1-0-chk.ticket left the queue while chk waited; chk did not start: queue it again"

    def sleep(s):
        sleeps.append(s)
        if len(sleeps) == 1:
            ticket.unlink()
        elif len(sleeps) == 2:
            lq.result_path(tmp_path, "chk").write_text(json.dumps(
                {"exit": 1, "log": None, "ended": "2026-11-08T21:00:00", "not_started": gone}))

    assert lq.wait(tmp_path, "chk", 60, poll=5, say=said.append, clock=Clock().now, sleep=sleep) == 1
    assert said[-1] == f"[queue] chk did not start, exit code 1: {gone}"


def test_pause_keeps_the_hold_and_status_says_who_owns_the_emulator(tmp_path):
    task = tmp_path / "t"
    done = task / "done"
    (tmp_path / f"1-{os.getpid()}-t.ticket").write_text(f"hold --done {done} --timeout 7200")
    assert "PAUSED" not in lq.status(tmp_path, now=1000)[0]
    lq.pause(task, 30, now=1000)
    assert lq.pause_until(task) == 1000 + 1800
    assert "PAUSED until" in lq.status(tmp_path, now=1500)[0]
    assert "PAUSED" not in lq.status(tmp_path, now=1000 + 1801)[0]  # lapsed
    lq.pause(task, None)
    assert lq.pause_until(task) is None


def test_status_warns_before_a_hold_expires(tmp_path):
    task = tmp_path / "t"
    task.mkdir()
    (tmp_path / f"1-{os.getpid()}-t.ticket").write_text(f"hold --done {task / 'done'} --timeout 7200")
    (task / "hold.deadline").write_text("10000")
    assert "expires" not in lq.status(tmp_path, now=10000 - 3600)[0]
    assert "hold expires in 10 min" in lq.status(tmp_path, now=10000 - 600)[0]


@pytest.mark.parametrize("module", ["live.queue", "live.backup", "live.dialogs"])
def test_importing_a_live_tool_leaves_the_importers_path_as_it_was(module):
    # #667: they overwrote sys.path[0], so a program that imported them lost its first path entry.
    code = f"import sys; before = list(sys.path); import {module}; assert sys.path == before, (before, sys.path)"
    env = {**os.environ, "PYTHONPATH": str(QUEUE_PY.parents[1])}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


@pytest.mark.parametrize("script", ["queue.py", "backup.py", "dialogs.py"])
def test_a_live_tool_still_runs_as_a_script(script):
    # A script's own folder, tools/live/, stays on its path: a module there that imported the stdlib `queue` would get
    # this queue.py instead and fail.
    subprocess.run([sys.executable, str(QUEUE_PY.parent / script), "--help"], check=True, capture_output=True)
