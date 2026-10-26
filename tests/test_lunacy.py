"""Lunacy for Enkephalin's price check (#373): pure data in, a verdict out. Every refusal is a case here, since a
wrong "charge" spends Lunacy."""

import pytest

import lunacy


def test_the_price_table_is_the_games_26_to_260():
    assert lunacy.PRICES == tuple(range(26, 261, 26)) and len(lunacy.PRICES) == lunacy.DAILY_MAX == 10


@pytest.mark.parametrize("price, charged, count, expected, verdict, step", [
    (26, 0, 2, None, lunacy.CHARGE, 0),  # the first of the day, two wanted
    (52, 1, 2, 1, lunacy.CHARGE, 1),  # the second, the step after the first Confirm
    (78, 2, 2, 2, lunacy.DONE, 2),  # two charged now: the price after the last Confirm is right, nothing more
    (52, 0, 2, None, lunacy.CHARGE, 1),  # one charged earlier today (by hand, a run before): this run charges two more
    (104, 0, 2, None, lunacy.CHARGE, 3),  # three earlier: the count is this run's, not the day's
    (260, 0, 10, None, lunacy.CHARGE, 9),  # the tenth of the day, the last the game allows
    (130, 1, 1, 4, lunacy.DONE, 4),
    (26, 0, 0, None, lunacy.DONE, 0),  # 0 charges: never a CHARGE, even on the first price
])
def test_the_price_is_on_the_table_and_this_runs_count_decides(price, charged, count, expected, verdict, step):
    assert lunacy.check(price, charged, count, expected)[:2] == (verdict, step)


@pytest.mark.parametrize("price, charged, count, expected", [
    (None, 0, 2, None),  # unread
    (0, 0, 2, None),
    (27, 0, 2, None),  # not in the table
    (25, 0, 2, None),
    (300, 0, 10, None),  # past the table's end
    (26, 1, 2, 1),  # still the first price after one Confirm: the Confirm did nothing, or not yet
    (78, 1, 3, 1),  # jumped past the second
    (52, 1, 2, 0),  # one step after the expected one
    (78, 2, 2, 3),  # the count is met, but the last Confirm did not take: a stop, not a success
])
def test_a_price_off_the_table_or_the_expected_step_stops_without_a_charge(price, charged, count, expected):
    verdict, _, why = lunacy.check(price, charged, count, expected)
    assert verdict == lunacy.STOP and why


@pytest.mark.parametrize("texts, price", [
    (["52"], 52),
    (["Lunacy 52"], 52),
    (["5 2"], None),  # a number split by a space is two numbers: refuse
    (["22 / 136", "2 / 136", "52"], 52),  # the Enkephalin before and after are not the price
    (["22/136 > 2/136", "104"], 104),
    (["26", "52"], None),  # two candidates: refuse
    ([], None),
    (["Recharge Enkephalin?"], None),
    (["Free 0", "26"], None),  # a second number: refuse
])
def test_the_price_is_the_one_number_left_after_the_fractions(texts, price):
    assert lunacy.read_price(texts) == price
