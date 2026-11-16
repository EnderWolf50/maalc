"""A task's options (#776, #777, #779, #781): the values its entry action (TaskStart, and LuxStart and ChargeStart built on it)
reads once, before any tap, and keeps in actions.TASK["options"]; every reader takes them from there.

The client sends them (MXU, MFAAvalonia; ADR 0013). Each option of interface.json writes its key into attach of the
task's entry node, a global option into attach of GlobalOptions, a node no next names; MaaFramework applies the client's
override array entry by entry and merges attach key by key, so the entry action reads them with context.get_node_data.
read checks both against task_options.schema.json; a value missing or wrong ends the task before any tap, with a line
that names the option. There is no settings-file fallback. A Luxcavation task's team is its option too (ExpTeam,
ThreadTeam: the cases of the team options file the settings GUI writes, #780).

The rules that cross a task's options with the teams (MirrorDungeon's target floor, a Luxcavation task's team) are
checked here too, at the task's start: the teams stay in the settings file."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from settings import SettingsError

SCHEMA = json.loads((Path(__file__).parent / "task_options.schema.json").read_text(encoding="utf-8"))
GLOBAL_NODE = "GlobalOptions"  # assets/resource/base/pipeline/options.json
GLOBAL = tuple(SCHEMA["$defs"][GLOBAL_NODE]["properties"])  # what every task reads: the webhook, the title's dialogs, the kept screens
# Where the user changes a node's options, for the line that names one.
WHERE = {GLOBAL_NODE: "the client's global options (MXU: Settings; MFAAvalonia: the global options item of the task list)"}
SECRET = {"webhook_url"}  # the options line says only whether it is set


class OptionsError(SettingsError):
    """What the task cannot run on among its options: a SettingsError, which every reader already stops on."""
    WHAT = "task options"


def nodes(task):
    """The nodes whose attach task (its entry node's name) reads: GlobalOptions, and its own when the schema has it."""
    return [GLOBAL_NODE, *([task] if task in SCHEMA["$defs"] else [])]


def where(node):
    """Where the user changes node's options, as a line that names one says it."""
    return WHERE.get(node, f"the options of the {node} task in the client's task list")


def check(node, values):
    """The errors of values, node's attach, against the schema's node, in its properties' order: each names the option
    (its title), what came and where to change it."""
    schema = SCHEMA["$defs"][node]
    place = where(node)
    found = {}
    for e in Draft202012Validator(schema).iter_errors(values):
        if not e.absolute_path and e.validator != "required":  # the attach itself, not one of its keys
            return [f"{node}'s attach: {e.message}; {place}"]
        if e.validator == "required":  # one error per missing key, all naming the whole list
            found.update({k: "not sent" for k in e.validator_value if k not in e.instance})
        else:
            found.setdefault(e.absolute_path[0], e.message)
    return [f"{schema['properties'][k]['title']} ({k}): {found[k]}; set it in {place}"
            for k in schema["properties"] if k in found]


def sent(context, node):
    """node's attach as MaaFramework's context has it: what the client sent over the bundle's own."""
    return (context.get_node_data(node) or {}).get("attach") or {}


def read(context, task):
    """task's options as the client sent them: the attach of nodes(task) (sent), the schema's keys only. OptionsError
    names each option that is missing or wrong."""
    values, errors = {}, []
    for node in nodes(task):
        got = sent(context, node)
        errors += check(node, got)
        values.update({k: got[k] for k in SCHEMA["$defs"][node]["properties"] if k in got})
    if errors:
        raise OptionsError(errors)
    return values


def line(values):
    """The options line a task's start logs: each value read, in the schema's order; a secret only set or not set."""
    shown = [f"{k} ({'set' if values[k] else 'not set'})" if k in SECRET
             else f"{k}={v if isinstance(v := values[k], str) else json.dumps(v)}" for k in values]
    return "options: " + ", ".join(shown)


def options(task, values):
    """The options of task as its readers take them, from read's values: MirrorDungeon's runs is the run cap, None for
    no limit (runs_limited false), as settlement.runs_done takes it."""
    if task != "MirrorDungeon":
        return dict(values)
    out = {k: v for k, v in values.items() if k not in ("runs_limited", "runs")}
    return {**out, "runs": values["runs"] if values["runs_limited"] else None}


def target_floor_errors(options, teams):
    """MirrorDungeon's rule (#385): a target floor past 5 needs the whole run HARD, so the difficulty is not normal and
    every enabled team (the rotation picks from them) plays HARD from floor 1 and is not normal_only. Floors 6+ open only
    when every floor of the run was HARD. The errors name the option or the team's settings path to change."""
    target_floor = options["target_floor"]
    if target_floor <= 5:
        return []
    errors = []
    need = f"but MirrorTargetFloor {target_floor} needs the whole run HARD"
    if options["difficulty"] == "normal":
        errors.append(f"MirrorDifficulty (difficulty): 'normal', {need}")
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


def team_errors(node, team, teams):
    """A Luxcavation task's rule (#366, #780): its team option (node's team: ExpTeam, ThreadTeam), an id, names one of
    teams, enabled or not. None, not sent: 「未選擇」 picked, or a list with no team (no team options file yet, or a
    client not reopened since the settings GUI wrote it). An id not in teams: a team deleted in the settings GUI, whose
    case the file keeps, so the client still sends it (#780)."""
    option = f"{SCHEMA['$defs'][node]['properties']['team']['title']} (team)"
    if team is None:
        return [f"{option}: no team picked; pick one in {where(node)} (an empty list: create the team in the settings "
                "GUI, save, then reopen the client)"]
    if team not in {t["id"] for t in teams}:
        return [f"{option}: team {team!r} was deleted in the settings GUI; pick another in {where(node)}"]
    return []
