"""The root warning (#648): DeviceRooted on the live capture and on every other screen of tests/screens (no false hit)."""

import numpy as np

from daily_child import ROOT, probe_child, run_child

SCREENS = ROOT / "tests" / "screens"


def child():
    from PIL import Image

    def body(context, actions, out):
        out["hits"], out["swept"] = [], 0
        for path in sorted(SCREENS.glob("*.png")):
            image = np.ascontiguousarray(np.array(Image.open(path).convert("RGB"))[:, :, ::-1])
            if image.shape[:2] == (720, 1280):
                out["swept"] += 1
                detail = context.run_recognition("DeviceRooted", image)
                if detail and detail.hit:
                    out["hits"].append(path.name)

    probe_child(body)


def test_the_root_warning_is_the_only_screen_it_hits():
    out = run_child(__file__)
    assert out["hits"] == ["RootWarning.png"], out["hits"]
    assert out["swept"] == len(list(SCREENS.glob("*.png")))  # every capture is 1280x720, so none was skipped


if __name__ == "__main__":
    child()
