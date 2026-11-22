"""The run's settlement actions (agent/settle_actions.py): the prompts after floors 5 and 10, the result page, the weekly bonuses, and the claim or the give-up."""

import json
import re

import pytest

import actions
import settle_actions
import settlement
from agent_patch import patch_all
from test_pipeline import load_nodes
import test_actions

from test_actions import argv, moved, page, page_until, taps

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def test_a_forfeited_run_gives_up_its_rewards_and_the_same_team_runs_next(context, monkeypatch, tmp_path):
    # #95: after_retries "forfeit" ends the run at Exploration Reward short of floor 5; the team keeps its place
    # at the head of the queue, so the team that lost runs the next run again.
    patch_all(monkeypatch, "ROOT", tmp_path)
    teams = [{"id": "a", "name": "A", "enabled": True}, {"id": "b", "name": "B", "enabled": True}]
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps({"version": 22, "teams": teams, "team_queue": ["a", "b"]}),
                                                       encoding="utf-8")
    actions.RUN.update(settings={"teams": teams}, team=teams[0], planned=True, difficulty="hard")
    taps = []

    def ocr(context, image, roi, only_rec=False):
        if roi == settle_actions.RESULT:
            return [("Floor 3 [HARD] 2/6", (300, 420, 90, 20))]
        if roi == actions.DIALOG_TEXT and taps:
            return [("End expedition without claiming rewards?", (400, 300, 400, 30))]
        return []
    patch_all(monkeypatch, "ocr", ocr)
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))

    settle_actions.Settle().run(context, None)
    assert taps == [settle_actions.GIVE_UP, actions.DIALOG_CONFIRM]
    assert json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))["team_queue"] == ["a", "b"]
    line = json.loads((tmp_path / "logs" / "runs.jsonl").read_text(encoding="utf-8"))
    assert line["result"] == "giveup" and line["team"] == "a"


