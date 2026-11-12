"""Read <root>/config/settings.json and check it (docs/spec/04-settings.md section 2).

An older version is migrated in memory only, one older than OLDEST_VERSION refused. The one write the agent makes is the order of `teams` (team_queue.py).
"""

import json
import os
import tempfile
from collections import Counter
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).parent / "settings.schema.json").read_text(encoding="utf-8"))
CURRENT_VERSION = SCHEMA["properties"]["version"]["const"]
# v0.1.0's, the first release: the versions before it were the developers' own files, and their migrations went (#653)
OLDEST_VERSION = 20
# MIGRATIONS[n] turns a version-n dict into a version-(n + 1) dict, one for each n from OLDEST_VERSION up; keep in step with
# gui/src/model.ts.
MIGRATIONS = {}


ROOT = Path(__file__).resolve().parent.parent  # resource/ sits under it in a release, under assets/ in the repo
GIFT_KEYWORDS = SCHEMA["$defs"]["gift_list"]["properties"]["order"]["items"]["enum"]  # the Gift Search page's tabs


def data_dir():
    return next(p for p in (ROOT / "resource", ROOT / "assets" / "resource") if p.is_dir()) / "base" / "data"


@cache
def _recipes():
    return json.loads((data_dir() / "gift_recipes.json").read_text(encoding="utf-8"))


@cache
def gift_tables():
    """data/gift_search.json's gifts (the Gift Search page's, page order) and data/gift_recipes.json's gifts and materials."""
    recipes = _recipes()
    return json.loads((data_dir() / "gift_search.json").read_text(encoding="utf-8"))["gifts"], recipes["gifts"], recipes["materials"]


def pack_gifts():
    """data/gift_recipes.json's `pack_gifts`: theme pack id (a string) -> the ids of the gifts only that pack's pool holds (#417)."""
    return _recipes()["pack_gifts"]


def extra_gifts():
    """data/gift_recipes.json's `extra_gifts`: the game's other gift ids 9000-9999, neither on the Gift Search page nor in a
    recipe (#332); a shop sells some of them (shop_gifts)."""
    return _recipes()["extra_gifts"]


def shop_pool():
    """data/gift_recipes.json's `shop` (#626): `sells`, the ids a shop may sell, and `not_on_normal`, those no NORMAL floor's
    shop shows (the file's note says where they come from)."""
    return _recipes()["shop"]


@cache
def shop_gifts():
    """The gifts a shop may sell, so a list may want and the shop buy them (#626): gift_search.json's in page order, then
    the materials' and extra_gifts' of gift_recipes.json in data order."""
    sells = set(shop_pool()["sells"])
    search, _, materials = gift_tables()
    return [g for g in search + materials + extra_gifts() if g["id"] in sells]


def vestiges():
    """data/gift_recipes.json's `vestiges`: the five gifts that are only fusion or sale material, tier I-V (ids 9991-9995, #161)."""
    return _recipes()["vestiges"]


@cache
def vestige_ids():
    return frozenset(v["id"] for v in vestiges())


def default_gorder():
    """Spec 04 section 13: every keyword's gifts a shop may sell (shop_gifts), the highest tier first, within a tier in
    shop_gifts' order."""
    by_tier = sorted(shop_gifts(), key=lambda g: -g["tier"])  # stable: shop_gifts' order within a tier
    return {k: [g["id"] for g in by_tier if g["keyword"] == k] for k in GIFT_KEYWORDS}


def keyword_gifts():
    """Every gift a list names by its keyword (spec 04 section 13): the Gift Search page's, the fusion gifts, the recipe
    materials and the other gifts (extra_gifts: a shop, a keyword fusion or an event gives one, and the shop tells it apart,
    #332); not the vestiges."""
    search, fusions, materials = gift_tables()
    return search + fusions + materials + extra_gifts()


def known_gift_ids():
    return {g["id"] for g in keyword_gifts()} | vestige_ids()


def clean_gift_list(gift_list):
    """(the list as the shop logic (agent/gifts.py) and the GUI use it, number of ids dropped from want and keep), spec 04 section 13: ids no data
    file has are dropped; a gorder keyword lacks gifts: they go last in data-file order, ids that keyword does not have are
    dropped (a missing keyword gets the default order). Else it stays: want may hold a gift that cannot be bought."""
    known = known_gift_ids()
    dropped = 0

    def known_only(ids):
        nonlocal dropped
        dropped += sum(i not in known for i in ids)
        return [i for i in ids if i in known]

    gorder = {}
    for kw, default in default_gorder().items():
        given = [i for i in gift_list["gorder"].get(kw, []) if i in default]
        gorder[kw] = list(dict.fromkeys(given)) + [i for i in default if i not in given]
    return {**gift_list, "want": known_only(gift_list["want"]), "keep": known_only(gift_list["keep"]), "gorder": gorder}, dropped


