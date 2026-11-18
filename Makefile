.PHONY: install eval test lint fmt

install:
	uv sync

eval:
	uv run python eval.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .
