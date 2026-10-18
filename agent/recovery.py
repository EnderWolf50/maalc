"""Stuck detection, recovery levels and the floor time limit, free of MaaFramework (docs/spec/06-recovery.md).

actions.py feeds every screen MirrorHub hands out to a Watchdog, asks a Ladder which level to
recover with, and does the taps; everything here is plain data in, plain data out.
"""

import json
import statistics
import struct
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np

SAME_SCREEN = 5  # the same screen type and thumbnail this many times in a row is stuck
WAIT_LIMITS = {"Loading": 90, "Connecting": 90}  # seconds a waiting screen may last, whatever it shows
HASH_FLOOR = {"BattlePause": 30}  # a turn playing out may sit still a while: also this many seconds
# Screens on the way back to a run after L2/L3: seeing them does not mean the stuck screen was got past.
TRANSIT = {"Loading", "Connecting", "RetryPopup", "GoToMirrorEntry", "NavTitle", "NavMainTabs", "NavDrive",
           "MirrorEntryPaused", "ResumeDialog", "ProgressPanel", "DownloadDialog", "PopupButton"}
UNKNOWN_KEEP = 30  # screens MirrorHub did not recognise that logs/unknown/ keeps
DOWNLOAD_HOLD = 30 * 60  # seconds after confirming the title's download dialog in which nothing is stuck
L2_PER_RUN, L3_PER_RUN, L3_PER_EXECUTION = 3, 2, 3
BATTLE = {"BattleTurn", "BattlePause"}  # L2 cannot go through mid-battle: only the map has To Window
BATTLE_LIMIT = 20 * 60
RUN_LIMIT_DEFAULT, RUN_LIMIT_MIN_RUNS = 60 * 60, 10
FLOOR_LIMIT, FLOORS = 45 * 60, 5  # live (#34): a HARD floor took up to ~25 min of real progress


def thumb(image):
    """A 32x18 grey thumbnail of a 1280x720 BGR screenshot: each 40x40 block's mean brightness."""
    h, w = image.shape[0] // 40 * 40, image.shape[1] // 40 * 40
    return image[:h, :w].reshape(h // 40, 40, w // 40, 40, -1).mean(axis=(1, 3, 4))


def same_screen(a, b):
    """Whether two thumbnails show the same screen: under 3% of the blocks moved by more than 8 levels.

    Live: the map's bus flame and glows flicker every frame, so an exact match never repeats.
    """
    return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 8).mean() < 0.03


def png(image):
    """A BGR screenshot as PNG bytes (stdlib only)."""
    h, w = image.shape[:2]
    rows = np.hstack([np.zeros((h, 1), np.uint8), image[:, :, ::-1].reshape(h, w * 3)])

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + chunk(b"IEND", b""))


def keep_unknown(root, image, stamp):
    """Save a screen MirrorHub recognised nothing on to <root>/logs/unknown/<stamp>.png, the newest UNKNOWN_KEEP.

    A popup nobody has a capture of (weekly reset, tutorial tip, an event's choice page) is otherwise lost once
    the back key closes it; this is the capture its node needs.
    """
    folder = Path(root) / "logs" / "unknown"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stamp}.png").write_bytes(png(image))
    for old in sorted(folder.glob("*.png"))[:-UNKNOWN_KEEP]:
        old.unlink()


class Watchdog:
    """Spots a screen that does not change (spec 06 卡住的定義: 畫面沒變, 載入畫面過久)."""

    def __init__(self):
        self.kind, self.kind_since = None, 0.0
        self.first, self.count, self.since = None, 0, 0.0  # the streak's first thumbnail
        self.hold_until = 0.0  # a download is under way until then: no screen counts as stuck

    def see(self, kind, small, now):
        """Record one screen handed out by MirrorHub (its type and thumb); True when it makes the bot stuck."""
        if kind != self.kind:
            self.kind, self.kind_since, self.first = kind, now, None
        if not same_screen(small, self.first):
            self.first, self.count, self.since = small, 0, now
        self.count += 1
        if self.held(now):
            return False
        if kind in WAIT_LIMITS:
            return now - self.kind_since > WAIT_LIMITS[kind]
        return self.count >= SAME_SCREEN and now - self.since >= HASH_FLOOR.get(kind, 0)

    def hold(self, now, seconds):
        """A download was confirmed: nothing is stuck for the next seconds (its progress screen is not known)."""
        self.hold_until = now + seconds

    def held(self, now):
        return now < self.hold_until

    def reset(self):
        self.__init__()