@pytest.mark.parametrize("cleared", [5, 3])  # claimed, given up
def test_an_exploration_reward_gone_is_handed_back_untouched(context, guarded, monkeypatch, cleared):
    actions.RUN.update(settings={}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setitem(actions.TASK, "options", {"weekly_bonus_use": "none", "weekly_bonus_amount": 0, "target_floor": 5})
    monkeypatch.setattr(settlement, "read_result", lambda text: settlement.Result(5, "normal", cleared, 5))
    assert settle_actions.Settle().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_an_exploration_reward_gone_after_a_toggle_tap_does_not_claim(context, guarded, monkeypatch):
    actions.RUN.update(settings={}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setitem(actions.TASK, "options", {"weekly_bonus_use": "all", "weekly_bonus_amount": 3, "target_floor": 5})
    monkeypatch.setattr(settlement, "read_result", lambda text: settlement.Result(5, "normal", 5, 5))
    monkeypatch.setattr(settlement, "bonus_toggles", lambda *a: 1)
    patch_all(monkeypatch, "toggles", lambda context, image: [False, False, False])
    page_until(context, "ExplorationReward", 1)
    assert settle_actions.Settle().run(context, argv())
    assert taps(context) == [(settle_actions.TOGGLE_X[0], 252)]


PROMPT_READS = [("XCancel", (522, 440, 160, 26)), ("✓Confirm", (705, 440, 158, 26))]  # as the help sheet shows them


@pytest.mark.parametrize(("after", "target", "pressed"), [
    (5, 5, (602, 453)), (10, 5, (602, 453)),  # target 5: Cancel, as v1
    (5, 10, (784, 453)), (10, 10, (602, 453)),  # target 10: on into floor 6, not into 11
    (5, 15, (784, 453)), (10, 15, (784, 453)),  # target 15: on both times
])
def test_the_prompt_after_floor_5_or_10_presses_confirm_or_cancel_by_the_target(context, clock, monkeypatch, after, target, pressed):
    # #434: the buttons are found by their text: the floor 10 prompt has no live capture yet (#854)
    monkeypatch.setitem(actions.TASK, "options", {"target_floor": target, "keep_dismissed_screens": False})
    page(context, {tuple(settle_actions.PROMPT_BUTTONS): PROMPT_READS})
    assert settle_actions.ParallelPrompt().run(context, argv({"after": after}, node="ParallelModePrompt"))
    assert taps(context) == [pressed]


def test_a_prompt_whose_button_does_not_read_is_left_for_the_next_look(context, clock, monkeypatch, capsys):
    monkeypatch.setitem(actions.TASK, "options", {"target_floor": 10, "keep_dismissed_screens": False})
    page(context, {tuple(settle_actions.PROMPT_BUTTONS): PROMPT_READS[:1]})  # Cancel only
    assert settle_actions.ParallelPrompt().run(context, argv({"after": 5}, node="ParallelModePrompt"))
    assert taps(context) == []
    assert "ParallelModePrompt: Confirm not read" in capsys.readouterr().out


def test_the_prompt_is_kept_in_the_dismissed_screens(context, clock, monkeypatch, tmp_path):
    # #847: the live prompts are the fixtures: #852's floor 5 one came from there, #854 waits for the floor 10 one
    monkeypatch.setitem(actions.TASK, "options", {"target_floor": 15, "keep_dismissed_screens": True})
    page(context, {tuple(settle_actions.PROMPT_BUTTONS): PROMPT_READS})
    settle_actions.ParallelPrompt().run(context, argv({"after": 10}, node="ExtremeModePrompt"))
    (shot,) = (tmp_path / "logs" / "dismissed").iterdir()
    assert shot.name.endswith("-ExtremeModePrompt.png")


def test_the_two_prompts_are_two_nodes_that_read_the_buttons_where_the_agent_does():
    nodes = load_nodes("popups.json")
    for name, after in (("ParallelModePrompt", 5), ("ExtremeModePrompt", 10)):
        buttons, body = nodes[name]["all_of"]
        assert buttons["roi"] == settle_actions.PROMPT_BUTTONS, name
        assert nodes[name]["custom_action"] == "ParallelPrompt" and nodes[name]["custom_action_param"] == {"after": after}
    assert nodes["ParallelModePrompt"]["all_of"][1]["roi"] == nodes["ExtremeModePrompt"]["all_of"][1]["roi"]  # one dialog
    infinity = re.compile(nodes["ParallelModePrompt"]["all_of"][1]["expected"])
    extreme = re.compile(nodes["ExtremeModePrompt"]["all_of"][1]["expected"])
    # the game's texts (InfinityFloor_CheckEnter_Modal_Desc, InfinityFloor_Extreme_CheckEnter_Modal_Desc)
    after_5, after_10 = "You can enter the Parallel Superposition Mode.", "You can enter the EXTREME Mode."
    assert infinity.search(after_5) and not infinity.search(after_10)
    assert extreme.search(after_10) and not extreme.search(after_5)


def test_a_prompt_looked_at_again_keeps_one_screen_a_minute(context, clock, monkeypatch, tmp_path):
    # a button that does not read brings the prompt back every 1.5 s: it must not push a prompt's first capture out
    monkeypatch.setitem(actions.TASK, "options", {"target_floor": 10, "keep_dismissed_screens": True})
    patch_all(monkeypatch, "DISMISSED_AT", {})
    page(context, {tuple(settle_actions.PROMPT_BUTTONS): PROMPT_READS[:1]})  # Confirm does not read
    stamps = iter(f"2026-11-20T00:00:0{i}Z" for i in range(3))
    monkeypatch.setattr(settlement, "now", lambda: next(stamps))
    for _ in range(3):
        settle_actions.ParallelPrompt().run(context, argv({"after": 5}, node="ParallelModePrompt"))
    assert len(list((tmp_path / "logs" / "dismissed").iterdir())) == 1
