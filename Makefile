SHELL := /bin/sh
export UV_CACHE_DIR ?= $(CURDIR)/.state/uv-cache
.PHONY: setup demo test check eval-fixtures eval-live smoke-live docker-smoke

setup:
	python3 scripts/check_runtime.py
	uv sync --frozen --python 3.12
	npm ci --ignore-scripts
	npx --no-install playwright install chromium

demo:
	uv run --frozen python -m repair_agent.cli serve

test:
	uv run --frozen pytest -q
	uv run --frozen python scripts/ui_journey.py

check:
	uv run --frozen ruff format --check src tests scripts
	uv run --frozen ruff check src tests scripts
	uv run --frozen mypy src
	uv run --frozen djlint src/repair_agent/templates --profile=jinja --check
	npm run check
	uv run --frozen python scripts/forbidden_characters.py

eval-fixtures:
	uv run --frozen python -m repair_agent.cli eval-fixtures

eval-live:
	uv run --frozen python -m repair_agent.cli eval-live

smoke-live:
	uv run --frozen python -m repair_agent.cli smoke-live --budget-usd .30

docker-smoke:
	docker build -t accessibility-repair-agent:local .
	docker run --rm accessibility-repair-agent:local uv run --frozen pytest -q
	docker run --rm accessibility-repair-agent:local uv run --frozen python scripts/ui_journey.py
