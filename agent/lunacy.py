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


def check(price, charged, count, expected):
    """What to do with the price the Recharge prompt shows: (verdict, its step in the table, why).

    charged: this run's Confirms so far; count: the charges this run asks for (charge_enkephalin.count), whatever was
    charged earlier today. expected: the step the price must be at after this run's last Confirm, None before the first.
    Any price the table lacks, or that is not the step after the last Confirm, is a STOP: the screen is not what the
    task thinks, and nothing is charged. The table's last step is the day's last charge: the caller ends after it.
    """
    if price not in PRICES:
        return STOP, None, f"the price {price} is not in the game's table {PRICES}"
    step = PRICES.index(price)
    if expected is not None and step != expected:
        return STOP, step, f"the price {price} is charge {step + 1} of the day, expected charge {expected + 1}"
    if charged >= count:
        return DONE, step, f"{charged} of {count} charges done"
    return CHARGE, step, f"price {price}, charge {charged + 1} of {count} (the day's {step + 1})"


def read_price(texts):
    """The price in the OCR strings of the prompt's area: the one number left once the "n / cap" Enkephalin readings are
    dropped; None when there is none or more than one (a read that is not sure is no read)."""
    found = re.findall(r"\d+", re.sub(r"\d+\s*/\s*\d+", " ", " ".join(texts)))
    return int(found[0]) if len(found) == 1 else None
