"""CLI: doc-extractor path/to/doc.txt  (или текст через stdin).

Код выхода: 0 — успешно, 2 — ответ LLM не прошёл валидацию (выведен fallback-JSON).
"""

import argparse
import sys
from pathlib import Path

from doc_extractor.config import load_settings
from doc_extractor.extractor import extract
from doc_extractor.llm import OllamaClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Извлечь JSON из текста документа")
    parser.add_argument("path", nargs="?", type=Path, help="Файл с текстом (по умолчанию stdin)")
    args = parser.parse_args()

    text = args.path.read_text(encoding="utf-8") if args.path else sys.stdin.read()
    outcome = extract(text, OllamaClient(load_settings()))

    for i, err in enumerate(outcome.errors, 1):
        print(f"[попытка {i}] ответ отклонён валидацией:\n{err}", file=sys.stderr)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(outcome.result.model_dump_json(indent=2))
    sys.exit(0 if outcome.valid else 2)


if __name__ == "__main__":
    main()
