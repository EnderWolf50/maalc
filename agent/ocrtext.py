"""OCR text normalisation: one way to compare what the game shows with what the code expects (#138).

OCR reads full-width forms, odd case, accents and stray or missing spaces; compare normalised text on both sides.
"""

import re
import unicodedata

LOOKALIKE = str.maketrans("OoDQIl|SsBZz", "000011155822")


def normalize(s):
    """NFKC, case folded, accents dropped (Ryōshū -> ryoshu), runs of spaces as one."""
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s or "").casefold())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def compact(s):
    """normalize(s) without anything but letters and digits: OCR drops and adds spaces and dots."""
    return "".join(c for c in normalize(s) if c.isalnum())


def has(text, *phrases):
    """Whether any of phrases shows in text, both compacted ("Leave the shop" in "LEAVE THESHOP?")."""
    t = compact(text)
    return any(compact(p) in t for p in phrases)


def floor_number(text, label=r"floor"):
    """The floor a title or result line names ("SELECT FLOOR 12 THEME PACK" -> 12); None when it shows no number.

    Two digits: the mirror runs to 15 floors (#383). `label` is the regex before the number, case folded.
    """
    m = re.search(label + r"\s*(\d{1,2})(?!\d)", normalize(text))
    return int(m[1]) if m else None


def digits(text):
    """The number a read of a digits-only ROI stands for, look-alike letters as digits (33O2 -> 3302); None without a digit (#82).

    Only for a ROI that holds nothing but a number: a word's O, l or S would turn into digits.
    """
    if not any(c.isdigit() for c in text):
        return None
    return int("".join(c for c in unicodedata.normalize("NFKC", text).translate(LOOKALIKE) if c.isdigit()))
