from pathlib import Path

from doc_extractor.evaluation import classify, compare, match_items, summarize
from doc_extractor.schema import ExtractionResult, LineItem

DATA = Path(__file__).resolve().parents[1] / "data" / "expected"


def _r(**kw) -> ExtractionResult:
    return ExtractionResult.model_validate({"doc_type": "invoice", **kw})


def test_hallucination_and_miss_are_counted_separately() -> None:
    expected = _r(supplier_bin=None, total_amount=1000)
    predicted = _r(supplier_bin="123456789012", total_amount=None)
    s = summarize([compare("d", expected, predicted)])
    assert s.per_field["supplier_bin"].hallucinated == 1
    assert s.per_field["total_amount"].missed == 1
    assert s.hallucinations == 1 and s.misses == 1 and s.wrong == 0


def test_wrong_value_is_neither_hallucination_nor_miss() -> None:
    assert classify("total_amount", 1000, 1001) == "wrong"
    assert classify("total_amount", 1000, 1000.001) == "correct"
    assert classify("doc_date", None, None) == "correct"


def test_name_and_number_comparison_is_normalized() -> None:
    assert classify("supplier_name", 'ТОО "Кокжиек Курылыс"', "ЖШС «Көкжиек Құрылыс»") == "correct"
    assert classify("doc_number", "AKT-09", "АКТ-09") == "correct"


def test_item_matching_reports_extra_and_missing() -> None:
    expected = [LineItem(name="Кофемашина", qty=2, price=1250)]
    predicted = [
        LineItem(name="Кофе машинасы / Кофемашина", qty=2, price=1250),
        LineItem(name="Доставка", qty=1, price=100),
    ]
    pairs, missing, extra = match_items(expected, predicted)
    assert len(pairs) == 1 and not missing
    assert [i.name for i in extra] == ["Доставка"]


def test_references_against_themselves_score_perfectly() -> None:
    results = []
    for path in sorted(DATA.glob("*.json")):
        ref = ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))
        results.append(compare(path.stem, ref, ref))
    s = summarize(results)
    assert s.hallucinations == s.misses == s.wrong == 0
    assert s.items_correct == s.items_expected
    assert all(st.accuracy == 1.0 for st in s.per_field.values() if st.total)
