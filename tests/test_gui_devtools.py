"""tools/gui_devtools.mjs: what a test can hold without a WebView2 (arguments, targets, keys, what `open` and `close` stop).

The page side (press, drag, scheme, stills) is proven on the real window: the tool's docs name that run.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import gui_probe as gp

TOOL = Path(__file__).resolve().parents[1] / "tools" / "gui_devtools.mjs"
NODE = shutil.which("node")
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="finds processes through Win32_Process")


def call(fn, *args):
    """The JSON value of the tool module's `fn(*args)`, or {"error": message} when it throws."""
    script = (f"import * as t from {json.dumps(TOOL.as_uri())};"
              f"let r; try {{ r = await t.{fn}(...{json.dumps(args)}); }} catch (e) {{ r = {{ error: e.message, usage: e.usage ?? false }}; }}"
              "process.stdout.write(JSON.stringify(r === undefined ? null : r));")
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def run(*args, timeout=60):
    return subprocess.run([NODE, str(TOOL), *args], capture_output=True, text=True, timeout=timeout)


# --- the command line ---------------------------------------------------------------------------------------------

def test_no_command_prints_the_usage_and_exits_2():
    r = run()
    assert r.returncode == 2
    assert "open --root" in r.stderr and "drag <from>" in r.stderr


def test_an_unknown_command_exits_2_and_names_it():
    r = run("jump", "--port", "9333")
    assert r.returncode == 2 and "jump" in r.stderr


@pytest.mark.parametrize("argv, words", [
    (["press"], "--port"),                                  # a page command needs the port
    (["press", "--port", "9333"], "target"),                # and its target
    (["drag", "--port", "9333"], "target"),
    (["key", "--port", "9333"], "key"),
    (["eval", "--port", "9333"], "expression"),
    (["still", "--port", "9333"], "png"),
    (["scheme", "sepia", "--port", "9333"], "light or dark"),
    (["press", "1,2", "--port", "x"], "--port"),
    (["press", "1,2", "--port", "9333", "--keep", "soon"], "--keep"),
    (["press", "1,2", "--port", "9333", "--viewport", "800"], "--viewport"),
    (["press", "1,2", "--port", "9333", "--colour", "red"], "--colour"),  # an option no command takes
    (["open"], "--root"),
    (["close"], "--root"),
    (["drag", ".a", "--port", "9333", "--keep", "forever"], "seconds"),  # a drag in the air ends by itself
])
def test_a_bad_command_line_exits_2_and_says_what_is_wrong(argv, words):
    r = run(*argv)
    assert r.returncode == 2, r.stderr
    assert words in r.stderr


def test_parse_reads_a_page_command_with_its_session_options():
    got = call("parseCommand", ["box", ".grace-side", "nav.sections", "--port", "9333", "--viewport", "800x480",
                                "--scheme", "light", "--keep", "2.5"])
    assert got["command"] == "box"
    assert got["args"] == [".grace-side", "nav.sections"]
    assert got["port"] == 9333
    assert got["viewport"] == {"width": 800, "height": 480}
    assert got["scheme"] == "light"
    assert got["keepMs"] == 2500


def test_scheme_and_hover_keep_their_state_until_stopped_and_the_rest_end_at_once():
    assert call("parseCommand", ["scheme", "light", "--port", "1"])["keepMs"] is None  # null: until stopped
    assert call("parseCommand", ["hover", ".pk", "--port", "1"])["keepMs"] is None
    assert call("parseCommand", ["press", ".pk", "--port", "1"])["keepMs"] == 0
    assert call("parseCommand", ["scheme", "dark", "--port", "1", "--keep", "3"])["keepMs"] == 3000
    assert call("parseCommand", ["press", ".pk", "--port", "1", "--keep", "forever"])["keepMs"] is None


def test_a_drag_with_nowhere_to_drop_stays_in_the_air_ten_seconds_unless_told():
    assert call("parseCommand", ["drag", ".a", "--port", "1"])["keepMs"] == 10000
    assert call("parseCommand", ["drag", ".a", "--port", "1", "--keep", "4"])["keepMs"] == 4000
    assert call("parseCommand", ["drag", ".a", ".b", "--port", "1"])["keepMs"] == 0


