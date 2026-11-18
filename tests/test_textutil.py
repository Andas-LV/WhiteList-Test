from datetime import date

import pytest

from doc_extractor.textutil import (
    bin_checksum_ok,
    compact_key,
    find_bins,
    find_currencies,
    find_dates,
    norm_key,
    number_candidates,
    ocr_fix,
    words_number_candidates,
)


def test_table_row_with_space_separators_yields_column_values() -> None:
    cands = number_candidates("Бумага А4 80г/м2   50   2 100   105 000")
    assert {50, 2100, 105000} <= cands


def test_number_formats() -> None:
    assert 1116.50 in number_candidates("Итого к оплате: 1,116.50 USD")
    assert 10441.38 in number_candidates("НДС: 10 441,38")
    assert 1250.0 in number_candidates("1 250,00")


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Үш жүз қырық мың теңге 00 тиын", 340_000),
        ("Двести сорок семь тысяч пятьсот тенге", 247_500),
        ("Один миллион двести тысяч", 1_200_000),
        ("(пятьсот пять тысяч) тенге", 505_000),
    ],
)
def test_amount_in_words(text: str, value: int) -> None:
    assert value in words_number_candidates(text)


def test_dates_numeric_word_and_kazakh() -> None:
    assert find_dates("Счёт № 1 от 12.11.2026") == {date(2026, 11, 12)}
    assert date(2026, 11, 2) in find_dates("№ 56 от 2 ноября 2026 г.")
    assert date(2026, 10, 9) in find_dates("AKT-09 / 09 қазан 2026 ж.")


def test_ocr_fix_only_touches_numeric_tokens() -> None:
    assert ocr_fix("БСН/БИН: 2l064090Ol80") == "БСН/БИН: 210640900180"
    assert ocr_fix("Cчет oт 2З.1O.2026") == "Cчет oт 23.10.2026"
    assert ocr_fix("ТОО Оазис") == "ТОО Оазис"


def test_find_bins_requires_exactly_12_digits() -> None:
    assert find_bins("БИН 170340021554, тел 87011234567890") == {"170340021554"}


def test_bin_checksum() -> None:
    assert bin_checksum_ok("210640900180")
    assert not bin_checksum_ok("170340021554")


def test_currency_markers() -> None:
    assert find_currencies("450 000 тг") == {"KZT"}
    assert find_currencies("Итого 2 850,00 EUR") == {"EUR"}
    assert find_currencies("Сумма 1000") == set()


def test_norm_key_handles_kazakh_and_lookalikes() -> None:
    assert norm_key("Көкжиек Құрылыс") == norm_key("Кокжиек Курылыс")
    assert compact_key("AKT-09") == compact_key("АКТ 09")
