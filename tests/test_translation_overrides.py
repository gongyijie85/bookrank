"""翻译覆盖共享助手测试（utils/translation_overrides + 模型序列化接线）。"""

from __future__ import annotations

from app.models.book import Book
from app.models.schemas import AwardBook
from app.utils.translation_overrides import TRANSLATION_OVERRIDES, apply_translation_overrides


class TestApplyTranslationOverrides:
    """纯函数行为：命中覆盖、不新增键、未命中不动、空值不覆盖"""

    def test_overrides_existing_key_by_isbn13(self):
        data = {'isbn13': '9780316556323', 'title_zh': '机翻错误'}
        apply_translation_overrides(data)
        assert data['title_zh'] == '喀耳刻'

    def test_overrides_by_isbn10_when_isbn13_missing(self):
        data = {'isbn10': '9780316556323', 'title_zh': '机翻错误'}
        apply_translation_overrides(data)
        assert data['title_zh'] == '喀耳刻'

    def test_does_not_introduce_new_keys(self):
        data = {'isbn13': '9780316556323'}
        apply_translation_overrides(data)
        assert 'title_zh' not in data

    def test_no_isbn_leaves_data_untouched(self):
        data = {'title_zh': '原文'}
        apply_translation_overrides(data)
        assert data['title_zh'] == '原文'

    def test_unknown_isbn_leaves_data_untouched(self):
        data = {'isbn13': '9780000000002', 'title_zh': '原文'}
        apply_translation_overrides(data)
        assert data['title_zh'] == '原文'

    def test_falsy_override_value_is_skipped(self):
        key = '9780316556323'
        original = TRANSLATION_OVERRIDES[key]
        TRANSLATION_OVERRIDES[key] = {'title_zh': ''}
        try:
            data = {'isbn13': key, 'title_zh': '原文'}
            apply_translation_overrides(data)
            assert data['title_zh'] == '原文'
        finally:
            TRANSLATION_OVERRIDES[key] = original


def _make_book(isbn13: str) -> Book:
    return Book(
        id=isbn13,
        title='CIRCE',
        author='Madeline Miller',
        publisher='Little, Brown',
        cover='',
        list_name='hardcover-fiction',
        category_id='c1',
        category_name='Fiction',
        rank=1,
        weeks_on_list=1,
        rank_last_week='无',
        published_date='2026-08-01',
        description='desc',
        details='details',
        publication_dt='2026-08-01',
        page_count='300',
        language='en',
        buy_links=[],
        isbn13=isbn13,
        isbn10='',
        price='0',
        title_zh='机翻错误',
    )


class TestModelWiring:
    """模型序列化接线：Book 与 AwardBook 的 to_dict 走共享助手"""

    def test_book_to_dict_applies_override(self):
        data = _make_book('9780316556323').to_dict()
        assert data['title_zh'] == '喀耳刻'

    def test_book_to_dict_without_override_untouched(self):
        data = _make_book('9780000000002').to_dict()
        assert data['title_zh'] == '机翻错误'

    def test_award_book_to_dict_applies_override(self, db):
        book = AwardBook(
            award_id=1,
            year=2026,
            title='CIRCE',
            title_zh='机翻错误',
            author='Madeline Miller',
            isbn13='9780316556323',
        )
        db.session.add(book)
        db.session.commit()

        data = book.to_dict(include_zh=True)
        assert data['title_zh'] == '喀耳刻'
