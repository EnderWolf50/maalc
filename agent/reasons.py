"""Stop reason codes (#881): a stop reason that the settings window shows in its own language.

A Reason is the stop's English text, as the log and the webhook have it, with a code of stop_reasons.json and its params
on top. The stop procedure logs the code after the stop line (code_line), and the runner and the window read it there. A
reason with no code (a plain str) shows its English text.
"""
from __future__ import annotations

import json
from pathlib import Path

CODES = json.loads((Path(__file__).with_name("stop_reasons.json")).read_text(encoding="utf-8"))["codes"]
CODE_LINE = "stop code: "  # after "[maalc] ", as log() writes it: runner/session.py and gui/src/runner.ts read it


class Reason(str):
    """A stop reason: str is its English text, code and params what the settings window fills its sentence with."""

    code: str
    params: dict

    def __new__(cls, text: str, code: str, **params) -> Reason:
        r = super().__new__(cls, text)
        r.code, r.params = code, params
        return r


def code_line(reason) -> str | None:
    """The line the stop procedure logs after its stop line: the reason's code, then its params as JSON when it has any;
    None for a reason with no code."""
    code = getattr(reason, "code", None)
    if code is None:
        return None
    params = getattr(reason, "params", {})
    return CODE_LINE + code + (" " + json.dumps(params, ensure_ascii=False, separators=(",", ":")) if params else "")


def carried(text: str, parts: list):
    """text, a reason made of parts (an OptionsError's errors), with the code of its one part when that part has one."""
    return Reason(text, parts[0].code, **parts[0].params) if len(parts) == 1 and getattr(parts[0], "code", None) else text


def of_node(node: str, text: str):
    """A pipeline node's stop (StopTask, Halt): coded by the node's name when stop_reasons.json has it."""
    return Reason(text, node) if node in CODES else text
