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


def _v4_to_v5(data):
    """Version 5 adds teams[].allow_white_gossypium (#90), on as before."""
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:
        if isinstance(team, dict):
            team.setdefault("allow_white_gossypium", True)
    return data


def _v5_to_v6(data):
    """Version 6 turns the numbers whose 0 meant something into switches (#137).

    run.runs 0 (no limit) becomes null, off; teams[].hard_from_floor 0 (the whole run HARD) becomes 1,
    which says the same. teams[].min_alive stays a number: 0 is no check.
    """
    run = data.get("run")
    if isinstance(run, dict) and run.get("runs") == 0:
        run["runs"] = None
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:
        if isinstance(team, dict):
            if team.get("hard_from_floor") == 0:
                team["hard_from_floor"] = 1
    return data


def _v6_to_v7(data):
    """Version 7 adds what the shop keeps out of fusions and sales (#77, #161), as before: teams[].keep_keywords none,
    keywordless "keep" (keep_keywordless on before #161 merged it), keep_gifts none. sell_max_tier 4 and sell_vestiges
    off are the user's defaults (#161): a tier V and a vestige are never sold (a vestige is keywordless: "keep" kept it)."""
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:
        if isinstance(team, dict):
            team.setdefault("keep_keywords", [])
            team.setdefault("keywordless", "keep")
            team.setdefault("keep_gifts", [])
            team.setdefault("sell_max_tier", 4)
            team.setdefault("sell_vestiges", False)
    return data


def _v7_to_v8(data):
    """Version 8 adds run.auto_accept_terms and run.auto_download (#85, #86), on: the user's decision (2026-10-21)."""
    if isinstance(data.get("run"), dict):
        data["run"].setdefault("auto_accept_terms", True)
        data["run"].setdefault("auto_download", True)
    return data


MARK_WEIGHTS = {"prefer": 5, "neutral": 0, "avoid": -5}


def _v8_to_v9(data):
    """Version 9 weighs theme packs (#240): prefer / neutral / avoid become 5 / 0 / -5, threshold 0 (refresh while every
    pack is avoided), unlisted 0 (neutral), event packs by weight: the same picks as before."""
    plans = data.get("theme_pack_plans")
    for plan in plans if isinstance(plans, list) else []:
        if isinstance(plan, dict) and isinstance(plan.get("marks"), dict):
            plan["weights"] = {k: MARK_WEIGHTS.get(v, v) for k, v in plan.pop("marks").items()}  # a bad mark stays bad
            plan.update(threshold=0, unlisted=0, event_packs="weight")
    return data


def _v9_to_v10(data):
    """Version 10 adds teams[].fusion_condition (#263), "any": the shop fuses as before."""
    teams = data.get("teams")
    for team in teams if isinstance(teams, list) else []:
        if isinstance(team, dict):
            team.setdefault("fusion_condition", "any")
    return data


def _v10_to_v11(data):
    """Version 11 adds run.keep_dismissed_screens (#244), on."""
    if isinstance(data.get("run"), dict):
        data["run"].setdefault("keep_dismissed_screens", True)
    return data


# MIGRATIONS[n] turns a version-n dict into a version-(n + 1) dict; keep in step with gui/src/model.ts.
MIGRATIONS = {1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4, 4: _v4_to_v5, 5: _v5_to_v6, 6: _v6_to_v7, 7: _v7_to_v8, 8: _v8_to_v9, 9: _v9_to_v10, 10: _v10_to_v11}

NO_TEAM = "No enabled team: set up a team in the settings GUI first."


class SettingsError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Invalid settings:\n" + "\n".join(f"- {e}" for e in errors))


def load_settings(root, need_team=False):
    """Return the checked settings dict, or raise SettingsError listing every problem.

    need_team: MirrorDungeon's own check, an enabled team (#364); the dailies run without one.
    """
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
    if need_team and not errors and not any(t["enabled"] for t in data["teams"]):
        errors.append(NO_TEAM)
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
