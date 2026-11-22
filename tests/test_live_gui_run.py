"""tools/live/gui_run.py: window matching, the run-log watch and the commands' refusals on fakes; on Windows, the title
change and the uniqueness check on real top-level windows, and the job that ends the app with the holder.

The page side (Start, Stop, the state on the real settings window) and a recording of the real window need the built app
and screen-record: the maalc-live-test skill runs them.
"""
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from live import gui_run as gr

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Win32 windows and jobs")


def win(hwnd, title, w=800, h=600, iconic=False, pid=1):
    return {"hwnd": hwnd, "pid": pid, "title": title, "w": w, "h": h, "iconic": iconic}


# --- matching -----------------------------------------------------------------------------------------------------

def test_matching_is_screen_records_case_insensitive_substring():
    ws = [win(1, "maalc"), win(2, "notes on maalc - Editor", 1900, 1000), win(3, "Android Device"), win(4, "MAALC-live-9333")]
    assert [w["hwnd"] for w in gr.matching(ws, "maalc")] == [1, 2, 4]
    assert [w["hwnd"] for w in gr.matching(ws, "maalc-live-9333")] == [4]


def test_sole_refuses_several_matches_and_names_them():
    ws = [win(1, "maalc"), win(2, "maalc - Editor", 1900, 1000)]
    with pytest.raises(gr.Ambiguous, match="2 visible windows.*hwnd 1, 2"):
        gr.sole(ws, "maalc")
    with pytest.raises(gr.Refused, match="no visible window"):
        gr.sole(ws, "Android Device")
    assert gr.sole(ws, "Editor")["hwnd"] == 2


def test_listing_shows_a_title_only_when_it_is_the_substring_exactly():
    rows = gr.listing([win(1, "maalc"), win(2, "notes about maalc.txt - Editor")], "maalc")
    assert rows[0]["title"] == "maalc"
    assert "title" not in rows[1]  # another title can name the user's own work
    assert rows[1]["size"] == [800, 600]


# --- the run log --------------------------------------------------------------------------------------------------

