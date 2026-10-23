"""Chinese names and starlight-grace text from the Localize Limbus Company (LLC) release, written into the data files.

Usage: uv run --group unpack python tools/llc_text.py [--release <tag>]  (default: the release the data files carry)
Downloads `LimbusLocalize_<release>.zip` from https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases
(cached under `.local/llc/`) and rewrites the `zh` of assets/resource/base/data/gift_search.json and gift_recipes.json
(from `LLC_zh-CN/EGOgift_*.json`, by gift id) and gui/src/graces.json (names: `MirrorDungeonUI_5.json`
`mirror_dungeon_5_buffs_title_<id>`; effects: the `DungeonStartBuffs_MD7.json` templates filled with the effect values of
`.local/unpack/` static data mirrordungeon-start-buffs-08). Simplified to Traditional with OpenCC s2twp. Fails on a gift
or grace the release lacks; gift_recipes.py reuses `gift_names`. LLC is CC BY-NC-SA 4.0 (NOTICE.md).
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
LANG = "LimbusCompany_Data/Lang/LLC_zh-CN/"
URL = "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/{0}/LimbusLocalize_{0}.zip"
LEVELS = {1: "base", 2: "plus", 3: "plus2"}
_S2TWP = opencc.OpenCC("s2twp")
FIXES = {"指標": "指針", "重新整理": "刷新", "映象": "鏡像", "透過階層": "通過階層", "松肉": "鬆肉"}  # where s2twp's Taiwan wording is wrong for the game text


def to_traditional(text):
    text = _S2TWP.convert(text)
    for wrong, right in FIXES.items():
        text = text.replace(wrong, right)
    return text


FIXES_NOTE = ", ".join(f"{a}->{b}" for a, b in FIXES.items())
NOTE_ZH = ("Chinese names: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json by gift id (Simplified Chinese), "
           "converted with OpenCC s2twp, then " + FIXES_NOTE + ". Chinese names licensed CC BY-NC-SA 4.0 (see NOTICE.md).")
NOTE_GRACES = ("Chinese names and effect text: the Localize Limbus Company release (Simplified Chinese): MirrorDungeonUI_5 titles and "
               "DungeonStartBuffs_MD7 templates filled with the client's start-buff values, converted with OpenCC s2twp, then " + FIXES_NOTE + ". English "
               "names: the game's starlight page. Licensed CC BY-NC-SA 4.0 (see NOTICE.md).")


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


def needed(value, template):
    if value is None:
        raise ValueError(f"template needs a value the effect lacks: {template}")
    return value


def effect_line(template, values, keyword_names):
    ref = values.get("referenceData")
    args = [values.get("value"), values.get("value2")] if not ref else [None, keyword_names[ref["buffKeyword"]], ref["stack"], ref["turn"], ref.get("limit")]
    text = re.sub(r"</?color[^>]*>", "", template)
    return to_traditional(re.sub(r"\{(\d)\}", lambda m: str(needed(args[int(m[1])], template)), text))


def grace_texts(z, static):
    """(base id -> title, base id -> {base, plus, plus2} -> [effect lines]) of the start-buff graces, in the game's own wording."""
    templates = {x["id"]: x["description"] for x in read(z, "DungeonStartBuffs_MD7.json")}
    keywords = {}
    for f in files(z, "Bufs") + files(z, "BattleKeywords"):
        for x in read(z, f):
            if x.get("name"):
                keywords.setdefault(x["id"], x["name"])
    titles = {x["id"]: x["content"] for x in read(z, "MirrorDungeonUI_5.json")}
    out, names = {}, {}
    for b in static["list"][0]["buffs"]:
        names[b["baseId"]] = to_traditional(titles[b["localizeId"]])
        lines = []
        for e in b["effects"]:
            key = e.get("customLocalizeTextId", e["type"])
            lines += effect_line(templates[key], e, keywords).splitlines()
        out.setdefault(b["baseId"], {})[LEVELS[b["level"]]] = lines
    return names, out


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
    GRACES.write_text(json.dumps(retitled(graces, args.release, NOTE_GRACES), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"release {args.release}: {len(names)} gift names, {len(titles)} graces")


if __name__ == "__main__":
    main()
