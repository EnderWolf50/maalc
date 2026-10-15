"""Stuck detection, recovery levels and the run time limit, free of MaaFramework (docs/spec/06-recovery.md).

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
           "MirrorEntryPaused", "ResumeDialog", "ProgressPanel"}
L2_PER_RUN, L3_PER_RUN, L3_PER_EXECUTION = 3, 2, 3
BATTLE_LIMIT = 20 * 60
RUN_LIMIT_DEFAULT, RUN_LIMIT_MIN_RUNS = 60 * 60, 10


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


class Watchdog:
    """Spots a screen that does not change (spec 06 卡住的定義: 畫面沒變, 載入畫面過久)."""

    def __init__(self):
        self.kind, self.kind_since = None, 0.0
        self.first, self.count, self.since = None, 0, 0.0  # the streak's first thumbnail

    def see(self, kind, small, now):
        """Record one screen handed out by MirrorHub (its type and thumb); True when it makes the bot stuck."""
        if kind != self.kind:
            self.kind, self.kind_since, self.first = kind, now, None
        if not same_screen(small, self.first):
            self.first, self.count, self.since = small, 0, now
        self.count += 1
        if kind in WAIT_LIMITS:
            return now - self.kind_since > WAIT_LIMITS[kind]
        return self.count >= SAME_SCREEN and now - self.since >= HASH_FLOOR.get(kind, 0)

    def reset(self):
        self.__init__()


class Ladder:
    """One run's recovery levels and their limits (spec 06 恢復的三級, 上限與停止).

    A stuck opens an episode on its screen type at the start level (L1, or L2 for the time limits);
    each further stuck before the bot gets past that screen climbs one level. Getting past it closes
    the episode; the same screen type stuck again later in the run stops.
    """

    def __init__(self):
        self.counts = {1: 0, 2: 0, 3: 0}
        self.open = None  # (screen type, level) of the episode under way
        self.done = set()

    def stuck(self, kind, start, l3_this_execution):
        """(level, None) to recover with, or (None, why) to stop."""
        if self.open:
            kind, level = self.open[0], self.open[1] + 1
        elif kind in self.done:
            return None, f"stuck on {kind} a second time this run"
        else:
            level = start
        if level > 3:
            return None, "L3 did not get past it"
        if level == 2 and self.counts[2] >= L2_PER_RUN:
            return None, f"L2 used {L2_PER_RUN} times this run"
        if level == 3 and self.counts[3] >= L3_PER_RUN:
            return None, f"game restarted {L3_PER_RUN} times this run"
        if level == 3 and l3_this_execution >= L3_PER_EXECUTION:
            return None, f"game restarted {L3_PER_EXECUTION} times since the bot started"
        self.counts[level] += 1
        self.open = (kind, level)
        return level, None

    def progress(self, kind):
        """MirrorHub handed out kind: a screen other than the stuck one closes the episode."""
        if self.open and kind != self.open[0] and kind not in TRANSIT:
            self.done.add(self.open[0])
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
    """Seconds team_id's run may take (spec 06 整局超時).

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