def log(folder: Path, name: str, text: str = "", mtime: float | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(text, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


def test_a_log_the_runner_prunes_meanwhile_is_left_out(tmp_path, monkeypatch):
    kept = log(tmp_path, "run-20261118-145743.log")
    gone = log(tmp_path, "run-20261118-145311.log")
    real_stat = Path.stat
    monkeypatch.setattr(Path, "stat", lambda p, **kw: (_ for _ in ()).throw(FileNotFoundError(p)) if p.name == gone.name
                        else real_stat(p, **kw))
    assert gr.run_logs(tmp_path) == [kept]


def test_the_watch_takes_the_next_new_log_or_the_newest_when_a_run_is_under_way(tmp_path):
    old = log(tmp_path, "run-20261118-145311.log", mtime=1000)
    assert gr.watched_log(tmp_path, {old.name}, under_way=False) is None
    assert gr.watched_log(tmp_path, {old.name}, under_way=True) == old
    new = log(tmp_path, "run-20261118-145743.log", mtime=2000)
    assert gr.watched_log(tmp_path, {old.name}, under_way=False) == new


def test_seen_finds_the_line_or_the_runs_end_first():
    assert gr.seen("14:57:45.600 [maalc] task ClaimMail started\n", "task ClaimMail started") == "line"
    assert gr.seen("14:57:45.600 [run] end succeeded\n14:57:46 [maalc] task ClaimMail started\n", "ClaimMail started") == "ended"
    assert gr.seen("14:57:45.600 [maalc] task ChargeEnkephalin started\n", "ClaimMail") is None


# --- open's root --------------------------------------------------------------------------------------------------

def install(root: Path, settings=True) -> Path:
    (root / "config").mkdir(parents=True)
    (root / gr.APP).write_bytes(b"")
    if settings:
        (root / "config" / "settings.json").write_text("{}", encoding="utf-8")
    return root


def test_open_refuses_a_folder_without_the_exe_or_its_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "main_checkout", lambda: tmp_path / "main")
    with pytest.raises(gr.Refused, match="no maalc-gui.exe"):
        gr.check_root(tmp_path)
    with pytest.raises(gr.Refused, match="bot.py prep"):
        gr.check_root(install(tmp_path / "a", settings=False))
    assert gr.check_root(install(tmp_path / "b")) == tmp_path / "b" / gr.APP


def test_open_refuses_the_main_checkouts_install(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "main_checkout", lambda: tmp_path)
    with pytest.raises(gr.Refused, match="user's own"):
        gr.check_root(install(tmp_path / "install"))


# --- record -------------------------------------------------------------------------------------------------------

def rec_args(tmp_path, **kw):
    return SimpleNamespace(**{"hwnd": None, "window": None, "out": str(tmp_path), "wait": 0, "profile": "gui",
                              "crop_top": None, "height": 720, "keep_gb": None, **kw})


@pytest.fixture
def screenrec(tmp_path, monkeypatch):
    """A fake screen-record: `start` writes the state with the hwnd `took` names (default: the largest match)."""
    calls, took = [], {}

    def fake(*args):
        calls.append(list(args))
        if args[0] == "start":
            title = args[args.index("--window") + 1]
            hwnd = took.get("hwnd") or max(gr.matching(gr.top_windows(), title), key=lambda w: w["w"] * w["h"])["hwnd"]
            (tmp_path / f"rec_{args[args.index('--profile') + 1]}.state.json").write_text(
                f'{{"hwnd": {hwnd}, "started": "2026-11-20T10:00:00.000", "mkv": "x.mkv"}}', encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(gr, "screenrec", fake)
    return SimpleNamespace(calls=calls, took=took)


def test_record_refuses_a_window_title_another_window_holds_too(tmp_path, monkeypatch, screenrec):
    monkeypatch.setattr(gr, "top_windows", lambda: [win(5, "maalc", 1200, 700), win(9, "maalc - Editor", 1900, 1000)])
    monkeypatch.setattr(gr, "window_title", lambda hwnd: "maalc")
    with pytest.raises(gr.Refused, match="title of its own"):
        gr.record_cmd(rec_args(tmp_path, hwnd=5))
    with pytest.raises(gr.Ambiguous):
        gr.record_cmd(rec_args(tmp_path, window="maalc", wait=30))  # several matches: no wait makes them fewer
    assert screenrec.calls == []


def test_record_records_the_retitled_window_and_hands_screen_record_its_title(tmp_path, monkeypatch, screenrec, capsys):
    monkeypatch.setattr(gr, "top_windows", lambda: [win(5, "maalc-live-9333", 1200, 700), win(9, "maalc - Editor", 1900, 1000)])
    monkeypatch.setattr(gr, "window_title", lambda hwnd: "maalc-live-9333")
    assert gr.record_cmd(rec_args(tmp_path, hwnd=5, crop_top=0)) == 0
    assert screenrec.calls == [["start", "--window", "maalc-live-9333", "--out", str(tmp_path), "--profile", "gui",
                                "--height", "720", "--crop-top", "0"]]
    assert '"recording": 5' in capsys.readouterr().out


def test_record_stops_a_recording_of_another_window(tmp_path, monkeypatch, screenrec):
    monkeypatch.setattr(gr, "top_windows", lambda: [win(5, "maalc-live-9333")])
    monkeypatch.setattr(gr, "window_title", lambda hwnd: "maalc-live-9333")
    screenrec.took["hwnd"] = 77  # a window that took the title between the check and the start
    with pytest.raises(gr.Refused, match="took window 77"):
        gr.record_cmd(rec_args(tmp_path, hwnd=5))
    assert screenrec.calls[-1] == ["stop", "--profile", "gui"]


def test_record_waits_for_the_window_to_appear(tmp_path, monkeypatch, screenrec):
    polls = iter([[], [], [win(3, "Android Device", 1280, 780)]])
    reads = []
    monkeypatch.setattr(gr, "top_windows", lambda: (reads.append(1), next(polls, [win(3, "Android Device", 1280, 780)]))[1])
    monkeypatch.setattr(gr.time, "sleep", lambda s: None)
    assert gr.record_cmd(rec_args(tmp_path, window="Android Device", wait=60, crop_top=60)) == 0
    assert len(reads) >= 3 and screenrec.calls[0][:3] == ["start", "--window", "Android Device"]


def test_record_waits_while_the_window_is_minimised_or_has_no_size(tmp_path, monkeypatch, screenrec):
    polls = iter([[win(3, "Android Device", iconic=True)], [win(3, "Android Device", 0, 0)]])
    reads = []
    monkeypatch.setattr(gr, "top_windows", lambda: (reads.append(1), next(polls, [win(3, "Android Device", 1280, 780)]))[1])
    monkeypatch.setattr(gr.time, "sleep", lambda s: None)
    assert gr.record_cmd(rec_args(tmp_path, window="Android Device", wait=60)) == 0
    assert len(reads) >= 3
    monkeypatch.setattr(gr, "top_windows", lambda: [win(3, "Android Device", iconic=True)])
    with pytest.raises(gr.Refused, match="minimised"):
        gr.record_cmd(rec_args(tmp_path, window="Android Device"))


def test_record_without_wait_refuses_a_missing_window(tmp_path, monkeypatch, screenrec):
    monkeypatch.setattr(gr, "top_windows", lambda: [])
    with pytest.raises(gr.Refused, match="no visible window"):
        gr.record_cmd(rec_args(tmp_path, window="Android Device"))


# --- start, stop, state -------------------------------------------------------------------------------------------

@pytest.fixture
def page(monkeypatch):
    """A fake Run tab: `states` are what successive reads return (the last one repeats); presses are recorded."""
    fake = SimpleNamespace(states=[], presses=[])

    def state(port):
        return fake.states.pop(0) if len(fake.states) > 1 else fake.states[0]

    monkeypatch.setattr(gr, "run_state", state)
    monkeypatch.setattr(gr, "press", lambda port, target: fake.presses.append(target))
    monkeypatch.setattr(gr.time, "sleep", lambda s: None)
    return fake


def phase(p, start=True, alerts=()):
    return {"phase": p, "status": p, "tasks": [], "start": start, "alerts": list(alerts)}


def test_start_presses_start_and_waits_for_the_run(page):
    page.states = [phase("idle"), phase("idle"), phase("running")]
    assert gr.start_cmd(SimpleNamespace(port=9333, timeout=5)) == 0
    assert page.presses == [gr.START]


def test_start_after_a_run_waits_for_this_runs_state_not_the_last_runs_end(page):
    last = {**phase("ended"), "status": "成功", "tasks": [{"name": "領信", "state": "succeeded", "reason": None}]}
    page.states = [last, last, last, phase("running")]
    assert gr.start_cmd(SimpleNamespace(port=9333, timeout=5)) == 0
    assert page.states == [phase("running")]  # every read of the last run's end was passed over


def test_start_refuses_when_start_is_disabled_and_says_why(page):
    page.states = [phase("idle", start=False, alerts=["先填模擬器位址"])]
    with pytest.raises(gr.Refused, match="先填模擬器位址"):
        gr.start_cmd(SimpleNamespace(port=9333, timeout=5))
    assert page.presses == []


def stop_args(tmp_path, **kw):
    return SimpleNamespace(**{"port": 9333, "timeout": 5, "root": str(tmp_path), "on": None, "delay": 0, "limit": 5, **kw})


def test_stop_on_a_line_waits_for_it_in_the_runs_log_then_presses_stop(tmp_path, page):
    log(tmp_path / "logs" / "runner", "run-20261118-145743.log", "14:57:45.600 [maalc] task ClaimMail started\n")
    page.states = [phase("running"), phase("running"), phase("stopping")]
    assert gr.stop_cmd(stop_args(tmp_path, on="task ClaimMail started")) == 0
    assert page.presses == [gr.STOP]


def test_stop_on_a_line_refuses_when_the_run_ends_first(tmp_path, page):
    log(tmp_path / "logs" / "runner", "run-20261118-145743.log", "14:57:45.600 [run] end succeeded\n")
    page.states = [phase("running")]
    with pytest.raises(gr.Refused, match="ended before"):
        gr.stop_cmd(stop_args(tmp_path, on="task ClaimMail started"))
    assert page.presses == []


def test_stop_refuses_when_no_run_is_under_way(tmp_path, page):
    page.states = [phase("ended")]
    with pytest.raises(gr.Refused, match="no run to stop"):
        gr.stop_cmd(stop_args(tmp_path))


def test_state_until_refuses_an_unknown_phase(page):
    page.states = [phase("idle")]
    with pytest.raises(gr.Refused, match="--until takes"):
        gr.state_cmd(SimpleNamespace(port=9333, until="done", timeout=1))


def test_the_users_own_settings_window_keeps_its_title(monkeypatch):
    monkeypatch.setattr(gr, "window_title", lambda hwnd: "maalc")
    monkeypatch.setattr(gr, "users_window", lambda hwnd: True)
    monkeypatch.setattr(gr, "_user32", lambda: pytest.fail("no title may be set"))
    with pytest.raises(gr.Refused, match="user's own"):
        gr.set_title(5, "maalc-live-9333", windows=lambda: [])


def test_the_command_line_needs_a_window_to_record_and_a_port_for_the_page():
    for argv in (["record", "--out", "x"], ["stop"], ["record", "--hwnd", "1", "--window", "a", "--out", "x"]):
        with pytest.raises(SystemExit):
            gr.parser().parse_args(argv)


# --- real windows (Windows) ---------------------------------------------------------------------------------------

@pytest.fixture
def two_maalc_windows():
    """Two top-level windows of this process titled "maalc", off screen, the second larger (an editor's, say)."""
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    u.CreateWindowExW.restype = wintypes.HWND
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                  wintypes.HINSTANCE, wintypes.LPVOID]
    u.DestroyWindow.argtypes = [wintypes.HWND]
    popup_visible = 0x80000000 | 0x10000000  # WS_POPUP | WS_VISIBLE
    made = [u.CreateWindowExW(0x80, "STATIC", "maalc", popup_visible, -9000, -9000, w, h, None, None, None, None)  # WS_EX_TOOLWINDOW
            for w, h in ((640, 400), (1600, 900))]
    assert all(made)
    yield made
    for h in made:
        u.DestroyWindow(h)


@windows_only
def test_a_retitled_window_is_the_only_match_for_its_title(two_maalc_windows):
    gui, other = two_maalc_windows
    title = f"maalc-live-test-{gui}"
    gr.set_title(gui, title)
    assert gr.window_title(gui) == title and gr.window_title(other) == "maalc"
    assert gr.sole(gr.top_windows(), title)["hwnd"] == gui
    with pytest.raises(gr.Refused, match="not 'maalc'"):  # only the settings window's own title is changed
        gr.set_title(gui, "something else")
    gr.set_title(gui, title)  # once more is fine: it already holds it


@windows_only
def test_a_title_another_window_already_holds_is_refused(two_maalc_windows):
    gui, other = two_maalc_windows
    gr.set_title(other, f"maalc-live-test-{other}-long")
    with pytest.raises(gr.Refused, match="already hold"):
        gr.set_title(gui, f"maalc-live-test-{other}")  # a substring of the other's title: screen-record would match both
    assert gr.window_title(gui) == "maalc"


@windows_only
def test_the_job_ends_a_child_when_the_holder_is_killed(tmp_path):
    holder = tmp_path / "holder.py"
    holder.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        sys.path.insert(0, {str(Path(gr.__file__).resolve().parents[1])!r})
        from live import gui_run
        gui_run.kill_with_me()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        print(child.pid, flush=True)
        time.sleep(120)
    """), encoding="utf-8")
    p = subprocess.Popen([sys.executable, str(holder)], stdout=subprocess.PIPE, text=True)
    child = int(p.stdout.readline())
    subprocess.run(["taskkill", "/F", "/PID", str(p.pid)], capture_output=True)  # not /T: only the job can end the child
    p.wait(10)
    for _ in range(50):
        out = subprocess.run(["tasklist", "/FI", f"PID eq {child}", "/NH"], capture_output=True, text=True).stdout
        if str(child) not in out:
            break
        time.sleep(0.1)
    else:
        subprocess.run(["taskkill", "/F", "/PID", str(child)], capture_output=True)
        pytest.fail("the child outlived its holder")


@windows_only
def test_only_an_app_from_the_main_install_is_the_users_window(two_maalc_windows, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(gr, "main_checkout", lambda: tmp_path)
    monkeypatch.setattr(gr, "apps_running", lambda exe: (seen.append(exe), [])[1])
    assert gr.users_window(two_maalc_windows[0]) is False
    assert seen == [tmp_path / "install" / gr.APP]


# --- the Run tab's rows -------------------------------------------------------------------------------------------

def row(task, state, name=None, reason=None):
    return {"id": task, "state": state, "name": name or task, "reason": reason}


def test_run_tasks_lists_only_the_rows_the_run_took_in_the_lists_order():
    rows = [row("ClaimMail", "succeeded", "領信"), row("ChargeEnkephalin", "off"), row("MirrorDungeon", "failed", "鏡像迷宮", "no emulator"),
            row("ExpLuxcavation", "off"), row("AssembleModules", "off"), row("ClaimPassMissions", "pending")]
    assert gr.run_tasks(rows) == [
        {"id": "ClaimMail", "name": "領信", "state": "succeeded", "reason": None},
        {"id": "MirrorDungeon", "name": "鏡像迷宮", "state": "failed", "reason": "no emulator"},
        {"id": "ClaimPassMissions", "name": "ClaimPassMissions", "state": "pending", "reason": None}]


def test_run_tasks_is_empty_before_a_run_and_after_an_edit_ended_the_lists_reading_with_it():
    assert gr.run_tasks([row("ClaimMail", None), row("MirrorDungeon", None)]) == []
    assert gr.run_tasks([]) == []


def test_run_state_keeps_the_pages_fields_and_swaps_its_rows_for_the_runs_tasks(monkeypatch):
    page = {"phase": "running", "status": "執行中", "start": False, "alerts": [],
            "rows": [row("ClaimMail", "running"), row("MirrorDungeon", "off")]}
    monkeypatch.setattr(gr, "evaluate", lambda port, js: page)
    state = gr.run_state(9333)
    assert state == {"phase": "running", "status": "執行中", "start": False, "alerts": [],
                     "tasks": [{"id": "ClaimMail", "name": "ClaimMail", "state": "running", "reason": None}]}
