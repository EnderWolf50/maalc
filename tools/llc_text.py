"""Chinese names and starlight-grace text from the Localize Limbus Company (LLC) release, written into the data files.

Usage: uv run --group unpack python tools/llc_text.py [--release <tag>]  (default: the release the data files carry)
Downloads `LimbusLocalize_<release>.zip` from https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases
(cached under `.local/llc/`) and rewrites the `zh` of assets/resource/base/data/gift_search.json and gift_recipes.json
(from `LLC_zh-CN/EGOgift_*.json`, by gift id) and gui/src/graces.json (names: `MirrorDungeonUI_5.json`
`mirror_dungeon_5_buffs_title_<id>`; effects: the `DungeonStartBuffs_MD7.json` templates filled with the effect values of
`.local/unpack/` static data mirrordungeon-start-buffs-08, each line as runs that say which text the game prints yellow). It writes gui/src/gift_effects.json too: the effect text of each
gift of gift_search.json, English from the client's `EN_EGOgift_*.json` and Chinese from `LLC_zh-CN/EGOgift_*.json` (`desc`),
a keyword tag named by the `Bufs*.json` and `BattleKeywords*.json` of each. Simplified to Traditional with OpenCC s2twp. Fails
on a gift or grace the release lacks; gift_recipes.py reuses `gift_names`. LLC is CC BY-NC-SA 4.0 (NOTICE.md).
"""

import argparse
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import opencc

from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
GRACES = REPO / "gui/src/graces.json"
EFFECTS = REPO / "gui/src/gift_effects.json"
LANG = "LimbusCompany_Data/Lang/LLC_zh-CN/"
URL = "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/{0}/LimbusLocalize_{0}.zip"
LEVELS = {1: "base", 2: "plus", 3: "plus2"}
_S2TWP = opencc.OpenCC("s2twp")
FIXES = {"指標": "指針", "重新整理": "刷新", "映象": "鏡像", "透過階層": "通過階層", "松肉": "鬆肉"}  # where s2twp's Taiwan wording is wrong for the game text
YELLOW = "#f8c200"  # the game's yellow in a grace's effect text: what a + or ++ level changed (#733)
BLUE = "#627eff"  # the game's blue of a keyword in a grace's effect text; the GUI shows it plain


def to_traditional(text):
    text = _S2TWP.convert(text)
    for wrong, right in FIXES.items():
        text = text.replace(wrong, right)
    return text


FIXES_NOTE = ", ".join(f"{a}->{b}" for a, b in FIXES.items())
NOTE_ZH = ("Chinese names: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json by gift id (Simplified Chinese), "
           "converted with OpenCC s2twp, then " + FIXES_NOTE + ". Chinese names licensed CC BY-NC-SA 4.0 (see NOTICE.md).")
NOTE_GRACES = ("Chinese names and effect text: the Localize Limbus Company release (Simplified Chinese): MirrorDungeonUI_5 titles and "
               "DungeonStartBuffs_MD7 templates filled with the client's start-buff values, converted with OpenCC s2twp, then " + FIXES_NOTE + ". Each "
               "effect line is a list of runs, `up` on the text the template colours the game's yellow (" + YELLOW + "), what a + or ++ level "
               "changed. English names: the game's starlight page. Licensed CC BY-NC-SA 4.0 (see NOTICE.md).")


def note_effects(client):
    return ("The effect text of each gift of gift_search.json, as the settings GUI shows it. English: the game client "
            f"{client}'s EN_EGOgift_*.json desc; Chinese: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json desc "
            "(Simplified Chinese), by gift id. A [tag] that names a keyword (Bufs*.json, BattleKeywords*.json of each) is replaced "
            "by its name, other bracketed notes stay, markup is dropped. The Chinese converted with OpenCC s2twp, then "
            + FIXES_NOTE + ". Chinese text licensed CC BY-NC-SA 4.0 (see NOTICE.md). Written by tools/llc_text.py.")


def current_release():
    """The release the data files were last written from (what a rerun without --release keeps)."""
    return json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["zh_release"]


def release_zip(release):
    path = local_dir("llc") / f"{release}.zip"
    if not path.is_file():
        part = path.with_suffix(".part")
        urllib.request.urlretrieve(URL.format(release), part)
        part.replace(path)
    return zipfile.ZipFile(path)


def read(z, name):
    return json.loads(z.read(LANG + name).decode("utf-8-sig"))["dataList"]


def files(z, prefix):
    return sorted(n[len(LANG):] for n in z.namelist() if n.startswith(LANG + prefix) and n.endswith(".json"))


