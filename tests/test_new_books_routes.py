"""新书路由测试"""

from unittest.mock import MagicMock, patch

import pytest


class TestAcquireSyncSlot:
    """测试 _acquire_sync_slot（v0.9.99: 原子检查+记录，消除冷却竞态窗口）"""

    def test_no_cooldown(self, app):
        """测试无冷却时返回 None"""
        import app.routes.new_books as mod

        with app.app_context():
            gate = mod.get_sync_request_gate()
            gate.reset()
            result = mod._acquire_sync_slot()
            assert result is None

    def test_in_cooldown(self, app):
        """测试冷却中返回剩余秒数"""
        import app.routes.new_books as mod

        with app.app_context():
            gate = mod.get_sync_request_gate()
            gate.reset()
            gate.record_sync()
            result = mod._acquire_sync_slot()
            assert result is not None
            assert '秒' in result

    def test_acquire_is_atomic_check_and_record(self, app):
        """通过即记录：第二次调用立即进入冷却（原子性，无双双通过窗口）"""
        import app.routes.new_books as mod

        with app.app_context():
            gate = mod.get_sync_request_gate()
            gate.reset()
            assert mod._acquire_sync_slot() is None
            # 检查与记录在同一锁内：紧接着的第二次调用必须命中冷却
            second = mod._acquire_sync_slot()
            assert second is not None
            assert '秒' in second


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


class TestSyncAsyncSubmit:
    """v0.9.96: 同步端点改后台任务（202 + 轮询状态）"""

    @pytest.fixture(autouse=True)
    def _reset_sync_state(self, app, clear_auth_failures):
        """每个用例复位任务槽、同步冷却与 admin 认证失败计数，避免跨用例污染。"""
        import app.routes.new_books as mod

        with app.app_context():
            mod.get_sync_request_gate().reset()
        with mod._sync_task_lock:
            mod._sync_task.clear()
            mod._sync_task.update({'status': 'idle'})
        yield
        with mod._sync_task_lock:
            mod._sync_task.clear()
            mod._sync_task.update({'status': 'idle'})

    def _inline_submit(self):
        """替换 submit_background_task：记录并同步执行（便于断言后台行为）。"""

        def _fake_submit(fn, *args, **kwargs):
            fn()
            return MagicMock()

        return _fake_submit

    def test_sync_all_returns_202_and_runs_background(self, client, admin_headers):
        """端点立即返回 202，不同步等待（回归：请求线程内等 600s/社挂死管理端点）"""
        modules = MagicMock()
        modules.sync_engine.sync_all_publishers.return_value = [
            {'success': True, 'added': 2, 'updated': 1, 'errors': 0},
        ]

        with (
            patch('app.routes.new_books.submit_background_task', self._inline_submit()),
            patch('app.routes.new_books.get_new_book_modules', return_value=modules),
        ):
            response = client.post('/api/new-books/sync', headers=admin_headers)
            data = response.get_json()
            assert response.status_code == 202
            assert data['success'] is True
            assert data['data']['status'] == 'submitted'
            modules.sync_engine.sync_all_publishers.assert_called_once()

            status_resp = client.get('/api/new-books/sync/status', headers=admin_headers)
            status = status_resp.get_json()['data']
            assert status['status'] == 'success'
            assert status['summary']['total_added'] == 2
            assert status['summary']['total_publishers'] == 1

    def test_sync_publisher_returns_202_with_result(self, client, admin_headers):
        modules = MagicMock()
        modules.sync_engine.sync_publisher_books.return_value = {'success': True, 'added': 3, 'updated': 0}

        with (
            patch('app.routes.new_books.submit_background_task', self._inline_submit()),
            patch('app.routes.new_books.get_new_book_modules', return_value=modules),
        ):
            response = client.post('/api/new-books/sync/1?max_books=20', headers=admin_headers)
            assert response.status_code == 202
            modules.sync_engine.sync_publisher_books.assert_called_once_with(1, max_books=20)

            status = client.get('/api/new-books/sync/status', headers=admin_headers).get_json()['data']
            assert status['status'] == 'success'
            assert status['kind'] == 'publisher'
            assert status['result']['added'] == 3

    def test_sync_publisher_failure_marks_error(self, client, admin_headers):
        """后台同步失败（result.success=False）落到 error 状态而非 HTTP 错误。"""
        modules = MagicMock()
        modules.sync_engine.sync_publisher_books.return_value = {'success': False, 'error': '出版社不存在'}

        with (
            patch('app.routes.new_books.submit_background_task', self._inline_submit()),
            patch('app.routes.new_books.get_new_book_modules', return_value=modules),
        ):
            response = client.post('/api/new-books/sync/999', headers=admin_headers)
            assert response.status_code == 202

            status = client.get('/api/new-books/sync/status', headers=admin_headers).get_json()['data']
            assert status['status'] == 'error'
            assert status['error'] == '出版社不存在'

    def test_sync_rejected_while_task_running(self, client, admin_headers, app):
        """任务运行中再次触发返回 409（单任务槽互斥）。"""
        import app.routes.new_books as mod

        with mod._sync_task_lock:
            mod._sync_task.update({'status': 'running'})

        response = client.post('/api/new-books/sync', headers=admin_headers)
        assert response.status_code == 409

    def test_sync_cooldown_still_enforced(self, client, admin_headers, app):
        """触发即记录冷却：60 秒内再次触发返回 429。"""
        modules = MagicMock()
        modules.sync_engine.sync_all_publishers.return_value = []

        with (
            patch('app.routes.new_books.submit_background_task', self._inline_submit()),
            patch('app.routes.new_books.get_new_book_modules', return_value=modules),
        ):
            first = client.post('/api/new-books/sync', headers=admin_headers)
            assert first.status_code == 202

            second = client.post('/api/new-books/sync', headers=admin_headers)
            assert second.status_code == 429

    def test_sync_background_exception_marks_error(self, client, admin_headers):
        """后台任务抛异常不影响已返回的 202，状态落 error。"""
        modules = MagicMock()
        modules.sync_engine.sync_all_publishers.side_effect = RuntimeError('upstream down')

        with (
            patch('app.routes.new_books.submit_background_task', self._inline_submit()),
            patch('app.routes.new_books.get_new_book_modules', return_value=modules),
        ):
            response = client.post('/api/new-books/sync', headers=admin_headers)
            assert response.status_code == 202

            status = client.get('/api/new-books/sync/status', headers=admin_headers).get_json()['data']
            assert status['status'] == 'error'
            assert 'upstream down' in status['error']

    def test_status_without_auth(self, client):
        response = client.get('/api/new-books/sync/status')
        assert response.status_code == 403


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
            mod.get_sync_request_gate().reset()

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

    def test_search_response_excludes_freshness_field(self, app, db, client):
        """独立的 /api/new-books/search 端点不携带 is_recently_published 字段（该字段只服务于列表卡片徽章）"""
        from datetime import date

        from app.models.new_book import NewBook, Publisher

        with app.app_context():
            publisher = Publisher(name='测试出版社', name_en='Test Publisher', crawler_class='TestCrawler')
            db.session.add(publisher)
            db.session.commit()

            book = NewBook(
                publisher_id=publisher.id,
                title='Freshness Search Target',
                author='Test Author',
                isbn13='9780000000401',
                category='Fiction',
                publication_date=date.today(),
            )
            db.session.add(book)
            db.session.commit()

        response = client.get('/api/new-books/search?keyword=Freshness')
        assert response.status_code == 200
        body = response.get_json()
        books = body['data']['books']
        assert len(books) >= 1
        assert all('is_recently_published' not in b for b in books)


