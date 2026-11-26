"""The team queue (ADR 0014, ADR 0016, docs/spec/03-decisions.md section 1): `team_queue` in the settings file, ids of
`teams` in the order they play, as the user put them in: a team may be in it more than once or not at all. The order of
`teams` is the team list's, the user's to arrange in the settings GUI; no pick looks at it.

A new run plays the first team of the queue whose usage fits its difficulty. Once the bot saw that team claim, its first
place in the queue, the one the pick took, moves to the end (requeue). That move is the one write the agent makes to the
settings file.
"""

import contextlib
import json
import re
from pathlib import Path

from settings import settings_path, write_settings

# The settings GUI marks the next run with its own copy (gui/src/model.ts nextRuns): tests/settings_cases.json
# next_run holds both to the same picks.
USAGE_FITS = {"any": {"hard", "normal"}, "hard_only": {"hard"}, "normal_only": {"normal"}}
UNUSABLE = (OSError, ValueError, LookupError, TypeError)  # a settings file missing, broken or of the wrong shape
QUEUE_VERSION = 22  # the first settings version with team_queue (#803): before it, the queue is the order of teams


def queued(settings):
    """The teams of settings (a version with team_queue) in queue order, a team once for each place it has."""
    by_id = {t["id"]: t for t in settings["teams"]}
    return [by_id[i] for i in settings["team_queue"]]


def pick_team(settings, difficulty):
    """First team in queue order whose usage fits difficulty ("hard"/"normal"); None ends the task.

    Skipped teams keep their place.
    """
    return next((t for t in queued(settings) if difficulty in USAGE_FITS[t["usage"]]), None)


def resumed_team(settings, difficulty):
    """The team of a run under way that this agent did not plan (a restart, a paused run picked up), and whether it is
    known (#436).

    No screen shows the team after the team page, so it comes from the queue, which only a claim changes: a run the bot
    began plays pick_team for the difficulty it began on. difficulty None: that is not known (auto), and the team is
    known only when every difficulty a run could begin on picks it. The run is played by the first pick (hard before
    normal); when no team fits, by the queue's first team, so a team comes back whenever the queue holds one. An
    empty queue is the caller's to refuse (load_settings need_team).
    """
    difficulties = [difficulty] if difficulty else ["hard", "normal"]
    fits = [t for t in (pick_team(settings, d) for d in difficulties) if t]
    team = fits[0] if fits else queued(settings)[0]
    return team, len({t["id"] for t in fits}) == 1


def requeue(root, team_id):
    """After the bot saw team team_id complete a run and claim: move its first place in the queue to the end. The pick
    takes a team by its first place (pick_team), so that is the one that played.

    Returns a line for the log.
    """
    gone = True

    def to_end(teams):
        nonlocal gone
        i = next((i for i, t in enumerate(teams) if t["id"] == team_id), None)
        gone = i is None
        if i is None or i == len(teams) - 1:
            return None
        return teams[:i] + teams[i + 1:] + [teams[i]]

    try:
        teams = _reorder(root, to_end)
    except UNUSABLE as e:
        return f"team queue not written ({e!r}): {team_id!r} keeps its place"
    if teams is None:
        return f"team queue: {team_id!r} is {'no longer in it' if gone else 'already last'}, the queue stays"
    return f"team queue: {team_id!r} to the end, next {teams[0]['id']!r}"


def migrate_cursor(root, address):
    """#501: the rotation cursor of the state files before the queue (<root>/state/<adb address>.json, {"cursor": id})
    becomes the queue head, once. The queue turns at this instance's cursor, so its teams run in the order the cursor
    would have run them; a cursor that no team of the queue has, or one disabled in a file older than version 24 (#954),
    changes nothing, as it started from the first one. Then every state file goes, other instances' too: one queue serves
    them all. With no usable settings file the state files stay for the next start.

    Returns a line for the log, None when there is nothing to migrate.
    """
    folder = Path(root) / "state"
    files = sorted(folder.glob("*.json"))
    if not files:
        return None
    try:
        cursor = json.loads(_cursor_file(folder, address).read_text(encoding="utf-8"))["cursor"]
    except UNUSABLE:
        cursor = None

    def turn(teams):
        i = next((i for i, t in enumerate(teams) if t["id"] == cursor and t.get("enabled", True)), 0)
        return teams[i:] + teams[:i] if i else None

    try:
        turned = _reorder(root, turn)
    except UNUSABLE as e:
        return f"rotation cursor not migrated ({e!r}): the state files stay"
    for f in files:
        f.unlink()
    with contextlib.suppress(OSError):
        folder.rmdir()
    return f"rotation cursor {cursor!r} migrated ({'now the queue head' if turned else 'the queue stays'}), state files removed"


def _cursor_file(folder, address):
    # "127.0.0.1:16384" -> "127.0.0.1_16384.json"; any character Windows forbids became "_".
    return folder / (re.sub(r'[<>:"/\\|?*]', "_", address) + ".json")


def _reorder(root, change):
    """change(teams in queue order) gives the new queue order, or None to leave the file alone; returns what was written,
    or None.

    The file is read now, not at the run's start, as the GUI may have saved since; nothing but the queue changes. A file
    the GUI has not written back is written at its own version: below version 22 its queue is the order of its teams, and
    a disabled team (below version 24) keeps its place (docs/spec/04-settings.md section 2). A file that changed between
    this read and the write (a GUI save) is read again (ADR 0011).
    """
    path = settings_path(root)
    for _ in range(3):
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        older = data["version"] < QUEUE_VERSION
        teams = change(data["teams"] if older else queued(data))
        if teams is None:
            return None
        if older:
            data["teams"] = teams
        else:
            data["team_queue"] = [t["id"] for t in teams]
        if write_settings(root, data, expected=text):
            return teams
    raise OSError(f"{path} kept changing under the write")
