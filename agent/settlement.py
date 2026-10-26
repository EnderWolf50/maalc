"""Settlement decisions, free of MaaFramework (docs/spec/03-decisions.md sections 1, 14).

actions.py reads the Exploration Reward window and taps; everything here is plain data in, plain data out.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ocrtext import has


def read_result(text):
    """(floor, hard, cleared, total) from the window's result, e.g. "Floor 5 [NORMAL] 6/6"; None when unreadable."""
    m = re.search(r"Floor\s*(\d).*?\[?\s*(HARD|NORMAL)\s*\]?.*?(\d)\s*/\s*(\d)", text, re.I | re.S)
    if not m:
        return None
    return int(m[1]), m[2].upper() == "HARD", int(m[3]), int(m[4])


def goal_met(result):
    """The goal is all five floors: Floor 5 with every node cleared (spec 03 section 14).

    Live 2026-10-16: a HARD floor may have 7 nodes (`Floor 5 [HARD] 7/7`), so the total is read, not assumed 6.
    """
    floor, _, cleared, total = result
    return floor == 5 and cleared == total


def floors_passed(result):
    floor, _, cleared, total = result
    return floor if cleared == total else floor - 1


def bonus_toggles(use, amount, hard, left, all_hard):
    """How many weekly-bonus toggles go ON for a run that met the goal.

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


CLAIM_COST = 5  # the Enkephalin Modules one Claim takes (Claim, spec 03 section 14)


def can_claim(modules):
    """A new run may start: the Modules cover one Claim. An unread panel (None) does not block it (#369)."""
    return modules is None or modules >= CLAIM_COST


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
