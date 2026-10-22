"""Chinese names and starlight-grace text from the Localize Limbus Company (LLC) release, written into the data files.

Usage: uv run --group unpack python tools/llc_text.py [--release 2026101602]
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
RELEASE = "2026101602"
LANG = "LimbusCompany_Data/Lang/LLC_zh-CN/"
URL = "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/{0}/LimbusLocalize_{0}.zip"
LEVELS = {1: "base", 2: "plus", 3: "plus2"}
_S2TWP = opencc.OpenCC("s2twp")
FIXES = {"指標": "指針", "重新整理": "刷新", "映象": "鏡像", "透過階層": "通過階層"}  # s2twp's computing terms where the game means something else


def to_traditional(text):
    text = _S2TWP.convert(text)
    for wrong, right in FIXES.items():
        text = text.replace(wrong, right)
    return text


NOTE_ZH = ("Chinese names: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json by gift id (Simplified Chinese), "
           "converted with OpenCC s2twp, then 指標->指針, 重新整理->刷新, 映象->鏡像, 透過階層->通過階層. Chinese names licensed CC BY-NC-SA 4.0 (see NOTICE.md).")
NOTE_GRACES = ("Chinese names and effect text: the Localize Limbus Company release (Simplified Chinese): MirrorDungeonUI_5 titles and "
               "DungeonStartBuffs_MD7 templates filled with the client's start-buff values, converted with OpenCC s2twp, then 指標->指針, 重新整理->刷新, 映象->鏡像, 透過階層->通過階層. English "
               "names: the game's starlight page. Licensed CC BY-NC-SA 4.0 (see NOTICE.md).")


def release_zip(release):
    path = local_dir("llc") / f"{release}.zip"
    if not path.is_file():
        urllib.request.urlretrieve(URL.format(release), path)
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


def effect_line(template, values, keyword_names):
    ref = values.get("referenceData")
    args = [values.get("value"), values.get("value2")] if not ref else [None, keyword_names[ref["buffKeyword"]], ref["stack"], ref["turn"], ref.get("limit")]
    text = re.sub(r"</?color[^>]*>", "", template)
    return to_traditional(re.sub(r"\{(\d)\}", lambda m: str(args[int(m[1])]), text))


def grace_texts(z, static):
    """buff level -> grace base id -> [effect lines], and base id -> title, in the game's own wording."""
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
            key = e.get("customLocalizeTextId", e["type"]).removesuffix("_TEXT_HIGHLIGHT")
            lines += effect_line(templates[key], e, keywords).splitlines()
        out.setdefault(b["baseId"], {})[LEVELS[b["level"]]] = lines
    return names, out


def credit(release):
    """The provenance keys of a data file whose Chinese text is LLC's (they replace the wiki's source and license keys)."""
    return {"zh_source": "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany", "zh_release": release,
            "license": "CC BY-NC-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}


def retitled(data, release, note):
    """data with the wiki keys dropped and `note`, the credit first; the other keys keep their order."""
    drop = {"note", "source", "source_section", "accessed", "license", "license_url", "zh_source", "zh_release"}
    return {"note": note, **credit(release), **{k: v for k, v in data.items() if k not in drop}}


def dump_search(data):
    """gift_search.json's layout: one line per header key and per gift."""
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "gifts"]
    gifts = ",\n".join("    " + json.dumps(g, ensure_ascii=False) for g in data["gifts"])
    return "{\n" + ",\n".join(head) + ',\n  "gifts": [\n' + gifts + "\n  ]\n}\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=RELEASE)
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
    assert len(graces["graces"]) == len(titles)
    for g, base_id in zip(graces["graces"], sorted(titles)):
        g["zh"], g["effects"] = titles[base_id], effects[base_id]
    GRACES.write_text(json.dumps(retitled(graces, args.release, NOTE_GRACES), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"release {args.release}: {len(names)} gift names, {len(titles)} graces")


if __name__ == "__main__":
    main()
