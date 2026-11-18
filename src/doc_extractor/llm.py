"""Тонкая обёртка над LLM-клиентом. Протокол позволяет подменить реальный вызов моком."""

from typing import Protocol

from ollama import Client

from doc_extractor.config import Settings


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        """Вернуть сырой текст ответа модели (ожидается JSON)."""
        ...


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        headers = (
            {"Authorization": f"Bearer {settings.ollama_api_key}"}
            if settings.ollama_api_key
            else None
        )
        self._client = Client(host=settings.ollama_host, headers=headers)
        self._model = settings.llm_model

    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format=json_schema,
            options={"temperature": 0},
        )
        return response.message.content or ""
