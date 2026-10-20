"""The title's User Agreement and the game's download and update dialogs (#85, #86), on the live captures."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions

SCREENS = Path(__file__).parent / "screens"
UNTICKED, TICKED = (np.asarray(Image.open(SCREENS / f"{n}.png").convert("RGB"))[:, :, ::-1].copy()
                    for n in ("UserAgreement", "UserAgreementTicked"))


def tick(image, box):
    x, y = box
    out = image.copy()
    out[y - 4:y + 23, x - 4:x + 23] = TICKED[y - 4:y + 23, x - 4:x + 23]
    return out


@pytest.fixture
def game(monkeypatch):
    """A fake game on the User Agreement: a tap on a box ticks it unless frozen; taps and stops are recorded."""
    state = SimpleNamespace(image=UNTICKED, taps=[], stops=[], frozen=False)
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: state.image

    def click(x, y):
        state.taps.append((x, y))
        n = actions.AGREE_SIZE
        for box in actions.AGREE_BOXES:
            if not state.frozen and box[0] <= x < box[0] + n and box[1] <= y < box[1] + n:
                state.image = tick(state.image, box)
        return MagicMock()
    ctx.tasker.controller.post_click.side_effect = click
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None: state.stops.append(reason) or False)
    actions.RUN.clear()
    actions.RUN["settings"] = {"run": {"auto_accept_terms": True, "auto_download": True}}
    actions.STUCK["updates"] = 0
    state.ctx = ctx
    yield state
    actions.RUN.clear()
    actions.STUCK["updates"] = 0


def test_the_boxes_read_ticked_or_not():
    assert not any(actions.agree_ticked(UNTICKED, *b) for b in actions.AGREE_BOXES)
    assert all(actions.agree_ticked(TICKED, *b) for b in actions.AGREE_BOXES)


def test_sweep_where_both_boxes_read_ticked():
    # CODING_STANDARDS: the brightness test's false positives over tests/screens. Harmless: it is read only once
    # UserAgreement hit, and a box reading ticked by mistake is only left untapped (Confirm stays dim).
    hits = []
    for png in sorted(SCREENS.glob("*.png")):
        image = np.asarray(Image.open(png).convert("RGB"))[:, :, ::-1]
        if image.shape[:2] == (720, 1280) and all(actions.agree_ticked(image, *b) for b in actions.AGREE_BOXES):
            hits.append(png.name)
    assert hits == ["BattleTurnLit.png", "BossGiftTrialsHard.png", "RunVictory.png", "SinnersTab.png",
                    "TeamSelect.png", "Title.png", "UserAgreementTicked.png"]


def test_both_boxes_are_ticked_then_confirm(game):
    assert actions.AcceptTerms().run(game.ctx, None)
    boxes = [(x + 9, y + 9) for x, y in actions.AGREE_BOXES]
    assert game.taps == [*boxes, actions.AGREE_CONFIRM]
    assert all(actions.agree_ticked(game.image, *b) for b in actions.AGREE_BOXES)


def test_a_ticked_box_is_not_tapped_again(game):
    game.image = TICKED
    actions.AcceptTerms().run(game.ctx, None)
    assert game.taps == [actions.AGREE_CONFIRM]  # a tap would untick it


def test_no_confirm_while_a_box_stays_unticked(game):
    game.frozen = True
    assert actions.AcceptTerms().run(game.ctx, None)  # MirrorHub looks again
    assert actions.AGREE_CONFIRM not in game.taps


def test_terms_off_stops_without_a_tap(game):
    actions.RUN["settings"]["run"]["auto_accept_terms"] = False
    assert not actions.AcceptTerms().run(game.ctx, None)
    assert game.taps == [] and "auto_accept_terms" in game.stops[0]


def test_download_off_stops_without_a_tap(game):
    actions.RUN["settings"]["run"]["auto_download"] = False
    box = SimpleNamespace(box=[600, 460, 80, 20])
    assert not actions.ConfirmDownload().run(game.ctx, box)
    assert not actions.AcceptUpdate().run(game.ctx, box)
    assert game.taps == [] and len(game.stops) == 2
    game.ctx.run_task.assert_not_called()


def test_an_update_dialog_is_pressed_and_the_game_restarted(game):
    actions.RUN.update(turn=(None, 3), map_misses=2)
    assert actions.AcceptUpdate().run(game.ctx, SimpleNamespace(box=[600, 460, 80, 20]))
    assert game.taps == [(640, 470)]
    game.ctx.run_task.assert_called_once_with("RecoverL3")
    assert "turn" not in actions.RUN and "map_misses" not in actions.RUN  # the restarted game starts the battle over


def test_an_update_notice_that_keeps_coming_back_stops_the_bot(game):
    box = SimpleNamespace(box=[600, 460, 80, 20])
    assert actions.AcceptUpdate().run(game.ctx, box) and actions.AcceptUpdate().run(game.ctx, box)
    assert not actions.AcceptUpdate().run(game.ctx, box)
    assert game.ctx.run_task.call_count == 2 and "update" in game.stops[0]


def test_a_confirmed_download_drops_the_floor_time_limit(game):
    # Live 2026-10-21: 32 min of download; the floor's limit would have restarted the game mid-download.
    actions.RUN["deadline"] = 0
    actions.ConfirmDownload().run(game.ctx, SimpleNamespace(box=[600, 460, 80, 20]))
    assert "deadline" not in actions.RUN
    actions.STUCK["watch"].reset()
