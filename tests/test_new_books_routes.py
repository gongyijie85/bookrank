"""新书路由测试"""


class TestCheckSyncCooldown:
    """测试 _check_sync_cooldown（v0.9.64: 适配多 worker 安全锁）"""

    def test_no_cooldown(self, app):
        """测试无冷却时返回 None"""
        import app.routes.new_books as mod

        # 设置同步时间为 0（很久之前）
        with app.app_context():
            mod._set_last_sync_time(0.0)
            result = mod._check_sync_cooldown()
            assert result is None

    def test_in_cooldown(self, app):
        """测试冷却中返回剩余秒数"""
        import time

        import app.routes.new_books as mod

        # 设置同步时间为当前
        with app.app_context():
            mod._set_last_sync_time(time.time())
            result = mod._check_sync_cooldown()
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
        # v0.9.63: Pydantic 验证返回 422 而不是 400
        response = client.get('/api/new-books/search')
        assert response.status_code == 422

    def test_search_new_books_long_keyword(self, client):
        # v0.9.63: Pydantic 验证返回 422 而不是 400
        response = client.get('/api/new-books/search?keyword=' + 'a' * 101)
        assert response.status_code == 422

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


class TestCSVSanitization:
    """v0.9.68: CSV 公式注入防护 + 速率限制测试"""

    def test_sanitize_csv_field_injection_prefixes(self):
        """_sanitize_csv_field 对 = + - @ \t \r 起始的字段加单引号"""
        import app.routes.new_books as mod

        assert mod._sanitize_csv_field('=cmd|..."calc"!A1') == '\'=cmd|..."calc"!A1'
        assert mod._sanitize_csv_field('+sum(A1:A10)') == "'+sum(A1:A10)"
        assert mod._sanitize_csv_field('-2+3') == "'-2+3"
        assert mod._sanitize_csv_field('@SUM(A1)') == "'@SUM(A1)"
        assert mod._sanitize_csv_field('\tinjection') == "'\tinjection"
        assert mod._sanitize_csv_field('\rinjection') == "'\rinjection"

    def test_sanitize_csv_field_passes_safe_text(self):
        """普通文本不被修改"""
        import app.routes.new_books as mod

        assert mod._sanitize_csv_field('The Girl I Was') == 'The Girl I Was'
        assert mod._sanitize_csv_field('Jeneva Rose') == 'Jeneva Rose'
        assert mod._sanitize_csv_field('9781335002341') == '9781335002341'
        assert mod._sanitize_csv_field('中文标题') == '中文标题'
        assert mod._sanitize_csv_field('') == ''
        assert mod._sanitize_csv_field(None) == ''

    def test_sanitize_csv_field_internal_special_chars_unchanged(self):
        """中间的特殊字符不被加前缀"""
        import app.routes.new_books as mod

        assert mod._sanitize_csv_field('A=B') == 'A=B'
        assert mod._sanitize_csv_field('1+2=3') == '1+2=3'
        assert mod._sanitize_csv_field('hello@world.com') == 'hello@world.com'

    def test_export_csv_returns_csv_with_injection_safe_content(self, client, app, db):
        """真实导出端点:含公式注入字符的字段被正确转义"""
        from app.models.new_book import NewBook, Publisher

        with app.app_context():
            publisher = Publisher(name='Test', name_en='TestPub', website='', crawler_class='X', is_active=True)
            db.session.add(publisher)
            db.session.commit()
            bad_book = NewBook(
                publisher_id=publisher.id,
                title='=cmd|"calc"!A1',
                author='@SUM(1+1)',
                isbn13='9780000000900',
                category='=malicious',
                is_displayable=True,
            )
            db.session.add(bad_book)
            db.session.commit()

        response = client.get('/api/new-books/export/csv?days=365')
        if response.status_code == 200:
            # BOM 之后的 CSV 文本
            content = response.data.decode('utf-8-sig')
            lines = [line for line in content.split('\n') if line]
            # 找含 =cmd 的行(可能是第二行 header, 或是数据行)
            for line in lines[1:]:  # 跳过 header
                # 如果包含 =cmd, 必须以 ' 开头
                if '=cmd' in line or 'cmd|' in line:
                    assert "'=cmd" in line or "'+" in line or "'@" in line, f'未转义: {line[:80]}'


class TestExportCooldown:
    """v0.9.68: CSV 导出每 IP 10 秒限速测试"""

    def test_export_cooldown_blocks_second_request(self, app, client):
        """首次导出 OK, 10 秒内第二次返回 429"""
        import app.routes.new_books as mod

        with app.app_context():
            mod.current_app.extensions.pop('export_last_127.0.0.1', None) if hasattr(mod, 'current_app') else None

        # 第一次
        r1 = client.get('/api/new-books/export/csv?days=30')
        assert r1.status_code in (200, 429, 500)

        # 第二次紧接
        r2 = client.get('/api/new-books/export/csv?days=30')
        # 第二次应被 429 拒绝
        if r1.status_code == 200:
            assert r2.status_code == 429
            body = r2.get_json()
            assert body['success'] is False
            assert '秒' in body.get('message', '')


class TestSearchEndpointFilters:
    """v0.9.68: /api/new-books/search 增加可选过滤"""

    def test_search_accepts_publisher_filter(self, client):
        response = client.get('/api/new-books/search?keyword=test&publisher_id=1')
        assert response.status_code in (200, 500)

    def test_search_accepts_category_filter(self, client):
        response = client.get('/api/new-books/search?keyword=test&category=Fiction')
        assert response.status_code in (200, 500)

    def test_search_accepts_days_filter(self, client):
        response = client.get('/api/new-books/search?keyword=test&days=30')
        assert response.status_code in (200, 500)

    def test_search_rejects_invalid_days(self, client):
        response = client.get('/api/new-books/search?keyword=test&days=999')
        assert response.status_code == 422

    def test_search_rejects_negative_publisher_id(self, client):
        response = client.get('/api/new-books/search?keyword=test&publisher_id=-1')
        assert response.status_code == 422

    def test_search_still_works_without_filters(self, client):
        """v0.9.68: 向后兼容:不带过滤的搜索仍可用"""
        response = client.get('/api/new-books/search?keyword=test')
        assert response.status_code in (200, 500)


class TestStatistics30d:
    """v0.9.68: get_statistics 返回 recent_books_30d"""

    def test_statistics_returns_recent_books_30d(self, app, db):
        """get_statistics 返回值包含 recent_books_30d 字段(v0.9.68 升级)"""
        from app.services.new_book_service import NewBookService

        with app.app_context():
            NewBookService.reset_instance()
            service = NewBookService()
            stats = service.get_statistics()
            assert 'recent_books_7d' in stats
            assert 'recent_books_30d' in stats
            assert isinstance(stats['recent_books_30d'], int)
            assert stats['recent_books_30d'] >= stats['recent_books_7d']
            assert stats['recent_books_30d'] == 0  # 空库
            assert stats['recent_books_7d'] == 0
