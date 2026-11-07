"""The Event action on fake event pages: when it taps, and what MirrorHub finds when it hands the page back."""

from unittest.mock import DEFAULT

import numpy as np

import actions
import test_actions
from ocrtext import has
from test_actions import Choices

clock, context = test_actions.clock, test_actions.context  # its fixtures


def fading(context, levels):
    """Screenshots filled with the next of levels (the last one repeats), the red button lit on each: a page fading in.
    Returns [(x, y), screenshots taken] for each tap."""
    shots, taps = [], []

    def screencap():
        shots.append(1)
        image = np.full((720, 1280, 3), levels[min(len(shots), len(levels)) - 1], np.uint8)
        image[640:650, 1080:1180] = (0, 0, 200)
        return image
    ctl = context.tasker.controller
    ctl.post_screencap.return_value.wait.return_value.get.side_effect = screencap
    ctl.post_click.side_effect = lambda x, y: taps.append(((x, y), len(shots))) or DEFAULT
    return taps


def test_the_lit_button_is_pressed_once_the_page_holds_still(context, clock):
    # #273: with MaaFramework's 200 ms pre_delay gone, MirrorHub hands the page over as soon as its button reads, which
    # can be mid-fade. Screenshots 3 and 4 are the first two alike.
    taps = fading(context, [40, 80, 120, 120])
    actions.Event().run(context, None)
    (xy, shots), *_ = taps
    assert xy == actions.EVENT_BUTTON and shots >= 4


def test_a_page_that_never_holds_still_is_handed_back_untapped(context, clock):
    taps = fading(context, [40, 80] * 30)
    assert actions.Event().run(context, None) is True
    assert taps == []


class Picked(Choices):
    """A Choices page that fades out once an option is tapped: the panel dims at once, the header still reads on the
    next `fade` screenshots, then the page that follows shows (no text)."""

    def __init__(self, context, monkeypatch, fade):
        super().__init__(context, monkeypatch, [("Take it.", ""), ("Leave it.", "")], ["Unknown story."])
        self.fade, self.since = fade, None  # screenshots since the tap

    def click(self, x, y):
        result = super().click(x, y)
        if self.tapped and self.since is None:
            self.since = 0
        return result

    def render(self):
        if self.since is None:
            return super().render()
        self.since += 1
        return super().render() // 2

    def read(self, name, image, override=None):
        return super().read(name, image, override) if self.since is None or self.since <= self.fade else None


def test_a_taken_option_hands_back_once_the_choices_page_is_gone(context, clock, monkeypatch):
    # #273: the tap returned once the panel changed, with the page still fading out; with MaaFramework's 200 ms
    # post_delay gone, MirrorHub's next look reads the fading Choices and taps an option again.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    page = Picked(context, monkeypatch, fade=3)
    actions.Event().run(context, None)
    assert len(page.tapped) == 1
    assert not has(actions.text(context, actions.screen(context), actions.CHOICES_HEADER), "Choices")


def test_a_choices_page_that_stays_after_the_tap_is_handed_back_in_time(context, clock, monkeypatch):
    # A boss's next question can come up as another Choices page: the wait for the old one to go is bounded.
    actions.RUN["team"] = {"keyword": "Burn"}
    actions.RUN["settings"] = {"event_overrides": []}
    page = Picked(context, monkeypatch, fade=float("inf"))
    began = actions.time.monotonic()
    actions.Event().run(context, None)
    assert len(page.tapped) == 1
    assert actions.time.monotonic() - began <= 2 * actions.EVENT_TAKE + 1
