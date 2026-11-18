from doc_extractor.grounding import ground
from doc_extractor.schema import ExtractionResult

INVOICE = """ТОО "Алматы Трейд Компани"
БИН 170340021554
Счёт на оплату № 1245 от 12.11.2026
Бумага А4 80г/м2            50       2 100     105 000
Картридж HP 85A            3     18 500      55 500
Итого:                                       160 500
НДС 16%:                                      25 680
Всего к оплате:                             186 180 тенге
"""

NO_VAT_NO_DATE = """ТОО "Ромашка"
Счёт на оплату № 7
Услуги — 100 000
Итого: 100 000
"""


def _result(**kw) -> ExtractionResult:
    return ExtractionResult.model_validate({"doc_type": "invoice", **kw})


def test_correct_values_are_kept_with_full_confidence() -> None:
    r = ground(
        _result(
            supplier_name='ТОО "Алматы Трейд Компани"',
            supplier_bin="170340021554",
            doc_number="1245",
            doc_date="2026-11-12",
            currency="KZT",
            total_amount=186180,
            vat_amount=25680,
            line_items=[
                {"name": "Бумага А4 80г/м2", "qty": 50, "price": 2100},
                {"name": "Картридж HP 85A", "qty": 3, "price": 18500},
            ],
        ),
        INVOICE,
    )
    assert r.total_amount == 186180
    assert r.field_confidence["total_amount"] == 1.0
    assert not any("не сходится" in w for w in r.warnings)


def test_hallucinated_bin_date_vat_currency_are_nulled() -> None:
    r = ground(
        _result(
            supplier_bin="123456789012",  # «вывела из названия»
            doc_date="2026-11-18",  # «сегодня»
            vat_amount=10714.29,  # «посчитала сама»: 100000 * 12/112
            currency="KZT",  # валюта не указана
            total_amount=100000,
        ),
        NO_VAT_NO_DATE,
    )
    assert r.supplier_bin is None
    assert r.doc_date is None
    assert r.vat_amount is None
    assert r.currency is None
    assert r.total_amount == 100000
    assert len([w for w in r.warnings if "обнулено" in w]) == 4
    assert "supplier_bin" not in r.field_confidence


def test_ocr_bin_is_kept_with_lower_confidence_and_warning() -> None:
    r = ground(_result(supplier_bin="210640900180"), "БСН/БИН: 2l064090Ol80")
    assert r.supplier_bin == "210640900180"
    assert r.field_confidence["supplier_bin"] == 0.6
    assert any("OCR" in w for w in r.warnings)


def test_invented_line_item_is_dropped() -> None:
    r = ground(_result(line_items=[{"name": "Доставка", "qty": 1, "price": 5000}]), NO_VAT_NO_DATE)
    assert r.line_items == []


def test_amount_in_words_grounds_total_and_detects_mismatch() -> None:
    text = "Счёт № 1\nИтого: 550 000\nВсего к оплате: пятьсот пять тысяч тенге"
    r = ground(_result(total_amount=550000), text)
    assert r.total_amount == 550000
    assert any("прописью" in w for w in r.warnings)


def test_lines_sum_mismatch_warns_but_keeps_total() -> None:
    text = "Товар А 2 1 000 2 000\nИтого: 5 000"
    r = ground(
        _result(total_amount=5000, line_items=[{"name": "Товар А", "qty": 2, "price": 1000}]),
        text,
    )
    assert r.total_amount == 5000
    assert any("не сходится" in w for w in r.warnings)
