import pytest

from ocrtext import compact, digits, floor_number, has, normalize


@pytest.mark.parametrize("read, expected", [
    ("Ｌｅａｖｅ　ｔｈｅ　ｓｈｏｐ", "leave the shop"),  # full-width forms and an ideographic space
    ("Ryōshū", "ryoshu"),
    ("  LEAVE   the\tShop ", "leave the shop"),
    ("Straße", "strasse"),
    ("", ""),
    (None, ""),
])
def test_normalize(read, expected):
    assert normalize(read) == expected


@pytest.mark.parametrize("read, phrase, expected", [
    ("Leave the shop?", "Leave the shop", True),
    ("LEAVETHE SHOP?", "Leave the shop", True),  # OCR drops a space and shouts
    ("Ｐｕｒｃｈａｓｅ", "Purchase", True),
    ("E.G.0 Gift", "E.G.O Gift", False),  # O read as 0 in a word is not undone: digits() is for numbers only
    ("EGO Gift", "E.G.O Gift", True),  # the dots dropped
    ("Keyword Refresh", "Keyword Selection", False),
])
def test_has(read, phrase, expected):
    assert has(read, phrase) is expected


def test_has_any_phrase():
    assert has("Claim the rewards?", "without using", "Claim the rewards")
    assert not has("", "x")


def test_compact_keys_names_alike():
    assert compact("Ryōshū's Ｇｉｆｔ") == compact("ryoshus gift") == "ryoshusgift"


@pytest.mark.parametrize("read, expected", [
    ("SELECT FLOOR 3 THEME PACK", 3),
    ("SELECT FLOOR 12 THEME PACK", 12),
    ("Floor 15", 15),
    ("Floor12 [HARD]", 12),  # OCR drops the space
    ("ＦＬＯＯＲ １０", 10),  # full-width forms
    ("Floor 123", None),  # three digits are not a floor
    ("Floor", None),
    ("Select theme pack", None),
    ("", None),
    (None, None),
])
def test_floor_number(read, expected):
    assert floor_number(read) == expected


def test_floor_number_takes_the_label_of_the_caller():
    assert floor_number("Exploring Floar 7", r"fl[a-z]*") == 7
    assert floor_number("Exploring Floar 7") is None


@pytest.mark.parametrize("read, cost", [
    ("3302", 3302),
    ("33O2", 3302),  # OCR reads digits as look-alike letters (#82)
    ("l5S", 155),
    ("2B4", 284),
    ("１２０", 120),  # full-width digits
    ("", None),
    ("Cost", None),  # no digit at all: not a number
])
def test_digits_reads_look_alike_letters_as_digits(read, cost):
    assert digits(read) == cost
