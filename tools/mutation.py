"""Mutation testing of the decision modules under agent/ (#634).

Each mutant is one small change to one module (`<` to `<=`, `and` to `or`, a number plus one, a call deleted, ...),
made on the parsed tree in the pytest process that tests it: `tools/mutation_plugin.py` swaps the module's code for
the mutated tree when the tests import it, so no file on disk is ever changed and the main checkout stays clean. A
mutant is killed when its module's tests fail, survived when they pass, timeout when they run past three times the
unmutated run (and 10 s). The method, the choices and the results: docs/research/mutation-testing.md.

    uv run python tools/mutation.py list                # mutants per module, no test run
    uv run python tools/mutation.py baseline            # each module's tests, unmutated: they pass, and how long
    uv run python tools/mutation.py run --budget 840    # mutants not yet in the results, for 14 minutes at most
    uv run python tools/mutation.py cover               # which test runs which line, each test file unmutated
    uv run python tools/mutation.py recheck --budget 840  # each survivor on every test that runs its line
    uv run python tools/mutation.py report              # the per-module table and the survivors, as Markdown

`run` and `recheck` are resumable: they append to `.local/scratch/mutation/results.jsonl` of the main checkout and skip
the mutants already there for the module's current source, so a long sweep runs as several short bench tickets:

    uv run python tools/live/queue.py run --resource bench --name mutation-<n> -- uv run python tools/mutation.py run --budget 840
"""

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from local_dir import local_dir

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agent"

# Module -> the first run's tests: the files that import it directly, less test_actions.py (46 s, it reaches the module
# through actions.py), test_gift_cells.py (105 s) and test_shop_skill_screens.py, test_frozen_home.py and test_title.py
# (each runs a MaaFramework child). A survivor is then run again on every test file that runs its line (`recheck`,
# from `cover`). A module's tests also reach the modules it imports; a mutant counts only for the module it changes.
MODULES = {
    "settlement": ["test_settlement.py"],
    "rewards": ["test_rewards.py", "test_trials.py", "test_trial_screens.py"],
    "battle": ["test_battle.py"],
    "run_start": ["test_run_start.py", "test_pack_cover.py"],
    "recovery": ["test_recovery.py", "test_battle.py", "test_dismiss_shots.py", "test_task_chain.py"],
    "gift_search": ["test_gift_search.py"],
    "shop": ["test_shop.py", "test_shop_skill.py"],
    "map_route": ["test_map_route.py"],
    "gifts": ["test_gifts.py", "test_shop_buy.py", "test_trials.py"],
    "gift_cells": ["test_run_start.py"],
    "team_queue": ["test_team_queue.py"],
    "lunacy": ["test_lunacy.py"],
    "luxcavation": ["test_luxcavation.py"],
    "ocrtext": ["test_ocrtext.py", "test_run_start.py"],
    "pack_cover": ["test_pack_cover.py"],
    "settings": ["test_settings.py", "test_shop_buy.py", "test_team_queue.py"],
    "hub_text": ["test_hub_text.py"],
    "pass_missions": ["test_pass_missions.py"],
}
# tools/mutation_plugin.py skips every test that runs a MaaFramework child and leaves out the ones that compare tables
# with this machine's unpacked game data. actions.py and main.py are left out of the sweep (the doc says why).

COMPARE = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
           ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
BINARY = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult, ast.FloorDiv: ast.Div,
          ast.Mod: ast.FloorDiv, ast.BitOr: ast.BitAnd, ast.BitAnd: ast.BitOr, ast.Pow: ast.Mult}
SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in",
          ast.NotIn: "not in", ast.Is: "is", ast.IsNot: "is not", ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
          ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.BitOr: "|", ast.BitAnd: "&", ast.Pow: "**",
          ast.And: "and", ast.Or: "or"}


