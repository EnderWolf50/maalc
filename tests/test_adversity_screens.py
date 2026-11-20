"""The Adversity page's one tap on the synthetic capture, through the real OCR and the real AdversityPage node (#851).

PassAdversity finds Challenge by its text, as no live capture shows where it sits yet (#855), and taps nothing else: on
tests/screens/AdversityPage.synthetic.png the tap lands on Challenge, not on a card. The page then gives way to the next
screen (passed) or stays up (the game wants one chosen: the task stops). It runs inside a real MaaFramework task
(resource bundle loaded, a still controller); the pytest process holds MaaFramework in AgentServer mode, so the task runs
in a child process: this file run as a script, as test_parallel_mode_screens.py does.
"""

from types import SimpleNamespace

from agent_patch import rebind
from daily_child import probe_child, run_child, screen

PAGE = "AdversityPage.synthetic.png"
AFTER = "ThemePack.png"  # a screen the page may give way to: not the page
# Where Challenge sits on the page as (x0, x1, y0, y1), by eye; the cards span x 40-1240, y 220-550.
CHALLENGE_SPAN = (1090, 1185, 615, 650)


def child():
    def body(context, actions, out):
        import run_start_actions

        actions.TASK["options"] = {"target_floor": 15, "keep_dismissed_screens": False}
        actions.RUN["floor"] = 11
        stops = []
        rebind("stop", lambda context, reason, line=None: stops.append(reason) or False)
        for case, stays in (("passed", False), ("stays", True)):
            clicks = []
            rebind("screen", lambda ctx: screen(PAGE if stays or not clicks else AFTER))
            tapper = SimpleNamespace(tasker=SimpleNamespace(stopping=False, controller=SimpleNamespace(
                post_click=lambda x, y: clicks.append((x, y)) or SimpleNamespace(wait=lambda: None))),
                run_recognition=context.run_recognition)
            stops.clear()
            done = run_start_actions.PassAdversity().run(tapper, SimpleNamespace(node_name="AdversityPage"))
            out[case] = {"done": done, "clicks": list(clicks), "stops": list(stops)}

    probe_child(body)


def read():
    return run_child(__file__)


def on_challenge(tap):
    x0, x1, y0, y1 = CHALLENGE_SPAN
    return x0 <= tap[0] <= x1 and y0 <= tap[1] <= y1


def test_the_page_is_passed_with_one_tap_on_challenge():
    o = read()["passed"]
    assert o["done"] is True and o["stops"] == []
    (tap,) = o["clicks"]
    assert on_challenge(tap), tap


def test_a_page_still_up_after_challenge_stops_the_task_after_that_one_tap():
    o = read()["stays"]
    assert o["done"] is False and o["stops"] == ["floor 11: the Adversity page stays up after Challenge with none selected"]
    (tap,) = o["clicks"]
    assert on_challenge(tap), tap


if __name__ == "__main__":
    child()
