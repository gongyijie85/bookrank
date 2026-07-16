# BookRank 数据库审计报告

**审计日期**：2026-07-02  
**审计范围**：`app/models/schemas.py`、`app/models/new_book.py`、`migrations/`、生产环境数据库配置（Render + Supabase PostgreSQL）  
**审计人**：Trae Agent（小组 6）  
**关联计划**：`d:\BookRank3\.trae\documents\bookrank-audit-execution-plan-2026-07-02.md`

---

## 执行摘要

本次审计对 BookRank 的数据库模型、迁移历史、索引与约束、连接池配置进行了全面检查。

- **模型层**：共 18 张表，覆盖用户行为、图书元数据、奖项、新书、周报、翻译缓存、API 缓存等模块。
- **迁移历史**：初始迁移 `3d9883f1b5ed` 存在历史缺陷（仅含 CREATE INDEX，缺少 CREATE TABLE），后续由 `create_all_missing_tables` 补充；当前迁移链可正常升级到最新状态。
- **索引与约束**：核心查询路径均有索引覆盖；部分大表（`award_books`、`new_books`、`translation_cache`、`api_cache`）需关注数据增长。
- **连接池**：`ProductionConfig` 已针对 Render/Supabase 做优化（`pool_size=2, max_overflow=1, pool_recycle=600, statement_timeout=15s`）。

**总体 verdict：PASS with CONCERNS（迁移历史存在遗留问题但已补救，大表增长需监控）**

---

## 数据库模型概览

| # | 表名 | 用途 | 核心字段 | 备注 |
|---|------|------|----------|------|
| 1 | `csrf_tokens` | CSRF Token 存储 | `token(PK)`, `created_at` | 需定期清理过期 token |
| 2 | `user_preferences` | 用户偏好 | `session_id(PK)`, `view_mode` | 匿名会话维度 |
| 3 | `user_categories` | 用户关注分类 | `id`, `session_id`, `category_id` | 复合唯一约束 |
| 4 | `user_viewed_books` | 用户浏览记录 | `id`, `session_id`, `isbn`, `viewed_at` | 行为日志，增长快 |
| 5 | `user_favorites` | 用户收藏 | `id`, `session_id`, `isbn`, `created_at` | 复合唯一约束 |
| 6 | `book_metadata` | 图书元数据缓存 | `isbn(PK)`, `title`, `author`, `description_*` | 核心缓存表 |
| 7 | `search_history` | 搜索历史 | `id`, `session_id`, `keyword`, `created_at` | 行为日志，增长快 |
| 8 | `awards` | 奖项 | `id`, `name`, `country` | 小表 |
| 9 | `award_books` | 获奖图书 | `id`, `award_id`, `year`, `title`, `isbn13` | 大表，索引充分 |
| 10 | `translation_cache` | 翻译缓存 | `id`, `source_hash`, `source_text`, `translated_text` | 大表，Text 字段多 |
| 11 | `api_cache` | 外部 API 缓存 | `id`, `api_source`, `request_hash`, `response_data` | 大表，Text 字段多 |
| 12 | `system_config` | 系统配置 | `key(PK)`, `value` | 小表 |
| 13 | `weekly_reports` | 周报 | `id`, `report_date`, `week_start`, `content` | JSON 存大字段 |
| 14 | `report_views` | 周报阅读记录 | `id`, `report_id`, `session_id`, `viewed_at` | 行为日志 |
| 15 | `user_behaviors` | 用户行为事件 | `id`, `session_id`, `event_type`, `created_at` | 行为日志，增长最快 |
| 16 | `publishers` | 出版社 | `id`, `name_en`, `crawler_class`, `is_active` | 小表 |
| 17 | `new_books` | 新书速递 | `id`, `publisher_id`, `title`, `isbn13` | 大表 |
| 18 | （由 `app/models/new_book.py` 定义） | 同上 | 同上 | `schemas.py` 重导出 |

---

## 迁移历史一致性

### 迁移文件清单

| 文件名 | Revision | Down Revision | 说明 |
|--------|----------|---------------|------|
| `3d9883f1b5ed_initial_migration_all_tables.py` | `3d9883f1b5ed` | `None` | **历史缺陷**：仅 CREATE INDEX，无 CREATE TABLE |
| `add_chinese_fields_to_book_metadata.py` | `add_chinese_fields...` | `3d9883f1b5ed` | 为 `book_metadata` 增加中文字段 |
| `add_csrf_tokens_table.py` | `add_csrf_tokens_table` | `add_chinese_fields...` | 增加 `csrf_tokens` 表 |
| `create_all_missing_tables.py` | `create_all_missing_tables` | `add_csrf_tokens_table` | 补充 8 张缺失表 |

### 检查结果

- **迁移链完整**：从 `None` → `3d9883f1b5ed` → `add_chinese_fields...` → `add_csrf_tokens_table` → `create_all_missing_tables`，无分支或断链。
- **初始迁移缺陷已补救**：`create_all_missing_tables` 已补充 `translation_cache`、`api_cache`、`system_config`、`weekly_reports`、`report_views`、`user_behaviors`、`publishers`、`new_books` 建表语句。
- **当前模型与迁移一致性**：通过代码审查，`book_metadata` 当前字段与迁移一致；`csrf_tokens` 与迁移一致；其他表字段与 `create_all_missing_tables` 一致。
- **建议**：在生产环境升级迁移前，先在临时数据库执行 `flask db upgrade` 验证；不要删除历史迁移文件。

---

## 索引与约束分析

### 索引覆盖良好的表

