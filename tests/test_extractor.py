import json

from doc_extractor.extractor import extract
from doc_extractor.schema import DocType

TEXT = "Счёт на оплату № 5 от 01.11.2026\nИтого: 1 000 тенге"
VALID = json.dumps(
    {
        "doc_type": "invoice",
        "doc_number": "5",
        "doc_date": "2026-11-01",
        "currency": "KZT",
        "total_amount": 1000,
    }
)


class ScriptedLLM:
    """Фейковая модель: отдаёт заранее заданные ответы и запоминает промпты."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        self.prompts.append(user)
        return self.responses.pop(0)


def test_valid_first_answer() -> None:
    outcome = extract(TEXT, ScriptedLLM(VALID))
    assert outcome.valid and outcome.attempts == 1
    assert outcome.result.total_amount == 1000


def test_retry_after_invalid_json_and_bad_field() -> None:
    bad_bin = json.dumps({"doc_type": "invoice", "supplier_bin": "12345"})
    llm = ScriptedLLM("not json at all", bad_bin, VALID)
    outcome = extract(TEXT, llm)
    assert outcome.valid and outcome.attempts == 3
    assert "не является JSON" in outcome.errors[0]
    assert "supplier_bin" in outcome.errors[1]
    # Ошибка валидации передаётся модели в повторном запросе
    assert "supplier_bin" in llm.prompts[2]


def test_fallback_when_model_never_returns_valid_output() -> None:
    llm = ScriptedLLM(*[json.dumps({"doc_type": "receipt"})] * 3)
    outcome = extract(TEXT, llm)
    assert not outcome.valid
    assert outcome.result.doc_type == DocType.UNKNOWN
    assert outcome.result.total_amount is None
    assert "не прошёл валидацию" in outcome.result.warnings[0]


def test_extra_fields_from_model_are_rejected() -> None:
    extra = json.dumps({"doc_type": "invoice", "buyer_name": "X"})
    outcome = extract(TEXT, ScriptedLLM(extra, VALID))
    assert outcome.attempts == 2
    assert "buyer_name" in outcome.errors[0]


def test_bin_with_spaces_is_normalized_before_validation() -> None:
    text = "БИН 210640900180\nСчёт № 1"
    answer = json.dumps({"doc_type": "invoice", "supplier_bin": "2106 4090 0180"})
    outcome = extract(text, ScriptedLLM(answer))
    assert outcome.attempts == 1
    assert outcome.result.supplier_bin == "210640900180"
