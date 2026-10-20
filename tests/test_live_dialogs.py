import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("dialogs", Path(__file__).resolve().parent.parent / "tools/live/dialogs.py")
dlg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dlg)


def test_only_text_ids_with_a_confirm_string_are_listed(tmp_path):
    (tmp_path / "EN_UI.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"dataList": [
        {"id": "ask_level_up", "content": "Will you enhance the selected Identity?"},
        {"id": "title", "content": "Mirror Dungeon"},
        {"id": "7", "content": "Will I miss them?"},
        {"id": 4, "content": "Where am I? Who am I?"},  # story line: numeric id
        {"content": "Claim reward"},
    ]}).encode())
    (tmp_path / "EN_Other.json").write_text(json.dumps({"abBattleHint": []}))
    assert list(dlg.dialogs(tmp_path)) == [("EN_UI", "ask_level_up", "Will you enhance the selected Identity?")]
