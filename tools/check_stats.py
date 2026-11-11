"""Summarise the run log of tools/check.py (#633): how many runs, how many red, which tests went red, what changed between a
red run and the next green one on the same branch, and where the time goes.

  uv run python tools/check_stats.py                  the last 14 days of <main checkout>/.local/check-runs.jsonl
  uv run python tools/check_stats.py --days 30 --top 15
  uv run python tools/check_stats.py --since 2026-11-11 --log some.jsonl

A run is red when any step exited non-zero. Each red run followed by a green run of the same branch in the same worktree
(several reds in a row count once, from the last one) is put in one of three classes by the files that differ between the
two (check.py records each run's files, as blob ids, against the point the branch left origin/main):

  code    a file other than a test changed (a doc too: review_lint reads docs): the check stopped a real error (estimate: the change may be
          unrelated to the failure)
  test    only test files changed (tests/, test_*.py, conftest.py): the test's own problem
  flaky   nothing changed and the run went green

A fourth line counts the transitions where the base (the point the branch left origin/main) moved between the two runs,
since the files are then measured from a new base and cannot be compared.
"""
import argparse
import datetime
import json
import statistics
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

import check


def load(path):
    """The records of the log; a missing file is no records, a line that is not JSON is skipped."""
    records = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return records
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("started"):
            records.append(rec)
    return sorted(records, key=lambda rec: rec["started"])


def is_red(rec):
    return any(step["exit"] for step in rec.get("steps", []))


def is_test(path):
    pure = PurePosixPath(path)
    return pure.parts[0] == "tests" or pure.name.startswith("test_") or pure.name == "conftest.py"


def changed_files(red, green):
    before, after = red.get("files", {}), green.get("files", {})
    return sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))


def classify(red, green):
    """`rebased`, `code`, `test` or `flaky` for a red run and the green run after it. A doc counts as code:
    review_lint reads the docs."""
    if red.get("base") != green.get("base"):
        return "rebased"  # origin/main moved under the branch: files are measured from a new base, so they say nothing
    changed = changed_files(red, green)
    if any(not is_test(path) for path in changed):
        return "code"
    return "test" if any(is_test(path) for path in changed) else "flaky"


def transitions(records):
    """[(red, green, class)] for every red run and the green one that follows it on the same branch and worktree."""
    out, last = [], {}
    for rec in records:
        key = (rec.get("worktree"), rec.get("branch"))
        before = last.get(key)
        if before and is_red(before) and not is_red(rec):
            out.append((before, rec, classify(before, rec)))
        last[key] = rec
    return out


def ranking(rows, top):
    """Lines `name  runs  mean  max  total` of {name: [seconds]}, by total seconds."""
    ranked = sorted(rows.items(), key=lambda item: -sum(item[1]))[:top]
    return [f"  {name:<44} {len(took):>4} runs  mean {statistics.fmean(took):>6.1f} s  max {max(took):>6.1f} s  total {sum(took):>7.0f} s"
            for name, took in ranked]


def summary(records, top=10):
    reds = [rec for rec in records if is_red(rec)]
    lines = [f"runs: {len(records)}, red: {len(reds)}, green: {len(records) - len(reds)}"]
    red_tests = Counter(name for rec in reds for name in [*rec.get("failed_tests", []), *rec.get("failed_maa", [])])
    lines.append("")
    lines.append("tests that went red (runs):")
    lines += [f"  {count:>3}  {name}" for name, count in red_tests.most_common(top)] or ["  none"]
    red_steps = Counter(step["name"] for rec in reds for step in rec.get("steps", []) if step["exit"])
    lines.append("steps that went red: " + (", ".join(f"{name} {count}" for name, count in red_steps.most_common()) or "none"))
    done = transitions(records)
    lines.append("")
    lines.append(f"red -> next green on the same branch: {len(done)}")
    notes = {"code": "code changed: the check stopped an error (estimate)", "test": "only tests changed: the test's own problem",
             "flaky": "nothing changed: flaky", "rebased": "base moved (rebase or pull of main): not comparable"}
    counts = Counter(kind for _, _, kind in done)
    lines += [f"  {counts[kind]:>3}  {note}" for kind, note in notes.items()]
    still = len({(r.get("worktree"), r.get("branch")) for r in reds} - {(g.get("worktree"), g.get("branch")) for _, g, _ in done})
    if still:
        lines.append(f"  ({still} red branch(es) never ran green in this period)")
    lines.append("")
    lines.append("slowest steps:")
    steps = {}
    for rec in records:
        for step in rec.get("steps", []):
            steps.setdefault(step["name"], []).append(step["seconds"])
    lines += ranking(steps, top)
    files = {}
    for rec in records:
        for name, took in rec.get("test_seconds", {}).items():
            files.setdefault(name, []).append(took)
    lines.append("")
    lines.append("slowest test files:")
    lines += ranking(files, top) or ["  none"]
    return "\n".join(lines)


def main(argv=None, now=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--days", type=int, default=14, help="how many days back (default 14)")
    parser.add_argument("--since", help="start date YYYY-MM-DD, instead of --days")
    parser.add_argument("--log", help="the log file (default: <main checkout>/.local/check-runs.jsonl)")
    parser.add_argument("--top", type=int, default=10, help="rows per ranking (default 10)")
    args = parser.parse_args(argv)
    path = Path(args.log) if args.log else check.default_log()
    now = now or datetime.datetime.now().astimezone()
    since = (datetime.datetime.fromisoformat(args.since).astimezone() if args.since else now - datetime.timedelta(days=args.days))
    records = [rec for rec in load(path) if datetime.datetime.fromisoformat(rec["started"]) >= since]
    print(f"{path}, since {since.isoformat(timespec='minutes')}")
    if not records:
        print("no runs in the period")
        return 0
    print(summary(records, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
