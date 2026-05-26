# BookRank 代码质量全面优化 — 设计文档

**日期**: 2026-05-26  
**范围**: 错误处理统一化 / 大文件拆分 / 服务注入标准化 / 前端清理  
**策略**: 分层渐进重构（方案 B），每阶段独立可验证

---

## 阶段 1：错误处理统一化

### 问题
- 253 处 `except Exception` 裸捕获
- 14 处 silently swallow（`pass` / `return None`）
- 没有统一的错误分类和统计

### 设计

新增 `app/utils/error_handler.py`，提供三个原语：

1. **`safe_execute(operation_name, fallback=None, category=ErrorCategory.UNKNOWN)`**
   - 装饰器/上下文管理器
   - 自动记录异常到 logger + ErrorTracker
   - 返回 fallback 值（降级）

2. **`ErrorCategory`** 枚举
   - API_CALL, DB_QUERY, TRANSLATION, CACHE, CRAWLER, UNKNOWN

3. **`log_error(category, message, exc_info=False)`**
   - 集中日志 + ErrorTracker 记录

### 变更文件
- **新增**: `app/utils/error_handler.py`
- **修改**: `main.py(5)`, `__init__.py(2)`, `zhipu_translation_service.py(3)`, `book_language_pack.py(2)`, `cache_service.py(1)`, `api_utils.py(1)`, `new_book_service.py(1)`, `translation_cache_service.py(2)`
- **新增测试**: `tests/test_error_handler.py`

---

## 阶段 2：大文件拆分

### 2a. `new_book_service.py`（1144行 → 4 模块）

| 新模块 | 职责 | 预估行数 |
|--------|------|----------|
| `publisher_registry.py` | 出版社定义、CRUD、爬虫类映射 | ~200 |
| `book_sync_service.py` | 数据同步编排、去重、批量处理 | ~350 |
| `book_translation_service.py` | 翻译管道管理 | ~300 |
| `new_book_service.py` | 薄门面，委托到子模块 | ~300 |

### 2b. `main.py` 路由层清理（965行）

- 提取 `_get_cached_data()` → `book_service`
- 提取 `_filter_category_data()` → `book_service`
- 路由层只保留：参数校验、调用 service、渲染模板

---

## 阶段 3：服务注入标准化

新增 `app/services/registry.py`：

```python
def get_book_service() -> BookService
def get_cache_service() -> CacheService
def get_translation_service() -> TranslationService
def get_image_cache_service() -> ImageCacheService
```

替换所有 `app.extensions.get('xxx')` → 类型安全的 getter。

---

## 阶段 4：前端清理

- 移除未使用的 JS：`app.js`、`components.js`、`store.js`（零模板引用）
- 移除 service-worker 中对应缓存条目

---

## 测试策略

每阶段完成后运行全量测试（214 tests），确保零回归。

---

## 风险与回滚

- 所有改动分阶段提交，每阶段可独立 revert
- 大文件拆分保持原有公开 API 不变（薄门面模式）
- 前端清理前确认零引用
