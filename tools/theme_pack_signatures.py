"""Write data/theme_pack_signatures.json: one small colour thumbnail per pack cover (#274), for agent/pack_cover.py.

Usage: uv run python tools/theme_pack_signatures.py [--check]
Reads the covers of #242 (data/theme_pack_covers/, index.json); no game files. --check exits 1 when the committed file
differs from what the covers give. Run it after tools/theme_pack_covers.py.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import pack_cover  # noqa: E402

COVERS = pack_cover.SIGNATURES.parent / "theme_pack_covers"


def build():
    index = json.loads((COVERS / "index.json").read_text(encoding="utf-8"))
    out = {}
    for name, file in index.items():
        rgb = np.asarray(Image.open(COVERS / file).convert("RGB"))
        out[name] = pack_cover.encode(pack_cover.signature(rgb[:, :, ::-1]))  # the agent's pages are BGR
    return json.dumps(out, ensure_ascii=False, indent=0) + "\n"


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        sys.exit(0 if pack_cover.SIGNATURES.read_text(encoding="utf-8") == text else 1)
    pack_cover.SIGNATURES.write_text(text, encoding="utf-8", newline="\n")
    print(f"{text.count(chr(10)) - 2} signatures -> {pack_cover.SIGNATURES}")
