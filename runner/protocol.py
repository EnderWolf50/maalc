"""The runner's protocol: one JSON object a line, commands on its stdin and events on its stdout, each with "v": VERSION.

Commands (one runner process takes one start or one scan, then ends):
- scan: report the devices MaaFramework finds (`devices`), MuMu first, then `end`.
- start: run `tasks` in turn, each {entry}: the task's entry node, which reads its options from the settings file at
  its start (#813). `root` is the install (default: the folder that holds runner/). `device` picks the emulator:
  `address` (default: the first device the scan finds), and `mumu_index` with `mumu_manager` to start a MuMu that is
  not running.
- stop: during a start, stop MaaFramework; the running task ends `stopped`, the ones after it `cancelled`.

Events: ready, log (a line of the run log, `source` runner, agent or console), devices, connection, resource, task (a
task's `state`: pending, running, succeeded, failed, stopped or cancelled, with the bot's `reason` for one it cancelled
and for the one it failed by stopping the whole list), error (its `kind`), end (the run's `result`).
tests/runner_cases.json holds the shared cases.
"""
from __future__ import annotations

import json

VERSION = 1

SOURCES = ("runner", "agent", "console")
STATES = ("pending", "running", "succeeded", "failed", "stopped", "cancelled")
CONNECTION = ("launching", "waiting", "connecting", "connected")
RESOURCE = ("loading", "loaded")
RESULTS = ("succeeded", "failed", "stopped")
ERRORS = ("protocol", "device_missing", "launch_failed", "device_timeout", "connect_failed", "resource_failed",
          "agent_failed", "agent_exit", "stop_timeout", "internal")


class ProtocolError(ValueError):
    """A command or event that does not follow the protocol; the message says what is wrong."""


def _str(v):
    return isinstance(v, str)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _one_of(*values):
    return lambda v: isinstance(v, str) and v in values


def _nullable(check):
    return lambda v: v is None or check(v)


def _list(check):
    return lambda v: isinstance(v, list) and all(check(i) for i in v)


def _obj(required, optional=None):
    optional = optional or {}

    def check(v):
        return (isinstance(v, dict) and set(required) <= set(v) <= set(required) | set(optional)
                and all(c(v[k]) for k, c in {**required, **optional}.items() if k in v))
    return check


DEVICE = _obj({"name": _str, "address": _str, "adb_path": _str,
               "mumu": _nullable(_obj({"index": _int, "manager": _str, "path": _str}))})
# event: (required fields, optional fields), each with its check; "v" and "event" come on top
EVENTS = {
    "ready": ({"pid": _int}, {}),
    "log": ({"t": _str, "source": _one_of(*SOURCES), "line": _str}, {}),
    "devices": ({"devices": _list(DEVICE)}, {}),
    "connection": ({"state": _one_of(*CONNECTION), "address": _str}, {}),
    "resource": ({"state": _one_of(*RESOURCE)}, {}),
    "task": ({"index": _int, "entry": _str, "state": _one_of(*STATES)}, {"reason": _nullable(_str)}),
    "error": ({"kind": _one_of(*ERRORS), "message": _str}, {"code": _int, "tail": _list(_str)}),
    "end": ({"result": _one_of(*RESULTS)}, {}),
}


def event(name: str, /, **fields) -> dict:
    return {"v": VERSION, "event": name, **fields}


def check_event(e) -> None:
    """ProtocolError unless e is a well-formed event."""
    if not isinstance(e, dict) or e.get("v") != VERSION or e.get("event") not in EVENTS:
        raise ProtocolError(f"not an event of protocol version {VERSION}: {e!r}"[:200])
    required, optional = EVENTS[e["event"]]
    if not _obj({"v": _int, "event": _str, **required}, optional)(e):
        raise ProtocolError(f"{e['event']}: fields do not match the protocol: {e!r}"[:200])


def line(e: dict) -> str:
    """The event as one line of JSON, UTF-8 text as it is."""
    return json.dumps(e, ensure_ascii=False, separators=(",", ":"))


def _fields(where: str, given: dict, allowed) -> None:
    for k in given:
        if k not in allowed:
            raise ProtocolError(f"{where}: unknown field {k!r}")


def _task(i: int, t) -> dict:
    if not isinstance(t, dict):
        raise ProtocolError(f"start: tasks[{i}] must be an object")
    _fields(f"start: tasks[{i}]", t, ("entry",))
    if not isinstance(t.get("entry"), str) or not t["entry"]:
        raise ProtocolError(f"start: tasks[{i}].entry must name the task's entry node")
    return {"entry": t["entry"]}


def _device(d) -> dict:
    if d is None:
        d = {}
    if not isinstance(d, dict):
        raise ProtocolError("start: device must be an object")
    _fields("start: device", d, ("address", "mumu_index", "mumu_manager"))
    for key, check, what in (("address", _str, "an adb address"), ("mumu_index", _int, "a MuMu instance number"),
                             ("mumu_manager", _str, "MuMuManager.exe's path")):
        if d.get(key) is not None and not check(d[key]):
            raise ProtocolError(f"start: device.{key} must be {what} or null")
    return {"address": d.get("address"), "mumu_index": d.get("mumu_index"), "mumu_manager": d.get("mumu_manager")}


def command(text: str) -> dict:
    """The command one line holds, checked and with its defaults filled in; ProtocolError says what is wrong."""
    try:
        msg = json.loads(text)
    except ValueError:
        raise ProtocolError(f"not JSON: {text[:80]!r}") from None
    if not isinstance(msg, dict):
        raise ProtocolError("not a JSON object")
    if msg.get("v") != VERSION:
        raise ProtocolError(f"protocol version {msg.get('v')!r}, the runner speaks {VERSION}")
    cmd = msg.get("cmd")
    if cmd not in ("start", "stop", "scan"):
        raise ProtocolError(f"unknown command {cmd!r}")
    if cmd != "start":
        _fields(cmd, msg, ("v", "cmd"))
        return {"cmd": cmd}
    _fields("start", msg, ("v", "cmd", "tasks", "root", "device"))
    tasks = msg.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ProtocolError("start: tasks must be a list of at least one task")
    if msg.get("root") is not None and not isinstance(msg["root"], str):
        raise ProtocolError("start: root must be the install's folder or null")
    return {"cmd": "start", "root": msg.get("root"), "device": _device(msg.get("device")),
            "tasks": [_task(i, t) for i, t in enumerate(tasks)]}
