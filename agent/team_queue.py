"""The team queue (ADR 0011, docs/spec/03-decisions.md section 1): the order of `teams` in the settings file.

A new run plays the first enabled team whose usage fits its difficulty. Once the bot saw that team claim, the team moves
to the end of the list (requeue): the one write the agent makes to the settings file.
"""

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path

from settings import settings_path

USAGE_FITS = {"any": {"hard", "normal"}, "hard_only": {"hard"}, "normal_only": {"normal"}}


def pick_team(teams, difficulty):
    """First enabled team in queue order whose usage fits difficulty ("hard"/"normal"); None ends the task.

    Skipped teams keep their place.
    """
    return next((t for t in teams if t["enabled"] and difficulty in USAGE_FITS[t["usage"]]), None)


def resumed_team(teams, difficulty):
    """The team of a run under way that this agent did not plan (a restart, a paused run picked up), and whether it is
    known (#436).

    No screen shows the team after the team page, so it comes from the queue, which only a claim changes: a run the bot
    began plays pick_team for the difficulty it began on. difficulty None: that is not known (auto), and the team is
    known only when every difficulty a run could begin on picks it. The run is played by the first pick (hard before
    normal); when no team fits, by the first enabled team, so a team comes back whenever one is enabled.
    """
    difficulties = [difficulty] if difficulty else ["hard", "normal"]
    fits = [t for t in (pick_team(teams, d) for d in difficulties) if t]
    team = fits[0] if fits else next(t for t in teams if t["enabled"])
    return team, len({t["id"] for t in fits}) == 1


def requeue(root, team_id):
    """After the bot saw team team_id complete a run and claim: move it to the end of the queue (pop and append).

    The file is read again, as the GUI may have saved since the run began; nothing but the order of `teams` changes.
    Returns a line for the log.
    """
    try:
        data = json.loads(settings_path(root).read_text(encoding="utf-8"))
        teams = data["teams"]
        i = next((i for i, t in enumerate(teams) if t["id"] == team_id), None)
        if i is None:
            return f"team queue: {team_id!r} is no longer in the settings, the queue stays"
        if i == len(teams) - 1:
            return f"team queue: {team_id!r} is already last"
        teams.append(teams.pop(i))
        write_settings(root, data)
    except (OSError, ValueError, LookupError, TypeError) as e:
        return f"team queue not written ({e!r}): {team_id!r} keeps its place"
    return f"team queue: {team_id!r} to the end, next {teams[0]['id']!r}"


def migrate_cursor(root, address):
    """#501: the rotation cursor of the state files before the queue (<root>/state/<adb address>.json, {"cursor": id})
    becomes the queue head, once. The list turns at this instance's cursor, so the enabled teams run in the order the
    cursor would have run them; a cursor that no enabled team has changes nothing, as it started from the first one.
    Then every state file goes, other instances' too: one queue serves them all. With no usable settings file the state
    files stay for the next start.

    Returns a line for the log, None when there is nothing to migrate.
    """
    folder = Path(root) / "state"
    files = sorted(folder.glob("*.json"))
    if not files:
        return None
    try:
        cursor = json.loads((folder / (re.sub(r'[<>:"/\\|?*]', "_", address) + ".json")).read_text(encoding="utf-8"))["cursor"]
    except (OSError, ValueError, LookupError, TypeError):
        cursor = None
    try:
        data = json.loads(settings_path(root).read_text(encoding="utf-8"))
        teams = data["teams"]
        i = next((i for i, t in enumerate(teams) if t["id"] == cursor and t["enabled"]), 0)
        if i:
            data["teams"] = teams[i:] + teams[:i]
            write_settings(root, data)
    except (OSError, ValueError, LookupError, TypeError) as e:
        return f"rotation cursor not migrated ({e!r}): the state files stay"
    for f in files:
        f.unlink()
    with contextlib.suppress(OSError):
        folder.rmdir()
    return f"rotation cursor {cursor!r} migrated ({'now the queue head' if i else 'the queue stays'}), state files removed"


def write_settings(root, data):
    """In the GUI's format (gui/src/App.tsx toText), via a temp file in the same folder and os.replace, so a crash never
    leaves half a file."""
    path = settings_path(root)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
