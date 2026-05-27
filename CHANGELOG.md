# Changelog

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
