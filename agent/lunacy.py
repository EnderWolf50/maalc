"""Lunacy for Enkephalin's price check, free of MaaFramework (#373, docs/spec/03-decisions.md section 16).

Charging spends Lunacy, so the one rule is: charge only a price the game's table says. actions.py reads the screen and
taps; everything here is plain data in, a verdict out.
"""

import re

# What check says to do: CHARGE taps Confirm, DONE cancels and ends the task a success, STOP cancels and fails it.
CHARGE, DONE, STOP = "charge", "done", "stop"

# The n-th charge of a day costs PRICES[n] (the game's enkephalinPriceTable, common-data; chance 9999 allows 10 a day, reset
# daily). Free Lunacy is spent first, so the price shown stays the same.
PRICES = (26, 52, 78, 104, 130, 156, 182, 208, 234, 260)
DAILY_MAX = len(PRICES)


def check(price, used, charged, count, expected):
    """What to do with the Use Lunacy tab as read: (verdict, why).

    price: the tab's price; used: its Daily Count, the day's charges so far (n of "n/10"). charged: this run's Confirms;
    count: the charges this run asks for (charge_enkephalin.count), whatever was charged earlier today (#362 D5).
    expected: the Daily Count after this run's last Confirm, None before the first. The price must be the table's at the
    Daily Count, and each Confirm must move the count up by one: anything else is a STOP, the screen is not what the
    task thinks, and nothing is charged. At 10/10 the day is done.
    """
    if used is None or not 0 <= used <= DAILY_MAX:
        return STOP, f"the Daily Count {used} did not read as n/{DAILY_MAX}"
    if expected is not None and used != expected:
        return STOP, f"the Daily Count is {used}/{DAILY_MAX} after the last Confirm, expected {expected}/{DAILY_MAX}"
    if used == DAILY_MAX:
        return DONE, f"{charged} of {count} charged, the day's {DAILY_MAX} charges are done"
    if price != PRICES[used]:
        return STOP, f"the price {price} is not the table's {PRICES[used]} at Daily Count {used}/{DAILY_MAX}"
    if charged >= count:
        return DONE, f"{charged} of {count} charges done"
    return CHARGE, f"price {price}, charge {charged + 1} of {count} (the day's {used + 1})"


def read_price(texts):
    """The price in the OCR strings of its area: the one number left once any "n / cap" reading is dropped; None when
    there is none or more than one (a read that is not sure is no read)."""
    found = re.findall(r"\d+", re.sub(r"\d+\s*/\s*\d+", " ", " ".join(texts)))
    return int(found[0]) if len(found) == 1 else None


def read_count(texts):
    """The Daily Count in the OCR strings under its label: n of the one "n/10"; None when there is none or more."""
    found = re.findall(r"(\d+)\s*/\s*(\d+)", " ".join(texts))
    return int(found[0][0]) if len(found) == 1 and int(found[0][1]) == DAILY_MAX else None
