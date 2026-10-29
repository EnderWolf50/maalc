"""HubText's pass on real captures (#157): every screen whose own OCR reads it is picked.

Shrunk to the det model's 960 px, the one pass over a hub's 1210 px of rois read the Formation popup's button as
"✓Confirm" and no SKIP on an event's choices, and left both screens out. The pass runs in a real MaaFramework task
(resource bundle loaded, a still controller); the pytest process holds MaaFramework in AgentServer mode, so the task
runs in a child process: this file run as a script, as test_map_cost.py does.
"""

import json
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))  # run as a script: as pytest's pythonpath has it

SCREENS = ROOT / "tests" / "screens"
# (hub text node, capture) -> a screen its pass must pick
PICKS = {("HubText", "FormationNoSinners.png"): "PopupButton", ("HomeText", "FormationNoSinners.png"): "PopupButton",
         ("ExpText", "FormationNoSinners.png"): "PopupButton", ("ExpText", "EventChoicesLitTop.png"): "Event",
         ("ExpText", "EventChoicesLitBottom.png"): "Event", ("ExpText", "EventChoicesScrolledBack.png"): "Event"}


def child():
    """Print {"<hub> <capture>": [picked], "<hub> <capture> own": [entries whose own OCR hits]}."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker

    import hub_text as ht

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
                for hub, capture in PICKS:
                    image = np.asarray(Image.open(SCREENS / capture).convert("RGB"))[:, :, ::-1].copy()
                    nodes, rois = ht.screens(context, hub)
                    out[f"{hub} {capture}"] = ht.pick(nodes, ht.ocr_pass(context, image, rois))
                    out[f"{hub} {capture} own"] = [n for n, _, specs in nodes
                                                   if specs is not None and context.run_recognition(n, image).hit]
            except Exception:  # MaaFramework swallows it: hand it to the test
                out["error"] = traceback.format_exc()
            return True

    resource = Resource()
    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    resource.register_custom_action("Probe", Probe())
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    tasker.post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    print(json.dumps(out))


@pytest.fixture(scope="module")
def picked():
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


@pytest.mark.parametrize(("hub", "capture"), list(PICKS))
def test_the_pass_picks_every_screen_its_own_ocr_reads(picked, hub, capture):
    own = picked[f"{hub} {capture} own"]
    assert PICKS[hub, capture] in own  # the screen is up: its own OCR reads it
    assert set(own) <= set(picked[f"{hub} {capture}"])


if __name__ == "__main__":
    child()
