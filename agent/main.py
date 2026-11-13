import os
import sys
from pathlib import Path

# <root> holds interface.json in a release and the repo checkout in development;
# config/, state/ and logs/ live under it. Located from this file, never from cwd.
ROOT = Path(__file__).resolve().parent.parent
# An install ships the MaaFramework DLLs once, in <root>/maafw/ where MXU loads them; a release's
# bundled Python has no maa/bin of its own (#497).
if (ROOT / "maafw").is_dir():
    os.environ.setdefault("MAAFW_BINARY_PATH", str(ROOT / "maafw"))

from maa.agent.agent_server import AgentServer  # noqa: E402

import actions  # noqa: E402,F401  registers custom actions
import lux_actions  # noqa: E402,F401  registers custom actions


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python agent/main.py <socket_id>")

    AgentServer.start_up(sys.argv[-1])
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
