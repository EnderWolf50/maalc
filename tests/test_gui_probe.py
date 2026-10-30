import json
import subprocess
import sys

import pytest

import gui_probe as gp

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="finds a Win32 window")

# sys._base_executable: a venv's python.exe is a launcher whose child owns the window
WINDOW = """
import sys, tkinter
root = tkinter.Tk()
root.title(sys.argv[1])
root.after(20000, root.destroy)
root.mainloop()
"""


def fake_assets(tmp_path):
    assets = tmp_path / "repo-assets"
    (assets / "resource").mkdir(parents=True)
    (assets / "resource" / "keep.txt").write_text("x")
    return assets


def test_demo_settings_is_the_valid_case():
    assert json.loads(gp.demo_settings())["language"] == "zh_tw"


def test_prepare_root_lays_out_exe_settings_and_assets(tmp_path):
    exe = tmp_path / "built.exe"
    exe.write_bytes(b"MZ")
    root = tmp_path / "sandbox"
    copied = gp.prepare_root(exe, root, '{"a": 1}', fake_assets(tmp_path))
    assert copied == root / gp.EXE_NAME and copied.read_bytes() == b"MZ"
    assert (root / "config" / "settings.json").read_text() == '{"a": 1}'
    assert (root / "assets" / "resource" / "keep.txt").read_text() == "x"


def test_prepare_root_twice_replaces_the_root_and_leaves_the_assets_alone(tmp_path):
    exe = tmp_path / "built.exe"
    exe.write_bytes(b"MZ")
    assets = fake_assets(tmp_path)
    root = tmp_path / "sandbox"
    gp.prepare_root(exe, root, "old", assets)
    (root / "stale.txt").write_text("stale")
    gp.prepare_root(exe, root, "new", assets)
    assert not (root / "stale.txt").exists()
    assert (root / "config" / "settings.json").read_text() == "new"
    assert (assets / "resource" / "keep.txt").read_text() == "x"


def test_prepare_root_refuses_an_existing_folder_it_did_not_make(tmp_path):
    exe = tmp_path / "built.exe"
    exe.write_bytes(b"MZ")
    foreign = tmp_path / "home"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("keep")
    with pytest.raises(gp.ForeignRoot):
        gp.prepare_root(exe, foreign, "x", fake_assets(tmp_path))
    assert (foreign / "precious.txt").read_text() == "keep"


def test_main_exits_1_and_deletes_nothing_for_a_root_without_the_marker(tmp_path, capsys):
    exe = tmp_path / "built.exe"
    exe.write_bytes(b"MZ")
    foreign = tmp_path / "home"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("keep")
    assert gp.main(["--exe", str(exe), "--root", str(foreign)]) == 1
    assert (foreign / "precious.txt").exists()
    assert gp.MARKER in capsys.readouterr().err


@windows_only
def test_wait_for_window_returns_the_window_of_the_process_with_the_title():
    proc = subprocess.Popen([sys._base_executable, "-c", WINDOW, "gui-probe-test"])
    try:
        hwnd, title, rect = gp.wait_for_window(proc, "gui-probe-test", 15)
        assert title == "gui-probe-test" and hwnd
        assert rect[2] > rect[0] and rect[3] > rect[1]
        assert gp.find_window(proc.pid, "another title") is None
    finally:
        gp.stop(proc)


@windows_only
def test_wait_for_window_gives_up_when_no_window_shows():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        assert gp.wait_for_window(proc, "never", 1, poll=0.1) is None
    finally:
        gp.stop(proc)


@windows_only
def test_main_exits_1_and_stops_the_process_when_no_window_shows(tmp_path, monkeypatch, capsys):
    exe = tmp_path / "built.exe"
    exe.write_bytes(b"MZ")
    started = []
    real_popen = subprocess.Popen

    def popen(cmd, **kw):
        proc = real_popen([sys.executable, "-c", "import time; time.sleep(20)"])
        started.append(proc)
        return proc

    monkeypatch.setattr(gp.subprocess, "Popen", popen)
    monkeypatch.setattr(gp, "prepare_root", lambda exe, root, text: root / gp.EXE_NAME)
    code = gp.main(["--exe", str(exe), "--root", str(tmp_path / "r"), "--timeout", "1"])
    assert code == 1
    assert "no window titled 'maalc'" in capsys.readouterr().err
    started[0].wait(timeout=10)  # killed by the probe
