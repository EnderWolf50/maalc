"""A boss gift card read off the boss captures in tests/screens (#381): its Enemy Level Up badge, its trial's name and
effect line through actions.trial_card, its gift's tier through actions.gift_tier.

trial_card runs inside a real MaaFramework task (resource bundle loaded, a still controller), so the OCR is the agent's
on the device. The pytest process holds MaaFramework in AgentServer mode, so the task runs in a child process: this file
run as a script, as test_map_cost.py does.
"""

import json
import subprocess
import sys
import traceback
import types
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

SCREENS = ROOT / "tests" / "screens"
# capture -> (its pool: the floor whose boss was cleared, [(card centre x: the Acquire tab's right edge - 114, Enemy Level
# Up N, trial, the gift's tier in the gift data)]), labelled by eye
CARDS = {
    "BossGiftTrials.png": (2, [(374, 1, "Growth II", 1), (638, 2, "Resilient II", 2), (904, 1, "Offense Level Up II", 1)]),
    "BossGiftTrialsHard.png": (1, [(242, 1, "Defense Level Up", 2), (506, 1, "Defense Skill Up", 1),
                                   (771, 2, "Take Less Damage", 1), (1035, 2, "Growth I", 2)]),
    # live 2026-10-28: Resilient V's and its neighbours' effect lines wrap to a second line
    "BossGiftTrialsFloor3.png": (3, [(375, 2, "Resilient V", 1), (638, 1, "Final Power Boost", 2), (904, 1, "Keen III", 2)]),
}
# A fight's gift page, whose tier PickGift does not score (main > other > owned there), but the last gift card of
# tests/screens: its numeral 8 px lower than a boss page's.
TIERS = {"GiftChoice.png": [(639, 2)]}


def load(name):
    return np.asarray(Image.open(SCREENS / name).convert("RGB"))[:, :, ::-1].copy()


def child():
    """Read every labelled card through actions.trial_card in a MaaFramework task; print {capture x: [N, name, line]}."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "test"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # nothing moves
            return lambda *args: True

    out = {}

    class Probe(CustomAction):
        def run(self, context, argv):
            try:
                for name, (_, cards) in CARDS.items():
                    image = load(name)
                    for x, *_ in cards:
                        out[f"{name} {x}"] = list(actions.trial_card(context, image, x))
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return True

    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    resource.register_custom_action("Probe", Probe())
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    tasker.post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    print(json.dumps(out))


@pytest.fixture(scope="module")
def read():
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


CASES = [(name, pool, x, level, trial) for name, (pool, cards) in CARDS.items() for x, level, trial, _ in cards]


@pytest.mark.parametrize(("name", "pool", "x", "level", "trial"), [pytest.param(*c, id=f"{c[0]}-{c[2]}") for c in CASES])
def test_a_boss_card_reads_its_badge_and_its_trial_by_the_effect_line(read, name, pool, x, level, trial):
    import rewards
    table = yaml.safe_load((ROOT / "assets/resource/base/data/trials.yaml").read_text(encoding="utf-8"))
    got_level, got_name, line = read[f"{name} {x}"]
    assert got_level == level
    assert rewards.read_trial(got_name, line, rewards.trials_of(table, pool)) == (trial, "effects")
    assert rewards.read_trial(got_name, "", rewards.trials_of(table, pool)) == (trial, "name")  # the name alone too


@pytest.mark.parametrize(("name", "x", "tier"), [(n, x, t) for n, (_, cards) in CARDS.items() for x, _, _, t in cards]
                         + [(n, x, t) for n, cards in TIERS.items() for x, t in cards])
def test_the_tier_numeral_over_a_gift_card_reads_as_the_gift_data_s_tier(name, x, tier):
    # The sweep: every gift card of tests/screens, 11 on 4 captures, tiers I and II, none misread. A III read right on a
    # 2026-10-28 frame that is not committed (Disk Fragment, floor 2); IV and V are on no capture yet.
    import actions
    assert actions.gift_tier(load(name), x) == tier


if __name__ == "__main__":
    child()