def skipped_nodes(tree):
    """Nodes no mutant touches: annotations, f-strings, docstrings and the `if __name__ == "__main__":` block."""
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            roots += [node.returns] + [a.annotation for a in ast.walk(node.args) if isinstance(a, ast.arg)]
        elif isinstance(node, ast.AnnAssign):
            roots.append(node.annotation)
        elif isinstance(node, ast.JoinedStr):
            roots.append(node)
        elif isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            roots.append(node)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                roots.append(first)
    return {id(n) for root in roots if root is not None for n in ast.walk(root)}


def replace(parent, old, new):
    """Put `new` where `old` sits among `parent`'s fields."""
    for field, value in ast.iter_fields(parent):
        if value is old:
            setattr(parent, field, new)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if item is old:
                    value[i] = new


def points(tree):
    """Every mutation of the tree, in a fixed order: (apply, line, col, what). `apply()` changes the tree."""
    skip = skipped_nodes(tree)
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    out = []

    def add(node, apply, what):
        out.append((apply, node.lineno, node.col_offset, what))

    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in COMPARE:
                    new = COMPARE[type(op)]
                    add(node, lambda n=node, i=i, new=new: n.ops.__setitem__(i, new()),
                        f"`{SYMBOL[type(op)]}` -> `{SYMBOL[new]}`")
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in BINARY:
            new = BINARY[type(node.op)]
            eq = "=" if isinstance(node, ast.AugAssign) else ""
            add(node, lambda n=node, new=new: setattr(n, "op", new()), f"`{SYMBOL[type(node.op)]}{eq}` -> `{SYMBOL[new]}{eq}`")
        elif isinstance(node, ast.BoolOp):
            new = ast.Or if isinstance(node.op, ast.And) else ast.And
            add(node, lambda n=node, new=new: setattr(n, "op", new()), f"`{SYMBOL[type(node.op)]}` -> `{SYMBOL[new]}`")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub)):
            add(node, lambda n=node: replace(parents[id(n)], n, n.operand),
                "`not x` -> `x`" if isinstance(node.op, ast.Not) else "`-x` -> `x`")
        elif isinstance(node, ast.Constant) and type(node.value) is bool:
            add(node, lambda n=node: setattr(n, "value", not n.value), f"`{node.value}` -> `{not node.value}`")
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            add(node, lambda n=node: setattr(n, "value", n.value + 1), f"`{node.value!r}` -> `{node.value + 1!r}`")
        elif isinstance(node, ast.If):
            add(node, lambda n=node: setattr(n, "test", ast.UnaryOp(ast.Not(), n.test)), "`if c:` -> `if not c:`")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            add(node, lambda n=node: setattr(n, "value", ast.Constant(None)), "call deleted")
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            add(node, lambda n=node: setattr(n, "value", ast.Constant(None)), "`return x` -> `return None`")
        elif isinstance(node, (ast.Break, ast.Continue)):
            other = ast.Continue if isinstance(node, ast.Break) else ast.Break
            add(node, lambda n=node, other=other: setattr(n, "__class__", other),
                "`break` -> `continue`" if isinstance(node, ast.Break) else "`continue` -> `break`")
    return out


def source(module):
    return (AGENT / f"{module}.py").read_text(encoding="utf-8")


def digest(module):
    return hashlib.sha256(source(module).encode("utf-8")).hexdigest()[:12]


def mutant(module, index):
    """The module's tree with its `index`-th mutation applied, and that mutation's (line, col, what)."""
    tree = ast.parse(source(module))
    apply, line, col, what = points(tree)[index]
    apply()
    ast.fix_missing_locations(tree)
    return tree, (line, col, what)


def pytest_command(module, files=None):
    files = [str(ROOT / "tests" / f) for f in files or MODULES[module]]
    return [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider",
            "-p", "mutation_plugin", *files]


def plugin_env(**extra):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "tools"), str(AGENT)]))
    for name in ("MAALC_MUTANT", "MAALC_COVER", "MAALC_TESTS"):
        env.pop(name, None)
    return {**env, **extra}


