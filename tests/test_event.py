"""The Event action on fake event pages: when it taps, and what MirrorHub finds when it hands the page back."""

from types import SimpleNamespace
from unittest.mock import DEFAULT

import numpy as np
import pytest

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
        self.fade, self.shots_since_tap = fade, None

    def click(self, x, y):
        result = super().click(x, y)
        if self.tapped and self.shots_since_tap is None:
            self.shots_since_tap = 0
        return result

    def render(self):
        if self.shots_since_tap is None:
            return super().render()
        self.shots_since_tap += 1
        return super().render() // 2

    def read(self, name, image, override=None):
        return super().read(name, image, override) if self.shots_since_tap is None or self.shots_since_tap <= self.fade else None


def test_a_taken_option_hands_back_once_the_choices_page_is_gone(context, clock, monkeypatch):
    # #273: the tap returned once the panel changed, which a lit card does before the page goes; with MaaFramework's
    # 200 ms post_delay gone, MirrorHub's next look would read the Choices still up and take an option again.
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


# #309 live, from the last Continue: the event page fades out with the button lit (FADE here), the first GET! window
# shows, the second GAP s after the first closes, and a tap closes a window CLOSE_LAG s later.
FADE, GAP, CLOSE_LAG = 0.4, 0.34, 0.1
# Offline medians with the bot's MaaFramework resource and agent link (#309): a node that reads text about 53 ms, a
# template about 5 ms; RetryPopup's template matches the window's Confirm, and its text is read there too. SHOT and TAP:
# not measured.
COST = {"Connecting": 0.006, "RetryPopup": 0.009, "PopupButton": 0.005, "Event": 0.053, "GiftGet": 0.053}
OCR, RETRY_ON_WINDOW, SHOT, TAP = 0.053, 0.045, 0.03, 0.01
PAGES = ["event", "window", "map"]


class GiftWindows:
    """The gift windows after an event's last Continue, each screenshot, tap and recognition taking its COST on the clock.
    The bottom bar's lever reads "0" in the button's label roi on the map (OCR of GiftGetOverMap.png), so the corner taps
    go on there. tapped_at: the time of the tap that closed each window, s from the start, as shown_at."""

    def __init__(self, context, first):
        self.start, self.first = actions.time.monotonic(), first
        self.shown_at, self.tapped_at = [], []
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        context.run_recognition.side_effect = self.read

    def page(self):
        t = actions.time.monotonic() - self.start
        if t < FADE:
            return "event"
        if not self.shown_at and t >= self.first:
            self.shown_at.append(self.first)
        elif len(self.shown_at) == len(self.tapped_at) == 1 and t >= self.tapped_at[0] + CLOSE_LAG + GAP:
            self.shown_at.append(self.tapped_at[0] + CLOSE_LAG + GAP)
        closed_at = [tap + CLOSE_LAG for tap in self.tapped_at]
        up = any(s <= t and (k >= len(closed_at) or t < closed_at[k]) for k, s in enumerate(self.shown_at))
        return "window" if up else "map"

    def render(self):
        actions.time.sleep(SHOT)
        image = np.zeros((720, 1280, 3), np.uint8)
        image[0, 0, 0] = PAGES.index(page := self.page())
        if page == "event":
            image[640:650, 1080:1180] = (0, 0, 200)
        return image

    def click(self, x, y):
        actions.time.sleep(TAP)
        if self.page() == "window" and len(self.tapped_at) < len(self.shown_at):
            self.tapped_at.append(actions.time.monotonic() - self.start)
        return DEFAULT

    def read(self, name, image, override=None):
        page = PAGES[image[0, 0, 0]]
        if override is None:
            actions.time.sleep(RETRY_ON_WINDOW if (name, page) == ("RetryPopup", "window") else COST.get(name, OCR))
            return SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if (name, page) in {("Event", "event"), ("GiftGet", "window")} else None
        actions.time.sleep(OCR)
        if tuple(override.get(name, {}).get("roi", ())) == tuple(actions.EVENT_BUTTON_LABEL):
            label = "Continue" if page == "event" else "0"
            return SimpleNamespace(all_results=[SimpleNamespace(text=label, box=(1155, 661, 14, 12))])
        return None


@pytest.mark.parametrize("first", [0.45, 0.49, 0.53, 0.57, 0.61])
def test_gift_windows_after_the_last_continue_are_tapped_as_fast_as_one_alone(context, clock, monkeypatch, first):
    # #309 live: a lone gift's window, closed by the next corner tap, was up 0.27-0.33 s; the second of two waited
    # 1.7-2.5 s for GiftGet. first: when the first window shows, which sets where both fall in the tap rhythm.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    windows = GiftWindows(context, first)
    assert actions.Event().run(context, None) is True
    assert len(windows.shown_at) == 2 and len(windows.tapped_at) == 2
    assert max(tap - shown for shown, tap in zip(windows.shown_at, windows.tapped_at)) < 0.5
