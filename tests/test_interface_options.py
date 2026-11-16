"""assets/interface.json's task and global options against what the agent reads (#776, #779, ADR 0013): every value a
client can send passes the agent's option schema (agent/task_options.schema.json), and every key the agent needs has an
option that sends it. Each value goes through tools/client_override.py, the override builder that follows MXU v2.7.1.
ExpTeam's and ThreadTeam's cases are those of the team options file the settings GUI writes (#780): tests/team_options.json
in place of the file interface.json imports (client_options)."""

import itertools
import json
import re
import shutil

import pytest

import client_override
import task_options
from client_options import ROOT, TEAM_OPTIONS, TEAM_PICK, attach, interface

PI = interface()
BARE = interface(teams=None)  # what a client loads before the settings GUI wrote the team options file
TEAM_KEYS = tuple(TEAM_PICK.values())  # the team options: their cases come from that file
OPTIONS = PI["option"]
TASKS = {t["name"]: t for t in PI["task"]}
SCHEMA = task_options.SCHEMA["$defs"]
CHOSEN = ("select", "switch")  # the types whose value is a case


def reachable(keys):
    """Each option the client shows from keys: the options themselves, and those nested under any of their cases."""
    out = []
    for key in keys:
        out.append(key)
        out += reachable([n for c in OPTIONS[key].get("cases", []) for n in c.get("option", [])])
    return list(dict.fromkeys(out))


def task_keys(task):
    """The options a client sends with task: the global ones, the task's own and those nested under them."""
    return reachable([*PI["global_option"], *TASKS[task].get("option", [])])


def errors(task, *pairs):
    """What the agent's start says of task posted with these NAME=VALUE options: the checks of task_options.read."""
    nodes = attach(client_override.build(PI, task, client_override.parse_options(PI, list(pairs)))[1])
    return [e for node in task_options.nodes(task) for e in task_options.check(node, nodes.get(node, {}))]


def shown_under(task, key):
    """The NAME=VALUE of the cases that show key among task's options: none for an option of the task's own list."""
    return [f"{p}={c['name']}" for p in task_keys(task) for c in OPTIONS[p].get("cases", []) if key in c.get("option", [])]


def values(key):
    """The values --option takes for option key: each case, or each input's default."""
    opt = OPTIONS[key]
    if client_override.kind(opt) == "input":
        return [opt["inputs"][0].get("default", "")]
    return [c["name"] for c in opt["cases"]]


def writes(opt):
    """(node, attach key) of every override an option's cases or inputs write."""
    overrides = [c.get("pipeline_override", {}) for c in opt.get("cases", [])] + [opt.get("pipeline_override", {})]
    return {(node, key) for o in overrides for node, data in o.items() for key in data.get("attach", {})}


@pytest.mark.parametrize("task", TASKS)
def test_every_task_posted_with_the_defaults_has_every_value_the_agent_needs(task):
    assert errors(task) == []


@pytest.mark.parametrize("task, key", [(t, k) for t in TASKS for k in task_keys(t)])
def test_every_case_and_default_of_every_option_passes_the_agents_schema(task, key):
    # each value with every other option at its default, and under a nested option, its parent's case that shows it
    parents = shown_under(task, key)
    for value in values(key):
        assert errors(task, *parents, f"{key}={value}") == [], (key, value)


@pytest.mark.parametrize("task", TASKS)
def test_every_combination_of_the_cases_passes_the_agents_schema(task):
    # the selects and switches of a task together (MirrorDungeon: 3 * 3 * 2 * 3 * 3 * 2 * 2 * 2 * 2 cases, 2592)
    chosen = [k for k in task_keys(task) if client_override.kind(OPTIONS[k]) in CHOSEN]
    for combo in itertools.product(*[[f"{k}={v}" for v in values(k)] for k in chosen]):
        assert errors(task, *combo) == [], combo


