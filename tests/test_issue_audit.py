from datetime import UTC, datetime

from issue_audit import audit

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def issue(number, labels=(), milestone="v1", updated="2026-11-04T00:00:00Z"):
    return {"number": number, "title": "t", "labels": [{"name": n} for n in labels],
            "milestone": {"title": milestone} if milestone else None, "updatedAt": updated}


def numbers(found, rule):
    return [i["number"] for i in found[rule]]


def test_a_triaged_issue_in_a_milestone_passes():
    found = audit([issue(1, ["ready-for-agent", "bug"])], NOW, 14)
    assert found == {"no milestone": [], "triage labels != 1": [], "stale": []}


def test_missing_milestone_and_triage_label_are_flagged():
    found = audit([issue(2, ["bug"], milestone=None)], NOW, 14)
    assert numbers(found, "no milestone") == [2]
    assert numbers(found, "triage labels != 1") == [2]


def test_two_triage_labels_are_flagged():
    found = audit([issue(3, ["needs-info", "ready-for-agent"])], NOW, 14)
    assert numbers(found, "triage labels != 1") == [3]


def test_maps_and_trackers_need_no_milestone_or_triage_label():
    found = audit([issue(4, ["wayfinder:map"], milestone=None), issue(5, ["tracking"], milestone=None)], NOW, 14)
    assert numbers(found, "no milestone") == []
    assert numbers(found, "triage labels != 1") == []


def test_an_issue_untouched_past_the_limit_is_stale_even_when_exempt():
    found = audit([issue(6, ["tracking"], milestone=None, updated="2026-10-01T00:00:00Z"),
                   issue(7, ["needs-triage"], updated="2026-10-30T00:00:00Z")], NOW, 14)
    assert numbers(found, "stale") == [6]
