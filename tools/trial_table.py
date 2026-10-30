"""Every Mounting Trial pool of the unpacked client into assets/resource/base/data/trials.yaml (#381).

Usage: uv run python tools/trial_table.py [static-data dir] [Localize/en dir] [--check]
Defaults: the main checkout's .local/unpack (tools/local_dir.py), client 1.117.0: its static data and English
localization. --check writes nothing and exits 1 when the committed file differs from what the data gives.

Pool n is the pick after the floor-n boss: floors[n-1].enemyBuffPool of mirrordungeon-08*.json, the same in every mode.
Its hidden gifts carry no link to a trial; the k-th of pool n is the k-th trial of id group n (MD5n1..., MD610x for
pools 10-14): each pool holds as many as its group, and 28 cards seen live in pools 1-4 all agree (#381). The trials'
values come from the static buff files, read against their English descriptions.

Score: enemy Clash Power points (pt), 1 pt = the enemy's Clash Power +1, the sum of each effect's weight x its value
(docs/spec/03-decisions.md section 12). Pools 1-4 and pools 5+ weigh differently: a guide's "never take" effects
(Damage Taken -x%, Damage Dealt +x%, Coin Power) cost 4 pt and more there. A Coin unit of pools 5+ is scored at the
in-budget weight; the agent adds coin_over - coin_in for each unit past the run's budget. MODEL's coin_budget is the
one place to raise that budget (a guide: "take some, not too many"); no setting holds it yet.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))
from local_dir import local_dir  # noqa: E402
from rewards import parse_effects  # noqa: E402

OUT = ROOT / "assets/resource/base/data/trials.yaml"
CLIENT = "1.117.0"
MODES = ("08", "08-hard", "08-infinite", "08-extreme")  # NORMAL, HARD, INFINITY, EXTREME (15 floors)

# Static ability -> (effect, factor to the description's number). Damage Taken is a negative multiplier: -0.05 is -5%.
ABILITIES = {"AtkAdder": ("offense", 1), "DefAdder": ("defense", 1), "DefaultMaxHpMultiplier": ("hp", 100),
             "DefaultMaxHpMultiplierBossRoomOnly": ("boss_hp", 100), "ParryingResultAdder": ("clash", 1),
             "SkillPowerResultAdder": ("final", 1), "SkillPowerAdder": ("base", 1), "PlusCoinScaleAdder": ("coin", 1),
             "MinusCoinScaleAdder": ("coin_minus", -1), "TakeAtkDamageMultiplier": ("taken", -100),
             "AtkDamageMultiplier": ("dealt", 100), "DefSkillPowerResultAdder": ("defskill", 1)}
# Where the static value and the description disagree, the static value (what the game applies) is kept.
TEXT_DIFFERS = {"MD542": {"hp"}}  # Body Up II: static Max HP 12.5%, description and screen +10%

# The model (#381, the user's decision of 2026-10-29). Pools 5+: a guide's points, 3 Offense Levels = 1 Clash Power,
# 1 Offense Level = 3.33% damage, so 1% damage = 0.1 pt; Base and Final 0.05 over Clash, an Offense Level 0.01 over a
# third, for the guide's tie-break Clash > Offense Level >= Base = Final. Defense Level and Max HP only break ties.
EARLY_POOLS = 4
WEIGHTS = {"clash": 1.0, "offense": 0.34, "base": 1.05, "final": 1.05, "coin": 1.5, "dealt": 0.1, "taken": 0.1,
           "defense": 0.02, "hp": 0.005, "boss_hp": 0.005, "defskill": 0.1}
EARLY_WEIGHTS = WEIGHTS | {"coin": 4.0, "dealt": 0.8, "taken": 0.8}  # pools 1-4: never take them (4 pt > a main gift's 3)
MODEL = {"early_pools": EARLY_POOLS, "level": 0.5, "coin_budget": 0, "coin_in": WEIGHTS["coin"], "coin_over": 3.0}


def load(path):
    """A client JSON file; the mirror dungeon files have whole-line // comments."""
    text = path.read_text(encoding="utf-8-sig")
    return json.loads("\n".join(line for line in text.splitlines() if not line.strip().startswith("//")))


def score(effects, pool):
    weights = EARLY_WEIGHTS if pool <= EARLY_POOLS else WEIGHTS
    return sum(weights[k] * v for k, v in effects.items())


