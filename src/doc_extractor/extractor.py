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
    valid: bool
    attempts: int
    errors: list[str] = field(default_factory=list)
    ungrounded: ExtractionResult | None = None


def _require_all_properties(node: Any) -> None:
    # pydantic не кладёт поля с default в required, и модель такие ключи просто опускает.
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
    if isinstance(obj, dict) and isinstance(obj.get("supplier_bin"), str):
        obj["supplier_bin"] = "".join(obj["supplier_bin"].split()) or None
    return obj


def parse_response(raw: str) -> ExtractionResult:
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
