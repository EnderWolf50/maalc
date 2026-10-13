from pathlib import Path

import main


def test_root_is_located_from_agent_file():
    assert main.ROOT == Path(__file__).resolve().parent.parent