NO_TEAM = "No enabled team: set up a team in the settings GUI first."


class SettingsError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Invalid settings:\n" + "\n".join(f"- {e}" for e in errors))


def settings_path(root):
    return Path(root) / "config" / "settings.json"


def write_settings(root, data, expected):
    """Write data in the GUI's format (gui/src/App.tsx toText) when the file still reads `expected`, the text the caller
    read; False, and nothing written, when another writer changed it since. Via a temp file in the same folder and
    os.replace, so a crash never leaves half a file."""
    path = settings_path(root)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if path.read_text(encoding="utf-8") != expected:
            os.unlink(tmp)
            return False
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return True


def load_settings(root, need_team=False):
    """Return the checked settings dict, or raise SettingsError listing every problem.

    need_team: MirrorDungeon's own check, an enabled team (#364); the dailies run without one.
    """
    path = settings_path(root)
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
    if not errors:  # ids a new season dropped are ignored, as the GUI drops them on load
        data["gift_lists"] = [clean_gift_list(gift_list)[0] for gift_list in data["gift_lists"]]
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
        if version not in MIGRATIONS:  # the GUI says the same (gui/src/model.ts parseSettings)
            raise SettingsError([f"settings version {version} is too old: maalc reads version {OLDEST_VERSION} and later; "
                                 "start a new settings file in the settings GUI"])
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
    for key in ("deployment_order_plans", "starlight_plans", "theme_pack_plans", "gift_lists"):
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
            ("gift_list", None if t["gift_list"] == "default" else t["gift_list"], "gift_lists"),
        ]
        for field, ref, key in refs:
            if ref is not None and ref not in plan_ids[key]:
                errors.append(f"teams/{i}/{field}: team {t['name']!r} uses missing plan {ref!r} (not in {key})")

    for i, t in enumerate(teams):
        sinners = t["skill_replacement"]["sinners"]
        dupes(f"teams/{i}/skill_replacement/sinners", [s["sinner"] for s in sinners], "sinner")
        for j, s in enumerate(sinners):
            # the deck starts at the game's 3/2/1 and every swap moves a card up, so S1 above 3 or S3 below 1 is never reached
            path, who, target = f"teams/{i}/skill_replacement/sinners/{j}/target", f"team {t['name']!r} sinner {s['sinner']!r}", s["target"]
            if sum(target.values()) != 6:
                errors.append(f"{path}: {who} targets {sum(target.values())} skills, not 6")
            if target["s1"] > 3:
                errors.append(f"{path}/s1: {who} targets {target['s1']} of skill 1, but swaps only lower it from the game's 3")
            if target["s3"] < 1:
                errors.append(f"{path}/s3: {who} targets {target['s3']} of skill 3, but swaps only raise it from the game's 1")

    target_floor = data["run"]["target_floor"]
    if target_floor > 5:
        # floors 6+ open only when every floor of the run was HARD, and the rotation picks from the enabled teams (#385)
        need = f"but target_floor {target_floor} needs the whole run HARD"
        if data["run"]["difficulty"] == "normal":
            errors.append(f"run/difficulty: difficulty is 'normal', {need}")
        for i, t in enumerate(teams):
            if not t["enabled"]:
                continue
            if t["usage"] == "normal_only":
                errors.append(f"teams/{i}/usage: team {t['name']!r} is normal_only, {need}")
            if t["hard_from_floor"] is None:
                errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} never switches to HARD, {need} (hard_from_floor 1)")
            elif t["hard_from_floor"] != 1:
                errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} starts HARD at floor {t['hard_from_floor']}, {need} (hard_from_floor 1)")

    for i, gift_list in enumerate(data["gift_lists"]):
        errors.extend(
            f"gift_lists/{i}: list {gift_list['name']!r} has gift {gid} in both want and keep"
            for gid in gift_list["want"] if gid in gift_list["keep"]
        )

    team_ids = {t["id"] for t in teams}
    for task, opts in data["luxcavation"].items():
        if opts["team"] is not None and opts["team"] not in team_ids:
            errors.append(f"luxcavation/{task}/team: team {opts['team']!r} is not in teams")

    dupes("event_overrides", [o["question"] for o in data["event_overrides"]], "question")
    dupes("trial_risk_overrides", [o["trial"] for o in data["trial_risk_overrides"]], "trial")
    return errors
