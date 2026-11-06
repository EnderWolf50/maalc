"""Seconds each test file takes on a CI runner, summed from the agent shards' junit XML. tests/conftest.py balances the
shards with tests/shard_seconds.json.

    python tools/shard_seconds.py check <junit.xml>...   fails when the table no longer matches these reports
    python tools/shard_seconds.py update --run <run id>  rewrites the table from that CI run's junit artifacts and the
                                                         EARLIER runs before it (each file's median, #463)
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
# Runner speed varies from run to run; a file off by more than this factor changed, not the runner.
RATIO = 2
# CI runs before the one update names whose times the median takes too: one runner's speed is not the table's (#463).
EARLIER = 4


def measured(reports):
    seconds = {}
    for report in reports:
        for case in ET.parse(report).iter("testcase"):
            module = next((p for p in case.get("classname", "").split(".") if p.startswith("test_")), None)
            if module:
                seconds[module + ".py"] = seconds.get(module + ".py", 0.0) + float(case.get("time") or 0)
    return seconds


def stale(table, seconds):
    problems = []
    for name, took in sorted(seconds.items()):
        listed = table.get(name)
        if listed is None:
            if took >= SLOW:
                problems.append(f"{name} took {took:.0f} s and is not in the table")
        elif max(took, listed) >= SLOW and not listed / RATIO <= took <= listed * RATIO:
            problems.append(f"{name} took {took:.0f} s, the table says {listed}")
    return problems


def unmeasured(seconds):
    return sorted(p.name for p in (ROOT / "tests").glob("test_*.py") if p.name not in seconds)


def download(run, folder):
    subprocess.run(["gh", "run", "download", str(run), "--pattern", "junit-*", "--dir", folder], check=True)


def check(reports):
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    seconds = measured(reports)
    problems = stale(table, seconds) + [f"{name} has no time in this run's reports" for name in unmeasured(seconds)]
    if not problems:
        print(f"tests/shard_seconds.json matches this run ({len(reports)} reports)")
        return 0
    run = os.environ.get("GITHUB_RUN_ID", "<run id>")
    fix = f"uv run python tools/shard_seconds.py update --run {run}, then commit tests/shard_seconds.json"
    for problem in problems:
        print(f"::error title=tests/shard_seconds.json is stale::{problem}. {fix}")
    return 1


def earlier(run):
    """The completed CI runs before run, newest first."""
    listed = subprocess.run(["gh", "run", "list", "--workflow", "ci.yml", "--status", "completed", "--limit", "50",
                             "--json", "databaseId"], capture_output=True, text=True, check=True).stdout
    return [r["databaseId"] for r in json.loads(listed) if r["databaseId"] < int(run)]


def reports_of(run, folder):
    """An earlier run's junit reports, downloaded into folder; none when it has none (a docs-only run, or expired)."""
    try:
        download(run, folder)
    except subprocess.CalledProcessError:
        return []
    return sorted(Path(folder).rglob("*.xml"))


def pick(seconds, others):
    """The table from a run's seconds and earlier runs' (#463): each file's median, or the run's own time when that is off
    from the median by more than RATIO (the file changed, not the runner). Either way the run passes the check."""
    table = {}
    for name, took in sorted(seconds.items()):
        median = round(statistics.median([took] + [other[name] for other in others if name in other]))
        table[name] = median if median / RATIO <= took <= median * RATIO else round(took)
    return table


def update(run):
    with tempfile.TemporaryDirectory() as folder:
        download(run, folder)
        reports = sorted(Path(folder).rglob("*.xml"))
        seconds = measured(reports)
    if missing := unmeasured(seconds):
        print(f"run {run} has no time for {', '.join(missing)}: a shard was cut short; use a run whose shards all passed")
        return 1
    others = {}
    for other in earlier(run):
        if len(others) == EARLIER:
            break
        with tempfile.TemporaryDirectory() as folder:
            found = reports_of(other, folder)
            if len(found) == len(reports):  # a report from every shard: none was cut short
                others[other] = measured(found)
    TABLE.write_text(json.dumps(pick(seconds, list(others.values())), indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(seconds)} files to tests/shard_seconds.json, the median of run {run} and {len(others)} before it"
          f" ({', '.join(map(str, others)) or 'none'})")
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
