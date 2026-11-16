"""The client override builder (#778): an interface, its imports and the chosen values in, the override array out, as
MXU v2.7.1 builds it. Every expected array below is written out from MXU v2.7.1's src/utils/pipelineOverride.ts:
generateTaskPipelineOverride sends the task's own pipeline_override, then each global_option, then each task option;
collectOptionOverrides sends a case's own pipeline_override, then the options nested under that case; an input fills
`"{name}"` with a bare number (int, empty is 0), true or false (bool) or a JSON string. An option with no value takes
src/stores/helpers.ts createDefaultOptionValue: default_case, else the first case; an input its default."""

import re

import pytest

import client_override

INTERFACE = r"""{
    "interface_version": 2,
    // whole-line comments, as assets/interface.json has them
    "import": ["config/teams.json", "config/gone.json"],
    "task": [
        {"name": "Mirror", "entry": "MirrorEntry", "pipeline_override": {"MirrorEntry": {"attach": {"base": 1}}},
         "option": ["Difficulty", "RunsLimit", "Strict", "Team"]},
        {"name": "Mail", "entry": "MailEntry"}
    ],
    "global_option": ["Webhook", "AutoDownload"],
    "option": {
        // no type: a select
        "Difficulty": {"default_case": "hard", "cases": [
            {"name": "auto", "pipeline_override": {"MirrorEntry": {"attach": {"difficulty": "auto"}}}},
            {"name": "hard", "pipeline_override": {"MirrorEntry": {"attach": {"difficulty": "hard"}}}}]},
        "RunsLimit": {"type": "switch", "cases": [
            {"name": "Yes", "option": ["Runs"], "pipeline_override": {"MirrorEntry": {"attach": {"runs_limited": true}}}},
            {"name": "No", "pipeline_override": {"MirrorEntry": {"attach": {"runs_limited": false}}}}]},
        "Runs": {"type": "input", "inputs": [{"name": "runs", "default": "1", "pipeline_type": "int"}],
                 "pipeline_override": {"MirrorEntry": {"attach": {"runs": "{runs}"}}}},
        "Strict": {"type": "input", "inputs": [{"name": "on", "default": "yes", "pipeline_type": "bool"}],
                   "pipeline_override": {"MirrorEntry": {"attach": {"strict": "{on}"}}}},
        // the placeholder the team options file replaces
        "Team": {"cases": []},
        "Webhook": {"type": "input", "inputs": [{"name": "url", "default": "", "password": true}],
                    "pipeline_override": {"GlobalOptions": {"attach": {"webhook_url": "{url}"}}}},
        "AutoDownload": {"type": "switch", "cases": [
            {"name": "Yes", "pipeline_override": {"GlobalOptions": {"attach": {"auto_download": true}}}},
            {"name": "No", "pipeline_override": {"GlobalOptions": {"attach": {"auto_download": false}}}}]}
    }
}"""

TEAMS = """{
    // the team options file: Team's whole definition, which replaces the main file's (MXU interfaceLoader.ts)
    "option": {"Team": {"default_case": "t1", "cases": [
        {"name": "none"},
        {"name": "t1", "pipeline_override": {"MirrorEntry": {"attach": {"team": "t1"}}}}]}}
}"""

BASE = {"MirrorEntry": {"attach": {"base": 1}}}


def mirror(key, value):
    return {"MirrorEntry": {"attach": {key: value}}}


def glob(key, value):
    return {"GlobalOptions": {"attach": {key: value}}}


