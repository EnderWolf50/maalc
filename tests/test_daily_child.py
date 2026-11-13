"""daily_child.load() (#480): the resource a child test runs on waits no pre_delay or post_delay. The game model moves to
the next screen at the tap, so the pipeline's waits (200 ms before and after a node by default, up to 10 s on some)
were only idle time. daily_child.run_task() (#564): a post MaaFramework does not take fails naming its scenario.
Both need MaaFramework outside AgentServer mode, so the checks run in a child process: this file run as a script.
"""

import json

import pytest
from daily_child import load, run_child, run_task

# RecoverL1 sets post_delay 2000, LuxExpEnter pre_delay 500, GoHome keeps MaaFramework's 200 ms defaults.
NODES = ["RecoverL1", "LuxExpEnter", "GoHome"]


def child():
    """Print {node: [pre_delay, post_delay]} of the resource load() returns, and "not_taken": what run_task raises on
    a post to a tasker bound to nothing (MaaFramework takes no post there: task id 0, as while a tasker still stops)."""
    from maa.tasker import Tasker

    _, resource = load()
    data = {name: resource.get_node_data(name) for name in NODES}
    try:
        run_task(Tasker(), "unbound", "GoHome")
        not_taken = None
    except AssertionError as e:
        not_taken = str(e)
    registered = {"action": sorted(resource.custom_action_list), "recognition": sorted(resource.custom_recognition_list)}
    print(json.dumps({"error": None, "not_taken": not_taken, "registered": registered,
                      **{name: [d["pre_delay"], d["post_delay"]] for name, d in data.items()}}))


@pytest.mark.parametrize("name", NODES)
def test_a_loaded_node_waits_no_delay(name):
    assert run_child(__file__)[name] == [0, 0]


def test_a_post_maaframework_does_not_take_fails_naming_its_scenario():
    # #564: the loops before run_task read .status on the missing detail of such a post and died on an AttributeError.
    not_taken = run_child(__file__)["not_taken"]
    assert not_taken and not_taken.startswith("unbound: ") and "GoHome" in not_taken, not_taken


def test_a_loaded_resource_serves_every_custom_name_the_pipeline_uses():
    # #676: load() imports main, which imports every module split off actions.py; actions alone registers only its own
    from test_agent_modules import pipeline_names  # not at the top: the child (this file as a script) has no use for it

    registered, used = run_child(__file__)["registered"], pipeline_names()
    lacks = {kind: sorted(set(names) - set(registered[kind])) for kind, names in used.items()}
    extra = {kind: sorted(set(registered[kind]) - set(names)) for kind, names in used.items()}
    assert registered == used, f"the child's resource lacks {lacks} and has {extra} besides"


if __name__ == "__main__":
    child()
