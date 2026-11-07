"""tools/check.py (#484): pytest runs as SHARDS processes at once, SHARD=i of SHARDS each, so tests/conftest.py splits the
files as CI's agent job does; the step fails when any shard fails, and its output names that shard."""

import types
from pathlib import Path

# A check.py that runs at import (before #484) would start the whole check from inside pytest, which collects this file
# again and recurses without end; fail at collection instead.
assert 'if __name__ == "__main__":' in (Path(__file__).parents[1] / "tools" / "check.py").read_text(encoding="utf-8")

import check  # noqa: E402

PYTEST = ["uv", "run", "pytest", "-q"]


class Popen:
    """subprocess.Popen as check.run_step calls it: each process writes one line naming its shard to the stdout it is
    given and ends with codes[shard]. events lists the starts and waits in order."""

    def __init__(self, codes):
        self.codes, self.envs, self.events = codes, [], []

    def __call__(self, cmd, stdout, stderr, env=None):
        shard = int(env["SHARD"]) if env and "SHARD" in env else 0
        self.envs.append(env)
        self.events.append(("start", shard))
        stdout.write(f"output of shard {shard}\n")
        stdout.flush()
        return types.SimpleNamespace(wait=lambda: self.events.append(("wait", shard)) or self.codes[shard])


def test_pytest_runs_as_four_shards_at_once():
    popen = Popen([0, 0, 0, 0])
    code, shown = check.run_step(PYTEST, 4, popen)
    assert code == 0 and shown == ""
    assert [(e["SHARDS"], e["SHARD"]) for e in popen.envs] == [("4", "0"), ("4", "1"), ("4", "2"), ("4", "3")]
    assert [kind for kind, _ in popen.events] == ["start"] * 4 + ["wait"] * 4  # every shard starts before any wait


def test_a_failing_shard_fails_the_step_and_shows_its_output():
    code, shown = check.run_step(PYTEST, 4, Popen([0, 0, 1, 0]))
    assert code == 1
    assert "shard 2 of 4" in shown and "output of shard 2" in shown
    assert "output of shard 0" not in shown and "output of shard 3" not in shown


def test_another_step_runs_once_without_a_shard():
    popen = Popen([1])
    code, shown = check.run_step(["uv", "run", "ruff", "check"], 1, popen)
    assert code == 1 and "output of shard 0" in shown and "shard 0 of" not in shown
    assert popen.envs == [None]


def test_the_shards_are_cis_agent_shards():
    assert check.SHARDS == 4 or check.SHARDS == check.os.cpu_count()
