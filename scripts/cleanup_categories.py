"""
清理新书分类数据中的营销文案

用法：
    python scripts/cleanup_categories.py

功能：
    1. 查询所有包含营销文案的分类
    2. 将这些分类置为 NULL
    3. 输出清理统计
"""
import re
import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.database import db
from app.models.new_book import NewBook


# 营销关键词列表
MARKETING_KEYWORDS = [
    'learn more', 'read more', 'see what', 'take the quiz',
    'join our', 'browse all', 'how to', 'on the rise',
    'you need to', 'you love', 'audiobook', 'events',
    'new releases', 'new stories', 'lists, essays',
]


def is_invalid_category(category: str) -> bool:
    """判断分类是否为无效的营销文案"""
    if not category:
        return False

    category = category.strip()

    # 长度检查
    if len(category) > 30:
        return True

    # 营销关键词检查
    category_lower = category.lower()
    for keyword in MARKETING_KEYWORDS:
        if keyword in category_lower:
            return True

    # 特殊字符检查
    if re.search(r'[>!<]|http[s]?://', category):
        return True

    # 引号检查
    if '"' in category or '"' in category or '"' in category:
        return True

    return False


def cleanup_categories(dry_run: bool = True):
    """
    清理无效分类数据

    Args:
        dry_run: 如果为 True，只显示将要清理的数据，不实际修改
    """
    app = create_app('development')

    with app.app_context():
        # 查询所有有分类的书籍
        books = NewBook.query.filter(
            NewBook.category.isnot(None),
            NewBook.is_displayable == True
        ).all()

        print(f"共找到 {len(books)} 本有分类的书籍")

        # 找出无效分类
        invalid_books = []
        for book in books:
            if is_invalid_category(book.category):
                invalid_books.append(book)

        print(f"其中 {len(invalid_books)} 本有无效分类：")
        print("-" * 60)

        for book in invalid_books:
            print(f"  ID: {book.id}")
            print(f"  书名: {book.title}")
            print(f"  分类: {book.category[:80]}...")
            print()

        if not invalid_books:
            print("没有发现无效分类数据！")
            return

        if dry_run:
            print("=" * 60)
            print("这是预览模式，不会实际修改数据库。")
            print("要执行清理，请运行：python scripts/cleanup_categories.py --execute")
        else:
            # 执行清理
            for book in invalid_books:
                book.category = None

            db.session.commit()
            print(f"已清理 {len(invalid_books)} 条无效分类数据。")


if __name__ == '__main__':
    dry_run = '--execute' not in sys.argv
    cleanup_categories(dry_run=dry_run)
