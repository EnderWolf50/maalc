"""tools/gui_shots.mjs shoots the built settings window with the game's data in it, and refuses a build that has none (#798).

A production build reads the game data only inside the Tauri app, so every still of it is the "Cannot read the game data"
page; a development build bundles the repo's data folder (gui/src/api.ts browserFiles). Both builds are made and served here,
and the tool is run on each. Needs Node, pnpm, the gui's packages and an Edge or Chrome; it skips without one.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "gui_shots.mjs"
GUI = ROOT / "gui"
NODE, PNPM = shutil.which("node"), shutil.which("pnpm")


def have_browser() -> bool:
    env = os.environ
    # the same four places as findBrowser() in tools/gui_shots.mjs
    paths = [(env.get("ProgramFiles(x86)"), "Microsoft/Edge/Application/msedge.exe"),
             (env.get("ProgramFiles"), "Microsoft/Edge/Application/msedge.exe"),
             (env.get("ProgramFiles"), "Google/Chrome/Application/chrome.exe"),
             (env.get("LOCALAPPDATA"), "Google/Chrome/Application/chrome.exe")]
    return any(base and (Path(base) / rel).exists() for base, rel in paths)


pytestmark = pytest.mark.skipif(
    not (sys.platform == "win32" and NODE and PNPM and (GUI / "node_modules").exists() and have_browser()),
    reason="needs Windows, Node, pnpm, the gui's packages and Edge or Chrome")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build(out: Path, development: bool) -> None:
    env = {**os.environ, "NODE_ENV": "development" if development else "production"}
    r = subprocess.run([PNPM, "--dir", str(GUI), "exec", "vite", "build", "--outDir", str(out), "--emptyOutDir"],
                       env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def serve(tmp_path_factory):
    """`serve(development)`: the URL of that build under `vite preview`; every preview is stopped at the end."""
    procs = []

    def start(development: bool) -> str:
        out = tmp_path_factory.mktemp("dev" if development else "prod")
        build(out, development)
        port = free_port()
        p = subprocess.Popen([PNPM, "--dir", str(GUI), "exec", "vite", "preview", "--outDir", str(out), "--port", str(port),
                              "--strictPort", "--host", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                return f"http://127.0.0.1:{port}/"
            except OSError:
                time.sleep(0.2)
        raise AssertionError("vite preview did not start")

    yield start
    for p in procs:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)


def shoot(url: str, out: Path, only: str):
    return subprocess.run([NODE, str(TOOL), "--out", str(out), "--url", url, "--only", only],
                          capture_output=True, text=True, timeout=300)


def test_a_development_build_is_shot_with_its_game_data(serve, tmp_path):
    r = shoot(serve(True), tmp_path, "gifts,starlight,themepacks-images")
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("gifts", "starlight", "themepacks-images"):
        assert (tmp_path / "light" / f"{name}.png").is_file()


def test_a_production_build_has_no_game_data_and_no_still_is_written(serve, tmp_path):
    r = shoot(serve(False), tmp_path, "gifts")
    assert r.returncode == 1
    assert "cannot read the game data" in r.stdout and "NODE_ENV=development" in r.stdout
    assert not list(tmp_path.rglob("*.png"))
