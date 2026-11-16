"""What a client sends with a task (#776, #779): the override array tools/client_override.py builds from
assets/interface.json as MXU does, and the attach MaaFramework then gives each node. The MaaFramework tests post the
array (daily_child.py); the in-process tests hand an entry action a fake context that answers get_node_data with the
attach (send).

The interface is the one an install's client loads once the settings GUI wrote its team options file (#780) for the
teams of settings_cases.json's valid file: TEAM_OPTIONS in place of the config/team_options.json interface.json
imports, which the repo has no copy of. Its ExpTeam and ThreadTeam take a (Team a), b (Team b), gone (a team since
deleted) or none (「未選擇」, the default, which sends nothing); teams=None is a client that found no such file."""

import sys
from pathlib import Path
from unittest.mock import DEFAULT

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))  # a child process (daily_child.py) has agent/ only on its path

import client_override

# The team options file the settings GUI writes for settings_cases.json's valid teams, a team "gone" since deleted
# (gui/src/teamOptions.test.ts checks the GUI writes this).
TEAM_OPTIONS = ROOT / "tests" / "team_options.json"
TEAM_PICK = {"ExpLuxcavation": "ExpTeam", "ThreadLuxcavation": "ThreadTeam"}  # each Luxcavation task's team option
# The global options at their defaults, as the options line at a task's start shows them (task_options.line, #779).
GLOBAL_DEFAULTS = "webhook_url (not set), auto_accept_terms=true, auto_download=true, keep_dismissed_screens=true"


def interface(teams=TEAM_OPTIONS):
    """assets/interface.json with its imports, as a client loads it: teams the team options file it finds (None: none)."""
    pi = client_override.load_interface(ROOT / "assets" / "interface.json")
    return client_override.merge(pi, client_override.read_jsonc(teams)) if teams else pi


def posting(task, *pairs, teams=TEAM_OPTIONS):
    """(entry, override array) a client posts task with: these NAME=VALUE options set, every other option its default."""
    pi = interface(teams)
    return client_override.build(pi, task, client_override.parse_options(pi, list(pairs)))[:2]


def override(task, *pairs, teams=TEAM_OPTIONS):
    """The override array a client posts task with: these NAME=VALUE options set, every other option its default."""
    return posting(task, *pairs, teams=teams)[1]


def attach(array):
    """Each node's attach once MaaFramework applied array entry by entry (a later entry wins a key)."""
    nodes = {}
    for entry in array:
        for name, node in entry.items():
            nodes.setdefault(name, {}).update(node.get("attach", {}))
    return nodes


def send(context, task, *pairs, drop=(), teams=TEAM_OPTIONS):
    """context (a MagicMock) answers get_node_data as MaaFramework does with task posted by a client with these
    options: the attach of the nodes the array writes, without the keys in drop (a value the client did not send), and
    the task's entry node an empty one when no option writes it. Any other node gets the mock's own answer."""
    entry, array = posting(task, *pairs, teams=teams)
    nodes = {entry: {}, **attach(array)}
    for values in nodes.values():
        for key in drop:
            values.pop(key, None)
    answer(context, nodes)


def send_defaults(context):
    """send for every task of the interface at once, each with its defaults: an entry action of any task reads them."""
    nodes = {}
    for task in interface()["task"]:
        nodes.setdefault(task["entry"], {})
        for name, values in attach(override(task["name"])).items():
            nodes.setdefault(name, {}).update(values)
    answer(context, nodes)


def answer(context, nodes):
    """context's get_node_data gives each node of nodes its attach, any other node the mock's own answer."""
    context.get_node_data.side_effect = lambda name: {"attach": nodes[name]} if name in nodes else DEFAULT
