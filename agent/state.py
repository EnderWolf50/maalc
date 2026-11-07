"""Agent state file and team rotation (docs/spec/03-decisions.md section 1, ADR 0003).

<root>/state/<controller address>.json holds only the rotation cursor: {"cursor": <team id>}.
"""

import json
import os
import re
import tempfile
from pathlib import Path

USAGE_FITS = {"any": {"hard", "normal"}, "hard_only": {"hard"}, "normal_only": {"normal"}}


def state_path(root, address):
    # "127.0.0.1:16384" -> "127.0.0.1_16384.json"; any character Windows forbids becomes "_".
    return Path(root) / "state" / (re.sub(r'[<>:"/\\|?*]', "_", address) + ".json")


def read_cursor(root, address):
    """The saved team id, or None when there is no usable state file (rotation then starts at the first team)."""
    try:
        cursor = json.loads(state_path(root, address).read_text(encoding="utf-8")).get("cursor")
    except (OSError, ValueError, AttributeError):
        return None
    return cursor if isinstance(cursor, str) else None


def write_cursor(root, address, team_id):
    """Write via a temp file in the same folder, then os.replace, so a crash never leaves half a file."""
    path = state_path(root, address)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"cursor": team_id}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _from_cursor(teams, cursor):
    """Enabled teams in rotation order, starting at the cursor, or at the first one if the cursor is stale."""
    enabled = [t for t in teams if t["enabled"]]
    start = next((i for i, t in enumerate(enabled) if t["id"] == cursor), 0)
    return enabled[start:] + enabled[:start]


def pick_team(teams, cursor, difficulty):
    """First enabled team from the cursor whose usage fits difficulty ("hard"/"normal"); None ends the task.

    Skipped teams do not move the cursor.
    """
    return next((t for t in _from_cursor(teams, cursor) if difficulty in USAGE_FITS[t["usage"]]), None)


def resumed_team(teams, cursor, difficulty):
    """The team of a run under way that this agent did not plan (a restart, a paused run picked up), and whether it is
    known (#436).

    No screen shows the team after the team page, so it comes from the cursor, which only a claim moves: a run the bot
    began plays pick_team for the difficulty it began on. difficulty None: that is not known (auto), and the team is
    known only when every difficulty a run could begin on picks it. The run is played by the first pick (hard before
    normal); when no team fits, by the cursor's own team, so a team comes back whenever one is enabled.
    """
    difficulties = [difficulty] if difficulty else ["hard", "normal"]
    fits = [t for t in (pick_team(teams, cursor, d) for d in difficulties) if t]
    team = fits[0] if fits else _from_cursor(teams, cursor)[0]
    return team, len({t["id"] for t in fits}) == 1


def next_cursor(teams, finished_id):
    """Cursor after the bot saw team finished_id complete a run and claim the reward: the next enabled team.

    None when finished_id is not an enabled team in the settings; the caller then leaves the cursor alone.
    """
    order = _from_cursor(teams, finished_id)
    if not order or order[0]["id"] != finished_id:
        return None
    return order[1 % len(order)]["id"]
