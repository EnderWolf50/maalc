from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction


# Placeholder so MirrorDungeon exercises the PI -> agent wiring. Replace with real actions.
@AgentServer.custom_action("Placeholder")
class Placeholder(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        print(f"Placeholder action ran in node {argv.node_name}", flush=True)
        return True
