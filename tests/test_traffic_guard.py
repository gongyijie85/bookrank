"""Regressions for public API shutdown and runaway HTML crawling."""

import logging
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app.utils.rate_limiter import IPRateLimiter


class RelatedLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'a' and ('related-book-card' in classes or 'm-related-book-card' in classes):
            self.links.append(attrs.get('href', ''))


def test_public_api_disabled_without_breaking_website_endpoints(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'PUBLIC_API_ENABLED', False)

    assert client.get('/api/public/bestsellers').status_code == 404
    assert client.get('/openapi.json').status_code == 404
    assert client.get('/api/category-books?category=hardcover-fiction').status_code == 200
    assert client.get('/health').status_code == 200


def test_nested_award_return_stops_crawlers_before_loading_book(client, caplog):
    nested = '/award-book/2?lang=zh&return_to=%2Fawards'
    query = urlencode({'lang': 'zh', 'return_to': nested})
    with caplog.at_level(logging.WARNING), patch('app.services.award_book_service.AwardBookService') as service:
        response = client.get(
            '/award-book/1?' + query,
            headers={'CF-Connecting-IP': '198.51.100.9', 'X-Forwarded-For': 'invalid, 192.0.2.8'},
            environ_base={'REMOTE_ADDR': '203.0.113.14'},
        )

    assert response.status_code == 410
    assert 'Location' not in response.headers
    assert response.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert len(response.data) < 150
    assert 'href="/award-book/1?lang=zh"' in response.get_data(as_text=True)
    assert 'return_to' not in response.get_data(as_text=True)
    assert '203.0.113.14' in caplog.text
    assert 'reported_cf_ip=198.51.100.9' in caplog.text
    assert 'reported_forwarded=192.0.2.8' in caplog.text
    service.assert_not_called()


@pytest.mark.parametrize('mobile', [False, True])
def test_related_award_links_do_not_grow_nested_return_paths(client, mobile):
    book = MagicMock()
    book.id = 1
    book.title = book.display_title = 'Test Book'
    book.title_zh = '测试书名'
    book.is_displayable = True
    book.author = 'Test Author'
    book.isbn13 = '9781234567890'
    book.publisher = 'Test Publisher'
    book.description = 'Test description'
    book.award = None
    service = MagicMock()
    service.get_award_book_by_id.return_value = book
    recommendations = MagicMock()
    recommendations.get_similarity_recommendations.return_value = {
        'recommendations': [
            {
                'id': 2,
                'title': 'Related Book',
                'title_zh': '相关图书',
                'author': 'Author',
                'year': 2023,
                'category': 'Fiction',
                'cover_url': None,
                'isbn13': '9789999999999',
            }
        ]
    }
    query = urlencode({'lang': 'zh', 'return_to': '/awards?year=2025'})
    headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile'} if mobile else {}
    with (
        patch('app.services.award_book_service.AwardBookService', return_value=service),
        patch('app.routes.main.get_or_create_recommendation_service', return_value=recommendations),
    ):
        response = client.get('/award-book/1?' + query, headers=headers)

    assert response.status_code == 200
    parser = RelatedLinkParser()
    parser.feed(response.get_data(as_text=True))
    assert parser.links
    assert parse_qs(urlsplit(parser.links[0]).query)['return_to'] == ['/award-book/1']


def test_page_limit_uses_trusted_proxy_client_address(app, client, monkeypatch, caplog):
    monkeypatch.setitem(app.config, 'TESTING', False)
    original = app.wsgi_app
    app.wsgi_app = ProxyFix(original, x_for=1)
    limiter = MagicMock()
    limiter.is_allowed.return_value = False
    limiter.get_retry_after.return_value = 30
    try:
        with caplog.at_level(logging.WARNING), patch('app.routes.main.get_rate_limiter', return_value=limiter):
            response = client.get(
                '/award-book/1',
                headers={'X-Forwarded-For': '203.0.113.1, 8.8.8.8'},
                environ_base={'REMOTE_ADDR': '10.0.0.5'},
            )
    finally:
        app.wsgi_app = original

    assert response.status_code == 429
    assert response.headers['Retry-After'] == '30'
    limiter.is_allowed.assert_called_once_with('8.8.8.8')
    assert '8.8.8.8' in caplog.text


def test_page_limit_is_per_client_and_returns_a_small_429(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'TESTING', False)
    limiter = IPRateLimiter(max_requests=2, window_seconds=60)
    query = urlencode({'return_to': '/award-book/2?return_to=%2Fawards'})
    with patch('app.routes.main.get_rate_limiter', return_value=limiter):
        first = client.get('/award-book/1?' + query, environ_base={'REMOTE_ADDR': '8.8.8.8'})
        second = client.get('/award-book/1?' + query, environ_base={'REMOTE_ADDR': '8.8.8.8'})
        blocked = client.get('/award-book/1?' + query, environ_base={'REMOTE_ADDR': '8.8.8.8'})
        other = client.get('/award-book/1?' + query, environ_base={'REMOTE_ADDR': '1.1.1.1'})

    assert [first.status_code, second.status_code, blocked.status_code, other.status_code] == [410, 410, 429, 410]
    assert len(blocked.data) < 100


def test_private_proxy_address_does_not_throttle_all_visitors(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'TESTING', False)
    query = urlencode({'return_to': '/award-book/2?return_to=%2Fawards'})
    with patch('app.routes.main.get_rate_limiter') as get_limiter:
        response = client.get('/award-book/1?' + query, environ_base={'REMOTE_ADDR': '10.0.0.5'})

    assert response.status_code == 410
    get_limiter.assert_not_called()


def test_website_category_api_is_rate_limited(app, client, monkeypatch):
    monkeypatch.setitem(app.config, 'TESTING', False)
    limiter = MagicMock()
    limiter.is_allowed.return_value = False
    limiter.get_retry_after.return_value = 30
    with patch('app.routes.main.get_rate_limiter', return_value=limiter):
        response = client.get('/api/category-books?category=hardcover-fiction', environ_base={'REMOTE_ADDR': '8.8.8.8'})

    assert response.status_code == 429
