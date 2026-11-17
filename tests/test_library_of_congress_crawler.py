"""美国国会图书馆爬虫：字段解析 + 请求参数（免费兜底新书源）。"""

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.publisher_crawler.base_crawler import CrawlRequest

RECORD = {
    'id': 'http://www.loc.gov/item/library-publications/the-invisible-host/',
    'title': 'The Invisible Host',
    'date': '2026-12-01',
    'contributor': ['gwen bristow', 'bruce manning'],
    'description': ['<p>A chilling locked room thriller.</p>'],
    'image_url': ['https://www.loc.gov/static/managed-content/9781464281082.jpg'],
    'language': ['English'],
    'subject': ['Fiction'],
    'item': {'isbn': ['9781464281082']},
}


class TestLibraryOfCongressCrawler:
    def _make(self):
        from app.services.publisher_crawler.library_of_congress import LibraryOfCongressCrawler

        return LibraryOfCongressCrawler()

    def test_metadata(self):
        crawler = self._make()
        assert crawler.PUBLISHER_NAME_EN == 'Library of Congress'
        assert crawler.CRAWLER_CLASS_NAME == 'LibraryOfCongressCrawler'
        # LOC robots.txt 写明 Crawl-Delay: 5
        assert crawler.config.request_delay == 5.0

    def test_parse_record_extracts_fields(self):
        book = self._make()._parse_record(RECORD)
        assert book is not None
        assert book.title == 'The Invisible Host'
        assert book.isbn13 == '9781464281082'
        assert book.publication_date == date(2026, 12, 1)
        assert book.author == 'gwen bristow, bruce manning'
        assert book.description == 'A chilling locked room thriller.'
        assert book.cover_url.endswith('.jpg')
        assert book.category == 'Fiction'

    def test_parse_record_skips_records_without_isbn(self):
        # 下游按 ISBN 去重，没有 ISBN 的记录不塞进数据里
        assert self._make()._parse_record({'title': 'No ISBN', 'item': {}}) is None
        assert self._make()._parse_record({'title': ''}) is None

    def test_parse_record_accepts_isbn10(self):
        book = self._make()._parse_record({'title': 'Old', 'item': {'isbn': ['0066620732']}})
        assert book is not None
        assert book.isbn10 == '0066620732'
        assert book.isbn13 is None

    def test_parse_date_variants(self):
        crawler = self._make()
        assert crawler._parse_date('2026-12-01') == date(2026, 12, 1)
        assert crawler._parse_date('2026-12') == date(2026, 12, 1)
        assert crawler._parse_date('2026') == date(2026, 1, 1)
        assert crawler._parse_date(None) is None
        assert crawler._parse_date('unknown') is None

    def test_get_new_books_requests_bounded_date_range(self):
        crawler = self._make()
        payload = {'results': [RECORD, {'title': 'No ISBN', 'item': {}}]}
        response = MagicMock()
        response.json.return_value = payload
        with patch.object(crawler, '_make_request', return_value=response) as request:
            books = list(crawler.get_new_books(CrawlRequest(max_books=10)).books)

        url = request.call_args[0][0]
        assert url.startswith('https://www.loc.gov/books/?')
        assert 'fo=json' in url
        assert 'sb=date_desc' in url
        assert 'dates=' in url
        assert 'c=' in url
        # 无 ISBN 的那条被跳过
        assert len(books) == 1

    def test_get_new_books_handles_missing_response(self):
        crawler = self._make()
        with patch.object(crawler, '_make_request', return_value=None):
            assert list(crawler.get_new_books(CrawlRequest(max_books=10)).books) == []
