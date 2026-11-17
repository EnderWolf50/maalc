"""The runner's protocol against the shared case file (tests/runner_cases.json), which the window's backend reads too."""

import json
from pathlib import Path

import pytest

from runner import protocol

CASES = json.loads((Path(__file__).resolve().parent / "runner_cases.json").read_text(encoding="utf-8"))


def test_the_case_file_speaks_the_runners_version():
    assert CASES["version"] == protocol.VERSION


@pytest.mark.parametrize("case", [c for c in CASES["commands"] if "command" in c], ids=lambda c: c["line"][:60])
def test_a_command_line_parses_to_its_case(case):
    assert protocol.command(case["line"]) == case["command"]


@pytest.mark.parametrize("case", [c for c in CASES["commands"] if "error" in c], ids=lambda c: c["line"][:60])
def test_a_bad_command_line_is_refused_and_says_why(case):
    with pytest.raises(protocol.ProtocolError) as e:
        protocol.command(case["line"])
    assert case["error"] in str(e.value)


@pytest.mark.parametrize("case", CASES["events"], ids=lambda c: json.dumps(c["event"])[:70])
def test_an_event_is_well_formed_as_its_case_says(case):
    if case["valid"]:
        protocol.check_event(case["event"])
    else:
        with pytest.raises(protocol.ProtocolError):
            protocol.check_event(case["event"])


def test_every_event_kind_and_task_state_has_a_valid_case():
    valid = [c["event"] for c in CASES["events"] if c["valid"]]
    assert {e["event"] for e in valid} == set(protocol.EVENTS)
    assert {"pending", "cancelled"} <= {e["state"] for e in valid if e["event"] == "task"}


def test_an_event_line_is_one_line_of_json_with_the_version():
    line = protocol.line(protocol.event("log", t="10:00:00.000", source="agent", line="[maalc] 一\n二"))
    assert "\n" not in line and json.loads(line) == {"v": 1, "event": "log", "t": "10:00:00.000", "source": "agent",
                                                      "line": "[maalc] 一\n二"}
    assert "一" in line  # written as UTF-8, not \u escapes
