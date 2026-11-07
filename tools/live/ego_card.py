"""A sinner's E.G.O card over a battle's planning phase (#468): open it while the bot runs, and time how long it stays.

    uv run --group probe python tools/live/ego_card.py [--port 16384] open --slot N --out DIR [--hold 2.5] [--attempts 4] [--timeout 1200]
    uv run --group probe python tools/live/ego_card.py score IMAGE...

**open** waits for a planning phase (BattleTurn's templates), long-presses the portrait under skill slot N (0 the
leftmost; the slots counted from the Win Rate label, as battle.slot_xs does) for --hold seconds, then logs when the
card shows (with how many cards its row holds) and when it goes, each line with its wall time, and saves both frames to
--out. The press blocks until the finger lifts, so "shown" is the first look after the lift: a card that came up
during the press stayed longer than the logged time. A press that brings no card in 3 s is tried again 3 s later, at
the planning phase then up. Exit 0 when a card opened and closed, 1 when one stayed up 30 s, 2 when --attempts presses
opened none or --timeout passed. A live test owns the emulator first (the maalc-live-test skill); the press races the
bot, which acts on the planning phase too.

**score** prints each EgoCard part's score (grey TM_CCOEFF_NORMED in its roi, as tests/test_ego_card.py scores them)
and where it matched, on each image.

The card and the planning phase are read with the pipeline's own nodes, EgoCard and BattleTurn, from this checkout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from functools import cache
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "tools", REPO / "agent"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import battle  # noqa: E402

PIPELINE = REPO / "assets/resource/base/pipeline"
IMAGES = REPO / "assets/resource/base/image"
PORTRAIT_Y = 665  # actions.SLOT_PORTRAIT_Y: a slot's portrait, under its skills
NO_CARD = 3  # s after a press with no card: that press opened none
CARD_LIMIT = 30  # s a card may stay up after the press before it counts as a failure


@cache
def nodes() -> dict:
    """Every pipeline node, read without the whole-line // comments (json.load fails on them)."""
    found = {}
    for path in sorted(PIPELINE.glob("*.json")):
        lines = path.read_text(encoding="utf-8").splitlines()
        found |= json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))
    return found


@cache
def parts(name: str) -> list[tuple[list, list, float]]:
    """(grey templates, roi, threshold) of each TemplateMatch of a node: the node itself, or each part of its And."""
    spec = nodes()[name]
    specs = spec["all_of"] if spec.get("recognition") == "And" else [spec]
    out = []
    for s in specs:
        files = s["template"] if isinstance(s["template"], list) else [s["template"]]
        out.append(([cv2.imread(str(IMAGES / f), cv2.IMREAD_GRAYSCALE) for f in files], s["roi"], s["threshold"]))
    return out


def best(gray, templates, roi) -> tuple[float, int, int]:
    """(score, x, y) of the best match of any template inside roi."""
    x, y, w, h = roi
    top = (-1.0, 0, 0)
    for t in templates:
        _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(gray[y:y + h, x:x + w], t, cv2.TM_CCOEFF_NORMED))
        top = max(top, (score, x + loc[0], y + loc[1]))
    return top


def grey(image):
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def card_up(image) -> bool:
    """EgoCard hits: every part of its And at its threshold."""
    g = grey(image)
    return all(best(g, t, roi)[0] >= threshold for t, roi, threshold in parts("EgoCard"))


CARD_BAND = (0, 100, 1280, 100)  # the row of cards' Details buttons, the whole width
# A Details button in the row, on the four captures of the card (one each of one card blue and green, two, three): the
# side cards of three score 0.87, the cards of two 0.96 and 0.93, a single card 1.00. cards() runs only on a frame
# card_up() already took for the card, so another screen's score does not count.
CARD_PEAK = 0.85
CARD_GAP = 100  # px between two cards' Details at least (277 apart in a row of three, 317 in a row of two)


