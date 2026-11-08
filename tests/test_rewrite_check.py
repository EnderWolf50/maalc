import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("rewrite_check", Path(__file__).resolve().parent.parent / "tools/rewrite_check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

ORIGINAL = """## Problem

The CSP (#207, for #164) keeps `'unsafe-eval'`: `gui/src/validate.ts:12` compiles at runtime.

```
Uncaught EvalError: Evaluating a string
```

See [the run](https://github.com/o/r/actions/runs/42) on 2026-11-07, 1.2 s later.
"""

REWRITE = """## 問題

CSP（#207，為了 #164）得留著 `'unsafe-eval'`：`gui/src/validate.ts:12` 在執行時編譯。

```
Uncaught EvalError: Evaluating a string
```

見 2026-11-07 的[那次執行](https://github.com/o/r/actions/runs/42)，1.2 s 後。
"""


def test_a_rewrite_that_keeps_every_token_passes_and_lists_the_term_it_kept_in_english():
    dropped, english = rc.check(ORIGINAL, REWRITE)
    assert dropped == [] and english == ["CSP"]


def test_a_dropped_code_span_link_reference_and_number_are_each_named():
    rewrite = REWRITE.replace("`'unsafe-eval'`", "unsafe-eval").replace("（#207，", "（").replace(
        "(https://github.com/o/r/actions/runs/42)", "").replace("1.2 s", "稍後")
    dropped, _ = rc.check(ORIGINAL, rewrite)
    assert set(dropped) == {"code: `'unsafe-eval'`", "reference: #207", "link: https://github.com/o/r/actions/runs/42",
                            "number: 1.2"}


def test_a_changed_fenced_block_is_dropped_even_when_the_words_stay():
    dropped, _ = rc.check(ORIGINAL, REWRITE.replace("Evaluating a string", "Evaluating  a string"))
    assert dropped == ["fenced block: ```\nUncaught EvalError: Evaluating a string\n```"]


def test_english_prose_left_in_the_rewrite_is_listed_and_code_is_not():
    _, english = rc.check(ORIGINAL, REWRITE.replace("在執行時編譯", "compiles at runtime"))
    assert english == ["compiles", "CSP", "runtime"]


def test_numbers_references_and_words_set_against_chinese_with_no_space_are_still_found():
    dropped, english = rc.check("Fails after 3 runs on floor 5 (#21), see CSP.", "在第5層跑3次後失敗（#21），見CSP。")
    assert dropped == [] and english == ["CSP"]
    dropped, _ = rc.check("floor 5 (#21)", "第層（#2）")
    assert set(dropped) == {"number: 5", "reference: #21"}


def test_the_cli_exits_1_on_a_drop_and_0_on_a_clean_rewrite(tmp_path, capsys):
    (tmp_path / "a.md").write_text(ORIGINAL, encoding="utf-8")
    (tmp_path / "b.md").write_text(REWRITE, encoding="utf-8")
    (tmp_path / "c.md").write_text(REWRITE.replace("#164", ""), encoding="utf-8")
    assert rc.main([str(tmp_path / "a.md"), str(tmp_path / "b.md")]) == 0
    assert rc.main([str(tmp_path / "a.md"), str(tmp_path / "c.md")]) == 1
    assert "dropped reference: #164" in capsys.readouterr().out