def run_tests(module, index=None, timeout=None, files=None, only=None):
    """(status, seconds) of the module's tests (or `files`, and of them the ids listed in the file `only`), on the
    mutant `index`: killed, survived, timeout or error; unmutated (index None): passed or error."""
    env = plugin_env(**({"MAALC_MUTANT": f"{module}:{index}"} if index is not None else {}),
                     **({"MAALC_TESTS": str(only)} if only else {}))
    start = time.monotonic()
    try:
        proc = subprocess.run(pytest_command(module, files), cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", time.monotonic() - start
    seconds = time.monotonic() - start
    if proc.returncode == 0:
        return ("survived" if index is not None else "passed"), seconds
    if proc.returncode in (1, 2) and index is not None:
        return "killed", seconds
    tail = proc.stdout.decode("utf-8", "replace")[-600:]
    return f"error {proc.returncode}: {tail}", seconds


def results_path():
    return local_dir("scratch", "mutation") / "results.jsonl"


def read_results():
    """The rows written so far; a last line a killed run left half written is skipped (its mutant runs again)."""
    path = results_path()
    if not path.exists():
        return []
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def done_keys(rows, phase=None):
    """The mutants a run of `phase` need not run again: those with a result that is not an error."""
    return {(r["module"], r["digest"], r["index"]) for r in rows
            if r.get("phase") == phase and not r["status"].startswith("error")}


def count(module):
    return len(points(ast.parse(source(module))))


def sweep(jobs, one, workers, start, budget):
    """Run one(job) on `workers` threads, append each row to the results as it ends, and return how many of each status
    ran. A job starting after `budget` seconds from `start` returns None and is left for the next run."""
    counts = {}

    def timed(job):
        return None if time.monotonic() - start > budget else one(job)

    with ThreadPoolExecutor(workers) as pool, results_path().open("a", encoding="utf-8") as out:
        for future in as_completed([pool.submit(timed, job) for job in jobs]):
            row = future.result()
            if row is None:
                continue
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            status = row["status"].split()[0]
            counts[status] = counts.get(status, 0) + 1
    return counts


def report_sweep(what, todo, counts, start):
    left = len(todo) - sum(counts.values())
    print(f"{what} {sum(counts.values())} in {time.monotonic() - start:.0f} s: {counts}; {left} left", flush=True)


def cmd_list(args):
    for module in args.modules or MODULES:
        print(f"{module}: {count(module)} mutants")


def baseline_path():
    return local_dir("scratch", "mutation") / "baseline.json"


def baselines(modules):
    """Each module's tests run unmutated, kept in baseline.json by module: {status, seconds, digest}."""
    path = baseline_path()
    base = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for module in modules:
        status, seconds = run_tests(module)
        base[module] = {"status": status.split()[0], "seconds": round(seconds, 1), "digest": digest(module)}
        print(f"{module}: {status} in {seconds:.1f} s", flush=True)
    path.write_text(json.dumps(base, indent=1), encoding="utf-8")
    return base


def cmd_baseline(args):
    base = baselines(args.modules or MODULES)
    return 0 if all(base[m]["status"] == "passed" for m in args.modules or MODULES) else 1


def cmd_run(args):
    """Run the mutants not in the results yet, `workers` at a time, until none is left or `budget` seconds pass. A
    module whose tests fail unmutated is left out: each of its mutants would count as killed."""
    start = time.monotonic()
    path = baseline_path()
    base = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    done = done_keys(read_results())
    todo = []
    for module in args.modules or MODULES:
        d = digest(module)
        if not isinstance(base.get(module), dict) or base[module]["digest"] != d:
            base = baselines([module])
        if base[module]["status"] != "passed":
            print(f"{module}: left out, its tests do not pass unmutated", flush=True)
            continue
        todo += [(module, d, i) for i in range(count(module)) if (module, d, i) not in done]
    print(f"{len(todo)} mutants to run", flush=True)

    def one(job):
        module, d, i = job
        status, seconds = run_tests(module, i, timeout=base[module]["seconds"] * 3 + 10)
        _, (line, col, what) = mutant(module, i)
        return {"module": module, "digest": d, "index": i, "line": line, "col": col, "what": what,
                "status": status, "seconds": round(seconds, 1)}

    report_sweep("ran", todo, sweep(todo, one, args.workers, start, args.budget), start)
    return 0


def cover_path():
    return local_dir("scratch", "mutation") / "cover.json"


def cmd_cover(args):
    """Which lines of the swept modules each test file runs, and how long it takes: the recheck's test choice."""
    out_dir = local_dir("scratch", "mutation", "cover")
    files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py") if p.name != "test_mutation.py")

    def one(name):
        out = out_dir / f"{name}.json"
        out.unlink(missing_ok=True)
        start = time.monotonic()
        cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-p", "mutation_plugin",
               str(ROOT / "tests" / name)]
        try:
            code = subprocess.run(cmd, cwd=ROOT, env=plugin_env(MAALC_COVER=str(out)), capture_output=True,
                                  timeout=600).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
        seconds = time.monotonic() - start
        found = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"lines": {}, "seconds": {}}
        print(f"{name}: exit {code}, {seconds:.1f} s, {sum(map(len, found['lines'].values()))} lines", flush=True)
        return name, {"exit": code, "seconds": round(seconds, 1), **found}

    with ThreadPoolExecutor(args.workers) as pool:
        found = dict(pool.map(one, files))
    cover_path().write_text(json.dumps(found), encoding="utf-8")
    return 0


