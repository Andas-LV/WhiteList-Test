"""Пайплайн: текст -> LLM -> JSON-парсинг -> pydantic -> (ретрай с ошибкой) -> grounding.

Если после MAX_ATTEMPTS ответ так и не прошёл валидацию, система НЕ пытается
«дочинить» его эвристиками, а возвращает безопасный результат: doc_type=unknown,
все поля null, причина в warnings, valid=False. Наружу никогда не уходит JSON,
не соответствующий схеме.
"""

import json
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from pydantic import ValidationError

from doc_extractor.grounding import ground
from doc_extractor.llm import LLMClient
from doc_extractor.prompt import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from doc_extractor.schema import DocType, ExtractionResult

MAX_ATTEMPTS = 3


@dataclass
class ExtractionOutcome:
    result: ExtractionResult
    valid: bool  # False — сработал fallback, ответ LLM так и не прошёл валидацию
    attempts: int
    errors: list[str] = field(default_factory=list)  # ошибки валидации по попыткам
    ungrounded: ExtractionResult | None = None  # ответ модели до grounding (для eval)


def _require_all_properties(node: Any) -> None:
    """Сделать все свойства объектов обязательными (рекурсивно, включая $defs).

    pydantic не включает поля со значением по умолчанию в `required`, и при constrained
    decoding модель такие ключи просто не выводит (в первом прогоне qwen3:8b пропускала
    currency в 8 из 10 документов). Nullable-поля остаются nullable: модель обязана явно
    написать null, а не молча опустить ключ.
    """
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
        for value in node.values():
            _require_all_properties(value)
    elif isinstance(node, list):
        for value in node:
            _require_all_properties(value)


@cache
def output_json_schema() -> dict[str, Any]:
    schema = ExtractionResult.model_json_schema()
    _require_all_properties(schema)
    return schema


def _coerce(obj: Any) -> Any:
    """Безопасные косметические правки до валидации (не меняют смысл значения)."""
    if isinstance(obj, dict) and isinstance(obj.get("supplier_bin"), str):
        obj["supplier_bin"] = "".join(obj["supplier_bin"].split()) or None
    return obj


def parse_response(raw: str) -> ExtractionResult:
    """Строгий разбор ответа модели. Бросает ValueError с понятным текстом ошибки."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Ответ не является JSON: {e}") from e
    try:
        return ExtractionResult.model_validate(_coerce(obj))
    except ValidationError as e:
        lines = [
            f"- {'.'.join(map(str, err['loc'])) or '<root>'}: {err['msg']}"
            for err in e.errors()[:15]
        ]
        raise ValueError("\n".join(lines)) from e


def fallback_result(attempts: int, last_error: str) -> ExtractionResult:
    return ExtractionResult(
        doc_type=DocType.UNKNOWN,
        warnings=[
            f"Ответ LLM не прошёл валидацию схемы после {attempts} попыток; "
            f"поля не заполнены. Последняя ошибка: {last_error}"
        ],
    )


def extract(text: str, llm: LLMClient, max_attempts: int = MAX_ATTEMPTS) -> ExtractionOutcome:
    schema = output_json_schema()
    user_prompt = build_user_prompt(text)
    errors: list[str] = []

    for attempt in range(1, max_attempts + 1):
        raw = llm.complete_json(SYSTEM_PROMPT, user_prompt, schema)
        try:
            parsed = parse_response(raw)
        except ValueError as e:
            errors.append(str(e))
            user_prompt = build_repair_prompt(text, raw, str(e))
            continue
        return ExtractionOutcome(
            result=ground(parsed, text),
            valid=True,
            attempts=attempt,
            errors=errors,
            ungrounded=parsed,
        )

    return ExtractionOutcome(
        result=fallback_result(max_attempts, errors[-1]),
        valid=False,
        attempts=max_attempts,
        errors=errors,
    )
