"""The Enkephalin Modules number in the bottom-left panel (#367): read by actions.module_count on the captures in
tests/screens that show the panel, and None where it does not (a page without it, a screen where the icon is not there).

The same function gives #369's Mirror Dungeon threshold. It runs inside a real MaaFramework task (resource bundle loaded,
a still controller), so the OCR is the agent's on the device; the pytest process holds MaaFramework in AgentServer
mode, so the task runs in a child process: this file run as a script, as test_map_cost.py does.
"""

import pytest
from daily_child import probe_child, run_child, screen

# Labelled by eye (2026-10-26 live; the panel moves between the main window's x 393 and the Luxcavation pages' x 242).
MODULES = {
    "MainWindow.png": 182, "MainWindowFadeIn.png": 182, "MainWindowLater.png": 104, "Drive.png": 182,
    "LuxExp.png": 104, "LuxExpLocked.png": 104, "LuxThread.png": 104,
}
# No panel, or none this function can read: the title screen, the Mirror Dungeon map, a shop, the Mirror Dungeon entry page (#369: PlanRun's read gives None there).
NONE = ["Title.png", "MirrorMap.png", "Shop.png", "Loading.png", "EntryNewRun.png", "EntryPaused.png", "EntryParallelOn.png"]


def child():
    """Read every capture through actions.module_count in a MaaFramework task; print {image: number read}."""
    def body(context, actions, out):
        for name in [*MODULES, *NONE]:
            out[name] = actions.module_count(context, screen(name))

    probe_child(body)


def read():
    return run_child(__file__)


@pytest.mark.parametrize(("name", "modules"), [pytest.param(n, m, id=n) for n, m in MODULES.items()])
def test_the_panel_reads_as_its_number(name, modules):
    assert read()[name] == modules


@pytest.mark.parametrize("name", NONE)
def test_a_screen_without_the_panel_reads_as_none(name):
    assert read()[name] is None


if __name__ == "__main__":
    child()
