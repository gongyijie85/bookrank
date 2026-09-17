# 出版社目录合一 — 设计文档

**日期**: 2026-08-14
**范围**: 展示目录与同步集合的关联方式
**策略**: 目录条目显式标注 sync_name_en 关联键，删除 main.py 别名表；1 个 ticket
**上游决策**: 架构评审候选 #8（grilling 提问超时，按推荐选项执行）

---

## 问题

- 展示目录（app/data/publishers.py，~40 条目）与同步集合
  （publisher_data.DEFAULT_PUBLISHERS，7 条）是两个平行定义；
- main.py 用 2 条别名把 'Hachette Book Group'/'Pan Macmillan' 映射到
  DB 的 'Hachette'/'Macmillan'——关联知识藏在路由代码里。

## 设计

- 目录中名称写法与 DB 不一致的 2 条可同步出版社条目新增可选字段
  sync_name_en（DB name_en 关联键）：Pan Macmillan→Macmillan、
  Hachette Book Group→Hachette；其余条目缺省回退 name_en 精确匹配。
- 删除 _PUBLISHER_DIRECTORY_ALIASES；_resolve_new_books_publisher_ids 改用
  pub.get('sync_name_en', name_en)。
- DEFAULT_PUBLISHERS 不动（存量库行零迁移风险）。

## 行为保持

- 出版社页面渲染、可跳转条目集合（与旧别名表等价）、total_publishers 不变。

## 变更文件

- app/data/publishers.py（5 条目标注）、app/routes/main.py（别名表删除）
- 文档: CONTEXT.md、本 spec
- 测试: tests/test_main_routes.py 既有别名用例保持绿色（语义等价）

## 测试策略

- 既有 publishers 页匹配/别名/无匹配用例保持绿色。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 术语

见根目录 CONTEXT.md（出版社目录 sync_name_en）。