class Ladder:
    """One run's recovery levels and their limits (spec 06 恢復的三級, 上限與停止).

    A stuck opens an episode on its screen type at the start level (L1, or L2 for the time limits);
    each further stuck before the bot gets past that screen climbs one level, up to L3, which may repeat
    within its limits (live: a restarted game sometimes hangs on CONNECTING). Getting past it closes
    the episode: a later stuck, even on the same screen type, starts over at its start level
    (2026-10-16). Only the per-run and per-launch caps stop. A battle skips L2 (live 2026-10-17, #70: it
    failed there and L3 followed anyway), and a level that did not go through is not charged to the run.
    """

    def __init__(self):
        self.counts = {1: 0, 2: 0, 3: 0}
        self.open = None  # (screen type, level) of the episode under way

    def stuck(self, kind, start, l3_this_execution):
        """(level, None) to recover with, or (None, why) to stop."""
        if self.open:
            kind, level = self.open[0], min(self.open[1] + 1, 3)  # L3 repeats while its limits allow
        else:
            level = start
        if level == 2 and kind in BATTLE:
            level = 3
        if level == 2 and self.counts[2] >= L2_PER_RUN:
            return None, f"L2 used {L2_PER_RUN} times this run"
        if level == 3 and self.counts[3] >= L3_PER_RUN:
            return None, f"game restarted {L3_PER_RUN} times this run"
        if level == 3 and l3_this_execution >= L3_PER_EXECUTION:
            return None, f"game restarted {L3_PER_EXECUTION} times since the bot started"
        self.counts[level] += 1
        self.open = (kind, level)
        return level, None

    def failed(self, level):
        """The level just given did not go through (L2 off the map, a failed force-stop): uncharge it.

        The episode stays at that level, so the next stuck climbs on or repeats L3; the caller still
        counts every L3 attempt towards L3_PER_EXECUTION, which bounds a force-stop that always fails.
        """
        self.counts[level] -= 1

    def progress(self, kind):
        """MirrorHub handed out kind: a screen other than the stuck one closes the episode."""
        if self.open and kind != self.open[0] and kind not in TRANSIT:
            self.open = None


def read_runs(root):
    """Every line of <root>/logs/runs.jsonl as a dict; unreadable lines are skipped."""
    lines = []
    try:
        text = (Path(root) / "logs" / "runs.jsonl").read_text(encoding="utf-8")
    except OSError:
        return lines
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            lines.append(item)
    return lines


def _seconds(start, end):
    return (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()


def run_limit(lines, team_id):
    """Seconds team_id's whole run may take, floor_limit's history part (spec 06 每層超時).

    Only the team's cleared runs with both times after its latest reset marker count:
    10 or more of them give twice their 95th percentile, fewer give 60 minutes.
    """
    since = max((i for i, x in enumerate(lines) if x.get("reset") == team_id), default=-1)
    times = []
    for x in lines[since + 1:]:
        if x.get("team") == team_id and x.get("result") == "clear" and x.get("start") and x.get("end"):
            try:
                times.append(_seconds(x["start"], x["end"]))
            except (TypeError, ValueError):
                continue
    if len(times) < RUN_LIMIT_MIN_RUNS:
        return RUN_LIMIT_DEFAULT
    return 2 * statistics.quantiles(times, n=20, method="inclusive")[-1]


def floor_limit(lines, team_id):
    """Seconds one floor of team_id's run may take (spec 06 每層超時): 45 minutes, or the team's
    run_limit spread over the 5 floors when that is longer.

    Live 2026-10-16 (#34): two HARD runs took 80 and 107 minutes of steady progress, so a whole-run
    limit of 60 minutes broke into runs that were fine. A floor restarts the clock, so a run that keeps
    reaching new floors is never cut off; a floor stuck past it still is.
    """
    return max(FLOOR_LIMIT, run_limit(lines, team_id) / FLOORS)


def over_time(kind, deadline, now):
    """Whether the floor time limit fires on this screen type.

    On the map, where L2 goes through; elsewhere only a battle's limit later: L2 fails mid-battle, and the
    L3 that follows restarts the game and the battle with it (live 2026-10-16, #34).
    """
    return deadline is not None and now > deadline + (0 if kind == "MirrorMap" else BATTLE_LIMIT)
