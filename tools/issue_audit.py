"""Issues that break docs/agents/issue-tracker.md "Keeping issues current".

  uv run python tools/issue_audit.py                # look back 14 days
  uv run python tools/issue_audit.py --days 30

Lists every open issue without a milestone or without exactly one triage label (docs/agents/triage-labels.md), and every
issue without an assignee that an open PR closes or that was closed as completed; a map (`wayfinder:map`) or a tracker
(`tracking`) needs none of these. Exit code 1 when one does. Then lists, without failing, the open issues a PR merged in
the last --days names, and those untouched for --days: only a person can tell whether the body still lists work that
is done.
"""
import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_AND_TRACKERS = {"wayfinder:map", "tracking"}
FAILING = ("no milestone", "triage labels != 1", "no assignee, an open PR closes it", "closed as completed, no assignee")


def triage_labels(table: str) -> set[str]:
    """The "Label in our tracker" column of triage-labels.md's table."""
    return {m[1] for m in re.finditer(r"^\|[^|]*\|\s*`([^`]+)`", table, re.M)}


def label_names(issue: dict) -> set[str]:
    return {label["name"] for label in issue["labels"]}


def describe(issue: dict) -> str:
    return f"#{issue['number']} [{','.join(sorted(label_names(issue)))}] {issue['title']}"


def pr_refs(numbers: list[int]) -> str:
    return ", ".join(f"#{n}" for n in numbers)


def audit(issues: list[dict], prs: list[dict], triage: set[str], now: datetime, days: int, *,
          open_prs: Sequence[dict] = (), closed: Sequence[dict] = ()) -> dict[str, list[str]]:
    """Each rule -> one line per issue breaking it. `issues` (open) and `closed` are `gh issue list` JSON, `prs`
    (merged) and `open_prs` are `gh pr list` JSON."""
    since = now - timedelta(days=days)
    named: dict[int, list[int]] = {}
    for pr in prs:
        if datetime.fromisoformat(pr["mergedAt"]) >= since:
            for n in sorted({int(n) for n in re.findall(r"#(\d+)", pr["title"] + "\n" + pr["body"])}):
                named.setdefault(n, []).append(pr["number"])
    closing: dict[int, list[int]] = {}
    for pr in open_prs:
        for ref in pr["closingIssuesReferences"]:
            closing.setdefault(ref["number"], []).append(pr["number"])
    found: dict[str, list[str]] = {rule: [] for rule in (*FAILING, f"named by a PR merged in {days} days",
                                                          f"untouched for {days} days")}
    for issue in issues:
        labels = label_names(issue)
        line = describe(issue)
        if not labels & MAPS_AND_TRACKERS:
            if issue["milestone"] is None:
                found["no milestone"].append(line)
            if len(labels & triage) != 1:
                found["triage labels != 1"].append(line)
            if issue["number"] in closing and not issue["assignees"]:
                found["no assignee, an open PR closes it"].append(f"{line} <- {pr_refs(closing[issue['number']])}")
        if issue["number"] in named:
            found[f"named by a PR merged in {days} days"].append(f"{line} <- {pr_refs(named[issue['number']])}")
        if datetime.fromisoformat(issue["updatedAt"]) < since:
            found[f"untouched for {days} days"].append(f"{line} ({issue['updatedAt'][:10]})")
    for issue in closed:
        if issue["stateReason"] == "COMPLETED" and not issue["assignees"] and not label_names(issue) & MAPS_AND_TRACKERS:
            found["closed as completed, no assignee"].append(describe(issue))
    return found


def gh(*args: str) -> list[dict]:
    return json.loads(subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                     check=True).stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    now = datetime.now(UTC)
    issues = gh("issue", "list", "--state", "open", "--limit", "1000", "--json",
                "number,title,labels,milestone,updatedAt,assignees")
    # Only the unassigned ones: every closed issue would outgrow --limit.
    closed = gh("issue", "list", "--state", "closed", "--search", "no:assignee", "--limit", "1000", "--json",
                "number,title,labels,stateReason,assignees")
    prs = gh("pr", "list", "--state", "merged", "--limit", "1000", "--search",
             f"merged:>={(now - timedelta(days=args.days)).date()}", "--json", "number,title,body,mergedAt")
    open_prs = gh("pr", "list", "--state", "open", "--limit", "1000", "--json", "number,closingIssuesReferences")
    triage = triage_labels((ROOT / "docs/agents/triage-labels.md").read_text(encoding="utf-8"))
    found = audit(issues, prs, triage, now, args.days, open_prs=open_prs, closed=closed)
    for rule, lines in found.items():
        print(f"== {rule}: {len(lines)}")
        print("\n".join(lines))
    return 1 if any(found[rule] for rule in FAILING) else 0


if __name__ == "__main__":
    sys.exit(main())
