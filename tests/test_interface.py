"""assets/interface.json once the settings window runs the tasks (#813, ADR 0015): what is left of the ProjectInterface is
what the development tools read (MaaDebugger, `maa-tools check`): the controller, the resource, the tasks' entry nodes
and the agent's start. The run options are the settings file's; no client option, global option, setting section,
import or zh_cn language is left, nor the code that served them."""

import json
import re

from daily_child import ROOT, interface

# what a ProjectInterface says of itself, then what the tools read
KEYS = {"$schema", "interface_version", "languages", "name", "label", "github", "version", "license", "controller",
        "resource", "agent", "task"}
# the files that served the client options (#776-#805): the attach the clients wrote, the team options file, the
# override the live tools built, the zh_cn locale MFAAvalonia needed
GONE = ["agent/task_options.schema.json", "assets/resource/base/pipeline/options.json", "assets/locales/zh_cn.json",
        "tools/client_override.py", "tools/zh_cn_locale.py", "tests/client_options.py", "tests/team_options.json",
        "gui/src/teamOptions.ts", "gui/src/movedOptions.ts"]


def test_interface_json_holds_only_what_the_development_tools_read():
    pi = interface()
    assert set(pi) == KEYS
    assert set(pi["languages"]) == {"zh_tw", "en_us"}
    assert all(set(task) == {"name", "label", "entry"} for task in pi["task"])


def test_each_task_of_the_interface_is_one_the_settings_task_list_names_in_its_order():
    schema = json.loads((ROOT / "agent" / "settings.schema.json").read_text(encoding="utf-8"))
    assert [t["name"] for t in interface()["task"]] == schema["$defs"]["task"]["enum"]
    assert all(t["entry"] == t["name"] for t in interface()["task"])


def test_the_locales_hold_the_labels_the_interface_names():
    text = (ROOT / "assets" / "interface.json").read_text(encoding="utf-8")
    labels = set(re.findall(r':\s*"\$(\w+)"', text))  # a value, not the "$schema" key
    for lang, path in interface()["languages"].items():
        assert set(json.loads((ROOT / "assets" / path).read_text(encoding="utf-8"))) == labels, lang


def test_no_code_of_the_client_options_is_left():
    assert [name for name in GONE if (ROOT / name).exists()] == []
    # the agent reads a task's options from the settings file, none from a node's attach
    assert [p.name for p in (ROOT / "agent").glob("*.py") if "attach" in p.read_text(encoding="utf-8")] == []


def test_the_release_neither_downloads_nor_names_mxu():
    # tools/install.py --release assembles the zip; tests/test_release_zip.py checks the tree a release build made
    assert not re.search(r"mxu", (ROOT / "tools" / "install.py").read_text(encoding="utf-8"), re.IGNORECASE)
    assert "MXU" not in (ROOT / "NOTICE.md").read_text(encoding="utf-8")
