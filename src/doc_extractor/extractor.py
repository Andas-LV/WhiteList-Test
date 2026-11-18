"""Пайплайн: текст документа -> LLM -> валидация -> пост-проверки."""

from doc_extractor.llm import LLMClient
from doc_extractor.schema import ExtractionResult


def extract(text: str, llm: LLMClient) -> ExtractionResult:
    # TODO: промпт, вызов LLM, валидация pydantic, ретрай при невалидном ответе,
    # детерминированные проверки (BIN есть в тексте, дата есть в тексте и т.п.)
    raise NotImplementedError
