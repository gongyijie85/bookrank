"""
PRH 官方 API 爬虫（PrhApiCrawler）单元测试

覆盖（工单 #86）：
- 爬虫注册表注册
- API key 缺失快速失败
- 14 天增量窗口请求参数构造（成对 onSaleFrom/onSaleTo，实证：成对才生效）
- division 黑名单过滤（加拿大系 91/29/9B/9E/97 与 Audio 22，保留 MIT Press 等代发）
- workId 去重（HC > TR > 其余，同档取 onsale 最新）
- 字段映射（onsale/price USD 优先/BISAC 分类/封面/source_url）
- 分页、空响应、首页请求失败、max_books 上限

所有 HTTP 请求通过 mock session 注入构造响应，测试环境禁止真实网络请求。
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """阻止所有爬虫在测试时实际请求网络"""
    import app.services.publisher_crawler.base_crawler as bc_mod

    monkeypatch.setattr(bc_mod.BaseCrawler, '_init_robots_parser', lambda self: None)
    monkeypatch.setattr(bc_mod.time, 'sleep', lambda x: None)


from app.services.publisher_crawler import get_all_crawlers, get_crawler_class
from app.services.publisher_crawler.base_crawler import CrawlerConfig
from app.services.publisher_crawler.prh_api import PrhApiCrawler


def _title(
    isbn: int = 9780000000001,
    title: str = 'Test Book',
    author: str = 'Test Author',
    onsale: str = '2026-07-21',
    division_code: str = '62',
    division_desc: str = 'Random House',
    format_code: str = 'HC',
    work_id: int = 100,
    pages: int = 300,
    price: list[dict] | None = None,
    subjects: list[dict] | None = None,
    language: str = 'E',
    seo_url: str = '/books/100/test-book/9780000000001',
) -> dict:
    """构造一条符合 PRH Enhanced API v2 真实信封的 title 记录"""
    return {
        'isbn': isbn,
        'title': title,
        'author': author,
        'onsale': onsale,
        'price': price if price is not None else [{'amount': 28.0, 'currencyCode': 'USD', 'pricingType': None}],
        'seoFriendlyUrl': seo_url,
        'format': {'code': format_code, 'description': 'Hardcover'},
        'division': {'code': division_code, 'description': division_desc},
        'imprint': {'code': 'XX', 'description': 'Some Imprint'},
        'pages': pages,
        'subjects': subjects if subjects is not None else [],
        'language': language,
        'workId': work_id,
    }


def _response(titles: list[dict], record_count: int | None = None) -> MagicMock:
    """构造 API 响应（顶层信封 + data.titles）"""
    body = {
        'status': 'ok',
        'recordCount': record_count if record_count is not None else len(titles),
        'data': {'titles': titles, '_links': []},
        'error': None,
    }
    resp = MagicMock(status_code=200, content=b'{}')
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def _crawler(responses) -> tuple[PrhApiCrawler, MagicMock]:
    """构造爬虫并注入 mock session，返回 (crawler, mock_request)"""
    crawler = PrhApiCrawler(CrawlerConfig(api_key='test-key'))
    mock_request = MagicMock(side_effect=responses)
    crawler._session.request = mock_request
    return crawler, mock_request


class TestRegistry:
    def test_registered_in_crawler_registry(self):
        assert get_crawler_class('PrhApiCrawler') is PrhApiCrawler
        assert 'PrhApiCrawler' in get_all_crawlers()

    def test_publisher_metadata(self):
        crawler, _ = _crawler([_response([])])
        assert crawler.PUBLISHER_NAME_EN == 'Penguin Random House'
        assert crawler.CRAWLER_CLASS_NAME == 'PrhApiCrawler'


class TestApiKey:
    def test_missing_api_key_fails_fast(self):
        with pytest.raises(ValueError, match='PRH_API_KEY'):
            PrhApiCrawler()

    def test_missing_api_key_in_config_fails_fast(self):
        with pytest.raises(ValueError, match='PRH_API_KEY'):
            PrhApiCrawler(CrawlerConfig())


class TestRequestParams:
    def test_incremental_window_params_are_paired(self):
        crawler, mock_request = _crawler([_response([_title()])])
        list(crawler.get_new_books())

        assert mock_request.call_count == 1
        url = (
            mock_request.call_args.args[1]
            if len(mock_request.call_args.args) > 1
            else mock_request.call_args.kwargs.get('url')
        )
        params = mock_request.call_args.kwargs['params']

        assert 'api.penguinrandomhouse.com' in url
        assert '/resources/v2/title/domains/PRH.US/titles' in url
        # 实证修正：onSaleFrom 单独使用不生效，必须与 onSaleTo 成对
        assert 'onSaleFrom' in params
        assert 'onSaleTo' in params
        date_from = datetime.strptime(params['onSaleFrom'], '%m/%d/%Y').date()
        date_to = datetime.strptime(params['onSaleTo'], '%m/%d/%Y').date()
        assert (date_to - date_from).days == PrhApiCrawler.INCREMENTAL_WINDOW_DAYS
        assert date_to == date.today()
        assert params['sort'] == 'onsale'
        assert params['dir'] == 'desc'
        assert params['api_key'] == 'test-key'

    def test_does_not_use_show_new_releases_in_incremental_mode(self):
        crawler, mock_request = _crawler([_response([_title()])])
        list(crawler.get_new_books())
        params = mock_request.call_args.kwargs['params']
        assert 'showNewReleases' not in params


class TestDivisionFilter:
    @pytest.mark.parametrize('code', ['91', '29', '9B', '9E', '97', '22'])
    def test_excludes_canadian_and_audio_divisions(self, code):
        crawler, _ = _crawler([_response([_title(division_code=code)])])
        assert list(crawler.get_new_books()) == []

    def test_keeps_distributed_publishers_like_mit_press(self):
        crawler, _ = _crawler([_response([_title(division_code='H1', division_desc='MIT Press')])])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].title == 'Test Book'

    def test_keeps_regular_prh_divisions(self):
        crawler, _ = _crawler([_response([_title(division_code='62', division_desc='Random House')])])
        assert len(list(crawler.get_new_books())) == 1


class TestWorkIdDedup:
    def test_prefers_hardcover_over_paperback_and_ebook(self):
        titles = [
            _title(isbn=9780000000001, format_code='EB', work_id=100, onsale='2026-07-21'),
            _title(isbn=9780000000002, format_code='TR', work_id=100, onsale='2026-07-21'),
            _title(isbn=9780000000003, format_code='HC', work_id=100, onsale='2026-07-21'),
        ]
        crawler, _ = _crawler([_response(titles)])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].isbn13 == '9780000000003'

    def test_prefers_trade_paperback_over_other_formats(self):
        titles = [
            _title(isbn=9780000000001, format_code='EB', work_id=100),
            _title(isbn=9780000000002, format_code='TR', work_id=100),
        ]
        crawler, _ = _crawler([_response(titles)])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].isbn13 == '9780000000002'

    def test_same_priority_keeps_latest_onsale(self):
        titles = [
            _title(isbn=9780000000001, format_code='HC', work_id=100, onsale='2026-07-01'),
            _title(isbn=9780000000002, format_code='HC', work_id=100, onsale='2026-07-21'),
        ]
        crawler, _ = _crawler([_response(titles)])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].isbn13 == '9780000000002'

    def test_dedup_across_pages(self):
        page1 = _response([_title(isbn=9780000000001, format_code='TR', work_id=100)], record_count=2)
        page2 = _response([_title(isbn=9780000000002, format_code='HC', work_id=100)], record_count=2)
        crawler, _ = _crawler([page1, page2])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].isbn13 == '9780000000002'

    def test_distinct_work_ids_all_kept(self):
        titles = [
            _title(isbn=9780000000001, work_id=100, title='Book A'),
            _title(isbn=9780000000002, work_id=101, title='Book B'),
        ]
        crawler, _ = _crawler([_response(titles)])
        books = list(crawler.get_new_books())
        assert {b.title for b in books} == {'Book A', 'Book B'}

    def test_records_without_work_id_are_kept_not_dropped(self):
        """无 workId 的记录不参与去重，不应被静默丢弃（审查反馈）"""
        title = _title(isbn=9780000000001, work_id=0, title='Orphan Book')
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())
        assert len(books) == 1
        assert books[0].title == 'Orphan Book'


class TestFieldMapping:
    def test_full_field_mapping(self):
        title = _title(
            isbn=9780143130321,
            title='Wolfsbane',
            author='Andrea Robertson',
            onsale='2026-07-21',
            pages=336,
            price=[
                {'amount': 19.99, 'currencyCode': 'CAD', 'pricingType': None},
                {'amount': 13.99, 'currencyCode': 'USD', 'pricingType': None},
            ],
            subjects=[
                {'code': 'YAF019000', 'description': 'Young Adult Fiction - Fantasy - General'},
            ],
            seo_url='/books/307257/wolfsbane-by-andrea-robertson/9780143130321',
        )
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())

        assert len(books) == 1
        book = books[0]
        assert book.title == 'Wolfsbane'
        assert book.author == 'Andrea Robertson'
        assert book.isbn13 == '9780143130321'
        assert book.publication_date == date(2026, 7, 21)
        assert book.page_count == 336
        assert book.price == '13.99'  # USD 优先，忽略 CAD
        assert book.category == 'Young Adult'  # BISAC 首个可映射项
        assert book.cover_url == 'https://images.penguinrandomhouse.com/cover/9780143130321'
        assert (
            book.source_url
            == 'https://www.penguinrandomhouse.com/books/307257/wolfsbane-by-andrea-robertson/9780143130321'
        )
        assert book.language == 'en'

    def test_price_falls_back_to_first_when_no_usd(self):
        title = _title(price=[{'amount': 19.99, 'currencyCode': 'CAD', 'pricingType': None}])
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())
        assert books[0].price == '19.99'

    def test_price_none_when_missing(self):
        title = _title(price=[])
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())
        assert books[0].price is None

    @pytest.mark.parametrize(
        ('bisac', 'expected'),
        [
            ('Fiction - Thrillers - Suspense', 'Thriller'),
            ('Fiction - Mystery & Detective - General', 'Mystery'),
            ('Fiction - Romance - General', 'Romance'),
            ('Fiction - Science Fiction - General', 'Science Fiction'),
            ('Fiction - Fantasy - General', 'Fantasy'),
            ('Biography & Autobiography - Literary', 'Biography'),
            ('History - United States - 20th Century', 'History'),
            ('Business & Economics - Management', 'Business'),
            ('Self-Help - Personal Growth - General', 'Self-Help'),
            ('Juvenile Fiction - Animals - Bears', 'Children'),
            ('Fiction - Literary', 'Fiction'),
            ('True Crime - General', 'Nonfiction'),
        ],
    )
    def test_bisac_category_mapping(self, bisac, expected):
        title = _title(subjects=[{'code': 'XXX000000', 'description': bisac}])
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())
        assert books[0].category == expected

    def test_category_none_when_no_mappable_subject(self):
        title = _title(subjects=[{'code': 'XXX000000', 'description': 'Poetry - General'}])
        crawler, _ = _crawler([_response([title])])
        books = list(crawler.get_new_books())
        assert books[0].category is None

    def test_unparseable_onsale_skips_book(self):
        title = _title(onsale='not-a-date')
        crawler, _ = _crawler([_response([title])])
        assert list(crawler.get_new_books()) == []


class TestResponses:
    def test_empty_titles_yields_nothing(self):
        crawler, _ = _crawler([_response([])])
        assert list(crawler.get_new_books()) == []

    def test_error_status_response_raises_on_first_page(self):
        """首屏 status=error 业务错误信封：抛异常走熔断，不静默产出空结果（审查反馈）"""
        resp = MagicMock(status_code=200, content=b'{}')
        resp.json.return_value = {
            'status': 'error',
            'recordCount': 0,
            'data': {'titles': [], '_links': []},
            'error': {'message': 'invalid api key'},
        }
        resp.raise_for_status = MagicMock()
        crawler, _ = _crawler([resp])
        with pytest.raises(RuntimeError):
            list(crawler.get_new_books())

    def test_error_status_mid_pagination_returns_partial(self):
        """翻页中途遇 status=error：返回已取部分（宁可漏报不误报）"""
        page1 = _response([_title(isbn=9780000000001, work_id=100)], record_count=5)
        resp = MagicMock(status_code=200, content=b'{}')
        resp.json.return_value = {
            'status': 'error',
            'recordCount': 5,
            'data': {'titles': [], '_links': []},
            'error': {'message': 'server error'},
        }
        resp.raise_for_status = MagicMock()
        crawler = PrhApiCrawler(CrawlerConfig(api_key='test-key'))
        crawler._session.request = MagicMock(side_effect=[page1, resp])
        books = list(crawler.get_new_books())
        assert len(books) == 1

    def test_first_page_failure_raises(self):
        crawler = PrhApiCrawler(CrawlerConfig(api_key='test-key'))
        crawler._session.request = MagicMock(return_value=None)
        with pytest.raises(RuntimeError):
            list(crawler.get_new_books())

    def test_later_page_failure_returns_partial(self):
        page1 = _response([_title(isbn=9780000000001, work_id=100)], record_count=5)
        crawler = PrhApiCrawler(CrawlerConfig(api_key='test-key'))
        crawler._session.request = MagicMock(side_effect=[page1, None])
        books = list(crawler.get_new_books())
        assert len(books) == 1

    def test_pagination_follows_record_count(self):
        page1 = _response([_title(isbn=9780000000001, work_id=100)], record_count=2)
        page2 = _response([_title(isbn=9780000000002, work_id=101)], record_count=2)
        crawler, mock_request = _crawler([page1, page2])
        books = list(crawler.get_new_books())
        assert len(books) == 2
        assert mock_request.call_count == 2
        second_params = mock_request.call_args_list[1].kwargs['params']
        assert second_params['start'] == 1

    def test_max_books_cap(self):
        titles = [_title(isbn=9780000000000 + i, work_id=100 + i, title=f'Book {i}') for i in range(5)]
        crawler, _ = _crawler([_response(titles, record_count=5)])
        books = list(crawler.get_new_books(max_books=3))
        assert len(books) == 3