| 表 | 关键索引 | 用途 |
|----|----------|------|
| `award_books` | `idx_award_books_award_year_category`、`idx_award_books_displayable_year`、`idx_award_books_search_combined`、`ix_award_books_isbn13` 等 | 奖项/年份/分类筛选、搜索、ISBN 查询 |
| `new_books` | `idx_new_books_publisher_date`、`idx_new_books_category_display`、`idx_new_books_search`、`ix_new_books_isbn13` 等 | 新书列表、分类筛选、搜索 |
| `book_metadata` | `idx_book_metadata_title`、`idx_book_metadata_author` | 元数据搜索 |
| `user_favorites` | `uix_user_favorite`、`idx_user_favorites_session_created` | 收藏查重与列表 |
| `translation_cache` | `uix_translation_source_target`、`idx_translation_lang_usage` | 翻译缓存去重与命中 |
| `api_cache` | `uix_api_cache_source_hash`、`idx_api_cache_expiry` | API 缓存去重与过期清理 |

### 潜在风险

| 严重等级 | 位置 | 问题 | 建议 |
|----------|------|------|------|
| **Medium** | `user_behaviors`、`search_history`、`report_views`、`user_viewed_books` | 行为日志表无 TTL/分区策略，长期运行会无限增长，影响查询与备份。 | 增加定期清理任务（如保留 90 天）；大表后考虑按时间分区或归档。 |
| **Medium** | `translation_cache.source_text`、`api_cache.response_data` | Text 字段存储大文本，频繁写入会增加表大小与 WAL。 | 监控表大小；评估是否需要限制缓存条目数或按 LRU 淘汰。 |
| **Low** | `award_books` 复合索引 | `idx_award_books_award_year_category` 覆盖 `(award_id, year, category)`，但分类筛选常单独使用 `category`。 | 当前 `ix_award_books_category` 已存在，满足需求。 |
| **Low** | `weekly_reports.content` | JSON 大字段存储整榜数据，单条可能达数百 KB。 | 周报数量少，当前可接受；若增长可考虑压缩或拆分。 |

---

## 外键约束分析

| 子表 | 字段 | 父表 | 约束 | 备注 |
|------|------|------|------|------|
| `user_categories` | `session_id` | `user_preferences` | `db.ForeignKey('user_preferences.session_id')` | 级联删除 |
| `user_viewed_books` | `session_id` | `user_preferences` | `db.ForeignKey('user_preferences.session_id')` | 级联删除 |
| `award_books` | `award_id` | `awards` | `db.ForeignKey('awards.id')` | 无级联删除 |
| `report_views` | `report_id` | `weekly_reports` | `db.ForeignKey('weekly_reports.id')` | 迁移中定义，无显式级联 |
| `new_books` | `publisher_id` | `publishers` | `db.ForeignKey('publishers.id', ondelete='CASCADE')` | 迁移中显式 CASCADE |

**说明**：核心关系均有外键约束；`award_books` 删除奖项时不会级联删除获奖图书，符合业务预期（奖项信息可缺失但图书保留）。

---

## 连接池与 Supabase 配置

### 当前 `ProductionConfig`

```python
SQLALCHEMY_ENGINE_OPTIONS: dict[str, object] = {
    'pool_size': 2,
    'max_overflow': 1,
    'pool_timeout': 15,
    'pool_recycle': 600,
    'pool_pre_ping': True,
    'echo': False,
    'connect_args': {
        'connect_timeout': 5,
        'options': '-c statement_timeout=15000',
    },
}
```

### 评估

- `pool_size=2 + max_overflow=1` 对单 Worker（`WEB_CONCURRENCY=1`）足够，但健康检查 `SELECT 1` 与请求并发时可能短暂等待。
- `pool_recycle=600` 配合 `pool_pre_ping=True` 可有效避免 Supabase Session Pooler 长时间连接中断。
- `statement_timeout=15000` 防止慢查询拖垮实例。
- Supabase Session Pooler 默认最大连接数 200，当前配置不会耗尽。

### 建议

- 保持当前连接池配置；若出现 `QueuePool limit` 告警，再调整为 `pool_size=1, max_overflow=2`。
- 监控 `pool_timeout` 与平均查询时间。

---

## 大表风险评估

| 表 | 风险点 | 当前缓解措施 | 后续建议 |
|----|--------|--------------|----------|
| `award_books` | 随奖项/年份增长 | 索引充分 | 长期可考虑按年份分区 |
| `new_books` | 随爬虫同步增长 | `is_displayable` 索引 | 定期清理旧数据或归档 |
| `translation_cache` | 每次翻译写入 | 唯一约束去重 | 设置最大条目数或定期清理低频条目 |
| `api_cache` | 每次外部 API 调用写入 | `expires_at` 索引 | 定期清理过期缓存 |
| `user_behaviors` / `search_history` / `report_views` / `user_viewed_books` | 匿名用户行为日志快速增长 | 有按时间索引 | 增加自动清理任务，保留 90 天 |

---

## 结论与下一步行动

1. **迁移链完整**：初始迁移 `3d9883f1b5ed` 的历史缺陷已由 `create_all_missing_tables` 补救，当前模型与迁移一致。
2. **索引与约束充分**：核心查询路径均已覆盖；行为日志大表需关注增长。
3. **连接池配置合理**：已适配 Render + Supabase Session Pooler。
4. **建议跟进**：
   - 为行为日志表增加定期清理任务。
   - 限制 `translation_cache` 与 `api_cache` 条目数或 TTL。
   - 部署前在临时数据库执行完整 `flask db upgrade` 验证。
