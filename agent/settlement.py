"""Settlement decisions, free of MaaFramework (docs/spec/03-decisions.md sections 1, 14).

actions.py reads the Exploration Reward window and taps; everything here is plain data in, plain data out.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from ocrtext import compact, floor_number, has


class Result(NamedTuple):
    """The Exploration Reward window's result line. difficulty: normal, hard, infinity, extreme, or None when the marker did not read."""

    floor: int
    difficulty: str | None
    cleared: int
    total: int

    @property
    def hard(self):
        """Whether the run was HARD: floors 6 and up need every floor HARD, so any of them is; None when a floor 1-5 marker did not read."""
        if self.difficulty is not None:
            return self.difficulty != "normal"
        return True if self.floor > 5 else None


MARKER = r"\[?\s*(HARD|NORMAL|INFINITY|EXTREME)\s*\]?"


def read_result(text):
    """The window's result as a Result, e.g. "Floor 5 [NORMAL] 6/6"; None when floor or progress is unreadable.

    The INFINITY and EXTREME markers are a guess from the game data (no capture shows them). A marker that does not
    read leaves difficulty None and the floors still decide the Claim (#384), instead of the window looking unread.
    """
    floor = floor_number(text)
    if floor is None:
        return None
    m = re.search(r"floor.*?" + MARKER + r".*?(\d{1,2})\s*/\s*(\d{1,2})", text, re.I | re.S)
    if m:
        return Result(floor, m[1].lower(), int(m[2]), int(m[3]))
    m = re.search(r"floor.*?(\d{1,2})\s*/\s*(\d{1,2})", text, re.I | re.S)
    return Result(floor, None, int(m[1]), int(m[2])) if m else None


def floors_passed(result):
    return result.floor if result.cleared == result.total else result.floor - 1


def claim_ok(result):
    """Floor 5 passed: the Claim is the game's to give, however far the run went after it (spec 03 section 14).

    Live 2026-10-16: a HARD floor may have 7 nodes (`Floor 5 [HARD] 7/7`), so the total is read, not assumed 6.
    """
    return floors_passed(result) >= 5


def target_reached(floors, target):
    """Whether a run that passed `floors` floors reached its target_floor (5, 10 or 15); only such a run toggles weekly bonuses."""
    return floors >= target


def claim_bonuses(result, target, use, amount, left, floors_hard, read_first):
    """How many weekly-bonus toggles go ON for a claimed run: none short of the target, none when the marker did not read."""
    if not target_reached(floors_passed(result), target) or result.difficulty is None:
        return 0
    return bonus_toggles(use, amount, result.hard, left, all_hard(floors_hard, result.floor, result.hard, read_first))


def first_floor_hard(text):
    """Whether the Exploration Reward window's floor 1 tile reads `[HARD] Floor1` (Dungeon Progress, left of the dialog)."""
    return re.search(r"floor1(?!\d)", compact(text)) is not None and has(text, "HARD")


def all_hard(floors_hard, floor, hard, read_first):
    """Whether every floor 1..floor was HARD, for a run that gets more than one weekly bonus (#382).

    floors_hard: the difficulty the theme pack page showed for each floor this agent saw. With floor 1 among them they
    say it all. A run picked up after a restart lacks the first floors; a run never goes back to NORMAL, so the window's
    last floor HARD (hard) and its floor 1 tile marked [HARD] (read_first(): the tile's text) make them all HARD. An
    unreadable tile is not HARD.
    """
    if 1 in floors_hard:
        return floor >= 1 and all(floors_hard.get(f) for f in range(1, floor + 1))
    return bool(hard) and first_floor_hard(read_first())


def bonus_toggles(use, amount, hard, left, all_hard):
    """How many weekly-bonus toggles go ON for a run that reached its target_floor.

    A run counts as hard when any floor was HARD; the window's last floor shows it, as a run never
    goes back to NORMAL. More than one bonus at once needs every floor HARD (in-game help page).
    """
    if use == "none" or use != ("hard" if hard else "normal"):
        return 0
    want = 1 if amount == "one" or not all_hard else 3
    return min(want, left)


def claim_dialog(text):
    """Which of the Exploration Reward window's confirm dialogs the text is, or None.

    giveup: GiveUpRewards' `End expedition without claiming rewards?`; no_bonus: Claim with bonuses left
    and none ON, or `Claim the rewards?` when none are left (live 2026-10-17); bonus: Claim with toggles
    ON, `Spend your 「Weekly Bonuses」 to claim the bonus rewards?`.
    """
    if has(text, "without claiming"):
        return "giveup"
    if has(text, "without using", "Claim the rewards"):
        return "no_bonus"
    if has(text, "Spend your"):
        return "bonus"
    return None


def counts_as_run(result):
    """Only a claimed run counts toward the run count; a given-up or stopped one does not."""
    return result == "clear"


# Settings that forfeit every run (min_alive above the deployment order's sinners left alive, or above its length) forfeit each one; used-up wipe retries are bad
# luck, which #34's acceptance expects up to 4 times in 14 runs. Two in a row may be luck, three hardly (#560).
FORFEITS_IN_A_ROW = 3


def forfeits_stop(forfeits):
    """Why no new run starts after the runs given up in a row since the last claim, or None.

    forfeits: each run's forfeit reason, None when the agent did not see it (a run picked up after a restart).
    """
    if len(forfeits) < FORFEITS_IN_A_ROW:
        return None
    return f"{len(forfeits)} runs in a row forfeited" + (f" ({forfeits[-1]})" if forfeits[-1] else "")


CLAIM_COST = 5  # the Enkephalin Modules one Claim takes (Claim, spec 03 section 14)


BACKS = 2  # back presses at the entry page to reach a page with the Modules panel, before the run starts unchecked
NOT_SEEN = object()


def new_run_gate(seen, backs):
    """What PlanRun does before it opens a new run (#369): "go", "done" or "back".

    seen: the Modules the panel showed on this trip's Drive page (OpenDrive), None when it did not read, NOT_SEEN when
    the trip did not pass a page with the panel (the last run's Claim took 5, so an old value is no use). Not seen: "back"
    to the Drive page, up to BACKS times, then "go" unchecked; an unread panel never blocks the run.
    """
    if seen is NOT_SEEN:
        return "back" if backs < BACKS else "go"
    return "go" if seen is None or seen >= CLAIM_COST else "done"


def runs_done(done, limit):
    """Whether the run count is reached: limit None (the switch off) means no limit (spec 04 section 5)."""
    return limit is not None and done >= limit


def now():
    """UTC ISO time with milliseconds, the format of the GUI's reset markers (JS toISOString)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def append_run(root, line):
    """Append one run to <root>/logs/runs.jsonl (spec 06, 執行記錄)."""
    path = Path(root) / "logs" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
