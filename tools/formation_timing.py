"""Formation.pick timing from a run's logs (#253): each card tap against the Total Participants readings around it.

    uv run python tools/formation_timing.py <run.log> <maafw.log>

Taps come from run.log (the controller prints each click in the emulator's pixels; this scales them to 1280 wide), the readings from the
ReadText OCR of the participants ROI in maafw.log. Per pick (Clear Selection to `formation re-picked`) it prints
one row per card tap: the gap to the tap before, and the first reading that shows the count up by one with its
delay after the tap. A reading is stamped when its OCR request starts (the screenshot is taken just before).
With fixed waits the delay is bounded by how often the old code looked, so it is an upper bound, not the lag.
`count` is the card tap's number in its pick: a pick with a repeated tap (the new code's) misaligns it.
"""

from __future__ import annotations

import re
import sys

CLICK = re.compile(r"^(\d\d:\d\d:\d\d\.\d{3}) x: (\d+), y: (\d+), width: (\d+)")
MARK = re.compile(r"^(\d\d:\d\d:\d\d\.\d{3}) \[maalc\] (formation re-picked.*)")
TS = re.compile(r"^\[\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d\.\d{3})\]")
TEXT = re.compile(r'"text":"(\d+)\s*/\s*(\d+)"')
# Copies of agent/actions.py's PARTICIPANTS, CLEAR_SELECTION, CARD_TAP_Y and CARD_X: this tool reads logs, not the agent.
ROI = '"roi":[1125,500,100,45]'
CLEAR, CARD_Y = (1145, 479), (290, 488)
CARD_X = [295 + round(132.2 * i) for i in range(6)]


def secs(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def taps(path):
    """[(t, x, y)] in 720p."""
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = CLICK.match(line)
        if m:
            scale = 1280 / int(m[4])
            out.append((secs(m[1]), round(int(m[2]) * scale), round(int(m[3]) * scale)))
    return out


def marks(path):
    return [(secs(m[1]), m[2]) for m in map(MARK.match, open(path, encoding="utf-8", errors="replace")) if m]


def readings(path):
    """[(t, selected)] of the participants OCR, stamped at the request."""
    pending, out = {}, []
    for line in open(path, encoding="utf-8", errors="replace"):
        if "ReadText" not in line:
            continue
        thread = re.search(r"\[(Tx\d+)\]", line)
        stamp = TS.match(line)
        if not thread or not stamp:
            continue
        if ROI in line and "run_recognition" in line:
            pending[thread[1]] = secs(stamp[1])
        elif "OCRer.cpp" in line and thread[1] in pending:
            t = pending.pop(thread[1])
            m = TEXT.search(line)
            out.append((t, int(m[1]) if m else None))
    return out


def card(x, y):
    if y in CARD_Y and min(abs(x - c) for c in CARD_X) < 6:
        return CARD_Y.index(y) * 6 + min(range(6), key=lambda i: abs(x - CARD_X[i]))
    return None


def main(run_log, maafw_log):
    tap_list, mark_list, reads = taps(run_log), marks(run_log), readings(maafw_log)
    print("pick\tcard\ttap\tgap_s\tcount\tfirst_up_s\treads_before_up")
    for p, (end, _) in enumerate(mark_list):
        clears = [t for t, x, y in tap_list if t < end and abs(x - CLEAR[0]) < 6 and abs(y - CLEAR[1]) < 6]
        if not clears:
            continue
        start, last = clears[-1], None
        n = 0
        for t, x, y in (k for k in tap_list if start < k[0] <= end):
            if card(x, y) is None:
                continue
            n += 1
            after = [(rt, c) for rt, c in reads if t <= rt < t + 10]
            up = next(((rt, c) for rt, c in after if c == n), None)
            seen = sum(1 for rt, c in after if up is None or rt < up[0])
            print(f"{p}\t{card(x, y)}\t{t:.3f}\t{'' if last is None else f'{t - last:.2f}'}\t{n}\t"
                  f"{'' if up is None else f'{up[0] - t:.2f}'}\t{seen}")
            last = t


if __name__ == "__main__":
    main(*sys.argv[1:3])