def gift_names(z):
    """gift id -> Traditional name, the first file (sorted) that lists the id."""
    names = {}
    for f in files(z, "EGOgift_"):
        for x in read(z, f):
            names.setdefault(x["id"], to_traditional(x["name"]))
    return names


def keyword_names(z):
    """keyword id -> LLC's (Simplified) name, from Bufs*.json and BattleKeywords*.json; the first file (sorted) that names it."""
    names = {}
    for f in files(z, "Bufs") + files(z, "BattleKeywords"):
        for x in read(z, f):
            if x.get("name"):
                names.setdefault(x["id"], x["name"])
    return names


def effect_text(text, names):
    """A gift's effect text as the GUI shows it: markup (`<noparse>`, colours) dropped, a `[tag]` that names a keyword replaced
    by the keyword's name (`[Combustion]` -> Burn); a bracketed note that names none (`[Cannot Stack]`) stays as it is."""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\[([^\]]+)\]", lambda m: names.get(m[1], m[0]), text).strip()


def _en_list(unpack, prefix):
    """id -> record of the client's English localization files `<prefix>*.json`; the first file (sorted) that lists the id."""
    out = {}
    for f in sorted((unpack / "raw/Localize/en").glob(prefix + "*.json")):
        for x in json.loads(f.read_text(encoding="utf-8-sig")).get("dataList", []):
            out.setdefault(x["id"], x)
    return out


def gift_effects(z, unpack, ids):
    """str(gift id) -> {"en", "zh"}: the effect text of each gift, in the order of `ids`."""
    en = _en_list(unpack, "EN_EGOgift_")
    en_names = {k: x["name"] for p in ("EN_Bufs", "EN_BattleKeywords") for k, x in _en_list(unpack, p).items() if x.get("name")}
    zh = {}
    for f in files(z, "EGOgift_"):
        for x in read(z, f):
            zh.setdefault(x["id"], x)
    zh_names = keyword_names(z)
    return {str(i): {"en": effect_text(en[i]["desc"], en_names), "zh": to_traditional(effect_text(zh[i]["desc"], zh_names))} for i in ids}


def dump_effects(data):
    """gift_effects.json's layout: one line per header key and per gift."""
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "effects"]
    rows = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data["effects"].items())
    return "{\n" + ",\n".join(head) + ',\n  "effects": {\n' + rows + "\n  }\n}\n"


def needed(value, template):
    if value is None:
        raise ValueError(f"template needs a value the effect lacks: {template}")
    return value


def effect_lines(template, values, keyword_names):
    """One effect's text as the game prints it: its lines, each a list of runs {"text", "up"}, `up` where the template colours
    the text YELLOW. Colour tags nest, the inner one holding until its own closing tag (TextMeshPro's colour stack); a colour
    other than YELLOW and BLUE is an error, since it might be a new mark. Each run is converted to Traditional on its own,
    and must come out as the line converted whole does."""
    ref = values.get("referenceData")
    args = [values.get("value"), values.get("value2")] if not ref else [None, keyword_names[ref["buffKeyword"]], ref["stack"], ref["turn"], ref.get("limit")]
    lines, colours = [[]], []
    for piece in re.split(r"(</?color[^>]*>)", template):
        if piece == "</color>":
            colours.pop()
        elif piece.startswith("<color="):
            colour = piece[len("<color="):-1].lower()
            if colour not in (YELLOW, BLUE):
                raise ValueError(f"template has a colour that is neither the game's yellow nor its blue: {colour} in {template}")
            colours.append(colour)
        else:
            text = re.sub(r"\{(\d)\}", lambda m: str(needed(args[int(m[1])], template)), piece)
            up = bool(colours) and colours[-1] == YELLOW
            for k, part in enumerate(text.split("\n")):
                if k:
                    lines.append([])
                if not part:
                    continue
                runs = lines[-1]
                if runs and runs[-1]["up"] == up:
                    runs[-1]["text"] += part
                else:
                    runs.append({"text": part, "up": up})
    out = []
    for runs in filter(None, lines):
        converted = [{"text": to_traditional(r["text"]), "up": r["up"]} for r in runs]
        whole = to_traditional("".join(r["text"] for r in runs))
        if "".join(r["text"] for r in converted) != whole:
            raise ValueError(f"converted run by run, the line reads otherwise than whole: {whole}")
        out.append(converted)
    return out


