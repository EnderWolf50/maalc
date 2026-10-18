"""Read <root>/config/settings.json and check it (docs/spec/04-settings.md section 2).

The agent never writes settings: old versions are migrated in memory only.
"""

import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).parent / "settings.schema.json").read_text(encoding="utf-8"))
CURRENT_VERSION = SCHEMA["properties"]["version"]["const"]

def _v1_to_v2(data):
    """Version 2 adds teams[].guard_turns (#52); its short orders need nothing."""
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:  # a broken file is left to the checks
        if isinstance(team, dict):
            team.setdefault("guard_turns", 0)
    return data


def _v2_to_v3(data):
    """Version 3 adds teams[].gift_search (#54), off."""
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:
        if isinstance(team, dict):
            team.setdefault("gift_search", {"enabled": False, "gifts": []})
    return data


def _v3_to_v4(data):
    """Version 4 adds run.theme_pack_refresh (#41), "all" as before."""
    if isinstance(data.get("run"), dict):
        data["run"].setdefault("theme_pack_refresh", "all")
    return data


# MIGRATIONS[n] turns a version-n dict into a version-(n + 1) dict; keep in step with gui/src/model.ts.
MIGRATIONS = {1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4}

NO_TEAM = "No enabled team: set up a team in the settings GUI first."


class SettingsError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Invalid settings:\n" + "\n".join(f"- {e}" for e in errors))


def load_settings(root):
    """Return the checked settings dict, or raise SettingsError listing every problem."""
    path = Path(root) / "config" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError([f"{path} not found. {NO_TEAM}"]) from None
    except (OSError, ValueError) as e:
        raise SettingsError([f"{path} is not readable JSON: {e}"]) from None

    data = migrate(data)
    errors = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
        for e in sorted(Draft202012Validator(SCHEMA).iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
    ]
    # Cross-checks assume the structure is valid.
    errors = errors or cross_check(data)
    if errors:
        raise SettingsError(errors)
    return data


def migrate(data):
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, int) or isinstance(version, bool):
        raise SettingsError([f"version must be an integer, got {version!r}"])
    if version > CURRENT_VERSION:
        raise SettingsError([f"settings version {version} is newer than this agent supports ({CURRENT_VERSION}); update maalc"])
    while version < CURRENT_VERSION:
        if version not in MIGRATIONS:
            raise SettingsError([f"settings version {version} cannot be migrated"])
        data = MIGRATIONS[version](data)
        version += 1
        data["version"] = version
    return data


def cross_check(data):
    """The checks spec 04 section 2 says the schema cannot express."""
    errors = []

    def dupes(path, values, what):
        errors.extend(f"{path}: {what} {v!r} appears {n} times" for v, n in Counter(values).items() if n > 1)

    plan_ids = {}
    for key in ("deployment_order_plans", "starlight_plans", "theme_pack_plans"):
        plan_ids[key] = {p["id"] for p in data[key]}
        dupes(key, [p["id"] for p in data[key]], "id")
        dupes(key, [p["name"] for p in data[key]], "name")
    teams = data["teams"]
    dupes("teams", [t["id"] for t in teams], "id")

    enabled = [t for t in teams if t["enabled"]]
    if not enabled:
        errors.append(NO_TEAM)
    for slot, n in Counter(t["game_team"] for t in enabled).items():
        if n > 1:
            names = ", ".join(repr(t["name"]) for t in enabled if t["game_team"] == slot)
            errors.append(f"teams: enabled teams {names} all use TEAMS #{slot}")

    for i, t in enumerate(teams):
        refs = [
            ("deployment_order", t["deployment_order"].get("plan"), "deployment_order_plans"),
            ("starlight", t["starlight"].get("plan"), "starlight_plans"),
            ("theme_pack_plan", None if t["theme_pack_plan"] == "default" else t["theme_pack_plan"], "theme_pack_plans"),
        ]
        for field, ref, key in refs:
            if ref is not None and ref not in plan_ids[key]:
                errors.append(f"teams/{i}/{field}: team {t['name']!r} uses missing plan {ref!r} (not in {key})")

    dupes("event_overrides", [o["question"] for o in data["event_overrides"]], "question")
    dupes("trial_risk_overrides", [o["trial"] for o in data["trial_risk_overrides"]], "trial")
    return errors
