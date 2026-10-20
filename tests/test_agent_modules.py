"""Guards for splitting agent/actions.py into modules: every custom action and recognition the pipeline names is still
registered by importing main.py, and no agent module hits an import cycle when imported on its own.

Both run in fresh interpreters: the pytest process has already imported actions under the real AgentServer.
"""

import json
import subprocess
import sys
from pathlib import Path

from test_pipeline import load_nodes

AGENT = Path(__file__).resolve().parent.parent / "agent"
TIMEOUT = 300  # a hung import fails its test instead of stalling the whole run

# A recording AgentServer in place of MaaFramework's, as test_map_shop.py does; main.py's import registers the names.
REGISTER_SCRIPT = """
import json, sys, types
names = {"action": [], "recognition": []}
def record(kind):
    return staticmethod(lambda name: lambda c: names[kind].append(name) or c)
stub = types.ModuleType("maa.agent.agent_server")
stub.AgentServer = type("AgentServer", (), {"custom_action": record("action"),
                                            "custom_recognition": record("recognition")})
sys.modules["maa.agent"] = types.ModuleType("maa.agent")
sys.modules["maa.agent.agent_server"] = stub
import main
print(json.dumps(names))
"""


def pipeline_names():
    """{"action": [...], "recognition": [...]}: every custom name a pipeline node uses, in any nesting (v1 or v2)."""
    names = {"action": set(), "recognition": set()}

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("custom_action", "custom_recognition") and isinstance(item, str):
                    names[key.removeprefix("custom_")].add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(load_nodes())
    return {kind: sorted(found) for kind, found in names.items()}


def test_main_registers_every_custom_name_the_pipeline_uses_once():
    r = subprocess.run([sys.executable, "-c", REGISTER_SCRIPT], cwd=AGENT, capture_output=True, text=True,
                       encoding="utf-8", timeout=TIMEOUT)
    assert r.returncode == 0, r.stderr
    registered = json.loads(r.stdout.splitlines()[-1])
    # sorted lists, not sets: a name two modules register shows up twice
    assert {kind: sorted(found) for kind, found in registered.items()} == pipeline_names()


def test_every_module_imports_on_its_own():
    # A from-import cycle only breaks when the cycle is entered at one particular module, so each gets its own
    # interpreter; they start together, as one at a time adds up to half a minute.
    runs = {p.stem: subprocess.Popen([sys.executable, "-c", f"import {p.stem}"], cwd=AGENT, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8") for p in sorted(AGENT.glob("*.py"))}
    last_error_line = {module: run.communicate(timeout=TIMEOUT)[1].strip().splitlines()[-1:]
                       for module, run in runs.items()}
    assert {module: line for module, line in last_error_line.items() if runs[module].returncode} == {}
