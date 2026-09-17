"""详情页「详细信息」缺失的**根因侧**回归锁。

现象：`/book/<i>` 的「详细信息」标签整块消失，只剩「图书简介」。
例：https://bookrank-ckml.onrender.com/book/4?category=trade-fiction-paperback

根因是三段叠加，缺任何一段都不复现：

1. **占位串被当成数据落库。** 抓取侧拿不到 description 时写回
   `'No detailed description available.'` 这类串，`Book.from_api_response`
   又把它当默认值写进 `details`（生产实测：整个分类 12 本书的 `details`
   清一色是这个串）。
2. **「有值即已补全」把自愈路径封死。** `book_detail_service` 的 `needs_details`
   是 `book.get('details') and not 占位串`，占位串让前半段为真、后半段为假，
   于是这本书永远不会再被补齐。
3. **详情只有 Google Books 一个数据源，而它对独立出版与新书常常没有条目。**
   9798890920461 在 Google Books 无记录，在 Open Library 的 work 级记录里却有
   582 字符完整简介 —— 但那条路径从没被调用过。

渲染侧的契约（占位串不得当正文渲染）已由 `test_card_desc_and_details_render.py`
锁住；本文件锁的是**取值侧**：占位串不得落库，且缺详情时要真的去补。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from app.models.book import Book
from app.services.book_detail_service import enrich_book_details
from app.utils.api_helpers import is_placeholder_text, strip_placeholder

#: 生产上 details 字段里存的占位串（实测取证）
PROD_PLACEHOLDER = 'No detailed description available.'

#: 仿真 Open Library work 级简介（真实取值是 582 字符，这里留足够长度）
WORK_DESCRIPTION = (
    'Betty Lou Dearden has been a member of the Ogden Quilter\u2019s Association for more than '
    'twenty years when it\u2019s announced that the biggest quilting competition in the country '
    'is coming to her small Utah town, and the women welcome two young gay men to their group.'
)
ISBN = '9798890920461'


def _nyt_book_data(**overrides) -> dict:
    data = {
        'title': 'STITCHED',
        'author': 'Eli McCann',
        'publisher': 'Torrey House',
        'primary_isbn13': ISBN,
        'primary_isbn10': '',
        'rank': 5,
        'weeks_on_list': 1,
        'rank_last_week': 0,
        'description': 'A short NYT summary.',
        'buy_links': [],
    }
    data.update(overrides)
    return data


def _make_book(**overrides) -> Book:
    """构造一本走详情页的书（字段与 `Book` dataclass 对齐）。"""
    defaults = {
        'id': ISBN,
        'title': 'STITCHED',
        'author': 'Eli McCann',
        'publisher': 'Torrey House',
        'cover': '',
        'list_name': 'Paperback Trade Fiction',
        'category_id': 'hardcover-fiction',
        'category_name': 'Paperback Trade Fiction',
        'rank': 1,
        'weeks_on_list': 1,
        'rank_last_week': '0',
        'published_date': '2026-09-27',
        'description': 'A short NYT summary.',
        'details': PROD_PLACEHOLDER,
        'publication_dt': 'Unknown',
        'page_count': 'Unknown',
        'language': 'Unknown',
        'buy_links': [],
        'isbn13': ISBN,
        'isbn10': '',
        'price': '未知',
        'title_zh': None,
        'description_zh': None,
        'details_zh': None,
    }
    defaults.update(overrides)
    return Book(**defaults)


class TestPlaceholderTextPredicate:
    """占位串判定：只认「没有内容」的串，不吃真实详情。"""

    def test_known_placeholders_are_recognised(self):
        for text in (PROD_PLACEHOLDER, 'No summary available.', 'No description available.', '暂无详细介绍'):
            assert is_placeholder_text(text) is True, text

    def test_real_details_are_not_mistaken_for_placeholders(self):
        assert is_placeholder_text(WORK_DESCRIPTION) is False
        assert is_placeholder_text('最初由Viking Penguin于2014年出版。') is False

    def test_strip_placeholder_normalises_to_empty_and_trims(self):
        assert strip_placeholder(PROD_PLACEHOLDER) == ''
        assert strip_placeholder('  Stitched  ') == 'Stitched'
        assert strip_placeholder(None) == ''
        assert strip_placeholder(12345) == ''


class TestPlaceholderIsNotPersisted:
    """第 1 段根因：写入边界不得把占位串当数据落库。"""

    @staticmethod
    def _from_api(supplement: dict, **book_overrides) -> Book:
        return Book.from_api_response(
            book_data=_nyt_book_data(**book_overrides),
            category_id='trade-fiction-paperback',
            category_name='平装小说',
            list_name='Paperback Trade Fiction',
            published_date='2026-09-27',
            supplement=supplement,
        )

    def test_empty_supplement_does_not_store_details_placeholder(self):
        book = self._from_api({})
        assert book.details == '', '没有详情时必须留空，而不是写入「没有详情」的占位串'

    def test_upstream_placeholder_is_normalised_to_empty(self):
        book = self._from_api({'details': PROD_PLACEHOLDER}, description='No summary available.')
        assert book.details == ''
        assert book.description == ''

    def test_real_values_pass_through_untouched(self):
        book = self._from_api({'details': WORK_DESCRIPTION}, description='A short NYT summary.')
        assert book.details == WORK_DESCRIPTION
        assert book.description == 'A short NYT summary.'


class TestEnrichBookDetailsFallback:
    """第 3 段根因：Google Books 无数据时必须真的去补第二个源。"""

    @staticmethod
    def _patch_open_library(text: str):
        return patch(
            'app.services.book_detail_service.get_or_create_open_library_client',
            return_value=MagicMock(fetch_work_description_by_isbn=MagicMock(return_value=text)),
        )

    def test_fallback_fills_details_when_google_books_has_nothing(self):
        book = {'details': PROD_PLACEHOLDER}
        with (
            patch('app.services.book_detail_service.fetch_google_books_details'),
            self._patch_open_library(WORK_DESCRIPTION),
        ):
            enrich_book_details(book, ISBN)

        assert book['details'] == WORK_DESCRIPTION, 'Google Books 没有详情时应回退到 Open Library'

    def test_details_is_cleared_when_no_source_has_anything(self):
        """两个源都没有内容时留空 —— 绝不能让占位串活着走出富化入口。"""
        book = {'details': PROD_PLACEHOLDER}
        with (
            patch('app.services.book_detail_service.fetch_google_books_details'),
            self._patch_open_library(''),
        ):
            enrich_book_details(book, ISBN)

        assert book['details'] == ''

    def test_google_books_result_wins_and_open_library_is_not_queried(self):
        def _fill(book: dict, isbn: str) -> None:
            book['details'] = WORK_DESCRIPTION

        book: dict = {'details': PROD_PLACEHOLDER}
        with (
            patch('app.services.book_detail_service.fetch_google_books_details', side_effect=_fill),
            self._patch_open_library('SHOULD NOT BE USED') as mock_get_client,
        ):
            enrich_book_details(book, ISBN)

        assert book['details'] == WORK_DESCRIPTION
        mock_get_client.assert_not_called()

    def test_open_library_failure_does_not_break_the_page(self):
        """兜底源抛异常不能把详情页带崩：没有详情仍是一张可用页面。"""
        book = {'details': PROD_PLACEHOLDER}
        with (
            patch('app.services.book_detail_service.fetch_google_books_details'),
            patch(
                'app.services.book_detail_service.get_or_create_open_library_client',
                side_effect=RuntimeError('open library down'),
            ),
        ):
            enrich_book_details(book, ISBN)

        assert book['details'] == ''


class TestDetailPageShowsDetailsFromFallback:
    """端到端：`/book/0` 必须渲染出带正文的「详细信息」标签（用户可见症状）。"""

    @pytest.fixture
    def book_service(self, app):
        """临时注册 book_service，测完无条件还原（同 test_card_desc_and_details_render）。"""
        original = app.extensions.get('book_service')
        try:

            def _register(books):
                svc = MagicMock()
                svc.get_books_by_category.return_value = books
                svc.get_cache_time.return_value = '2026-09-17'
                svc.get_latest_cache_time.return_value = '2026-09-17'
                app.extensions['book_service'] = svc

            yield _register
        finally:
            if original is None:
                app.extensions.pop('book_service', None)
            else:
                app.extensions['book_service'] = original

    @staticmethod
    def _get(client, open_library_text: str) -> str:
        with (
            patch('app.services.book_detail_service.fetch_google_books_details'),
            patch(
                'app.services.book_detail_service.get_or_create_open_library_client',
                return_value=MagicMock(fetch_work_description_by_isbn=MagicMock(return_value=open_library_text)),
            ),
            patch('app.routes.main.merge_or_translate_book'),
        ):
            response = client.get('/book/0?category=hardcover-fiction&lang=zh')
        assert response.status_code == 200
        return response.get_data(as_text=True)

    def test_details_tab_renders_the_fallback_content(self, client, book_service):
        book_service([_make_book()])

        soup = BeautifulSoup(self._get(client, WORK_DESCRIPTION), 'html.parser')

        assert soup.find(id='tab-details') is not None, '有详情时「详细信息」标签必须出现'
        panel = soup.find(id='panel-details')
        assert panel is not None
        panel_text = panel.get_text(' ', strip=True)
        assert WORK_DESCRIPTION[:60] in panel_text, '兜底取到的简介必须真的渲染到面板里'
        assert PROD_PLACEHOLDER not in panel_text, '占位串不得出现在页面上'

    def test_tab_still_disappears_when_no_source_has_details(self, client, book_service):
        """反向断言，证明上一条用例真的在测兜底而不是恒真。"""
        book_service([_make_book()])

        soup = BeautifulSoup(self._get(client, ''), 'html.parser')

        assert soup.find(id='tab-details') is None