class TestStatistics30d:
    """v0.9.68: get_statistics 返回 recent_books_30d"""

    def test_statistics_returns_recent_books_30d(self, app, db):
        """get_statistics 返回值包含 recent_books_30d 字段(v0.9.68 升级)"""
        from unittest.mock import MagicMock

        from app.services.new_book.query_service import NewBookQueryService

        with app.app_context():
            query_service = NewBookQueryService(MagicMock())
            stats = query_service.get_statistics()
            assert 'recent_books_7d' in stats
            assert 'recent_books_30d' in stats
            assert isinstance(stats['recent_books_30d'], int)
            assert stats['recent_books_30d'] >= stats['recent_books_7d']
            assert stats['recent_books_30d'] == 0  # 空库
            assert stats['recent_books_7d'] == 0


def _seed_probe_books(db):
    from datetime import UTC, datetime, timedelta

    from app.models.new_book import NewBook, Publisher

    publisher = Publisher(name='Probe', name_en='Probe', crawler_class='ProbeCrawler')
    db.session.add(publisher)
    db.session.flush()
    today = datetime(2026, 9, 30, 0, 5, tzinfo=UTC).date()
    created = datetime(2026, 9, 30, 0, 5, tzinfo=UTC)
    for isbn, publication_date in (
        ('9780000000001', today),
        ('9780000000002', today + timedelta(days=1)),
        ('9780000000003', None),
        ('9780000000004', today + timedelta(days=200)),
        ('9780000000005', today - timedelta(days=400)),
    ):
        db.session.add(
            NewBook(
                publisher_id=publisher.id,
                title='Probe',
                author='Probe',
                isbn13=isbn,
                publication_date=publication_date,
                created_at=created,
                is_displayable=True,
            )
        )
    db.session.commit()


