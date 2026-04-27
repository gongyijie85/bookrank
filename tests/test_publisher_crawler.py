"""
出版社爬虫模块单元测试

覆盖：
- BaseCrawler 通用方法（_clean_text, _extract_isbn, _parse_date, _parse_price, _truncate_description）
- BookInfo 数据类
- SimpleResponse 包装类
- PenguinRandomHouse 迁移验证
- SimonSchuster/Macmillan __init__ 修复验证
- 爬虫注册机制
- GoogleBooks/OpenLibrary 解析方法
"""
import inspect
from datetime import date
from unittest.mock import Mock

import pytest

from app.services.publisher_crawler.base_crawler import BaseCrawler, BookInfo, CrawlerConfig, SimpleResponse
from app.services.publisher_crawler import get_crawler_class, get_all_crawlers


class _TestCrawler(BaseCrawler):
    """可测试的 BaseCrawler 子类"""
    PUBLISHER_NAME = "Test"
    PUBLISHER_NAME_EN = "Test"
    PUBLISHER_WEBSITE = "https://example.com"
    CRAWLER_CLASS_NAME = "TestCrawler"

    def get_new_books(self, category=None, max_books=100):
        yield from []

    def get_book_details(self, book_url=""):
        return None

    def get_categories(self):
        return []


