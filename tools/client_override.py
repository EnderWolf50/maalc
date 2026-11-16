"""The pipeline override a client posts with a task, built from an install's interface.json as MXU v2.7.1 builds it, so
the live bot (tools/live/bot.py) and the tests post a task the way the user's client does (#778, spec #776).

    interface = load_interface(root / "interface.json", warn=print)
    values = parse_options(interface, ["MirrorDifficulty=hard", "MirrorRuns=3"])
    entry, override, used = build(interface, "MirrorDungeon", values)

MXU's sources it follows: src/services/interfaceLoader.ts (mergeImported) for the imports, src/utils/pipelineOverride.ts
(generateTaskPipelineOverride, collectOptionOverrides) for the array, src/stores/helpers.ts (createDefaultOptionValue)
and src/utils/optionHelpers.ts (findSwitchCase) for the defaults and switches. MaaFramework applies the array entry by
entry, so a later entry wins a key. The array holds the task's own pipeline_override, then each global option, then each
task option; MXU's resource and controller options would come between the last two, and maalc's interface has none.
An option sends its chosen case's pipeline_override, then the options nested under that case, in turn. An option with no
value takes its default: a select its default_case, else its first case; a switch the same, as Yes or No; an input
each input's default. An input whose value leaves its override not JSON drops that override, as MXU drops it. Where it
differs from MXU: a checkbox or hotkey option is not sent (its used line says so), and --option sets no input option
with several inputs; maalc's interface has neither.
"""
from __future__ import annotations

import json
from pathlib import Path

YES, NO = ("Yes", "yes", "Y", "y"), ("No", "no", "N", "n")  # the case names a switch's on and off take (findSwitchCase)


def read_jsonc(path: Path):
    """A JSON file whose whole-line // comments are dropped first: json.loads fails on them."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads("\n".join(ln for ln in lines if not ln.strip().startswith("//")))


def load_interface(path: Path, warn=lambda line: None) -> dict:
    """The interface at path with each file its `import` names merged in, the paths taken from its folder: an imported
    option replaces the main file's whole definition, tasks are appended, global options appended once each. An import
    that is missing or does not parse is skipped, with a warn line, as MXU does."""
    pi = read_jsonc(path)
    for name in pi.get("import", []):
        try:
            imported = read_jsonc(path.parent / name)
        except (OSError, ValueError) as e:
            warn(f"import {name} not read ({type(e).__name__}): skipped")
            continue
        pi["task"] = [*pi.get("task", []), *imported.get("task", [])]
        pi["global_option"] = list(dict.fromkeys([*pi.get("global_option", []), *imported.get("global_option", [])]))
        pi["option"] = {**pi.get("option", {}), **imported.get("option", {})}
    return pi


def kind(opt: dict) -> str:
    """An option's type; one with none is a select."""
    return opt.get("type", "select")


SENT = ("select", "switch", "input")  # the types the bot sends; a checkbox or hotkey option is not sent (`build`)


def parse_options(interface: dict, pairs: list[str]) -> dict:
    """The --option NAME=VALUE pairs as build takes them: a select's VALUE is one of its cases, a switch's Yes or No, an
    input's the text it fills in. ValueError names the first pair whose option or case the interface lacks, or whose
    option the bot cannot set (a type it does not send, an input option with several inputs)."""
    options = interface.get("option", {})
    values = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        opt = options.get(name)
        if not sep:
            problem = "takes NAME=VALUE"
        elif opt is None:
            problem = f"interface.json has no option {name}"
        elif kind(opt) not in SENT:
            problem = f"{name} is a {kind(opt)} option, which the bot does not send"
        elif kind(opt) == "input":
            if len(opt["inputs"]) == 1:
                values[name] = value
                continue
            problem = f"{name} has {len(opt['inputs'])} inputs; the bot sets an input option with one"
        elif kind(opt) == "switch":
            if value in YES + NO:
                values[name] = value in YES
                continue
            problem = f"{name} is a switch: Yes or No"
        else:
            cases = [c["name"] for c in opt["cases"]]
            if value in cases:
                values[name] = value
                continue
            problem = f"{name} has no case {value} (cases: {', '.join(cases) or 'none'})"
        raise ValueError(f"--option {pair}: {problem}")
    return values


