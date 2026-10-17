"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
import recovery


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    ctx.run_recognition.return_value = None  # OCR reads nothing, no node hits
    actions.RUN.clear()
    actions.RUN.update(settings={}, team={})  # a run plan in memory
    actions.STUCK["flag"] = None
    yield ctx
    actions.RUN.clear()
    actions.STUCK["flag"] = None


def test_a_missed_victory_does_not_carry_the_battle_clock_into_the_next_battle(context):
    # #80: the last battle ended without VICTORY being seen, its clock and turn count left behind.
    actions.RUN["battle_start"] = time.time() - recovery.BATTLE_LIMIT - 60
    actions.RUN["turn"] = (None, 3)
    actions.Formation().run(context, None)  # the next battle's formation (fading in: no count read)
    actions.PlayTurn().run(context, SimpleNamespace(box=[600, 400, 40, 20]))
    assert actions.STUCK["flag"] is None


def reads(context, texts):
    """OCR reads texts[roi] (a list of (text, box)) in that roi, nothing elsewhere; no other node hits."""
    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in texts.get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition


def taps(context):
    return [c.args for c in context.tasker.controller.post_click.call_args_list]


def test_a_battle_is_switched_to_the_shortest_animations_once(context):
    reads(context, {tuple(actions.SPEED_LABEL): [("MAX", (1085, 28, 50, 25))]})
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert taps(context)[:2] == [actions.SPEED_TOGGLE, actions.SPEED_MIN]
    context.tasker.controller.post_click.reset_mock()
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))  # the next turn
    assert actions.SPEED_TOGGLE not in taps(context)


def test_a_battle_already_at_the_shortest_animations_is_left_alone(context):
    reads(context, {tuple(actions.SPEED_LABEL): [("MIN", (1085, 28, 50, 25))]})
    actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert actions.SPEED_TOGGLE not in taps(context)
