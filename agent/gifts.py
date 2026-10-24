"""What a gift list (docs/spec/04-settings.md section 13) makes of a gift: its state, what locks it, the buy queue, the fusion to make.

Pure data in, data out, no MaaFramework (the shop, the other actions and the GUI's model.ts use the same rules; both
sides run tests/gift_list_cases.json). A gift list here is a cleaned one (settings.clean_gift_list): `order`, `want`, `keep`,
`gorder`. `tables` is {"buyable": gift_search.json's gifts, "fusions": gift_recipes.json's gifts}, the game files' when None.
`run_packs` are the ids of the theme packs the run took, None when unknown (the agent restarted mid-run): then a pack-specific
fusion locks its materials all the same.
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


def lockers(gift_list, gift_id, run_packs=None, tables=None):
    """The wanted fusions that lock a drop gift, in data-file order: it is a material of any of their recipes, or of
    any group. A pack-specific fusion (data `specific`) only when run_packs and its `packs` share one, or run_packs is None."""
    if state(gift_list, gift_id) != "drop":
        return []
    return [f["id"] for f in (tables or _game_tables())["fusions"]
            if state(gift_list, f["id"]) == "want" and gift_id in _materials(f)
            and (not f.get("specific") or run_packs is None or set(f.get("packs", [])) & set(run_packs))]


def effective(gift_list, gift_id, run_packs=None, tables=None):
    """"want", "keep" (kept, or a drop gift something locks) or "drop"."""
    own = state(gift_list, gift_id)
    return "keep" if own == "drop" and lockers(gift_list, gift_id, run_packs, tables) else own


def queue(gift_list, tables=None):
    """The ids to buy, first first: per keyword in `order`, its `gorder` gifts the list wants and the shop sells."""
    buyable = {g["id"] for g in (tables or _game_tables())["buyable"]}
    return [i for k in gift_list["order"] for i in gift_list["gorder"][k] if i in buyable and state(gift_list, i) == "want"]


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


def recipe_fusion(gift_list, owned_ids, tables=None, slots=None):
    """{"gift": id, "materials": [ids]} for the first wanted fusion in list order whose materials `owned_ids` (a list,
    repeats count) hold, else None. List order = the keyword's place in `order` (`queue`'s), then data-file order: a fusion
    is in no `gorder` (that holds the shop's gifts). A pack-specific fusion is made whatever the run packs. `slots`: the fuse page's material slots; a recipe needing more is passed over (the next
    wanted one is tried)."""
    owned = Counter(owned_ids)
    place = {k: n for n, k in enumerate(gift_list["order"])}
    for fusion in sorted((tables or _game_tables())["fusions"], key=lambda f: place.get(f["keyword"], len(place))):
        if state(gift_list, fusion["id"]) == "want" and (materials := _pick(fusion, owned, slots)):
            return {"gift": fusion["id"], "materials": materials}
    return None
