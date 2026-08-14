"""分类清洗模块：NewBook.category 的营销文案过滤与英文→中文归一。

单一归属（候选 #3）：sanitize 规则仍在 publisher_data.sanitize_category，
本模块提供扫描与批量写入两个操作，admin 清理与 /migrate-categories
两条路由共用。入库路径只做单值清洗，不经过本模块。
"""

from dataclasses import asdict, dataclass, field

from ..models.database import db
from ..models.new_book import NewBook
from . import publisher_data


@dataclass
class InvalidCategory:
    """一条待清洗的分类记录。"""

    id: int
    title: str
    old_category: str | None
    new_category: str | None


@dataclass
class CategoryScan:
    """一次分类扫描的结果。"""

    total_checked: int
    invalid: list[InvalidCategory] = field(default_factory=list)


@dataclass
class CategoryCleanupResult:
    """一次清理（扫描 + 可选写入）的结果；details 为 JSON 就绪的字典列表。"""

    total_checked: int
    invalid_found: int
    updated: int
    details: list[dict] = field(default_factory=list)


def scan() -> CategoryScan:
    """扫描所有带分类的新书，返回待清洗清单（不写入）。"""
    books = NewBook.query.filter(NewBook.category.isnot(None)).all()  # type: ignore[union-attr]
    invalid = []
    for book in books:
        old_category = book.category
        new_category = publisher_data.sanitize_category(old_category)
        if new_category != old_category:
            invalid.append(
                InvalidCategory(
                    id=book.id,
                    title=book.title,
                    old_category=old_category,
                    new_category=new_category,
                )
            )
    return CategoryScan(total_checked=len(books), invalid=invalid)


def _batch_update(id_to_category: dict[int, str | None]) -> int:
    """批量更新 NewBook 分类并提交，返回更新条数（本模块内聚的唯一事务样式）。"""
    books = db.session.query(NewBook).filter(NewBook.id.in_(list(id_to_category.keys()))).all()  # type: ignore[attr-defined]
    for book in books:
        book.category = id_to_category[book.id]
    db.session.commit()
    return len(books)


def apply_cleanup(dry_run: bool = False) -> CategoryCleanupResult:
    """扫描并（可选）批量写入清洗后的分类。

    Args:
        dry_run: True 只扫描不写入（预览），False 写入。

    Returns:
        CategoryCleanupResult（details 为前 50 条的 JSON 就绪字典）
    """
    scan_result = scan()
    updated = 0
    if not dry_run and scan_result.invalid:
        id_to_category = {item.id: item.new_category for item in scan_result.invalid}
        updated = _batch_update(id_to_category)

    return CategoryCleanupResult(
        total_checked=scan_result.total_checked,
        invalid_found=len(scan_result.invalid),
        updated=updated,
        details=[asdict(item) for item in scan_result.invalid[:50]],
    )
