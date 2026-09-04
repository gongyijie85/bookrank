.PHONY: lint format typecheck test check translations build-frontend

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

# 前端打包（#177）：CSS/JS 合并+minify+指纹 -> static/dist/
build-frontend:
	node scripts/build_frontend.mjs

check: lint typecheck test translations
