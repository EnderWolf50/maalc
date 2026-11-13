"""An encounter's pages: the event and its choices, the reward cards, and the gift choice."""

import functools
import json
import re
import time

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import gift_search
import recovery
import rewards
import run_start
import shop
from actions import (ENDS_ON, GET_TITLE, GIFT_IDS, GIFT_NAMES, POPUPS, RUN, PageEnded, avoided_gifts, columns,
                     current_run, data, gone, hands_back, log, moved, ocr, on_page, page_guard, screen, scroll, shows,
                     still, stuck, tap, text, until, want_of)
from ocrtext import compact, has
from settings import data_dir


# Events, reward cards and gifts (spec 03 sections 10-12).
EVENT_BUTTON = (1130, 645)  # SKIP / Proceed / Continue / Commence share it; grey while it does nothing
EVENT_STORY = [60, 320, 580, 200]
CHOICES_HEADER = [690, 105, 170, 45]
CHOICE_ROWS = [690, 170, 480, 440]
CHECK_PROMPT = [850, 295, 300, 50]
EVENT_PORTRAIT_X = [77 + round(69.3 * i) for i in range(12)]  # 7 in a boss's mid-battle event, from the left
EVENT_PORTRAIT_Y = 655
EVENT_NEUTRAL = (5, 5)  # top-left corner: nothing there on any event page
EVENT_CARD = (940, 195)  # a check's card at the right: alone, it waits for this tap to open its prompt (card_alone)
EVENT_TEXT_TAPS = 30
# A text tap every EVENT_TAP_EVERY s, the lit button's pixels looked at after each, the page's text only every
# EVENT_READ_EVERY taps: live 2026-10-20, a screenshot and 3 OCRs after each tap made it one every 0.3-1.1 s whatever
# the wait, and the text kept up at 0.15 s (no tap lost; the user's own taps 0.15 s).
EVENT_TAP_EVERY, EVENT_READ_EVERY = 0.15, 3
EVENT_TAKE = 1.5  # s a tap on an event page has to show
EVENT_LABELS = {"skip", "proceed", "continue", "commence"}  # the Event node's expected, compact()ed
EVENT_BUTTON_LABEL = [1040, 612, 190, 66]  # the Event node's roi; on most maps the bottom bar's lever reads there (#511)
# s the map an event ends on holds still before Event hands back: GET! windows come over it, and close on the corner taps
# (#309). The 2026-10-23 window recording, 28 event ends (#511): the map held still at most 0.23 s before a window came;
# the last map stopped moving 0-0.27 s after it showed.
EVENT_MAP_REST = 0.4
EVENT_LIMIT = 180  # s one event may take before recovery L1 (AALC allows 300); a boss quiz of several rounds stays well under
EVENT_ODDS_WAIT = 2.0  # s after a check's prompt first shows that no odds read hands back to MirrorHub, not a sinner (#380); live: the odds came 1.8 s after
EVENT_GAP = 30  # s between two Event calls after which the next call is another event
EVENT_LEAST = 0.5 # s after a tap before the screen counts as moved: a fade's first frames are the same page
CHOICE_X = 925  # the option list's middle
CHOICE_STEP = 150  # px per drag of a list that scrolls: about a card (130-150 px), so none is skipped
CHOICE_SCROLLS = 6  # drags at most to an end of the list


@functools.cache
def event_table():
    """data/event_table.json's events (spec 03 section 10, #93), read once."""
    return json.loads((data_dir() / "event_table.json").read_text(encoding="utf-8"))["events"]


def red_button(image):
    b, g, r = image[640:650, 1080:1180].reshape(-1, 3).mean(0)
    return r > 150 and r - b > 70


def card_alone(image):
    """A check's card at the right with nothing under it (live 2026-10-28, J1, tests/screens/LuxEventCard.png): a
    Luxcavation battle's event shows it after SKIP, SKIP grey, and goes on only once the card is tapped. Its lit frame's
    bottom strip over a black panel; under the prompt or a check's result the panel is lit."""
    b, g, r = image[230:240, 760:1120].reshape(-1, 3).mean(0)
    return r > 90 and g > 75 and image[290:300, 700:1180].mean() < 10


