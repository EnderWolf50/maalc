"""assets/locales/zh_cn.json is zh_tw.json converted with OpenCC t2s (#799): tools/zh_cn_locale.py writes it, and these
tests fail until it ran after a change to zh_tw.json."""

import json

import zh_cn_locale
from client_options import client_interface
from zh_cn_locale import LOCALES


def test_the_committed_zh_cn_file_is_the_one_the_tool_writes_from_zh_tw():
    # read_text turns the CRLF a Windows checkout writes into \n, as the tool writes it
    committed = (LOCALES / "zh_cn.json").read_text(encoding="utf-8")
    assert committed == zh_cn_locale.render((LOCALES / "zh_tw.json").read_text(encoding="utf-8")), (
        "run `uv run python tools/zh_cn_locale.py`")


def test_each_text_is_converted_to_simplified_and_keeps_its_key_and_order():
    tw = {"GlobalOptions": "全域選項", "MuMu": "MuMu 模擬器", "maalc": "maalc", "MirrorRuns": "局數\n「說明」"}
    cn = json.loads(zh_cn_locale.render(json.dumps(tw, ensure_ascii=False)))
    assert list(cn.items()) == [("GlobalOptions", "全域选项"), ("MuMu", "MuMu 模拟器"), ("maalc", "maalc"),
                                ("MirrorRuns", "局数\n「说明」")]


def test_interface_json_names_the_zh_cn_file_under_the_key_both_clients_look_up():
    # MXU v2.7.1's zh-CN takes interface key zh_cn (src/i18n/index.ts); MFAAvalonia v2.16.4 reads zh_cn as zh-CN, its
    # default language (LanguageHelper.cs NormalizeLangCode)
    assert client_interface()["languages"]["zh_cn"] == "locales/zh_cn.json"