def loaded_lines(module, line):
    """The lines of `module` that read a name a statement on `line` sets: where a module-level constant is used."""
    tree = ast.parse(source(module))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
             and n.lineno == line}
    return {n.lineno for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id in names} | {n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in names}


def wide_tests(cover, module, line):
    """The tests (ids, from files that pass unmutated) that run `line` of `module`. A line only imports run (a module
    constant) takes the tests that run a line reading what it sets."""
    def tests(lines):
        return {t for c in cover.values() if c["exit"] == 0 for n in lines
                for t in c["lines"].get(module, {}).get(str(n), ()) if t != "(import)"}
    return sorted(tests([line]) or tests(loaded_lines(module, line)))


def wide_seconds(cover, ids):
    return sum(c["seconds"].get(t, 0) for c in cover.values() for t in ids)


def cmd_recheck(args):
    """Each survivor again, on every test file that runs its line (cover): killed there, survived, or not reached."""
    start = time.monotonic()
    cover = json.loads(cover_path().read_text(encoding="utf-8"))
    rows = read_results()
    done = done_keys(rows, "wide")
    todo = [r for r in rows if r.get("phase") is None and r["status"] == "survived" and r["module"] in MODULES
            and r["digest"] == digest(r["module"]) and (r["module"], r["digest"], r["index"]) not in done
            and (not args.modules or r["module"] in args.modules)]
    print(f"{len(todo)} survivors to recheck", flush=True)
    ids_dir = local_dir("scratch", "mutation", "ids")

    def one(r):
        ids = wide_tests(cover, r["module"], r["line"])
        if not ids:
            return {**r, "phase": "wide", "status": "unreached", "seconds": 0.0, "tests": 0}
        listed = ids_dir / f"{r['module']}-{r['index']}.txt"
        listed.write_text("\n".join(ids), encoding="utf-8")
        files = sorted({t.split("::")[0].removeprefix("tests/") for t in ids})
        timeout = wide_seconds(cover, ids) * 3 + 30 + 5 * len(files)  # and each file's collection
        status, seconds = run_tests(r["module"], r["index"], timeout=timeout, files=files, only=listed)
        return {**r, "phase": "wide", "status": status, "seconds": round(seconds, 1), "tests": len(ids)}

    report_sweep("rechecked", todo, sweep(todo, one, args.workers, start, args.budget), start)
    return 0


