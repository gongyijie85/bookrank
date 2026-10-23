from unittest.mock import Mock

import pytest
import requests

from app.services.publisher_crawler.base_crawler import BaseCrawler, CrawlerConfig, CrawlRequest
from app.services.publisher_crawler.google_books import GoogleBooksCrawler
from app.services.publisher_crawler.google_books_publisher import HachetteGoogleCrawler


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(BaseCrawler, '_init_robots_parser', lambda self: None)
    monkeypatch.setattr('app.services.publisher_crawler.base_crawler.time.sleep', lambda seconds: None)
    monkeypatch.setattr(GoogleBooksCrawler, '_quota_blocked_until', 0, raising=False)
    monkeypatch.setattr(GoogleBooksCrawler, '_validate_api_key', lambda self: False)


def test_swallowed_google_transport_failure_is_distinct_from_successful_empty():
    crawler = HachetteGoogleCrawler(CrawlerConfig(max_retries=0))
    crawler._session = Mock()
    crawler._session.get.side_effect = requests.Timeout('test timeout')
    failed = crawler.get_new_books(CrawlRequest(max_books=2))
    assert list(failed.books) == []
    assert failed.errors

    crawler._session.get.side_effect = None
    crawler._session.get.return_value = Mock(status_code=200, json=Mock(return_value={'items': []}))
    empty = crawler.get_new_books(CrawlRequest(max_books=2))
    assert list(empty.books) == []
    assert empty.errors == []


def test_google_429_stops_other_publishers_without_retry_storm():
    first = GoogleBooksCrawler(CrawlerConfig(max_retries=2))
    first._session = Mock()
    first._session.get.return_value = Mock(status_code=429, headers={'Retry-After': '3600'})
    outcome = first.get_new_books(CrawlRequest(max_books=2))
    assert list(outcome.books) == []
    assert outcome.errors
    assert first._session.get.call_count == 1

    second = HachetteGoogleCrawler(CrawlerConfig(max_retries=2))
    second._session = Mock()
    outcome = second.get_new_books(CrawlRequest(max_books=2))
    assert list(outcome.books) == []
    assert outcome.errors
    second._session.get.assert_not_called()


def test_google_transient_timeout_retries_with_bounded_attempts():
    crawler = GoogleBooksCrawler(CrawlerConfig(max_retries=1))
    crawler._session = Mock()
    ok = Mock(status_code=200, json=Mock(return_value={'items': []}))
    crawler._session.get.side_effect = [requests.Timeout('first timeout'), ok]
    result = crawler.get_new_books(CrawlRequest(max_books=2))
    assert list(result.books) == []
    assert result.errors == []
    assert crawler._session.get.call_count == 2


def test_google_rejected_validated_key_falls_back_once_without_key():
    crawler = GoogleBooksCrawler(CrawlerConfig(api_key='test-key', max_retries=0))
    crawler._key_validated = True
    crawler._key_is_valid = True
    rejected = Mock(status_code=400)
    rejected.raise_for_status.side_effect = requests.HTTPError('rejected key')
    accepted = Mock(status_code=200, json=Mock(return_value={'items': []}))
    replies = iter([rejected, accepted])
    calls = []

    def respond(*args, **kwargs):
        calls.append(dict(kwargs['params']))
        return next(replies)

    crawler._session = Mock()
    crawler._session.get.side_effect = respond
    result = crawler.get_new_books(CrawlRequest(max_books=2))
    assert list(result.books) == []
    assert result.errors == []
    assert len(calls) == 2
    assert calls[0]['key'] == 'test-key'
    assert 'key' not in calls[1]
    assert crawler._key_is_valid is False


def test_google_transport_retry_exhaustion_does_not_become_success_empty():
    crawler = GoogleBooksCrawler(CrawlerConfig(max_retries=1))
    crawler._session = Mock()
    crawler._session.get.side_effect = requests.Timeout('all requests timed out')
    result = crawler.get_new_books(CrawlRequest(max_books=2))
    assert list(result.books) == []
    assert result.errors
    assert crawler._session.get.call_count == 2


def test_transport_adapter_does_not_multiply_manual_retry_attempts():
    crawler = GoogleBooksCrawler(CrawlerConfig(max_retries=3))
    assert crawler._session.get_adapter('https://').max_retries.total == 0


@pytest.mark.parametrize('exception_type', [requests.HTTPError, requests.RequestException, RuntimeError])
def test_request_errors_never_log_credentials_or_query(exception_type, caplog):
    import logging
    import secrets

    token, username, password = (secrets.token_hex(12) for _ in range(3))
    target = f'https://{username}:{password}@example.invalid/resource?api_key={token}#fragment'
    crawler = GoogleBooksCrawler(CrawlerConfig(max_retries=0))
    crawler._session = Mock()
    crawler._session.request.side_effect = exception_type(f'failed prepared request {target}')
    with caplog.at_level(logging.DEBUG):
        assert crawler._make_request(target) is None
    assert all(value not in caplog.text for value in (token, username, password))
    assert 'api_key=' not in caplog.text
    assert 'example.invalid/resource' in caplog.text
    assert exception_type.__name__ in caplog.text
