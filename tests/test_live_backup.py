import importlib.util
import threading
import time
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("backup", Path(__file__).resolve().parent.parent / "tools/live/backup.py")
bk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bk)


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


def test_hold_waits_for_the_done_file_then_verifies(tmp_path, capsys):
    root, dest, done = tmp_path / "install", tmp_path / "bak", tmp_path / "done"
    (root / "agent").mkdir(parents=True)
    (root / "agent/main.py").write_text("a")
    threading.Timer(0.3, lambda: (done.write_text(""), (root / "agent/main.py").write_text("b"))).start()
    assert bk.hold(root, dest, done, timeout=10, poll=0.05) == 1  # the file changed while it waited
    assert "done file found" in capsys.readouterr().out
    assert bk.hold(root, dest, done, timeout=10, poll=0.05) == 0  # backs up afresh; nothing changes


def test_hold_gives_up_at_the_timeout(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    assert bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.1, poll=0.02) == 0
    assert "timed out" in capsys.readouterr().out


def test_hold_keeps_the_emulator_while_the_guarded_bot_runs_and_a_timeout_after_it(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    ended = []
    checks = iter([True] * 40)  # the bot runs for 40 polls (0.4 s or more), past the timeout, then ends

    def running(_log):
        if (r := next(checks, False)) is False and not ended:
            ended.append(time.monotonic())
        return r

    assert bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.3, poll=0.01,
                   guard=tmp_path / "bot.log", running=running) == 0
    assert time.monotonic() - ended[0] >= 0.25  # the timeout ran again from the bot's end
    assert "timed out" in capsys.readouterr().out


def test_hold_logs_when_the_bot_ended_and_stops_the_recording_after_the_grace(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    checks, stopped = iter([True] * 5), []
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.4, poll=0.01, guard=tmp_path / "bot.log",
            running=lambda _log: next(checks, False), stop_profile="p", grace=0.1, stop=stopped.append)
    assert stopped == ["p"]  # once
    assert capsys.readouterr().out.count("[hold] bot ended 20") == 1


def test_hold_notes_the_end_of_a_restarted_bot_and_keeps_its_recording(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    runs, stopped = iter([True, False, True, True, True]), []  # ends, restarts within the grace, runs on
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.2, poll=0.05, guard=tmp_path / "bot.log",
            running=lambda _log: next(runs, False), stop_profile="p", grace=5, stop=stopped.append)
    assert stopped == [] and capsys.readouterr().out.count("[hold] bot ended 20") == 2


def test_hold_notes_a_bot_that_ended_within_one_poll_but_not_a_pid_file_of_an_earlier_run(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    bot, stopped = tmp_path / "bot.log", []
    pid_file = bot.with_name("bot.log.pid")
    pid_file.write_text('{"pid": 1, "start": null, "cmd": "old"}')  # an earlier run under the same log
    threading.Timer(0.2, lambda: pid_file.write_text('{"pid": 2, "start": null, "cmd": "new"}')).start()  # the bot, gone at once
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.5, poll=0.02, guard=bot,
            running=lambda _log: False, stop_profile="p", grace=0.05, stop=stopped.append)
    out = capsys.readouterr().out
    assert out.count("[hold] bot ended 20") == 1 and stopped == ["p"]


def test_hold_ignores_a_pid_file_left_by_an_earlier_run(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    bot, stopped = tmp_path / "bot.log", []
    bot.with_name("bot.log.pid").write_text('{"pid": 1, "start": null, "cmd": "old"}')
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.2, poll=0.02, guard=bot,
            running=lambda _log: False, stop_profile="p", grace=0.05, stop=stopped.append)
    assert "bot ended" not in capsys.readouterr().out and stopped == []


def test_hold_does_not_time_out_while_paused_and_shows_its_deadline(tmp_path, capsys):
    (tmp_path / "install").mkdir()
    done = tmp_path / "t" / "done"
    done.parent.mkdir()
    (done.parent / "pause").write_text(str(time.time() + 0.3))  # paused for 0.3 s
    began = time.monotonic()
    assert bk.hold(tmp_path / "install", tmp_path / "bak", done, timeout=0.2, poll=0.01) == 0
    assert time.monotonic() - began >= 0.45  # the 0.2 s timeout ran only after the pause lapsed
    assert "timed out" in capsys.readouterr().out
    assert not (done.parent / "hold.deadline").exists()  # removed when the hold ends


def test_hold_writes_the_deadline_a_second_agent_reads_in_status(tmp_path):
    (tmp_path / "install").mkdir()
    done = tmp_path / "done"
    seen = []
    threading.Timer(0.1, lambda: (seen.append((tmp_path / "hold.deadline").read_text()), done.write_text(""))).start()
    bk.hold(tmp_path / "install", tmp_path / "bak", done, timeout=500, poll=0.02, wall=lambda: 1000.0)
    assert 1000 + 400 < float(seen[0]) <= 1500


def test_hold_requires_an_explicit_timeout(tmp_path):
    with pytest.raises(SystemExit):
        bk.main(["hold", "--done", str(tmp_path / "d"), "--root", str(tmp_path)])


def test_hold_follows_a_second_bot_run_under_its_own_log(tmp_path, capsys):
    # live-1 T-live: the second bot of one hold ran under bot-b.log; a guard on bot.log alone stopped its recording 60 s
    # after the first ended. A glob guard follows every bot log of the hold.
    (tmp_path / "install").mkdir()
    up, stopped = {"bot.log": False, "bot-b.log": False}, []

    def start(name):
        (tmp_path / name).write_text("")
        (tmp_path / f"{name}.pid").write_text('{"pid": 1, "start": null, "cmd": "bot"}')
        up[name] = True

    start("bot.log")
    threading.Timer(0.1, lambda: up.update({"bot.log": False})).start()  # the first run ends
    threading.Timer(0.15, lambda: start("bot-b.log")).start()  # the second starts within the grace
    threading.Timer(0.5, lambda: up.update({"bot-b.log": False})).start()
    began = time.monotonic()
    bk.hold(tmp_path / "install", tmp_path / "bak", tmp_path / "never", timeout=0.3, poll=0.01, guard=tmp_path / "bot*.log",
            running=lambda log: up[log.name], stop_profile="p", grace=0.2, stop=lambda p: stopped.append(time.monotonic() - began))
    assert len(stopped) == 1 and stopped[0] >= 0.7  # 0.2 s after the second run's end, not the first's
    assert capsys.readouterr().out.count("[hold] bot ended 20") == 2