@AgentServer.custom_action("Event")
class Event(CustomAction):
    """One step on an event page: press the lit button, open a check's card, pick a checker or an option, else advance
    the text (spec 03 section 10). The mirror's, and a Luxcavation battle's (ExpText, J1)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # One event's clock: a call more than EVENT_GAP s after the last starts the next event's (#92).
        now = time.monotonic()
        event = RUN.get("event")
        if event is None or now - event["last"] > EVENT_GAP:
            event = RUN["event"] = {"since": now, "last": now, "checked": set()}
        event["last"] = now
        if now - event["since"] > EVENT_LIMIT:
            RUN.pop("event")
            return stuck(f"one event went on over {EVENT_LIMIT} s")
        image = still(context)
        if image is None:
            log("event: the page did not hold still; MirrorHub looks again")
            return True
        tried = RUN.setdefault("event_tried", set())  # this question's options a tap did nothing on
        checked = event["checked"]  # portraits a tap did nothing on in this check
        if red_button(image):
            Event.advance(context, image, pressed_at=Event.press(context))
        elif card_alone(image):
            tap(context, *EVENT_CARD, wait=0)
            Event.settle(context, image)
        elif has(text(context, image, CHECK_PROMPT), "Choose a character"):
            # One read per portrait: read as a row, neighbouring captions run together ("HighVery Low").
            captions = [(text(context, image, [x - 38, 605, 76, 24], only_rec=True), x) for x in EVENT_PORTRAIT_X]
            # The odds are drawn after the prompt (#380): in the first EVENT_ODDS_WAIT s with none read, no blind first
            # sinner; past it a check that never draws them goes on sinner by sinner (#92).
            if all(rewards.odds_rank(t) is None for t, _ in captions) and now - event.setdefault("prompt_at", now) < EVENT_ODDS_WAIT:
                log("event check: no odds read yet; MirrorHub looks again")
                return True
            i = rewards.pick_checker(captions, checked, lowest=event.get("lowest", False))
            if i is None:  # all the odds read were tried: the next sinner not tried yet, round again when all are
                i = next((k for k in range(len(captions)) if k not in checked), None)
                if i is None:
                    checked.clear()
                    i = 0
            log(f"event check: {', '.join(t for t, _ in captions) or 'no odds read'}: take sinner {i + 1}")
            tap(context, captions[i][1], EVENT_PORTRAIT_Y, wait=0)
            if Event.settle(context, image) is None:
                checked.add(i)
        elif has(text(context, image, CHOICES_HEADER), "Choices"):
            checked.clear()
            event.pop("prompt_at", None)
            run = RUN if "lux" in RUN else current_run(context)  # a Luxcavation battle's (J1): its team, no Mirror run plan
            story = [t for t, _ in sorted(ocr(context, image, EVENT_STORY), key=lambda r: (r[1][1], r[1][0]))]
            scrolls = rewards.choice_scrollbar(image) or any(None in c for c in rewards.choice_cards(image))
            options, image = self.read_choices(context, image, scrolls)
            if not options:
                return True
            overrides = data("events.yaml") | {o["question"]: o["option"] for o in run.get("settings", {}).get("event_overrides", [])}
            question = next(filter(None, (run_start.match_name(t, list(overrides)) for t in story + [" ".join(story)])), None) if overrides else None
            known = rewards.match_event(" ".join(story), event_table())
            # Grey options (taken in an earlier round of the same questions) and ones a tap did nothing on are closed.
            closed = {k for k, (t, is_open, _) in enumerate(options) if t in tried or not is_open}
            i, lowest = rewards.choice_plan([t for t, _, _ in options], run["team"]["keyword"], overrides.get(question), closed, known,
                                            want_of(run))
            shown = " | ".join(("(closed) " if k in closed else "") + t for k, (t, _, _) in enumerate(options))
            if i is None:
                log(f"event: {shown}: all closed, scroll for more")
                scroll(context, CHOICE_X, 420, 0, -CHOICE_STEP)  # in case the list scrolls with no sign of it
                return True
            log(f"event: {shown}: take {options[i][0]!r}" + (f" (override {question!r})" if question else "")
                + ("" if known else " (not in the event table: hint rules)") + (" (a wanted gift only a failed check gives: lowest odds)" if lowest else ""))
            y, image = self.into_view(context, image, options, i) if scrolls else (options[i][2], image)
            if y is None:
                log(f"event: {options[i][0]!r} not found again in the list")
                return True
            event["lowest"] = lowest  # for this option's check; the next option taken sets its own
            tap(context, CHOICE_X, y, wait=0)
            if until(context, lambda im: not Event.panel_same(image, im), timeout=EVENT_TAKE) is None:
                log(f"event: {options[i][0]!r} did nothing: try another")
                tried.add(options[i][0])
            # A lit card changes the panel before the page goes: MirrorHub reading Choices would take one again.
            elif (after := until(context, gone(context, {"roi": CHOICES_HEADER, "expected": "Choices"}, image), timeout=EVENT_TAKE)) is None:
                log(f"event: Choices still up {EVENT_TAKE} s after taking {options[i][0]!r}")
            else:
                Event.advance(context, after)
        else:
            tried.clear()
            Event.advance(context, image)
        return True

    @staticmethod
    def press(context):
        """Tap the lit button, and return when (time.monotonic()): the page it leads to starts its question's and its
        check's tries over."""
        RUN.get("event_tried", set()).clear()
        if event := RUN.get("event"):
            event["checked"].clear()
            event.pop("prompt_at", None)
        tap(context, *EVENT_BUTTON, wait=0)
        return time.monotonic()

    @staticmethod
    def advance(context, image, pressed_at=None):
        """Text running on (the button grey, or a press of it lit fading out): taps on a dead corner show it line by
        line, and a button that lights is pressed; keep on until there is something else to act on, for MirrorHub's
        next look (#557: handed back, a lit button waited 0.6-1.2 s for it).

        A Choices page or a check prompt shows up to EVENT_READ_EVERY - 1 taps late: a tap on the dead corner picks nothing.
        pressed_at: time.monotonic() of a tap on the lit button just now, image the screen it was tapped on (#188:
        MirrorHub's look after it paused the taps 1.6-5.3 s). The button stays lit while the press fades out, its
        label read once a screen that has not moved since the last (1 OCR, besides the page check every
        EVENT_READ_EVERY taps); the first screen without it is read before the next tap (3 OCRs). Lit with another
        label (SKIP, then Continue), it is the next button; lit EVENT_TAKE s on, the press was lost.
        Only two labels read whole tell another button: one read empty or in part while it fades ("Contnue") is not,
        as MirrorHub's Event node would still match the fading button and press it twice.
        A next button is pressed on the first screen that has not moved since the last (a press mid-fade is lost, #273),
        its label read whole, else MirrorHub presses it. A popup over it (CONNECTING after a taken option) is waited
        out as page_guard waits, before MirrorHub would answer it.
        On the map the event ends on, the taps go on until the screen a look saw it on has not changed for
        EVENT_MAP_REST s (#511).
        """
        last, pressed_label = 0.0, None  # None: not in a press's fade (any more)
        if pressed_at is not None:
            last, pressed_label = pressed_at, compact(text(context, image, EVENT_BUTTON_LABEL))
        shot_at = still_since = time.monotonic()
        thumb, map_seen_at = recovery.thumb(image), None
        for n in range(1, EVENT_TEXT_TAPS + 1):
            time.sleep(max(0.0, last + EVENT_TAP_EVERY - time.monotonic()))
            last = time.monotonic()
            if (n - 1) % EVENT_READ_EVERY == 0:  # on the last read's screenshot (#118, ADR 0007): an OCR a tap would undo the 0.15 s
                try:
                    page_guard(context, "Event", image=image)
                except PageEnded:
                    map_seen_at = shot_at
            if map_seen_at is not None and still_since <= map_seen_at and shot_at - still_since >= EVENT_MAP_REST:
                raise PageEnded("Event")
            tap(context, *EVENT_NEUTRAL, wait=0)
            image, shot_at = screen(context), time.monotonic()
            before, thumb = thumb, recovery.thumb(image)
            if moved := not recovery.same_screen(before, thumb):
                still_since = shot_at
            if red_button(image):
                if pressed_label is not None and time.monotonic() - pressed_at >= EVENT_TAKE:
                    break
                if moved:
                    continue
                label = compact(text(context, image, EVENT_BUTTON_LABEL))
                if pressed_label is not None and not (pressed_label in EVENT_LABELS and label in EVENT_LABELS and label != pressed_label):
                    continue
                if label not in EVENT_LABELS:
                    break
                if on_page(context, image, *POPUPS):
                    image = page_guard(context, "Event")
                    thumb = recovery.thumb(image)
                    continue
                pressed_at = last = Event.press(context)
                pressed_label = label
                continue
            read = n % EVENT_READ_EVERY == 0 or pressed_label is not None
            pressed_label = None
            if card_alone(image):
                break
            if not read:
                continue
            # The label roi reads empty off the event page, on a map too (MapCostFloor3.png): the map waits for the guard.
            if not text(context, image, EVENT_BUTTON_LABEL) and not on_page(context, image, *ENDS_ON["Event"]):
                break
            if any(has(text(context, image, roi), k) for k, roi in (("Choices", CHOICES_HEADER), ("Choose a character", CHECK_PROMPT))):
                break

    @staticmethod
    def settle(context, before):
        """Wait for a tap to show on screen, at most EVENT_TAKE s; MirrorHub looks again after.

        Returns the screen that moved, None when the tap did nothing.
        """
        return until(context, lambda im: moved(before, im), timeout=EVENT_TAKE, least=EVENT_LEAST)

    @staticmethod
    def panel_same(before, after):
        """Whether the choice panel looks as it did: a tap on it did nothing."""
        x, y, w, h = CHOICE_ROWS
        return recovery.same_screen(*(recovery.thumb(i[y:y + h, x:x + w]) for i in (before, after)))

    @staticmethod
    def shown(context, image, scrolls):
        """The options on screen as [(text, y of its first line)]; in a list that scrolls only those whose frame shows whole."""
        rows = [(" ".join(lines), y) for y, lines in Event.rows(ocr(context, image, CHOICE_ROWS))]
        if not scrolls:
            return rows
        whole = [(top, bottom) for top, bottom in rewards.choice_cards(image) if top is not None and bottom is not None]
        return [(t, y) for t, y in rows if any(top < y < bottom for top, bottom in whole)]

    @staticmethod
    def drag(context, image, dy):
        """Scroll the option list by dy px (dy < 0 shows what is below); the screen after, None when it did not move."""
        page_guard(context, "Event", image=image)
        scroll(context, CHOICE_X, 420 if dy < 0 else 260, 0, dy)
        after = screen(context)
        # Pixel by pixel, not panel_same's thumbnails: cards about a drag apart look alike in those.
        y0, y1 = rewards.CHOICE_LIST_Y
        return after if np.abs(after[y0:y1, 690:1170].astype(int) - image[y0:y1, 690:1170]).mean() >= 2 else None

    @staticmethod
    def read_choices(context, image, scrolls):
        """Every option as [(text, open, y of its first line where read)] top to bottom, and the screen it ends on.

        A list that scrolls (#93) is dragged to its top, then down a card at a time without a fling, each
        option read once its frame shows whole; the same text read again is the same option.
        """
        if not scrolls:
            return [(t, rewards.choice_open(image, y), y) for t, y in Event.shown(context, image, False)], image
        for _ in range(CHOICE_SCROLLS):  # to the top
            after = Event.drag(context, image, CHOICE_STEP)
            if after is None:
                break
            image = after
        options = []
        for _ in range(CHOICE_SCROLLS):
            for t, y in Event.shown(context, image, True):
                if not run_start.match_name(t, [o[0] for o in options], margin=0):
                    options.append((t, rewards.choice_open(image, y), y))
            after = Event.drag(context, image, -CHOICE_STEP)
            if after is None:
                break
            image = after
        if not options:  # no whole frame read: take the list as it reads
            return Event.read_choices(context, image, False)
        return options, image

    @staticmethod
    def into_view(context, image, options, i):
        """(y to tap, screen) for option i of a list that scrolls, dragged until its frame shows whole; (None, screen) when not found.

        A screen with none of the options read (#196: one the read missed) is dragged on the same way, up first
        (read_choices ends at the bottom), turning once at an end of the list. It gives up at an end of the
        list the options on screen put the pick beyond, or at the second end with none of them read.
        """
        texts = [t for t, _, _ in options]
        step, turned = CHOICE_STEP, False
        for _ in range(2 * CHOICE_SCROLLS + 1):
            seen = {}  # option index -> y, for the options on screen
            for t, y in Event.shown(context, image, True):
                if name := run_start.match_name(t, texts, margin=0):
                    seen.setdefault(texts.index(name), y)
            if i in seen:
                return seen[i], image
            if seen:
                step = CHOICE_STEP if min(seen) > i else -CHOICE_STEP
            after = Event.drag(context, image, step)
            if after is None:
                if turned or seen:  # both ends with none read, or the end the options on screen put it beyond
                    return None, image
                step, turned = -step, True
            else:
                image = after
        return None, image

    @staticmethod
    def rows(results):
        """Option rows top to bottom as (y of the first line, [lines]); a gap over 50 px starts a new row."""
        rows = []
        for t, (x, y, w, h) in sorted(results, key=lambda r: r[1][1]):
            if rows and y - rows[-1][2] < 50:
                rows[-1][1].append(t)
                rows[-1][2] = y
            else:
                rows.append([y + h // 2, [t], y])
        return [(y, lines) for y, lines, _ in rows]


REWARD_TITLE = [290, 112, 490, 48]
REWARD_CARDS = [130, 190, 1020, 280]  # the cards, for still(): they slide in over 0.27-0.97 s (#334)
CARD_TEXT = [130, 340, 1020, 120]
SELECTABLE = [880, 115, 170, 40]
CARD_CONFIRM = (808, 528)
CARD_ROUNDS = 12  # a look is a round: per tap up to CARD_REREADS rereads and the tap (a card of 3 that never reads: 9), then Confirm
CARD_REREADS = 2  # a card that reads as nothing is looked at again this often per tap before it is taken as it reads


@AgentServer.custom_action("RewardCard")
class RewardCard(CustomAction):
    """Take reward cards in the team's order until Selectable n/m is full, then Confirm; never Cancel (spec 03 section 11).

    #334: each look waits for the cards to stop moving, which the game ignores taps during. A card counts as taken
    when Selectable's count went up; a tap that did not raise it is made again on the same card.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        order = current_run(context)["team"]["reward_cards"]
        taken, rereads = set(), 0
        for _ in range(CARD_ROUNDS):
            image = page_guard(context, "RewardCard", image=still(context, roi=REWARD_CARDS, runs=2))
            m = re.search(r"(\d)\s*/\s*(\d)", text(context, image, SELECTABLE))
            if m and m[1] == m[2]:
                tap(context, *CARD_CONFIRM, wait=0)
                get = shows(context, GET_TITLE, "GET")  # a gift's popup leaves the title up: MirrorHub hands it to GiftGet (#377)
                until(context, lambda im: not has(text(context, im, REWARD_TITLE), "Encounter Reward") or get(im))
                return True
            if not m:  # no count to tell a tap by: the page is not up
                continue
            cards = columns(ocr(context, image, CARD_TEXT))
            if not cards or len(taken) == len(cards):
                time.sleep(1)  # kept (#58): the cards still slide in; the next round's still() reads them at rest
                continue
            types = [rewards.card_type(" ".join(lines)) for _, lines in cards]
            if None in types and rereads < CARD_REREADS:  # still sliding in, or misread: not ready
                rereads += 1
                continue
            i = rewards.pick_card(types, order, taken)
            log(f"reward cards: {', '.join(str(t) for t in types)}: take {types[i] or ' '.join(cards[i][1])!r}")
            tap(context, cards[i][0], 300, wait=0)
            before = int(m[1])

            def picked(im):  # Selectable's count went up: not a misread digit, not a tap that dropped the card again
                n = re.search(r"(\d)\s*/\s*\d", text(context, im, SELECTABLE))
                return n is not None and int(n[1]) > before
            if until(context, picked, timeout=1.5) is not None:
                taken.add(i)
                rereads = 0
        return stuck("reward card page did not fill Selectable")


GIFT_CARDS = [100, 150, 1080, 410]  # 1-4 cards; on the boss page the Mounting Trials half below each
GIFT_COUNT = [1060, 555, 160, 50]  # "Select 0/2"; "Select" alone on a page that takes one card (#494)
GIFT_SELECT = (1138, 579)
REFUSE_GIFT = [870, 560, 160, 40]
# A boss card's trial half, around the card's centre x: the Enemy Level Up badge's "+N" at its left (from x - 103), the
# trial's icon, its name, then its effect line, wrapped to two or three lines (tests/screens/BossGiftTrials*.png, #381).
TRIAL_HALF = (-125, 438, 250, 105)  # x from the centre, y, w, h
# Measured on the 10 boss cards of tests/screens (16 with two more 2026-10-28 frames, not committed):
TRIAL_NAME_FOOT = 470  # a name's box starts above it (y 444-451), an effect line's below (475+)
TRIAL_BADGE_X = -60  # a "+N" box starts left of the centre by more (-103), the name's by at most 24


def gift_count(context, image=None):
    return gift_search.select_count(text(context, screen(context) if image is None else image, GIFT_COUNT))


def gift_tier(image, x):
    """The tier (1-5) of the gift card centred at x, from the yellow numeral over its icon (shop.numeral), or None (#381).

    The numeral is 17 px tall, its top at y 212 on a boss page (220 on a fight's), left of the centre, I-III centred
    at x - 13 to x - 9; the icon's own yellow sits right of the window. Its strokes are counted as shop.tier counts a
    cell's: 2 px under the top and 3 over the foot. Every gift card of tests/screens (11 on 4 captures, tiers I-II)
    reads its gift data's tier (test_trial_screens.py), as do 6 more on two 2026-10-28 frames (a III among them); a IV or
    V is on no capture yet.
    """
    mask = shop.yellow(image[203:250, x - 26:x + 2])
    rows = np.flatnonzero(mask.any(axis=1))
    return shop.numeral(mask, rows[0] + 2, rows[0] + 14) if len(rows) >= 8 else None


def trial_card(context, image, x):
    """(Enemy Level Up N or None, the trial name's OCR, its effect line's OCR) of the boss gift card centred at x (#381).

    One OCR over the card's trial half (TRIAL_HALF): the whole page's misses badges (none of BossGiftTrials.png's 3);
    the half's read every badge, name and effect line of the 10 boss cards in tests/screens (test_trial_screens.py) and
    of 6 more on two 2026-10-28 frames. A wrapped effect line joins top to bottom.
    The icon reads as one or two stray letters ("X", "0x"): no name is that short.
    """
    dx, y, w, h = TRIAL_HALF
    level, name, line = None, [], []
    for t, (bx, by, _, _) in sorted(ocr(context, image, [x + dx, y, w, h]), key=lambda r: (r[1][1], r[1][0])):
        badge = re.fullmatch(r"\+\s*(\d)", t.strip())
        if badge and bx < x + TRIAL_BADGE_X:
            level = int(badge[1])
        elif by >= TRIAL_NAME_FOOT:
            line.append(t)
        elif len(compact(t)) >= 3 and not has(t, "Mounting"):
            name.append(t)
    return level, " ".join(name), " ".join(line)


def gift_cards(context, image):
    """(card centres x, each card's [(y, OCR line)], whether Mounting Trials hang under the cards) of a gift choice page (#418).

    The "Acquire E.G.O Gift" tab sits on each card's top-right corner, 114 px right of its centre; no tab, no centres.
    """
    results = ocr(context, image, GIFT_CARDS)
    centres = sorted(x + w - 114 for t, (x, y, w, h) in results if has(t, "Acquire"))
    lines = [[] for _ in centres]
    for t, (x, y, w, h) in results:
        i = min(range(len(centres)), key=lambda i: abs(centres[i] - x - w // 2), default=None)
        if i is not None and abs(centres[i] - x - w // 2) < 130 and not has(t, "Acquire"):
            lines[i].append((y, t))
    return centres, lines, any(has(t, "Mounting") for t, _ in results)


@AgentServer.custom_action("PickGift")
class PickGift(CustomAction):
    """Gift choice after a fight, an event or a boss: best cards until Select n/m is full, then Select (spec 03 section 12).

    Each card scores by its category (rewards.gift_score): pack-want 9 > want 6 > material 5.5 > main keyword 3 > other 2 >
    owned 0 (#416). When Mounting Trials hang under them (after a boss), each scores gift (main and other with its tier) -
    (trial + level x Enemy Level Up N), the trial told from the pool of the floor just cleared
    (data/trials.yaml, #381). Refuse Gift is never pressed: it hands out random trials.
    A gift the team avoids (#90) comes last: taken only when nothing else fills the count.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        centres, lines, trials = gift_cards(context, image)
        if not centres:
            return True  # page fading in or out: let MirrorHub look again
        table = data("trials.yaml")
        # The pool of the floor just cleared; every trial when the floor is unknown (the agent restarted mid-run).
        pool = rewards.trials_of(table, run.get("floor")) or rewards.trials_of(table, None)
        overrides = {o["trial"]: o["risk"] for o in run["settings"]["trial_risk_overrides"]}
        scores = rewards.scores(pool, table["model"], run.get("trial_coins", 0), overrides)
        avoid = [g["name"] for g in avoided_gifts(run["team"])]
        wanting = want_of(run)
        cards, names = [], []
        for x, card in zip(centres, lines):
            gift = " ".join(t for y, t in card if y < 410)
            owned = any(compact(t) == "owned" for _, t in card)
            kind = rewards.gift_kind(gift, run["team"]["keyword"], owned, avoid)
            gift_id = rewards.card_gift(card, GIFT_IDS)
            label = GIFT_NAMES[gift_id] if gift_id else repr(rewards.card_title(card))
            want = wanting(gift_id) if gift_id else None
            name, tier, cost, trial_note = None, None, None, None
            if trials:  # the tier counts on the boss page only (#381); a fight's page stays main > other > owned
                tier = gift_tier(image, x)
                level, read, line = trial_card(context, image, x)
                name, how = rewards.read_trial(read, line, pool)
                score = scores[name] if name else max(scores.values())  # unread: the pool's worst
                cost = rewards.burden(score, level, table["model"])
                trial_note = f"{name or '?'} +{'?' if level is None else level} score {score:g}"
                if not name or compact(read) != compact(name):  # the name read is not the trial's: what was, for the log
                    trial_note += f" ({f'by its {how}' if how else 'unread: the pool worst'}, read {read!r} / {line!r})"
            cards.append(rewards.Card(kind, tier, cost, label, gift_id, trial_note, rewards.category(kind, want)))
            names.append(name)
        ranked = rewards.rank_gifts(cards)
        log("gifts: " + ", ".join(rewards.card_line(c) for c in cards) + f": order {ranked}")

        def pick(i):
            before = gift_count(context, page_guard(context, "GiftChoice"))
            tap(context, centres[i], 300, wait=0)
            until(context, lambda im: gift_count(context, im) != before, timeout=1.5)

        taken = rewards.pick_gifts(ranked, lambda: text(context, screen(context), GIFT_COUNT), pick, trials)
        for _ in range(3):
            page_guard(context, "GiftChoice")
            tap(context, *GIFT_SELECT, wait=0)
            if until(context, lambda im: not has(text(context, im, REFUSE_GIFT), "Refuse")) is not None:
                # The run's Coin Power units so far, for the budget of pools past early_pools (spec 03 section 12)
                RUN["owned"] = RUN.get("owned", []) + [cards[i].gift_id for i in taken if cards[i].gift_id]  # held from now on
                coins = sum(table["trials"][names[i]]["effects"].get("coin", 0) for i in taken if names[i])
                if coins:
                    RUN["trial_coins"] = run.get("trial_coins", 0) + coins
                    log(f"trials: {RUN['trial_coins']} Coin Power units this run")
                return True
        return stuck("Select did not take the gifts")
