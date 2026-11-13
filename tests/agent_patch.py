"""Setting a name of the agent's actions modules in a test (#676): `actions` and every `agent/*_actions.py` page module
split off it. A page module that does `from actions import tap` holds a binding of its own, so a fake set on
actions.tap alone is never called by it, and a test that asserts no tap still passes. patch_all and rebind set the name
in every actions module that binds the same object.

Only these modules: a name actions imports from another agent file (load_settings from settings.py, pick_team) stays
as it is in the file that defines it, as monkeypatch.setattr(actions, ...) left it. tests/test_agent_patch.py fails on
a test or tool that sets a name on one of them directly.
"""

import importlib
from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent / "agent"


def actions_module_names(folder=AGENT):
    """"actions" and the name of every page module in folder (a *_actions.py), without importing them."""
    return ["actions", *(p.stem for p in sorted(folder.glob("*_actions.py")))]


def actions_modules():
    """actions, then every page module beside it, each imported: one imported while a patch is on would bind the fake
    for good (`from actions import tap`)."""
    import actions  # here, not at the top: a MaaFramework child imports this file before its stand-in AgentServer

    return [actions, *map(importlib.import_module, actions_module_names(Path(actions.__file__).parent)[1:])]


def modules_binding(name):
    """The actions modules that bind name to one object: the one actions binds, or, when actions has no name, the one
    the page modules bind. AttributeError when no module binds it, as monkeypatch.setattr raises, or when page modules
    bind different objects and actions none.

    The same object is `is`: a page module's own None, True or small int under a name actions binds to the same value
    counts as actions' too."""
    modules = actions_modules()
    bound = [m for m in modules if name in vars(m)]
    if not bound:
        raise AttributeError(f"no actions module binds {name!r}")
    target = vars(bound[0])[name]
    if bound[0] is not modules[0] and any(vars(m)[name] is not target for m in bound):
        raise AttributeError(f"{', '.join(m.__name__ for m in bound)} bind different objects as {name!r}")
    return [m for m in bound if vars(m)[name] is target]


def patch_all(monkeypatch, name, value):
    """monkeypatch.setattr(module, name, value) on every module of modules_binding(name); monkeypatch undoes each."""
    for module in modules_binding(name):
        monkeypatch.setattr(module, name, value)


def rebind(name, value):
    """patch_all for a MaaFramework child, which nothing undoes: name is value in every module of modules_binding(name)."""
    for module in modules_binding(name):
        setattr(module, name, value)
