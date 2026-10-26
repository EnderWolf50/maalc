"""Lunacy for Enkephalin's price check (#373): pure data in, a verdict out. Every refusal is a case here, since a
wrong "charge" spends Lunacy."""

import pytest

import lunacy


def test_the_price_table_is_the_games_26_to_260():
    assert lunacy.PRICES == tuple(range(26, 261, 26)) and len(lunacy.PRICES) == lunacy.DAILY_MAX == 10


@pytest.mark.parametrize("price, used, charged, count, expected, verdict", [
    (26, 0, 0, 2, None, lunacy.CHARGE),  # the first of the day, two wanted
    (52, 1, 1, 2, 1, lunacy.CHARGE),  # the second: Daily Count went up by one after the Confirm
    (78, 2, 2, 2, 2, lunacy.DONE),  # two charged now, the last Confirm counted: nothing more
    (104, 3, 0, 2, None, lunacy.CHARGE),  # live 2026-10-27: 3/10 and 104; three earlier today, this run charges two more
    (260, 9, 0, 10, None, lunacy.CHARGE),  # the tenth of the day, the last the game allows
    (None, 10, 0, 2, None, lunacy.DONE),  # 10/10: the day's charges are done, whatever the price shows
    (260, 10, 1, 2, 10, lunacy.DONE),  # the tenth was this run's: its Confirm counted, the day is done
    (26, 0, 0, 0, None, lunacy.DONE),  # 0 charges: never a CHARGE, even on the first price
])
def test_the_price_is_the_tables_at_the_daily_count_and_this_runs_count_decides(price, used, charged, count, expected, verdict):
    assert lunacy.check(price, used, charged, count, expected)[0] == verdict


@pytest.mark.parametrize("price, used, charged, count, expected", [
    (None, 0, 0, 2, None),  # the price unread
    (26, None, 0, 2, None),  # the Daily Count unread
    (26, 11, 0, 2, None),  # past the day's 10
    (27, 0, 0, 2, None),  # not the table's price
    (52, 0, 0, 2, None),  # the table's, but not at this Daily Count
    (104, 2, 0, 2, None),
    (300, 9, 0, 10, None),  # past the table's end
    (26, 0, 1, 2, 1),  # still 0/10 after one Confirm: the Confirm did nothing, or not yet
    (78, 2, 1, 3, 1),  # jumped past the second
    (78, 2, 2, 2, 3),  # the count is met, but the last Confirm did not count: a stop, not a success
])
def test_a_price_or_count_off_the_table_or_the_expected_step_stops_without_a_charge(price, used, charged, count, expected):
    verdict, why = lunacy.check(price, used, charged, count, expected)
    assert verdict == lunacy.STOP and why


@pytest.mark.parametrize("texts, used", [
    (["3/10"], 3),  # live 2026-10-27
    (["3 / 10"], 3),
    (["10/10"], 10),
    (["0/10"], 0),
    (["3/1O"], None),  # a cap that is not 10: refuse
    (["3/10", "4/10"], None),  # two: refuse
    ([], None),
])
def test_the_daily_count_is_the_one_n_over_10(texts, used):
    assert lunacy.read_count(texts) == used


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
