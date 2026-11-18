from dataclasses import dataclass
from datetime import date

from doc_extractor.schema import SCALAR_FIELDS, ExtractionResult, LineItem
from doc_extractor.textutil import (
    bin_checksum_ok,
    compact_key,
    contains_number,
    find_bins,
    find_currencies,
    find_dates,
    number_candidates,
    ocr_fix,
    token_coverage,
    words_number_candidates,
)

EXACT, WORDS, FUZZY = 1.0, 0.7, 0.6
NAME_MIN_COVERAGE = 0.6
ITEM_NAME_MIN_COVERAGE = 0.5


@dataclass(frozen=True)
class TextFacts:
    text: str
    ocr_text: str
    numbers: set[float]
    numbers_ocr: set[float]
    numbers_words: set[float]
    dates: set[date]
    dates_ocr: set[date]
    bins: set[str]
    bins_ocr: set[str]
    currencies: set[str]

    @classmethod
    def from_text(cls, text: str) -> "TextFacts":
        ocr_text = ocr_fix(text)
        return cls(
            text=text,
            ocr_text=ocr_text,
            numbers=number_candidates(text),
            numbers_ocr=number_candidates(ocr_text),
            numbers_words=words_number_candidates(text),
            dates=find_dates(text),
            dates_ocr=find_dates(ocr_text),
            bins=find_bins(text),
            bins_ocr=find_bins(ocr_text),
            currencies=find_currencies(text),
        )

    def number_level(self, value: float) -> float | None:
        if contains_number(value, self.numbers):
            return EXACT
        if contains_number(value, self.numbers_words):
            return WORDS
        if contains_number(value, self.numbers_ocr):
            return FUZZY
        return None

    def date_level(self, value: date) -> float | None:
        if value in self.dates:
            return EXACT
        if value in self.dates_ocr:
            return FUZZY
        return None

    def bin_level(self, value: str) -> float | None:
        if value in self.bins:
            return EXACT
        if value in self.bins_ocr:
            return FUZZY
        return None

    def code_level(self, value: str) -> float | None:
        key = compact_key(value)
        if not key:
            return None
        if key in compact_key(self.text):
            return EXACT
        if key in compact_key(self.ocr_text):
            return FUZZY
        return None

    def name_level(self, value: str, min_coverage: float) -> float | None:
        coverage = max(token_coverage(value, self.text), token_coverage(value, self.ocr_text))
        if coverage >= 0.999:
            return EXACT
        if coverage >= min_coverage:
            return FUZZY
        return None


def ground(result: ExtractionResult, text: str) -> ExtractionResult:
    facts = TextFacts.from_text(text)
    data = result.model_copy(deep=True)
    warnings: list[str] = list(data.warnings)
    levels: dict[str, float] = {"doc_type": EXACT}

    def check(field: str, level: float | None, shown: object) -> None:
        if level is None:
            setattr(data, field, None)
            warnings.append(f"{field}: значение «{shown}» не найдено в тексте — обнулено")
        else:
            levels[field] = level

    if data.supplier_bin is not None:
        check("supplier_bin", facts.bin_level(data.supplier_bin), data.supplier_bin)
        if levels.get("supplier_bin") == FUZZY:
            warnings.append(
                f"supplier_bin: восстановлен из OCR-искажённой записи ({data.supplier_bin})"
            )
        if data.supplier_bin is not None and not bin_checksum_ok(data.supplier_bin):
            warnings.append(
                f"supplier_bin: {data.supplier_bin} не проходит проверку контрольной цифры"
            )

    if data.doc_date is not None:
        check("doc_date", facts.date_level(data.doc_date), data.doc_date.isoformat())

    for field in ("total_amount", "vat_amount"):
        value = getattr(data, field)
        if value is not None:
            check(field, facts.number_level(value), value)

    if data.currency is not None:
        check("currency", EXACT if data.currency.value in facts.currencies else None, data.currency)

    if data.doc_number is not None:
        check("doc_number", facts.code_level(data.doc_number), data.doc_number)

    if data.supplier_name is not None:
        check(
            "supplier_name",
            facts.name_level(data.supplier_name, NAME_MIN_COVERAGE),
            data.supplier_name,
        )

    data.line_items = _ground_items(data.line_items, facts, warnings)
    warnings.extend(_consistency_warnings(data, facts))

    data.field_confidence = {
        field: round(min(data.field_confidence.get(field, 1.0), level), 2)
        for field, level in levels.items()
        if field in SCALAR_FIELDS and (field == "doc_type" or getattr(data, field) is not None)
    }
    data.warnings = list(dict.fromkeys(warnings))
    return data


def _ground_items(items: list[LineItem], facts: TextFacts, warnings: list[str]) -> list[LineItem]:
    kept: list[LineItem] = []
    for item in items:
        if facts.name_level(item.name, ITEM_NAME_MIN_COVERAGE) is None:
            warnings.append(f"line_items: позиция «{item.name}» не найдена в тексте — удалена")
            continue
        for attr in ("qty", "price"):
            value = getattr(item, attr)
            if value is not None and facts.number_level(value) is None:
                setattr(item, attr, None)
                warnings.append(
                    f"line_items[{item.name}].{attr}: {value} не найдено в тексте — обнулено"
                )
        kept.append(item)
    return kept


def _consistency_warnings(data: ExtractionResult, facts: TextFacts) -> list[str]:
    out: list[str] = []
    total, vat = data.total_amount, data.vat_amount

    priced = [i for i in data.line_items if i.qty is not None and i.price is not None]
    if total is not None and priced and len(priced) == len(data.line_items):
        lines_sum = sum(i.qty * i.price for i in priced)  # type: ignore[operator]
        plausible = [lines_sum] + ([lines_sum + vat] if vat is not None else [])
        if not any(abs(total - p) < 0.01 for p in plausible):
            out.append(f"Сумма позиций ({lines_sum:g}) не сходится с total_amount ({total:g})")

    big_word_amounts = {v for v in facts.numbers_words if v >= 100}
    if total is not None and big_word_amounts and not contains_number(total, big_word_amounts):
        shown = ", ".join(f"{v:g}" for v in sorted(big_word_amounts))
        out.append(f"Сумма прописью ({shown}) не совпадает с total_amount ({total:g})")
    return out
