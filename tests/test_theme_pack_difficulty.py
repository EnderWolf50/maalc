"""The theme pack page's difficulty label on floors 6-15 (#386), read by PickThemePack.set_difficulty on the real OCR.

No capture shows the page past floor 5 yet (#853, #855 bring them; #854, #856 the fixtures). The three synthetic pages are
ThemePack.png (floor 2, HARD) with the label box's inside, the arrows and `HARD ///`, painted over in the box's own dark
fill, then INFINITY or EXTREME (uiConfig.difficultyLabel of floors 6-10 and 11-15) drawn in the HARD text's orange in
Bahnschrift Bold Condensed, or nothing (NoLabel). Real MaaFramework and its OCR, in a child process (this file run as a
script), as test_consecutive_ocr.py does.
"""

import pytest
from daily_child import probe_child, run_child, screen

# (capture, floor, want) -> (set_difficulty's result, the floor's HARD as noted, the floor's last log line, HARD for want of a label)
CASES = {
    ("ThemePackInfinity.synthetic.png", 6, True): (True, True, "floor 6: HARD", False),
    ("ThemePackExtreme.synthetic.png", 11, True): (True, True, "floor 11: HARD", False),
    ("ThemePackNoLabel.synthetic.png", 6, True): (True, True, "floor 6: HARD", True),  # unread past floor 5: HARD, no stuck
    ("ThemePackNoLabel.synthetic.png", 15, True): (True, True, "floor 15: HARD", True),
    ("ThemePack.png", 7, True): (True, True, "floor 7: HARD", False),  # a page past floor 5 still showing HARD
    ("ThemePackNoLabel.synthetic.png", 5, True): (False, None, None, False),  # target 5 as before: unread up to floor 5 is the stuck
    ("ThemePack.png", 3, True): (True, True, "floor 3: HARD", False),
}


def child():
    def body(context, actions, out):
        from agent_patch import rebind

        import run_start_actions
        out["cases"] = []
        for name, floor, want in CASES:
            image, lines, taps = screen(name), [], []
            rebind("screen", lambda context, image=image: image)  # the page stays: page_guard and until look at it
            rebind("log", lines.append)
            rebind("tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
            actions.RUN.clear()
            result = run_start_actions.PickThemePack.set_difficulty(context, floor, want)
            out["cases"].append([name, floor, want, result, actions.RUN.get("floors_hard", {}).get(floor), lines[-1] if lines else None,
                                 any("no difficulty label read" in x for x in lines), taps])

    probe_child(body)


def read():
    return {(name, floor, want): rest for name, floor, want, *rest in run_child(__file__)["cases"]}


@pytest.mark.parametrize("case", list(CASES), ids=lambda c: f"{c[0]}-floor{c[1]}")
def test_the_label_or_its_absence_gives_the_floor_its_difficulty_without_a_switch(case):
    *got, taps = read()[case]
    assert tuple(got) == CASES[case]
    assert taps == []


if __name__ == "__main__":
    child()
