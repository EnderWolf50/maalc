import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_every_maatools_case_image_exists():
    # maa-tools test only warns on a missing image (07-assets-and-testing.md).
    config = (REPO / "maatools.config.mts").read_text(encoding="utf-8")
    images = re.findall(r"'([\w-]+\.png)'", config)
    assert images
    missing = [i for i in images if not (REPO / "tests/screens" / i).is_file()]
    assert not missing
