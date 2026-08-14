# 单一人库管道 — 设计文档

**日期**: 2026-08-14
**范围**: seed_from_static_data 与爬虫流共用同一保存/计数/批量提交逻辑
**策略**: 提取 SyncEngine 私有 _ingest_book_stream；删除 4 个一行 statics；1 个 ticket
**上游决策**: 架构评审候选 #4（grilling 已确认）

---

## 问题

- seed_from_static_data 手写第二条入库循环（行校验、BookInfo 构造、save_book、
  计数、批量提交），与 sync_publisher_books 的爬虫流同构；
- SyncEngine 上 4 个一行 statics（_resolve_static_data_dir / _normalize_isbn /
  _parse_static_date / _parse_int）纯委托 publisher_data；
- ingestor 的 docstring 声称「SyncEngine 只保留同步编排」，与现状矛盾。

## 设计

### _ingest_book_stream（两路共用）

    def _ingest_book_stream(
        self,
        book_infos: Iterable[BookInfo],
        publisher: Publisher,
        *,
        translate: bool,
        touched_books: list[NewBook],
        commit_interval: int | None = None,
        on_error: Callable[[Exception, BookInfo], None] | None = None,
    ) -> dict[str, int]

- 对每本书：total 计数（含保存失败尝试，统一为爬虫流语义）→ save_book →
  计数 added/updated/skipped；异常走 on_error（默认 DB_QUERY「保存书籍失败」）。
- commit_interval 非 None 时按 total 批量提交。

### _iter_static_book_infos（静态行解析收敛）

    def _iter_static_book_infos(self, rows, result) -> Iterator[BookInfo]

- 非字典行 / 缺标题作者行 → result['skipped'] += 1；
- 构造异常 → CRAWLER 日志 + result['errors'] += 1；
- BookInfo 构造直用 pd.normalize_isbn / pd.parse_static_date / pd.parse_int_safe。

### 删除

- SyncEngine 上 4 个一行 statics，调用点直用 publisher_data。

## 行为保持（Q3）与一处语义统一

- 结果字典字段（files_seen/total/added/updated/skipped/errors）、逐文件 commit、
  last_sync_at/sync_count 更新、ensure_static_data_seeded 跳过语义不变。
- 已知语义统一：total 统一为「尝试计数」（爬虫流语义）。原静态路径仅在
  保存成功时计入 total，合并后失败的保存尝试也计入 total（errors 同步 +1）。

## 变更文件

- app/services/new_book/sync_engine.py
- tests/test_sync_engine.py（静态播种用例补充非法行/失败尝试计数）
- docs/superpowers/specs/ 本文件

## 测试策略

- 既有 test_sync_engine.py 播种/同步用例保持绿色。
- 新增：非法行跳过计数、保存失败时 total 与 errors 同时 +1。
- 验收门：全量 pytest、ruff check、mypy 通过。