EQUIVALENT = ROOT / "docs" / "research" / "mutation-equivalent.json"
KINDS = ["killed", "wide", "timeout", "survived", "unreached", "equivalent", "error"]


def equivalent_key(r):
    return f"{r['module']}:{r['line']}:{r['col']}:{r['what']}"


def final_rows():
    """Each mutant of the current sources by its last row: a recheck's (phase "wide") over the first run's."""
    rows = {}
    for r in read_results():
        if r["module"] in MODULES and r["digest"] == digest(r["module"]):
            rows[(r["module"], r["index"])] = r
    return rows


def kind(r, equivalent):
    status = r["status"].split()[0]
    if status == "killed" and r.get("phase") == "wide":
        return "wide"
    if status in ("survived", "unreached") and equivalent_key(r) in equivalent:
        return "equivalent"
    return status


def cmd_report(args):
    """The per-module table, the survivors and the equivalent mutants of the current sources, as Markdown.

    A survivor listed in docs/research/mutation-equivalent.json ({"module:line:col:what": "why it changes nothing"})
    counts as equivalent.
    """
    equivalent = json.loads(EQUIVALENT.read_text(encoding="utf-8")) if EQUIVALENT.exists() else {}
    rows = final_rows()
    lines = ["| module | mutants | killed | killed by wider tests | timeout | survived | unreached | equivalent | error "
             "| not run | score |", "|---|" + "---|" * 10]
    survivors, equivalents = [], []
    for module in args.modules or MODULES:
        total = count(module)
        mine = sorted((r for (m, _), r in rows.items() if m == module), key=lambda r: (r["line"], r["col"], r["index"]))
        text = source(module).splitlines()
        n = dict.fromkeys(KINDS, 0)
        for r in mine:
            k = kind(r, equivalent)
            n[k] += 1
            where = f"`agent/{module}.py:{r['line']}`"
            if k == "equivalent":
                equivalents.append(f"| {where} | {r['what']} | {equivalent[equivalent_key(r)]} |")
            elif k in ("survived", "unreached"):
                tests = ("none runs it" if k == "unreached" else
                         f"{r['tests']} tests" if "tests" in r else f"{len(MODULES[module])} files")
                code = text[r["line"] - 1].strip()[:90].replace("|", "\\|")
                survivors.append(f"| {where} | {r['what']} | {tests} | `{code}` |")
        caught = n["killed"] + n["wide"] + n["timeout"]
        scored = caught + n["survived"] + n["unreached"]
        score = f"{100 * caught / scored:.0f}%" if scored else "-"
        lines.append(f"| {module} | {total} | " + " | ".join(str(n[k]) for k in KINDS) + f" | {total - len(mine)} | {score} |")
    print("\n".join(lines))
    print("\nscore = (killed + killed by wider tests + timeout) / (those + survived + unreached); equivalent and error "
          "mutants are left out.\n")
    print("| where | mutation | tests run | line |\n|---|---|---|---|")
    print("\n".join(survivors))
    print("\n| where | mutation | why it changes nothing |\n|---|---|---|")
    print("\n".join(equivalents))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    commands = {"list": cmd_list, "baseline": cmd_baseline, "run": cmd_run, "cover": cmd_cover,
                "recheck": cmd_recheck, "report": cmd_report}
    for name in commands:
        p = sub.add_parser(name)
        p.add_argument("modules", nargs="*", help=f"some of: {' '.join(MODULES)} (default all)")
        if name in ("run", "recheck"):
            p.add_argument("--budget", type=float, default=840, help="seconds after which no new mutant starts")
        if name in ("run", "recheck", "cover"):
            p.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if unknown := set(args.modules) - set(MODULES):
        parser.error(f"not in the sweep: {' '.join(sorted(unknown))}")
    return commands[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
