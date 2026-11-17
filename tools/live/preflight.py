"""Cheap checks before a costly step of a live test, and two that run during the run (the maalc-live-test skill).

    uv run --group probe python tools/live/preflight.py screen [--install DIR] [--port 16384] [--shot OUT.png]
    uv run python tools/live/preflight.py recording --out DIR [--seconds 15]
    uv run python tools/live/preflight.py plan --log run.log [--within 60]

**screen** screenshots the emulator and names the screen with the pipeline's own nodes (the install's resource/base):
`ok` the main screen (exit 0); `accept` an update, download or User Agreement dialog, which the user allowed the bot
to accept on 2026-10-21 (exit 0, the line says which; the bot's nodes do it when `run.auto_download` /
`run.auto_accept_terms` are on); `stop` a resumable Mirror Dungeon run, an outdated client or any other screen (exit 1
with the reason). Run it before any pytest or install rebuild: a game update found after 21 minutes of prep cost a run.

**recording** says whether the recording in progress in `--out` (the `.mkv` its live `rec_<profile>.state.json` names)
grew over `--seconds`. A file that did not grow, or that ffmpeg has not written yet because no frame came, is a `note:`
for the report, exit 0: a game frozen on one screen draws nothing, like a sleeping display, so a still file does not mean
a broken recording, and the recording stays on. Exit 1 only when `--out` has no recording in progress: no state file
without `ended` whose `ffmpeg_pid` still runs (the state format is `save()` of the screen-record skill's `screenrec.py`).

**plan** waits up to `--within` seconds for the bot's `new run:` line (a run it planned itself) in `--log`. A
`no run plan in memory` line, or none in time, means the bot continues a leftover run with no plan (weekly bonuses,
Modules and the team are then not its own choice): exit 1, stop it. For a task that plans no Mirror run pass
`--pattern`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from live import screen_probe  # noqa: E402
from local_dir import main_checkout  # noqa: E402

# Pipeline node -> (verdict, what it means), in the order the probe tries them: the first that hits names the screen.
SCREENS = {
    "UpdateDialog": ("accept", "a game update dialog"),
    "DownloadDialog": ("accept", "a data download dialog"),
    "UserAgreement": ("accept", "the User Agreement"),
    "ClientOutdated": ("stop", "the game client is out of date: update it from the Play Store (the user's call)"),
    "ResumeDialog": ("stop", "the Resume dialog of a paused Mirror Dungeon run; forfeiting or continuing it is the user's call"),
    "MirrorEntryPaused": ("stop", "the entry page of a resumable Mirror Dungeon run; forfeiting or continuing it is the user's call"),
    "HomeReached": ("ok", "the main screen"),
}
PROBE = "PreflightProbe"
PROBE_TIMEOUT_MS = 4000


def classify(hit: str | None) -> tuple[str, str]:
    """(verdict, reason) for the node that hit; None when no node of SCREENS did."""
    return SCREENS.get(hit) or ("stop", "not the main screen and none of the known dialogs: look at a screenshot")


def probe_override() -> dict:
    """The pipeline override of one probe task: the known nodes tried in order, each with its action switched off."""
    return screen_probe.override(PROBE, SCREENS, PROBE_TIMEOUT_MS)


def first_hit(node_names: list[str]) -> str | None:
    return screen_probe.first_hit(node_names, SCREENS)


def look(root: Path, port: int, shot: Path | None) -> str | None:
    """The name of the first known node that reads the emulator's screen now (None: none of them)."""
    import os

    os.environ["MAAFW_BINARY_PATH"] = str(root / "maafw")
    from maa.resource import Resource
    from maa.tasker import Tasker
    from maa.toolkit import Toolkit

    from live.device import connect
    from live.device import shot as save

    Toolkit.init_option(str(root / "debug"))
    ctl = connect(port)
    if shot:
        save(ctl, shot)
    res = Resource()
    res.post_bundle(str(root / "resource/base")).wait()
    t = Tasker()
    t.bind(res, ctl)
    return screen_probe.look(t, PROBE, probe_override(), SCREENS)


