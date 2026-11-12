"""Name the emulator's screen with the pipeline's own nodes: the probe of `preflight.py screen` and `giveup.py`.

One task runs a DirectHit probe node whose `next` lists the known screens in order, each with its action switched
off, so the first screen node that hits names the screen and nothing is tapped. Each caller sets up its own Tasker:
preflight.py loads the install's `maafw/` and resource, giveup.py the venv's MaaFramework and the repo's resource.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

OFF = {"action": "DoNothing", "next": [], "pre_delay": 0, "post_delay": 0}  # a screen node: its recognition only


def override(probe: str, screens: Iterable[str], timeout_ms: int, own: Mapping[str, dict] | None = None) -> dict:
    """The pipeline override of one probe task: `screens` tried in order, each with its action switched off; `own`
    adds the recognition of a screen that is not a pipeline node."""
    screens = list(screens)
    nodes = {n: {**OFF, **(own or {}).get(n, {})} for n in screens}
    nodes[probe] = {"recognition": "DirectHit", "action": "DoNothing", "next": screens, "timeout": timeout_ms}
    return nodes


def first_hit(node_names: Iterable[str], screens: Iterable[str]) -> str | None:
    """The first of the task's nodes that is one of `screens`: the probe node itself and the rest are not."""
    known = set(screens)
    return next((n for n in node_names if n in known), None)


def look(tasker, probe: str, nodes: dict, screens: Iterable[str]) -> str | None:
    """Run the probe task on `tasker` (bound to a resource and the emulator) and name the screen it hit, or None."""
    job = tasker.post_task(probe, nodes)
    job.wait()
    detail = job.get()
    return first_hit([n.name for n in detail.nodes] if detail else [], screens)