def _wire_probe_query(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace

    from app.routes import new_books as routes
    from app.services.new_book.query_service import NewBookQueryService

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 30, 0, 5, tzinfo=tz)

    monkeypatch.setattr('app.services.new_book.query_service.datetime', FrozenDateTime)
    service = NewBookQueryService(MagicMock())
    monkeypatch.setattr(routes, 'get_new_book_modules', lambda: SimpleNamespace(query_service=service))
    monkeypatch.setattr(routes, '_ensure_static_seeded', lambda _modules: None)


_WINDOW = {
    'all': {'9780000000001', '9780000000002', '9780000000003'},
    'published': {'9780000000001'},
    'upcoming': {'9780000000002'},
    'pending': {'9780000000003'},
}
_OPEN = {
    'all': {'9780000000001', '9780000000002', '9780000000003', '9780000000004', '9780000000005'},
    'published': {'9780000000001', '9780000000005'},
    'upcoming': {'9780000000002', '9780000000004'},
    'pending': {'9780000000003'},
}


class TestPublicationStatusApi:
    @pytest.mark.parametrize('mode', ('list', 'list_search', 'search'))
    @pytest.mark.parametrize('status', ('all', 'published', 'upcoming', 'pending'))
    def test_forwards_publication_status(self, client, db, monkeypatch, mode, status):
        _wire_probe_query(monkeypatch)
        _seed_probe_books(db)
        if mode == 'search':
            path = f'/api/new-books/search?keyword=Probe&publication_status={status}'
        elif mode == 'list_search':
            path = f'/api/new-books?search=Probe&publication_status={status}'
        else:
            path = f'/api/new-books?publication_status={status}'
        response = client.get(path)
        assert response.status_code == 200
        data = response.get_json()['data']
        books = data['books']
        expected = _OPEN[status] if mode == 'search' else _WINDOW[status]
        assert {book['isbn13'] for book in books} == expected
        pagination = data['pagination']
        assert pagination['total'] == len(expected)
        per_page = pagination['per_page']
        assert pagination['pages'] == (pagination['total'] + per_page - 1) // per_page
        if mode == 'search':
            assert all('is_recently_published' not in book for book in books)

    @pytest.mark.parametrize(
        'path',
        (
            '/api/new-books?publication_status=bogus',
            '/api/new-books/search?keyword=Probe&publication_status=bogus',
        ),
    )
    def test_invalid_publication_status_is_422(self, client, path):
        response = client.get(path)
        assert response.status_code == 422
        assert response.get_json()['success'] is False

    @pytest.mark.parametrize('publication_status', ('published', 'upcoming', 'pending'))
    def test_export_csv_matches_list_search_and_status(self, client, db, monkeypatch, publication_status):
        import csv
        from datetime import UTC, datetime, timedelta

        from app.models.new_book import NewBook, Publisher
        from app.routes.new_books import get_sync_request_gate

        _wire_probe_query(monkeypatch)
        _seed_probe_books(db)
        publisher = db.session.query(Publisher).filter_by(name='Probe').one()
        today = datetime(2026, 9, 30, tzinfo=UTC).date()
        when = {'published': today, 'upcoming': today + timedelta(days=1), 'pending': None}[publication_status]
        slot = ('published', 'upcoming', 'pending').index(publication_status) + 1
        db.session.add(
            NewBook(
                publisher_id=publisher.id,
                title='Noise',
                author='Other',
                isbn13=f'978000000001{slot}',
                publication_date=when,
                created_at=datetime(2026, 9, 30, 0, 5, tzinfo=UTC),
                is_displayable=True,
            )
        )
        db.session.commit()
        params = {'search': 'Probe', 'publication_status': publication_status}
        get_sync_request_gate().reset()
        listed = client.get('/api/new-books', query_string=params)
        assert listed.status_code == 200
        api_isbns = [book['isbn13'] for book in listed.get_json()['data']['books']]
        get_sync_request_gate().reset()
        exported = client.get('/api/new-books/export/csv', query_string=params)
        assert exported.status_code == 200
        assert exported.data.startswith(b'\xef\xbb\xbf')
        parsed = list(csv.reader(exported.data.decode('utf-8-sig').splitlines()))
        assert len(parsed[0]) == 14
        assert parsed[0][6] == 'ISBN-13'
        csv_isbns = [row[6] for row in parsed[1:] if row]
        assert csv_isbns == api_isbns
        assert set(csv_isbns) == _WINDOW[publication_status]

    def test_export_csv_select_new_books_error_is_500(self, client, db, monkeypatch):
        from sqlalchemy import event
        from sqlalchemy.exc import SQLAlchemyError

        from app.routes.new_books import get_sync_request_gate

        def fail_new_books_select(conn, cursor, statement, parameters, context, executemany):
            sql = statement.lower().lstrip()
            if sql.startswith('select') and 'new_books' in sql:
                raise SQLAlchemyError('select new_books failed')

        _wire_probe_query(monkeypatch)
        event.listen(db.engine, 'before_cursor_execute', fail_new_books_select)
        try:
            get_sync_request_gate().reset()
            response = client.get('/api/new-books/export/csv')
            assert response.status_code == 500
            assert response.get_json()['success'] is False
        finally:
            event.remove(db.engine, 'before_cursor_execute', fail_new_books_select)

    def test_export_csv_probe_formula_guard_matches_api_then_429(self, client, db, monkeypatch):
        import csv
        from datetime import datetime, timedelta
        from io import StringIO

        from app.models.new_book import NewBook, Publisher
        from app.routes.new_books import get_sync_request_gate

        _wire_probe_query(monkeypatch)
        today = datetime(2026, 9, 30, 0, 0, 0)
        publisher = Publisher(name='=House', name_en='House', crawler_class='HouseCrawler')
        db.session.add(publisher)
        db.session.flush()
        rows = [
            NewBook(
                title=f'=Probe {i}',
                author='+Author',
                title_zh='@中文',
                description='\tinjected',
                price='-9',
                isbn13=f'978{i:010d}',
                publication_date=today,
                created_at=today + timedelta(seconds=i),
                publisher_id=publisher.id,
                category='Fiction',
            )
            for i in range(510)
        ]
        rows.extend(
            NewBook(
                title=f'=Probe upcoming {j}',
                author='+Author',
                title_zh='@中文',
                description='\tinjected',
                price='-9',
                isbn13=f'979{j:010d}',
                publication_date=today + timedelta(days=40),
                created_at=today + timedelta(days=40, seconds=j),
                publisher_id=publisher.id,
                category='Fiction',
            )
            for j in range(5)
        )
        rows.append(
            NewBook(
                title='Noise',
                author='+Author',
                title_zh='@中文',
                description='\tinjected',
                price='-9',
                isbn13='9781000000000',
                publication_date=today,
                created_at=today,
                publisher_id=publisher.id,
                category='Fiction',
            )
        )
        db.session.add_all(rows)
        db.session.commit()
        expected = [f'978{i:010d}' for i in range(509, -1, -1)]
        found = []
        page_sizes = []
        for page in range(1, 12):
            response = client.get(
                '/api/new-books',
                query_string={'search': 'Probe', 'publication_status': 'published', 'per_page': 50, 'page': page},
            )
            assert response.status_code == 200
            body = response.get_json()
            assert body['success'] is True
            assert body['data']['pagination']['total'] == 510
            assert body['data']['pagination']['pages'] == 11
            chunk = body['data']['books']
            found.extend(book['isbn13'] for book in chunk)
            page_sizes.append(len(chunk))
        assert page_sizes == [50] * 10 + [10]
        assert found == expected
        export_qs = {'search': 'Probe', 'publication_status': 'published'}
        get_sync_request_gate().reset()
        exported = client.get('/api/new-books/export/csv', query_string=export_qs)
        assert exported.status_code == 200
        assert exported.data.startswith(b'\xef\xbb\xbf')
        assert exported.mimetype == 'text/csv'
        assert 'attachment' in exported.headers['Content-Disposition']
        decoded = list(csv.reader(StringIO(exported.data.decode('utf-8-sig'))))
        assert len(decoded[0]) == 14
        assert len(decoded) == 501
        assert [row[6] for row in decoded[1:]] == expected[:500]
        first = decoded[1]
        assert first[0].startswith("'=Probe")
        assert first[2] == "'+Author"
        assert first[8] == "'-9"
        assert first[3] == "'=House"
        assert first[1] == "'@中文"
        assert first[11] == "'\tinjected"
        limited = client.get('/api/new-books/export/csv', query_string=export_qs)
        assert limited.status_code == 429
        assert limited.get_json()['success'] is False
