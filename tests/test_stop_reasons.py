"""Stop reason codes (#881): agent/stop_reasons.json, the codes the bot's stops carry, and the line the stop procedure logs."""

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import actions
import battle_actions
import reasons
from agent_patch import patch_all
from test_pipeline import load_nodes

AGENT = Path(__file__).resolve().parent.parent / "agent"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(text):
    return set(PLACEHOLDER.findall(text))


@pytest.mark.parametrize("code", sorted(reasons.CODES))
def test_each_code_has_a_sentence_in_both_languages_with_the_same_params(code):
    entry = reasons.CODES[code]
    assert set(entry) == {"zh_tw", "en_us"} and all(entry.values()), entry
    assert placeholders(entry["zh_tw"]) == placeholders(entry["en_us"]), entry


def reason_calls():
    """(file:line, code, param names) of each Reason(text, "Code", **params) the agent's modules make."""
    for path in sorted(set(AGENT.glob("*.py")) - {AGENT / "reasons.py"}):  # of_node: the node's name, tested below
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Reason":
                code = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else None
                yield f"{path.name}:{node.lineno}", code, {k.arg for k in node.keywords}


def test_each_coded_stop_of_the_agent_names_a_code_of_the_file_with_its_params():
    calls = list(reason_calls())
    assert len(calls) >= 10, calls  # the walk finds them
    bad = [(where, code, params) for where, code, params in calls
           if code not in reasons.CODES or params != placeholders(reasons.CODES[code]["en_us"])]
    assert bad == []


def test_each_stop_node_of_the_pipeline_has_a_code():
    # StopTask and Halt take the node's name as the code (reasons.of_node): a new one needs its sentences
    stops = sorted(n for n, spec in load_nodes().items() if spec.get("custom_action") in ("StopTask", "Halt"))
    assert stops and [n for n in stops if n not in reasons.CODES] == []


def test_a_coded_reason_is_its_english_text_with_the_code_on_top():
    r = reasons.Reason("EXP: defeated with the 2 retries used up", "LuxDefeated", retries=2)
    assert r == "EXP: defeated with the 2 retries used up" and f"stop: {r}" == "stop: EXP: defeated with the 2 retries used up"
    assert (r.code, r.params) == ("LuxDefeated", {"retries": 2})
    assert json.dumps({"reason": r}) == '{"reason": "EXP: defeated with the 2 retries used up"}'  # the webhook's


def test_the_code_line_names_the_code_and_its_params_as_json():
    assert reasons.code_line(reasons.Reason("x", "LuxDefeated", retries=2)) == 'stop code: LuxDefeated {"retries":2}'
    assert reasons.code_line(reasons.Reason("maintenance notice", "MaintenanceNotice")) == "stop code: MaintenanceNotice"
    assert reasons.code_line("a reason with no code") is None


@pytest.fixture
def stopped(monkeypatch, tmp_path):
    """The reasons actions.stop was called with, each with its whole_list; the stop procedure itself does not run."""
    calls = []
    patch_all(monkeypatch, "stop", lambda context, reason, line=None, whole_list=False: calls.append((reason, whole_list)) or False)
    patch_all(monkeypatch, "ROOT", tmp_path)
    patch_all(monkeypatch, "TASK", {"runs": 0, "done": None, "options": {}})
    monkeypatch.setitem(actions.STUCK, "updates", 0)
    return calls


def coded(calls):
    return [(getattr(r, "code", None), getattr(r, "params", None), whole) for r, whole in calls]


@pytest.mark.parametrize("node", sorted(n for n, spec in load_nodes().items() if spec.get("custom_action") in ("StopTask", "Halt")))
def test_a_stop_node_of_the_pipeline_stops_with_its_name_as_the_code(stopped, node):
    spec = load_nodes()[node]
    action = actions.Halt if spec["custom_action"] == "Halt" else actions.StopTask
    argv = SimpleNamespace(node_name=node, custom_action_param=json.dumps(spec["custom_action_param"]))
    assert action().run(MagicMock(), argv) is False
    assert coded(stopped) == [(node, {}, action is actions.Halt)]
    assert stopped[0][0] == f"{node}: {spec['custom_action_param']}"  # the English text as it was


@pytest.mark.parametrize("action, off, code", [
    (actions.ConfirmDownload, "auto_download", "DownloadOff"),
    (actions.AcceptUpdate, "auto_download", "UpdateOff"),
    (actions.AcceptTerms, "auto_accept_terms", "TermsOff"),
])
def test_a_title_dialog_with_its_option_off_stops_the_whole_list_with_a_code(stopped, action, off, code):
    actions.TASK["options"] = {off: False}
    assert action().run(MagicMock(), SimpleNamespace(box=[0, 0, 10, 10])) is False
    assert coded(stopped) == [(code, {}, True)]


def test_an_update_that_keeps_coming_back_stops_with_the_times_it_came(stopped, monkeypatch):
    monkeypatch.setitem(actions.STUCK, "updates", actions.UPDATE_RESTARTS)
    assert actions.AcceptUpdate().run(MagicMock(), SimpleNamespace(box=[0, 0, 10, 10])) is False
    assert coded(stopped) == [("UpdateRepeats", {"times": actions.UPDATE_RESTARTS + 1}, True)]
    assert stopped[0][0] == f"the game asked for an update {actions.UPDATE_RESTARTS + 1} times since the bot started"


def test_a_daily_hubs_stuck_below_l3_stops_with_the_stuck_code(stopped):
    actions.STUCK["flag"] = ("PassBanner", 1, "PassBanner: the screen did not change")
    argv = SimpleNamespace(node_name="PassStuck", custom_action_param='"Claim Pass Missions is stuck"')
    assert actions.DailyRecover().run(MagicMock(), argv) is False
    assert coded(stopped) == [("Stuck", {}, False)] and stopped[0][0] == "PassStuck: Claim Pass Missions is stuck"


def test_a_restart_the_launchs_streak_refuses_stops_with_the_stuck_code(stopped, monkeypatch):
    # restart_game's second way out; its first (the task's restarts) is test_recovery.py's daily restarts
    monkeypatch.setitem(actions.STUCK, "restarts", SimpleNamespace(attempt=lambda kind: "game restarted 3 times in a row"))
    assert actions.restart_game(MagicMock(), "the game is frozen", "MirrorMap") is False
    assert coded(stopped) == [("Stuck", {}, False)] and stopped[0][0] == "the game is frozen; game restarted 3 times in a row"


def test_wipe_retries_used_up_stop_the_run_with_a_code(stopped, monkeypatch):
    patch_all(monkeypatch, "current_run", lambda context: None)
    monkeypatch.setitem(actions.TASK, "options", {"wipe_retries": 1, "after_retries": "stop"})
    monkeypatch.setitem(actions.RUN, "wipes", 1)
    assert battle_actions.Wipe().run(MagicMock(), None) is False
    assert coded(stopped) == [("RetriesUsedUp", {}, False)] and stopped[0][0] == "retries used up"
