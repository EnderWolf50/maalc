"""Open issues that break docs/agents/issue-tracker.md "Keeping issues current".

  uv run python tools/issue_audit.py                # look back 14 days
  uv run python tools/issue_audit.py --days 30

Lists every open issue without a milestone or without exactly one triage label (docs/agents/triage-labels.md); a map
(`wayfinder:map`) or a tracker (`tracking`) needs neither. Exit code 1 when one does. Then lists, without failing,
the open issues a PR merged in the last --days names, and those untouched for --days: only a person can tell whether
the body still lists work that is done.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_AND_TRACKERS = {"wayfinder:map", "tracking"}
FAILING = ("no milestone", "triage labels != 1")


def triage_labels(table: str) -> set[str]:
    """The "Label in our tracker" column of triage-labels.md's table."""
    return {m[1] for m in re.finditer(r"^\|[^|]*\|\s*`([^`]+)`", table, re.M)}


def audit(issues: list[dict], prs: list[dict], triage: set[str], now: datetime, days: int) -> dict[str, list[str]]:
    """Each rule -> one line per open issue breaking it. `issues` and `prs` are `gh issue list` / `gh pr list` JSON."""
    since = now - timedelta(days=days)
    named: dict[int, list[int]] = {}
    for pr in prs:
        if datetime.fromisoformat(pr["mergedAt"]) >= since:
            for n in sorted({int(n) for n in re.findall(r"#(\d+)", pr["title"] + "\n" + pr["body"])}):
                named.setdefault(n, []).append(pr["number"])
    found: dict[str, list[str]] = {rule: [] for rule in (*FAILING, f"named by a PR merged in {days} days",
                                                          f"untouched for {days} days")}
    for issue in issues:
        labels = {label["name"] for label in issue["labels"]}
        line = f"#{issue['number']} [{','.join(sorted(labels))}] {issue['title']}"
        if not labels & MAPS_AND_TRACKERS:
            if issue["milestone"] is None:
                found["no milestone"].append(line)
            if len(labels & triage) != 1:
                found["triage labels != 1"].append(line)
        if issue["number"] in named:
            found[f"named by a PR merged in {days} days"].append(
                f"{line} <- {', '.join(f'#{n}' for n in named[issue['number']])}")
        if datetime.fromisoformat(issue["updatedAt"]) < since:
            found[f"untouched for {days} days"].append(f"{line} ({issue['updatedAt'][:10]})")
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
                "number,title,labels,milestone,updatedAt")
    prs = gh("pr", "list", "--state", "merged", "--limit", "1000", "--search",
             f"merged:>={(now - timedelta(days=args.days)).date()}", "--json", "number,title,body,mergedAt")
    triage = triage_labels((ROOT / "docs/agents/triage-labels.md").read_text(encoding="utf-8"))
    found = audit(issues, prs, triage, now, args.days)
    for rule, lines in found.items():
        print(f"== {rule}: {len(lines)}")
        print("\n".join(lines))
    return 1 if any(found[rule] for rule in FAILING) else 0


if __name__ == "__main__":
    sys.exit(main())
