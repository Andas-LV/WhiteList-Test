# doc-extractor

Сервис/CLI: текст документа (счёт, КП, акт) → JSON по фиксированной схеме.
Главная цель — не выдумывать то, чего нет в документе.

> Статус: каркас проекта. Пайплайн и eval в разработке.

## Требования

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (сам создаёт `.venv` и ставит зависимости)

## Установка

```bash
uv sync
cp .env.example .env   # вписать OLLAMA_API_KEY
```

Переменные окружения:

| Переменная       | Пример                | Назначение                          |
|------------------|-----------------------|-------------------------------------|
| `OLLAMA_HOST`    | `https://ollama.com`  | Ollama Cloud или локальный Ollama   |
| `OLLAMA_API_KEY` | `...`                 | ключ Ollama Cloud (локально не нужен) |
| `LLM_MODEL`      | `gpt-oss:120b`        | модель                              |

## Запуск

```bash
uv run doc-extractor data/docs/01_invoice_almaty_trade.txt
```

## Eval

```bash
make eval        # или: uv run python eval.py
```

## Тесты и линтер

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Структура

```
src/doc_extractor/
  schema.py     # pydantic-схема выхода
  llm.py        # клиент LLM (Ollama) + протокол для моков
  extractor.py  # пайплайн извлечения
  cli.py        # CLI
data/docs/      # тексты документов
data/expected/  # эталонные JSON
eval.py         # мини-eval
```

## Принятые решения

TODO

## Что сделано / что нет

TODO
