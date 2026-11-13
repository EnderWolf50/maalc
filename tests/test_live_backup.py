import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from live import backup as bk
from live import hold as hl
from live import queue as lq


class Clock:
    """A virtual clock for `hold`: sleep() moves time on and runs the events due, so no test waits on the wall clock (#649)."""

    def __init__(self):
        self.now, self.events = 1000.0, []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        for event in sorted((e for e in self.events if e[0] <= self.now), key=lambda e: e[0]):
            self.events.remove(event)
            event[1]()

    def at(self, seconds, fn):
        """Run `fn` in the first sleep() that reaches `seconds` from now."""
        self.events.append((self.now + seconds, fn))


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(bk, "time", SimpleNamespace(monotonic=c.monotonic, sleep=c.sleep))
    return c


def test_verify_reports_changed_missing_and_new_files_but_not_runtime_output(tmp_path):
    root, dest = tmp_path / "install", tmp_path / "bak"
    for name, text in {"agent/main.py": "a", "config/settings.json": "{}", "logs/run.log": "x"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    assert bk.backup(root, dest) == 2 and (dest / "settings.json").read_text() == "{}"
    assert bk.verify(root, dest) == []
    (root / "agent/main.py").write_text("b")
    (root / "config/settings.json").unlink()
    (root / "new.txt").write_text("n")
    (root / "logs/run.log").write_text("y")
    assert bk.verify(root, dest) == ["changed  agent/main.py", "missing  config/settings.json", "new      new.txt"]


def test_hold_waits_for_the_done_file_then_verifies(tmp_path, capsys, clock):
    root, dest, done = tmp_path / "install", tmp_path / "bak", tmp_path / "done"
    (root / "agent").mkdir(parents=True)
    (root / "agent/main.py").write_text("a")
    clock.at(0.3, lambda: (done.write_text(""), (root / "agent/main.py").write_text("b")))
    assert bk.hold(root, dest, done, timeout=10, poll=0.05) == 1  # the file changed while it waited
    assert "done file found" in capsys.readouterr().out
    assert bk.hold(root, dest, done, timeout=10, poll=0.05) == 0  # backs up afresh; nothing changes


def test_hold_gives_up_at_the_timeout(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    assert bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.1, poll=0.02) == 0
    assert "timed out" in capsys.readouterr().out


def test_hold_keeps_the_emulator_while_the_guarded_bot_runs_and_a_timeout_after_it(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    ended = []
    checks = iter([True] * 40)  # the bot runs for 40 polls (0.4 s), past the timeout, then ends

    def running(_log):
        if (r := next(checks, False)) is False and not ended:
            ended.append(clock.now)
        return r

    assert bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.3, poll=0.01,
                   guard=tmp_path / "bot.log", running=running) == 0
    assert clock.now - ended[0] >= 0.25  # the timeout ran again from the bot's end
    assert "timed out" in capsys.readouterr().out


def test_hold_logs_when_the_bot_ended_and_stops_the_recording_after_the_grace(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    checks, stopped = iter([True] * 5), []
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.4, poll=0.01, guard=tmp_path / "bot.log",
            running=lambda _log: next(checks, False), stop_profile="p", grace=0.1, stop=stopped.append)
    assert stopped == ["p"]  # once
    assert capsys.readouterr().out.count("[hold] bot ended 20") == 1


def test_hold_notes_the_end_of_a_restarted_bot_and_keeps_its_recording(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    runs, stopped = iter([True, False, True, True, True]), []  # ends, restarts within the grace, runs on
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.2, poll=0.05, guard=tmp_path / "bot.log",
            running=lambda _log: next(runs, False), stop_profile="p", grace=5, stop=stopped.append)
    assert stopped == [] and capsys.readouterr().out.count("[hold] bot ended 20") == 2


def test_hold_notes_a_bot_that_ended_within_one_poll_but_not_a_pid_file_of_an_earlier_run(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    bot, stopped = tmp_path / "bot.log", []
    pid_file = bot.with_name("bot.log.pid")
    pid_file.write_text('{"pid": 1, "start": null, "cmd": "old"}')  # an earlier run under the same log
    clock.at(0.2, lambda: pid_file.write_text('{"pid": 2, "start": null, "cmd": "new"}'))  # the bot, gone at once
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.5, poll=0.02, guard=bot,
            running=lambda _log: False, stop_profile="p", grace=0.05, stop=stopped.append)
    out = capsys.readouterr().out
    assert out.count("[hold] bot ended 20") == 1 and stopped == ["p"]


def test_hold_ignores_a_pid_file_left_by_an_earlier_run(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    bot, stopped = tmp_path / "bot.log", []
    bot.with_name("bot.log.pid").write_text('{"pid": 1, "start": null, "cmd": "old"}')
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.2, poll=0.02, guard=bot,
            running=lambda _log: False, stop_profile="p", grace=0.05, stop=stopped.append)
    assert "bot ended" not in capsys.readouterr().out and stopped == []


def test_hold_does_not_time_out_while_paused_and_shows_its_deadline(tmp_path, capsys, clock):
    (tmp_path / "install").mkdir()
    done = tmp_path / "t" / "done"
    done.parent.mkdir()
    (done.parent / "pause").write_text(str(clock.now + 0.3))  # paused for 0.3 s
    began, state = clock.now, tmp_path / "1-2-t.hold.json"
    # wall and monotonic share the virtual timeline here, so the pause file's wall time lapses as the clock moves
    assert bk.hold(tmp_path / "install", tmp_path / "bak", done, timeout=0.2, poll=0.01, wall=clock.monotonic, state_file=state) == 0
    assert clock.now - began >= 0.45  # the 0.2 s timeout ran only after the pause lapsed
    assert "timed out" in capsys.readouterr().out
    assert not state.exists()  # removed when the hold ends


def test_hold_writes_the_deadline_a_second_agent_reads_in_status(tmp_path, monkeypatch):
    """At this monotonic time, monotonic() + 500 rounds up: the file read 1500.0000000000018 for wall 1000 (#578)."""
    (tmp_path / "install").mkdir()
    done, seen, state = tmp_path / "done", [], tmp_path / "1-2-t.hold.json"

    def sleep(_):
        seen.append(json.loads(state.read_text(encoding="utf-8"))["deadline"])
        done.write_text("")

    monkeypatch.setattr(bk, "time", SimpleNamespace(monotonic=lambda: 16240.694345345151, sleep=sleep))
    bk.hold(tmp_path / "install", tmp_path / "bak", done, timeout=500, wall=lambda: 1000.0, state_file=state)
    assert seen == [1500]


def test_hold_requires_an_explicit_timeout(tmp_path):
    with pytest.raises(SystemExit):
        bk.main(["hold", "--done", str(tmp_path / "d"), "--root", str(tmp_path)])


def test_hold_follows_a_second_bot_run_under_its_own_log(tmp_path, capsys, clock):
    # live-1 T-live: the second bot of one hold ran under bot-b.log; a guard on bot.log alone stopped its recording 60 s
    # after the first ended. A glob guard follows every bot log of the hold.
    (tmp_path / "install").mkdir()
    up, stopped = {"bot.log": False, "bot-b.log": False}, []

    def start(name):
        (tmp_path / name).write_text("")
        (tmp_path / f"{name}.pid").write_text('{"pid": 1, "start": null, "cmd": "bot"}')
        up[name] = True

    start("bot.log")
    clock.at(0.1, lambda: up.update({"bot.log": False}))  # the first run ends
    clock.at(0.15, lambda: start("bot-b.log"))  # the second starts within the grace
    clock.at(0.5, lambda: up.update({"bot-b.log": False}))
    began = clock.now
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.3, poll=0.01, guard=tmp_path / "bot*.log",
            running=lambda log: up[log.name], stop_profile="p", grace=0.2, stop=lambda p: stopped.append(clock.now - began))
    assert len(stopped) == 1 and stopped[0] >= 0.7  # 0.2 s after the second run's end, not the first's
    assert capsys.readouterr().out.count("[hold] bot ended 20") == 2