def build(interface: dict, task: str, values: dict) -> tuple[str, list[dict], list[str]]:
    """(entry, override, used) to post task with: its entry node, the override array MXU would send with these values,
    and each option it went through as NAME=VALUE, marked `(default)` when values did not give it. A password input
    shows only whether it is set. ValueError when the interface has no such task."""
    t = next((t for t in interface.get("task", []) if t["name"] == task), None)
    if t is None:
        names = ", ".join(t["name"] for t in interface.get("task", []))
        raise ValueError(f"interface.json has no task {task} (tasks: {names})")
    override, used = [], []
    if t.get("pipeline_override") is not None:
        override.append(t["pipeline_override"])
    for key in [*interface.get("global_option", []), *t.get("option", [])]:
        collect(key, interface.get("option", {}), values, override, used)
    return t["entry"], override, used


def shown_by(interface: dict, option: str) -> list[tuple[str, str]]:
    """The (option, case) pairs a client must pick for option to be sent, outermost first: an option nested under a case
    is sent only while that case is chosen (collect). None for an option of a task's own list or a global one."""
    options = interface.get("option", {})
    parent = next(((k, c["name"]) for k, o in options.items() for c in o.get("cases", []) if option in c.get("option", [])), None)
    return [] if parent is None else [*shown_by(interface, parent[0]), parent]


def collect(key: str, options: dict, values: dict, override: list, used: list) -> None:
    """Append option key's overrides and its used line, then those of the options nested under its chosen case."""
    opt = options.get(key)
    if opt is None:
        return  # MXU skips an option name with no definition
    given = key in values
    if kind(opt) not in SENT:
        used.append(f"{key}: a {kind(opt)} option, not sent (the bot sends {', '.join(SENT)} options)")
        return
    if kind(opt) == "input":
        fill(key, opt, values.get(key), override, used)
        return
    cases = opt["cases"]
    default = opt.get("default_case") or (cases[0]["name"] if cases else "")
    if kind(opt) == "switch":
        on = values[key] if given else (default or "Yes") in YES
        case = next((c for c in cases if c["name"] in (YES if on else NO)), None)
        shown = case["name"] if case else ("Yes" if on else "No")
    else:
        name = values[key] if given else default
        case = next((c for c in cases if c["name"] == name), None)
        shown = name if case else "(no case)"
    used.append(f"{key}={shown}" + ("" if given else " (default)"))
    if case is None:
        return
    if case.get("pipeline_override") is not None:
        override.append(case["pipeline_override"])
    for nested in case.get("option", []):
        collect(nested, options, values, override, used)


def fill(key: str, opt: dict, given: str | None, override: list, used: list) -> None:
    """An input option: each input's value put in place of its "{name}" in the option's pipeline_override (int bare,
    empty is 0; bool true or false; anything else a JSON string). given is the value of an option with one input; one
    with several takes each input's default. An override that is not JSON once filled in is not sent."""
    text = json.dumps(opt["pipeline_override"], ensure_ascii=False, separators=(",", ":")) if opt.get("pipeline_override") else None
    for item in opt["inputs"]:
        value = given if given is not None else item.get("default") or ""
        shown = ("(set)" if value else "(not set)") if item.get("password") else value
        used.append(f"{key}={shown}" + ("" if given is not None else " (default)"))
        if text is None:
            continue
        pipeline_type = item.get("pipeline_type") or "string"
        if pipeline_type == "int":
            quoted = bare = value or "0"
        elif pipeline_type == "bool":
            quoted = bare = "true" if value.lower() in ("true", "1", "yes", "y") else "false"
        else:
            quoted = json.dumps(value, ensure_ascii=False)
            bare = quoted[1:-1]
        mark = "{" + item["name"] + "}"
        text = text.replace(f'"{mark}"', quoted).replace(mark, bare)
    if text is None:
        return
    try:
        override.append(json.loads(text, parse_constant=not_json))
    except ValueError:
        used[-1] += ": not JSON once filled in, not sent (MXU drops it)"


def not_json(constant: str):
    """json.loads takes NaN and Infinity, which JSON.parse refuses: MXU drops such an override, so it is not JSON here."""
    raise ValueError(f"{constant} is not JSON")
