"""
扩展爬虫测试

覆盖 base_crawler, macmillan, open_library, google_books,
google_books_publisher 的生产活跃爬虫核心逻辑。
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """阻止所有爬虫在测试时实际请求网络"""
    import app.services.publisher_crawler.base_crawler as bc_mod

    monkeypatch.setattr(bc_mod.BaseCrawler, '_init_robots_parser', lambda self: None)
    monkeypatch.setattr(bc_mod.time, 'sleep', lambda x: None)

    _orig_create = bc_mod.BaseCrawler._create_session

    def _safe_session(self):
        s = _orig_create(self)
        _orig_req = s.request

        def _blocked_request(*a, **kw):
            raise bc_mod.requests.ConnectionError('测试环境禁止实际网络请求')

        s.request = _blocked_request
        s.get = lambda *a, **kw: _blocked_request(*a, **kw)
        return s

    monkeypatch.setattr(bc_mod.BaseCrawler, '_create_session', _safe_session)


from app.services.publisher_crawler.base_crawler import (
    BaseCrawler,
    BookInfo,
    CrawlerConfig,
    CrawlRequest,
    SimpleResponse,
)

# ---------- 辅助具体爬虫 ----------


class ConcreteCrawler(BaseCrawler):
    """用于测试 BaseCrawler 的具体子类"""

    PUBLISHER_NAME = '测试出版'
    PUBLISHER_NAME_EN = 'Test Publisher'
    PUBLISHER_WEBSITE = 'https://test.com'
    CRAWLER_CLASS_NAME = 'ConcreteCrawler'

    def _iter_new_books(self, request):
        yield BookInfo(title='X', author='Y')

    def get_book_details(self, book_url):
        return BookInfo(title='D', author='A')

    def get_categories(self):
        return [{'id': 'fiction', 'name': '小说'}]


# ---------- BaseCrawler ----------


class TestBaseCrawlerInit:
    def test_default_config(self):
        c = ConcreteCrawler()
        assert c.config.max_retries == 3
        assert c.config.timeout == 15

    def test_custom_config(self):
        cfg = CrawlerConfig(max_retries=5, timeout=20, max_pages=2)
        c = ConcreteCrawler(cfg)
        assert c.config.max_retries == 5
        assert c.config.timeout == 20

    def test_publisher_properties(self):
        c = ConcreteCrawler()
        assert c.PUBLISHER_NAME == '测试出版'
        assert c.PUBLISHER_WEBSITE == 'https://test.com'

    def test_context_manager(self):
        with ConcreteCrawler() as c:
            assert c is not None


class TestBaseCrawlerRequest:
    def _mock_session(self, c, status_code=200, text='OK'):
        mock_resp = MagicMock(status_code=status_code, text=text, content=b'OK')
        mock_resp.raise_for_status = MagicMock()
        c._session.request = MagicMock(return_value=mock_resp)
        return mock_resp

    def test_success(self):
        c = ConcreteCrawler()
        self._mock_session(c, 200, '<html>OK</html>')
        resp = c._make_request('https://test.com/page')
        assert resp is not None
        assert resp.status_code == 200

    def test_retry_on_429(self):
        c = ConcreteCrawler()
        r429 = MagicMock(status_code=429, text='rate limited')
        r200 = MagicMock(status_code=200, text='OK', content=b'OK')
        r200.raise_for_status = MagicMock()
        c._session.request = MagicMock(side_effect=[r429, r200])
        resp = c._make_request('https://test.com')
        assert resp is not None

    def test_returns_none_on_persistent_error(self):
        c = ConcreteCrawler()
        c._session.request = MagicMock(return_value=MagicMock(status_code=500, text='err'))
        resp = c._make_request('https://test.com')
        assert resp is None

    def test_returns_none_on_exception(self):
        c = ConcreteCrawler()
        c._session.request = MagicMock(side_effect=Exception('net'))
        resp = c._make_request('https://test.com')
        assert resp is None


class TestBaseCrawlerParsing:
    def test_parse_html(self):
        c = ConcreteCrawler()
        soup = c._parse_html('<html><body><p>Hello</p></body></html>')
        assert soup.find('p').get_text() == 'Hello'

    def test_clean_text(self):
        c = ConcreteCrawler()
        assert c._clean_text('  a\nb  ') == 'a b'

    def test_truncate_description_short(self):
        c = ConcreteCrawler()
        assert c._truncate_description('short') == 'short'

    def test_truncate_description_long(self):
        c = ConcreteCrawler()
        long = 'word ' * 600
        result = c._truncate_description(long)
        assert len(result) < len(long)

    def test_truncate_description_none(self):
        c = ConcreteCrawler()
        assert c._truncate_description(None) is None

    def test_parse_date_valid(self):
        c = ConcreteCrawler()
        d = c._parse_date('January 15, 2025')
        assert d is not None
        assert d.year == 2025

    def test_parse_date_none(self):
        c = ConcreteCrawler()
        assert c._parse_date(None) is None

    def test_parse_date_invalid(self):
        c = ConcreteCrawler()
        assert c._parse_date('not a date') is None

    def test_parse_price_valid(self):
        c = ConcreteCrawler()
        assert c._parse_price('$29.99') == '$29.99'

    def test_parse_price_none(self):
        c = ConcreteCrawler()
        assert c._parse_price(None) is None

    def test_parse_price_no_number(self):
        c = ConcreteCrawler()
        assert c._parse_price('no number') == 'no number'


class TestBaseCrawlerExtractIsbn:
    def test_isbn13(self):
        c = ConcreteCrawler()
        isbn13, isbn10 = c._extract_isbn('9781234567890')
        assert isbn13 == '9781234567890'

    def test_isbn10(self):
        c = ConcreteCrawler()
        isbn13, isbn10 = c._extract_isbn('1234567890')
        assert isbn10 == '1234567890'

    def test_both(self):
        c = ConcreteCrawler()
        isbn13, isbn10 = c._extract_isbn('9781234567890 123456789X')
        assert isbn13 == '9781234567890'

    def test_none(self):
        c = ConcreteCrawler()
        isbn13, isbn10 = c._extract_isbn('')
        assert isbn13 is None


class TestSimpleResponse:
    def test_json(self):
        r = SimpleResponse({'key': 'val'}, 200)
        assert r.json() == {'key': 'val'}
        assert r.status_code == 200


class TestBookInfo:
    def test_defaults(self):
        b = BookInfo(title='T', author='A')
        assert b.isbn13 is None
        assert b.buy_links == []
        assert b.source_url is None

    def test_to_dict(self):
        b = BookInfo(title='T', author='A', isbn13='978123', publication_date=date(2025, 1, 15))
        d = b.to_dict()
        assert d['title'] == 'T'
        assert d['publication_date'] == '2025-01-15'

    def test_to_dict_no_date(self):
        b = BookInfo(title='T', author='A')
        d = b.to_dict()
        assert d['publication_date'] is None


class TestCrawlerConfig:
    def test_defaults(self):
        cfg = CrawlerConfig()
        assert cfg.max_retries == 3
        assert cfg.timeout == 15
        assert cfg.request_delay == 1.0
        assert cfg.max_pages == 10

    def test_custom(self):
        cfg = CrawlerConfig(max_retries=10, timeout=30)
        assert cfg.max_retries == 10
        assert cfg.timeout == 30


# ---------- Macmillan ----------


class TestMacmillanCrawler:
    def _make(self):
        from app.services.publisher_crawler.macmillan import MacmillanCrawler

        return MacmillanCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '麦克米伦'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) > 0

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
            assert books == []

    def test_get_new_books_empty_page(self):
        c = self._make()
        resp = MagicMock(status_code=200, text='<html><body></body></html>')
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
            assert isinstance(books, list)

    def test_get_book_details_no_response(self):
        c = self._make()
        c._session.get = MagicMock(side_effect=Exception('net'))
        assert c.get_book_details('https://macmillan.com/book/1') is None

    def test_get_book_details_success(self):
        c = self._make()
        data = {
            'volumeInfo': {
                'title': 'Macmillan Book',
                'authors': ['Author'],
                'description': 'Desc',
                'industryIdentifiers': [{'type': 'ISBN_13', 'identifier': '9781234567890'}],
                'imageLinks': {'thumbnail': 'http://img.jpg'},
                'categories': ['Fiction'],
                'publishedDate': '2025-01-01',
                'pageCount': 300,
                'language': 'en',
            },
        }
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        c._session.get = MagicMock(return_value=mock_resp)
        book = c.get_book_details('9781234567890')
        assert book is not None

    def test_sitemap_stops_after_google_rate_limit(self):
        c = self._make()

        def rate_limited_lookup(_isbn):
            c._google_rate_limited = True
            return None

        with (
            patch.object(c, '_query_imprint', return_value=iter(())),
            patch.object(c, '_fetch_sitemap_isbns', return_value=['1', '2', '3']),
            patch.object(c, '_lookup_isbn', side_effect=rate_limited_lookup) as lookup,
        ):
            assert list(c.get_new_books(CrawlRequest(max_books=1)).books) == []

        lookup.assert_called_once_with('1')


# ---------- OpenLibrary ----------


class TestOpenLibraryCrawler:
    def _make(self):
        from app.services.publisher_crawler.open_library import OpenLibraryCrawler

        return OpenLibraryCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == 'Open Library'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) > 0

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
            assert isinstance(books, list)

    def test_get_new_books_success(self):
        c = self._make()
        data = {
            'works': [
                {
                    'title': 'OL Book',
                    'authors': [{'name': 'Author'}],
                    'key': '/works/OL1W',
                    'availability': {'isbn': '9781234567890'},
                    'cover_id': 12345,
                    'first_publish_year': 2024,
                    'subject': ['Fiction'],
                }
            ],
        }
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = data
        mock_resp.raise_for_status = MagicMock()
        c._session.get = MagicMock(return_value=mock_resp)
        books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
        assert len(books) >= 1

    def test_get_book_details_no_response(self):
        c = self._make()
        c._session.request = MagicMock(side_effect=Exception('net'))
        assert c.get_book_details('/works/OL1W') is None

    def test_get_book_details_success(self):
        c = self._make()
        data = {
            'title': 'Detail Book',
            'authors': [{'author': {'key': '/authors/OL1A'}}],
            'description': {'value': 'A great book'},
            'covers': [999],
        }
        author_data = {'name': 'Author Name'}
        mock_resp1 = MagicMock(status_code=200)
        mock_resp1.json.return_value = data
        mock_resp1.raise_for_status = MagicMock()
        mock_resp2 = MagicMock(status_code=200)
        mock_resp2.json.return_value = author_data
        mock_resp2.raise_for_status = MagicMock()
        c._session.request = MagicMock(side_effect=[mock_resp1, mock_resp2])
        book = c.get_book_details('/works/OL1W')
        assert book is not None


# ---------- GoogleBooks ----------


class TestGoogleBooksCrawler:
    def _make(self, api_key=None):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler

        cfg = CrawlerConfig(api_key=api_key) if api_key else CrawlerConfig()
        return GoogleBooksCrawler(cfg)

    def test_init_with_key(self):
        c = self._make('test_key')
        assert c._api_key == 'test_key'

    def test_init_without_key(self):
        c = self._make()
        assert c._api_key is None

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) > 0

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
            assert isinstance(books, list)

    def test_get_new_books_success(self):
        c = self._make()
        recent_date = (date.today() - timedelta(days=10)).isoformat()
        data = {
            'items': [
                {
                    'volumeInfo': {
                        'title': 'GB Book',
                        'authors': ['Author'],
                        'description': 'Desc',
                        'industryIdentifiers': [
                            {'type': 'ISBN_13', 'identifier': '9781234567890'},
                        ],
                        'imageLinks': {'thumbnail': 'http://img.jpg'},
                        'categories': ['Fiction'],
                        'publishedDate': recent_date,
                        'pageCount': 300,
                        'language': 'en',
                    },
                    'saleInfo': {'listPrice': {'amount': 29.99}},
                }
            ],
            'totalItems': 1,
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        c._session.get = MagicMock(return_value=resp)
        books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
        assert len(books) >= 1

    def test_get_book_details_no_response(self):
        c = self._make()
        c._session.get = MagicMock(side_effect=Exception('net'))
        assert c.get_book_details('9781234567890') is None

    def test_get_book_details_success(self):
        c = self._make()
        item = {
            'volumeInfo': {
                'title': 'Detail Book',
                'authors': ['Author'],
            },
        }
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = item
        mock_resp.raise_for_status = MagicMock()
        c._session.get = MagicMock(return_value=mock_resp)
        book = c.get_book_details('9781234567890')
        assert book is not None


# ---------- GoogleBooksPublisher ----------


class TestGoogleBooksPublisherCrawler:
    def _make(self, api_key=None):
        from app.services.publisher_crawler.google_books_publisher import GoogleBooksPublisherCrawler

        cfg = CrawlerConfig(api_key=api_key) if api_key else CrawlerConfig()
        return GoogleBooksPublisherCrawler(cfg)

    def test_init(self):
        c = self._make('test_key')
        assert c._api_key == 'test_key'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) > 0

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(CrawlRequest(max_books=1)).books)
            assert isinstance(books, list)