def table(static, en):
    """{name: {"id", "pool", "effects", "score"}} in pool order, and the pool sizes; asserts what the data must hold."""
    names = {d["id"]: (d["name"], d.get("desc", "")) for f in ("EN_Bufs_Mirror5.json", "EN_Bufs_Mirror6.json")
             for d in load(en / f)["dataList"]}
    buffs = {b["id"]: b.get("list", []) for f in ("mirror-dungeon-5-floor-buff.json", "mirror-dungeon-5-infinite-floor-buff.json",
                                                  "mirror-dungeon-6-infinite-floor-buff.json")
             for b in load(static / "buff" / f)["list"]}  # with EXTREME's Mounting Adversities (MD6Limit*), not trials
    groups = [sorted((i for i in names if re.fullmatch(rf"MD5{g}\d", i)), key=lambda i: int(i[2:])) for g in range(1, 10)]
    groups += [sorted((i for i in names if re.fullmatch(rf"MD61{g}\d", i)), key=lambda i: int(i[2:])) for g in range(5)]  # pools 10-14
    modes = [[f["enemyBuffPool"] for f in load(static / f"mirrordungeon/mirrordungeon-{m}.json")["list"][0]["floors"]]
             for m in MODES]
    longest = max(modes, key=len)
    for pools in modes:  # every mode draws floor n's pick from the same pool
        assert all(p in ([], longest[n]) for n, p in enumerate(pools)), "a mode has a pool of its own"
    sizes = [len(p) for p in longest if p]
    assert sizes == [len(g) for g in groups], (sizes, [len(g) for g in groups])
    trials = {}
    for pool, ids in enumerate(groups, 1):
        for i in ids:
            name, desc = names[i]
            effects = {}
            for a in buffs[i]:
                assert a["ability"] in ABILITIES, (i, a["ability"])  # a new kind of effect: weigh it first
                key, factor = ABILITIES[a["ability"]]
                effects[key] = round(a["value"] * factor, 4)
            assert effects.pop("coin_minus", None) == effects.get("coin"), i  # Plus and Minus Coin Power come in pairs
            shown = parse_effects(desc)
            assert {k for k in effects | shown if effects.get(k) != shown.get(k)} == TEXT_DIFFERS.get(i, set()), (i, effects, shown)
            assert name not in trials, name  # overrides and the OCR go by name
            trials[name] = {"id": i, "pool": pool, "effects": effects, "score": round(score(effects, pool), 4)}
    return trials, sizes


def num(v):
    return f"{v:g}"


def flow(d):
    return "{" + ", ".join(f"{k}: {num(v) if isinstance(v, (int, float)) else v}" for k, v in d.items()) + "}"


def render(trials, sizes):
    lines = [
        "# Mounting Trials of every pool (#381, docs/spec/05-game-data.md section 4). Generated by tools/trial_table.py from the",
        f"# game client {CLIENT}'s static data and English localization; game data (c) Project Moon, see NOTICE.md.",
        "# Do not edit: rerun the tool. Settings trial_risk_overrides replace a trial's score, by name.",
        "# pool n: the pick after the floor-n boss. effects: on the enemy (offense/defense: Offense/Defense Level, hp/boss_hp: Max HP /",
        "# Boss Max HP %, clash/final/base: Clash/Final/Base Power, coin: Plus and Minus Coin Power, taken: Damage Taken -%,",
        "# dealt: Damage Dealt +%, defskill: Defense Skill Final Power). score: pt, 1 pt = the enemy's Clash Power +1; a Coin",
        "# unit of a pool past early_pools at coin_in, coin_over past the run's coin_budget. level: pt per Enemy Level Up +1.",
        f"client: {CLIENT}",
        f"model: {flow(MODEL)}",
        f"weights: {{early: {flow(EARLY_WEIGHTS)}, late: {flow(WEIGHTS)}}}",
        "pools: {" + ", ".join(f"{n}: {s}" for n, s in enumerate(sizes, 1)) + "}",
        "trials:",
    ]
    lines += [f"  {name}: {{id: {t['id']}, pool: {t['pool']}, effects: {flow(t['effects'])}, score: {num(t['score'])}}}"
              for name, t in trials.items()]
    return "\n".join(lines) + "\n"


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    unpack = None if len(args) >= 2 else local_dir("unpack")
    static = Path(args[0]) if args else unpack / "static/Assets/Resources_moved/StaticData/static-data"
    en = Path(args[1]) if len(args) > 1 else unpack / "raw/Localize/en"
    text = render(*table(static, en))
    if check:
        same = OUT.read_text(encoding="utf-8") == text
        print("trials.yaml is up to date" if same else "trials.yaml differs from the game data: rerun tools/trial_table.py")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"{text.count('{id: ')} trials -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
