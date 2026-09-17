"""OpenAPI spec endpoint tests (ROADMAP #1)."""

import json


def test_openapi_json_served(client):
    resp = client.get('/openapi.json')
    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))
    assert data['openapi'] == '3.1.0'
    assert data['info']['title'] == 'BookRank Public API'
    # 覆盖所有公开端点（与 /api/public echo 对齐）
    assert '/api/public/bestsellers' in data['paths']
    assert '/api/public/awards' in data['paths']
    assert '/api/public/book/{isbn}' in data['paths']
    assert '/api/public/new-books' in data['paths']
    assert '/api/public/reports/weekly/{date}' in data['paths']


def test_api_info_advertises_openapi(client):
    resp = client.get('/api/public/')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['openapi'] == '/openapi.json'
