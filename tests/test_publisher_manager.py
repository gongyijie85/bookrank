"""出版社管理模块测试

由 tests/test_new_book_service.py 拆分而来（门面坍塌重构）：
针对 PublisherManager 的出版社初始化、查询、状态切换与迁移规则。
"""

import pytest

from app.models.new_book import Publisher
from app.services.new_book.publisher_manager import PublisherManager


@pytest.fixture
def manager():
    """创建出版社管理模块实例（无状态，直接使用全局 db.session）"""
    return PublisherManager()


class TestPublisherManager:
    def test_init_publishers(self, manager, db):
        """测试初始化默认出版社"""
        count = manager.init_publishers()

        assert count > 0
        assert Publisher.query.count() >= count

    def test_init_publishers_seeds_unreliable_sources_as_inactive(self, manager, db):
        """Google Books(通用关键词搜索) 和 Open Library 实测数据质量不可靠，
        全新部署时应该以停用状态创建，不需要管理员事后手动关掉。"""
        manager.init_publishers()

        google_books = Publisher.query.filter_by(name_en='Google Books').first()
        open_library = Publisher.query.filter_by(name_en='Open Library').first()

        assert google_books is not None
        assert google_books.is_active is False
        assert open_library is not None
        assert open_library.is_active is False

    def test_init_publishers_does_not_override_existing_row_active_state(self, manager, db):
        """已存在的出版社行不应该被 init_publishers() 静默改动 is_active——
        管理员通过 update_publisher_status 手动切换过的状态要保留。"""
        existing = Publisher(
            name='Google Books',
            name_en='Google Books',
            website='https://books.google.com',
            crawler_class='GoogleBooksCrawler',
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        manager.init_publishers()

        refreshed = Publisher.query.filter_by(name_en='Google Books').first()
        assert refreshed.is_active is True

    def test_init_publishers_migrates_prh_to_official_api_crawler(self, manager, db):
        """存量库中仍绑定旧 Google Books 变体的 PRH 记录，init_publishers()
        应自动换向到官方 API 爬虫，无需手工改库（工单 #86）。"""
        existing = Publisher(
            name='企鹅兰登',
            name_en='Penguin Random House',
            website='https://www.penguinrandomhouse.com',
            crawler_class='PenguinRandomHouseCrawler',
            is_active=True,
        )
        db.session.add(existing)
        db.session.commit()

        manager.init_publishers()

        # expire_all 强制从数据库重新加载：同会话内直接 query 会命中
        # 未提交的内存脏对象，掩盖"迁移不 commit"这类落库遗漏（工单 #88）
        db.session.expire_all()
        refreshed = Publisher.query.filter_by(name_en='Penguin Random House').first()
        assert refreshed.crawler_class == 'PrhApiCrawler'

    def test_init_publishers_migrates_hachette_hc_to_google_books_channel(self, manager, db):
        """存量库中绑定站点爬虫的 Hachette/HarperCollins 记录，init_publishers()
        应自动切回 Google Books 出版社通道（工单 #112：站点抓取在生产失效）。"""
        db.session.add(
            Publisher(
                name='阿歇特',
                name_en='Hachette',
                website='https://www.hachettebookgroup.com',
                crawler_class='HachetteCrawler',
                is_active=True,
            )
        )
        db.session.add(
            Publisher(
                name='哈珀柯林斯',
                name_en='HarperCollins',
                website='https://www.harpercollins.com',
                crawler_class='HarperCollinsCrawler',
                is_active=True,
            )
        )
        db.session.commit()

        manager.init_publishers()

        # expire_all 强制从数据库重新加载，避免同会话脏对象掩盖落库遗漏（工单 #88）
        db.session.expire_all()
        hachette = Publisher.query.filter_by(name_en='Hachette').first()
        harper = Publisher.query.filter_by(name_en='HarperCollins').first()
        assert hachette.crawler_class == 'HachetteGoogleCrawler'
        assert harper.crawler_class == 'HarperCollinsGoogleCrawler'

    def test_get_publishers(self, manager, db):
        """测试获取出版社列表"""
        manager.init_publishers()

        publishers = manager.get_publishers(active_only=True)

        assert len(publishers) > 0
        for publisher in publishers:
            assert publisher.is_active is True

    def test_get_publisher(self, manager, db):
        """测试获取单个出版社"""
        manager.init_publishers()

        publisher = Publisher.query.first()
        assert publisher is not None

        result = manager.get_publisher(publisher.id)

        assert result is not None
        assert result.id == publisher.id

    def test_update_publisher_status(self, manager, db):
        """测试更新出版社状态"""
        manager.init_publishers()

        publisher = Publisher.query.first()
        assert publisher is not None

        result = manager.update_publisher_status(publisher.id, False)

        assert result is True
        assert db.session.get(Publisher, publisher.id).is_active is False

        result = manager.update_publisher_status(publisher.id, True)

        assert result is True
        assert db.session.get(Publisher, publisher.id).is_active is True
