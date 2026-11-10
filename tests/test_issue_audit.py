from datetime import UTC, datetime
from pathlib import Path

from issue_audit import audit, triage_labels

NOW = datetime(2026, 11, 5, tzinfo=UTC)
TRIAGE = triage_labels((Path(__file__).resolve().parent.parent / "docs/agents/triage-labels.md").read_text("utf-8"))


def issue(number, labels=(), milestone="v1", updated="2026-11-04T00:00:00Z", assignees=(), reason=None):
    return {"number": number, "title": "t", "labels": [{"name": n} for n in labels],
            "milestone": {"title": milestone} if milestone else None, "updatedAt": updated,
            "assignees": [{"login": a} for a in assignees], "stateReason": reason}


def pr(number, body, merged="2026-11-01T00:00:00Z"):
    return {"number": number, "title": "fix", "body": body, "mergedAt": merged}


def flagged(issues, rule, prs=(), closed=()):
    found = audit(issues, list(prs), TRIAGE, NOW, 14, closed=closed)
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


def test_an_open_issue_an_open_pr_closes_needs_an_assignee_even_when_the_pr_is_stacked():
    issues = [issue(10, ["ready-for-agent"]), issue(11, ["ready-for-agent"], assignees=["someone"]),
              issue(12, ["ready-for-agent"]), issue(13, ["tracking"], milestone=None)]
    open_prs = [{"number": 200, "body": "", "closingIssuesReferences": [{"number": n} for n in (10, 11, 13)]},
                {"number": 201, "body": "Stacked on #200.\r\n\r\nCloses #12", "closingIssuesReferences": []}]
    found = audit(issues, [], TRIAGE, NOW, 14, open_prs=open_prs)
    assert found["no assignee, an open PR closes it"] == ["#10 [ready-for-agent] t <- #200",
                                                          "#12 [ready-for-agent] t <- #201"]


def test_an_issue_closed_as_completed_needs_an_assignee():
    closed = [issue(14, reason="COMPLETED"), issue(15, reason="NOT_PLANNED"),
              issue(16, reason="COMPLETED", assignees=["someone"]), issue(17, ["tracking"], reason="COMPLETED")]
    assert flagged([], "closed as completed, no assignee", closed=closed) == ["#14"]


def test_a_tooling_issue_needs_no_milestone_but_still_one_triage_label():
    issues = [issue(18, ["tooling", "ready-for-agent"], milestone=None), issue(19, ["tooling"], milestone=None)]
    assert flagged(issues, "no milestone") == []
    assert flagged(issues, "triage labels != 1") == ["#19"]
