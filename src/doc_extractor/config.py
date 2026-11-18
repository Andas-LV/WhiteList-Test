import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    ollama_api_key: str | None
    llm_model: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL", "qwen3:8b"),
    )
