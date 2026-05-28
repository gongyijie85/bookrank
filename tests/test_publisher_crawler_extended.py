"""
扩展爬虫测试

覆盖 base_crawler, hachette, macmillan, harpercollins, open_library,
google_books, google_books_publisher, penguin_random_house, simon_schuster,
rss_crawler, mixed_crawl4ai_crawler 的核心逻辑。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup


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
    SimpleResponse,
)

# ---------- 辅助具体爬虫 ----------


class ConcreteCrawler(BaseCrawler):
    """用于测试 BaseCrawler 的具体子类"""

    PUBLISHER_NAME = '测试出版'
    PUBLISHER_NAME_EN = 'Test Publisher'
    PUBLISHER_WEBSITE = 'https://test.com'
    CRAWLER_CLASS_NAME = 'ConcreteCrawler'

    def get_new_books(self, category=None, max_books=100):
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


# ---------- Hachette ----------


class TestHachetteCrawler:
    def _make(self):
        from app.services.publisher_crawler.hachette import HachetteCrawler

        return HachetteCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '阿歇特'
        assert c.PUBLISHER_NAME_EN == 'Hachette Book Group'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) >= 10
        assert any(cat['id'] == 'fiction' for cat in cats)

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(max_books=1))
            assert books == []

    def test_get_new_books_empty_page(self):
        c = self._make()
        resp = MagicMock(status_code=200, text='<html><body></body></html>')
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=1))
            assert books == []

    def test_get_new_books_with_links(self):
        c = self._make()
        html = """
        <html><body>
        <div role="tabpanel" aria-label="New Releases">
            <a href="/titles/author/title/9781234567890/">
                <img alt="Book Title" src="/cover.jpg"/>
            </a>
        </div>
        </body></html>
        """
        resp = MagicMock(status_code=200, text=html)
        detail_resp = MagicMock(status_code=200, text='<html><body><p>Desc</p></body></html>')
        with patch.object(c, '_make_request', side_effect=[resp, detail_resp]):
            books = list(c.get_new_books(max_books=1))
            assert len(books) >= 1

    def test_get_book_details_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            assert c.get_book_details('https://hachette.com/titles/a/t/978123/') is None

    def test_get_book_details_success(self):
        c = self._make()
        html = '<html><body><p class="description">Great book</p><p>On Sale: January 15, 2025</p></body></html>'
        resp = MagicMock(status_code=200, text=html)
        with patch.object(c, '_make_request', return_value=resp):
            book = c.get_book_details('https://hachette.com/titles/a/t/9781234567890/')
            assert book is not None

    def test_crawl_method(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


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
            books = list(c.get_new_books(max_books=1))
            assert books == []

    def test_get_new_books_empty_page(self):
        c = self._make()
        resp = MagicMock(status_code=200, text='<html><body></body></html>')
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=1))
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


# ---------- HarperCollins ----------


class TestHarperCollinsCrawler:
    def _make(self):
        from app.services.publisher_crawler.harpercollins import HarperCollinsCrawler

        return HarperCollinsCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '哈珀柯林斯'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) > 0

    def test_is_url_allowed_no_parser(self):
        c = self._make()
        c._robots_parser = None
        assert c._is_url_allowed('https://harpercollins.com/') is True

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(max_books=1))
            assert books == []

    def test_get_new_books_empty_page(self):
        c = self._make()
        resp = MagicMock(status_code=200, text='<html><body></body></html>')
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_get_new_books_with_alt(self):
        c = self._make()
        html = """
        <html><body>
        <img alt="Great Book by Author Name (9780063445758)" src="/cover.jpg"/>
        </body></html>
        """
        resp = MagicMock(status_code=200, text=html)
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=5))
            assert len(books) >= 1

    def test_get_book_details_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            assert c.get_book_details('https://harpercollins.com/products/book') is None

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


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
            books = list(c.get_new_books(max_books=1))
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
        books = list(c.get_new_books(max_books=1))
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

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


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
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_get_new_books_success(self):
        c = self._make()
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
                        'publishedDate': '2025-01-01',
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
        books = list(c.get_new_books(max_books=1))
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

    def test_crawl(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


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
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


# ---------- PenguinRandomHouse ----------


class TestPenguinRandomHouseCrawler:
    def _make(self):
        from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler

        return PenguinRandomHouseCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '企鹅兰登'
        assert c.config.request_delay == 0.8

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) >= 10

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


# ---------- SimonSchuster ----------


class TestSimonSchusterCrawler:
    def _make(self):
        from app.services.publisher_crawler.simon_schuster import SimonSchusterCrawler

        return SimonSchusterCrawler()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '西蒙舒斯特'
        assert c.config.request_delay == 0.8

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert len(cats) >= 8

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


# ---------- PublisherRSSCrawler ----------


class TestPublisherRSSCrawler:
    def _make_rss_class(self):
        from app.services.publisher_crawler.rss_crawler import PublisherRSSCrawler

        class _TestRSS(PublisherRSSCrawler):
            PUBLISHER_NAME = '测试RSS'
            PUBLISHER_NAME_EN = 'Test RSS'
            PUBLISHER_WEBSITE = 'https://rss.com'
            CRAWLER_CLASS_NAME = 'TestRSSCrawler'
            FEED_URLS = ['https://rss.com/feed.xml']

            def get_categories(self):
                return []

        return _TestRSS

    def _make(self):
        return self._make_rss_class()()

    def test_init(self):
        c = self._make()
        assert c.PUBLISHER_NAME == '测试RSS'

    def test_get_categories(self):
        c = self._make()
        cats = c.get_categories()
        assert isinstance(cats, list)

    def test_get_new_books_no_feeds(self):
        from app.services.publisher_crawler.rss_crawler import PublisherRSSCrawler

        class _EmptyRSS(PublisherRSSCrawler):
            PUBLISHER_NAME = '空'
            PUBLISHER_NAME_EN = 'Empty'
            PUBLISHER_WEBSITE = 'https://empty.com'
            CRAWLER_CLASS_NAME = 'EmptyRSS'
            FEED_URLS = []

            def get_categories(self):
                return []

        c = _EmptyRSS()
        books = list(c.get_new_books(max_books=1))
        assert books == []

    def test_get_new_books_no_response(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)

    def test_get_new_books_rss_format(self):
        c = self._make()
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <item>
                <title>RSS Book</title>
                <link>https://rss.com/book/1</link>
                <description>A great book</description>
                <pubDate>Tue, 15 Jan 2025 10:00:00 +0000</pubDate>
                <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Author Name</dc:creator>
            </item>
        </channel>
        </rss>"""
        resp = MagicMock(status_code=200, text=rss_xml)
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=5))
            assert len(books) >= 1

    def test_get_new_books_atom_format(self):
        c = self._make()
        atom_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Test Atom Feed</title>
            <entry>
                <title>Atom Book</title>
                <link href="https://rss.com/book/2"/>
                <summary>An atom book</summary>
                <published>2025-01-15T10:00:00Z</published>
                <author><name>Atom Author</name></author>
            </entry>
        </feed>"""
        resp = MagicMock(status_code=200, text=atom_xml)
        with patch.object(c, '_make_request', return_value=resp):
            books = list(c.get_new_books(max_books=5))
            assert len(books) >= 1

    def test_parse_feed_invalid_xml(self):
        c = self._make()
        items = c._parse_feed('not xml')
        assert items == []

    def test_parse_feed_rss(self):
        c = self._make()
        rss = '<rss><channel><item><title>T</title><link>L</link></item></channel></rss>'
        items = c._parse_feed(rss)
        assert len(items) == 1
        assert items[0]['title'] == 'T'

    def test_parse_feed_atom(self):
        c = self._make()
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title></entry></feed>'
        items = c._parse_feed(atom)
        assert len(items) >= 1

    def test_crawl_books(self):
        c = self._make()
        with patch.object(c, '_make_request', return_value=None):
            books = c.crawl(max_books=1)
            assert isinstance(books, list)


# ---------- MixedCrawl4AICrawler ----------


class _TestMixedCrawler:
    """辅助：创建可实例化的 MixedCrawl4AI 子类"""

    pass


def _make_mixed():
    from app.services.publisher_crawler.mixed_crawl4ai_crawler import MixedCrawl4AICrawler

    class _TM(MixedCrawl4AICrawler):
        PUBLISHER_NAME = '测试混合'
        PUBLISHER_NAME_EN = 'Test Mixed'
        PUBLISHER_WEBSITE = 'https://mixed.com'
        CRAWLER_CLASS_NAME = 'TestMixed'
        NEW_RELEASES_URL = 'https://mixed.com/new'
        CATEGORY_MAP = {'fiction': '小说'}

        def get_categories(self):
            return [{'id': 'fiction', 'name': '小说'}]

    return _TM()


class TestMixedCrawlerInit:
    def test_init(self):
        c = _make_mixed()
        assert c.PUBLISHER_NAME == '测试混合'

    def test_check_crawl4ai(self):
        c = _make_mixed()
        assert isinstance(c._crawl4ai_available, bool)


class TestMixedCrawlerRequest:
    def test_make_request_with_fallback_success(self):
        c = _make_mixed()
        with patch.object(c, '_make_request') as m:
            m.return_value = MagicMock(status_code=200, text='<html><body></body></html>')
            soup, source = c._make_request_with_fallback('https://test.com')
            assert soup is not None
            assert source == 'requests'

    def test_make_request_with_fallback_crawl4ai(self):
        c = _make_mixed()
        c._crawl4ai_available = True
        with (
            patch.object(c, '_make_request', return_value=None),
            patch.object(c, '_crawl_with_crawl4ai', return_value='<html><body></body></html>'),
        ):
            soup, source = c._make_request_with_fallback('https://test.com')
            assert soup is not None
            assert source == 'crawl4ai'

    def test_make_request_with_fallback_all_fail(self):
        c = _make_mixed()
        c._crawl4ai_available = False
        with patch.object(c, '_make_request', return_value=None):
            soup, source = c._make_request_with_fallback('https://test.com')
            assert soup is None

    def test_crawl_with_crawl4ai_not_available(self):
        c = _make_mixed()
        c._crawl4ai_available = False
        assert c._crawl_with_crawl4ai('https://test.com') is None


class TestMixedCrawlerParsing:
    def test_parse_book_list_empty(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._parse_book_list(soup) == []

    def test_parse_book_list_with_items(self):
        c = _make_mixed()
        html = """
        <div class="product-item">
            <a href="/books/1">Title</a>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        books = c._parse_book_list(soup)
        assert isinstance(books, list)

    def test_parse_book_list_with_headings(self):
        c = _make_mixed()
        html = '<div><h2>Book Title</h2><a href="/book/1">link</a></div>'
        soup = BeautifulSoup(html, 'html.parser')
        books = c._parse_book_list(soup)
        assert isinstance(books, list)

    def test_extract_title(self):
        c = _make_mixed()
        html = '<html><body><h1 class="book-title">My Book</h1></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_title(soup) == 'My Book'

    def test_extract_title_fallback(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html><body><p>text</p></body></html>', 'html.parser')
        assert c._extract_title(soup) == 'Unknown Title'

    def test_extract_author(self):
        c = _make_mixed()
        html = '<html><body><div class="author-name">Author</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_author(soup) == 'Author'

    def test_extract_author_fallback(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html><body><p>text</p></body></html>', 'html.parser')
        assert c._extract_author(soup) == 'Unknown Author'

    def test_extract_description(self):
        c = _make_mixed()
        html = '<html><body><div class="description">Desc</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_description(soup) == 'Desc'

    def test_extract_description_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_description(soup) is None

    def test_extract_cover_url(self):
        c = _make_mixed()
        html = '<html><body><div class="book-cover"><img src="/cover.jpg"/></div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        url = c._extract_cover_url(soup)
        assert url is not None

    def test_extract_cover_url_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_cover_url(soup) is None

    def test_extract_category(self):
        c = _make_mixed()
        html = '<html><body><div class="category">fiction</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_category(soup) == '小说'

    def test_extract_category_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_category(soup) is None

    def test_extract_price(self):
        c = _make_mixed()
        html = '<html><body><div class="price">$29.99</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_price(soup) == '$29.99'

    def test_extract_price_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_price(soup) is None

    def test_extract_page_count(self):
        c = _make_mixed()
        html = '<html><body><div class="page-count">352 pages</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_page_count(soup) == 352

    def test_extract_page_count_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_page_count(soup) is None

    def test_extract_isbn_text(self):
        c = _make_mixed()
        html = '<html><body><div class="isbn">9781234567890</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_isbn_text(soup) is not None

    def test_extract_isbn_text_from_page(self):
        c = _make_mixed()
        html = '<html><body><p>ISBN: 9781234567890</p></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_isbn_text(soup) is not None

    def test_extract_isbn_text_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html><body><p>No ISBN</p></body></html>', 'html.parser')
        assert c._extract_isbn_text(soup) is None

    def test_extract_buy_links(self):
        c = _make_mixed()
        html = """
        <html><body>
        <div class="buy-buttons">
            <a href="https://amazon.com/dp/123">Buy on Amazon</a>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        links = c._extract_buy_links(soup)
        assert len(links) >= 1

    def test_extract_buy_links_empty(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html></html>', 'html.parser')
        assert c._extract_buy_links(soup) == []


class TestMixedCrawlerBooks:
    def test_get_new_books_empty(self):
        c = _make_mixed()
        with patch.object(c, '_make_request_with_fallback', return_value=(None, None)):
            books = list(c.get_new_books(max_books=1))
            assert books == []

    def test_get_book_details_none(self):
        c = _make_mixed()
        with patch.object(c, '_make_request_with_fallback', return_value=(None, None)):
            assert c.get_book_details('https://mixed.com/book/1') is None

    def test_get_book_details_success(self):
        c = _make_mixed()
        html = '<html><body><h1 class="book-title">Book</h1></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        with patch.object(c, '_make_request_with_fallback', return_value=(soup, 'requests')):
            book = c.get_book_details('https://mixed.com/book/1')
            assert book is not None

    def test_build_list_url_no_category(self):
        c = _make_mixed()
        url = c._build_list_url(None, 1)
        assert url == 'https://mixed.com/new'

    def test_build_list_url_with_category(self):
        c = _make_mixed()
        url = c._build_list_url('fiction', 1)
        assert 'category=fiction' in url

    def test_build_list_url_page2(self):
        c = _make_mixed()
        url = c._build_list_url(None, 2)
        assert 'page=2' in url

    def test_build_list_url_category_and_page(self):
        c = _make_mixed()
        url = c._build_list_url('fiction', 3)
        assert 'category=fiction' in url
        assert 'page=3' in url

    def test_extract_publication_date_from_element(self):
        c = _make_mixed()
        html = '<html><body><div class="publication-date">January 15, 2025</div></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_publication_date(soup) is not None

    def test_extract_publication_date_from_page_text(self):
        c = _make_mixed()
        html = '<html><body><p>On Sale: January 15, 2025</p></body></html>'
        soup = BeautifulSoup(html, 'html.parser')
        assert c._extract_publication_date(soup) is not None

    def test_extract_publication_date_none(self):
        c = _make_mixed()
        soup = BeautifulSoup('<html><body><p>No date</p></body></html>', 'html.parser')
        assert c._extract_publication_date(soup) is None

    def test_crawl_books_yields(self):
        c = _make_mixed()
        with patch.object(c, '_make_request_with_fallback', return_value=(None, None)):
            books = list(c.get_new_books(max_books=1))
            assert isinstance(books, list)
