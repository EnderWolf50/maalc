"""Seconds each test file takes on a CI runner, summed from the agent shards' junit XML. tests/conftest.py balances the
shards with tests/shard_seconds.json.

    python tools/shard_seconds.py check <junit.xml>...   fails when the table no longer matches these reports, one per
                                                         shard: a file off by more than RATIO both as measured and at
                                                         its shard's runner pace
    python tools/shard_seconds.py update --run <run id>  rewrites the table from the junit artifacts of that CI run and
                                                         of the EARLIER_RUNS before it whose agent shards all passed:
                                                         each file's median, or that run's own time when it is off from
                                                         the median by more than RATIO both as measured and at its
                                                         shard's runner pace
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tests" / "shard_seconds.json"
# A file faster than this cannot unbalance a shard on its own; conftest counts an unlisted one 0.15 s a test.
SLOW = 30
RATIO = 2
# Whole seconds round a file of PACE_MIN_SECONDS by 10 % at most; with PACE_MIN_FILES one changed file cannot set the
# median.
PACE_MIN_SECONDS = 5
PACE_MIN_FILES = 3
# CI runs before the one update names whose times the median takes too: one runner's speed is not the table's (#463).
EARLIER_RUNS = 4
# How many completed CI runs update looks back through for them: about four weeks; junit artifacts are kept 14 days.
LISTED_RUNS = 200


def measured(reports):
    seconds = {}
    for report in reports:
        for case in ET.parse(report).iter("testcase"):
            module = next((p for p in case.get("classname", "").split(".") if p.startswith("test_")), None)
            if module:
                seconds[module + ".py"] = seconds.get(module + ".py", 0.0) + float(case.get("time") or 0)
    return seconds


def pace(table, shard):
    ratios = [took / table[name] for name, took in shard.items() if table.get(name, 0) >= PACE_MIN_SECONDS]
    return statistics.median(ratios) if len(ratios) >= PACE_MIN_FILES else 1


def within_ratio(took, listed, runner_pace):
    return any(listed * p / RATIO <= took <= listed * p * RATIO for p in (1, runner_pace))


def stale(table, shard):
    problems = []
    runner_pace = pace(table, shard)
    for name, took in sorted(shard.items()):
        listed = table.get(name)
        if listed is None:
            if took >= SLOW:
                problems.append(f"{name} took {took:.0f} s and is not in the table")
        elif max(took, listed) >= SLOW and not within_ratio(took, listed, runner_pace):
            problems.append(f"{name} took {took:.0f} s, the table says {listed} (its shard's pace x{runner_pace:.2f})")
    return problems


def unmeasured(seconds):
    return sorted(p.name for p in (ROOT / "tests").glob("test_*.py") if p.name not in seconds)


def download(run, folder):
    subprocess.run(["gh", "run", "download", str(run), "--pattern", "junit-*", "--dir", folder], check=True)


def check(reports):
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    problems = [problem for report in reports for problem in stale(table, measured([report]))]
    problems += [f"{name} has no time in this run's reports" for name in unmeasured(measured(reports))]
    if not problems:
        print(f"tests/shard_seconds.json matches this run ({len(reports)} reports)")
        return 0
    run = os.environ.get("GITHUB_RUN_ID", "<run id>")
    fix = f"uv run python tools/shard_seconds.py update --run {run}, then commit tests/shard_seconds.json"
    for problem in problems:
        print(f"::error title=tests/shard_seconds.json is stale::{problem}. {fix}")
    return 1


def gh_json(*args):
    return json.loads(subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout)


def earlier(run):
    """The completed CI runs before run, newest first."""
    listed = gh_json("run", "list", "--workflow", "ci.yml", "--status", "completed", "--limit", str(LISTED_RUNS),
                     "--json", "databaseId")
    return [r["databaseId"] for r in listed if r["databaseId"] < int(run)]


def agents_passed(run):
    """Every agent shard of run passed: none failed, was cancelled or cut short, and the run did not skip them (docs only)."""
    agents = [j for j in gh_json("run", "view", str(run), "--json", "jobs")["jobs"] if j["name"].split(" (")[0] == "agent"]
    return bool(agents) and all(j["conclusion"] == "success" for j in agents)


def reports_of(run, folder):
    """An earlier run's junit reports, downloaded into folder; none when its artifacts expired."""
    try:
        download(run, folder)
    except subprocess.CalledProcessError:
        return []
    return sorted(Path(folder).rglob("*.xml"))


def median_table(shards, others):
    """check takes the pace from the table, so each shard's pace is taken again from what is written until no file
    changes: the run passes the check."""
    table = {}
    for shard in shards:
        written = {name: round(statistics.median([took] + [other[name] for other in others if name in other]))
                   for name, took in shard.items()}
        while True:
            runner_pace = pace(written, shard)
            changed = {name: round(took) for name, took in shard.items()
                       if round(took) != written[name] and not within_ratio(took, written[name], runner_pace)}
            if not changed:
                break
            written |= changed
        table |= written
    return dict(sorted(table.items()))


def update(run):
    with tempfile.TemporaryDirectory() as folder:
        download(run, folder)
        reports = sorted(Path(folder).rglob("*.xml"))
        seconds = measured(reports)
        shards = [measured([report]) for report in reports]
    if missing := unmeasured(seconds):
        print(f"run {run} has no time for {', '.join(missing)}: a shard was cut short; use a run whose shards all passed")
        return 1
    others = {}
    for other in earlier(run):
        if len(others) == EARLIER_RUNS:
            break
        if agents_passed(other):
            with tempfile.TemporaryDirectory() as folder:
                if found := reports_of(other, folder):
                    others[other] = measured(found)
    TABLE.write_text(json.dumps(median_table(shards, list(others.values())), indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(seconds)} files to tests/shard_seconds.json, the median of run {run} and {len(others)} before it"
          f" ({', '.join(map(str, others)) or 'none'})")
    if len(others) < EARLIER_RUNS:
        print(f"only {len(others)} earlier CI runs (of the last {LISTED_RUNS} completed) had every agent shard pass with its"
              " junit kept: a slow or fast runner can still set the table")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check").add_argument("reports", nargs="+", type=Path)
    commands.add_parser("update").add_argument("--run", required=True)
    args = parser.parse_args()
    return check(args.reports) if args.command == "check" else update(args.run)


if __name__ == "__main__":
    sys.exit(main())
