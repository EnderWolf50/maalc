"""daily_child.load() (#480): the resource a child test runs on waits no pre_delay or post_delay. The game model moves to
the next screen at the tap, so the pipeline's waits (200 ms a node by default, up to 5 s on some) were only idle time.
load() needs MaaFramework outside AgentServer mode, so the check runs in a child process: this file run as a script.
"""

import json

import pytest
from daily_child import load, run_child

# HomeBack sets post_delay 2000, LuxExpEnter pre_delay 500, GoHome keeps MaaFramework's 200 ms defaults.
NODES = ["HomeBack", "LuxExpEnter", "GoHome"]


def child():
    """Print {node: [pre_delay, post_delay]} of the resource load() returns."""
    _, resource = load()
    data = {name: resource.get_node_data(name) for name in NODES}
    print(json.dumps({"error": None, **{name: [d["pre_delay"], d["post_delay"]] for name, d in data.items()}}))


@pytest.mark.parametrize("name", NODES)
def test_a_loaded_node_waits_no_delay(name):
    assert run_child(__file__)[name] == [0, 0]


if __name__ == "__main__":
    child()
