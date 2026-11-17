"""Google Books 出版社通道：inpublisher 两种写法的兜底。

Google Books 的 `inpublisher:` 是否接受带引号写法并不稳定。实测带引号查询返回空
`items` 时，日志只能说「无更多结果」，分不清是「该社真的没新书」还是「语法不认」。
这里在首页为空时自动换另一种写法重试，并把 totalItems 打进日志。
"""

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.publisher_crawler.base_crawler import CrawlRequest


def _volume(title: str, published: str) -> dict:
    return {
        'id': title.lower().replace(' ', '-'),
        'volumeInfo': {
            'title': title,
            'authors': ['Author'],
            'publishedDate': published,
            'industryIdentifiers': [{'type': 'ISBN_13', 'identifier': '9780000000001'}],
        },
    }


def _response(items: list, total: int) -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = {'totalItems': total, 'items': items}
    response.raise_for_status = MagicMock()
    return response


class TestInpublisherFallback:
    def _make(self):
        from app.services.publisher_crawler.google_books_publisher import (
            SimonSchusterGoogleCrawler,
        )

        return SimonSchusterGoogleCrawler()

    def test_falls_back_to_unquoted_form_when_first_query_is_empty(self):
        crawler = self._make()
        recent = date.today().isoformat()

        responses = [
            _response([], 0),  # 带引号写法：空
            _response([_volume('Fallback Book', recent)], 1),  # 去引号写法：有货
        ]
        queries: list[str] = []

        def fake_get(url, params=None, timeout=None):
            queries.append(params['q'])
            return responses.pop(0)

        with patch.object(crawler._session, 'get', side_effect=fake_get):
            books = list(crawler.get_new_books(CrawlRequest(max_books=5)).books)

        assert len(books) == 1
        assert books[0].title == 'Fallback Book'
        assert '"' in queries[0]
        assert '"' not in queries[1]

    def test_used_quoted_form_when_it_returns_items(self):
        crawler = self._make()
        recent = date.today().isoformat()
        queries: list[str] = []

        def fake_get(url, params=None, timeout=None):
            queries.append(params['q'])
            return _response([_volume('Quoted Book', recent)], 1)

        with patch.object(crawler._session, 'get', side_effect=fake_get):
            books = list(crawler.get_new_books(CrawlRequest(max_books=1)).books)

        assert len(books) == 1
        assert '"' in queries[0]
        # 第一种写法就命中，不该再发兜底请求
        assert all('"' in q for q in queries)
