"""What a client sends with a task (#776, #779): the override array tools/client_override.py builds from
assets/interface.json as MXU does, and the attach MaaFramework then gives each node. The MaaFramework tests post the
array (daily_child.py); the in-process tests hand an entry action a fake context that answers get_node_data with the
attach (send)."""

import sys
from pathlib import Path
from unittest.mock import DEFAULT

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))  # a child process (daily_child.py) has agent/ only on its path

import client_override

# The global options at their defaults, as the options line at a task's start shows them (task_options.line, #779).
GLOBAL_DEFAULTS = "webhook_url (not set), auto_accept_terms=true, auto_download=true, keep_dismissed_screens=true"


def interface():
    """assets/interface.json with its imports, as a client loads it."""
    return client_override.load_interface(ROOT / "assets" / "interface.json")


def override(task, *pairs):
    """The override array a client posts task with: these NAME=VALUE options set, every other option its default."""
    pi = interface()
    return client_override.build(pi, task, client_override.parse_options(pi, list(pairs)))[1]


def attach(array):
    """Each node's attach once MaaFramework applied array entry by entry (a later entry wins a key)."""
    nodes = {}
    for entry in array:
        for name, node in entry.items():
            nodes.setdefault(name, {}).update(node.get("attach", {}))
    return nodes


def send(context, task, *pairs, drop=()):
    """context (a MagicMock) answers get_node_data as MaaFramework does with task posted by a client with these
    options: the attach of the nodes the array writes, without the keys in drop (a value the client did not send). Any
    other node gets the mock's own answer."""
    nodes = attach(override(task, *pairs))
    for values in nodes.values():
        for key in drop:
            values.pop(key, None)
    answer(context, nodes)


def send_defaults(context):
    """send for every task of the interface at once, each with its defaults: an entry action of any task reads them."""
    nodes = {}
    for task in interface()["task"]:
        for name, values in attach(override(task["name"])).items():
            nodes.setdefault(name, {}).update(values)
    answer(context, nodes)


def answer(context, nodes):
    """context's get_node_data gives each node of nodes its attach, any other node the mock's own answer."""
    context.get_node_data.side_effect = lambda name: {"attach": nodes[name]} if name in nodes else DEFAULT
