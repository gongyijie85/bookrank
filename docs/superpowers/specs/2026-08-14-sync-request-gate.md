# 同步请求闸门 — 设计文档

**日期**: 2026-08-14
**范围**: 同步冷却、多 worker 锁、per-IP 导出冷却、静态播种一次性化
**策略**: 新模块 SyncRequestGate + setup 注册；1 个 ticket
**上游决策**: 架构评审候选 #5（grilling 已确认）

---

## 问题

- sync_lock / last_sync_time / export_last_<ip> 是 current_app.extensions 的裸键，
  生命周期规则散在 routes/new_books.py 的 4 个辅助函数里；
- per-IP 导出冷却字典无界增长（每个访问过的 IP 永久占键）；
- 7 处每请求调用 engine.ensure_static_data_seeded()（每次至少一次 COUNT 查询）。

## 设计

新模块 app/services/sync_request_gate.py：

    class SyncRequestGate:
        sync_cooldown_remaining() -> float | None   # 60s 冷却，None=放行
        record_sync()                                # 同步完成时记录
        export_cooldown_remaining(ip) -> float | None  # 10s/每 IP + 惰性过期清理
        seed_static_data(sync_engine)               # 进程内一次性播种（幂等）

- setup.init_services 注册 app.extensions['sync_request_gate']；
- service_helpers 提供 get_sync_request_gate()。

## 路由改写（行为保持）

- _check_sync_cooldown / _check_export_cooldown 只做消息格式化，状态在闸门内；
- 同步路由 record_sync 替代 lock+_set_last_sync_time；
- _ensure_static_seeded（6 处）+ main.py 新书页改走 gate.seed_static_data。
- 消息文本与 429/冷却语义不变。

## 变更文件

- 新增: app/services/sync_request_gate.py、tests/test_sync_request_gate.py
- 修改: app/setup.py、app/utils/service_helpers.py、app/routes/new_books.py、
  app/routes/main.py、tests/test_new_books_routes.py（冷却测试迁移到闸门 API）
- 文档: CONTEXT.md 术语、本 spec

## 测试策略

- 闸门单测：冷却窗口/record_sync/每 IP 独立/惰性过期清理/播种一次/播种失败可重试。
- 既有路由冷却与导出 429 测试保持绿色（状态访问改闸门）。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 术语

见根目录 CONTEXT.md（同步请求闸门、导出冷却）。
