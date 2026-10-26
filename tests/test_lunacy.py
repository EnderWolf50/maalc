"""Lunacy for Enkephalin's price check (#373): pure data in, a verdict out. Every refusal is a case here, since a
wrong "charge" spends Lunacy."""

import pytest

import lunacy


def test_the_price_table_is_the_games_26_to_260():
    assert lunacy.PRICES == tuple(range(26, 261, 26)) and len(lunacy.PRICES) == lunacy.DAILY_MAX == 10


@pytest.mark.parametrize("price, count, expected, verdict, bought", [
    (26, 2, None, lunacy.CHARGE, 0),  # the first of the day, two wanted
    (52, 2, 1, lunacy.CHARGE, 1),  # the second, as the task's own count says
    (78, 2, 2, lunacy.DONE, 2),  # two are done: nothing more, whatever the price shows
    (52, 2, None, lunacy.CHARGE, 1),  # one bought by hand earlier today: this task buys the second only
    (78, 2, None, lunacy.DONE, 2),  # today's count already met by hand
    (260, 10, None, lunacy.CHARGE, 9),  # the tenth, the last
    (130, 1, None, lunacy.DONE, 4),
    (26, 0, None, lunacy.DONE, 0),  # 0 charges: never a CHARGE, even on the first price
])
def test_the_price_is_the_next_of_the_table_and_the_count_decides(price, count, expected, verdict, bought):
    assert lunacy.check(price, count, expected)[:2] == (verdict, bought)


@pytest.mark.parametrize("price, count, expected", [
    (None, 2, None),  # unread
    (0, 2, None),
    (27, 2, None),  # not in the table
    (25, 2, None),
    (300, 10, None),  # past the table's end
    (26, 2, 1),  # still the first price after one Confirm: the Confirm did nothing, or not yet
    (78, 3, 1),  # jumped past the second
    (52, 2, 0),  # dearer than the first, after nothing was bought
])
def test_a_price_off_the_table_or_the_expected_step_stops_without_a_charge(price, count, expected):
    verdict, _, why = lunacy.check(price, count, expected)
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
