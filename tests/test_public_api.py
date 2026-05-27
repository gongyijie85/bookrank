"""Public API 路由测试"""

import json
from unittest.mock import MagicMock, patch

from app.models.new_book import Publisher


class TestApiInfo:
    """测试 /api/public/ 端点"""

    def test_api_info(self, client):
        response = client.get('/api/public/')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'endpoints' in data['data']
        assert data['data']['version'] == '1.2.0'


class TestGetAllBestsellers:
    """测试 /api/public/bestsellers"""

    def test_service_unavailable(self, client, app):
        with app.app_context():
            app.extensions.pop('book_service', None)
            response = client.get('/api/public/bestsellers')
            data = json.loads(response.data)
            assert data['success'] is False

    def test_with_mock_service(self, client, app):
        mock_service = MagicMock()
        mock_service.get_books_by_category.return_value = []
        mock_service.get_latest_cache_time.return_value = None

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/public/bestsellers')
            assert response.status_code == 200
            del app.extensions['book_service']


class TestSearchBestsellers:
    """测试 /api/public/bestsellers/search"""

    def test_no_keyword(self, client):
        response = client.get('/api/public/bestsellers/search')
        data = json.loads(response.data)
        assert data['success'] is False

    def test_short_keyword(self, client):
        response = client.get('/api/public/bestsellers/search?keyword=a')
        data = json.loads(response.data)
        assert data['success'] is False

    def test_invalid_keyword_format(self, client):
        response = client.get('/api/public/bestsellers/search?keyword=<script>')
        data = json.loads(response.data)
        assert data['success'] is False

    def test_with_mock_service(self, client, app):
        mock_service = MagicMock()
        mock_service.search_books.return_value = []

        with app.app_context():
            app.extensions['book_service'] = mock_service
            response = client.get('/api/public/bestsellers/search?keyword=python')
            assert response.status_code == 200
            del app.extensions['book_service']


class TestGetBookDetails:
    """测试 /api/public/book/<isbn>"""

    def test_invalid_isbn(self, client):
        response = client.get('/api/public/book/invalid-isbn')
        data = json.loads(response.data)
        assert data['success'] is False

    def test_book_not_found(self, client, app):
        mock_service = MagicMock()
        mock_service.get_books_by_category.return_value = []

        with app.app_context():
            app.extensions['book_service'] = mock_service
            with patch('app.routes.public_api._award_service') as mock_award:
                mock_award.find_award_book_by_isbn.return_value = None
                response = client.get('/api/public/book/9780000000000')
                data = json.loads(response.data)
                assert data['success'] is False
            del app.extensions['book_service']


class TestGetWeeklyReportByDate:
    """测试 /api/public/reports/weekly/<date>"""

    def test_invalid_date_format(self, client):
        response = client.get('/api/public/reports/weekly/not-a-date')
        data = json.loads(response.data)
        assert data['success'] is False


class TestGetNewBooks:
    """测试 /api/public/new-books"""

    def test_empty_new_books(self, client, db):
        response = client.get('/api/public/new-books')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['books'] == []
        assert data['data']['total'] == 0

    def test_new_books_pagination(self, client, db):
        response = client.get('/api/public/new-books?page=1&per_page=10')
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['page'] == 1
        assert data['data']['per_page'] == 10

    def test_new_books_with_category_filter(self, client, db):
        response = client.get('/api/public/new-books?category=fiction')
        data = json.loads(response.data)
        assert data['success'] is True

    def test_new_books_publisher_not_found(self, client, db):
        response = client.get('/api/public/new-books/nonexistent-publisher')
        data = json.loads(response.data)
        assert data['success'] is False
        assert response.status_code == 404

    def test_new_books_by_publisher(self, client, db, app):
        with app.app_context():
            pub = Publisher(name='测试出版社', name_en='TestPub', crawler_class='RssCrawler', is_active=True)
            db.session.add(pub)
            db.session.commit()
            response = client.get('/api/public/new-books/测试出版社')
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['data']['publisher']['name'] == '测试出版社'


class TestGetRecommendations:
    """测试 /api/public/recommendations"""

    def test_empty_recommendations(self, client, db):
        response = client.get('/api/public/recommendations')
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'recommendations' in data['data']

    def test_recommendations_limit(self, client, db):
        response = client.get('/api/public/recommendations?limit=5')
        data = json.loads(response.data)
        assert data['success'] is True
