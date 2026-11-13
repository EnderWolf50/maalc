"""The Thread tab's Daily Bonuses (#429): ThreadBonuses' OCR on the captures in tests/screens, through
luxcavation.read_bonuses, as ThreadLuxcavation reads it before its first battle. Runs in a MaaFramework child process,
as test_module_count.py does.
"""

import pytest
from daily_child import probe_child, run_child, screen
import luxcavation

# Labelled by eye: every Thread tab capture so far shows 0/3.
BONUSES = {name: 0 for name in ("LuxThread.png", "LuxThreadLust.png", "LuxThreadScrolled.png", "LuxConsecThread1.png",
                                "LuxConsecThread2Open.png", "LuxConsecThread3Open.png", "LuxConsecThread10Open.png",
                                "LuxThreadLevels.png")}  # Level Select dims the tab, the box still reads
NONE = ["LuxExp.png", "MainWindow.png"]


def child():
    """Read every capture's Daily Bonuses; print {image: n read}."""
    def body(context, actions, out):
        for name in [*BONUSES, *NONE]:
            out[name] = luxcavation.read_bonuses(actions.ocr_texts(context, screen(name), "ThreadBonuses"))

    probe_child(body)


def read():
    return run_child(__file__)


@pytest.mark.parametrize(("name", "n"), [pytest.param(k, v, id=k) for k, v in BONUSES.items()])
def test_the_daily_bonuses_read_as_their_n(name, n):
    assert read()[name] == n


@pytest.mark.parametrize("name", NONE)
def test_a_screen_without_the_box_reads_as_none(name):
    assert read()[name] is None


if __name__ == "__main__":
    child()