# --- targets and keys ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    ("120,80", {"kind": "point", "x": 120, "y": 80}),
    ("120.5, 80.25", {"kind": "point", "x": 120.5, "y": 80.25}),
    (".grace-side button", {"kind": "css", "selector": ".grace-side button"}),
    ("[data-tab='teams']", {"kind": "css", "selector": "[data-tab='teams']"}),
    ("js:document.querySelectorAll('.grace')[5]", {"kind": "js", "expr": "document.querySelectorAll('.grace')[5]"}),
])
def test_a_target_is_a_point_a_selector_or_an_expression(text, want):
    assert call("parseTarget", text) == want


def test_shift_tab_holds_shift_around_the_tab():
    ev = call("keyEvents", "Shift+Tab")
    assert [(e["type"], e["key"], e["modifiers"]) for e in ev] == [
        ("rawKeyDown", "Shift", 8), ("rawKeyDown", "Tab", 8), ("keyUp", "Tab", 8), ("keyUp", "Shift", 0)]
    tab = ev[1]
    assert tab["code"] == "Tab" and tab["windowsVirtualKeyCode"] == 9 and tab["nativeVirtualKeyCode"] == 9
    assert "text" not in tab


def test_ctrl_s_sends_the_letter_without_text_and_a_plain_letter_types_it():
    ctrl_s = call("keyEvents", "ctrl+s")
    assert [e["key"] for e in ctrl_s] == ["Control", "s", "s", "Control"]
    assert ctrl_s[1]["code"] == "KeyS" and ctrl_s[1]["windowsVirtualKeyCode"] == 83 and ctrl_s[1]["modifiers"] == 2
    assert "text" not in ctrl_s[1]
    a = call("keyEvents", "a")
    assert a[0] == {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65,
                    "modifiers": 0, "text": "a", "unmodifiedText": "a"}
    assert call("keyEvents", "Shift+A")[1]["text"] == "A"


def test_enter_types_a_return_and_alt_f4_is_a_system_key():
    assert call("keyEvents", "Enter")[0]["text"] == "\r"
    f4 = [e for e in call("keyEvents", "Alt+F4") if e["key"] == "F4"]
    assert [e["isSystemKey"] for e in f4] == [True, True] and f4[0]["windowsVirtualKeyCode"] == 115
    assert call("keyEvents", "PageDown")[0]["windowsVirtualKeyCode"] == 34
    assert call("keyEvents", "Esc")[0]["key"] == "Escape"


def test_an_ime_key_is_reported_as_process():
    s = call("keyEvents", "Ctrl+S", True)[1]
    assert s["key"] == "Process" and s["windowsVirtualKeyCode"] == 229 and s["code"] == "KeyS"


def test_an_unknown_key_names_itself():
    assert "Nope" in call("keyEvents", "Ctrl+Nope")["error"]
    assert "modifier" in call("keyEvents", "Ctrl+Shift")["error"]


# --- what open and close stop -------------------------------------------------------------------------------------

def test_the_marker_is_the_probes():
    assert call("probeMarker") == gp.MARKER


def test_root_state_tells_a_probe_root_from_a_foreign_one(tmp_path):
    assert call("rootState", str(tmp_path / "none")) == "missing"
    foreign = tmp_path / "home"
    foreign.mkdir()
    assert call("rootState", str(foreign)) == "foreign"
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / gp.MARKER).write_text("x")
    assert call("rootState", str(probe)) == "probe"


AUTO = object()


def proc(pid, name, exe, cmd=AUTO):
    return {"pid": pid, "name": name, "exe": exe, "cmd": f'"{exe}"' if cmd is AUTO else cmd}


