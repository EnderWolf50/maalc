"""Open issues that break docs/agents/issue-tracker.md "Keeping issues current".

  uv run python tools/issue_audit.py                # stale = untouched for 14 days
  uv run python tools/issue_audit.py --stale-days 7

Lists every open issue without a milestone, without exactly one triage label, or untouched for --stale-days. A map
(`wayfinder:map`) or a long-running tracker (`tracking`) needs neither a milestone nor a triage label. Exit code 1
when an issue lacks a milestone or a triage label; stale issues alone exit 0, since only a person can tell whether
one is still current.
"""
import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

TRIAGE = {"needs-triage", "needs-info", "ready-for-agent", "ready-for-human"}
EXEMPT = {"wayfinder:map", "tracking"}


def audit(issues: list[dict], now: datetime, stale_days: int) -> dict[str, list[dict]]:
    """Each rule's name -> the open issues (`gh issue list --json number,title,labels,milestone,updatedAt`) breaking it."""
    found: dict[str, list[dict]] = {"no milestone": [], "triage labels != 1": [], "stale": []}
    for issue in issues:
        labels = {label["name"] for label in issue["labels"]}
        if not labels & EXEMPT:
            if issue["milestone"] is None:
                found["no milestone"].append(issue)
            if len(labels & TRIAGE) != 1:
                found["triage labels != 1"].append(issue)
        if now - datetime.fromisoformat(issue["updatedAt"]) > timedelta(days=stale_days):
            found["stale"].append(issue)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stale-days", type=int, default=14)
    args = parser.parse_args()
    out = subprocess.run(["gh", "issue", "list", "--state", "open", "--limit", "1000", "--json",
                          "number,title,labels,milestone,updatedAt"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    found = audit(json.loads(out), datetime.now(UTC), args.stale_days)
    for rule, issues in found.items():
        print(f"== {rule}: {len(issues)}")
        for issue in issues:
            labels = ",".join(label["name"] for label in issue["labels"])
            print(f"#{issue['number']} [{labels}] {issue['updatedAt'][:10]} {issue['title']}")
    return 1 if found["no milestone"] or found["triage labels != 1"] else 0


if __name__ == "__main__":
    sys.exit(main())
