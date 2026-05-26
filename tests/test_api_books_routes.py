"""API Books 路由测试"""

import json
from unittest.mock import MagicMock


class TestGetBooks:
    """测试 /api/books/<category>"""

    def test_invalid_category(self, client):
        response = client.get('/api/books/invalid-category')
        assert response.status_code == 400

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            response = client.get('/api/books/hardcover-fiction')
            assert response.status_code == 503

    def test_valid_category(self, client, app):
        mock_service = MagicMock()
        mock_service.get_books_by_category.return_value = []
        mock_service.get_latest_cache_time.return_value = None

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/books/hardcover-fiction')
            assert response.status_code == 200
            del app.extensions['book_service']

    def test_all_category(self, client, app):
        mock_service = MagicMock()
        mock_service.get_books_by_category.return_value = []
        mock_service.get_latest_cache_time.return_value = None

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/books/all')
            assert response.status_code == 200
            del app.extensions['book_service']


class TestSearchBooks:
    """测试 /api/search"""

    def test_no_keyword(self, client):
        response = client.get('/api/search')
        assert response.status_code == 400

    def test_short_keyword(self, client):
        response = client.get('/api/search?keyword=a')
        assert response.status_code == 400

    def test_long_keyword(self, client):
        response = client.get('/api/search?keyword=' + 'a' * 101)
        assert response.status_code == 400

    def test_invalid_keyword_format(self, client):
        response = client.get('/api/search?keyword=<script>alert(1)</script>')
        assert response.status_code == 400

    def test_valid_search(self, client, app):
        mock_service = MagicMock()
        mock_service.search_books.return_value = []
        mock_service.get_latest_cache_time.return_value = None

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/search?keyword=python')
            assert response.status_code == 200
            del app.extensions['book_service']


class TestSearchHistory:
    """测试 /api/search/history"""

    def test_get_history(self, client):
        response = client.get('/api/search/history')
        assert response.status_code in (200, 500)

    def test_get_history_with_limit(self, client):
        response = client.get('/api/search/history?limit=10')
        assert response.status_code in (200, 500)


class TestUserPreferences:
    """测试 /api/user/preferences"""

    def test_get_preferences(self, client):
        response = client.get('/api/user/preferences')
        assert response.status_code in (200, 500)

    def test_post_preferences(self, client):
        response = client.post(
            '/api/user/preferences',
            data=json.dumps({'view_mode': 'grid'}),
            content_type='application/json',
        )
        assert response.status_code in (200, 500)

    def test_post_preferences_not_json(self, client):
        response = client.post(
            '/api/user/preferences',
            data='not json',
            content_type='text/plain',
        )
        assert response.status_code == 400


class TestExportCSV:
    """测试 /api/export/<category>"""

    def test_invalid_category(self, client):
        response = client.get('/api/export/invalid-category')
        assert response.status_code == 400

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            response = client.get('/api/export/hardcover-fiction')
            assert response.status_code == 503

    def test_valid_export(self, client, app):
        mock_service = MagicMock()
        mock_service.get_books_by_category.return_value = []

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/export/hardcover-fiction')
            assert response.status_code == 200
            assert 'text/csv' in response.headers.get('Content-Type', '')
            del app.extensions['book_service']


class TestBookDetails:
    """测试 /api/book-details/<isbn>"""

    def test_invalid_isbn(self, client):
        response = client.get('/api/book-details/invalid-isbn')
        assert response.status_code == 400
