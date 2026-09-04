.PHONY: lint format typecheck test check translations

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/

test:
	python -m pytest tests/

# 提取/更新/编译翻译（awards 等新增 _() 后的 CI 前置步骤）
translations:
	pybabel extract -F babel.cfg -o translations/messages.pot .
	pybabel update -D messages -i translations/messages.pot -d translations
	pybabel compile -d translations

check: lint typecheck test translations
