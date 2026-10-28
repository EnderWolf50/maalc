"""ClaimMail (#372, spec 00 daily tasks): open the Mailbox, press Claim All, end at the main window.

The real task in a child process (daily_child.py), on a model of the game: a screenshot per screen and the taps that
move between them.
"""

import json

from daily_child import ROOT, bind, game_class, inside, interface as interface_json, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)  # the bottom tab bar's Window tab
MAIL_ICON = (1085, 95, 70, 60)
MAILBOX_CLOSE = (690, 530, 175, 45)
CLAIM_ALL = (880, 530, 180, 45)

# screen name -> tests/screens image
SCREENS = {"main": "MainWindow.png", "drive": "Drive.png", "mailbox": "Mailbox.png", "empty": "MailboxEmpty.png"}


def child():
    """Run ClaimMail from each start; print one JSON line {scenario: {succeeded, nodes, clicks, screen, done}}."""
    actions, resource = load()

    class Game(game_class()):
        """The mailbox holds mail until Claim All."""

        images = {name: screen(png) for name, png in SCREENS.items()}

        def set(self, start, mail=True):
            self.screen, self.mail, self.clicks, self.keys = start, mail, [], []

        def on_tap(self, x, y):
            if self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            elif self.screen == "main" and inside(MAIL_ICON, x, y):
                self.screen = "mailbox" if self.mail else "empty"
            elif self.screen == "mailbox" and inside(CLAIM_ALL, x, y):
                self.screen, self.mail = "empty", False
            elif self.screen in ("mailbox", "empty") and inside(MAILBOX_CLOSE, x, y):
                self.screen = "main"
            return True

    game = Game()
    game.set("main")
    tasker = bind(resource, game)
    out = {"error": None}
    for scenario, (start, mail) in {
        "main": ("main", True), "drive": ("drive", True), "box_open": ("mailbox", True), "no_mail": ("main", False),
    }.items():
        game.set(start, mail)
        out[scenario] = result(tasker.post_task("ClaimMail", {"ClaimMailHub": {"timeout": 20000}}).wait().get(), game, actions)
    print(json.dumps(out))


def strip(path):
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("//"))


def test_claim_mail_presses_claim_all_once_and_ends_at_the_main_window():
    out = run_child(__file__)
    for name in ("main", "drive", "box_open"):
        o = out[name]
        assert o["succeeded"] and o["screen"] == "main" and o["done"] == "mail claimed", name  # live-2 G3
        claims = [c for c in o["clicks"] if inside(CLAIM_ALL, *c)]
        assert len(claims) == 1, name  # the one claim; the empty box after it is not pressed again
        assert o["nodes"][-1] == "TaskDone" and "MailClaimAll" in o["nodes"] and "MailEmpty" in o["nodes"], name
    # The first step is GoHome (spec 01): from Drive its Window tab, from a stray open box that box's Close.
    assert inside(WINDOW_TAB, *out["drive"]["clicks"][0])
    assert inside(MAILBOX_CLOSE, *out["box_open"]["clicks"][0])


def test_claim_mail_with_no_mail_ends_a_success_without_pressing_claim_all():
    o = run_child(__file__)["no_mail"]
    assert o["succeeded"] and o["screen"] == "main" and o["done"] == "no mail to claim"
    assert not any(inside(CLAIM_ALL, *c) for c in o["clicks"])
    assert "MailEmpty" in o["nodes"] and "MailClaimAll" not in o["nodes"]


def test_the_empty_box_is_read_before_a_one_button_popup_over_it():
    # Review S4: "No mail available to claim" may come as a one-button popup over the box; closing it first would hide
    # that the task is done. The server's popups still come first (the box reads under them).
    from test_pipeline import hub_entries, load_nodes

    names = hub_entries(load_nodes(), "MailText")
    assert names.index("RetryPopup") < names.index("MailEmpty") < names.index("PopupButton") < names.index("MailClaimAll")


def test_claim_mail_is_a_task_of_the_interface_and_the_global_mailbox_still_only_closes():
    interface = interface_json()
    assert {"name": "ClaimMail", "label": "$ClaimMail", "entry": "ClaimMail"} in interface["task"]
    mailbox = json.loads(strip(ROOT / "assets/resource/base/pipeline/popups.json"))["Mailbox"]
    assert mailbox["custom_action"] == "DismissShot" and "Claim" not in json.dumps(mailbox)


if __name__ == "__main__":
    child()
