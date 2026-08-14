# 分类清洗单一归属 — 设计文档

**日期**: 2026-08-14
**范围**: NewBook.category 的营销文案过滤与英文→中文归一
**策略**: 新深模块 app/services/category_cleanup_service.py，两条路由共用；1 个 ticket
**上游决策**: 架构评审候选 #3（grilling 决策树，维护者未在线答复，按推荐选项执行）

---

## 问题

“清洗一个分类”的规则只有一处（publisher_data.sanitize_category），但被
三条 seam 触达：

1. admin.py cleanup_categories：扫描 + 对比 + batch_update_categories 写入；
2. routes/new_books.py _migrate_categories：同构扫描 + 内联事务；
3. ingestor._sanitize_category：一行委托包装。

两个扫描循环重复、两种事务样式；分类规则没有单一归属。

## 设计

新模块 app/services/category_cleanup_service.py：

    @dataclass
    class CategoryScan:
        total_checked: int
        invalid: list[dict]  # {id, title, old_category, new_category}

    def scan() -> CategoryScan: ...
    def apply_cleanup(dry_run: bool = False) -> dict
        # 返回 {total_checked, invalid_found, updated, details(前 50 条)}

- 规则仍只有 publisher_data.sanitize_category 一处；模块内部调用它。
- 写入统一走 admin_service.batch_update_categories（单一事务样式）。
- ingestor 删除一行包装，直接调 publisher_data.sanitize_category
  （入库路径只做单值清洗，不参与扫描）。

## 路由改写（行为保持）

- GET/POST /api/admin/categories/cleanup：调用 apply_cleanup(dry_run)，
  返回结构与消息不变。
- POST /api/new-books/migrate-categories：调用 apply_cleanup(dry_run=False)，
  返回 {migrated_count: updated, total_checked}，消息不变。

## 变更文件

- 新增: app/services/category_cleanup_service.py
- 修改: app/routes/admin.py（cleanup_categories）、
  app/routes/new_books.py（删除 _migrate_categories）、
  app/services/new_book/ingestor.py（删除包装）
- 新增测试: tests/test_category_cleanup_service.py
- 文档: CONTEXT.md 术语「分类清洗（category cleanup）」；
  tests/regression-suite.md 登记

## 测试策略

- 模块单测：scan 识别营销分类/英文映射；dry_run 不写入；apply 写入并返回计数。
- 既有 admin 清理测试保持绿色（patch sanitize_category 仍生效）。
- 真实路径回归（test_cleanup_with_real_sanitize_detects_marketing_category）保持。
- 验收门：全量 pytest、ruff check、mypy 通过。

## 术语

见根目录 CONTEXT.md（分类清洗：sanitize=单值规则，scan=清单扫描，apply=批量写入）。
