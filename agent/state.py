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


def next_cursor(teams, finished_id):
    """Cursor after the bot saw team finished_id complete a run and claim the reward: the next enabled team.

    None when finished_id is not an enabled team in the settings; the caller then leaves the cursor alone.
    """
    order = _from_cursor(teams, finished_id)
    if not order or order[0]["id"] != finished_id:
        return None
    return order[1 % len(order)]["id"]
