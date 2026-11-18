"""CLI: doc-extractor path/to/doc.txt  (или текст через stdin)."""

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
    result = extract(text, OllamaClient(load_settings()))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
