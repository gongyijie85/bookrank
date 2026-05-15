.PHONY: lint format typecheck test check

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/

test:
	python -m pytest tests/ -v --cov=app --cov-report=term-missing

check: lint typecheck test
