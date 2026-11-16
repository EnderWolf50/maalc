"""assets/interface.json's task and global options against what the agent reads (#776, #779, ADR 0013): every value a
client can send passes the agent's option schema (agent/task_options.schema.json), and every key the agent needs has an
option that sends it. Each value goes through tools/client_override.py, the override builder that follows MXU v2.7.1.
ExpTeam's, ThreadTeam's and MirrorStartTeam's cases are those of the team options file the settings GUI writes (#780,
#805): tests/team_options.json in place of the file interface.json imports (client_options)."""

import itertools
import json
import re
import shutil

import pytest
from jsonschema import Draft202012Validator

import client_override
import task_options
from client_options import ROOT, TEAM_OPTIONS, TEAM_PICK, attach, client_interface
from test_settings import CASES as SETTINGS_CASES, v20

PI = client_interface()
BARE = client_interface(teams=None)  # what a client loads before the settings GUI wrote the team options file
TEAM_KEYS = tuple(TEAM_PICK.values())  # the Luxcavation tasks' team options
FILE_KEYS = (*TEAM_KEYS, "MirrorStartTeam")  # the options whose cases come from that file, one per team
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
    # the selects and switches of a task together (MirrorDungeon: 3 * 3 * 2 * 3 * 3 * 2 * 2 * 2 * 2 cases, 2592). Not
    # the options of the team options file: a team's case writes only its own key, and each one passes on its own
    # (test_every_case_and_default_of_every_option_passes_the_agents_schema); the product would multiply the rest by
    # the teams.
    chosen = [k for k in task_keys(task) if client_override.kind(OPTIONS[k]) in CHOSEN and k not in FILE_KEYS]
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


def as_mfaavalonia_reads(path):
    """The JSONC file at path as MFAAvalonia v2.16.4 reads it into its classes (Newtonsoft.Json, JsonHelper.cs:103-110): a
    key names a member whatever its case, and of two keys that name the same member the later one wins
    (JsonPropertyCollection.GetClosestMatchProperty tries the exact name, then one in another case). Every key comes
    back in lower case, so it holds for class members only, not for a dictionary's keys (the option table's names)."""
    return client_override.read_jsonc(path, object_pairs_hook=lambda pairs: {key.lower(): value for key, value in pairs})


def test_mxu_shows_every_global_option_in_a_setting_section():
    # MXU v2.7.1 shows a global option only in a setting section of its Settings page (SettingsPage.tsx, section.option:
    # JSON.parse, so a key in this case only) and sends it as global_option lists it
    shown = [k for section in PI["setting"] for k in section["option"]]
    assert sorted(shown) == sorted(PI["global_option"])


def test_mfaavalonia_reads_every_setting_section_with_no_option():
    # #799: MFAAvalonia v2.16.4 builds a setting section's item again on its worker thread at each task start, which
    # throws there (TaskLoader.CreateSettingItem sets EnableSetting, which touches the window) and leaves every later
    # start ignored; a section with no option it skips. It shows the global options from global_option alone, once.
    sections = as_mfaavalonia_reads(ROOT / "assets" / "interface.json")["setting"]
    assert len(sections) == len(PI["setting"])
    assert all(not section.get("option") for section in sections)


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


@pytest.mark.parametrize("language", ["zh_tw", "zh_cn", "en_us"])
def test_every_text_interface_json_names_is_in_every_language(language):
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


def test_the_start_team_is_a_placeholder_holding_follow_the_queue_the_team_options_file_fills_with_the_teams():
    # #805: before the settings GUI wrote the file the dropdown has only 「照隊伍佇列」, which sends nothing and is the
    # default in both clients (case 0, default_case); the file adds a case per team, which sends its id as start_team
    placeholder, filled = BARE["option"]["MirrorStartTeam"], OPTIONS["MirrorStartTeam"]
    queue = {"name": "queue", "label": "$MirrorStartTeam_queue"}
    assert placeholder["cases"] == [queue] and placeholder["default_case"] == "queue"
    assert {k: v for k, v in filled.items() if k != "cases"} == {k: v for k, v in placeholder.items() if k != "cases"}
    assert filled["cases"][0] == queue and filled["default_case"] == "queue"
    assert {c["name"]: c["pipeline_override"] for c in filled["cases"][1:]} == {
        i: {"MirrorDungeon": {"attach": {"start_team": i}}} for i in ("a", "b", "gone")}
    for pi in (PI, BARE):
        nodes = attach(client_override.build(pi, "MirrorDungeon", {})[1])
        assert "start_team" not in nodes["MirrorDungeon"]


def test_interface_json_imports_the_team_options_file_from_the_config_folder(tmp_path):
    # #780: a client reads interface.json's imports from its folder; the settings GUI writes config/team_options.json
    # (gui/src/teamOptions.test.ts checks the GUI's path), which install.py and both clients' updates leave alone
    assert BARE["import"] == ["config/team_options.json"]
    shutil.copy(ROOT / "assets" / "interface.json", tmp_path / "interface.json")
    (tmp_path / "config").mkdir()
    shutil.copy(TEAM_OPTIONS, tmp_path / "config" / "team_options.json")
    loaded = client_override.load_interface(tmp_path / "interface.json")
    assert {k: loaded["option"][k] for k in FILE_KEYS} == {k: OPTIONS[k] for k in FILE_KEYS}


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


def old_attach(old):
    """Each node's attach as a version 20 file held its values in run, luxcavation and charge_enkephalin, by the keys the
    agent read there before #779, #780 and #781 moved them: a run cap of null is the limit switch off."""
    run = dict(old.get("run", {}))
    if "runs" in run:
        runs = run.pop("runs")
        run.update(runs_limited=runs is not None, **({} if runs is None else {"runs": runs}))
    lux = old.get("luxcavation", {})
    return {task_options.GLOBAL_NODE: {k: v for k, v in run.items() if k in task_options.GLOBAL},
            "MirrorDungeon": {k: v for k, v in run.items() if k not in task_options.GLOBAL},
            "ExpLuxcavation": lux.get("exp", {}), "ThreadLuxcavation": lux.get("thread", {}),
            "ChargeEnkephalin": old.get("charge_enkephalin", {})}


def sent_by_every_task(chosen):
    """Each node's attach once a client posted every task of the interface with these options (parse_options')."""
    nodes = {}
    for task in TASKS:
        for name, values in attach(client_override.build(PI, task, chosen)[1]).items():
            nodes.setdefault(name, {}).update(values)
    return nodes


@pytest.mark.parametrize("case", SETTINGS_CASES["migrate_v20"], ids=lambda c: c["name"])
def test_the_values_the_settings_window_lists_set_in_the_client_send_what_the_old_file_held(case):
    # #782: the settings window lists a version 20 file's moved values off the client's defaults (the case's moved,
    # which gui/src/movedOptions.test.ts checks the window lists, NAME=VALUE as bot.py run --option takes them). Each set
    # in the client as listed, every task sends the old file's values; one the list leaves out is the client's default
    # already, and one the agent refuses (a file broken by hand) gets the client's default. A count goes with count mode
    # alone and the run cap with its switch on (the schema's descriptions: sent only while ...); a null team is none
    # picked. The two pops below are those nestings, the only ones interface.json has: a new one fails the first assert.
    assert {n for o in OPTIONS.values() for c in o.get("cases", []) for n in c.get("option", [])} == {
        "MirrorRuns", "ExpCount", "ThreadCount"}
    old = v20(case["edits"])
    pairs = [f"WebhookUrl={old['run']['webhook_url']}" if p == "WebhookUrl=(set)" else p for p in case["moved"]]
    sent, default = sent_by_every_task(client_override.parse_options(PI, pairs)), sent_by_every_task({})
    for node, values in old_attach(old).items():
        props = SCHEMA[node]["properties"]
        want = {**default[node], **{k: v for k, v in values.items() if Draft202012Validator(props[k]).is_valid(v)}}
        if want.get("runs_limited") is False:
            want.pop("runs", None)
        if want.get("mode") == "daily":
            want.pop("count", None)
        assert sent[node] == want, node
