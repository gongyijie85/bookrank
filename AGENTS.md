# BookRank Agent 指南

BookRank：图书发现平台（Flask 3 / Python 3.13 + SQLAlchemy 2.0 + Jinja2 + 原生 ES2020+ JS，部署 Render + Gunicorn）。

## 验证命令面（改完代码必跑）

与 CI 口径一致，按序执行：

```bash
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/
pytest tests/ -m "not slow" --cov=app --cov-fail-under=70
```

快捷方式：`make check`（lint + typecheck + test；注意其 test 目标不带覆盖率阈值与 `not slow` 过滤，**提交前请以上述四条命令为准**）。CI 额外使用 `-x --timeout=30`，且当前 CI 的 mypy 命令带 `--ignore-missing-imports`（口径统一到 pyproject 的工作见 issue #100）。

## 质量门现状

- **Ruff**：lint + format 双门，全绿。
- **mypy**：对 app/ 生效，但 pyproject 中对约 26 个热点模块存在 `disable_error_code` overrides（清零工作进行中，见 issue #100）。
- **pytest**：覆盖率阈值本地与 CI 均为 70%（实测约 82%）；CI 只收集 `tests/`。
- **前端**：`static/js` 与 `static/mobile/js` 目前无测试与 lint 门（ESLint 门引入中，见 issue #101）。

## 区域地图

- `app/routes/`：HTTP 路由层，薄层，业务逻辑下沉到 services。
- `app/services/`：业务核心（27 个文件）。重点子域：`new_book/`（新书速递同步引擎与出版社爬虫）、`publisher_data.py`（出版社数据）、翻译服务（智谱 GLM 主 + deep-translator 备）。
- `app/models/`：SQLAlchemy 模型。
- `app/utils/`：错误处理、i18n、净化等工具。
- `scripts/`：运维与数据脚本。
- `tests/`：正式测试唯一位置（73 个文件，marker：unit/integration/slow/api/models/routes/services）。
- `static/js`、`static/mobile/js`、`templates/`：前端（无构建、无打包）。

## Hotspot 提示

- **出版社相关代码（new_book/、publisher_crawler/、publisher_data.py）为活跃开发区**：可能有未合入的 WIP，改动前先 `git status` 确认边界，勿覆盖他人进行中工作。
- **翻译与外部 API**：智谱、NYT、PRH 等依赖环境变量密钥（`ZHIPU_API_KEY`、`NYT_API_KEY`、`PRH_API_KEY`）；测试一律 mock，勿在测试中依赖真实密钥或外网。
- **根目录 `test_*.py` 是本地调试产物**：已被 .gitignore 忽略，不参与任何门禁，勿提交、勿依赖（见 CONTRIBUTING.md 测试约定）。
- **测试环境依赖型 flake**：`test_new_book_service.py::test_sync_publisher_books_writes_language_pack` 在无 `PRH_API_KEY` 环境的全量运行中可能失败，属已知问题（issue #90 fog），勿因它阻塞无关改动。

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `gongyijie85/bookrank`. See `docs/agents/issue-tracker.md`.

### Triage labels

Issues use the five canonical triage labels, plus type, priority (`p0`–`p3`) and module labels
(e.g. `awards`, `new-books`, `mobile`, `i18n`). Apply labels when creating or triaging an
issue. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. See `docs/agents/domain.md`.

## Verify your change (command surface)

Run from the repo root. CI runs the same commands, so local green ≈ CI green:

```bash
ruff check app/ tests/          # lint, must be clean
ruff format --check app/ tests/ # formatting gate (run `ruff format` to fix)
mypy app/                       # type gate, zero errors (pyproject whitelist is the only config)
python -m pytest tests/         # ~2300 tests, coverage gate --cov-fail-under=70 (currently ~83%)
make check                      # all of the above + pybabel translations extract/update/compile
```

Notes:

- `mypy` takes no CLI flags: `pyproject.toml [tool.mypy]` is the single source of truth.
  Do not re-add `--ignore-missing-imports` or `disable_error_code` overrides.
