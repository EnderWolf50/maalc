import yaml

import theme_pack_floors as tpf

TEXT = (
    "# header\n"
    "packs:\n"
    "  The B.E.: {H: [3, 4, 5]}\n"
    "  \"Line 4 - Section #3\": {H: [5]}  # DIFFICULT\n"
    "  # Event packs\n"
    "  S.E.A.: {N: [2], H: [2, 3]}\n"
    "\n"
    "# ids\n"
    "pack_ids:\n"
    "  The B.E.: 3001\n"
    "  \"Line 4 - Section #3\": 1111\n"
    "  S.E.A.: 1102\n"
    "  \"Who Couldn't be Bloodfiends\": 1507\n"
    "\n"
    "event_packs:\n"
    "  - S.E.A.\n"
)


def row(pid, conditions, difficult=False):
    return {"id": pid, "exceptionConditions": conditions, **({"difficulty": "DIFFICULT"} if difficult else {})}


def test_a_rows_floors_are_its_selectable_floors_per_mode_counted_from_1_and_true_where_it_lists_none():
    # dungeonIdx 0-3: NORMAL, HARD, INFINITY, EXTREME; selectableFloors count from 0; no selectableFloors is every floor
    assert tpf.floors(row(1001, [{"dungeonIdx": 0, "selectableFloors": [0, 1]}, {"dungeonIdx": 1, "selectableFloors": [0]}])) == {"N": [1, 2], "H": [1]}
    assert tpf.floors(row(1110, [{"dungeonIdx": 1, "selectableFloors": [4]}, {"dungeonIdx": 2}, {"dungeonIdx": 3}])) == {"H": [5], "I": True, "X": True}
    assert tpf.floors(row(1122, [])) == {}


def test_the_listed_packs_get_their_floors_and_the_missing_ones_are_appended_with_their_ids():
    rows = {
        3001: tpf.Row("The B.E.", tpf.floors(row(3001, [{"dungeonIdx": 1, "selectableFloors": [2, 3, 4]}, {"dungeonIdx": 2}])), False),
        1111: tpf.Row("Line 4 - Section #3", {"H": [5], "I": True, "X": True}, True),
        1102: tpf.Row("S.E.A.", {"N": [2], "H": [2, 3]}, False),
        1507: tpf.Row("Who Couldn't be Bloodfiends", {"X": True}, True),
        1513: tpf.Row("Line 1 : MADNESS", {"X": True}, True),
        1122: tpf.Row("Pilgrimage of Compassion", {}, False),  # on no floor of any mode: left out
    }
    assert tpf.update(TEXT, rows) == (
        "# header\n"
        "packs:\n"
        "  The B.E.: {H: [3, 4, 5], I: true}\n"
        "  \"Line 4 - Section #3\": {H: [5], I: true, X: true}  # DIFFICULT\n"
        "  # Event packs\n"
        "  S.E.A.: {N: [2], H: [2, 3]}\n"
        "  \"Who Couldn't be Bloodfiends\": {X: true}  # DIFFICULT\n"
        "  \"Line 1 : MADNESS\": {X: true}  # DIFFICULT\n"
        "\n"
        "# ids\n"
        "pack_ids:\n"
        "  The B.E.: 3001\n"
        "  \"Line 4 - Section #3\": 1111\n"
        "  S.E.A.: 1102\n"
        "  \"Who Couldn't be Bloodfiends\": 1507\n"
        "  \"Line 1 : MADNESS\": 1513\n"
        "\n"
        "event_packs:\n"
        "  - S.E.A.\n"
    )


def test_a_listed_name_keeps_its_spelling_though_the_data_spells_it_otherwise():
    # 1119's title was read live as "Walpurgis Night: Hatred and Despair"; the data says "Hatred and Despair"
    text = "packs:\n  \"Walpurgis Night: Hatred and Despair\": {N: [3]}\n\npack_ids:\n  \"Walpurgis Night: Hatred and Despair\": 1119\n"
    rows = {1119: tpf.Row("Hatred and Despair", {"N": [3, 4], "H": [3, 4]}, False)}
    assert tpf.update(text, rows) == (
        "packs:\n  \"Walpurgis Night: Hatred and Despair\": {N: [3, 4], H: [3, 4]}\n\npack_ids:\n  \"Walpurgis Night: Hatred and Despair\": 1119\n"
    )


def test_a_name_yaml_would_misread_is_quoted():
    assert [tpf.key(n) for n in ("S.E.A.", "N Corp. New League of Nine Littérateurs", "Faith & Erosion", "Line 1 : MADNESS",
                                 "Hell's Chicken", "Nest, Workshop, and Technology")] == [
        "S.E.A.", "N Corp. New League of Nine Littérateurs", "\"Faith & Erosion\"", "\"Line 1 : MADNESS\"", "\"Hell's Chicken\"",
        "\"Nest, Workshop, and Technology\""]
    for name in ('Say "Hi"', "- Dash", "[Bracket]", "*Star", "Trailing ", "A Midspring Night's Dream 2", "Line 4 - Section #3"):
        assert yaml.safe_load(f"{tpf.key(name)}: 1") == {name: 1}, name
