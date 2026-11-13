"""The run's settlement actions (agent/settle_actions.py): the result page, the weekly bonuses, and the claim or the give-up."""

import json

import pytest

import actions
import settle_actions
import settlement
from agent_patch import patch_all
import test_actions

from test_actions import argv, moved, page_until, taps

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def test_a_forfeited_run_gives_up_its_rewards_and_the_same_team_runs_next(context, monkeypatch, tmp_path):
    # #95: after_retries "forfeit" ends the run at Exploration Reward short of floor 5; the team keeps its place
    # at the head of the queue, so the team that lost runs the next run again.
    patch_all(monkeypatch, "ROOT", tmp_path)
    teams = [{"id": "a", "name": "A", "enabled": True}, {"id": "b", "name": "B", "enabled": True}]
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps({"teams": teams}), encoding="utf-8")
    actions.RUN.update(settings={"run": {}, "teams": teams}, team=teams[0], planned=True, difficulty="hard")
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
    assert [t["id"] for t in json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))["teams"]] == ["a", "b"]
    line = json.loads((tmp_path / "logs" / "runs.jsonl").read_text(encoding="utf-8"))
    assert line["result"] == "giveup" and line["team"] == "a"


@pytest.mark.parametrize("cleared", [5, 3])  # claimed, given up
def test_an_exploration_reward_gone_is_handed_back_untouched(context, guarded, monkeypatch, cleared):
    actions.RUN.update(settings={"run": {"weekly_bonus_use": "none", "weekly_bonus_amount": 0, "target_floor": 5}}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setattr(settlement, "read_result", lambda text: settlement.Result(5, "normal", cleared, 5))
    assert settle_actions.Settle().run(context, argv())
    assert moved(context) == 0 and actions.STUCK["flag"] is None


def test_an_exploration_reward_gone_after_a_toggle_tap_does_not_claim(context, guarded, monkeypatch):
    actions.RUN.update(settings={"run": {"weekly_bonus_use": "all", "weekly_bonus_amount": 3, "target_floor": 5}}, team={"hard_from_floor": None}, difficulty="normal")
    monkeypatch.setattr(settlement, "read_result", lambda text: settlement.Result(5, "normal", 5, 5))
    monkeypatch.setattr(settlement, "bonus_toggles", lambda *a: 1)
    patch_all(monkeypatch, "toggles", lambda context, image: [False, False, False])
    page_until(context, "ExplorationReward", 1)
    assert settle_actions.Settle().run(context, argv())
    assert taps(context) == [(settle_actions.TOGGLE_X[0], 252)]
