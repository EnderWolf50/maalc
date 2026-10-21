import json
from pathlib import Path

from PIL import Image

import theme_pack_covers as tpc

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data"
COVERS = DATA / "theme_pack_covers"
MAX_BYTES = 1_000_000  # the thumbnails ship inside the install: a season's worth stays under 1 MB


def test_pack_ids_reads_the_id_from_each_pack_comment():
    text = 'packs:\n  - The B.E.  # 3001 H345\n  - "Hell\'s Chicken"  # 1101 N2 H2\n  - S.E.A.  # 1102\n  - "Line 4 - Section #3"  # 1208 N4\n\nevent_packs:\n  - S.E.A.  # 9999\n'
    assert tpc.pack_ids(text) == {"The B.E.": 3001, "Hell's Chicken": 1101, "S.E.A.": 1102, "Line 4 - Section #3": 1208}


def test_every_pack_of_the_yaml_has_a_cover():
    packs = tpc.pack_ids((DATA / "theme_packs.yaml").read_text(encoding="utf-8"))
    index = json.loads((COVERS / "index.json").read_text(encoding="utf-8"))
    assert set(index) == set(packs)
    for name, file in index.items():
        assert file == f"{packs[name]}.webp"
        assert Image.open(COVERS / file).size[0] == 120


def test_the_thumbnails_stay_small():
    assert sum(f.stat().st_size for f in COVERS.glob("*.webp")) < MAX_BYTES
