"""Write assets/locales/zh_cn.json, the Simplified Chinese texts of interface.json (#799): zh_tw.json converted with OpenCC
t2s, text by text, its keys and their order kept. MFAAvalonia's default language is Simplified Chinese, and it takes a
text only from the file of the language it shows, so without this file its task list shows the raw keys.

Run `uv run python tools/zh_cn_locale.py` after any change to zh_tw.json; never edit zh_cn.json by hand
(tests/test_zh_cn_locale.py fails until the two match)."""

import json
from pathlib import Path

import opencc

LOCALES = Path(__file__).resolve().parent.parent / "assets" / "locales"
_T2S = opencc.OpenCC("t2s")


def render(zh_tw: str) -> str:
    """zh_cn.json's text for zh_tw.json's text, in its format (4-space indent, the characters as they are)."""
    texts = {key: _T2S.convert(text) for key, text in json.loads(zh_tw).items()}
    return json.dumps(texts, ensure_ascii=False, indent=4) + "\n"


def main():
    target = LOCALES / "zh_cn.json"
    target.write_text(render((LOCALES / "zh_tw.json").read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
