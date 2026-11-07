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


# From the last Continue tap, live: the event page fades out with the button lit for FADE s, the map shows LEAD s before
# the first GET! window, a tap closes a window CLOSE_LAG s later (#309), the next one shows GAP s after (#309), and the
# screen moves for MOTION s after each of these (the 2026-10-23 window recording, 28 event ends, #511: the map showed
# 0.03-0.47 s before the first window, the screen moved 0.17-0.27 s after a change, and a window came after the map had
# held still for at most 0.23 s).
FADE, CLOSE_LAG, GAP, MOTION = 0.3, 0.1, 0.34, 0.23
LEADS = [0.03, 0.12, 0.21, 0.3, 0.39, 0.47]
# Offline medians with the bot's MaaFramework resource and agent link (#309): a node that reads text about 53 ms, a
# template about 5 ms; RetryPopup's template matches the window's Confirm, and its text is read there too. SHOT and TAP:
# not measured.
COST = {"Connecting": 0.006, "RetryPopup": 0.009, "PopupButton": 0.005, "Event": 0.053, "GiftGet": 0.053, "MirrorMap": 0.005}
OCR, RETRY_ON_WINDOW, SHOT, TAP = 0.053, 0.045, 0.03, 0.01
PAGES = ["event", "window", "map"]
# GiftGetOverMap.png: MirrorMap hits under a GET! window too.
HITS = {("Event", "event"), ("GiftGet", "window"), ("MirrorMap", "window"), ("MirrorMap", "map")}


class Outro:
    """What an event's last Continue leads to: `windows` GET! windows over the map, the first `lead` s after the map shows,
    each screenshot, tap and recognition taking its COST on the clock. The bottom bar's lever reads "0" in the button's
    label roi on the map (OCR of GiftGetOverMap.png), so the corner taps go on there. Times are s from the Continue tap:
    shown_at and tapped_at (the tap that closed it) for each window, last_tap, and still_at, when the map holds still."""

    def __init__(self, context, windows, lead):
        self.windows, self.lead = windows, lead
        self.pressed, self.last_tap, self.shown_at, self.tapped_at = None, None, [], []
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        context.run_recognition.side_effect = self.read

    def now(self):
        return -1.0 if self.pressed is None else actions.time.monotonic() - self.pressed

    def changes(self):
        """When the screen changed: the event page gone, each window shown and closed."""
        return sorted([FADE, *self.shown_at, *(tap + CLOSE_LAG for tap in self.tapped_at)])

    def page(self, t):
        if t < FADE:
            return "event"
        closed = len(self.tapped_at) == len(self.shown_at)
        if closed and len(self.shown_at) < self.windows:
            due = self.tapped_at[-1] + CLOSE_LAG + GAP if self.shown_at else FADE + self.lead
            if t >= due:
                self.shown_at.append(due)
                closed = False
        return "map" if closed and (not self.tapped_at or t >= self.tapped_at[-1] + CLOSE_LAG) else "window"

    @property
    def still_at(self):
        return self.changes()[-1] + MOTION

    def render(self):
        actions.time.sleep(SHOT)
        t = self.now()
        page = self.page(t)
        image = np.full((720, 1280, 3), 60 if page == "event" else 30, np.uint8)
        if page == "event":
            image[640:650, 1080:1180] = (0, 0, 200)
        elif page == "window":
            image[160:560, 300:980] = 120
        if t >= FADE:
            image[680:720, 600:640] = 30 + 20 * (int(t * 30) % 2)  # the bus flame flickers on every frame (same_screen)
            since = t - max(c for c in self.changes() if c <= t)
            if since < MOTION:  # something slides across
                x = int(since / MOTION * 1080)
                image[100:620, x:x + 200] = 200
        image[0, 0, 0] = PAGES.index(page)
        return image

    def click(self, x, y):
        actions.time.sleep(TAP)
        if self.pressed is None and (x, y) == actions.EVENT_BUTTON:
            self.pressed = actions.time.monotonic()
        t = self.now()
        self.last_tap = t
        if self.page(t) == "window" and len(self.tapped_at) < len(self.shown_at):
            self.tapped_at.append(t)
        return DEFAULT

    def read(self, name, image, override=None):
        page = PAGES[image[0, 0, 0]]
        if override is None:
            actions.time.sleep(RETRY_ON_WINDOW if (name, page) == ("RetryPopup", "window") else COST.get(name, OCR))
            return SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if (name, page) in HITS else None
        actions.time.sleep(OCR)
        if tuple(override.get(name, {}).get("roi", ())) == tuple(actions.EVENT_BUTTON_LABEL):
            label = "Continue" if page == "event" else "0"
            return SimpleNamespace(all_results=[SimpleNamespace(text=label, box=(1155, 661, 14, 12))])
        return None


@pytest.mark.parametrize("lead", LEADS)
def test_gift_windows_after_the_last_continue_are_tapped_as_fast_as_one_alone(context, clock, monkeypatch, lead):
    # #309 live: a lone gift's window, closed by the next corner tap, was up 0.27-0.33 s; the second of two waited
    # 1.7-2.5 s for GiftGet. lead sets where both windows fall in the tap rhythm.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    outro = Outro(context, 2, lead)
    assert actions.Event().run(context, None) is True
    assert len(outro.shown_at) == 2 and len(outro.tapped_at) == 2
    assert max(tap - shown for shown, tap in zip(outro.shown_at, outro.tapped_at)) < 0.5


@pytest.mark.parametrize("windows, lead", [(0, 0.0)] + [(n, lead) for n in (1, 2) for lead in LEADS])
def test_an_event_hands_back_once_the_map_it_ends_on_holds_still(context, clock, monkeypatch, windows, lead):
    # #511 live: Event looked at the map 1 s more before it handed back, 1.4-1.6 s after its last corner tap. The map
    # shows between two GET! windows too, so the hand-back waits for it to hold still, and no window is left to MirrorHub.
    monkeypatch.setattr(actions, "page_guard", test_actions.REAL_GUARD)
    outro = Outro(context, windows, lead)
    assert actions.Event().run(context, None) is True
    handed_back = outro.now()
    assert len(outro.tapped_at) == windows
    assert handed_back - outro.last_tap < 0.5
    assert handed_back - outro.still_at < 1.0
