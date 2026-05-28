"""管理增强 API 路由测试（阶段4: v0.9.31）"""

import json


class TestCrawlerRun:
    """POST /api/admin/crawler/run/<publisher_name>"""

    def test_publisher_not_found(self, client, admin_headers):
        response = client.post(
            '/api/admin/crawler/run/不存在的出版社',
            data=json.dumps({'max_books': 5}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False
        assert response.status_code == 404

    def test_without_auth(self, client):
        response = client.post(
            '/api/admin/crawler/run/test',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)


class TestCrawlerStatus:
    """GET /api/admin/crawler/status"""

    def test_get_status(self, client, admin_headers):
        response = client.get('/api/admin/crawler/status', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'publishers' in data['data']
        assert 'total_publishers' in data['data']
        assert 'active_crawlers' in data['data']

    def test_without_auth(self, client):
        response = client.get('/api/admin/crawler/status')
        assert response.status_code in (401, 403)


class TestSystemStatus:
    """GET /api/admin/system/status"""

    def test_get_system_status(self, client, admin_headers):
        response = client.get('/api/admin/system/status', headers=admin_headers)
        data = json.loads(response.data)
        assert data['success'] is True

        system = data['data']
        assert 'process' in system
        assert 'pid' in system['process']
        assert 'memory_rss_mb' in system['process']
        assert 'memory_percent' in system['process']

        assert 'database' in system
        assert 'type' in system['database']

        assert 'cache' in system
        assert 'uptime_seconds' in system
        assert 'timestamp' in system

    def test_process_metrics_positive(self, client, admin_headers):
        response = client.get('/api/admin/system/status', headers=admin_headers)
        data = json.loads(response.data)
        process = data['data']['process']
        assert process['memory_rss_mb'] >= 0
        assert process['threads'] >= 1

    def test_without_auth(self, client):
        response = client.get('/api/admin/system/status')
        assert response.status_code in (401, 403)


class TestBackupExport:
    """GET /api/admin/backup/export"""

    def test_export_returns_json(self, client, admin_headers):
        response = client.get('/api/admin/backup/export', headers=admin_headers)
        assert response.status_code == 200
        assert 'application/json' in response.content_type

    def test_export_has_structure(self, client, admin_headers):
        response = client.get('/api/admin/backup/export', headers=admin_headers)
        data = json.loads(response.data)
        assert 'exported_at' in data
        assert 'tables' in data
        assert isinstance(data['tables'], dict)

    def test_export_includes_known_tables(self, client, admin_headers):
        response = client.get('/api/admin/backup/export', headers=admin_headers)
        data = json.loads(response.data)
        expected_tables = ['awards', 'award_books']
        for table in expected_tables:
            assert table in data['tables']

    def test_without_auth(self, client):
        response = client.get('/api/admin/backup/export')
        assert response.status_code in (401, 403)


class TestBackupImport:
    """POST /api/admin/backup/import"""

    def test_import_invalid_format(self, client, admin_headers):
        response = client.post(
            '/api/admin/backup/import',
            data=json.dumps({'invalid': True}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is False

    def test_import_empty_data(self, client, admin_headers):
        response = client.post(
            '/api/admin/backup/import',
            data=json.dumps({'tables': {}}),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['total'] == 0

    def test_import_with_records(self, client, admin_headers):
        import_data = {
            'tables': {
                'awards': {
                    'count': 1,
                    'records': [{'name': '测试奖项', 'category_count': 5}],
                },
            },
        }
        response = client.post(
            '/api/admin/backup/import',
            data=json.dumps(import_data),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True

    def test_import_unknown_table_ignored(self, client, admin_headers):
        import_data = {
            'tables': {
                'nonexistent_table': {'records': [{'x': 1}]},
            },
        }
        response = client.post(
            '/api/admin/backup/import',
            data=json.dumps(import_data),
            content_type='application/json',
            headers=admin_headers,
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['total'] == 0

    def test_without_auth(self, client):
        response = client.post(
            '/api/admin/backup/import',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code in (401, 403)
