import importlib.util
import threading
import time
from pathlib import Path

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
