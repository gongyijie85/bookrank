"""分类清洗模块测试（候选 #3）

scan / apply_cleanup 的扫描、dry_run 预览与批量写入语义。
"""

import pytest

from app.models.new_book import NewBook, Publisher
from app.services.category_cleanup_service import apply_cleanup, scan


@pytest.fixture
def seeded(db):
    pub = Publisher(name='测试社', name_en='Test Pub', crawler_class='TestCrawler')
    db.session.add(pub)
    db.session.flush()
    db.session.add_all(
        [
            NewBook(publisher_id=pub.id, title='脏分类', author='A', category='Fiction learn more'),
            NewBook(publisher_id=pub.id, title='英文分类', author='A', category='Fiction'),
            NewBook(publisher_id=pub.id, title='干净分类', author='A', category='小说'),
            NewBook(publisher_id=pub.id, title='无分类', author='A', category=None),
        ]
    )
    db.session.commit()
    return pub


class TestScan:
    def test_scan_finds_marketing_and_english_categories(self, db, seeded):
        result = scan()

        assert result.total_checked == 3  # category 为 None 的不扫描
        titles = {item.title for item in result.invalid}
        assert titles == {'脏分类', '英文分类'}

    def test_scan_maps_english_to_chinese(self, db, seeded):
        result = scan()

        fiction = next(item for item in result.invalid if item.title == '英文分类')
        assert fiction.new_category == '小说'


class TestApplyCleanup:
    def test_dry_run_does_not_write(self, db, seeded):
        result = apply_cleanup(dry_run=True)

        assert result.invalid_found == 2
        assert result.updated == 0
        assert NewBook.query.filter_by(category='小说').count() == 1  # 只有原有的干净分类

    def test_apply_writes_and_counts(self, db, seeded):
        result = apply_cleanup(dry_run=False)

        assert result.invalid_found == 2
        assert result.updated == 2
        refreshed = {b.title: b.category for b in NewBook.query.all()}
        assert refreshed['脏分类'] is None  # learn more → 清洗为 None
        assert refreshed['英文分类'] == '小说'
