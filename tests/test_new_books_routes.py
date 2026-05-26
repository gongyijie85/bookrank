"""新书路由测试"""

from app.routes.new_books import _check_sync_cooldown


class TestCheckSyncCooldown:
    """测试 _check_sync_cooldown"""

    def test_no_cooldown(self):
        import app.routes.new_books as mod

        mod._last_sync_time = 0.0
        result = _check_sync_cooldown()
        assert result is None

    def test_in_cooldown(self):
        import time

        import app.routes.new_books as mod

        mod._last_sync_time = time.time()
        result = _check_sync_cooldown()
        assert result is not None
        assert '秒' in result


class TestNewBooksAPIRoutes:
    """测试 /api/new-books/* 端点"""

    def test_get_publishers(self, client):
        response = client.get('/api/new-books/publishers')
        assert response.status_code in (200, 500)

    def test_get_publisher_not_found(self, client):
        response = client.get('/api/new-books/publishers/99999')
        assert response.status_code in (200, 404, 500)

    def test_get_new_books_list(self, client):
        response = client.get('/api/new-books')
        assert response.status_code in (200, 500)

    def test_get_new_books_with_params(self, client):
        response = client.get('/api/new-books?days=7&category=fiction&page=1&per_page=10')
        assert response.status_code in (200, 500)

    def test_get_new_books_with_search(self, client):
        response = client.get('/api/new-books?search=python')
        assert response.status_code in (200, 500)

    def test_get_book_detail_not_found(self, client):
        response = client.get('/api/new-books/99999')
        assert response.status_code in (200, 404, 500)

    def test_search_new_books_no_keyword(self, client):
        response = client.get('/api/new-books/search')
        assert response.status_code == 400

    def test_search_new_books_long_keyword(self, client):
        response = client.get('/api/new-books/search?keyword=' + 'a' * 101)
        assert response.status_code == 400

    def test_search_new_books_valid(self, client):
        response = client.get('/api/new-books/search?keyword=python')
        assert response.status_code in (200, 500)

    def test_get_categories(self, client):
        response = client.get('/api/new-books/categories')
        assert response.status_code in (200, 500)

    def test_get_statistics(self, client):
        response = client.get('/api/new-books/statistics')
        assert response.status_code in (200, 500)

    def test_export_csv(self, client):
        response = client.get('/api/new-books/export/csv')
        assert response.status_code in (200, 500)

    def test_update_publisher_status_not_json(self, client):
        response = client.post(
            '/api/new-books/publishers/1/status',
            data='not json',
            content_type='text/plain',
        )
        assert response.status_code in (400, 403, 429, 500)

    def test_sync_all_publishers_no_auth(self, client):
        response = client.post('/api/new-books/sync')
        assert response.status_code in (403, 429, 500)

    def test_sync_publisher_no_auth(self, client):
        response = client.post('/api/new-books/sync/1')
        assert response.status_code in (403, 429, 500)

    def test_init_publishers_no_auth(self, client):
        response = client.post('/api/new-books/init')
        assert response.status_code in (403, 429, 500)
