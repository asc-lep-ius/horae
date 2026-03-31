.PHONY: install pre-commit-install lint format test typecheck run

install:
	uv sync

pre-commit-install:
	uv run pre-commit install

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

test:
	uv run pytest

typecheck:
	uv run pyright

run:
	uv run uvicorn horae.app:app --reload --host 0.0.0.0 --port 8000