@pytest.fixture
def install(tmp_path):
    (tmp_path / "interface.json").write_text(INTERFACE, encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config/teams.json").write_text(TEAMS, encoding="utf-8")
    return tmp_path


def built(install, task, *pairs):
    interface = client_override.load_interface(install / "interface.json")
    return client_override.build(interface, task, client_override.parse_options(interface, list(pairs)))


def test_no_values_sends_every_default_task_override_then_global_then_task_options(install):
    entry, override, used = built(install, "Mirror")
    assert entry == "MirrorEntry"
    assert override == [
        BASE,
        glob("webhook_url", ""), glob("auto_download", True),  # AutoDownload: no default_case, its first case
        mirror("difficulty", "hard"),  # default_case, not the first case
        mirror("runs_limited", True), mirror("runs", 1),  # the case's own override, then the input nested under it
        mirror("strict", True),  # bool: "yes" is true
        mirror("team", "t1"),  # the imported definition and its default_case
    ]
    assert used == ["Webhook=(not set) (default)", "AutoDownload=Yes (default)", "Difficulty=hard (default)",
                    "RunsLimit=Yes (default)", "Runs=1 (default)", "Strict=yes (default)", "Team=t1 (default)"]


def test_given_values_fill_the_inputs_as_mxu_does(install):
    _, override, used = built(install, "Mirror", "Difficulty=auto", "Runs=", "Strict=0", r'Webhook=hook\a "x"',
                              "AutoDownload=No", "Team=none")
    assert override == [
        BASE,
        glob("webhook_url", r'hook\a "x"'),  # a backslash and quotes go in JSON-escaped and read back as given
        glob("auto_download", False),
        mirror("difficulty", "auto"),
        mirror("runs_limited", True), mirror("runs", 0),  # int: an empty value is 0
        mirror("strict", False),  # bool: anything but true, 1, yes, y is false
        # Team=none: a case with no pipeline_override sends nothing
    ]
    assert used == ["Webhook=(set)", "AutoDownload=No", "Difficulty=auto", "RunsLimit=Yes (default)", "Runs=",
                    "Strict=0", "Team=none"]


def test_an_option_nested_under_the_case_not_chosen_is_not_sent(install):
    _, override, used = built(install, "Mirror", "RunsLimit=No", "Runs=5")
    assert mirror("runs_limited", False) in override
    assert not any("runs" in o.get("MirrorEntry", {}).get("attach", {}) for o in override)
    assert not any(u.startswith("Runs=") for u in used)


def test_a_task_with_no_options_of_its_own_sends_the_global_options(install):
    entry, override, used = built(install, "Mail")
    assert (entry, override) == ("MailEntry", [glob("webhook_url", ""), glob("auto_download", True)])


def test_a_missing_import_is_skipped_with_a_warning(install):
    (install / "config/teams.json").unlink()
    warnings = []
    interface = client_override.load_interface(install / "interface.json", warn=warnings.append)
    _, override, used = client_override.build(interface, "Mirror", {})
    assert warnings == ["import config/teams.json not read (FileNotFoundError): skipped",
                        "import config/gone.json not read (FileNotFoundError): skipped"]
    assert not any("team" in o.get("MirrorEntry", {}).get("attach", {}) for o in override)  # cases: [], nothing
    assert used[-1] == "Team=(no case) (default)"


def test_an_int_input_that_is_not_a_number_drops_that_override_as_mxu_does(install):
    # MXU: JSON.parse of the filled-in override fails, it logs a warning and sends the rest
    _, override, used = built(install, "Mirror", "Runs=abc")
    assert mirror("runs_limited", True) in override
    assert not any("runs" in o.get("MirrorEntry", {}).get("attach", {}) for o in override)
    assert "Runs=abc: not JSON once filled in, not sent (MXU drops it)" in used


@pytest.mark.parametrize("pair, says", [
    ("Nope=1", "interface.json has no option Nope"),
    ("Difficulty=extreme", "Difficulty has no case extreme (cases: auto, hard)"),
    ("AutoDownload=maybe", "AutoDownload is a switch: Yes or No"),
    ("Runs.count=3", "Runs takes Runs=VALUE"),
    ("Difficulty", "takes NAME=VALUE"),
])
def test_an_option_or_case_the_interface_lacks_is_refused(install, pair, says):
    interface = client_override.load_interface(install / "interface.json")
    with pytest.raises(ValueError, match=re.escape(f"--option {pair}: {says}")):
        client_override.parse_options(interface, [pair])


def test_a_task_the_interface_lacks_is_refused(install):
    interface = client_override.load_interface(install / "interface.json")
    with pytest.raises(ValueError, match="interface.json has no task Nope"):
        client_override.build(interface, "Nope", {})
