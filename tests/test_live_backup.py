import importlib.util
import threading
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
