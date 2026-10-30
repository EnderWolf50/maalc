"""Mechanical checks for findings reviewers caught by hand : the tree as it stands."""
import ast
import re
from pathlib import Path

import pytest
import yaml

from test_pipeline import PIPELINE, load_nodes

ROOT = Path(__file__).resolve().parent.parent
IMAGES = PIPELINE.parent / "image"
CODE_DIRS = ("agent", "tools")  # Python: module-level names

# A template whose file name does not start with its node's name, and is not shared by several nodes. Each is kept;
# renaming the file is a change of its own.
RENAMED = {("LuxThreadLevel", "Luxcavation/LuxLevelSelect.png"), ("PopupButton", "Screen/DialogButtonParchment.png")}


def templates(nodes):
    """(node, template path) of every template a node lists, inline sub-recognitions included."""
    found = []

    def walk(node, spec):
        if isinstance(spec, dict):
            tpl = spec.get("template")
            found.extend((node, t) for t in ([tpl] if isinstance(tpl, str) else tpl or []))
            for v in spec.values():
                walk(node, v)
        elif isinstance(spec, list):
            for v in spec:
                walk(node, v)

    for name, spec in nodes.items():
        walk(name, spec)
    return found


def test_a_template_is_named_after_its_node_or_shared():
    refs = templates(load_nodes())
    users = {}
    for node, tpl in refs:
        users.setdefault(tpl, set()).add(node)
    odd = [(n, t) for n, t in refs if not Path(t).stem.startswith(n) and len(users[t]) == 1 and (n, t) not in RENAMED]
    assert not odd, f"rename the file after its node, or the node after its file: {odd}"
    assert all((IMAGES / t).is_file() for _, t in refs)
    assert all(users[t] for _, t in RENAMED)  # an entry whose file is no longer used goes out of RENAMED


def test_a_task_hub_lists_its_stuck_node_first():
    nodes = load_nodes()
    hubs = [n for n in nodes if n.endswith("Hub")]
    assert hubs
    for hub in hubs:
        first = re.sub(r"^(\[\w+\])+", "", nodes[hub]["next"][0])
        stuck = "Stuck" if hub == "MirrorHub" else hub[:-len("Hub")] + "Stuck"  # the mirror's is the unprefixed one
        assert first == stuck and stuck in nodes, hub


def module_names(path):
    names = {}
    for st in ast.parse(path.read_text(encoding="utf-8")).body:
        targets = st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, ast.AnnAssign) else []
        for t in targets:
            if isinstance(t, ast.Name):
                names.setdefault(t.id, []).append(st.lineno)
    return names


@pytest.mark.parametrize("path", sorted(p for d in CODE_DIRS for p in (ROOT / d).glob("*.py")), ids=lambda p: p.name)
def test_no_module_constant_is_defined_twice(path):
    # ruff F811 covers functions and imports, not an assignment: the later one wins unseen (PORTRAIT_Y tapped y 655).
    twice = {n: lines for n, lines in module_names(path).items() if len(lines) > 1 and n != "__all__"}
    assert not twice, twice


def test_every_ci_job_has_a_timeout_and_pytest_a_default():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
    assert [name for name, job in jobs.items() if "timeout-minutes" not in job] == []
    assert "timeout = " in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
