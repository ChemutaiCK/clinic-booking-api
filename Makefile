.PHONY: help install run test test-cov lint format migrate migrate-generate seed docker-up docker-down docker-logs clean

help:
	@echo "Available targets:"
	@echo "  install          Install dependencies into .venv"
	@echo "  run              Run the API locally with uvicorn (reload enabled)"
	@echo "  test             Run the test suite"
	@echo "  test-cov         Run the test suite with coverage report"
	@echo "  lint             Run ruff, black --check, isort --check"
	@echo "  format           Auto-format code with black and isort"
	@echo "  migrate          Apply Alembic migrations (upgrade head)"
	@echo "  migrate-generate Autogenerate a new Alembic migration (MSG=... required)"
	@echo "  seed             Seed the database with sample doctors/patients"
	@echo "  docker-up        Start the full stack via docker compose"
	@echo "  docker-down      Stop the docker compose stack"
	@echo "  docker-logs      Tail docker compose logs"
	@echo "  clean            Remove caches and build artifacts"

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pre-commit install

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

test-cov:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check .
	black --check .
	isort --check-only .

format:
	black .
	isort .
	ruff check --fix .

migrate:
	alembic upgrade head

migrate-generate:
	@if [ -z "$(MSG)" ]; then echo "Usage: make migrate-generate MSG='description'"; exit 1; fi
	alembic revision --autogenerate -m "$(MSG)"

seed:
	python -m scripts.seed

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