@pytest.mark.parametrize("task, pairs, sent", [
    # #781: what a new settings file had: daily mode, no count sent (count mode's is 1 for EXP, 3 for Thread, the day's
    # Daily Bonuses), no retries, Consecutive Battle on; ChargeEnkephalin 0, no Lunacy spent
    ("ExpLuxcavation", (), {"mode": "daily", "retries": 0, "consecutive": True}),
    ("ExpLuxcavation", ("ExpMode=count",), {"mode": "count", "count": 1, "retries": 0, "consecutive": True}),
    ("ThreadLuxcavation", (), {"mode": "daily", "retries": 0, "consecutive": True}),
    ("ThreadLuxcavation", ("ThreadMode=count",), {"mode": "count", "count": 3, "retries": 0, "consecutive": True}),
    ("ChargeEnkephalin", (), {"count": 0}),
])
def test_a_daily_tasks_options_start_where_a_new_settings_file_had_them(task, pairs, sent):
    assert attach(client_override.build(PI, task, client_override.parse_options(PI, list(pairs)))[1])[task] == sent


def test_every_attach_key_an_option_writes_is_the_agents_and_named_after_it():
    # the schema's title is what the agent's stop line names: the option that writes the key
    for key, opt in OPTIONS.items():
        for node, attach_key in writes(opt):
            assert node in SCHEMA, (key, node)
            assert SCHEMA[node]["properties"][attach_key]["title"] == key, (key, attach_key)


def test_every_key_the_agent_reads_has_an_option_that_writes_it():
    written = {w for opt in OPTIONS.values() for w in writes(opt)}
    for node, schema in SCHEMA.items():
        assert {(node, k) for k in schema["properties"]} <= written, node


def test_the_global_options_write_only_global_options_node_and_a_tasks_only_its_entry():
    for key in reachable(PI["global_option"]):
        assert {n for n, _ in writes(OPTIONS[key])} == {task_options.GLOBAL_NODE}, key
    for task in TASKS.values():
        for key in reachable(task.get("option", [])):
            assert {n for n, _ in writes(OPTIONS[key])} == {task["entry"]}, key


def test_a_select_or_switch_starts_on_its_first_case_in_both_clients():
    # MFAAvalonia starts a task option on case 0 and ignores default_case; MXU takes default_case: the same (#776). Not
    # the team options: the file's first default_case is the team the settings file picked (MXU only), its case 0
    # 「未選擇」 (#780).
    for key, opt in OPTIONS.items():
        if client_override.kind(opt) in CHOSEN and key not in TEAM_KEYS:
            assert opt.get("default_case") == opt["cases"][0]["name"], key


def test_a_switch_has_the_cases_yes_and_no():
    # MFAAvalonia draws a toggle only for cases named yes and no, and reads on or off from the name
    for key, opt in OPTIONS.items():
        if client_override.kind(opt) == "switch":
            assert sorted(c["name"] for c in opt["cases"]) == ["No", "Yes"], key


def test_every_global_option_is_in_a_setting_section():
    # MXU v2.7.1 shows a global option only in a setting section of its Settings page
    shown = [k for section in PI.get("setting", []) for k in section["option"]]
    assert sorted(shown) == sorted(PI["global_option"])


def test_a_nested_option_is_only_under_its_case():
    # MFAAvalonia sends an option listed both nested and in the task's list twice
    nested = {n for opt in OPTIONS.values() for c in opt.get("cases", []) for n in c.get("option", [])}
    for task in TASKS.values():
        assert not nested & set(task.get("option", [])), task["name"]
    assert not nested & set(PI["global_option"])


def test_every_option_is_shown_somewhere():
    shown = set(reachable(PI["global_option"])) | {k for t in TASKS for k in task_keys(t)}
    assert set(OPTIONS) == shown


