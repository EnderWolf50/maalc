"""Custom actions: the choices MirrorHub hands to the Agent (ADR 0002).

The Pipeline decides which screen is up; these decide what to pick on it.
"""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

# Starting E.G.O gift page, 1280x720 (spec 02, 開局).
# ponytail: one fixed keyword, the team's main keyword from settings replaces it (#25).
STARTING_GIFT_CABINET = (360, 245)  # Bleed
STARTING_GIFT_FIRST = (970, 262)
STARTING_GIFT_SELECT = (1080, 587)


@AgentServer.custom_action("Halt")
class Halt(CustomAction):
    """End the task on a screen the bot must not act on yet; the reason goes to the log."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        reason = json.loads(argv.custom_action_param or '""')
        print(f"[maalc] halt at {argv.node_name}: {reason}", flush=True)
        return True


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Keep the team the game has selected and log it.

    ponytail: fixed team; rotation over the settings' teams lands with #23 and #25.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        image = context.tasker.controller.post_screencap().wait().get()
        detail = context.run_recognition("TeamName", image)
        name = detail.best_result.text if detail and detail.best_result else "?"
        print(f"[maalc] team: {name}", flush=True)
        return True


@AgentServer.custom_action("PickStartingGift")
class PickStartingGift(CustomAction):
    """Open the keyword cabinet, take its first gift, press Select."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        controller = context.tasker.controller
        for x, y in (STARTING_GIFT_CABINET, STARTING_GIFT_FIRST, STARTING_GIFT_SELECT):
            controller.post_click(x, y).wait()
            time.sleep(1)
        return True