def screen(root: Path, port: int, shot: Path | None, say=print, see=look) -> int:
    if shot:
        shot.parent.mkdir(parents=True, exist_ok=True)  # the archive folder of a new topic is made at step 5, after this
    verdict, reason = classify(see(root, port, shot))
    say(f"{verdict}: {reason}")
    return 1 if verdict == "stop" else 0


def ffmpeg_running(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq ffmpeg.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    return f'"{pid}"' in r.stdout


def read_state(sp: Path) -> dict:
    for _ in range(5):  # screenrec swaps the file in with os.replace; Windows can refuse a read during the swap
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.2)
    return {}


def live_recording(out: Path, running=None) -> Path | None:
    """The .mkv of the newest recording still running in `out`: its rec_<profile>.state.json names it, has no `ended`,
    and its ffmpeg runs. screenrec writes the .mkv once the first frame is encoded and remuxes it to .mp4 at stop."""
    running, live = running or ffmpeg_running, []
    for sp in out.glob("rec_*.state.json"):
        st = read_state(sp)
        if st.get("mkv") and not st.get("ended") and running(st.get("ffmpeg_pid")):
            live.append((sp.stat().st_mtime, Path(st["mkv"])))
    return max(live)[1] if live else None


def size_of(f: Path) -> int | None:
    try:
        return f.stat().st_size
    except FileNotFoundError:
        return None  # no frame encoded yet, or `stop` already removed it


def recording_check(out: Path, seconds: float, say=print, sleep=time.sleep, clock=time.strftime, running=None) -> int:
    rec = live_recording(out, running)
    if rec is None:
        say(f"no recording in progress in {out} (no rec_*.state.json with a running ffmpeg): start one with screenrec.py start")
        return 1
    size = size_of(rec) or 0
    sleep(seconds)
    now = size_of(rec)
    if now and now > size:
        say(f"{rec.name} grew {size} -> {now} bytes in {seconds:.0f} s")
        return 0
    what = "did not grow" if now is not None else "has no frame yet"
    say(f"note: {rec.name} {what} in the {seconds:.0f} s before {clock('%H:%M:%S')}: no new frames "
        "(a frozen game or a sleeping display). Keep recording; put this line in the report")
    return 0


NEW_RUN = r"\[maalc\] new run: \S+, team "  # the plan line (agent/run_start_actions.py); the other `new run:` lines are Module reads
NO_PLAN = re.compile(r"no run plan in memory")
BOT_START = "[run] child pid"  # tools/live/bot.py writes it when it starts the agent; the log is appended to across runs


def plan_line(log: Path, within: float, pattern: str = NEW_RUN, say=print, clock=time.monotonic, sleep=time.sleep) -> int:
    want, deadline = re.compile(pattern), clock() + within
    while True:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
        starts = [i for i, l in enumerate(lines) if BOT_START in l]
        lines = lines[starts[-1]:] if starts else lines  # only the bot run that just started
        if bad := next((l for l in lines if NO_PLAN.search(l)), None):
            say(f"stop: the bot has no run plan ({bad.strip()[:140]}); it continues a leftover run. Stop the run tree and look at the screen")
            return 1
        if hit := next((l for l in lines if want.search(l)), None):
            say(f"ok: {hit.strip()[:160]}")
            return 0
        if clock() >= deadline:
            say(f"stop: no line matching /{pattern}/ in {within:.0f} s: the bot may be continuing a leftover run. Look at the screen before letting it go on")
            return 1
        sleep(2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("screen")
    s.add_argument("--install", type=Path, default=main_checkout() / "install")
    s.add_argument("--port", type=int, default=16384)
    s.add_argument("--shot", type=Path)
    r = sub.add_parser("recording")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--seconds", type=float, default=15)
    p = sub.add_parser("plan")
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--within", type=float, default=60)
    p.add_argument("--pattern", default=NEW_RUN)
    a = ap.parse_args(argv)
    if a.command == "screen":
        return screen(a.install.resolve(), a.port, a.shot)
    if a.command == "recording":
        return recording_check(a.out, a.seconds)
    return plan_line(a.log, a.within, a.pattern)


if __name__ == "__main__":
    sys.exit(main())
