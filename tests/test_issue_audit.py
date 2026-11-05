from datetime import UTC, datetime
from pathlib import Path

from issue_audit import audit, triage_labels

NOW = datetime(2026, 11, 5, tzinfo=UTC)
TRIAGE = triage_labels((Path(__file__).resolve().parent.parent / "docs/agents/triage-labels.md").read_text("utf-8"))


def issue(number, labels=(), milestone="v1", updated="2026-11-04T00:00:00Z"):
    return {"number": number, "title": "t", "labels": [{"name": n} for n in labels],
            "milestone": {"title": milestone} if milestone else None, "updatedAt": updated}


def pr(number, body, merged="2026-11-01T00:00:00Z"):
    return {"number": number, "title": "fix", "body": body, "mergedAt": merged}


def flagged(issues, rule, prs=()):
    found = audit(issues, list(prs), TRIAGE, NOW, 14)
    return [line.split()[0] for line in found[rule]]


def test_triage_labels_come_from_the_tracker_table():
    assert TRIAGE == {"needs-triage", "needs-info", "ready-for-agent", "ready-for-human", "wontfix"}


def test_a_triaged_issue_in_a_milestone_passes():
    found = audit([issue(1, ["ready-for-agent", "bug"])], [], TRIAGE, NOW, 14)
    assert not any(found.values())


def test_missing_milestone_and_triage_label_are_flagged():
    assert flagged([issue(2, ["bug"], milestone=None)], "no milestone") == ["#2"]
    assert flagged([issue(2, ["bug"], milestone=None)], "triage labels != 1") == ["#2"]


def test_two_triage_labels_are_flagged():
    assert flagged([issue(3, ["needs-info", "ready-for-agent"])], "triage labels != 1") == ["#3"]


def test_maps_and_trackers_need_no_milestone_or_triage_label():
    issues = [issue(4, ["wayfinder:map"], milestone=None), issue(5, ["tracking"], milestone=None)]
    assert flagged(issues, "no milestone") == []
    assert flagged(issues, "triage labels != 1") == []


def test_an_open_issue_a_recent_merged_pr_names_is_listed_with_the_pr():
    found = audit([issue(6, ["needs-triage"]), issue(7, ["needs-triage"])],
                  [pr(100, "Refs #6"), pr(101, "Refs #7", merged="2026-10-01T00:00:00Z")], TRIAGE, NOW, 14)
    assert found["named by a PR merged in 14 days"] == ["#6 [needs-triage] t <- #100"]


def test_an_issue_untouched_past_the_window_is_listed_even_when_a_tracker():
    issues = [issue(8, ["tracking"], milestone=None, updated="2026-10-01T00:00:00Z"),
              issue(9, ["needs-triage"], updated="2026-10-30T00:00:00Z")]
    assert flagged(issues, "untouched for 14 days") == ["#8"]