def cards(image) -> int:
    """How many cards the row shows: Details buttons across the band, each a peak at CARD_PEAK or more."""
    (templates, _, _), _ = parts("EgoCard")
    x, y, w, h = CARD_BAND
    scores = cv2.matchTemplate(grey(image)[y:y + h, x:x + w], templates[0], cv2.TM_CCOEFF_NORMED).max(axis=0)
    found = []
    for i in scores.argsort()[::-1]:
        if scores[i] < CARD_PEAK:
            break
        if all(abs(i - j) >= CARD_GAP for j in found):
            found.append(i)
    return len(found)


def win_rate_x(image) -> int | None:
    """The Win Rate label's x when BattleTurn hits (a planning phase), else None."""
    (templates, roi, threshold), = parts("BattleTurn")
    score, x, _ = best(grey(image), templates, roi)
    return x if score >= threshold else None


def open_card(grab, press, say, slot: int, hold: float, attempts: int, timeout: float = 1200, shot=None,
              clock=time.monotonic, sleep=time.sleep) -> int:
    """Long-press slot `slot`'s portrait at a planning phase, then time the card: 0 it opened and closed, 1 it stayed up,
    2 no press opened one."""
    end, tried = clock() + timeout, 0
    while clock() < end and tried < attempts:
        image = grab()
        x = win_rate_x(image)
        if x is None:
            sleep(0.1)
            continue
        xs = battle.slot_xs(x)
        sx = xs[min(slot, len(xs) - 1)]
        tried += 1
        say(f"planning phase (Win Rate at x {x}, {len(xs)} slots): long press {hold} s on slot {xs.index(sx)} ({sx}, {PORTRAIT_Y}), try {tried}")
        press(sx, PORTRAIT_Y, hold)
        pressed, opened = clock(), None
        while clock() < pressed + CARD_LIMIT:
            image = grab()
            up = card_up(image)
            if up and opened is None:
                opened = clock()
                n = cards(image)
                say(f"card open: {n} card{'s' if n > 1 else ''}")
                if shot:
                    shot("card-open", image)
            elif not up and opened is not None:
                say(f"card gone {clock() - opened:.1f} s after it showed")
                if shot:
                    shot("card-gone", image)
                return 0
            elif not up and clock() > pressed + NO_CARD:
                break
            sleep(0.1)
        if opened is not None:
            say(f"card still up {CARD_LIMIT} s after the press")
            return 1
        say("no card after the press")
        sleep(3)
    say("no press opened a card" if tried >= attempts else f"no card in {timeout:.0f} s")
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=16384)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("open")
    p.add_argument("--slot", type=int, required=True, help="the skill slot whose portrait is pressed, 0 the leftmost")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--hold", type=float, default=2.5)
    p.add_argument("--attempts", type=int, default=4)
    p.add_argument("--timeout", type=float, default=1200)
    p = sub.add_parser("score")
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)
    if a.command == "score":
        for f in a.images:
            g = grey(cv2.imread(f))
            scores = [best(g, t, roi) for t, roi, _ in parts("EgoCard")]
            hit = all(s >= threshold for (s, _, _), (_, _, threshold) in zip(scores, parts("EgoCard")))
            print(f"{Path(f).name}: " + ", ".join(f"{s:.3f} at ({x}, {y})" for s, x, y in scores) + (" hit" if hit else " miss"))
        return 0
    from live.device import connect, press, stamp

    ctl = connect(a.port)
    a.out.mkdir(parents=True, exist_ok=True)

    def shot(name, image):
        cv2.imwrite(str(a.out / f"{stamp()}-{name}.png"), image)

    return open_card(lambda: ctl.post_screencap().wait().get(), lambda x, y, s: press(ctl, x, y, s),
                     lambda line: print(stamp(), line, flush=True), a.slot, a.hold, a.attempts, a.timeout, shot)


if __name__ == "__main__":
    sys.exit(main())
