"""A task's options (#777, #813): the values its entry action (TaskStart, and LuxStart and ChargeStart built on it) reads
once, before any tap, and keeps in actions.TASK["options"]; every reader takes them from there.

They come from the settings file: run (MirrorDungeon's own and the four every task reads), luxcavation.<exp|thread> and
charge_enkephalin (ADR 0015). The settings' schema checks them when the file loads. The rules that cross them with the
teams (MirrorDungeon's target floor, a Luxcavation task's team) are checked here, at the task's start, so a team
deleted or disabled stops only the task that names it; MirrorDungeon's start team on such a team is ignored, not an
error (start_team_ignored)."""

import json

from reasons import Reason
from settings import SCHEMA, SettingsError

# The settings' run keys every task reads: the stop procedure's webhook, the title's two dialogs, the kept screens.
GLOBAL = ("webhook_url", "auto_accept_terms", "auto_download", "keep_dismissed_screens")
# The rest of run, in the schema's order: MirrorDungeon's own.
MIRROR = tuple(k for k in SCHEMA["properties"]["run"]["properties"] if k not in GLOBAL)
LUX_KEY = {"ExpLuxcavation": "exp", "ThreadLuxcavation": "thread"}  # each Luxcavation task's section under luxcavation
SECRET = {"webhook_url"}  # the options line says only whether it is set


class OptionsError(SettingsError):
    """A rule a task's options break against the teams: a SettingsError, which every reader already stops on."""
    WHAT = "task options"


def where(task):
    """Where the user changes task's options, as a line that names one says it."""
    return f"the options of the {task} task in the settings GUI's task list"


def read(settings, task):
    """task's options (its entry node's name) from settings: GLOBAL of run, then its own: MirrorDungeon's MIRROR of run,
    a Luxcavation task's luxcavation.<key>, ChargeEnkephalin's charge_enkephalin; a task with none of its own has GLOBAL
    alone (AssembleModules, ClaimMail, ClaimPassMissions)."""
    run = settings["run"]
    values = {k: run[k] for k in GLOBAL}
    if task == "MirrorDungeon":
        values.update({k: run[k] for k in MIRROR})
    elif task in LUX_KEY:
        values.update(settings["luxcavation"][LUX_KEY[task]])
    elif task == "ChargeEnkephalin":
        values.update(settings["charge_enkephalin"])
    return values


def line(values):
    """The options line a task's start logs: each value read, in read's order; a secret only set or not set."""
    shown = [f"{k} ({'set' if values[k] else 'not set'})" if k in SECRET
             else f"{k}={v if isinstance(v := values[k], str) else json.dumps(v)}" for k in values]
    return "options: " + ", ".join(shown)


def target_floor_errors(options, teams):
    """MirrorDungeon's rule (#385): a target floor past 5 needs the whole run HARD, so the difficulty is not normal and
    every enabled team (the rotation picks from them) plays HARD from floor 1 and is not normal_only. Floors 6+ open only
    when every floor of the run was HARD. The errors name the settings path to change."""
    target_floor = options["target_floor"]
    if target_floor <= 5:
        return []
    errors = []
    need = f"but run/target_floor {target_floor} needs the whole run HARD"
    if options["difficulty"] == "normal":
        errors.append(f"run/difficulty: 'normal', {need}")
    for i, t in enumerate(teams):
        if not t["enabled"]:
            continue
        if t["usage"] == "normal_only":
            errors.append(f"teams/{i}/usage: team {t['name']!r} is normal_only, {need}")
        if t["hard_from_floor"] is None:
            errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} never switches to HARD, {need} (hard_from_floor 1)")
        elif t["hard_from_floor"] != 1:
            errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} starts HARD at floor {t['hard_from_floor']}, {need} (hard_from_floor 1)")
    return errors


def start_team_ignored(team, teams):
    """MirrorDungeon's start team (#805): run.start_team, None for no flag in the team queue, names an enabled team of
    teams. A flag on a disabled team, or on an id not in teams (a team deleted in the settings GUI), has no effect: the
    task follows the queue as with no flag, and the flag stays in the file for the team enabled again (#878). The line
    for the log that says so, None for a flag that counts or no flag."""
    if team is None:
        return None
    found = next((t for t in teams if t["id"] == team), None)
    if found is None:
        return f"run/start_team: team {team!r} is no longer listed, the flag is ignored and the task follows the team queue"
    if not found["enabled"]:
        return (f"run/start_team: team {found['name']!r} (id {team!r}) is disabled, the flag is ignored and the task "
                "follows the team queue")
    return None


def team_errors(task, team, teams):
    """A Luxcavation task's rule (#366, #780): its team (luxcavation.<key>.team), an id, names one of teams, enabled or
    not. None: none picked yet. An id not in teams: a team deleted in the settings GUI."""
    path = f"luxcavation/{LUX_KEY[task]}/team"
    if team is None:
        return [Reason(f"{path}: no team picked; pick one in {where(task)}", "NoTeamPicked")]
    if team not in {t["id"] for t in teams}:
        return [Reason(f"{path}: team {team!r} was deleted in the settings GUI; pick another in {where(task)}", "TeamDeleted",
                       team=team)]
    return []
