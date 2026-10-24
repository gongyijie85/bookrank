"""The tab-details API caches data while retaining request validation and limits."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.schemas import BookMetadata
from app.routes.api import books as api_books
from app.services.user_service import UserService
from app.utils import api_helpers, service_helpers

ISBN = '9780143127550'
ENDPOINT = f'/api/book-details/{ISBN}'


@pytest.fixture
def sources(monkeypatch):
    google = Mock()
    google.fetch_book_details.return_value = {
        'details': 'Original details',
        'isbn_13': ISBN,
        'page_count': 321,
        'language': 'en',
        'publisher': 'Example publisher',
        'publication_dt': '2026-09-01',
    }
    metadata = Mock(return_value=SimpleNamespace(details_zh='已保存的简介'))
    translator = Mock()
    translator.translate.return_value = '同步翻译简介'
    monkeypatch.setattr(service_helpers, 'get_or_create_google_books_client', lambda: google)
    monkeypatch.setattr(api_books._user_service, 'get_book_metadata', metadata)
    monkeypatch.setattr(api_books, 'get_service', lambda name: translator if name == 'translation_service' else None)
    return google, metadata, translator


def test_repeat_return_to_uses_cached_data_and_builds_a_response_each_time(client, sources, monkeypatch):
    google, metadata, translator = sources
    success = Mock(wraps=api_books.APIResponse.success)
    monkeypatch.setattr(api_books.APIResponse, 'success', success)

    first = client.get(ENDPOINT, query_string={'return_to': '/awards?year=2026'})
    second = client.get(ENDPOINT, query_string={'return_to': '/award-book/1?return_to=/awards?year=2026'})

    assert first.status_code == second.status_code == 200
    assert first.get_json()['data'] == second.get_json()['data']
    google.fetch_book_details.assert_called_once_with(ISBN)
    metadata.assert_called_once_with(ISBN)
    translator.translate.assert_not_called()
    assert success.call_count == 2


def test_response_data_mutation_does_not_modify_the_cached_payload(client, sources, monkeypatch):
    original_success = api_books.APIResponse.success

    def success_with_mutation(data):
        response = original_success(data=data)
        data['details'] = 'Mutated by response consumer'
        data['buy_links']['changed'] = 'https://example.com'
        return response

    monkeypatch.setattr(api_books.APIResponse, 'success', success_with_mutation)

    first = client.get(ENDPOINT).get_json()['data']
    second = client.get(ENDPOINT).get_json()['data']

    assert first == second
    assert second['details'] == 'Original details'
    assert second['buy_links'] == {}
    sources[0].fetch_book_details.assert_called_once_with(ISBN)


def test_metadata_commit_invalidates_the_api_payload(client, db, sources, monkeypatch):
    google, _, _ = sources
    monkeypatch.setattr(api_books._user_service, 'get_book_metadata', UserService().get_book_metadata)
    metadata = BookMetadata(isbn=ISBN, title='Book', author='Author', details_zh='更新前简介')
    db.session.add(metadata)
    db.session.commit()
    assert client.get(ENDPOINT).get_json()['data']['details_zh'] == '更新前简介'

    metadata.details_zh = '更新后简介'
    db.session.commit()

    assert client.get(ENDPOINT).get_json()['data']['details_zh'] == '更新后简介'
    assert google.fetch_book_details.call_count == 2


@pytest.mark.parametrize('warm', [False, True])
@pytest.mark.parametrize('flushed', [False, True])
def test_uncommitted_metadata_does_not_enter_api_cache(client, db, sources, monkeypatch, warm, flushed):
    monkeypatch.setattr(api_books._user_service, 'get_book_metadata', UserService().get_book_metadata)
    metadata = BookMetadata(isbn=ISBN, title='Book', author='Author', details_zh='Committed details')
    db.session.add(metadata)
    db.session.commit()
    if warm:
        assert client.get(ENDPOINT).get_json()['data']['details_zh'] == 'Committed details'
    metadata.details_zh = 'Uncommitted details'
    if flushed:
        db.session.flush()

    assert client.get(ENDPOINT).get_json()['data']['details_zh'] == 'Uncommitted details'
    db.session.rollback()

    assert client.get(ENDPOINT).get_json()['data']['details_zh'] == 'Committed details'


@pytest.mark.parametrize(
    ('failure', 'status_code', 'message'),
    [
        ({}, 404, 'Book not found in Google Books'),
        (RuntimeError('no such table: api_cache'), 404, 'Book not found'),
        (RuntimeError('Google Books unavailable'), 500, 'Failed to fetch book details'),
    ],
)
def test_not_found_and_errors_are_not_cached(client, sources, failure, status_code, message):
    google, metadata, _ = sources
    google.fetch_book_details.side_effect = [failure, deepcopy(google.fetch_book_details.return_value)]

    first = client.get(ENDPOINT)
    second = client.get(ENDPOINT)
    third = client.get(ENDPOINT)

    assert first.status_code == status_code
    assert first.get_json()['message'] == message
    assert second.status_code == third.status_code == 200
    assert google.fetch_book_details.call_count == 2
    metadata.assert_called_once_with(ISBN)


def test_invalid_isbn_is_rejected_before_loading(client, sources):
    response = client.get('/api/book-details/invalid-isbn')

    assert response.status_code == 400
    assert response.get_json()['message'] == 'Invalid ISBN format'
    sources[0].fetch_book_details.assert_not_called()
    sources[1].assert_not_called()


def test_cached_api_data_does_not_bypass_rate_limits(client, app, sources, monkeypatch):
    limiter = Mock()
    limiter.is_allowed.side_effect = [True, True, False]
    limiter.get_retry_after.return_value = 60
    monkeypatch.setattr(api_helpers, 'get_rate_limiter', lambda *args: limiter)
    monkeypatch.setitem(app.config, 'TESTING', False)

    assert client.get(ENDPOINT).status_code == 200
    assert client.get(ENDPOINT).status_code == 200
    limited = client.get(ENDPOINT)

    assert limited.status_code == 429
    assert limiter.is_allowed.call_count == 3
    sources[0].fetch_book_details.assert_called_once_with(ISBN)
    sources[1].assert_called_once_with(ISBN)


def test_translation_and_cover_fallback_are_retained_in_cached_data(client, sources):
    google, metadata, translator = sources
    metadata.return_value = None

    first = client.get(ENDPOINT)
    second = client.get(ENDPOINT)

    assert first.status_code == second.status_code == 200
    data = second.get_json()['data']
    assert data['description'] == data['details_zh'] == '同步翻译简介'
    assert data['details'] == 'Original details'
    assert data['cover_url'] == f'https://covers.openlibrary.org/b/isbn/{ISBN}-L.jpg'
    assert data['page_count'] == 321
    google.fetch_book_details.assert_called_once_with(ISBN)
    translator.translate.assert_called_once_with('Original details', 'en', 'zh', field_type='details')
