"""tools/live/memwatch.py samples a live run's process tree until its root ends."""

import csv
import importlib.util
import subprocess
import sys

import pytest

from live import memwatch

# The root sleeps, starts a child whose command line ends in agent/main.py, and ends when the child does.
ROOT = ("import subprocess, sys, time; time.sleep(0.4); "
        "subprocess.run([sys.executable, '-c', 'import time; time.sleep(1.2)', 'install/agent/main.py'])")


@pytest.mark.skipif(sys.platform != "win32", reason="private bytes are Windows'")
@pytest.mark.skipif(importlib.util.find_spec("psutil") is None, reason="psutil is the probe group's")
def test_a_child_started_after_the_root_is_counted_under_its_role_until_the_root_ends(tmp_path, capsys):
    out = tmp_path / "mem.csv"
    root = subprocess.Popen([sys.executable, "-c", ROOT])
    try:
        assert memwatch.main(["--pid", str(root.pid), "--csv", str(out), "--every", "0.1"]) == 0
    finally:
        root.kill()
        root.wait()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {r["role"] for r in rows if int(r["pid"]) == root.pid} == {"other"}
    agents = {int(r["pid"]) for r in rows if r["role"] == "agent"}  # a venv's python.exe starts the real one under it
    assert agents and root.pid not in agents
    assert all(float(r["working_set_mb"]) > 0 and float(r["private_mb"]) > 0 for r in rows)
    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith("tree: peak working set ")
    assert any(line.startswith("agent: peak working set ") for line in printed)


@pytest.mark.parametrize("name, cmdline, expected", [
    ("python.exe", ["python", "-u", "install\\agent\\main.py", "MaaAgent_1"], "agent"),
    ("python.exe", ["python", "-u", "tools/live/bot.py", "tasker", "--install", "install"], "tasker"),
    ("python.exe", ["python", "-u", "tools/live/bot.py", "run", "--install", "install"], "other"),
    ("mxu.exe", ["mxu.exe"], "client"),
    ("MFAAvalonia.exe", ["MFAAvalonia.exe"], "client"),
    ("uv.exe", ["uv", "run", "python", "tools/live/bot.py", "run"], "other"),
    ("python.exe", [], "other"),
])
def test_a_process_role_comes_from_its_command_line(name, cmdline, expected):
    assert memwatch.role(name, cmdline) == expected


def test_the_summary_sums_each_sample_over_the_tree_and_over_each_role_in_sampling_order():
    rows = [
        {"time": "23:59:55.000", "pid": 1, "role": "tasker", "working_set_mb": 100, "private_mb": 300},
        {"time": "23:59:55.000", "pid": 2, "role": "agent", "working_set_mb": 50, "private_mb": 80},
        {"time": "00:00:00.000", "pid": 1, "role": "tasker", "working_set_mb": 400, "private_mb": 900},
        {"time": "00:00:00.000", "pid": 2, "role": "agent", "working_set_mb": 60, "private_mb": 70},
        {"time": "00:00:05.000", "pid": 1, "role": "tasker", "working_set_mb": 200, "private_mb": 500},
    ]
    lines = memwatch.summary(rows)
    assert lines[0] == ("tree: peak working set 460.0 MB at 00:00:00.000, peak private 970.0 MB at 00:00:00.000; "
                        "last 00:00:05.000: working set 200.0 MB, private 500.0 MB")
    assert lines[1] == ("agent: peak working set 60.0 MB at 00:00:00.000, peak private 80.0 MB at 23:59:55.000; "
                        "last 00:00:00.000: working set 60.0 MB, private 70.0 MB")
    assert lines[2].startswith("tasker: peak working set 400.0 MB at 00:00:00.000")