class TestBaseCrawlerMethods:
    """BaseCrawler 通用方法测试"""

    def setup_method(self):
        self.crawler = _TestCrawler()

    def test_clean_text_normal(self):
        assert self.crawler._clean_text("  hello  world  ") == "hello world"

    def test_clean_text_none(self):
        assert self.crawler._clean_text(None) == ""

    def test_clean_text_empty(self):
        assert self.crawler._clean_text("") == ""

    def test_extract_isbn13(self):
        isbn13, isbn10 = self.crawler._extract_isbn("ISBN: 9780134685991")
        assert isbn13 == "9780134685991"
        assert isbn10 is None

    def test_extract_isbn10(self):
        isbn13, isbn10 = self.crawler._extract_isbn("ISBN: 013468599X")
        assert isbn10 == "013468599X"

    def test_extract_isbn_none(self):
        isbn13, isbn10 = self.crawler._extract_isbn("no isbn here")
        assert isbn13 is None
        assert isbn10 is None

    def test_parse_date_iso(self):
        result = self.crawler._parse_date("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_parse_date_month_name(self):
        result = self.crawler._parse_date("January 15, 2024")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_year_only(self):
        result = self.crawler._parse_date("2024")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_none(self):
        assert self.crawler._parse_date(None) is None

    def test_parse_date_invalid(self):
        assert self.crawler._parse_date("not a date") is None

    def test_parse_price_dollar(self):
        assert self.crawler._parse_price("$28.99") == "$28.99"

    def test_parse_price_none(self):
        assert self.crawler._parse_price(None) is None

    def test_truncate_description_short(self):
        assert self.crawler._truncate_description("short") == "short"

    def test_truncate_description_long(self):
        long_text = "a" * 3000
        result = self.crawler._truncate_description(long_text)
        assert len(result) <= 2003
        assert result.endswith("...")

    def test_truncate_description_none(self):
        assert self.crawler._truncate_description(None) is None

    def test_context_manager(self):
        with _TestCrawler() as crawler:
            assert crawler is not None


class TestBookInfo:
    """BookInfo 数据类测试"""

    def test_to_dict(self):
        info = BookInfo(title="Test", author="Author")
        d = info.to_dict()
        assert d['title'] == "Test"
        assert d['author'] == "Author"
        assert d['isbn13'] is None

    def test_to_dict_with_date(self):
        info = BookInfo(title="Test", author="Author", publication_date=date(2024, 1, 15))
        d = info.to_dict()
        assert d['publication_date'] == "2024-01-15"

    def test_default_buy_links(self):
        info = BookInfo(title="Test", author="Author")
        assert info.buy_links == []


class TestSimpleResponse:
    """SimpleResponse 包装类测试"""

    def test_json_returns_data(self):
        resp = SimpleResponse({"key": "value"})
        assert resp.json() == {"key": "value"}

    def test_status_code_default(self):
        resp = SimpleResponse({})
        assert resp.status_code == 200

    def test_status_code_custom(self):
        resp = SimpleResponse({}, status_code=404)
        assert resp.status_code == 404


class TestPenguinRandomHouseMigration:
    """企鹅兰登爬虫迁移验证"""

    def test_inherits_from_mixed_crawl4ai(self):
        from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
        from app.services.publisher_crawler.mixed_crawl4ai_crawler import MixedCrawl4AICrawler
        assert issubclass(PenguinRandomHouseCrawler, MixedCrawl4AICrawler)

    def test_publisher_name(self):
        from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
        assert PenguinRandomHouseCrawler.PUBLISHER_NAME == "企鹅兰登"
        assert PenguinRandomHouseCrawler.CRAWLER_CLASS_NAME == "PenguinRandomHouseCrawler"

    def test_category_map_exists(self):
        from app.services.publisher_crawler.penguin_random_house import PenguinRandomHouseCrawler
        assert 'fiction' in PenguinRandomHouseCrawler.CATEGORY_MAP
        assert PenguinRandomHouseCrawler.CATEGORY_MAP['fiction'] == '小说'


class TestCrawlerInitBug:
    """爬虫 __init__ 重复定义 bug 修复验证"""

    def test_simon_schuster_no_duplicate_init(self):
        from app.services.publisher_crawler.simon_schuster import SimonSchusterCrawler
        source = inspect.getsource(SimonSchusterCrawler)
        init_count = source.count('def __init__')
        assert init_count == 1

    def test_macmillan_no_duplicate_init(self):
        from app.services.publisher_crawler.macmillan import MacmillanCrawler
        source = inspect.getsource(MacmillanCrawler)
        init_count = source.count('def __init__')
        assert init_count == 1

    def test_macmillan_request_delay(self):
        from app.services.publisher_crawler.macmillan import MacmillanCrawler
        crawler = MacmillanCrawler()
        assert crawler.config.request_delay == 1.3

    def test_simon_schuster_request_delay(self):
        from app.services.publisher_crawler.simon_schuster import SimonSchusterCrawler
        crawler = SimonSchusterCrawler()
        assert crawler.config.request_delay == 1.2


class TestCrawlerRegistry:
    """爬虫注册机制测试"""

    def test_registry_has_all_seven_crawlers(self):
        all_crawlers = get_all_crawlers()
        expected = [
            'OpenLibraryCrawler', 'GoogleBooksCrawler',
            'PenguinRandomHouseCrawler', 'SimonSchusterCrawler',
            'HachetteCrawler', 'HarperCollinsCrawler', 'MacmillanCrawler',
        ]
        for name in expected:
            assert name in all_crawlers, f"缺少爬虫: {name}"

    def test_get_crawler_class_returns_correct_type(self):
        cls = get_crawler_class('PenguinRandomHouseCrawler')
        assert cls is not None
        assert issubclass(cls, BaseCrawler)

    def test_get_crawler_class_unknown_returns_none(self):
        cls = get_crawler_class('NonExistentCrawler')
        assert cls is None


class TestGoogleBooksParsing:
    """Google Books 爬虫解析测试"""

    def setup_method(self):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        self.crawler = GoogleBooksCrawler()

    def test_is_recent_book_current_year(self):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        assert GoogleBooksCrawler._is_recent_book("2025-01-01", 2024) is True

    def test_is_recent_book_old(self):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        assert GoogleBooksCrawler._is_recent_book("2020-01-01", 2024) is False

    def test_is_recent_book_empty(self):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        assert GoogleBooksCrawler._is_recent_book("", 2024) is True

    def test_is_recent_book_invalid(self):
        from app.services.publisher_crawler.google_books import GoogleBooksCrawler
        assert GoogleBooksCrawler._is_recent_book("invalid", 2024) is True

    def test_parse_volume_info_complete(self):
        volume = {
            'title': 'Test Book',
            'authors': ['John Doe'],
            'description': 'A test book',
            'publishedDate': '2024-06-15',
            'pageCount': 300,
            'language': 'en',
            'industryIdentifiers': [
                {'type': 'ISBN_13', 'identifier': '9780134685991'},
                {'type': 'ISBN_10', 'identifier': '0134685991'},
            ],
            'imageLinks': {'thumbnail': 'https://example.com/cover.jpg'},
            'canonicalVolumeLink': 'https://books.google.com/books?id=test',
        }
        result = self.crawler._parse_volume_info(volume, 'fiction')
        assert result is not None
        assert result.title == 'Test Book'
        assert result.author == 'John Doe'
        assert result.isbn13 == '9780134685991'
        assert result.page_count == 300

    def test_parse_volume_info_minimal(self):
        volume = {'title': 'Minimal Book'}
        result = self.crawler._parse_volume_info(volume, 'fiction')
        assert result is not None
        assert result.title == 'Minimal Book'
        assert result.author == 'Unknown Author'

    def test_parse_volume_info_no_title(self):
        result = self.crawler._parse_volume_info({}, 'fiction')
        assert result is None


class TestOpenLibraryParsing:
    """Open Library 爬虫解析测试"""

    def setup_method(self):
        from app.services.publisher_crawler.open_library import OpenLibraryCrawler
        self.crawler = OpenLibraryCrawler()

    def test_parse_work_complete(self):
        work = {
            'title': 'Test Work',
            'author_name': ['Jane Doe'],
            'cover_id': 12345,
            'isbn': ['9780134685991'],
            'first_publish_year': 2024,
            'key': '/works/OL12345W',
        }
        result = self.crawler._parse_work(work, 'fiction')
        assert result is not None
        assert result.title == 'Test Work'
        assert result.author == 'Jane Doe'
        assert result.isbn13 == '9780134685991'
        assert '12345' in result.cover_url

    def test_parse_work_minimal(self):
        work = {'title': 'Minimal', 'author_name': ['Author']}
        result = self.crawler._parse_work(work, 'fiction')
        assert result is not None
        assert result.title == 'Minimal'

    def test_generate_buy_links_with_isbn(self):
        links = self.crawler._generate_buy_links('9780134685991', None, 'Test')
        assert len(links) >= 1
        assert links[0]['name'] == 'Amazon'

    def test_generate_buy_links_no_isbn(self):
        links = self.crawler._generate_buy_links(None, None, 'Test')
        assert len(links) == 0
