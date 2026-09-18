.PHONY: lint format typecheck test check translations build-frontend i18n-drift check-covers check-lang

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/

test:
	python -m pytest tests/

# i18n 目录漂移检查（与 CI 的 i18n-catalog job 同款）。刻意不并入 check：
# check 里的 translations 会先把目录补齐，再查漂移必然恒过，失去意义。
i18n-drift:
	python scripts/check_i18n_drift.py

# 提取/更新/编译翻译（awards 等新增 _() 后的 CI 前置步骤）
translations:
	pybabel extract -F babel.cfg -o translations/messages.pot .
	pybabel update -D messages -i translations/messages.pot -d translations
	pybabel compile -d translations

# 前端打包（#177）：CSS/JS 合并+minify+指纹 -> static/dist/
build-frontend:
	node scripts/build_frontend.mjs

# 同步 Code Wiki/ -> GitHub wiki（默认 dry-run；--push 实际推送）
sync-wiki:
	python scripts/sync_wiki.py

# 封面可用性自检：请求线上 /cover，找出"永久停在占位图"的封面。
# 国内不挂 VPN 的用户看到的就是这个结果（浏览器同样只请求本站 /cover）。
# 退出码非 0 = 有封面在代理侧永久不可用。默认打生产；本地起服务后加 --base http://127.0.0.1:5000。
# 定时监控用更保守的参数：--attempts 3 --wait 6 --distinguish-upstream
# （见 .github/workflows/cover-monitor.yml；--attempts 1 会把冷缓存误报成故障）
check-covers:
	python scripts/check_cover_proxy.py

# 语言切换自检：用真实浏览器把语言从 zh 切到 en，列出仍冻结在原语言的 chrome 文案。
# 语言偏好存在 localStorage，切换是**就地改写** DOM（不重新请求），所以静态读模板看不出
# 有没有生效 —— 必须真浏览器。需要 Chrome（可用环境变量 CHROME 指定路径）。
#   make check-lang URL=https://bookrank-ckml.onrender.com/book/0?category=hardcover-fiction
check-lang:
	node scripts/check_lang_residue.mjs "$(URL)"

check: lint typecheck test translations
