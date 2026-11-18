"""Мини-eval: прогоняет data/docs/*.txt через пайплайн и сравнивает с data/expected/*.json.

    uv run python eval.py                  # кеш + LLM при промахе
    uv run python eval.py --cache offline  # только сохранённые ответы, без API
    uv run python eval.py --cache refresh  # заново спросить модель

Ответы модели кешируются в data/llm_cache/<модель>/ — поэтому eval воспроизводим без ключа.
"""

import argparse
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
from ollama import ResponseError

from doc_extractor.config import load_settings
from doc_extractor.evaluation import compare, format_report, summarize
from doc_extractor.extractor import extract
from doc_extractor.llm import CachedLLM, LLMCacheMiss, OllamaClient
from doc_extractor.schema import ExtractionResult

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cache", choices=["use", "refresh", "offline"], default="use")
    parser.add_argument("--only", default="", help="подстрока имени документа")
    args = parser.parse_args()

    settings = load_settings()
    inner = None if args.cache == "offline" else OllamaClient(settings)
    llm = CachedLLM(inner, settings.llm_model, DATA / "llm_cache", mode=args.cache)

    docs = [p for p in sorted((DATA / "docs").glob("*.txt")) if args.only in p.stem]
    results, baseline_results = [], []
    print(f"Модель: {settings.llm_model} | документов: {len(docs)} | кеш: {args.cache}\n")

    for doc in docs:
        expected = ExtractionResult.model_validate_json(
            (DATA / "expected" / f"{doc.stem}.json").read_text(encoding="utf-8")
        )
        try:
            outcome = extract(doc.read_text(encoding="utf-8"), llm)
        except LLMCacheMiss as e:
            print(f"{doc.stem}: {e}\nЗапустите без --cache offline, чтобы спросить модель.")
            return 1
        except (ResponseError, httpx.HTTPError) as e:
            print(f"{doc.stem}: ошибка обращения к LLM ({settings.ollama_host}): {e}")
            return 1

        print(f"  {doc.stem}: попыток {outcome.attempts}{'' if outcome.valid else ', FALLBACK'}")
        results.append(
            compare(
                doc.stem, expected, outcome.result, valid=outcome.valid, attempts=outcome.attempts
            )
        )
        raw = outcome.ungrounded or outcome.result
        baseline_results.append(
            compare(doc.stem, expected, raw, valid=outcome.valid, attempts=outcome.attempts)
        )

    summary = summarize(results)
    print()
    print(format_report(summary, results, baseline=summarize(baseline_results)))

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports / f"eval_{settings.llm_model.replace(':', '_')}_{stamp}.json"
    path.write_text(
        json.dumps(
            [dataclasses.asdict(r) for r in results], ensure_ascii=False, indent=2, default=str
        ),
        encoding="utf-8",
    )
    print(f"\nПодробный отчёт: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
