"""Cheap checks before a costly step of a live test, and two that run during the run (the maalc-live-test skill).

    uv run --group probe python tools/live/preflight.py screen [--install DIR] [--port 16384] [--shot OUT.png]
    uv run python tools/live/preflight.py recording --out DIR [--seconds 15]
    uv run python tools/live/preflight.py plan --log run.log [--within 60]

**screen** screenshots the emulator and names the screen with the pipeline's own nodes (the install's resource/base):
`ok` the main screen (exit 0); `accept` an update, download or User Agreement dialog, which the user allowed the bot
to accept on 2026-10-21 (exit 0, the line says which; the bot's nodes do it when `run.auto_download` /
`run.auto_accept_terms` are on); `stop` a resumable Mirror Dungeon run, an outdated client or any other screen (exit 1
with the reason). Run it before any pytest or install rebuild: a game update found after 21 minutes of prep cost a run.

**recording** exits 1 when the newest `rec_*.mkv` (a recording in progress) or `rec_*.mp4` in `--out` did not grow over `--seconds`: a display that went to sleep
after `screenrec.py start` leaves a clip with no frames.

**plan** waits up to `--within` seconds for the bot's `new run:` line (a run it planned itself) in `--log`. A
`no run plan in memory` line, or none in time, means the bot continues a leftover run with no plan (weekly bonuses,
Modules and the team are then not its own choice): exit 1, stop it. For a task that plans no Mirror run pass
`--pattern`.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

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
    nodes = {n: {"action": "DoNothing", "next": [], "post_delay": 0, "pre_delay": 0} for n in SCREENS}
    nodes[PROBE] = {"recognition": "DirectHit", "action": "DoNothing", "next": list(SCREENS), "timeout": PROBE_TIMEOUT_MS}
    return nodes


def first_hit(node_names: list[str]) -> str | None:
    return next((n for n in node_names if n in SCREENS), None)


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
    job = t.post_task(PROBE, probe_override())
    job.wait()
    detail = job.get()
    return first_hit([n.name for n in detail.nodes] if detail else [])


def screen(root: Path, port: int, shot: Path | None, say=print, see=look) -> int:
    verdict, reason = classify(see(root, port, shot))
    say(f"{verdict}: {reason}")
    return 1 if verdict == "stop" else 0


def recording_grows(out: Path, seconds: float, say=print, sleep=time.sleep) -> int:
    def newest():
        # screenrec writes .mkv while recording and remuxes it to .mp4 at stop; a tie goes to the .mkv
        files = sorted([*out.glob("rec_*.mkv"), *out.glob("rec_*.mp4")], key=lambda p: (p.stat().st_mtime, p.suffix == ".mkv"))
        return (files[-1], files[-1].stat().st_size) if files else (None, 0)

    first, size = newest()
    if first is None:
        say(f"no rec_*.mkv or rec_*.mp4 in {out}: the recording did not start")
        return 1
    sleep(seconds)
    last, now = newest()
    if last == first and now > size:
        say(f"{first.name} grew {size} -> {now} bytes in {seconds:.0f} s")
        return 0
    say(f"{first.name} did not grow in {seconds:.0f} s ({size} bytes): the display may be asleep (bot.py awake); stop the recording and start it again")
    return 1


NEW_RUN = r"\[maalc\] new run: "
NO_PLAN = re.compile(r"no run plan in memory")


def plan_line(log: Path, within: float, pattern: str = NEW_RUN, say=print, clock=time.monotonic, sleep=time.sleep) -> int:
    want, deadline = re.compile(pattern), clock() + within
    while True:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
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
        return recording_grows(a.out, a.seconds)
    return plan_line(a.log, a.within, a.pattern)


if __name__ == "__main__":
    sys.exit(main())