@pytest.mark.parametrize("key, input", [(k, i) for k, o in OPTIONS.items() if client_override.kind(o) == "input" for i in o["inputs"]])
def test_an_input_the_client_lets_through_is_one_the_agent_takes(key, input):
    # verify, a regex JavaScript and .NET read alike, is the client's check: MXU marks the field and sends it anyway,
    # MFAAvalonia refuses the start. Whatever it lets through the agent must take: an int with a leading 0 is not JSON
    # once filled in, and MXU drops it, so verify keeps it out.
    if input.get("pipeline_type") != "int":
        return
    task = next(t for t in TASKS if key in task_keys(t))
    parents = shown_under(task, key)
    for text in ["0", "1", "2", "9", "10", "99", "01", "007", "-1", "", "1.5", " 1", "abc"]:
        if re.fullmatch(input["verify"], text):
            assert errors(task, *parents, f"{key}={text}") == [], text
    assert input["default"] and re.fullmatch(input["verify"], input["default"])


def test_the_webhook_is_a_password_input_with_no_default():
    # the clients mask and encrypt a password input; the PI schema refuses a default on one
    (item,) = OPTIONS["WebhookUrl"]["inputs"]
    assert item["password"] is True and "default" not in item


@pytest.mark.parametrize("language", ["zh_tw", "en_us"])
def test_every_text_interface_json_names_is_in_both_languages(language):
    # a $key in a label, description or pattern_msg is looked up in the language's file
    texts = json.loads((ROOT / "assets" / PI["languages"][language]).read_text(encoding="utf-8"))

    def strings(node):
        if isinstance(node, dict):
            return [s for v in node.values() for s in strings(v)]
        if isinstance(node, list):
            return [s for v in node for s in strings(v)]
        return [node] if isinstance(node, str) else []

    named = {s[1:] for s in strings(PI) if s.startswith("$")}
    assert named and named - set(texts) == set()
    assert all(texts[k].strip() for k in named)


@pytest.mark.parametrize("key", TEAM_KEYS)
def test_a_team_option_is_a_placeholder_the_team_options_file_fills_with_its_cases(key):
    # #780: interface.json's own definition has no case, so the dropdown is empty until the settings GUI wrote the
    # file; the file's definition is the same but for its cases and default_case (MXU replaces the whole definition)
    placeholder, filled = BARE["option"][key], OPTIONS[key]
    assert placeholder["cases"] == [] and "default_case" not in placeholder
    drop = ("cases", "default_case")
    assert {k: v for k, v in filled.items() if k not in drop} == {k: v for k, v in placeholder.items() if k not in drop}
    assert filled["cases"][0] == {"name": "none", "label": "$LuxTeam_none"}  # 「未選擇」, which sends nothing
    assert errors(next(t for t in TASKS if key in TASKS[t].get("option", [])), f"{key}=none") == []


def test_interface_json_imports_the_team_options_file_from_the_config_folder(tmp_path):
    # #780: a client reads interface.json's imports from its folder; the settings GUI writes config/team_options.json
    # (gui/src/teamOptions.test.ts checks the GUI's path), which install.py and both clients' updates leave alone
    assert BARE["import"] == ["config/team_options.json"]
    shutil.copy(ROOT / "assets" / "interface.json", tmp_path / "interface.json")
    (tmp_path / "config").mkdir()
    shutil.copy(TEAM_OPTIONS, tmp_path / "config" / "team_options.json")
    loaded = client_override.load_interface(tmp_path / "interface.json")
    assert {k: loaded["option"][k] for k in TEAM_KEYS} == {k: OPTIONS[k] for k in TEAM_KEYS}


def test_global_options_is_a_node_no_next_names():
    # it only holds the global options' values: a next to it would run it
    from test_pipeline import load_nodes

    nodes = load_nodes()
    assert nodes[task_options.GLOBAL_NODE] == {"attach": {}}
    named = {n.split("]")[-1] for node in nodes.values() for key in ("next", "on_error") for n in node.get(key, [])}
    assert task_options.GLOBAL_NODE not in named


def test_the_entry_nodes_the_options_write_are_the_tasks_entries():
    for node in SCHEMA:
        assert node == task_options.GLOBAL_NODE or TASKS[node]["entry"] == node
