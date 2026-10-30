"""What a gift list (docs/spec/04-settings.md section 13) makes of a gift: its state, what locks it, the buy queue, the fusion to make.

Pure data in, data out, no MaaFramework (the shop, the other actions and the GUI's model.ts use the same rules; both
sides run tests/gift_list_cases.json). A gift list here is a cleaned one (settings.clean_gift_list): `order`, `want`, `keep`,
`gorder`. `tables` is {"buyable": gift_search.json's gifts, "fusions": gift_recipes.json's gifts}, the game files' when None.
`run_packs` are the ids of the theme packs the run took, None when unknown (the agent restarted mid-run): then a pack-specific
fusion locks its materials all the same. `owned` are the ids of the gifts held (repeats count), none when unknown: a wanted
fusion held is made no more, so it locks and buys nothing (the user, 2026-10-30).
"""
from collections import Counter
from functools import cache

import yaml

import settings


@cache
def _game_tables():
    buyable, fusions, _ = settings.gift_tables()
    return {"buyable": buyable, "fusions": fusions}


@cache
def default_list():
    """data/gift_lists.yaml's default list: the fields of a settings gift list without id and name."""
    return yaml.safe_load((settings.data_dir() / "gift_lists.yaml").read_text(encoding="utf-8"))["default_list"]


def resolve_list(ref, gift_lists):
    """The list a team's `gift_list` names: "default" is the data file's list. None when no list has that id."""
    if ref == "default":
        return default_list()
    return next((g for g in gift_lists if g["id"] == ref), None)


def main_keyword(gift_list):
    """The first keyword of `order` that is not Keywordless: the team's main keyword."""
    return next(k for k in gift_list["order"] if k != "Keywordless")


def state(gift_list, gift_id):
    """"want", "keep" or "drop" (everything the list does not mention)."""
    return "want" if gift_id in gift_list["want"] else "keep" if gift_id in gift_list["keep"] else "drop"


def _materials(fusion):
    return [i for recipe in fusion.get("recipes", []) for i in recipe] + [i for group in fusion.get("groups", []) for i in group["ids"]]


def _to_make(gift_list, fusion, run_packs, owned):
    """Whether the list still makes `fusion`: wanted, not owned, and not pack-specific (data `specific`) unless run_packs and
    its `packs` share one, or run_packs is None."""
    return (state(gift_list, fusion["id"]) == "want" and fusion["id"] not in owned
            and (not fusion.get("specific") or run_packs is None or bool(set(fusion.get("packs", [])) & set(run_packs))))


def lockers(gift_list, gift_id, run_packs=None, tables=None, owned=()):
    """The fusions the list still makes (_to_make) that lock a drop gift, in data-file order: it is a material of any of
    their recipes, or of any group."""
    if state(gift_list, gift_id) != "drop":
        return []
    return [f["id"] for f in (tables or _game_tables())["fusions"] if gift_id in _materials(f) and _to_make(gift_list, f, run_packs, owned)]


def effective(gift_list, gift_id, run_packs=None, tables=None, owned=()):
    """"want", "keep" (kept, or a drop gift something locks) or "drop"."""
    own = state(gift_list, gift_id)
    return "keep" if own == "drop" and lockers(gift_list, gift_id, run_packs, tables, owned) else own


def queue(gift_list, tables=None):
    """The ids to buy, first first: per keyword in `order`, its `gorder` gifts the list wants and the shop sells."""
    buyable = {g["id"] for g in (tables or _game_tables())["buyable"]}
    return [i for k in gift_list["order"] for i in gift_list["gorder"][k] if i in buyable and state(gift_list, i) == "want"]


def purchases(gift_list, run_packs=None, owned=(), tables=None):
    """What the shop buys, first first: (id, None) for each gift of `queue` (the list wants it), then (id, fusion id) for each
    gift the shop sells that a fusion the list still makes (_to_make; in recipe_fusion's order) lacks: none once `owned`
    completes one of its recipes or its groups; else each id a recipe needs more of than owned, and the ids not owned of
    a group short of its `need`. Each id once, for its first reason. Nothing marks a material: it keeps its own state, and is
    bought no more once its fusion is owned (the user, 2026-10-30). A pack-specific fusion buys nothing while run_packs is
    None (the agent restarted mid-run): the run may never have pulled its pack, so its Cost would be lost; its materials
    stay locked all the same (lockers)."""
    tables = tables or _game_tables()
    buyable, held, out = {g["id"] for g in tables["buyable"]}, Counter(owned), {i: None for i in queue(gift_list, tables)}
    for fusion in _in_list_order(gift_list, tables["fusions"]):
        if (fusion.get("specific") and run_packs is None) or not _to_make(gift_list, fusion, run_packs, held) or _pick(fusion, held, None):
            continue
        short = [i for recipe in fusion.get("recipes", []) for i, n in Counter(recipe).items() if held[i] < n]
        short += [i for group in fusion.get("groups", []) if sum(held[i] > 0 for i in group["ids"]) < group["need"]
                  for i in group["ids"] if not held[i]]
        for i in short:
            if i in buyable:
                out.setdefault(i, fusion["id"])
    return list(out.items())


def _in_list_order(gift_list, fusions):
    """The fusions in list order: the keyword's place in `order` (`queue`'s), then data-file order (a fusion is in no
    `gorder`, which holds the shop's gifts)."""
    place = {k: n for n, k in enumerate(gift_list["order"])}
    return sorted(fusions, key=lambda f: place.get(f["keyword"], len(place)))


def _pick(fusion, owned, slots):
    """The materials to put in for `fusion`, or None: the first recipe `owned` (a Counter) has all of; for groups the first
    `need` owned ids of each group in data-file order. A set needing more than `slots` materials (None: any) is passed over."""
    room = slots or 99
    for recipe in fusion.get("recipes", []):
        if len(recipe) <= room and all(owned[i] >= n for i, n in Counter(recipe).items()):
            return list(recipe)
    groups = [[i for i in group["ids"] if owned[i]][:group["need"]] for group in fusion.get("groups", [])]
    if groups and all(len(picked) == group["need"] for picked, group in zip(groups, fusion["groups"])):
        picks = [i for picked in groups for i in picked]
        return picks if len(picks) <= room else None
    return None


def recipe_fusion(gift_list, owned_ids, tables=None, slots=None, skip=()):
    """{"gift": id, "materials": [ids]} for the first wanted fusion in list order (_in_list_order) whose materials `owned_ids`
    (a list, repeats count) hold, else None. A pack-specific fusion is made whatever the run packs. `slots`: the fuse page's
    material slots; a recipe needing more is passed over (the next wanted one is tried). `skip`: fusion ids not to make (the
    page refused them this visit). A fusion already owned is not made again. Every owned gift is a material, whatever its
    state: a wanted fusion comes before any keep (the user, 2026-10-30: "want is the highest priority, it may eat a keep")."""
    held = Counter(owned_ids)
    for fusion in _in_list_order(gift_list, (tables or _game_tables())["fusions"]):
        if fusion["id"] in skip or fusion["id"] in held or state(gift_list, fusion["id"]) != "want":
            continue
        if materials := _pick(fusion, held, slots):
            return {"gift": fusion["id"], "materials": materials}
    return None
