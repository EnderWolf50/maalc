"""tools/split_actions.py (#676): a page module's names move out of agent/actions.py as they are, with the imports
their code uses, and the tests and tools that read them through `actions` read the module; a table that does not fit
agent/actions.py writes nothing."""

import re
from collections import Counter
from pathlib import Path

import pytest

import split_actions
from split_actions import Misfit, Source, split

ROOT = Path(__file__).resolve().parent.parent

# A small agent: json, luxcavation and load_settings only the Luxcavation code reads, time and SettingsError only the
# code that stays, AgentServer both.
ACTIONS = '''"""The agent's actions."""

import json
import time

from maa.agent.agent_server import AgentServer

import luxcavation
from settings import SettingsError, load_settings

ROOT = "root"


def log(msg):
    print(msg)


# Luxcavation's cost a battle
LUX = {"exp": luxcavation.EXP_COST}


@AgentServer.custom_action("LuxStart")
class LuxStart:
    def run(self, context, argv):
        log(json.dumps(LUX))
        return load_settings(ROOT)
WAIT = 2


@AgentServer.custom_action("Halt")
class Halt:
    def run(self, context, argv):
        return [time.time() for _ in range(WAIT)] and SettingsError


def lux_wait():
    return WAIT
'''
TABLE = {"lux_actions": ("Luxcavation's pages.", ("LUX", "LuxStart", "lux_wait"))}
STAY = ("ROOT", "log", "WAIT", "Halt")
MAIN = '''from maa.agent.agent_server import AgentServer  # noqa: E402

import actions  # noqa: E402,F401  registers custom actions


def main():
    pass
'''
TEST = '''import actions


def test_lux():
    assert actions.LUX["exp"] == 3 and actions.ROOT == "root"


def child():
    actions, resource = load()
    return actions.LuxStart, actions.luxcavation, getattr(actions, "lux_wait")


def body(context, actions, out):
    """A probe: reads actions.LUX."""
    out["lux"] = actions.LUX


def test_lux_alone():
    import actions  # not at the top: as a child's
    assert actions.LUX
'''


def agent(tmp_path, actions=ACTIONS):
    for path, text in {"agent/actions.py": actions, "agent/main.py": MAIN, "tests/test_lux.py": TEST}.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    return tmp_path


def text(root, path):
    return (root / path).read_text(encoding="utf-8")


def test_the_module_takes_its_statements_and_the_imports_they_use(tmp_path):
    root = agent(tmp_path)

    report = split(root, "lux_actions", TABLE, STAY)

    assert report.moved == ["LUX", "LuxStart", "lux_wait"]
    assert text(root, "agent/lux_actions.py") == '''"""Luxcavation's pages."""

import json

from maa.agent.agent_server import AgentServer

import luxcavation
from actions import ROOT, WAIT, log
from settings import load_settings


# Luxcavation's cost a battle
LUX = {"exp": luxcavation.EXP_COST}


@AgentServer.custom_action("LuxStart")
class LuxStart:
    def run(self, context, argv):
        log(json.dumps(LUX))
        return load_settings(ROOT)


def lux_wait():
    return WAIT
'''


def test_actions_py_keeps_the_rest_and_the_imports_it_still_uses(tmp_path):
    root = agent(tmp_path)

    split(root, "lux_actions", TABLE, STAY)

    # WAIT sat right under LuxStart: it keeps the two blank lines LUX's comment had above it
    assert text(root, "agent/actions.py") == '''"""The agent's actions."""

import time

from maa.agent.agent_server import AgentServer

from settings import SettingsError

ROOT = "root"


def log(msg):
    print(msg)


WAIT = 2


@AgentServer.custom_action("Halt")
class Halt:
    def run(self, context, argv):
        return [time.time() for _ in range(WAIT)] and SettingsError
'''


def test_main_imports_the_module_after_actions(tmp_path):
    root = agent(tmp_path)

    split(root, "lux_actions", TABLE, STAY)

    assert "import actions  # noqa: E402,F401  registers custom actions\n" \
           "import lux_actions  # noqa: E402,F401  registers custom actions\n" in text(root, "agent/main.py")


def test_a_test_reads_a_moved_name_and_an_import_only_the_module_uses_through_the_module(tmp_path):
    # actions bound by the file's import, by an assignment in a function and as a parameter: import lux_actions follows;
    # an import of actions nothing reads any more becomes the import of lux_actions (ruff F401 fails an unused one)
    root = agent(tmp_path)

    report = split(root, "lux_actions", TABLE, STAY)

    assert text(root, "tests/test_lux.py") == '''import actions
import lux_actions


def test_lux():
    assert lux_actions.LUX["exp"] == 3 and actions.ROOT == "root"


def child():
    actions, resource = load()
    import lux_actions
    return lux_actions.LuxStart, lux_actions.luxcavation, getattr(actions, "lux_wait")


def body(context, actions, out):
    """A probe: reads actions.LUX."""
    import lux_actions
    out["lux"] = lux_actions.LUX


def test_lux_alone():
    import lux_actions  # not at the top: as a child's
    assert lux_actions.LUX
'''
    assert report.renamed == {"tests/test_lux.py": 5}


def test_a_string_lookup_and_a_mention_are_left_for_a_hand_edit(tmp_path):
    root = agent(tmp_path)

    report = split(root, "lux_actions", TABLE, STAY)

    # the line numbers of the file as the split leaves it
    assert [line.split(": ")[:2] for line in report.by_hand] == [["tests/test_lux.py:12", "getattr by a string"],
                                                                ["tests/test_lux.py:16", "still names it"]]


@pytest.mark.parametrize("change, problem", [
    (("def log(msg):", "def extra():\n    pass\n\n\ndef log(msg):"), "extra is not in the table"),
    (("return WAIT", "return ROOT and Halt"), "lux_wait (lux_actions) reads Halt of other_actions"),
    (("and SettingsError", "and LUX"), "Halt stays in actions.py and reads LUX, which goes to lux_actions"),
])
def test_a_table_that_does_not_fit_writes_nothing(tmp_path, change, problem):
    root = agent(tmp_path, ACTIONS.replace(*change))
    table = {**TABLE, "other_actions": ("Other pages.", ("Halt",))}

    with pytest.raises(Misfit, match=re.escape(problem)):
        split(root, "lux_actions", table, tuple(n for n in STAY if n != "Halt"))

    assert text(root, "agent/actions.py") == ACTIONS.replace(*change)
    assert not (root / "agent/lux_actions.py").exists() and text(root, "tests/test_lux.py") == TEST


def test_the_table_places_every_top_level_name_of_actions_py_once():
    # a name added to actions.py goes in the table, in the module of the code around it
    table = [n for _, names in split_actions.MODULES.values() for n in names] + list(split_actions.STAY)
    _, statements = split_actions.statements(Source((ROOT / "agent/actions.py").read_text(encoding="utf-8")))
    assert [n for n, k in Counter(table).items() if k > 1] == []
    assert [n for s in statements for n in s.names if n not in table] == []


def test_the_pilot_module_fits_actions_py():
    # #676 PR 4 splits lux_actions first: nothing it moves reads another page module, nothing staying reads it
    src = Source((ROOT / "agent/actions.py").read_text(encoding="utf-8"))
    assert split_actions.plan(src, "lux_actions")[3] == []
