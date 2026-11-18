"""Сравнение предсказаний с эталоном: точность по полям, галлюцинации и пропуски раздельно.

Для каждого поля исход одного из четырёх видов:
  correct      — совпало (в т.ч. оба null);
  hallucinated — в эталоне null, а модель заполнила (выдумала);
  missed       — в эталоне есть значение, а модель вернула null (пропустила);
  wrong        — оба заполнены, но значения разные.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from doc_extractor.schema import SCALAR_FIELDS, ExtractionResult, LineItem
from doc_extractor.textutil import compact_key, name_tokens

Status = Literal["correct", "hallucinated", "missed", "wrong"]
NUMERIC = {"total_amount", "vat_amount", "qty", "price"}
ITEM_MATCH_THRESHOLD = 0.5


@dataclass
class FieldStats:
    correct: int = 0
    hallucinated: int = 0
    missed: int = 0
    wrong: int = 0

    @property
    def total(self) -> int:
        return self.correct + self.hallucinated + self.missed + self.wrong

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def add(self, status: Status) -> None:
        setattr(self, status, getattr(self, status) + 1)


def values_equal(name: str, expected: Any, predicted: Any) -> bool:
    if name in NUMERIC:
        return abs(float(expected) - float(predicted)) < 0.01
    if name == "supplier_name":
        return name_tokens(expected) == name_tokens(predicted)
    if name == "doc_number":
        return compact_key(str(expected)) == compact_key(str(predicted))
    return str(expected) == str(predicted)


def classify(name: str, expected: Any, predicted: Any) -> Status:
    if expected is None and predicted is None:
        return "correct"
    if expected is None:
        return "hallucinated"
    if predicted is None:
        return "missed"
    return "correct" if values_equal(name, expected, predicted) else "wrong"


def _overlap(a: str, b: str) -> float:
    ta, tb = set(name_tokens(a)), set(name_tokens(b))
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


def match_items(
    expected: list[LineItem], predicted: list[LineItem]
) -> tuple[list[tuple[LineItem, LineItem]], list[LineItem], list[LineItem]]:
    """Жадное сопоставление позиций по названию. Возвращает (пары, пропущенные, лишние)."""
    scored = sorted(
        (
            (_overlap(e.name, p.name), i, j)
            for i, e in enumerate(expected)
            for j, p in enumerate(predicted)
        ),
        reverse=True,
    )
    used_e: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[LineItem, LineItem]] = []
    for score, i, j in scored:
        if score < ITEM_MATCH_THRESHOLD or i in used_e or j in used_p:
            continue
        used_e.add(i)
        used_p.add(j)
        pairs.append((expected[i], predicted[j]))
    missing = [e for i, e in enumerate(expected) if i not in used_e]
    extra = [p for j, p in enumerate(predicted) if j not in used_p]
    return pairs, missing, extra


@dataclass
class DocResult:
    name: str
    valid: bool
    attempts: int
    fields: dict[str, tuple[Status, Any, Any]]  # поле -> (статус, эталон, предсказание)
    items_expected: int
    items_predicted: int
    items_correct: int
    items_missing: list[str]
    items_extra: list[str]
    expected_warnings: int
    predicted_warnings: list[str]


def compare(
    name: str,
    expected: ExtractionResult,
    predicted: ExtractionResult,
    *,
    valid: bool = True,
    attempts: int = 1,
) -> DocResult:
    fields: dict[str, tuple[Status, Any, Any]] = {}
    for f in SCALAR_FIELDS:
        e, p = getattr(expected, f), getattr(predicted, f)
        fields[f] = (classify(f, e, p), e, p)

    pairs, missing, extra = match_items(expected.line_items, predicted.line_items)
    items_correct = 0
    for k, (e_item, p_item) in enumerate(pairs):
        ok = True
        for attr in ("qty", "price"):
            e, p = getattr(e_item, attr), getattr(p_item, attr)
            status = classify(attr, e, p)
            fields[f"line_items.{attr}#{k}"] = (status, e, p)
            ok &= status == "correct"
        items_correct += ok

    return DocResult(
        name=name,
        valid=valid,
        attempts=attempts,
        fields=fields,
        items_expected=len(expected.line_items),
        items_predicted=len(predicted.line_items),
        items_correct=items_correct,
        items_missing=[i.name for i in missing],
        items_extra=[i.name for i in extra],
        expected_warnings=len(expected.warnings),
        predicted_warnings=predicted.warnings,
    )


@dataclass
class Summary:
    per_field: dict[str, FieldStats] = field(default_factory=dict)
    docs: int = 0
    fallbacks: int = 0
    retries: int = 0
    items_expected: int = 0
    items_predicted: int = 0
    items_correct: int = 0
    items_missing: int = 0
    items_extra: int = 0
    docs_needing_warning: int = 0
    docs_warned_correctly: int = 0
    docs_false_alarm: int = 0

    @property
    def hallucinations(self) -> int:
        return sum(s.hallucinated for s in self.per_field.values())

    @property
    def misses(self) -> int:
        return sum(s.missed for s in self.per_field.values())

    @property
    def wrong(self) -> int:
        return sum(s.wrong for s in self.per_field.values())


def summarize(results: list[DocResult]) -> Summary:
    s = Summary()
    for f in [*SCALAR_FIELDS, "line_items.qty", "line_items.price"]:
        s.per_field[f] = FieldStats()
    for r in results:
        s.docs += 1
        s.fallbacks += not r.valid
        s.retries += r.attempts - 1
        for key, (status, _, _) in r.fields.items():
            s.per_field[key.split("#")[0]].add(status)
        s.items_expected += r.items_expected
        s.items_predicted += r.items_predicted
        s.items_correct += r.items_correct
        s.items_missing += len(r.items_missing)
        s.items_extra += len(r.items_extra)
        if r.expected_warnings:
            s.docs_needing_warning += 1
            s.docs_warned_correctly += bool(r.predicted_warnings)
        elif r.predicted_warnings:
            s.docs_false_alarm += 1
    return s


def format_report(
    summary: Summary, results: list[DocResult], baseline: Summary | None = None
) -> str:
    out: list[str] = []
    out.append(
        f"{'Поле':<20}{'Точность':>10}{'Верно':>8}{'Галлюц.':>9}{'Пропуск':>9}{'Неверно':>9}"
    )
    out.append("-" * 65)
    for name, st in summary.per_field.items():
        out.append(
            f"{name:<20}{st.accuracy:>9.0%} {st.correct:>4}/{st.total:<3}"
            f"{st.hallucinated:>9}{st.missed:>9}{st.wrong:>9}"
        )
    out.append("-" * 65)
    out.append(f"ГАЛЛЮЦИНАЦИИ (заполнено, а в эталоне null): {summary.hallucinations}")
    out.append(f"ПРОПУСКИ     (null, а в эталоне значение):  {summary.misses}")
    out.append(f"Неверные значения (оба заполнены):          {summary.wrong}")
    if baseline is not None:
        out.append(
            f"  без grounding было: галлюцинаций {baseline.hallucinations}, "
            f"пропусков {baseline.misses}, неверных {baseline.wrong}"
        )
    out.append("")
    out.append(
        f"Позиции: эталон {summary.items_expected}, найдено {summary.items_predicted}, "
        f"полностью верно {summary.items_correct}, "
        f"лишних (выдуманных) {summary.items_extra}, пропущено {summary.items_missing}"
    )
    out.append(
        f"Предупреждения: противоречие отмечено в {summary.docs_warned_correctly}"
        f"/{summary.docs_needing_warning} документов, где оно есть; "
        f"лишние предупреждения в {summary.docs_false_alarm} документах"
    )
    out.append(
        f"Валидация: документов {summary.docs}, повторных запросов {summary.retries}, "
        f"fallback (ответ так и не прошёл схему) {summary.fallbacks}"
    )

    out.append("\nРасхождения по документам:")
    for r in results:
        problems = [
            f"    {k.split('#')[0]}: {status} (эталон={e!s}, ответ={p!s})"
            for k, (status, e, p) in r.fields.items()
            if status != "correct"
        ]
        problems += [f"    позиция пропущена: {n}" for n in r.items_missing]
        problems += [f"    лишняя позиция: {n}" for n in r.items_extra]
        flag = "" if r.valid else "  [FALLBACK]"
        out.append(f"  {r.name}{flag}: {'OK' if not problems else ''}")
        out.extend(problems)
    return "\n".join(out)
