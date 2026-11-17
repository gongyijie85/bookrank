"""Google Books 每分钟配额节流：日配额没满也会 429。

GCP 配额页只显示 `Queries per day`（1000），很容易让人以为"配额没动就没事"。
实际还有 `Queries per minute per user`（100），7 个爬虫并发跑会瞬间打满，
表现为 429，而不是配额耗尽。
"""

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.publisher_crawler.base_crawler import CrawlRequest


def _volume(title: str, published: str) -> dict:
    return {
        'id': title.lower(),
        'volumeInfo': {
            'title': title,
            'authors': ['Author'],
            'publishedDate': published,
            'industryIdentifiers': [{'type': 'ISBN_13', 'identifier': '9780000000002'}],
        },
    }


def _response(items: list, total: int, status: int = 200) -> MagicMock:
    response = MagicMock(status_code=status)
    response.json.return_value = {'totalItems': total, 'items': items}
    response.raise_for_status = MagicMock()
    return response


class TestMinuteQuotaThrottle:
    def _make(self):
        from app.services.publisher_crawler.google_books_publisher import (
            SimonSchusterGoogleCrawler,
        )

        return SimonSchusterGoogleCrawler()

    def test_waits_when_window_is_full(self):
        crawler = self._make()
        calls = {'allowed': [False, False, True], 'sleeps': [], 'retry': 5}

        class FakeLimiter:
            def is_allowed(self):
                return calls['allowed'].pop(0)

            def get_retry_after(self):
                return calls['retry']

        with (
            patch('app.services.publisher_crawler.google_books._QUOTA_LIMITER', FakeLimiter()),
            patch(
                'app.services.publisher_crawler.google_books.time.sleep',
                side_effect=lambda seconds: calls['sleeps'].append(seconds),
            ),
        ):
            crawler._acquire_quota()

        assert calls['sleeps'] == [5, 5]

    def test_retries_once_on_429(self):
        crawler = self._make()
        recent = date.today().isoformat()
        responses = [
            _response([], 0, status=429),
            _response([_volume('After Retry', recent)], 1),
        ]

        with (
            patch.object(crawler._session, 'get', side_effect=lambda *a, **k: responses.pop(0)),
            patch.object(crawler, '_acquire_quota'),
        ):
            books = list(crawler.get_new_books(CrawlRequest(max_books=1)).books)

        assert len(books) == 1
        assert books[0].title == 'After Retry'
