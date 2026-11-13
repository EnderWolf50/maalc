"""agent_patch.patch_all and rebind (#676): a test sets a name of the agent's actions modules in every module of the
family that binds it, so a page module split off actions.py (`from actions import tap`) calls the fake too. The checks
run on a stand-in family in a child process (this file run as a script), whose `actions` is the stand-in's; and the guard
fails on a test or tool that still sets such a name on one module directly.
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

import pytest
from daily_child import run_child

ROOT = Path(__file__).resolve().parent.parent

# The stand-in family: actions imports load_settings from another agent file (settings), page_actions binds actions'
# names as a split-off page module does, other_actions holds a tap of its own; moved is a name only page_actions has,
# twice one that two page modules define apart.
FAMILY = {
    "settings.py": 'load_settings = "settings.load_settings"\n',
    "actions.py": 'from settings import load_settings  # noqa: F401\n\ntap = "actions.tap"\nROOT = "actions.ROOT"\n',
    "page_actions.py": 'from actions import ROOT, load_settings, tap  # noqa: F401\n\nmoved = "page_actions.moved"\n'
                       'twice = "page_actions.twice"\n',
    "other_actions.py": 'tap = "other_actions.tap"\ntwice = "other_actions.twice"\n',
}
MODULES = ["actions", "page_actions", "other_actions", "settings"]


def child():
    """Print what each stand-in module binds after each step, and the errors of the names patch_all cannot set."""
    folder = Path(tempfile.mkdtemp())
    for name, text in FAMILY.items():
        (folder / name).write_text(text, encoding="utf-8")
    sys.path.insert(0, str(folder))
    from agent_patch import patch_all, rebind

    def names(name):
        return {m: getattr(sys.modules[m], name, None) for m in MODULES if m in sys.modules}

    out = {"error": None}
    monkeypatch = pytest.MonkeyPatch()
    patch_all(monkeypatch, "tap", "fake")
    patch_all(monkeypatch, "load_settings", "fake")
    patch_all(monkeypatch, "moved", "fake")
    out["patched"] = {name: names(name) for name in ("tap", "load_settings", "moved")}
    monkeypatch.undo()
    out["undone"] = {name: names(name) for name in ("tap", "load_settings", "moved")}
    rebind("ROOT", "fake")
    for name in ("nowhere", "twice"):
        try:
            patch_all(monkeypatch, name, "fake")
            out[name] = None
        except AttributeError as e:
            out[name] = str(e)
    monkeypatch.undo()
    out["rebound"] = names("ROOT")
    print(json.dumps(out))


def test_patch_all_sets_the_name_in_every_actions_module_that_binds_it():
    assert run_child(__file__)["patched"]["tap"] == {
        "actions": "fake", "page_actions": "fake", "other_actions": "other_actions.tap", "settings": None}


def test_patch_all_leaves_the_file_that_defines_an_imported_name():
    # actions imports load_settings from settings.py: patching it there too would reach callers the patch never did
    assert run_child(__file__)["patched"]["load_settings"] == {
        "actions": "fake", "page_actions": "fake", "other_actions": None, "settings": "settings.load_settings"}


def test_patch_all_finds_a_name_only_a_page_module_binds():
    assert run_child(__file__)["patched"]["moved"]["page_actions"] == "fake"


def test_monkeypatch_undoes_patch_all_in_every_module():
    assert run_child(__file__)["undone"] == {
        "tap": {"actions": "actions.tap", "page_actions": "actions.tap", "other_actions": "other_actions.tap", "settings": None},
        "load_settings": {"actions": "settings.load_settings", "page_actions": "settings.load_settings",
                          "other_actions": None, "settings": "settings.load_settings"},
        "moved": {"actions": None, "page_actions": "page_actions.moved", "other_actions": None, "settings": None}}


def test_rebind_sets_the_name_in_every_actions_module_and_stays():
    # a MaaFramework child's ROOT: nothing undoes it, the monkeypatch.undo() after it included
    assert run_child(__file__)["rebound"] == {"actions": "fake", "page_actions": "fake", "other_actions": None, "settings": None}


def test_patch_all_fails_on_a_name_no_actions_module_binds():
    assert "'nowhere'" in run_child(__file__)["nowhere"]


def test_patch_all_fails_on_a_name_two_page_modules_bind_apart():
    # actions has no twice, page_actions and other_actions each define one: which one the test drives is not known
    assert "'twice'" in run_child(__file__)["twice"]


def direct_sets(source, modules):
    """Line numbers of source where a name is set on one of modules directly: a setattr or delattr call (builtin, or a
    method such as monkeypatch's) on the module or on a "module.name" string, and an assignment to or del of module.name.
    Setting an attribute of an object a module holds (actions.time, actions.TASK["done"]) is not one: every module that
    binds the object sees it."""

    def on_module(node):
        return isinstance(node, ast.Name) and node.id in modules

    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args and \
                (isinstance(node.func, ast.Name) and node.func.id in ("setattr", "delattr")
                 or isinstance(node.func, ast.Attribute) and node.func.attr in ("setattr", "delattr")):
            first = node.args[0]
            dotted = isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.split(".")[0] in modules
            if on_module(first) or dotted:
                lines.append(node.lineno)
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            lines += [node.lineno for t in targets for e in ast.walk(t) if isinstance(e, ast.Attribute) and on_module(e.value)
                      and isinstance(e.ctx, (ast.Store, ast.Del))]
    return sorted(set(lines))


@pytest.mark.parametrize("line", [
    'monkeypatch.setattr(actions, "tap", fake)', 'actions.ROOT = folder', 'setattr(actions, "tap", fake)',
    'monkeypatch.setattr("actions.tap", fake)', 'monkeypatch.delattr(actions, "tap")', 'del actions.tap',
    'actions.LOGS += 1', 'actions.time = clock = SleptClock()', 'lux_actions.consecutive_now = read'])
def test_the_guard_finds_a_name_set_on_an_actions_module(line):
    assert direct_sets(line, {"actions", "lux_actions"}) == [1]


@pytest.mark.parametrize("line", [
    'patch_all(monkeypatch, "tap", fake)', 'rebind("ROOT", folder)', 'monkeypatch.setattr(actions.time, "sleep", fake)',
    'actions.TASK["done"] = None', 'actions.RUN.team = {}', 'test_actions.FUSING = {}', 'monkeypatch.setattr(game, "tap", fake)'])
def test_the_guard_passes_patch_all_and_an_object_a_module_holds(line):
    assert direct_sets(line, {"actions", "lux_actions"}) == []


def test_no_test_or_tool_sets_a_name_on_an_actions_module_directly():
    # monkeypatch.setattr(actions, ...) and actions.<name> = ... miss a page module's own binding: use patch_all, rebind
    modules = {"actions", *(p.stem for p in (ROOT / "agent").glob("*_actions.py"))}
    found = [f"{path.relative_to(ROOT).as_posix()}:{n}" for folder in ("tests", "tools") for path in sorted((ROOT / folder).rglob("*.py"))
             for n in direct_sets(path.read_text(encoding="utf-8"), modules)]
    assert not found, "set these through agent_patch.patch_all or rebind: " + ", ".join(found)


if __name__ == "__main__":
    child()
