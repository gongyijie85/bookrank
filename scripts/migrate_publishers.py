"""
出版社爬虫迁移脚本

将 Simon & Schuster、Hachette、HarperCollins、Macmillan 的爬虫类
从 HTML 爬虫切换到 Google Books Publisher 爬虫。

原因：HTML 爬虫无法获取这些出版社的数据（反爬、JS 渲染等），
Google Books API 按出版社名搜索是最稳定可靠的方案。

用法:
    python scripts/migrate_publishers.py
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.database import db
from app.models.new_book import Publisher


# 迁移映射：旧爬虫类名 -> 新爬虫类名
CRAWLER_MIGRATION = {
    'SimonSchusterCrawler': 'SimonSchusterGoogleCrawler',
    'HachetteCrawler': 'HachetteGoogleCrawler',
    'HarperCollinsCrawler': 'HarperCollinsGoogleCrawler',
    'MacmillanCrawler': 'MacmillanGoogleCrawler',
}


def migrate_publishers():
    """执行出版社爬虫迁移"""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("出版社爬虫迁移脚本")
        print("=" * 60)

        # 查询需要迁移的出版社
        publishers = Publisher.query.filter(
            Publisher.crawler_class.in_(list(CRAWLER_MIGRATION.keys()))
        ).all()

        if not publishers:
            print("\n没有需要迁移的出版社。")
            print("可能已经迁移过了，或者数据库中没有对应的出版社。")

            # 显示当前状态
            print("\n当前出版社状态:")
            all_publishers = Publisher.query.order_by(Publisher.name_en).all()
            for pub in all_publishers:
                print(f"  {pub.name_en}: {pub.crawler_class}")
            return

        print(f"\n找到 {len(publishers)} 个需要迁移的出版社:\n")

        for pub in publishers:
            old_class = pub.crawler_class
            new_class = CRAWLER_MIGRATION.get(old_class)

            if not new_class:
                print(f"  [跳过] {pub.name_en}: 无对应迁移映射 ({old_class})")
                continue

            print(f"  {pub.name_en}:")
            print(f"    旧爬虫: {old_class}")
            print(f"    新爬虫: {new_class}")

            # 执行迁移
            pub.crawler_class = new_class

        # 确认提交
        print("\n" + "-" * 60)
        confirm = input("确认执行迁移？(y/N): ").strip().lower()

        if confirm == 'y':
            db.session.commit()
            print("\n迁移完成！")

            # 显示迁移后状态
            print("\n迁移后出版社状态:")
            all_publishers = Publisher.query.order_by(Publisher.name_en).all()
            for pub in all_publishers:
                status = "✓" if pub.crawler_class in CRAWLER_MIGRATION.values() else " "
                print(f"  [{status}] {pub.name_en}: {pub.crawler_class}")
        else:
            db.session.rollback()
            print("\n已取消迁移。")


if __name__ == "__main__":
    migrate_publishers()
