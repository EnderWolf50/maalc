"""Mechanical checks for findings reviewers caught by hand : the tree as it stands."""
import ast
import re
from pathlib import Path

import pytest
import shard_seconds
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


def ci_jobs():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]



def test_every_ci_job_has_a_timeout_and_pytest_a_default():
    jobs = ci_jobs()
    assert [name for name, job in jobs.items() if "timeout-minutes" not in job] == []
    assert "timeout = " in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_ci_ok_does_not_wait_for_shard_balance_and_pipeline_runs_for_bot_files_only():
    # #628: shard-balance reports only; pipeline (maa-tools) runs when the changes job saw a file the bot reads.
    jobs = ci_jobs()
    assert "shard-balance" not in jobs["ci-ok"]["needs"] and "pipeline" in jobs["ci-ok"]["needs"]
    assert jobs["pipeline"]["if"] == "needs.changes.outputs.bot == 'true'"
    assert "bot" in jobs["changes"]["outputs"]
    step = next(s for s in jobs["changes"]["steps"] if s.get("id") == "botfilter")
    assert "predicate-quantifier" not in step["with"]  # `every` would need one file to match all of them
    bot = yaml.safe_load(step["with"]["filters"])["bot"]
    assert {"assets/**", "agent/**", "tests/screens/**", "maatools.config.mts"} <= set(bot)  # imageRoot of maa-tools test
    assert not any(p.startswith("docs") for p in bot)


def test_the_test_jobs_run_on_windows_and_shard_seconds_reads_their_runner():
    # #636: the bot runs on Windows only, so the jobs that test it do too; the shard table's earlier runs must be the same
    # runner's, or a Linux time sets a Windows shard.
    jobs = ci_jobs()
    assert {name: jobs[name]["runs-on"] for name in ("agent", "pipeline", "gui")} == dict.fromkeys(
        ("agent", "pipeline", "gui"), "windows-latest")
    assert shard_seconds.RUNNER == jobs["agent"]["runs-on"]
    # Windows' default shell is pwsh, which has no python3
    runs = [step["run"] for name in ("agent", "pipeline") for step in jobs[name]["steps"] if "run" in step]
    assert not [run for run in runs if "python3" in run]


def test_a_test_reads_a_pure_logic_module_directly_not_through_a_page_module():
    # #676: `event_actions.shop.fuse_slots` is `shop.fuse_slots` under a longer name that says the page owns it, and
    # so is `settle_actions.has` for `ocrtext.has`. A page module's own names (shop_actions.FUSE_CELLS) are fine.
    modules = {p.stem for p in (ROOT / "agent").glob("*.py")}
    pages = {m for m in modules if m == "actions" or m.endswith("_actions")}
    pure = modules - pages - {"main"}
    through = {}  # page -> the pure modules and the names of them that it imports
    for page in pages:
        body = ast.parse((ROOT / "agent" / f"{page}.py").read_text(encoding="utf-8")).body
        through[page] = {a.name for n in body if isinstance(n, ast.Import) for a in n.names if a.name in pure} | {
            a.asname or a.name for n in body if isinstance(n, ast.ImportFrom) and n.module in pure for a in n.names}
    reads = [f"{path.relative_to(ROOT)}:{n.lineno}: {n.value.id}.{n.attr}"
             for folder in ("tests", "tools") for path in sorted((ROOT / folder).rglob("*.py"))
             for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.attr in through.get(n.value.id, ())]
    assert reads == []
