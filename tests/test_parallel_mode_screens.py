"""The entry switch's floor read and the floor 5/10 prompts' buttons on the captures, through the real OCR (#434).

ParallelSwitch reads the paused run's floor in the entry page's Exploring field; ParallelPrompt finds Confirm or Cancel
by their text: the floor 5 prompt on a live capture (#852), the floor 10 one only on the help sheet and a synthetic
capture until #854. They run inside a real MaaFramework task (resource bundle loaded, a still controller); the pytest
process holds MaaFramework in AgentServer mode, so the task runs in a child process: this file run as a script, as
test_module_count.py does.
"""

import json
from types import SimpleNamespace

import pytest
from agent_patch import rebind
from daily_child import probe_child, run_child, screen

# The entry page captures: a new run, and two runs paused at floor 1 (the switch OFF, ON).
ENTRY = ["EntryNewRun.png", "EntryPaused.png", "EntryParallelOn.png"]
# The prompt captures and the floor after which each comes; where Cancel and Confirm sit on each, as (x0, x1, y0, y1),
# by eye on the help sheet, moved as the synthetic one moved its dialog (-10 px in x, +21 px in y), and on the
# live floor 5 prompt over the map (#852: the bot tapped Cancel at 539, 469 there).
PROMPTS = {"ParallelModePrompt.png": 5, "ParallelModeExtreme.png": 10,
           "ParallelModePromptOverMap.png": 5, "ParallelModeExtremeOverMap.synthetic.png": 10}
BUTTONS = {"ParallelModePrompt.png": ((522, 684, 434, 470), (705, 865, 434, 470)),
           "ParallelModeExtreme.png": ((469, 630, 434, 470), (651, 811, 434, 470)),
           "ParallelModePromptOverMap.png": ((450, 627, 452, 490), (652, 830, 452, 490)),
           "ParallelModeExtremeOverMap.synthetic.png": ((459, 620, 455, 491), (641, 801, 455, 491))}
TARGETS = (5, 10, 15)


def child():
    def body(context, actions, out):
        import run_start_actions
        import settle_actions

        out["switch"] = {}
        for png in ENTRY:
            for target in TARGETS:
                actions.TASK["options"] = {"target_floor": target, "keep_dismissed_screens": False}
                arg = SimpleNamespace(custom_recognition_param=json.dumps({"on": True}), image=screen(png), node_name="X")
                out["switch"][f"{png} {target}"] = run_start_actions.ParallelSwitch().analyze(context, arg) is not None
        clicks = []
        tapper = SimpleNamespace(tasker=SimpleNamespace(controller=SimpleNamespace(
            post_click=lambda x, y: clicks.append((x, y)) or SimpleNamespace(wait=lambda: None))),
            run_recognition=context.run_recognition)
        out["taps"] = {}
        for png, after in PROMPTS.items():
            rebind("screen", lambda ctx, png=png: screen(png))
            for target in TARGETS:
                actions.TASK["options"] = {"target_floor": target, "keep_dismissed_screens": False}
                clicks.clear()
                settle_actions.ParallelPrompt().run(tapper, SimpleNamespace(
                    custom_action_param=json.dumps({"after": after}), node_name="ParallelModePrompt"))
                out["taps"][f"{png} {target}"] = list(clicks)

    probe_child(body)


def read():
    return run_child(__file__)


@pytest.mark.parametrize("png", ENTRY)
@pytest.mark.parametrize("target", TARGETS)
def test_the_switch_on_is_due_on_the_entry_captures_for_a_target_above_5(png, target):
    # the paused ones show floor 1: a run in floors 1-5 still switches
    assert read()["switch"][f"{png} {target}"] is (target > 5)


@pytest.mark.parametrize("png", list(PROMPTS))
@pytest.mark.parametrize("target", TARGETS)
def test_the_prompt_captures_get_confirm_towards_a_target_past_them_else_cancel(png, target):
    (tap,) = read()["taps"][f"{png} {target}"]
    cancel, confirm = BUTTONS[png]
    x0, x1, y0, y1 = confirm if target > PROMPTS[png] else cancel
    assert x0 <= tap[0] <= x1 and y0 <= tap[1] <= y1, tap


if __name__ == "__main__":
    child()
