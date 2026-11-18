"""LLM-клиенты. Протокол LLMClient позволяет подменить реальный вызов кешем или фейком в тестах."""

import hashlib
import json
from pathlib import Path
from typing import Literal, Protocol

from ollama import Client

from doc_extractor.config import Settings


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        """Вернуть сырой текст ответа модели (ожидается JSON)."""
        ...


class LLMCacheMiss(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        headers = (
            {"Authorization": f"Bearer {settings.ollama_api_key}"}
            if settings.ollama_api_key
            else None
        )
        self._client = Client(host=settings.ollama_host, headers=headers, timeout=180)
        self.model = settings.llm_model

    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format=json_schema,  # structured outputs: декодирование ограничено схемой
            options={"temperature": 0},
        )
        return response.message.content or ""


CacheMode = Literal["use", "refresh", "offline"]


class CachedLLM:
    """Кеш ответов на диске: ключ = sha256(модель, промпты, схема).

    use     — брать из кеша, при промахе звать модель и сохранить;
    refresh — всегда звать модель и перезаписать кеш;
    offline — только кеш, промах = ошибка (eval без ключа API).
    """

    def __init__(
        self, inner: LLMClient | None, model: str, cache_dir: Path, mode: CacheMode = "use"
    ) -> None:
        self._inner = inner
        self._model = model
        self._dir = cache_dir / model.replace(":", "_").replace("/", "_")
        self._mode = mode

    def _key(self, system: str, user: str, json_schema: dict) -> str:
        payload = json.dumps([self._model, system, user, json_schema], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def complete_json(self, system: str, user: str, json_schema: dict) -> str:
        path = self._dir / f"{self._key(system, user, json_schema)}.json"
        if self._mode != "refresh" and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        if self._mode == "offline" or self._inner is None:
            raise LLMCacheMiss(f"Нет ответа в кеше: {path}")
        response = self._inner.complete_json(system, user, json_schema)
        self._dir.mkdir(parents=True, exist_ok=True)
        record = {"model": self._model, "user_prompt_head": user[:200], "response": response}
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return response
