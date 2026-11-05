"""Seconds each test file takes on a CI runner, summed from the agent shards' junit XML. tests/conftest.py balances the
shards with tests/shard_seconds.json.

    python tools/shard_seconds.py check <junit.xml>...   fails when the table no longer matches these reports
    python tools/shard_seconds.py update --run <run id>  rewrites the table from that CI run's junit artifacts
"""

import argparse
import json
import os
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


def update(run):
    with tempfile.TemporaryDirectory() as folder:
        download(run, folder)
        seconds = measured(sorted(Path(folder).rglob("*.xml")))
    if missing := unmeasured(seconds):
        print(f"run {run} has no time for {', '.join(missing)}: a shard was cut short; use a run whose shards all passed")
        return 1
    TABLE.write_text(json.dumps({n: round(s) for n, s in sorted(seconds.items())}, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(seconds)} files to tests/shard_seconds.json, {sum(seconds.values()):.0f} s in all")
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
