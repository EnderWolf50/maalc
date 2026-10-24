"""Download the ppocr_v6/small OCR model into assets/resource/base/model/ocr.

Same model the MaaPracticeBoilerplate copies from the MaaCommonAssets submodule;
fetched file by file at a pinned commit to skip the ~350 MB submodule.
The model is PaddleOCR (Apache-2.0), see NOTICE.md.
"""

import shutil
from pathlib import Path
from urllib.request import urlretrieve

COMMIT = "dabcd4681ac990dc4361de26416d986abd80e4aa"
BASE = f"https://raw.githubusercontent.com/MaaXYZ/MaaCommonAssets/{COMMIT}/OCR/ppocr_v6/small"
FILES = ["det.onnx", "rec.onnx", "keys.txt"]

ocr_dir = Path(__file__).resolve().parent.parent / "assets/resource/base/model/ocr"
# MaaFramework keeps one OCR instance per model folder. On DirectML the default one reads a line (only_rec) in 31 ms once a
# det+rec pass has used it, 4 ms before; a folder of its own, used by only_rec reads alone, keeps the 4 ms (#329, gift_cells.PLATE_MODEL).
COPY = "plate"

if __name__ == "__main__":
    ocr_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if (ocr_dir / name).exists():
            print(f"skip {name}")
            continue
        print(f"fetch {name}")
        urlretrieve(f"{BASE}/{name}", ocr_dir / f"{name}.part")
        (ocr_dir / f"{name}.part").rename(ocr_dir / name)
    for name in FILES:
        (ocr_dir / COPY).mkdir(exist_ok=True)
        if not (ocr_dir / COPY / name).exists():
            shutil.copy2(ocr_dir / name, ocr_dir / COPY / name)
