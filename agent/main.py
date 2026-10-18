import sys
from pathlib import Path

from maa.agent.agent_server import AgentServer

# <root> holds interface.json in a release and the repo checkout in development;
# config/, state/ and logs/ live under it. Located from this file, never from cwd.
ROOT = Path(__file__).resolve().parent.parent

import actions  # noqa: E402,F401  registers custom actions


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python agent/main.py <socket_id>")

    AgentServer.start_up(sys.argv[-1])
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
# ci probe: agent only