- Column operators (`.is_()/.desc()/.ilike()`) and `db.Model` bases are known mypy
  false positives: line-level `# type: ignore[...]` with a narrow code list is the
  convention (see `app/services/new_book/query_service.py`). Do not broaden to
  module-level disables.
- Frontend: `node scripts/build_frontend.mjs` rebuilds `static/dist/` (hashed bundles).
  Never hand-edit `static/dist/`; edit `static/js|css` + templates, then rebuild.
- i18n: after touching `_()` strings run `make translations` (extract → update → compile)
  or the `.po`/`.mo` files drift from the templates.
- Full suite takes ~2 min; use `pytest tests/test_x.py -q` for a tight loop.

## Quality gates (current)

| Gate | Threshold | Status |
| ---- | --------- | ------ |
| ruff check + format | clean | enforced in CI |
| mypy `app/` | 0 errors | enforced in CI (T5 #100) |
| pytest `--cov-fail-under` | 70 (local == CI) | ~83% actual |
| ESLint `static/js` | zero-tolerance job | see T6 #101 |

## Hotspots (read before touching)

- `app/services/new_book/` (`sync_engine.py`, `query_service.py`, `ingestor.py`): crawler
  orchestration + batch import. Concurrency (ThreadPoolExecutor) and idempotency
  (`batch_id`) matter; run the new-book tests after any change.
- Translation stack (`zhipu_translation_service.py`, `free_translation_service.py`,
  `book_language_pack.py`, `translation_cache_service.py`): primary/fallback/cache
  layers. `deep-translator` is intentionally NOT installed (security); the code
  degrades gracefully, keep it that way.
- `app/services/award_book_service.py`: N+1-sensitive; `test_n_plus_one_regression.py`
  and `test_save_book_metadata_batch_uses_single_select` lock the query counts.
- `app/models/schemas.py` + `new_book.py`: classic `db.Column` declarative style.
  Keep it; do not "modernize" to `Mapped[]` without a tracking issue (spike showed
  150+ constructor false positives, T5 #100).
- `app/routes/admin.py`: admin-only endpoints (`admin_required` + CSRF). CSRF tokens
  are single-use with 1h TTL; residual risk accepted and recorded in `SECURITY.md`.
- Mobile templates (`templates/mobile/`, `static/mobile/js/`): parallel to desktop,
  keep feature parity (search entry, filters, badges).
- HuggingFace Space (`elvis85-bookrank.hf.space`) is a read-only mirror of `main`. The
  `deploy` job commits main's files into the Space repo and HuggingFace rebuilds on push
  — restarting a Space never ships code. Space-only runtime behaviour goes behind
  `app/utils/space_runtime.py` (HF injects `SPACE_ID`); never patch files inside the Space
  repo, that is how it drifted into an unreproducible hard fork once already. The Space's
  `README.md` front matter holds its SDK config and is deliberately preserved by the sync.

## Area map

```text
app/routes/          # Flask blueprints (main, new_books, api/* incl. awards, admin, analytics, health, public_api)
app/services/        # business logic; clients (nyt/google_books/open_library/wikidata/zhipu)
app/services/new_book/  # new-books pipeline: sync_engine → ingestor → query_service
app/models/          # SQLAlchemy models (schemas.py, new_book.py, book.py) + db in database.py
app/utils/           # service_helpers (service registry), api_helpers (CSRF/auth), error_handler
app/tasks/           # APScheduler jobs (weekly_report_task); external cron via CRON_SECRET
scripts/             # build_frontend.mjs, sync_wiki.py, init/migrate helpers
tests/               # pytest suite; regression evidence lives next to specs
static/dist/         # BUILD OUTPUT (frontend bundles) — do not hand-edit
templates/ (+mobile/)# Jinja2 desktop + mobile views
docs/agents/         # agent skill wiring (issue tracker, triage labels, domain)
```

Test files mirror the area they cover (`test_<area>.py`); put regression tests for a
bugfix next to the module's existing test file, not in the repo root
(root-level `test_*.py` are local debug scraps, git-ignored — see CONTRIBUTING.md).
