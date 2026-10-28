"""The Consecutive Battle box's N (#375), read by actions.consecutive_now on the captures of tests/screens, and the team page
that says Chain To Battle! after a x N battle, which LuxTeamSelect must still know.

Real MaaFramework and its OCR, in a child process (this file run as a script), as test_module_count.py does.
"""

import pytest
from daily_child import probe_child, run_child, screen

# capture -> (the page's box, N): live 2026-10-27, the open row and the closed title read alike; Level Select's yellow 4 only
# reads through the narrow roi on the digit.
READS = {
    "LuxConsecExp1.png": ("exp", 1), "LuxConsecExp1Open.png": ("exp", 1), "LuxConsecExp2Open.png": ("exp", 2),
    "LuxConsecExp10Open.png": ("exp", 10), "LuxConsecExp9Open.png": ("exp", 9),
    # stage 9 at the right (the tab as it opens), and in the middle where the 10th is locked (the user's account, 2026-10-28):
    # the box moves with the Enter the bot taps
    "LuxExp.png": ("exp", 1), "LuxExpLocked.png": ("exp", 1), "LuxThread.png": ("thread", 1), "LuxThreadLust.png": ("thread", 1),
    "LuxConsecThread1.png": ("thread", 1), "LuxConsecThread2Open.png": ("thread", 2), "LuxConsecThread3Open.png": ("thread", 3),
    "LuxConsecThread10Open.png": ("thread", 10),
    "LuxConsecLevel3.png": ("level", 3), "LuxConsecLevel4Open.png": ("level", 4), "LuxConsecLevel4.png": ("level", 4),
}
ENTER = {"exp": "LuxExpEnter", "thread": "LuxThreadEnter"}  # the node whose box LuxEnter hands to the reading
# A page with no such box: the Drive page, the team page, a box of another page.
NONE = {"Drive.png": "exp", "LuxTeamSelect.png": "thread", "MainWindow.png": "level", "LuxConsecThread1.png": "level",
        "LuxConsecExp1.png": "level"}
TEAM_PAGES = ["LuxTeamSelect.png", "LuxTeamSelectChain.png"]
NOT_TEAM_PAGES = ["LuxConsecExp1.png", "LuxThreadLevels.png", "TeamSelect.png"]


def enter_of(context, actions, name, box):
    """The centre of the Enter on the capture, as LuxEnter takes it from its node's box; None where the page has no card."""
    hit = actions.seen(context, screen(name), ENTER[box]) if box in ENTER else None
    return None if hit is None else (hit.box[0] + hit.box[2] // 2, hit.box[1] + hit.box[3] // 2)


def child():
    def body(context, actions, out):
        out.update(read={}, none={}, team={}, enters={})
        for name, (box, _) in READS.items():
            enter = enter_of(context, actions, name, box)
            out["enters"][name] = enter
            out["read"][name] = actions.consecutive_now(context, screen(name), box, enter)
        for name, box in NONE.items():
            out["none"][f"{name}/{box}"] = actions.consecutive_now(context, screen(name), box)
        for name in [*TEAM_PAGES, *NOT_TEAM_PAGES]:
            out["team"][name] = actions.seen(context, screen(name), "LuxTeamSelect") is not None

    probe_child(body)


def read():
    return run_child(__file__)


@pytest.mark.parametrize(("name", "n"), [pytest.param(k, v[1], id=k) for k, v in READS.items()])
def test_the_title_reads_as_its_count(name, n):
    assert read()["read"][name] == n


@pytest.mark.parametrize("name", [k for k, v in READS.items() if v[0] in ENTER])
def test_a_card_page_is_read_from_the_enter_the_bot_taps(name):
    assert read()["enters"][name] is not None


@pytest.mark.parametrize("key", [f"{n}/{b}" for n, b in NONE.items()])
def test_a_page_without_that_box_reads_none(key):
    assert read()["none"][key] is None


@pytest.mark.parametrize("name", TEAM_PAGES)
def test_the_team_page_is_known_before_a_battle_and_before_a_chain(name):
    assert read()["team"][name] is True


@pytest.mark.parametrize("name", NOT_TEAM_PAGES)
def test_other_pages_are_not_the_team_page(name):
    assert read()["team"][name] is False


if __name__ == "__main__":
    child()
