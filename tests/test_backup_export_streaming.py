"""Backup export streaming + api_cache cleanup scheduling regressions."""

import json

import pytest

from app.models.schemas import APICache


@pytest.fixture
def admin_headers(app):
    app.config['ADMIN_SECRET'] = 'test-admin-secret'
    return {'X-Admin-Secret': 'test-admin-secret'}


@pytest.fixture
def csrf_headers(client):
    resp = client.get('/api/csrf-token')
    token = resp.get_json()['data']['csrf_token']
    return {'X-CSRF-Token': token}


class TestBackupExportStreaming:
    def test_export_returns_valid_json(self, client, admin_headers, db):
        """上传备份导出为合法 JSON（流式 yield 拼接后需是完整 JSON 对象）。

        db fixture：SQLite :memory: 每测试重建表；流式 generator 惰性消费，
        因此必须持有 db 上下文直到 get_data() 完成。
        """
        resp = client.get('/api/admin/backup/export', headers=admin_headers)
        assert resp.status_code == 200
        data = json.loads(resp.get_data(as_text=True))
        assert set(data['tables'].keys()) == {
            'awards',
            'award_books',
            'weekly_reports',
            'translation_caches',
            'book_metadata',
            'search_histories',
        }
        # 每表 records 必须是列表（流式写出的 count 与 records 一致）
        for name, table in data['tables'].items():
            assert table['count'] == len(table['records']), name

    def test_export_requires_admin(self, client):
        resp = client.get('/api/admin/backup/export')
        assert resp.status_code in (401, 403)


class TestApiCacheCleanupTask:
    def test_clear_expired_removes_stale(self, app, db):
        from app.services.api_cache_service import get_api_cache_service

        svc = get_api_cache_service()
        db.session.add(
            APICache(
                api_source='nyt',
                request_key='expired',
                request_hash='e' * 64,
                response_data='{}',
                status_code=200,
                ttl_seconds=60,
                expires_at=__import__('datetime').datetime.now(__import__('datetime').UTC)
                - __import__('datetime').timedelta(hours=1),
                usage_count=1,
                last_used_at=__import__('datetime').datetime.now(__import__('datetime').UTC),
            )
        )
        db.session.commit()

        deleted = svc.clear_expired()
        # 至少删掉刚插入的过期行（其余按测试库状态浮动）
        remaining = APICache.query.filter_by(request_hash='e' * 64).count()
        assert remaining == 0
        assert deleted >= 1

    def test_cleanup_task_wired_in_setup(self, app):
        """_api_cache_expired_cleanup_task 应可执行且不抛异常。"""
        from app.setup import _api_cache_expired_cleanup_task

        _api_cache_expired_cleanup_task(app)  # 不应 raise
