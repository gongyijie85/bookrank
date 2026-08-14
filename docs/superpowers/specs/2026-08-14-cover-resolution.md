# 封面解析单一策略 — 设计文档

**日期**: 2026-08-14
**范围**: 获奖书籍封面的 fetch→cache→persist 收敛为 CoverResolver
**策略**: 新模块 CoverResolver + 批编排留在 AwardCoverSyncService；1 个 ticket
**上游决策**: 架构评审候选 #6（grilling 已确认）

---

## 问题

- resolve_cover_for_book（单本路径）与 sync_missing_covers（批量路径）各自实现
  fetch→cache→persist，策略分叉（6b7b633 只补了批量路径的缓存文件丢失探测）；
- 两条路径都私探 ImageCacheService._cache_dir。

## 设计

新模块 app/services/cover_resolver.py：

    class CoverResolver:
        resolve(book, persist=True) -> str | None   # 唯一策略入口
        cached_path_available(local_path) -> bool    # 候选筛选（公开）

- 策略链：本地文件 → 原 URL 缓存 → needs_fetch（无 URL 或未命中且 OL 封面）→
  回源（OL ISBN → OL 书名 → Google ISBN → Google 书名）→ 缓存 → 持久化。
- ImageCacheService 新增公开 is_cached_file_present(local_path)，消除 _cache_dir 私探。

## 服务改写（行为保持）

- AwardCoverSyncService 退化为批编排：候选筛选（cached_path_available）、
  逐个 resolve、delay、统计（total_checked/updated/failed/skipped/errors/status）、
  _is_running 防重入——字段与语义不变。
- main.py 的 resolve_cover_for_book 调用签名不变。

## 变更文件

- 新增: app/services/cover_resolver.py
- 修改: app/services/award_cover_sync_service.py、app/services/api_utils.py、
  tests/test_award_cover_sync_service.py（探测/缓存测试迁移到 resolver 与
  ImageCacheService 公开方法）
- 文档: CONTEXT.md 术语、本 spec

## 测试策略

- 既有 31 个封面测试迁移后保持绿色；候选筛选/丢失缓存/存在缓存集成用例不变。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 术语

见根目录 CONTEXT.md（封面解析）。
