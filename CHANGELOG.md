# Changelog

## v0.9.31 - 2026-05-28

### feat: 管理增强 — 爬虫管理、系统监控、数据备份

**爬虫管理 API**：
- `POST /api/admin/crawler/run/<publisher>` 手动触发爬虫（支持 category、max_books 参数）
- `GET /api/admin/crawler/status` 查看所有出版社爬虫状态（活跃数、上次运行时间）
- 内存中跟踪爬虫运行状态（running/completed/failed）

**系统监控**：
- `GET /api/admin/system/status` 返回进程指标（RSS内存、VMS内存、CPU、线程数）
- 数据库类型检测（sqlite/postgresql/mysql）
- 缓存命中率统计、错误日志统计、进程运行时间

**数据备份 API**：
- `GET /api/admin/backup/export` 导出全库为 JSON 文件（awards、award_books、weekly_reports 等6张表）
- `POST /api/admin/backup/import` 从 JSON 导入数据（跳过 id/timestamp 字段避免冲突）

**依赖变更**：
- 新增 `psutil>=5.9.0`（系统监控指标采集）

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 987 passed

## v0.9.30 - 2026-05-27

### feat: 功能补全 — 收藏持久化、公共API、搜索扩展

**收藏持久化**：
- 新建 `UserFavorite` 模型（session_id + isbn + created_at）
- `POST /api/favorites` 添加收藏 | `DELETE /api/favorites/<isbn>` 取消收藏
- `GET /api/favorites` 获取收藏列表 | `GET /api/favorites/check/<isbn>` 检查状态
- 前端 `toggleFavorite` 对接后端 API，替换原有 console.log 占位

**新书公共 API**：
- `GET /api/public/new-books` 获取新书列表（支持分页、分类、出版社筛选）
- `GET /api/public/new-books/<publisher>` 按出版社获取新书

**推荐公共 API**：
- `GET /api/public/recommendations` 智能推荐（自动降级到热门推荐）

**搜索扩展**：
- SmartSearchService 同时搜索 AwardBook + NewBook 两个数据源
- 搜索结果合并，每条结果标注 `source: 'award'` 或 `'new_book'`

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.11%

## v0.9.29 - 2026-05-27

### refactor: 前端瘦身 — CSS/JS 提取与模板精简

**CSS 提取**：
- `templates/index.html` 1093 行内联 CSS → `static/css/index.css` 独立文件
- 通过 `{% block extra_css %}` + `<link>` 标签引用，保留 CSP nonce

**JS 提取**：
- `templates/index.html` 1250 行内联 JS → `static/js/index.js` ES Module
- Jinja2 模板变量（defaultCover、currentCategory）提取到 `window.APP_CONFIG` 配置对象
- 通过 `<script type="module">` 加载，保留 CSP nonce

**模板瘦身**：
- `index.html` 从 2703 行减至约 580 行（减少 78%）
- 保留最小化内联 script 块传递服务端配置变量

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.46%

## v0.9.28 - 2026-05-27

### chore: 地基修复 — 统一 Python 版本与 CI 门禁

**render.yaml**：
- `PYTHON_VERSION` 3.11.0 → 3.13.0
- 构建命令改用 `requirements-prod.txt`（减少生产环境内存占用）

**CI 工作流统一**：
- `test.yml`：Python 3.11 → 3.13；移除 `--exit-zero`，lint 错误阻断构建
- `update-books.yml`：Python 3.10 → 3.13
- `ci.yml`：已为 3.13，无需修改

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed

## v0.9.27 - 2026-05-27

### refactor: 服务注入标准化（阶段3完成）

**增强 `service_helpers.py`**：
- `get_translation_service()` 添加返回类型 `HybridTranslationService | None`
- 新增 `register_service(app, name, service)` 统一服务注册
- 新增 `require_cache_service()`、`require_translation_service()`、`require_image_cache_service()` 非空 getter

**替换直接 `app.extensions` 访问**：
- `setup.py`：5 处 `app.extensions['xxx'] = ...` → `register_service()`
- `setup.py`：5 处 `app.extensions.get('xxx')` → 类型安全 getter 函数
- `scripts/batch_translate.py`：3 处 `app.extensions.get('book_service')` → `get_book_service()`
- `app/utils/__init__.py`：导出新增的 5 个函数

**保留未替换**：
- `app/utils/exceptions.py`：`safe_service_call` 使用动态 key，保持原样
- `migrations/env.py`：Flask-Migrate 扩展，保持原样

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.46%

## v0.9.26 - 2026-05-27

### refactor: 大文件拆分（阶段2完成）

**NewBookService 拆分为子模块**：
- `app/services/new_book/publisher_manager.py`（81行）：PublisherManager 类
- `app/services/new_book/sync_engine.py`（416行）：SyncEngine 类
- `app/services/new_book/translation_pipeline.py`（105行）：TranslationPipeline 类
- `app/services/new_book/query_service.py`（159行）：NewBookQueryService 类
- `app/services/new_book/__init__.py`（154行）：NewBookService 门面类，保持向后兼容
- 原 `new_book_service.py` 改为重导出（3行），所有公开 API 签名不变

**main.py 辅助函数提取**：
- `app/utils/book_filters.py`（60行）：filter_books_by_search, filter_books_by_publisher, filter_books_by_weeks, sort_books
- `app/utils/date_helpers.py`（28行）：validate_date, parse_report_content
- `app/services/book_detail_service.py`（214行）：fetch_google_books_details, merge_or_translate_book, translate_field_async, update_book_from_google_books, is_valid_isbn
- `app/routes/main.py`：972行 → 677行（减少 295行，-30.4%）

**Bug 修复**：
- 移除重复 `@staticmethod` 装饰器
- 统一 `_GOOGLE_BOOKS_CRAWLERS` 定义
- mypy 类型注解修复：门面类类级别注解、SQLAlchemy filter 表达式 type ignore

**验证**：ruff 0 错误 | mypy 0 错误 | pytest 953 passed | 覆盖率 60.72%