def test_started_from_picks_the_roots_app_and_the_webview2_on_its_data_folder():
    root = r"C:\s\gui-root"
    view = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\142.0\msedgewebview2.exe"
    procs = [
        proc(1, "maalc-gui.exe", r"C:\s\gui-root\maalc-gui.exe"),
        proc(2, "maalc-gui.exe", r"C:\games\install\maalc-gui.exe"),  # the user's own app
        proc(3, "maalc-gui.exe", r"C:\s\gui-root-2\maalc-gui.exe"),  # another root sharing the prefix
        proc(4, "msedgewebview2.exe", view, f'"{view}" --embedded-browser-webview=1 --user-data-dir="C:\\s\\gui-root\\webview2\\EBWebView" --x'),
        proc(5, "msedgewebview2.exe", view, f'"{view}" --type=renderer --user-data-dir="C:\\s\\gui-root-2\\webview2\\EBWebView"'),
        proc(6, "msedgewebview2.exe", view, f'"{view}" --type=gpu-process --user-data-dir=C:\\s\\gui-root\\webview2\\EBWebView'),
        proc(7, "msedgewebview2.exe", view, f'"{view}" --user-data-dir="C:\\Users\\u\\AppData\\Local\\tw.enderwolf.maalc\\EBWebView"'),
        proc(8, "msedgewebview2.exe", view, None),  # a process whose command line cannot be read
    ]
    assert call("startedFrom", procs, root) == [1, 4, 6]


def test_started_from_ignores_case_and_slashes():
    procs = [proc(1, "MAALC-GUI.EXE", "c:/S/Gui-Root/maalc-gui.exe"),
             proc(2, "msedgewebview2.exe", "x", '--user-data-dir="c:/s/GUI-ROOT/webview2/EBWebView"')]
    assert call("startedFrom", procs, "C:\\s\\gui-root\\") == [1, 2]


def node_exe():
    return subprocess.run([NODE, "-p", "process.execPath"], capture_output=True, text=True, check=True).stdout.strip()


def fake(path: Path, *args):
    """A process running as `path`: node itself, linked or copied there, waiting a minute with `args` on its command line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            os.link(node_exe(), path)
        except OSError:
            shutil.copy2(node_exe(), path)
    return subprocess.Popen([str(path), "-e", "setTimeout(() => {}, 60000)", "--", *args])


def wait_gone(p, seconds=15):
    try:
        p.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


@windows_only
def test_close_stops_exactly_what_runs_from_the_root(tmp_path):
    root = tmp_path / "gui-root"
    other = tmp_path / "gui-root-2"
    for r in (root, other):
        r.mkdir()
        (r / gp.MARKER).write_text("x")
    view = tmp_path / "runtime" / "msedgewebview2.exe"
    started = [
        fake(root / "maalc-gui.exe"),
        fake(view, f'--user-data-dir={root / "webview2" / "EBWebView"}'),
    ]
    spared = [
        fake(other / "maalc-gui.exe"),
        fake(view, f'--user-data-dir={other / "webview2" / "EBWebView"}'),
    ]
    try:
        time.sleep(1)
        r = run("close", "--root", str(root))
        assert r.returncode == 0, r.stderr
        assert sorted(json.loads(r.stdout.splitlines()[-1])["stopped"]) == sorted(p.pid for p in started)
        assert all(wait_gone(p) for p in started)
        assert all(p.poll() is None for p in spared)
    finally:
        for p in started + spared:
            p.kill()


@windows_only
def test_close_on_a_folder_the_probe_did_not_make_stops_nothing(tmp_path):
    home = tmp_path / "install"  # as the user's install/: an app runs from it, and it has no marker
    app = fake(home / "maalc-gui.exe")
    try:
        r = run("close", "--root", str(home))
        assert r.returncode == 1
        assert gp.MARKER in r.stderr
        time.sleep(1)
        assert app.poll() is None
    finally:
        app.kill()


def test_close_on_a_missing_root_has_nothing_to_stop(tmp_path):
    r = run("close", "--root", str(tmp_path / "never"))
    assert r.returncode == 0
    assert json.loads(r.stdout.splitlines()[-1]) == {"stopped": []}


def test_open_on_a_folder_the_probe_did_not_make_starts_nothing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "precious.txt").write_text("keep")
    r = run("open", "--root", str(home), "--exe", str(tmp_path / "missing.exe"))
    assert r.returncode == 1
    assert gp.MARKER in r.stderr
    assert sorted(p.name for p in home.iterdir()) == ["precious.txt"]