def grace_texts(z, static):
    """(base id -> title, base id -> {base, plus, plus2} -> [effect lines]) of the start-buff graces, in the game's own wording
    and yellow marks (effect_lines)."""
    templates = {x["id"]: x["description"] for x in read(z, "DungeonStartBuffs_MD7.json")}
    keywords = keyword_names(z)
    titles = {x["id"]: x["content"] for x in read(z, "MirrorDungeonUI_5.json")}
    out, names = {}, {}
    for b in static["list"][0]["buffs"]:
        names[b["baseId"]] = to_traditional(titles[b["localizeId"]])
        lines = []
        for e in b["effects"]:
            key = e.get("customLocalizeTextId", e["type"])
            lines += effect_lines(templates[key], e, keywords)
        out.setdefault(b["baseId"], {})[LEVELS[b["level"]]] = lines
    return names, out


def dump_graces(data):
    """graces.json's layout: JSON indented by 2, except that each effect line, a list of runs, stays on one line."""
    def grace(g):
        levels = ",\n".join(f"        {json.dumps(level)}: [\n" + ",\n".join("          " + json.dumps(runs, ensure_ascii=False) for runs in lines)
                            + "\n        ]" for level, lines in g["effects"].items())
        keys = [f"      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in g.items() if k != "effects"]
        return "    {\n" + ",\n".join(keys + ['      "effects": {\n' + levels + "\n      }"]) + "\n    }"
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "graces"]
    return "{\n" + ",\n".join(head) + ',\n  "graces": [\n' + ",\n".join(map(grace, data["graces"])) + "\n  ]\n}\n"


def credit(release):
    """The provenance keys of a data file whose Chinese text is LLC's (they replace the wiki's source and license keys)."""
    return {"zh_source": "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany", "zh_release": release,
            "license": "CC BY-NC-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}


def retitled(data, release, note):
    """data with `note` and the credit (replacing any earlier credit keys) first; the other keys keep their order."""
    drop = {"note", "license", "license_url", "zh_source", "zh_release"}
    return {"note": note, **credit(release), **{k: v for k, v in data.items() if k not in drop}}


def dump_search(data):
    """gift_search.json's layout: one line per header key and per gift."""
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "gifts"]
    gifts = ",\n".join("    " + json.dumps(g, ensure_ascii=False) for g in data["gifts"])
    return "{\n" + ",\n".join(head) + ',\n  "gifts": [\n' + gifts + "\n  ]\n}\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=current_release(), help="the LLC release tag; default: the one the data files carry")
    args = parser.parse_args()
    z = release_zip(args.release)
    names = gift_names(z)
    for name, dump in (("gift_search.json", dump_search), ("gift_recipes.json", lambda d: json.dumps(d, ensure_ascii=False, indent=1) + "\n")):
        data = json.loads((DATA / name).read_text(encoding="utf-8"))
        lists = [data["gifts"]] + ([data["materials"]] if "materials" in data else [])
        missing = [g["id"] for gifts in lists for g in gifts if g["id"] not in names]
        assert not missing, f"{name}: not in the release: {missing}"
        for gifts in lists:
            for g in gifts:
                g["zh"] = names[g["id"]]
        note = re.sub(r"Chinese names: .*?\(see NOTICE\.md\)\.", lambda _: NOTE_ZH, data["note"])
        assert NOTE_ZH in note, name
        (DATA / name).write_text(dump(retitled(data, args.release, note)), encoding="utf-8")
    static = json.loads((local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-start-buffs/"
                         "mirrordungeon-start-buffs-08.json").read_text(encoding="utf-8-sig"))
    titles, effects = grace_texts(z, static)
    graces = json.loads(GRACES.read_text(encoding="utf-8"))
    english = json.loads((local_dir("unpack") / "raw/Localize/en/EN_MirrorDungeonUI_5.json").read_text(encoding="utf-8-sig"))["dataList"]
    base_ids = {x["content"]: i for i in titles for x in english if x["id"] == f"mirror_dungeon_5_buffs_title_{i}"}  # grace en name -> base id
    assert sorted(base_ids) == sorted(g["en"] for g in graces["graces"]), "graces.json and the client disagree on the grace names"
    for g in graces["graces"]:
        g["zh"], g["effects"] = titles[base_ids[g["en"]]], effects[base_ids[g["en"]]]
    GRACES.write_text(dump_graces(retitled(graces, args.release, NOTE_GRACES)), encoding="utf-8")
    from game_data import unpack_client
    unpack = local_dir("unpack")
    ids = [g["id"] for g in json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]]
    effects = gift_effects(z, unpack, ids)
    EFFECTS.write_text(dump_effects({"note": note_effects(unpack_client(unpack)), **credit(args.release), "effects": effects}),
                       encoding="utf-8")
    print(f"release {args.release}: {len(names)} gift names, {len(titles)} graces, {len(effects)} gift effects")


if __name__ == "__main__":
    main()