def test_hold_reads_a_relative_done_and_guard_from_the_main_checkout(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(bk, "main_checkout", lambda: tmp_path)
    monkeypatch.setattr(bk, "local_dir", lambda *parts: tmp_path / "bak")
    monkeypatch.setattr(bk, "hold", lambda root, dest, done, timeout, **kw: seen.update(done=done, guard=kw["guard"]) or 0)
    bk.main(["hold", "--done", ".local/scratch/t/done", "--guard", ".local/scratch/t/bot*.log", "--timeout", "5"])
    assert seen == {"done": tmp_path / ".local/scratch/t/done", "guard": tmp_path / ".local/scratch/t/bot*.log"}
    bk.main(["hold", "--done", str(tmp_path / "abs-done"), "--timeout", "5"])
    assert seen == {"done": tmp_path / "abs-done", "guard": None}


def test_a_hold_under_a_queue_ticket_publishes_beside_it_and_one_outside_a_queue_does_not(tmp_path, monkeypatch):
    # #693: `queue.py run` hands its command the ticket; `status` reads the hold's state beside it (hold.py)
    seen, ticket = {}, tmp_path / "1-2-t.ticket"
    monkeypatch.setattr(bk, "main_checkout", lambda: tmp_path)
    monkeypatch.setattr(bk, "local_dir", lambda *parts: tmp_path / "bak")
    monkeypatch.setattr(bk, "hold", lambda root, dest, done, timeout, **kw: seen.update(state=kw["state_file"]) or 0)
    monkeypatch.setenv(lq.TICKET_ENV, str(ticket))
    bk.main(["hold", "--done", "d", "--timeout", "5"])
    assert seen["state"] == hl.state_path(ticket) == tmp_path / "1-2-t.hold.json"
    monkeypatch.delenv(lq.TICKET_ENV)
    bk.main(["hold", "--done", "d", "--timeout", "5"])
    assert seen["state"] is None


def test_status_shows_what_a_queued_hold_publishes_and_nothing_once_it_ended(tmp_path, clock):
    """#693: the stranded bot and the deadline `queue.py status` shows come from the hold's own state file, from its
    first poll to its end (they were read off the hold's command line and a hold.deadline file)."""
    (tmp_path / "install").mkdir()
    qdir, task = tmp_path / "queue", tmp_path / "t"
    qdir.mkdir()
    task.mkdir()
    ticket = qdir / f"1-{os.getpid()}-t.ticket"
    ticket.write_text("uv run python tools/live/backup.py hold")
    bot, gone = task / "bot.log", subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    bot.write_text("x")
    lq.pid_file(bot).write_text(json.dumps({"pid": gone.pid, "start": None, "cmd": "bot"}))
    ended, lines = bot.stat().st_mtime, []
    look = lambda: lines.extend([lq.status(qdir, now=ended + 1500)[0], lq.status(qdir, now=8200 - 600)[0]])  # noqa: E731
    clock.at(0.05, look)
    clock.at(0.1, lambda: (task / "done").write_text(""))
    assert bk.hold(tmp_path / "install", tmp_path / "bak", task / "done", timeout=7200, poll=0.01, guard=bot,
                   running=lambda _log: False, wall=lambda: 1000.0, state_file=hl.state_path(ticket)) == 0
    stranded, expiring = lines
    assert "bot ended 25 min ago, waiting for the agent" in stranded  # the guard's bot ended 25 min ago, no done file
    assert "hold expires in 10 min" in expiring  # the deadline: wall 1000 + the 7200 s timeout
    assert not hl.state_path(ticket).exists()
    assert lq.status(qdir, now=ended + 1500)[0].endswith(": uv run python tools/live/backup.py hold")  # no note left
