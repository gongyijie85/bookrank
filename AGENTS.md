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
